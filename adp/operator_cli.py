"""Installed profile CLI; never import project Python or print credential payloads."""
from __future__ import annotations

from pathlib import Path

from .errors import ADPError
from .operator_profile import load_profile
from .schema import require


def selectors(command):
    command.add_argument('--operator-profile',type=Path)
    command.add_argument('--operator-trust',type=Path)


def add_commands(commands,common):
    for name in ('setup','preview'):
        command=commands.add_parser(name,parents=[common])
        selectors(command)
        if name=='setup':
            group=command.add_mutually_exclusive_group(required=True)
            group.add_argument('--dry-run',action='store_true')
            group.add_argument('--apply',action='store_true')
            command.add_argument('--authorize-memory-write',action='store_true')


def run(args):
    from .operator_setup import setup,preview,status,verify_enrollment
    from .operator_controller import InstalledProject
    require(getattr(args,'operator_profile',None) is not None and getattr(args,'operator_trust',None) is not None,
        'Select both installed --operator-profile and explicit --operator-trust')
    require(not getattr(args,'controller',None),'Choose one installed profile or advanced controller')
    # Mixing legacy flags with a signed profile is an authority ambiguity.
    require(all(getattr(args,k,None) is None for k in ('config','remote','repository_id','branch','storage')),
        'Memory/remote overrides cannot modify an installed delegation')
    p=load_profile(args.operator_profile,args.operator_trust,retain_revocation=(
        args.command in ('run','resume','handoff') and getattr(args,'authorize_execution',False)
        or args.command=='setup' and getattr(args,'apply',False) and getattr(args,'authorize_memory_write',False)))
    command=args.command
    if command=='status': return status(p),0
    if command=='setup' and args.apply:
        return setup(p,authorized=args.authorize_memory_write),0
    if command in ('preview','doctor','setup'):
        try:
            report=preview(p)
            if command=='doctor' and getattr(args,'check_runtime',False):
                from .codex_runtime import CodexExecRuntime
                capabilities=CodexExecRuntime(p.state/'runtime').capabilities()
                report['runtime']={
                    'qualification':'NOTRUN; deferred to M8','capability_observation':'SUPPORTED' if capabilities.independent_contexts else 'UNSUPPORTED_RUNTIME',
                    'version':capabilities.version,'independent_contexts':capabilities.independent_contexts,
                    'workspace_write':capabilities.workspace_write,'observe':capabilities.observe,'cancel':capabilities.cancel,
                    'maximum_parallel':capabilities.maximum_parallel}
            return report,0 if report['status']=='CONFIGURATION_VERIFIED' else 4
        except (ADPError,OSError,ValueError,TypeError,KeyError):
            return {'mode':'READ_ONLY','status':'UNKNOWN','repository_id':p.repository_id,
                'next_action':'Provide current independently authenticated policy, scope, credentials and remote metadata',
                'runtime':'NOTRUN','background_work':False},4
    require(command in ('run','resume','handoff') and args.authorize_execution,
        'Explicit --authorize-execution is required')
    require(not getattr(args,'test_runtime',False),'Installed profiles select actual CodexExecRuntime only')
    w=p.payload['window']; parallel=getattr(args,'maximum_parallel',None)
    parallel=w['maximum_parallel'] if parallel is None else parallel
    rounds=getattr(args,'rounds',1)
    require(type(parallel) is int and 1<=parallel<=w['maximum_parallel'] and type(rounds) is int and 1<=rounds<=4,
        'Invocation exceeds the unchanged finite project delegation')
    verify_enrollment(p)
    controller=InstalledProject(p,mutating=True).build()
    selected=controller.track
    if command=='resume' and getattr(args,'adopt_generation',False): selected.adopt_generation(authorized=True)
    if command=='handoff': result=selected.handoff(authorized=True)
    else:
        method=selected.resume if command=='resume' else selected.run
        result=method(rounds=rounds,maximum_parallel=parallel,authorized=True)
    return result,0 if result.get('status')=='COMPLETE' else 7 if result.get('status') in ('UNSUPPORTED','UNSUPPORTED_RUNTIME') else 4
