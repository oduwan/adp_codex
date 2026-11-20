"""Bounded private provenance for installed operator authorities and recovery."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat

from .config import load_json, safe_path
from .discovery_schema import digest
from .guard_types import Attestation
from .operator_profile import private_file, Verified
from .schema import encode, fields, require
from .storage import locked, sync_directory

PREFIX = 'operator-proof:'
SOURCE = 'operator-source:'


class OperatorEvidence:
    """Content-addressed private receipts; no raw credential or worker transcript.

    This store conveys provenance, never execution permission or a new M2 fact.
    Missing history is an error. Recovered effects still use accepted journals.
    """
    def __init__(self, profile):
        self.profile = profile
        self.directory = safe_path(profile.state / 'authority')

    def prepare(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._check()

    def _check(self):
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                'Owned private operator evidence required')

    def _put(self, prefix, body):
        self._check()
        raw = encode(body, 1048576)
        name = digest(body)
        path = self.directory / (prefix + name + '.json')
        with locked(self.directory):
            entries = list(self.directory.iterdir())
            require(len(entries) <= 513 and all(p.name == 'lock' or p.is_file() and not p.is_symlink()
                    for p in entries), 'Operator evidence capacity/layout is unavailable')
            if path.exists():
                require(load_json(path,1048576) == body, 'Retained operator evidence differs')
                return name
            require(len(entries) < 513 and sum(p.stat().st_size for p in entries) + len(raw) <= 16*1024*1024,
                    'Operator evidence capacity exhausted; retain history and reconcile')
            descriptor = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            sync_directory(self.directory)
        return name

    def read(self, reference):
        self._check()
        require(type(reference) is str and reference.startswith((PREFIX,SOURCE)), 'Invalid operator evidence reference')
        prefix = 'proof-' if reference.startswith(PREFIX) else 'source-'
        fingerprint = reference.split(':',1)[1]
        require(len(fingerprint)==64 and all(c in '0123456789abcdef' for c in fingerprint), 'Invalid operator evidence digest')
        body=private_file(self.directory/(prefix+fingerprint+'.json'))
        require(digest(body)==fingerprint, 'Operator provenance digest differs')
        return body

    def source(self, verified):
        require(type(verified) is Verified and verified.document['kind'] != 'credential',
                'Do not copy credentials into execution provenance')
        return SOURCE+self._put('source-',verified.document)

    def retained_source(self, reference, *, kind, current=False):
        document=self.read(reference)
        return self.profile.trust.verify_document(document,kind,self.profile.repository_id,current=current)

    def find(self, purpose, subject):
        self._check()
        matches=[]
        paths=list(self.directory.iterdir())
        require(len(paths)<=513,'Operator evidence capacity exhausted')
        for path in paths:
            if not path.name.startswith('proof-'): continue
            body=private_file(path)
            require(path.name=='proof-'+digest(body)+'.json','Retained operator receipt differs')
            if (body.get('purpose'),body.get('subject'))==(purpose,subject):
                proof=Attestation(body['principal'],PREFIX+digest(body),subject)
                require(self.verify(proof,purpose=purpose,subject=subject),'Retained proof is unavailable')
                matches.append(proof)
        require(len(matches)<=1,'Ambiguous retained provenance')
        return matches[0] if matches else None

    def attest(self, purpose, subject, principal, *, provenance=(), binding=None):
        """Internal primitive; callers must establish the exact typed proof first."""
        body={'schema_version':1,'repository_id':self.profile.repository_id,
            'profile_id':self.profile.identifier,'profile_digest':self.profile.fingerprint,
            'issuer':self.profile.payload['authority'],'principal':principal,'purpose':purpose,
            'subject':subject,'provenance':list(provenance),'binding':binding or {}}
        secret=self.profile.trust.key(body['issuer'],'automation',body['repository_id'])
        body['signature']=hmac.new(secret,('adp/operator-receipt/v1:'+digest(body)).encode(),hashlib.sha256).hexdigest()
        return Attestation(principal,PREFIX+self._put('proof-',body),subject)

    def verify(self, evidence, *, purpose, subject):
        try:
            self.profile.live()
            require(type(evidence) is Attestation and evidence.subject==subject,'Operator proof subject differs')
            body=self.read(evidence.reference)
            fields(body,'schema_version repository_id profile_id profile_digest issuer principal purpose subject provenance binding signature')
            require(body['schema_version']==1 and body['repository_id']==self.profile.repository_id
                and body['issuer']==self.profile.payload['authority']
                and body['profile_id']==self.profile.identifier and body['profile_digest']==self.profile.fingerprint
                and body['principal']==evidence.reviewer and body['purpose']==purpose and body['subject']==subject,
                'Operator proof domain or enrollment differs')
            secret=self.profile.trust.key(body['issuer'],'automation',body['repository_id'])
            unsigned={k:v for k,v in body.items() if k!='signature'}
            expected=hmac.new(secret,('adp/operator-receipt/v1:'+digest(unsigned)).encode(),hashlib.sha256).hexdigest()
            require(hmac.compare_digest(expected,body['signature']),'Operator receipt authentication failed')
            # Historical source evidence is authenticated, not made freshly valid.
            # Admission/provider callers retain their own current-time checks.
            for reference in body['provenance']:
                document=self.read(reference)
                self.profile.trust.verify_document(document,document['kind'],self.profile.repository_id,current=False)
            return True
        except Exception:
            return False
