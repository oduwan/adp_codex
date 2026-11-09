"""Build a pinned archive, then install its wheel offline into a fresh venv."""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import venv

from qualification_support import command,pinned_archive,private_directory,sha256,write_evidence

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-ref',required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args=parser.parse_args()
    directory=private_directory(args.evidence_dir,ROOT)
    archive=directory/'archive';archive_hash=pinned_archive(ROOT,args.source_ref,archive)
    outside=directory/'outside';outside.mkdir()
    consumer=directory/'consumer';venv.EnvBuilder(with_pip=True,system_site_packages=False).create(consumer)
    python=consumer/'bin/python'
    environment={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','TMPDIR','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR')}
    logs={}
    logs['before']=command([str(python),'-I','-c',"import importlib.util;assert importlib.util.find_spec('adp') is None"],cwd=outside,log=directory/'before.log',env=environment)
    wheels=directory/'wheels';wheels.mkdir()
    logs['build']=command([sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',str(wheels),str(archive)],cwd=outside,log=directory/'build.log',seconds=120,env=environment)
    wheel,=wheels.glob('adp_codex-*.whl')
    logs['install']=command([str(python),'-m','pip','install','--no-index','--no-deps',str(wheel)],cwd=outside,log=directory/'install.log',seconds=60,env=environment)
    probe="import adp,json,pathlib,sys,importlib.metadata;assert importlib.metadata.version('adp-codex')=='0.1.0';root=pathlib.Path(adp.__file__).resolve();assert root.is_relative_to(pathlib.Path(sys.prefix));assert not root.is_relative_to(pathlib.Path("+repr(str(ROOT))+"));print(json.dumps({'import':'PASS','module':'site-packages/adp','version':'0.1.0'}))"
    logs['import']=command([str(python),'-I','-c',probe],cwd=outside,log=directory/'import.log',env=environment)
    logs['cli']=command([str(consumer/'bin/adp'),'--help'],cwd=outside,log=directory/'cli.log',env=environment)
    logs['readonly-plan']=command([str(consumer/'bin/adp'),'plan','--help'],cwd=outside,log=directory/'plan.log',env=environment)
    summary={'schema_version':1,'status':'PASS','source':args.source_ref,'python':platform.python_version(),
        'original_denominator':6,'observed':list(logs),'archive_sha256':archive_hash,'wheel_sha256':sha256(wheel),'logs':logs,
        'public_release':'NOT_AUTHORIZED','limits':'Local installation qualification only; no registry publication or plugin host activation'}
    digest=write_evidence(directory/'installation.json',summary)
    print(json.dumps({'status':'PASS','source':args.source_ref,'python':platform.python_version(),'original_denominator':6,'evidence_sha256':digest},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
