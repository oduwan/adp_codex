"""Standard installed composition of accepted ports. No project controller import."""
from __future__ import annotations

from dataclasses import replace

from .autonomous_track import AutonomousTrack, TaskSpec, TrackWindow
from .codex_runtime import CodexExecRuntime
from .conductor import Conductor, Project
from .discovery import DependencyPlanner
from .discovery_github import GitHubDiscoveryAdapter, GitHubHTTPTransport as DiscoveryHTTP
from .discovery_types import Identity
from .discovery_schema import digest, typed
from .execution_cli import Controller
from .execution_memory import ExecutionJournal
from .execution_policy import M4ReadinessService
from .execution_types import Admission
from .errors import ADPError
from .github_product import DelegationProfile, GitHubProductForge, GitHubForgeHTTPTransport, delegation_subject
from .guard import ProgressGuard
from .guard_types import Requirement, data
from .memory import Memory
from .network_git import GitHubCAS, GitHubGitExecutionPort, GitHubPolicyAdapter, GitHubTarget
from .network_http import GitHubHTTPTransport
from .operator_authority import OperatorAuthority
from .operator_providers import ProjectProviders
from .policy_types import Operation, Qualifications, Request
from .project_validation import ProjectValidation, ReportedEvidence, observation_subject, policy_subject
from .project_validation_github import GitHubEvidenceSource, GitHubValidationHTTP
from .project_validation_types import EvidencePolicy, ProjectObservation
from .schema import fields, require
from .schema import key
from .ticket_preparation import TicketArchive, TicketPreparer

READ_PERMISSIONS=(('checks','read'),('contents','read'),('issues','read'),('metadata','read'),('pull_requests','read'),('statuses','read'))


