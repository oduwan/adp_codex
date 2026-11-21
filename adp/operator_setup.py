"""Read-only enrollment plus explicitly authorized, restartable M1 setup."""
from __future__ import annotations
from dataclasses import dataclass

from .config import safe_path
from .discovery import complete_snapshot
from .discovery_schema import digest
from .errors import ADPError
from .execution_memory import ExecutionJournal
from .git import value
from .guard_types import data
from .memory import Memory
from .operator_evidence import OperatorEvidence
from .operator_profile import private_file
from .schema import encode, fields, require
from .storage import atomic, locked
import os
import stat


def manifest(profile):
    return {'schema_version':1,'profile':profile.fingerprint,'trust':profile.trust.fingerprint,
        'repository_id':profile.repository_id,'window':profile.payload['window']['id']}


def verify_enrollment(profile):
    path=profile.state/'enrollment.json'
    require(path.exists() and private_file(path)==manifest(profile),
        'BLOCKED_OPERATOR: no matching retained enrollment; use explicit setup or reconcile the original profile')
    require((profile.state/'revocation.json').exists() and (profile.state/'authority').is_dir(),
        'BLOCKED_OPERATOR: retained private authority history is missing; do not recreate execution authority')
    profile.live()


def status(profile):
    profile.live()
    memory=Memory(profile.memory_config()).inspect()
    state=memory.get('state',{})
    execution=state.get('execution',{})
    # No runtime construction, recovery, lock, discovery, or migration.
    return {'mode':'READ_ONLY','repository_id':profile.repository_id,'delegation':profile.identifier,
        'memory_health':memory['health'],'local_owner':memory.get('local_owner',False),
        'generation':state.get('generation'),'track':execution.get('track'),
        'task_stages':{row['id'] if 'id' in row else name:row.get('stage','UNKNOWN') for name,row in execution.get('tasks',{}).items()},
        'enrollment':'MATCHED' if (profile.state/'enrollment.json').exists() and private_file(profile.state/'enrollment.json')==manifest(profile) else 'NOT_ENROLLED',
        'execution_liveness':'UNKNOWN','background_work':'UNKNOWN',
        'next_action':'Use a bounded authorized run/resume; a checkpoint does not prove running workers'}


@dataclass(frozen=True)
class PreviewBinding:
    discovery: str
    policy: str
    assessment: str


def preview(profile, *, installed=None, expected: PreviewBinding | None = None):
    from .operator_controller import InstalledProject
    installed=installed or InstalledProject(profile)
    require(not installed.authority.mutating,'Preview requires read-only providers')
    snapshots=tuple(adapter.discover() for adapter in installed.readiness.adapters)
    if expected is not None:
        from .operator_authority import remote_semantics
        require(remote_semantics(snapshots) == expected.discovery,
                'Guided enrollment discovery changed after review')
    complete=all(complete_snapshot(s) for s in snapshots)
    inspections=[]
    for task in profile.tasks:
        inspection=installed.policy_factories[task.task_id]().inspect_repository()
        inspections.append(inspection)
    try:
        reviews=installed.providers.reviews(snapshots)
        track=installed.planner.plan(snapshots,reviews=reviews)
        tasks=[{'issue_id':c.identity.issue_id,'status':str(c.status),'reasons':list(c.reasons),
            'dependencies':[data(i) for i in c.prerequisites]} for c in track.candidates
            if c.identity.issue_id in profile.delegation['issues']]
        source=installed.providers.assessment(snapshots)
        for index,spec in enumerate(profile.tasks):
            row=next(t for t in tasks if t['issue_id']==spec.issue_id)
            candidate=next(c for c in track.candidates if c.identity.issue_id==spec.issue_id)
            snapshot=next(s for s in snapshots if s.repository.id==profile.repository_id)
            row['packet_preview']=installed.providers.preview_task(spec,candidate,inspections[index],snapshot,source)
            if row['packet_preview']['blockers']:
                row['status']='BLOCKED_OPERATOR';row['reasons']+=row['packet_preview']['blockers']
    except ADPError:
        tasks=[{'issue_id':task.issue_id,'status':'UNKNOWN','reasons':['Current independent task assessment is unavailable'],
            'dependencies':'UNKNOWN'} for task in profile.tasks]
    conflicts=[reason for inspection in inspections for reason in inspection.conflicts]
    verified=complete and not conflicts and all(i.sources for i in inspections) and len(tasks)==len(profile.tasks) and all(
        t['status'] not in ('UNKNOWN','NEEDS_SPEC','BLOCKED_OPERATOR') and t.get('packet_preview') for t in tasks)
    if expected is not None:
        require(verified, 'Guided enrollment configuration is incomplete')
        require(source.fingerprint == expected.assessment
                and installed.authority.preview_sources('discovery/') == {expected.assessment}
                and installed.authority.preview_sources('policy/') == {expected.policy},
                'Guided enrollment provider observations changed after review')
    return {'mode':'READ_ONLY','status':'CONFIGURATION_VERIFIED' if verified else 'UNKNOWN',
        'repository_id':profile.repository_id,'repository':profile.payload['repository']['name'],
        'delegation':profile.identifier,'window':profile.payload['window'],
        'operations':profile.delegation['operations'],'branches':profile.delegation['branches'],
        'merge_mode':profile.delegation['merge_mode'],'merge_envelope':profile.delegation['merge_envelope'],
        'policy':[{'digest':i.digest,'rules':[data(s.rules) for s in i.sources],'conflicts':list(i.conflicts)} for i in inspections],
        'checks':[data(c) for c in profile.checks],'tasks':tasks,
        'discovery':'COMPLETE' if complete else 'UNKNOWN',
        'runtime':{'qualification':'NOTRUN; deferred to M8','capability_observation':'UNKNOWN',
            'version':'UNKNOWN','independent_contexts':'UNKNOWN','workspace_write':'UNKNOWN',
            'observe':'UNKNOWN','cancel':'UNKNOWN','next_action':'Execution performs the accepted capability-only preflight before dispatch'},
        'operator_actions':['Unknown scope or authority needs a specific external decision',
            'Manual merge and Draft readiness require project approval',
            'Project supplies its own CI environment and evidence'],
        'next_action':'Explicit setup --apply --authorize-memory-write' if verified else 'Refresh project policy, permissions or complete remote metadata'}


