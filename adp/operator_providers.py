"""Installed data adapters for independently interpreted project policy and scope."""
from __future__ import annotations

from dataclasses import replace

from .autonomous_track import PreparationInputs
from .errors import ADPError
from .discovery import review_subject
from .discovery_schema import digest, typed
from .discovery_types import ReadinessReview
from .guard_types import data
from .execution_privacy import credential_shaped
from .operator_authority import remote_semantics
from .policy import PolicyProvider
from .policy_types import SourceClaim, SourceKind, Protection
from .schema import fields, require
from .ticket_preparation import original_scope_subject, preparation_subject, addition_subject, change_digest, validate_proposal
from .ticket_types import OriginalScope, Proposal, PreparationReview, ScopeAdditionApproval, ChangeKind, DependencyEdit, OriginalTicket


def policy_semantics(snapshot):
    return digest({'repository_id':snapshot.repository_id,'remote_fingerprint':snapshot.remote_fingerprint,
        'documents':[data(d) for d in snapshot.documents]})


def assessment_policy(inspection):
    return digest({'documents':policy_semantics(inspection.snapshot),
        'sources':[{'kind':s.kind,'reference':s.reference,'document_digest':s.document_digest,
            'rules':data(s.rules),'principal':s.evidence.reviewer} for s in inspection.sources]})