class InstalledProject:
    def __init__(self, profile, *, mutating=False):
        self.profile=profile
        self.authority=OperatorAuthority(profile,mutating=mutating)
        self.providers=ProjectProviders(profile,self.authority)
        self.memory=Memory(profile.memory_config())
        self.journal=ExecutionJournal(self.memory)
        self.projects={}; self.adapters={}; self.policy_factories={}; self.services={}
        self.planner=DependencyPlanner(authority=self.authority,clock=profile.trust.clock)
        self._wire_readers()

    def _wire_readers(self):
        p,a=self.profile,self.authority
        credential=a.credential(p.payload['providers']['credentials']['read'],READ_PERMISSIONS)
        self.read_token=credential
        self.read_transport=DiscoveryHTTP(credential.token)
        if set(p.delegation['operations']) & {'PR','MERGE','REPORT'}:
            a.credential(p.payload['providers']['credentials']['forge'],GitHubForgeHTTPTransport.permissions)
        if Operation.TICKET_EDIT in p.delegation['operations']:
            from .ticket_publication import GitHubTicketHTTPTransport
            a.credential(p.payload['providers']['credentials']['ticket'],GitHubTicketHTTPTransport.permissions)
        paths=a.signed('policy').payload['paths']
        fields(paths,'governance profiles contracts')
        for task in p.tasks:
            cfg=p.project_config(task)
            self.adapters[task.task_id]=GitHubDiscoveryAdapter(p.payload['repository']['name'],self.read_transport,
                expected_id=p.repository_id,config=cfg,clock=p.trust.clock)
            token=a.credential(p.payload['providers']['credentials']['cas'],GitHubHTTPTransport.permissions)
            transport=GitHubHTTPTransport(token,authority=a,clock=p.trust.clock)
            service=GitHubCAS(self.target(task),transport)
            self.services[task.task_id]=service
            def policy(admission=None,safety=None,task=task,cfg=cfg,service=service):
                # A fresh transport and policy observation; no cached ALLOW.
                adapter=GitHubPolicyAdapter(cfg,service,governance=tuple(paths['governance']),
                    profiles=tuple(paths['profiles']),contracts=tuple(paths['contracts']),fingerprint_worktree=True)
                return self.providers.policy(adapter,safety)
            self.policy_factories[task.task_id]=policy
        self.readiness=M4ReadinessService((self.adapters[p.tasks[0].task_id],),self.planner,self.providers.reviews)

    def target(self,task):
        p=self.profile; r=p.payload['repository']
        from .git import value
        return GitHubTarget(p.repository_id,r['node_id'],r['database_id'],*r['name'].split('/'),
            value(task.workspace,'symbolic-ref','HEAD').removeprefix('refs/heads/'))

    def build(self):
        """Only setup-verified execution callers may create private archives."""
        p,a=self.profile,self.authority
        require(a.mutating,'Read-only enrollment cannot build execution state')
        a.store.prepare()
        guard=ProgressGuard(self.memory,authority=a,clock=p.trust.clock)
        runtime=CodexExecRuntime(p.state/'runtime')
        for task in p.tasks:
            cfg=p.project_config(task)
            policy_factory=self.policy_factories[task.task_id]
            cas=self.services[task.task_id]
            forge_service=GitHubCAS(self.target(task),GitHubForgeHTTPTransport(a.credential(p.payload['providers']['credentials']['forge'],
                GitHubForgeHTTPTransport.permissions),authority=a,clock=p.trust.clock))
            self.projects[task.task_id]=Project(task.workspace,policy_factory,a,
                GitHubGitExecutionPort(cfg,cas,self.journal),GitHubProductForge(forge_service,self.journal,a),None)
        c=Conductor(self.memory,guard,self.readiness,runtime,a,self.projects,clock=p.trust.clock)
        a.conductor=c
        specs=[]
        roots=tuple([*(task.workspace for task in p.tasks),self.memory.path,self.memory.config.root])
        for task in p.tasks:
            archive=TicketArchive(p.state/'tickets'/key(task.task_id),protected_roots=roots)
            preparer=TicketPreparer(adapters=(self.adapters[task.task_id],),planner=self.planner,
                policy=self.policy_factories[task.task_id](),authority=a,archive=archive,clock=p.trust.clock)
            a.preparers[task.task_id]=preparer
            def assess(original,track,inspection,archive=archive):
                return self.providers.assess(original,track,inspection,archive.frozen_reference(original.issue.identity))
            def admission(packet,task=task):
                requirement=Requirement(packet.original_reference,packet.preparation_reference,
                    tuple(clause.text for clause in packet.clauses if clause.kind=='ACCEPTANCE'),
                    tuple('issue:'+digest(identity) for identity in packet.dependencies))
                return Admission(packet.identity,task.task_id,task.slug,task.task_id,packet.base_sha,requirement,
                    packet.goal,packet.goal[:128],packet.allowed_paths)
            def delegation(admission,plan,scope):
                a.live(); d=p.delegation
                require(admission.identity.issue_id in d['issues'] and plan.task.source_ref in d['branches'],'Product effect outside delegation')
                profile=DelegationProfile(p.repository_id,admission.identity.issue_id,admission.task_id,
                    c._task(admission)['product_iteration'],plan.task.source_ref,
                    'refs/heads/'+next(s.rules.base_branch for s in c._project(admission).policy_factory(admission,None).inspect_repository().sources if s.rules.base_branch),
                    plan.task.revision,plan.policy_digest,scope,tuple(op for op in d['operations'] if op in ('PR','MERGE','REPORT')),
                    d['merge_mode'],tuple(d['merge_methods']),d['merge_envelope'],p.evidence.issued_at,p.evidence.expires_at)
                return replace(profile,evidence=a.proof('github-product/delegation',delegation_subject(profile),p.evidence,
                    binding={'expires_at':p.evidence.expires_at}))
            specs.append(TaskSpec(Identity(p.repository_id,task.issue_id),task.task_id,task.task_id,preparer,assess,
                admission,self.validation,delegation,self.policy_factories[task.task_id],mode=p.payload['providers']['validation']['mode']))
            if Operation.TICKET_EDIT in p.delegation['operations']:
                from .ticket_publication import TicketPublisher, GitHubTicketHTTPTransport
                selected=Admission(Identity(p.repository_id,task.issue_id),task.task_id,task.slug,task.task_id,
                    task.expected_revision,Requirement('ticket-preparation','ticket-preparation',('Scope conserved',)),
                    'Prepare the original admitted ticket','Prepare ticket',('placeholder',))
                service=GitHubCAS(self.target(task),GitHubTicketHTTPTransport(
                    a.credential(p.payload['providers']['credentials']['ticket'],GitHubTicketHTTPTransport.permissions),
                    authority=a,clock=p.trust.clock))
                specs[-1]=replace(specs[-1],ticket_publisher=TicketPublisher(c,selected,service))
        w=p.payload['window']
        window=TrackWindow(w['id'],p.fingerprint,w['issued_at'],w['expires_at'],w['maximum_rounds'],w['maximum_tasks'],w['maximum_parallel'])
        return Controller(c,(),w['maximum_parallel'],AutonomousTrack(c,window,tuple(specs)))

    def validation(self, provider, task, **kwargs):
        require(not kwargs.get('candidate'),'UNSUPPORTED: installed profile does not execute candidate checks')
        p,a=self.profile,self.authority
        plan=provider.plan(task,Request(Operation.VALIDATE))
        config=p.payload['providers']['validation']
        policy=EvidencePolicy(plan.policy_digest,p.checks,p.evidence.issued_at,p.evidence.expires_at,
            maximum_age=config['maximum_age'],result_maximum_age=config['result_maximum_age'])
        policy=replace(policy,evidence=a.proof('project-validation/policy',policy_subject(plan,policy),p.evidence,
            binding={'expires_at':p.evidence.expires_at}))
        def attest(query,observation,source=None):
            subject=observation_subject(query,observation)
            binding={'query':data(query),'observation':data(replace(observation,evidence=None)),
                'expires_at':min(p.evidence.expires_at,observation.observed_at+policy.maximum_age)}
            return (a.proof('project-validation/observation',subject,source,binding=binding) if source else
                a.store.attest('project-validation/observation',subject,p.payload['authority'],binding=binding))
        if config['kind']=='github':
            source=GitHubEvidenceSource(p.payload['repository']['name'],p.repository_id,str(p.payload['repository']['database_id']),p.checks,
                GitHubValidationHTTP(self.read_token.token),attest=attest,clock=p.trust.clock)
        else:
            def observe(query):
                try:
                    source=a.signed('project-evidence',config['path'])
                    require(source.payload['request']==data(query.request),'Current project request is unavailable')
                except (ADPError,OSError,KeyError):
                    source=a.request_data('project-evidence','project-validation/observe',{'query':data(query)})
                body=source.payload
                fields(body,'repository_id request results observed_at complete coverage')
                require(body['request']==data(query.request),'Current exact project check request is unavailable')
                observation=typed(ProjectObservation,{'query_digest':digest(query),'observed_at':body['observed_at'],
                    'complete':body['complete'],'results':body['results'],'coverage':body['coverage'],'evidence':None,'action_key':None})
                require(source.issued_at<=observation.observed_at<source.expires_at,'Project evidence time differs')
                return replace(observation,evidence=attest(query,observation,source))
            source=ReportedEvidence(observe)
        result=ProjectValidation(provider,task,policy,source,directory=p.state/'validation'/key(task.task_id),
            protected_roots=tuple([*(t.workspace for t in p.tasks),self.memory.path]),maximum_observations=config['maximum_observations'],
            clock=p.trust.clock,retain_requests=True)
        a.validators[(task.task_id,digest(policy))]=result
        return result
