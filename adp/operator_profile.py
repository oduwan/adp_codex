"""Installed data profiles and authenticated project feeds, never target code."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import stat
import time

from .config import Config, load_json, remote_identity, safe_path
from .discovery_schema import digest, typed
from .errors import AuthorityError
from .execution_privacy import credential_shaped
from .git import value, git
from .policy_schema import branch, ref, sha
from .policy_types import Operation
from .project_validation_types import RequiredCheck, Phase
from .schema import encode, fields, require, string
from .storage import atomic, locked

ROLES = {'operator', 'automation', 'project-policy', 'scope-reviewer', 'project-check', 'token-issuer'}
KINDS = {'profile': 'operator', 'revocations': 'operator', 'policy': 'project-policy',
    'assessment': 'scope-reviewer', 'project-evidence': 'project-check', 'credential': 'token-issuer',
    'scope-addition': 'operator', 'decision': 'scope-reviewer', 'operator-decision': 'operator'}
SUPPORTED = {Operation.INSPECT, Operation.EDIT, Operation.STAGE, Operation.COMMIT,
    Operation.VALIDATE, Operation.PUSH, Operation.PR, Operation.MERGE, Operation.REPORT, Operation.TICKET_EDIT}


def private_file(path, *, limit=1048576):
    string(str(path),4096)
    path = safe_path(Path(path).absolute())
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077
            and info.st_nlink == 1 and info.st_size <= limit, 'Use an owned protected regular operator file')
    return load_json(path, limit)


def file_digest(path):
    return hashlib.sha256(encode(private_file(path), 1048576)).hexdigest()


def signed_subject(document):
    return digest({k: v for k, v in document.items() if k != 'signature'})


@dataclass(frozen=True)
class Verified:
    document: dict
    fingerprint: str
    principal: str

    @property
    def payload(self): return self.document['payload']
    @property
    def issued_at(self): return self.document['issued_at']
    @property
    def expires_at(self): return self.document['expires_at']


class Trust:
    """Explicit local trust root. It is never resolved from a project profile."""
    def __init__(self, path, *, clock=None):
        self.path = safe_path(Path(path).absolute())
        self.clock = clock or (lambda: int(time.time()))
        self.fingerprint = file_digest(self.path)
        self._root()

    def _root(self):
        root = private_file(self.path, limit=65536)
        fields(root, 'schema_version principals')
        require(type(root['schema_version']) is int and root['schema_version'] == 1 and type(root['principals']) is list
                and 1 <= len(root['principals']) <= 16, 'Unsupported operator trust root')
        principals, keys = {}, set()
        for row in root['principals']:
            fields(row, 'id roles repositories key_file')
            string(row['id'], 128)
            require(row['id'] not in principals and type(row['roles']) is list and row['roles']
                    and set(row['roles']) <= ROLES and len(row['roles']) == len(set(row['roles'])), 'Invalid canonical operator principal')
            require('scope-reviewer' not in row['roles'] or row['roles']==['scope-reviewer'],
                    'Independent semantic reviewer cannot alias another installed role')
            require(type(row['repositories']) is list and 1 <= len(row['repositories']) <= 16
                    and all(type(x) is str and x for x in row['repositories']), 'Explicit trust repository scopes required')
            key_data = private_file(row['key_file'], limit=1024)
            fields(key_data, 'schema_version key_hex')
            require(type(key_data['schema_version']) is int and key_data['schema_version'] == 1 and type(key_data['key_hex']) is str
                    and len(key_data['key_hex']) == 64, 'Invalid protected verifier key')
            try: secret = bytes.fromhex(key_data['key_hex'])
            except ValueError: raise AuthorityError('Invalid protected verifier key') from None
            require(len(secret) == 32 and secret not in keys, 'Key aliases cannot impersonate independent principals')
            keys.add(secret); principals[row['id']] = (row, secret)
        return principals

    def key(self, principal, role, repository):
        require(file_digest(self.path) == self.fingerprint, 'Operator trust root changed; re-enroll explicitly')
        row, secret = self._root().get(principal, ({}, b''))
        require(role in row.get('roles', ()) and repository in row.get('repositories', ()), 'Principal role or project scope is not authenticated')
        return secret

    def verify_document(self, document, kind, repository, *, current=True):
        fields(document, 'schema_version kind signer issued_at expires_at payload signature')
        require(type(document['schema_version']) is int and document['schema_version'] == 1 and document['kind'] == kind and kind in KINDS
                and type(document['payload']) is dict and document['payload'].get('repository_id') == repository,
                'Signed operator evidence kind/repository differs')
        issued, expires = document['issued_at'], document['expires_at']
        require(type(issued) is int and type(expires) is int and 0 <= issued < expires
                and expires - issued <= 3600 and (not current or issued <= self.clock() < expires),
                'Operator/project evidence is expired or not current')
        secret = self.key(document['signer'], KINDS[kind], repository)
        expected = hmac.new(secret, ('adp/operator/v1:' + signed_subject(document)).encode(), hashlib.sha256).hexdigest()
        require(type(document['signature']) is str and hmac.compare_digest(expected, document['signature']),
                'Operator/project evidence signature is not authenticated')
        return Verified(document, digest(document), document['signer'])

    def read(self, path, kind, repository, *, current=True):
        return self.verify_document(private_file(path), kind, repository, current=current)


@dataclass(frozen=True)
class TaskProfile:
    issue_id: str
    number: int
    task_id: str
    slug: str
    workspace: Path
    expected_revision: str


@dataclass(frozen=True)
class OperatorProfile:
    path: Path
    evidence: Verified
    trust: Trust
    repository_id: str
    tasks: tuple[TaskProfile, ...]
    checks: tuple[RequiredCheck, ...]

    @property
    def payload(self): return self.evidence.payload
    @property
    def identifier(self): return self.payload['id']
    @property
    def fingerprint(self): return self.evidence.fingerprint
    @property
    def state(self): return Path(self.payload['memory']['private_state'])
    @property
    def delegation(self): return self.payload['delegation']

    def live(self, *, retain=False):
        current = self.trust.read(self.path, 'profile', self.repository_id)
        require(current.fingerprint == self.fingerprint, 'Installed delegation changed; re-enroll explicitly')
        revocation = self.trust.read(self.payload['providers']['revocations'], 'revocations', self.repository_id)
        body = revocation.payload
        fields(body, 'repository_id sequence revoked')
        require(type(body['sequence']) is int and body['sequence'] >= 0 and type(body['revoked']) is list
                and all(type(x) is str for x in body['revoked']), 'Invalid current revocation inventory')
        require(self.payload['window']['issued_at'] <= self.trust.clock() < self.payload['window']['expires_at'], 'Finite operator window expired')
        watermark=self.state/'revocation.json'
        def compare():
            if watermark.exists():
                previous=private_file(watermark)
                fields(previous,'sequence digest')
                require(type(previous['sequence']) is int and body['sequence']>=previous['sequence']
                    and (body['sequence']!=previous['sequence'] or previous['digest']==revocation.fingerprint),
                    'Revocation rollback or conflicting sequence refused')
        if retain:
            with locked(self.state):
                compare()
                next_value={'sequence':body['sequence'],'digest':revocation.fingerprint}
                if not watermark.exists() or private_file(watermark)!=next_value:
                    atomic(watermark,encode(next_value))
        else: compare()
        require(self.identifier not in body['revoked'], 'Project delegation is revoked')
        return revocation

    def memory_config(self):
        m = self.payload['memory']
        cfg = Config.discover(Path(m['repo']), remote=m['remote'], repository_id=self.repository_id,
            branch=m['branch'], storage=Path(m['storage']))
        require(cfg.root==Path(m['repo']),'Select the actual coordination Git root')
        endpoint = value(cfg.root, 'remote', 'get-url', cfg.remote)
        require(remote_identity(endpoint, cfg.root).startswith('file:'),
                'Accepted network CAS requires a separate local coordination remote')
        require(value(Path(remote_identity(endpoint, cfg.root)[5:]), 'rev-parse', '--is-bare-repository') == 'true',
                'Select an existing local bare coordination remote')
        return cfg

    def project_config(self, task):
        cfg = Config.discover(task.workspace, remote=self.payload['repository']['remote'], repository_id=self.repository_id)
        require(cfg.root==task.workspace,'Select the actual product Git worktree root')
        endpoint = 'https://github.com/' + self.payload['repository']['name']
        actual = value(cfg.root, 'remote', 'get-url', cfg.remote)
        require(actual in (endpoint, endpoint + '.git'), 'Project remote differs from the enrolled canonical GitHub endpoint')
        require(value(cfg.root, 'symbolic-ref', 'HEAD') in self.delegation['branches'], 'Checkout is outside delegated feature branches')
        return cfg


def load_profile(path, trust_path, *, clock=None, retain_revocation=False, recover_initial_setup=False):
    try:
        return _load_profile(path,trust_path,clock=clock,retain_revocation=retain_revocation,recover_initial_setup=recover_initial_setup)
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError):
        raise AuthorityError('Malformed protected operator configuration; inspect the closed schema') from None


def _load_profile(path, trust_path, *, clock=None, retain_revocation=False,recover_initial_setup=False):
    trust = Trust(trust_path, clock=clock)
    path = safe_path(Path(path).absolute()); raw = private_file(path, limit=65536)
    rid = raw.get('payload', {}).get('repository_id')
    string(rid)
    verified = trust.verify_document(raw, 'profile', rid)
    p = verified.payload
    fields(p, 'id repository_id authority repository memory window delegation providers tasks checks')
    string(p['id'], 128); string(p['authority'], 128)
    trust.key(p['authority'], 'automation', rid)
    require(p['authority']!=verified.principal,'Operator delegation cannot be automation self-approval')
    r, m, w, d, providers = (p[k] for k in ('repository', 'memory', 'window', 'delegation', 'providers'))
    fields(r, 'name node_id database_id remote'); fields(m, 'repo remote branch storage private_state owner')
    fields(w, 'id issued_at expires_at maximum_rounds maximum_tasks maximum_parallel')
    fields(d, 'issues operations branches merge_mode merge_methods merge_envelope ticket_envelope allow_setup allow_claim reviews')
    fields(providers, 'policy assessment decisions decision_socket revocations validation credentials')
    from .network_git import GitHubTarget
    require(type(r['database_id']) is int and str(r['database_id']) == rid, 'M4/M1 canonical database identity must match')
    GitHubTarget(rid, r['node_id'], r['database_id'], *r['name'].split('/'), 'validation-only')
    string(r['remote'], 128); branch(m['branch']); string(m['remote'],128); string(m['owner'],128)
    require(type(w['id']) is str and len(w['id']) == 64 and all(c in '0123456789abcdef' for c in w['id']), 'Exact finite window identity required')
    require(type(w['issued_at']) is int and type(w['expires_at']) is int and verified.issued_at <= w['issued_at'] < w['expires_at'] <= verified.expires_at,
            'Window cannot extend the signed project delegation')
    for name, maximum in (('maximum_rounds',32),('maximum_tasks',8),('maximum_parallel',4)):
        require(type(w[name]) is int and 1 <= w[name] <= maximum, 'Operator budget exceeds accepted finite bounds')
    require(type(d['issues']) is list and 1 <= len(d['issues']) <= 8 and len(d['issues']) == len(set(d['issues'])), 'Explicit finite issue scope required')
    require(type(d['operations']) is list and d['operations'] and len(d['operations']) == len(set(d['operations']))
            and set(d['operations']) <= SUPPORTED, 'Unsupported or ambiguous delegated operation')
    require(type(d['branches']) is list and d['branches'] and len(d['branches']) <= 8, 'Explicit feature branch scope required')
    require(len(set(d['branches']))==len(d['branches']),'Duplicate branch scope')
    for item in d['branches']:
        ref(item)
        require(item.startswith('refs/heads/'),'Delegation selects feature branches, not tags')
    require(d['merge_mode'] in ('MANUAL','DELEGATED') and type(d['merge_methods']) is list
            and set(d['merge_methods']) <= {'merge','squash'} and d['merge_envelope'] in ('HEAD_ATOMIC_BASE_OBSERVED','ATOMIC_BASE'), 'Unsupported merge configuration')
    require(all(type(d[k]) is bool for k in ('allow_setup','allow_claim')) and type(d['reviews']) is int and 1 <= d['reviews'] <= 16,
            'Explicit operator setup/ownership and independent-review conditions required')
    require(d['ticket_envelope'] is None or d['ticket_envelope']=='OBSERVED_VERSION','Unsupported existing-ticket envelope')
    require(Operation.TICKET_EDIT not in d['operations'] or d['ticket_envelope']=='OBSERVED_VERSION',
            'Explicit project assent to native observed-version ticket edits is required')
    require(type(p['tasks']) is list and 1 <= len(p['tasks']) <= w['maximum_tasks'], 'Bounded enrolled task list required')
    tasks=[]
    for item in p['tasks']:
        fields(item, 'issue_id number task_id slug workspace expected_revision')
        for k in ('issue_id','task_id','slug'): string(item[k],128)
        string(item['workspace'],4096)
        require(type(item['number']) is int and item['number'] > 0 and item['issue_id'] in d['issues'], 'Task is outside delegated issue scope')
        branch(item['slug']); sha(item['expected_revision'])
        tasks.append(TaskProfile(item['issue_id'],item['number'],item['task_id'],item['slug'],safe_path(Path(item['workspace']).absolute()),item['expected_revision']))
    for values in ([t.issue_id for t in tasks],[t.task_id for t in tasks],[t.workspace for t in tasks]):
        require(len(values) == len(set(values)), 'Duplicate enrolled task/workspace identity')
    require(type(p['checks']) is list and 1 <= len(p['checks']) <= 32, 'Project-prescribed check inventory required')
    checks=tuple(typed(RequiredCheck,c) for c in p['checks'])
    require(len({(c.name,c.phase) for c in checks})==len(checks), 'Duplicate project check identity')
    fields(providers['validation'], 'kind path mode maximum_age result_maximum_age maximum_observations')
    v=providers['validation']
    require(type(v['maximum_age']) is int and 1<=v['maximum_age']<=3600
        and (v['result_maximum_age'] is None or type(v['result_maximum_age']) is int and 1<=v['result_maximum_age']<=3600)
        and type(v['maximum_observations']) is int and 1<=v['maximum_observations']<=8,
        'Explicit bounded project evidence freshness/observation policy required')
    require(providers['validation']['kind'] in ('github','signed') and providers['validation']['mode'] in ('COMMITTED','POST_PR'),
            'Use a supported project-owned evidence sequence; no candidate runner is supplied')
    if providers['validation']['kind']=='github':
        require(providers['validation']['mode']=='POST_PR' and all(c.phase==Phase.AFTER_PR for c in checks),
                'Native GitHub evidence requires a published PR; pre-PR checks need the project evidence source')
    fields(providers['credentials'], 'read cas forge ticket')
    for k in ('repo','storage','private_state'):
        string(m[k],4096)
        candidate=Path(m[k])
        require(candidate.is_absolute() and safe_path(candidate)==candidate,'Absolute normalized memory paths required')
    files_to_protect = [Path(providers[k]) for k in ('policy','assessment','decisions','revocations')]
    files_to_protect.extend(Path(v) for v in providers['credentials'].values() if v is not None)
    if providers['decision_socket'] is not None: files_to_protect.append(Path(providers['decision_socket']))
    if providers['validation']['path'] is not None: files_to_protect.append(Path(providers['validation']['path']))
    for row,_ in trust._root().values(): files_to_protect.append(Path(row['key_file']))
    roots = [t.workspace for t in tasks] + [Path(m['repo']),Path(m['storage'])]
    for configured in [t.workspace for t in tasks]+[Path(m['repo'])]:
        for entry in git(configured,'-c','core.quotePath=false','worktree','list','--porcelain',limit=65536).splitlines():
            if entry.startswith(b'worktree '):
                raw=os.fsdecode(entry[9:])
                require(raw.startswith('/'),'Quoted or noncanonical linked worktree paths require operator reconciliation')
                string(raw,4096)
                roots.append(safe_path(Path(raw)))
    for candidate in [path, trust.path, *files_to_protect, Path(m['private_state'])]:
        string(str(candidate),4096)
        require(candidate.is_absolute() and safe_path(candidate)==candidate, 'Absolute protected operator paths required')
        require(all(not candidate.is_relative_to(root) and not root.is_relative_to(candidate) for root in roots),
                'Operator configuration/secrets must be outside product and memory roots')
    profile=OperatorProfile(path,verified,trust,rid,tuple(tasks),checks)
    cfg=profile.memory_config()
    commons=[Path(value(cfg.root,'rev-parse','--path-format=absolute','--git-common-dir')),
        Path(remote_identity(value(cfg.root,'remote','get-url',cfg.remote),cfg.root)[5:])]
    commons.extend(Path(value(t.workspace,'rev-parse','--path-format=absolute','--git-common-dir')) for t in tasks)
    require(all(not candidate.is_relative_to(common) and not common.is_relative_to(candidate)
        for candidate in [path,trust.path,*files_to_protect,profile.state] for common in commons),
        'Keep operator authority outside all Git administration and coordination remotes')
    require(all(not profile.state.is_relative_to(candidate.parent) and not candidate.is_relative_to(profile.state)
        for candidate in [path,trust.path,*files_to_protect]), 'Keep authentication/provider roots separate from private execution evidence')
    for task in tasks: profile.project_config(task)
    require(not credential_shaped({k:v for k,v in p.items() if k not in ('providers','memory','tasks')}), 'Private credentials do not belong in profile payloads')
    if retain_revocation and (profile.state/'enrollment.json').exists():
        if (profile.state/'revocation.json').exists(): profile.live(retain=True)
        else:
            from .memory import Memory
            require(recover_initial_setup and Memory(profile.memory_config()).inspect()['health']=='UNINITIALIZED',
                'Retained revocation history is missing')
            profile.live()
    else: profile.live()
    return profile
