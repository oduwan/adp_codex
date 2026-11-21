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


def run(args, *, expected_binding=None, before_effects=None):
    from .operator_setup import setup,preview,status,verify_enrollment
    from .operator_controller import InstalledProject
    require(getattr(args,'operator_profile',None) is not None and getattr(args,'operator_trust',None) is not None,
        'Select both installed --operator-profile and explicit --operator-trust')
    require(not getattr(args,'controller',None),'Choose one installed profile or advanced controller')
    # Mixing legacy flags with a signed profile is an authority ambiguity.
    require(all(getattr(args,k,None) is None for k in ('config','remote','repository_id','branch','storage')),
        'Memory/remote overrides cannot modify an installed delegation')
    retain=(
        args.command in ('run','resume','handoff') and getattr(args,'authorize_execution',False)
        or args.command=='setup' and getattr(args,'apply',False) and getattr(args,'authorize_memory_write',False))
    p=load_profile(args.operator_profile,args.operator_trust,retain_revocation=retain,
        expected_binding=expected_binding,
        recover_initial_setup=(args.command=='setup' and getattr(args,'apply',False) and getattr(args,'authorize_memory_write',False)))
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
                if not capabilities.independent_contexts:
                    report['configuration_status']=report['status']
                    report['status']='UNSUPPORTED_RUNTIME'
                    report['next_action']='Install a supported authenticated Codex CLI and qualified Linux supervision; no worker was launched'
                    return report,7
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
    scoped_preflight={}
    if before_effects is not None:
        before_effects()
        scoped_preflight['before_effects']=before_effects
    controller=InstalledProject(p,mutating=True).build()
    selected=controller.track
    if command=='resume' and getattr(args,'adopt_generation',False): selected.adopt_generation(authorized=True)
    if command=='handoff': result=selected.handoff(authorized=True, **scoped_preflight)
    else:
        method=selected.resume if command=='resume' else selected.run
        result=method(rounds=rounds,maximum_parallel=parallel,authorized=True, **scoped_preflight)
    report=exit_report(p,controller,result,command)
    return report,0 if report['status'] in ('COMPLETE','HANDOFF_RECORDED') else 7 if report['status'] in ('UNSUPPORTED','UNSUPPORTED_RUNTIME') else 4


def exit_report(profile,controller,result,command):
    """Observe all enrolled dispositions without dispatch or implied execution."""
    from .discovery_schema import digest
    from .discovery_types import Identity
    observed=controller.conductor.journal.inspect()
    track=observed['state']['execution'].get('track')
    rows=[]
    for task in profile.tasks:
        slot=(track or {}).get('slots',{}).get(digest(Identity(profile.repository_id,task.issue_id)))
        attempted=result.get('tasks',{}).get(task.task_id)
        rows.append({'issue_id':task.issue_id,'task_id':task.task_id,
            'status':attempted.get('status','UNKNOWN') if attempted else slot['status'] if slot else 'NOT_ADMITTED',
            'reason':attempted.get('reason') if attempted else 'No execution receipt; refresh current admission' if not slot else None})
    outcome=result.get('status','UNKNOWN')
    if command=='handoff' and observed['health']=='SYNCED' and observed['state']['owner'] is None:
        outcome='HANDOFF_RECORDED'
    actions={'COMPLETE':'Review completed product outcomes; no background work is implied',
        'HANDOFF_RECORDED':'Preserve private evidence; the next confirmed M1 owner must explicitly adopt the same finite window',
        'PENDING_VALIDATION':'Wait for current exact-SHA prescribed project evidence, then resume the same finite window',
        'WAITING_HUMAN_APPROVAL':'Obtain the project-required PR readiness or human merge decision with fresh exact-SHA gates',
        'UNKNOWN':'Reconcile retained worker stops and external effects; never repeat an uncertain write',
        'UNSUPPORTED':'Install the missing qualified runtime/project provider; no successful execution is claimed',
        'UNSUPPORTED_RUNTIME':'Install the qualified Codex CLI/supervisor; no successful runtime execution is claimed'}
    pending=[row['status'] for row in rows if row['status'] in actions]
    action=actions.get(outcome) or (actions[pending[0]] if pending else
        'Inspect the specific task blocker; supply required authority/provider evidence or correct within original scope and remaining M2 budget')
    if track and track['used_rounds']>=track['maximum_rounds'] and outcome!='COMPLETE':
        action='Finite track budget exhausted; obtain operator disposition without resetting counters or silently renewing the window'
    return {'status':outcome,'tasks':rows,'next_action':action,'generation':observed['state']['generation'],
        'window':{'id':track['id'],'used_rounds':track['used_rounds'],'maximum_rounds':track['maximum_rounds'],
            'expires_at':track['expires']} if track else None,
        'background_work':result.get('background_work','UNKNOWN'),'unconfirmed_contexts':result.get('unconfirmed_contexts',[])}