class ProjectProviders:
    def __init__(self, profile, authority):
        self.p,self.a=profile,authority

    def preview_task(self, task, candidate, inspection, snapshot, source):
        from .operator_profile import private_file
        from .schema import key as task_key
        from .discovery_schema import key as identity_key
        path=self.p.state/'tickets'/task_key(task.task_id)/('baseline-'+identity_key(candidate.identity)+'.json')
        original=(typed(OriginalTicket,private_file(path)) if path.exists() else
            OriginalTicket(snapshot.repository,candidate.issue,snapshot.observed_at))
        row=next(r for r in source.payload['tasks'] if r['issue_id']==task.issue_id)
        require(original.issue.identity==candidate.identity and row['original_issue_digest']==digest(data(original.issue))
            and row['policy_semantics']==assessment_policy(inspection),'Current policy/original ticket assessment differs')
        require(row['scope'].get('original_reference') is None and row['scope'].get('evidence') is None
            and row['proposal'].get('original_reference') is None and row['proposal'].get('policy_digest') is None,
            'Only mechanical preview archive/policy bindings may be unset')
        reference='ticket-original:'+digest(data(original))
        scope=typed(OriginalScope,{**row['scope'],'original_reference':reference})
        proposal=typed(Proposal,{**row['proposal'],'original_reference':reference,'policy_digest':inspection.digest})
        validate_proposal(original,scope,proposal)
        require(proposal.expected_issue_revision==candidate.issue.revision,'Prepared ticket version is stale')
        required={check for claim in inspection.sources for check in claim.rules.checks}
        require(set(scope.checks)==required=={check.name for check in self.p.checks},'Project-prescribed check inventory differs')
        return {'scope':data(scope),'proposal':data(proposal),'execution_authority':'UNKNOWN',
            'blockers':['Specific external scope-addition approval required'] if any(c.kind in (ChangeKind.ADDITION,ChangeKind.UNKNOWN) for c in proposal.changes) else []}

    def policy(self, adapter, safety=None):
        """Project verifier owns interpretation and protection observations.

        The signed source rows retain their original times. Local revision/ref
        rebinding is mechanical only while every reviewed document is identical.
        Protection rows keep exact observed remote revisions and native limits.
        """
        snapshot=adapter.inspect()
        try:
            source=self.a.signed('policy')
            require(source.payload['document_inventory_digest']==policy_semantics(snapshot)
                and all(next((r.revision for r in snapshot.remote_refs if r.name==p['ref']),None)==p['revision']
                    for p in source.payload['protections']),'Current policy observation changed')
        except (ADPError,OSError,KeyError):
            source=self.a.request_data('policy','policy/inspect',{'snapshot':data(snapshot)})
        body=source.payload
        fields(body,'repository_id document_inventory_digest paths sources protections')
        require(body['document_inventory_digest']==policy_semantics(snapshot),
            'UNKNOWN: project governance changed or is not independently interpreted')
        provider=PolicyProvider(adapter,authority=self.a,safety=safety,clock=self.p.trust.clock)
        sources=[]
        for raw in body['sources']:
            claim=typed(SourceClaim,raw)
            require(claim.kind in (SourceKind.GOVERNANCE,SourceKind.PROFILE,SourceKind.CONTRACT)
                and claim.evidence is None and source.issued_at<=claim.observed_at<claim.expires_at<=source.expires_at,
                'Project policy source or original expiry differs')
            purpose='policy/'+claim.kind.lower()
            sources.append(replace(claim,evidence=self.a.proof(purpose,provider.source_subject(claim,snapshot),source,
                binding={'expires_at':claim.expires_at})))
        protections=[]
        for raw in body['protections']:
            protection=typed(Protection,raw)
            require(protection.evidence is None and source.issued_at<=protection.observed_at<protection.expires_at<=source.expires_at,
                'Project protection observation expiry differs')
            actual=next((r.revision for r in snapshot.remote_refs if r.name==protection.ref),None)
            require(actual==protection.revision and snapshot.remote_refs_known,'Current remote protection revision differs')
            protections.append(replace(protection,evidence=self.a.proof('policy/protection',
                provider.protection_subject(protection,snapshot),source,binding={'expires_at':protection.expires_at})))
        provider.sources,provider.protections=tuple(sources),tuple(protections)
        return provider

    def assessment(self, snapshots):
        try:
            source=self.a.signed('assessment')
            require(source.payload['snapshot_digest']==remote_semantics(snapshots),'Remote inventory changed')
        except (ADPError,OSError,KeyError):
            source=self.a.request_data('assessment','track/assessment',{'snapshots':[data(s) for s in snapshots]})
        body=source.payload
        fields(body,'repository_id snapshot_digest tasks')
        require(not credential_shaped(body),'Private credential-shaped task evidence cannot enter previews or packets')
        require(body['snapshot_digest']==remote_semantics(snapshots) and type(body['tasks']) is list
            and 1<=len(body['tasks'])<=64,'UNKNOWN: independent assessment does not cover the current remote inventory')
        return source

    def reviews(self, snapshots):
        source=self.assessment(snapshots)
        result=[]
        for row in source.payload['tasks']:
            fields(row,'issue_id original_issue_digest policy_semantics scope proposal readiness preparer dependency_edits')
            review=typed(ReadinessReview,row['readiness'])
            require(review.scope==row['scope']['goal'] and review.acceptance==tuple(
                c['text'] for c in row['scope']['clauses'] if c['kind']=='ACCEPTANCE'),
                'Readiness interpretation differs from the independently reviewed original scope')
            issue=next((i for s in snapshots for i in s.issues if i.identity==review.identity),None)
            require(issue is not None and review.identity.issue_id==row['issue_id'] and review.evidence is None
                and source.principal not in issue.authors and source.principal!=row['preparer']
                and source.issued_at<=review.observed_at<review.expires_at<=source.expires_at,
                'Current independent readiness identity or expiry differs')
            evidence=self.a.proof('discovery/readiness',review_subject(snapshots,review),source,
                binding={'expires_at':review.expires_at})
            result.append(replace(review,evidence=evidence))
        return tuple(result)

    def assess(self, original, track, inspection, reference):
        source=self.assessment(track.snapshots)
        rows=[r for r in source.payload['tasks'] if r['issue_id']==original.issue.identity.issue_id]
        require(len(rows)==1,'Independent original ticket assessment is missing or ambiguous')
        row=rows[0]
        require(source.principal not in original.issue.authors and source.principal!=row['preparer']
            and row['original_issue_digest']==digest(data(original.issue))
            and row['policy_semantics']==assessment_policy(inspection),
            'Original ticket or project policy interpretation changed')
        raw=dict(row['scope'])
        require(raw.get('original_reference') is None and raw.get('evidence') is None,
            'Signed scope binds original issue identity; archive reference is assigned mechanically')
        raw['original_reference']=reference
        scope=typed(OriginalScope,raw)
        # Persist the FIRST interpretation separately. A refreshed provider cannot
        # quietly rewrite allowed paths/checks/clauses of a frozen original.
        baseline=digest({'domain':'operator/original-scope','identity':data(original.issue.identity),
            'original_issue_digest':row['original_issue_digest']})
        existing=self.a.store.find('operator/original-scope',baseline)
        interpretation={k:v for k,v in data(scope).items() if k not in ('evidence','original_reference')}
        if existing:
            require(self.a.store.read(existing.reference)['binding']['interpretation']==interpretation,
                'BLOCKED_OPERATOR: frozen original interpretation cannot be expanded by a profile/provider refresh')
        else:
            self.a.proof('operator/original-scope',baseline,source,binding={'interpretation':interpretation})
        scope=replace(scope,evidence=self.a.proof('ticket/original-scope',original_scope_subject(scope),source,
            binding={'expires_at':source.expires_at}))
        raw=dict(row['proposal'])
        require(raw.get('original_reference') is None and raw.get('policy_digest') is None,
            'Signed proposal must leave only mechanical archive/policy bindings unset')
        raw.update(original_reference=reference,policy_digest=inspection.digest)
        proposal=typed(Proposal,raw)
        review=PreparationReview(row['preparer'],source.issued_at,source.expires_at)
        review=replace(review,evidence=self.a.proof('ticket/preparation',
            preparation_subject(original,scope,proposal,review,track),source,binding={'expires_at':source.expires_at}))
        additions=[]
        for change in proposal.changes:
            if change.kind!=ChangeKind.ADDITION: continue
            approval=ScopeAdditionApproval(change.id,reference,change_digest(change),source.issued_at,source.expires_at)
            evidence=self.a.decision('ticket/scope-addition',addition_subject(approval),
                {'original':data(original),'change':data(change),'scope':data(scope),'proposal':data(proposal)},operator=True)
            additions.append(replace(approval,evidence=evidence))
        require(type(row['dependency_edits']) is list and len(row['dependency_edits'])<=32,'Bounded reviewed dependency edits required')
        edits=tuple(typed(DependencyEdit,value) for value in row['dependency_edits'])
        return PreparationInputs(scope,proposal,review,tuple(additions),edits)