def setup(profile, *, authorized=False, expected_preview: PreviewBinding | None = None):
    require(authorized and profile.delegation['allow_setup'],'Explicit memory-write authority and project setup delegation required')
    require(profile.trust.read(profile.path, 'profile', profile.repository_id).fingerprint == profile.fingerprint,
            'Setup requires the persisted, verified operator profile')
    cfg=profile.memory_config(); memory=Memory(cfg)
    observed=memory.inspect()
    path=profile.state/'enrollment.json'
    initial=observed['health']=='UNINITIALIZED'
    if path.exists() and not initial:
        require(private_file(path)==manifest(profile) and (profile.state/'revocation.json').exists()
            and (profile.state/'authority').is_dir(),'Retained enrollment/authority history is missing or changed')
    profile.live(retain=path.exists() and (profile.state/'revocation.json').exists())
    preflight=preview(profile) if expected_preview is None else preview(profile, expected=expected_preview)
    require(preflight['status']=='CONFIGURATION_VERIFIED','UNKNOWN: complete independently verified enrollment is required before memory writes')
    def initial_layout():
        if not profile.state.exists(): return
        info=safe_path(profile.state).stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,
            'Private enrollment directory is not owned/protected')
        entries=list(profile.state.iterdir())
        require(all(p.name in ('authority','revocation.json','enrollment.json','lock') and not p.is_symlink() for p in entries),
            'Unknown existing private history cannot be adopted')
        if (profile.state/'authority').exists():
            require(not any((profile.state/'authority').iterdir()),'Existing authority receipts require retained enrollment')
        if path.exists(): require(private_file(path)==manifest(profile),'Enrollment intent differs')
    if path.exists() and not initial:
        verify_enrollment(profile)
    else:
        # Do not adopt pre-existing worker/effect state by creating new receipts.
        require(initial,
            'BLOCKED_OPERATOR: existing memory/private state requires its retained enrollment')
        initial_layout()
        for task in profile.tasks:
            require(value(task.workspace,'rev-parse','HEAD')==task.expected_revision,
                'Enrollment source changed from explicitly selected original revision')
        profile.state.mkdir(mode=0o700,parents=True,exist_ok=True)
        atomic(path,encode(manifest(profile))) # intent before M1 effects
        OperatorEvidence(profile).prepare()
        profile.live(retain=True)
    with locked(profile.state):
        profile.live()
        observed=memory.inspect()
        if observed['health']=='UNINITIALIZED':
            memory.initialize(authorized=True)
            observed=memory.inspect()
        require(observed['health']=='SYNCED','Use explicit M1 recovery for an interrupted checkpoint; never reset memory')
        if observed['state']['owner'] is None:
            require(profile.delegation['allow_claim'],'Project did not delegate M1 claim')
            memory.claim(profile.payload['memory']['owner'])
        else:
            require(observed['local_owner'],'BLOCKED_OPERATOR: foreign owner requires confirmed-stop handoff')
        profile.live()
        if memory.inspect()['state']['schema_version']==1: memory.upgrade_guard(authorized=True)
        journal=ExecutionJournal(memory)
        journal.upgrade(authorized=True)
        journal.upgrade_product_flow(authorized=True)
        journal.upgrade_track(authorized=True)
        profile.live()
    return {'status':'SETUP_COMPLETE','repository_id':profile.repository_id,
        'generation':memory.inspect()['state']['generation'],'execution':'NOT_STARTED',
        'next_action':'preview, then run --authorize-execution with finite invocation limits'}
