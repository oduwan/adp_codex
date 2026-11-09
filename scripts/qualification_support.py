"""Offline M6 evidence helpers: explicit statuses, immutable inventories, hashes."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import unittest

STATUSES=('PASS','FAIL','ERROR','TIMEOUT','SKIP','NOTRUN','UNKNOWN','UNSUPPORTED')


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_directory(path,source):
    path=Path(path).absolute();source=Path(source).resolve()
    for ancestor in (path,*path.parents):
        if ancestor.is_symlink():raise ValueError('Evidence path contains a symlink')
    if path.resolve().is_relative_to(source) or source.is_relative_to(path.resolve()):
        raise ValueError('Private evidence must remain outside source history')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=path.stat()
    if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ValueError('Private evidence requires an owned mode0700 directory')
    return path


def private_file(path,mode='wb'):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    return os.fdopen(descriptor,mode)


def write_evidence(path,payload):
    raw=(json.dumps(payload,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with private_file(path) as output:
        output.write(raw);output.flush();os.fsync(output.fileno())
    return hashlib.sha256(raw).hexdigest()


def command(argv,*,cwd,log,seconds=120,env=None):
    with private_file(log) as output:
        result=subprocess.run(argv,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL,timeout=seconds,check=False)
    if result.returncode:raise RuntimeError('Qualification command failed; inspect private evidence')
    return sha256(log)


def pinned_archive(repository,revision,destination):
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',revision):raise ValueError('Use an exact source revision')
    raw=subprocess.check_output(['git','-C',str(repository),'archive','--format=tar',revision],timeout=60)
    if len(raw)>16*1024*1024:raise ValueError('Source archive exceeds frozen bound')
    extract_archive(raw,destination)
    return hashlib.sha256(raw).hexdigest()


def extract_archive(raw,destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        members=archive.getmembers();seen=set()
        if len(members)>4096:raise ValueError('Archive file-count bound exceeded')
        for member in members:
            path=PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or member.name in seen
                    or not(member.isfile() or member.isdir()) or member.size>4*1024*1024):
                raise ValueError('Unsafe source archive member')
            seen.add(member.name)
        for member in members:
            target=destination/member.name
            if member.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as source,open(target,'xb') as output:output.write(source.read())


def test_ids(suite):
    for case in suite:
        if isinstance(case,unittest.TestSuite):yield from test_ids(case)
        else:yield case.id()


class HonestResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.observations={}
    def _record(self,test,status):
        case=getattr(test,'test_case',test).id()
        rank={'PASS':0,'SKIP':1,'NOTRUN':2,'UNKNOWN':3,'UNSUPPORTED':4,'TIMEOUT':5,'FAIL':6,'ERROR':7}
        if rank[status]>=rank.get(self.observations.get(case,'PASS'),0):self.observations[case]=status
    def addSuccess(self,test):
        super().addSuccess(test);self._record(test,'PASS')
    def addFailure(self,test,error):
        super().addFailure(test,error);self._record(test,'FAIL')
    def addError(self,test,error):
        super().addError(test,error);self._record(test,'ERROR')
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self._record(test,'SKIP')
    def addExpectedFailure(self,test,error):
        super().addExpectedFailure(test,error);self._record(test,'FAIL')
    def addUnexpectedSuccess(self,test):
        super().addUnexpectedSuccess(test);self._record(test,'FAIL')
    def addSubTest(self,test,subtest,error):
        super().addSubTest(test,subtest,error)
        if error is not None:self._record(test,'FAIL' if issubclass(error[0],test.failureException) else 'ERROR')


def accounting(inventory,observations):
    if len(inventory)!=len(set(inventory)) or set(observations)-set(inventory):raise ValueError('Original test inventory changed')
    if any(status not in STATUSES for status in observations.values()):raise ValueError('Unsupported outcome')
    actual={case:observations.get(case,'NOTRUN') for case in inventory}
    counts={status:sum(value==status for value in actual.values()) for status in STATUSES}
    return {'original_denominator':len(inventory),'counts':counts,'tests':actual,
            'status':'PASS' if counts['PASS']==len(inventory) and inventory else 'FAIL'}
