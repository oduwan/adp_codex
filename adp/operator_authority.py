"""Installed authorization: delegated operations and separately authenticated facts.

No Python, shell, approval expression or credential is loaded from a project.
Semantic approvals are external signed inputs, never inferred from file paths.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib

from .discovery import review_subject
from .discovery_schema import digest, typed
from .discovery_types import ReadinessReview
from .errors import ADPError
from .execution_types import Role, RuntimeStatus
from .guard_types import Attestation, data
from .operator_evidence import OperatorEvidence
from .operator_profile import private_file
from .policy_types import Authorization, Effect, Operation, Plan, Qualifications
from .schema import fields, require


def remote_semantics(snapshots):
    """Signed remote facts, excluding ONLY observation time/local checkout binding.

    Bodies, source versions, authors, dependency/PR identities and coverage remain.
    Local source/ref/policy are bound separately by M3, M1 and exact plan grants.
    """
    rows=[]
    for snapshot in sorted(snapshots,key=lambda s:s.repository.id):
        row=data(snapshot)
        row.pop('observed_at',None)
        for key in ('memory_id','checkout_ref','checkout_sha'):
            row['repository'].pop(key,None)
        rows.append(row)
    return digest(rows)


class OperatorAuthority:
    def __init__(self, profile, *, mutating=False):
        self.profile=profile
        self.mutating=mutating
        self.store=OperatorEvidence(profile)
        self.conductor=None
        self.validators={}
        self._tokens={}
        self._ephemeral={}
        self.preparers={}

    def live(self):
        return self.profile.live(retain=self.mutating)

    def signed(self, kind, path=None):
        self.live()
        return self.profile.trust.read(path or self.profile.payload['providers'][kind],kind,self.profile.repository_id)

    def proof(self, purpose, subject, source, *, binding=None):
        binding=dict(binding or {})
        binding['expires_at']=min(binding.get('expires_at',source.expires_at),source.expires_at,self.profile.evidence.expires_at)
        if not self.mutating:
            evidence=Attestation(source.principal,'operator-preview:'+digest({'source':source.fingerprint,'purpose':purpose,'subject':subject}),subject)
            self._ephemeral[(evidence,purpose,subject)]=source
            return evidence
        return self.store.attest(purpose,subject,source.principal,
            provenance=(self.store.source(source),),binding=binding)

    def preview_sources(self, domain: str) -> set[str]:
        require(not self.mutating, 'Preview sources are available only from read-only observations')
        return {source.fingerprint for (_, purpose, _), source in self._ephemeral.items()
                if purpose.startswith(domain)}

    def request_data(self, kind, purpose, context):
        from .operator_decisions import exchange
        require(kind in ('policy','assessment','project-evidence'),'Unsupported installed project data request')
        endpoint=self.profile.payload['providers']['decision_socket']
        require(endpoint is not None,'UNKNOWN_PROVIDER: '+purpose+'; provide current authenticated project data')
        self.live()
        challenge={'schema_version':1,'repository_id':self.profile.repository_id,'profile_digest':self.profile.fingerprint,
            'purpose':purpose,'subject':digest(context),'context':context,'context_digest':digest(context),'required_kind':kind}
        document=exchange(endpoint,challenge)
        return self.profile.trust.verify_document(document,kind,self.profile.repository_id)

    def decision(self, purpose, subject, context=None, *, operator=False):
        """Exact-purpose semantic decisions only. No wildcard or positive flag."""
        inventory=private_file(self.profile.payload['providers']['decisions'])
        fields(inventory,'schema_version decisions')
        require(type(inventory['schema_version']) is int and inventory['schema_version']==1
            and type(inventory['decisions']) is list and len(inventory['decisions'])<=64,'Bounded signed decisions required')
        matches=[]
        for document in inventory['decisions']:
            if document.get('kind') != ('operator-decision' if operator else 'decision'):
                continue
            source=self.profile.trust.verify_document(document,document['kind'],self.profile.repository_id,current=False)
            payload=source.payload
            fields(payload,'repository_id purpose subject context_digest')
            if ((payload['purpose'],payload['subject'],payload['context_digest'])==(purpose,subject,digest(context or {}))
                and source.issued_at<=self.profile.trust.clock()<source.expires_at):
                matches.append(source)
        require(len(matches)<=1,'BLOCKED_OPERATOR: current exact semantic decision is ambiguous')
        if not matches:
            from .operator_decisions import exchange
            endpoint=self.profile.payload['providers']['decision_socket']
            require(endpoint is not None,'UNKNOWN_PROVIDER: '+purpose+'; install the independently authorized signed decision provider')
            challenge={'schema_version':1,'repository_id':self.profile.repository_id,'profile_digest':self.profile.fingerprint,
                'purpose':purpose,'subject':subject,'context':context or {},'context_digest':digest(context or {}),
                'required_kind':'operator-decision' if operator else 'decision'}
            document=exchange(endpoint,challenge)
            source=self.profile.trust.verify_document(document,challenge['required_kind'],self.profile.repository_id)
            fields(source.payload,'repository_id purpose subject context_digest')
            require(source.payload=={key:challenge[key] for key in ('repository_id','purpose','subject','context_digest')},
                'Independent response differs from the actual complete challenge')
            matches.append(source)
        source=matches[0]
        require(source.principal != self.profile.payload['authority'],'Independent decision cannot be automation self-approval')
        return self.proof(purpose,subject,source,binding={'context_digest':digest(context or {}),'expires_at':source.expires_at})

    def verify(self, evidence, *, purpose, subject):
        try: self.live()
        except (ADPError,OSError,ValueError,TypeError): return False
        if not self.mutating and (evidence,purpose,subject) in self._ephemeral:
            try:
                self.live()
                source=self._ephemeral[(evidence,purpose,subject)]
                self.profile.trust.verify_document(source.document,source.document['kind'],self.profile.repository_id)
                return True
            except (ADPError,OSError,ValueError,TypeError): return False
        if purpose=='github/installation-token-scope':
            try:
                self.live()
                path,permissions=self._tokens[(evidence,subject)]
                token=self.credential(path,permissions,remember=False)
                from .network_http import installation_scope_subject
                return installation_scope_subject(token,permissions=permissions)==subject and token.evidence==evidence
            except (ADPError,OSError,KeyError,ValueError,TypeError):
                return False
        if not self.store.verify(evidence,purpose=purpose,subject=subject):
            return False
        try:
            body=self.store.read(evidence.reference)
            expires=body['binding'].get('expires_at')
            if expires is not None and self.profile.trust.clock()>=expires:
                return False
            return True
        except (ADPError,OSError,KeyError,TypeError):
            return False

    def credential(self, path, permissions, *, remember=True):
        """Trusted issuer signs actual issuance request/response and exact token.

        Issuance proof stays in its protected issuer file, never the receipt store.
        This verifies provenance only; a valid token grants no project operation.
        """
        from .network_http import ScopedInstallationToken, installation_scope_subject
        source=self.signed('credential',path)
        p=source.payload
        fields(p,'repository_id token issuance_request issuance_response')
        token=typed(ScopedInstallationToken,p['token'])
        request,response=p['issuance_request'],p['issuance_response']
        fields(request,'installation_id repository_ids permissions')
        fields(response,'token_sha256 repository_ids repository_node_id permissions issued_at expires_at')
        require(request=={'installation_id':token.installation_id,'repository_ids':list(token.repository_ids),
            'permissions':dict(permissions)} and response=={
            'token_sha256':hashlib.sha256(token.token.encode()).hexdigest(),'repository_ids':list(token.repository_ids),
            'repository_node_id':token.repository_node_id,'permissions':dict(permissions),
            'issued_at':token.issued_at,'expires_at':token.expires_at},'Actual token issuance records differ')
        r=self.profile.payload['repository']
        require(token.repository_ids==(r['database_id'],) and token.repository_node_id==r['node_id']
            and source.issued_at<=token.issued_at<=self.profile.trust.clock()<token.expires_at<=source.expires_at,
            'Credential repository or issuance lifetime differs')
        subject=installation_scope_subject(token,permissions=permissions)
        evidence=Attestation(source.principal,'issuer:'+source.fingerprint,subject)
        token=replace(token,evidence=evidence)
        if remember: self._tokens[(evidence,subject)]=(path,permissions)
        return token

    def _task(self, task_id):
        matches=[task for task in self.profile.tasks if task.task_id==task_id]
        require(len(matches)==1,'Task is outside installed delegation')
        return matches[0]

    def _current(self, task_id):
        require(self.conductor is not None,'Installed Conductor unavailable')
        observed=self.conductor.journal.inspect()
        require(observed['health']=='SYNCED' and observed['local_owner'],'Current M1 ownership required')
        self._task(task_id)
        return observed

    def authorize(self, plan, qualifications=Qualifications()):
        require(self.mutating,'Read-only enrollment cannot authorize product effects')
        require(type(plan) is Plan and plan.policy_effect==Effect.ALLOW,'Verified project policy must allow this operation')
        self.live()
        task=self._task(plan.task.task_id)
        d=self.profile.delegation
        require(plan.task.repository_id==self.profile.repository_id and plan.task.source_ref in d['branches']
            and plan.request.operation in d['operations'],'Operation or source branch is not delegated')
        cfg=self.profile.project_config(task)
        from .git import value
        require(value(cfg.root,'rev-parse','HEAD')==plan.task.revision,'Exact source changed before authorization')
        observed=self._current(task.task_id)
        require(plan.task.generation==observed['state']['generation'],'Owner generation changed')
        require(plan.required_reviews>=d['reviews'] or not plan.gated,'Project independent-review gate is weaker than enrollment')
        if plan.request.operation==Operation.MERGE:
            require(d['merge_mode']=='DELEGATED' and plan.payload.method in d['merge_methods']
                and d['merge_envelope']=='HEAD_ATOMIC_BASE_OBSERVED','WAITING_HUMAN_APPROVAL: merge is not delegated or supported')
        from .policy import PolicyProvider
        # operation_subject is static in behavior but includes exact safety/memory.
        subject=PolicyProvider.authorization_subject(plan,qualifications)
        evidence=self.store.attest('policy/operation',subject,self.profile.evidence.principal,
            provenance=(self.store.source(self.profile.evidence),),binding={'plan':digest(plan),'expires_at':self.profile.evidence.expires_at})
        return Authorization(evidence,qualifications)

    def runtime_fact(self, receipt, principal=None, *, role=Role.REVIEWER, revision=None):
        """Authenticate a canonical, stopped real runtime result, never a label."""
        from .codex_runtime import CodexExecRuntime
        c=self.conductor
        require(c is not None and type(c.runtime) is CodexExecRuntime,'Real runtime provenance is unavailable')
        state=c.journal.inspect()['state']
        jobs=[job for task in state['execution']['tasks'].values() for job in task['jobs'].values() if job['receipt']==receipt]
        require(len(jobs)==1,'Unique durable actual worker receipt required')
        job=jobs[0]
        actual=c.runtime.observe(job['request_id'])
        require(job['role']==role and job['generation']==state['generation']
            and actual.request_id==job['request_id'] and actual.request_digest==job['request_digest']
            and actual.receipt==receipt and actual.stopped is True and actual.status==RuntimeStatus.COMPLETED
            and actual.context_id==job['context'] and actual.result is not None
            and data(actual.result)==job['result'] and (revision is None or job['revision']==revision)
            and (principal is None or principal=='worker:'+job['request_id']), 'Actual stopped independent worker proof differs')
        if role==Role.REVIEWER:
            require(actual.result.approved is True and actual.result.outcome=='PASS','Independent Reviewer did not approve')
        developer_contexts={j['context'] for t in state['execution']['tasks'].values() for j in t['jobs'].values() if j['role']==Role.DEVELOPER}
        require(actual.context_id is not None and actual.context_id not in developer_contexts,'Reviewer/Forensic context is not independent')
        return job

    def grant(self, *, purpose, subject, context=None):
        require(self.mutating,'Read-only enrollment cannot grant execution authority')
        self.live(); context=context or {}
        if purpose in ('ticket/edit','ticket/observed-version'):
            d=self.profile.delegation
            require(Operation.TICKET_EDIT in d['operations'] and d['ticket_envelope']=='OBSERVED_VERSION',
                'BLOCKED_OPERATOR: existing-ticket edits/native observed-version envelope are not delegated')
            bundle=context.get('bundle',context)
            from .autonomous_track import PreparationInputs
            from .discovery_types import Track
            from .ticket_preparation import original_scope_subject, preparation_subject
            inputs=typed(PreparationInputs,bundle['inputs']);track=typed(Track,bundle['track'])
            matches=[]
            for task_id,preparer in self.preparers.items():
                if preparer.archive.frozen_reference(self._task_identity(task_id))==bundle['original']:
                    matches.append((task_id,preparer))
            require(len(matches)==1,'Exact frozen ticket preparation is unavailable')
            task_id,preparer=matches[0];original=preparer.archive.original(bundle['original'])
            self._current(task_id)
            require(self.verify(inputs.scope.evidence,purpose='ticket/original-scope',subject=original_scope_subject(inputs.scope))
                and self.verify(inputs.review.evidence,purpose='ticket/preparation',subject=preparation_subject(
                    original,inputs.scope,inputs.proposal,inputs.review,track)), 'Independent exact ticket preparation is unavailable')
            return self.proof(purpose,subject,self.profile.evidence,binding={'preparation':inputs.review.evidence.reference})
        if purpose in ('progress','forensic','policy/review'):
            if 'receipt' in context:
                role=Role.FORENSIC if purpose=='forensic' else Role.REVIEWER
                job=self.runtime_fact(context['receipt'],context.get('principal') or context.get('reviewer'),role=role,
                    revision=context.get('revision'))
                return self.store.attest(purpose,subject,'worker:'+job['request_id'],
                    binding={'job':digest(job),'receipt':job['receipt'],'expires_at':self.profile.payload['window']['expires_at']})
            # Prerequisite and cause-narrowing semantic progress needs its own
            # independent proof. No prior failure automatically becomes progress.
            if context.get('prior_failure'): return None
            return self.decision(purpose,subject,context)
        if purpose in ('execution/run','track/window','track/refresh','execution/dispatch','admission',
                       'execution/effect','effect','track/lifecycle'):
            return self._delegated(purpose,subject,context)
        if purpose=='track/worker-scope':
            request=context.get('request',{})
            if request.get('role')==Role.DEVELOPER:
                return self.decision(purpose,subject,context)
            return self._delegated(purpose,subject,context)
        if purpose in ('policy/project-check','policy/project-validation'):
            self.validate_gates(context)
            return self.store.attest(purpose,subject,self.profile.payload['authority'],binding={'expires_at':self.profile.evidence.expires_at})
        if purpose in ('effect/observed','effect/submit','forge/operation'):
            return self.decision(purpose,subject,context,operator=True)
        return self.decision(purpose,subject,context,
            operator=purpose in ('ticket/scope-addition','track/adopt-generation'))

    def _task_identity(self, task_id):
        from .discovery_types import Identity
        return Identity(self.profile.repository_id,self._task(task_id).issue_id)

    def _delegated(self, purpose, subject, context):
        d=self.profile.delegation
        require(context,'Exact typed operation context is unavailable')
        if purpose=='admission':
            self._task(context['task_id']); self._current(context['task_id'])
            from .guard_types import Requirement, Limits
            requirement=typed(Requirement,context['requirement'])
            require(requirement.limits==Limits(),'Installed profile cannot increase accepted M2 limits')
        elif purpose in ('execution/effect','effect'):
            plan=typed(Plan,context['plan'])
            self.authorize(plan)
        elif purpose in ('execution/dispatch','track/worker-scope'):
            request=context['request']; self._current(request['task_id'])
            require(request['generation']==self.conductor.journal.inspect()['state']['generation']
                and request['role'] in (Role.DEVELOPER,Role.REVIEWER,Role.FORENSIC)
                and request['workspace']==str(self._task(request['task_id']).workspace), 'Worker execution context differs')
        else:
            observed=self.conductor.journal.inspect()
            require(observed['local_owner'] and observed['health']=='SYNCED','M1 ownership required')
            if purpose=='execution/run':
                require(context['parallel']<=self.profile.payload['window']['maximum_parallel'] and context['rounds']<=4,'Run exceeds finite delegation')
            if purpose=='track/window':
                w=context['window']; expected=self.profile.payload['window']
                require(w['id']==expected['id'] and w['maximum_rounds']==expected['maximum_rounds']
                    and w['maximum_tasks']==expected['maximum_tasks'] and w['maximum_parallel']==expected['maximum_parallel']
                    and w['expires']==expected['expires_at'],'Track budgets/deadline changed')
        return self.store.attest(purpose,subject,self.profile.evidence.principal,
            provenance=(self.store.source(self.profile.evidence),),binding={'context_digest':digest(context),'expires_at':self.profile.evidence.expires_at})

    def validate_gates(self, context):
        from .project_validation_types import EvidenceGate, ObservationQuery, ProjectObservation
        gates=context.get('gates') or [context.get('gate')]
        require(gates and all(gates),'Authentic project gate provenance required')
        for raw in gates:
            gate=typed(EvidenceGate,raw)
            reference=gate.evidence.split(':',1)[1]
            proof=self.store.find('project-validation/observation',reference)
            require(proof is not None,'Actual project observation receipt is missing')
            body=self.store.read(proof.reference)['binding']
            query=typed(ObservationQuery,body['query'])
            observation=typed(ProjectObservation,body['observation'])
            observation=replace(observation,evidence=proof)
            matches=[v for v in self.validators.values() if v.task.task_id==gate.request.task_id and data(v.policy)==context['policy']]
            require(matches and any(data(v._evaluate(query,observation))==raw for v in matches),
                'Current project policy or actual observation differs')
