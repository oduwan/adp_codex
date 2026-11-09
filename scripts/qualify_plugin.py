"""Opt-in disposable local plugin install/discovery; no model or public listing."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

from qualification_support import command,pinned_archive,private_directory,private_file,sha256,write_evidence

ROOT=Path(__file__).resolve().parents[1]


def call(command,cwd,environment,log,seconds=60):
    with private_file(log) as output:
        result=subprocess.run(command,cwd=cwd,env=environment,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=output,timeout=seconds,check=False)
    if len(result.stdout)>2*1024*1024:raise ValueError('Plugin response exceeds bound')
    if result.returncode:raise RuntimeError('Plugin capability/operation failed; inspect private log')
    return json.loads(result.stdout)


def skills(cwd,environment,log):
    # Documented app-server discovery only. No thread/turn/model/daemon request.
    with private_file(log) as errors:
        process=subprocess.Popen(['codex','app-server','--listen','stdio://','-c',f'projects.{json.dumps(str(cwd))}.trust_level="trusted"'],
            cwd=cwd,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
        try:
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            buffered=bytearray();total=0
            def send(payload):process.stdin.write((json.dumps(payload)+'\n').encode());process.stdin.flush()
            def receive(expected):
                nonlocal total
                end=time.monotonic()+30
                while time.monotonic()<end:
                    while b'\n' in buffered:
                        line,_,remaining=buffered.partition(b'\n');buffered[:]=remaining
                        response=json.loads(line)
                        if response.get('id')==expected:
                            if 'error' in response:raise RuntimeError('Codex discovery refused; raw error retained privately')
                            return response['result']
                    if selector.select(max(0,end-time.monotonic())):
                        block=os.read(process.stdout.fileno(),65536)
                        if not block:raise RuntimeError('Codex discovery transport exited')
                        buffered.extend(block);total+=len(block)
                        if total>2*1024*1024:raise ValueError('Codex discovery response bound exceeded')
                raise TimeoutError('Codex discovery exceeded fixed30s budget')
            send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'adp-m6-qualification','version':'0.1.0'}}})
            initialized=receive(1)
            send({'method':'initialized','params':{}})
            send({'id':2,'method':'skills/list','params':{'cwds':[str(cwd)],'forceReload':True}})
            return {'initialize':initialized,'skills':receive(2)}
        finally:
            process.stdin.close()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=8)
            process.stdout.close()
            if 'selector' in locals():selector.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-ref',required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--authorize-local-plugin-install',action='store_true')
    args=parser.parse_args()
    if not args.authorize_local_plugin_install:parser.error('Explicit owned local plugin-install authority is required')
    directory=private_directory(args.evidence_dir,ROOT)
    catalog=directory/'catalog';catalog.mkdir()
    plugin=catalog/'plugins/adp-codex';plugin.parent.mkdir()
    archive_hash=pinned_archive(ROOT,args.source_ref,plugin)
    name='adp-m6-'+uuid.uuid4().hex[:12]
    marketplace=catalog/'.agents/plugins';marketplace.mkdir(parents=True)
    (marketplace/'marketplace.json').write_text(json.dumps({'name':name,'plugins':[{'name':'adp-codex',
        'source':{'source':'local','path':'./plugins/adp-codex'},'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]}))
    config=catalog/'.codex';config.mkdir()
    (config/'config.toml').write_text('[plugins."adp-codex@'+name+'"]\nenabled = true\n')
    environment={k:v for k,v in os.environ.items() if k in ('PATH','HOME','USER','LANG','LC_ALL','TMPDIR','HTTPS_PROXY','HTTP_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','CODEX_HOME')}
    command(['git','init','--initial-branch=local-catalog'],cwd=catalog,log=directory/'git-init.log',env=environment)
    selector='adp-codex@'+name
    installed=False;attempted=False;catalog_attempted=False
    evidence={'schema_version':1,'source':args.source_ref,'original_denominator':3,'archive_sha256':archive_hash,
              'public_release':'NOT_AUTHORIZED','limits':'Enabled host discovery only; no GUI/model-driven skill usage, model turn or public listing'}
    try:
        evidence['runtime']=subprocess.check_output(['codex','--version'],env=environment,stderr=subprocess.DEVNULL,timeout=10).decode().strip()
        # CLI catalog registration is explicit; desktop repository auto-discovery
        # is not a substitute for observing the CLI's configured marketplace.
        catalog_attempted=True
        registered=call(['codex','plugin','marketplace','add',str(catalog),'--json'],catalog,environment,directory/'catalog-add.log')
        write_evidence(directory/'catalog-add.json',registered)
        if registered.get('marketplaceName')!=name or registered.get('alreadyAdded') is True:
            raise ValueError('Qualification catalog is not freshly registered')
        before=call(['codex','plugin','list','--marketplace',name,'--available','--json'],catalog,environment,directory/'before.log')
        write_evidence(directory/'before.json',before)
        if any(p.get('name')=='adp-codex' for p in before.get('installed',[])):raise ValueError('Qualification namespace is not fresh')
        attempted=True
        result=call(['codex','plugin','add',selector,'--json'],catalog,environment,directory/'install.log')
        installed=True;write_evidence(directory/'install.json',result)
        root=Path(result['installedPath'])
        if sha256(root/'plugin.json')!=sha256(plugin/'plugin.json'):raise ValueError('Installed portable manifest differs')
        skill=root/'skills/adp-codex/SKILL.md'
        if sha256(skill)!=sha256(plugin/'skills/adp-codex/SKILL.md'):raise ValueError('Installed skill differs')
        if not (root/'docs/ARCHITECTURE.md').is_file():raise ValueError('Installed skill references are missing')
        after=call(['codex','plugin','list','--marketplace',name,'--json'],catalog,environment,directory/'after.log')
        write_evidence(directory/'after.json',after)
        own=[p for p in after.get('installed',[]) if p.get('name')=='adp-codex']
        if len(own)!=1 or own[0].get('enabled') is not True:raise ValueError('Installed plugin is not observably enabled')
        observed=skills(catalog,environment,directory/'discovery.log')
        write_evidence(directory/'discovery.json',observed)
        available=[s for row in observed['skills'].get('data',[]) for s in row.get('skills',[])
                   if isinstance(s.get('path'),str) and Path(s['path']).resolve()==skill.resolve()]
        if (len(available)!=1 or available[0].get('enabled') is not True
                or sha256(Path(available[0]['path']))!=sha256(plugin/'skills/adp-codex/SKILL.md')):
            raise ValueError('Exact installed skill was not actually discovered/enabled')
        evidence.update(status='PASS',manifest_sha256=sha256(root/'plugin.json'),skill_sha256=sha256(skill),
            installed=True,enabled=True,discovered=True,model_usage='NOTRUN',gui_usage='UNSUPPORTED')
    except Exception as exc:
        evidence.update(status='UNSUPPORTED' if isinstance(exc,FileNotFoundError) else 'ERROR',error_type=type(exc).__name__)
        raise
    finally:
        try:
            if attempted and not installed:
                actual=call(['codex','plugin','list','--marketplace',name,'--json'],catalog,environment,directory/'reconcile.log')
                write_evidence(directory/'reconcile.json',actual)
                installed=any(p.get('name')=='adp-codex' for p in actual.get('installed',[]))
            if installed:
                cleanup=call(['codex','plugin','remove',selector,'--json'],catalog,environment,directory/'remove.log')
                write_evidence(directory/'remove.json',cleanup)
                after_cleanup=call(['codex','plugin','list','--marketplace',name,'--json'],catalog,environment,directory/'cleanup-check.log')
                write_evidence(directory/'cleanup-check.json',after_cleanup)
                if any(p.get('name')=='adp-codex' for p in after_cleanup.get('installed',[])):
                    raise RuntimeError('Disposable plugin cleanup is unconfirmed')
                evidence['own_namespace_removed']=True
            if catalog_attempted:
                catalogs=call(['codex','plugin','marketplace','list','--json'],catalog,environment,directory/'catalog-reconcile.log')
                write_evidence(directory/'catalog-reconcile.json',catalogs)
                if any(row.get('name')==name for row in catalogs.get('marketplaces',[])):
                    removed=call(['codex','plugin','marketplace','remove',name,'--json'],catalog,environment,directory/'catalog-remove.log')
                    write_evidence(directory/'catalog-remove.json',removed)
                remaining=call(['codex','plugin','marketplace','list','--json'],catalog,environment,directory/'catalog-cleanup.log')
                write_evidence(directory/'catalog-cleanup.json',remaining)
                if any(row.get('name')==name for row in remaining.get('marketplaces',[])):
                    raise RuntimeError('Disposable catalog cleanup is unconfirmed')
                evidence['own_catalog_removed']=True
        except Exception as exc:
            evidence.update(status='ERROR',cleanup_error_type=type(exc).__name__)
            raise
        finally:
            digest=write_evidence(directory/'plugin.json',evidence)
            print(json.dumps({'status':evidence.get('status','UNKNOWN'),'source':args.source_ref,'evidence_sha256':digest,'public_release':'NOT_AUTHORIZED'},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
