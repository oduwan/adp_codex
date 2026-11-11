"""Focused #17 enrollment/authority/entry-point checks, never a track campaign."""
from dataclasses import replace
import copy
import hashlib
import hmac
import io
import json
from pathlib import Path
from unittest.mock import patch

from operator_fixtures import OperatorFixture, run, snapshot
from adp import cli
from adp.cli import parser
from adp.discovery_schema import digest, typed
from adp.errors import ADPError
from adp.execution_types import Role
from adp.guard_types import Attestation, Limits, data
from adp.operator_authority import OperatorAuthority, remote_semantics
from adp.operator_controller import READ_PERMISSIONS, InstalledProject
from adp.operator_evidence import OperatorEvidence
from adp.operator_profile import load_profile, private_file
from adp.operator_providers import ProjectProviders
from adp.operator_setup import preview, setup, status, verify_enrollment
from adp.policy_adapters import MockRepositoryAdapter
from adp.policy_types import Operation, Request, Qualifications
from adp.project_validation_types import Phase
from adp.ticket_preparation import TicketArchive
from adp.ticket_types import OriginalTicket


class OperatorProfileTests(OperatorFixture):
    def test_installed_profile_signature_repository_and_roles(self):
        self.assertEqual(self.profile.repository_id,'17')
        raw=private_file(self.profile_path);raw['payload']['repository_id']='18';self.write(self.profile_path,raw)
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)

    def test_unsafe_profile_and_secret_paths_refuse(self):
        self.profile_path.chmod(0o644)
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)
        self.profile_path.chmod(0o600)
        key=self.auth/'automation.key.json';target=self.auth/'saved.key.json';key.rename(target);key.symlink_to(target)
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)
        key.unlink();target.rename(key)
        self.body['memory']['repo']='relative-control'
        with self.assertRaises(ADPError): self.refresh_profile()

    def test_duplicate_unknown_schema_and_executable_fields_refuse(self):
        for field,value in (('schema_version',2),('controller','run-this.py')):
            raw=self.signed('profile',self.body);raw[field]=value;self.write(self.profile_path,raw)
            with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)
        self.profile_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)

    def test_expired_and_revoked_delegation_refuse(self):
        self.sign_write('profile',self.body,expires=self.now-1)
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust,clock=lambda:self.now)
        self.refresh_profile();self.sign_write('revocations',{'repository_id':'17','sequence':1,'revoked':[self.body['id']]})
        with self.assertRaises(ADPError): self.profile.live()

    def test_exact_issue_operation_and_branch_scope(self):
        for key,value in (('issues',['foreign']),('operations',['DEPLOY']),('branches',['refs/heads/foreign'])):
            original=copy.deepcopy(self.body);self.body['delegation'][key]=value
            with self.assertRaises(ADPError): self.refresh_profile()
            self.body=original
        self.refresh_profile()

    def test_limits_expiry_and_resume_cannot_expand(self):
        for name,value in (('maximum_rounds',33),('maximum_parallel',5),('expires_at',self.now+301)):
            saved=copy.deepcopy(self.body);self.body['window'][name]=value
            with self.assertRaises(ADPError): self.refresh_profile()
            self.body=saved
        self.refresh_profile();setup(self.profile,authorized=True)
        self.body['window']['id']='8'*64;self.refresh_profile()
        with self.assertRaises(ADPError): verify_enrollment(self.profile)

    def test_key_alias_and_issue_author_cannot_approve_scope(self):
        root=private_file(self.trust);root['principals'][2]['key_file']=root['principals'][1]['key_file'];self.write(self.trust,root)
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)

    def test_changed_policy_and_check_provider_refuse(self):
        a=self.installed();adapter=MockRepositoryAdapter(replace(self.policy_snapshot,documents=()))
        with self.assertRaises(ADPError): a.providers.policy(adapter)
        self.body['checks'][0]['provider']='foreign-provider';self.refresh_profile()
        # The installed validator retains this exact identity; existing native
        # #21 rejects project results from the original provider.
        self.assertEqual(self.profile.checks[0].provider,'foreign-provider')

    def test_credential_possession_does_not_authorize_effect(self):
        installed=self.installed();a=installed.authority
        token=a.credential(self.body['providers']['credentials']['read'],READ_PERMISSIONS)
        self.assertTrue(token.token)
        with self.assertRaises(ADPError): a.grant(purpose='execution/effect',subject='a'*64,context={})

    def test_specific_scope_addition_receipt_cannot_be_replaced_by_profile(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        with self.assertRaises(ADPError): a.grant(purpose='ticket/scope-addition',subject='a'*64,context={'change':'new feature'})
        with self.assertRaises(ADPError): a.decision('ticket/scope-addition','a'*64,{'change':'new feature'},operator=True)


class OperatorEnrollmentTests(OperatorFixture):
    def test_two_project_policies_preview_distinct_rules(self):
        first=preview(self.profile)
        self.assertEqual(first['status'],'CONFIGURATION_VERIFIED')
        setup(self.profile,authorized=True)
        self.assertTrue(status(self.profile)['local_owner'])
        run(self.product,'branch','-m','change/one')
        self.body['delegation'].update(branches=['refs/heads/change/one'],merge_mode='DELEGATED',merge_methods=['squash'])
        self.rules=replace(self.rules,base_branch='stable',branch_template='change/{slug}',subject_template='repair: {summary}',merge_method='squash')
        self.refs=(replace(self.refs[0],name='refs/heads/stable'),replace(self.refs[1],name='refs/heads/change/one'))
        self.casmock.return_value=self.refs
        self.policy_snapshot=replace(self.policy_snapshot,source_ref='refs/heads/change/one',remote_refs=self.refs)
        self.install_policy();self.refresh_profile();self.install_assessment()
        second=preview(self.profile)
        self.assertEqual(second['policy'][0]['rules'][0]['base_branch'],'stable')
        self.assertNotEqual(first['policy'][0]['rules'],second['policy'][0]['rules'])
        self.assertEqual(second['merge_mode'],'DELEGATED')
        other=OperatorFixture()
        other.repository_id='18';other.project_name='beta/tooling'
        other.setUp()
        try:
            other.rules=replace(other.rules,base_branch='stable',branch_template='change/{slug}',
                subject_template='repair: {summary}',merge_method='squash',checks=('smoke',))
            run(other.product,'branch','-m','change/one')
            other.refs=(replace(other.refs[0],name='refs/heads/stable'),replace(other.refs[1],name='refs/heads/change/one'))
            other.casmock.return_value=other.refs
            other.policy_snapshot=replace(other.policy_snapshot,source_ref='refs/heads/change/one',remote_refs=other.refs)
            other.body['delegation'].update(branches=['refs/heads/change/one'],merge_mode='MANUAL',merge_methods=['squash'])
            other.body['checks'][0].update(name='smoke',origin='fixture:independent-checks')
            other.install_policy();other.refresh_profile();other.install_assessment()
            other.assessment['tasks'][0]['scope']['checks']=['smoke']
            other.sign_write('assessment',other.assessment)
            report=preview(other.profile)
            self.assertEqual(report['status'],'CONFIGURATION_VERIFIED')
            self.assertEqual(report['repository_id'],'18');self.assertNotEqual(other.head,self.head)
            self.assertEqual(report['checks'][0]['name'],'smoke')
            self.assertEqual(report['merge_mode'],'MANUAL')
            setup(other.profile,authorized=True)
            self.assertTrue(status(other.profile)['local_owner'])
            self.assertEqual(status(other.profile)['generation'],1)
        finally: other.doCleanups()

    def test_preview_and_doctor_preserve_files_refs_and_memory(self):
        from adp.operator_cli import run as entry
        before=snapshot(self.base)
        report=preview(self.profile)
        self.assertEqual(snapshot(self.base),before)
        from adp.execution_types import Capabilities
        args=parser().parse_args(['doctor','--operator-profile',str(self.profile_path),
            '--operator-trust',str(self.trust),'--check-runtime'])
        with patch('adp.operator_cli.load_profile',return_value=self.profile),patch('adp.codex_runtime.CodexExecRuntime.capabilities',
                return_value=Capabilities('codex-exec','private-host','fixture-version',True,True,True,True,1)):
            observed,code=entry(args)
        self.assertEqual(observed['runtime']['version'],'fixture-version')
        self.assertNotIn('private-host',json.dumps(observed));self.assertEqual(snapshot(self.base),before)
        self.assertFalse(self.profile.state.exists());self.assertEqual(report['mode'],'READ_ONLY')
        args=parser().parse_args(['doctor','--operator-profile',str(self.profile_path),'--operator-trust',str(self.trust)])
        with patch('adp.operator_cli.load_profile',return_value=self.profile): entry(args)
        self.assertEqual(snapshot(self.base),before)

    def test_missing_or_partial_metadata_remains_unknown(self):
        self.transport.responses.pop('/repos/demo/project/issues/1/dependencies/blocked_by?per_page=100&page=1')
        report=preview(self.profile)
        self.assertEqual(report['discovery'],'UNKNOWN');self.assertEqual(report['status'],'UNKNOWN')
        self.assertEqual(report['tasks'][0]['status'],'UNKNOWN')

    def test_canonical_repository_and_remote_drift_refuse(self):
        run(self.product,'remote','set-url','origin','https://github.com/foreign/project')
        with self.assertRaises(ADPError): load_profile(self.profile_path,self.trust)

    def test_manual_and_delegated_merge_intersect_project_rules(self):
        installed=self.installed()
        provider=installed.policy_factories[self.profile.tasks[0].task_id]()
        inspection=provider.inspect_repository()
        self.assertFalse(inspection.conflicts);self.assertEqual(self.profile.delegation['merge_mode'],'MANUAL')
        self.assertEqual(inspection.sources[0].rules.merge_method,'merge')

    def test_native_check_phases_and_provider_identities_preserved(self):
        self.body['providers']['validation'].update(kind='github',path=None,mode='POST_PR')
        with self.assertRaises(ADPError): self.refresh_profile()
        self.body['checks'][0].update(phase='AFTER_PR',denominator=None,native_record_is_attempt=True,
            provider='github-check-run',origin='github-app:123')
        self.refresh_profile();self.assertEqual(self.profile.checks[0].origin,'github-app:123')

    def test_setup_requires_explicit_authority_before_writes(self):
        before=snapshot(self.base)
        with self.assertRaises(ADPError): setup(self.profile)
        self.assertEqual(before,snapshot(self.base))

    def test_setup_initializes_actual_m1_m2_and_track_once(self):
        setup(self.profile,authorized=True)
        from adp.memory import Memory
        memory=Memory(self.profile.memory_config());before=memory.inspect()
        setup(self.profile,authorized=True)
        after=memory.inspect()
        self.assertEqual(before['local_head'],after['local_head']);self.assertEqual(after['state']['schema_version'],3)
        self.assertEqual(after['state']['execution']['schema_version'],3)
        self.assertEqual(after['state']['progress_guard'],before['state']['progress_guard'])

    def test_interrupted_setup_reobserves_without_reset_or_duplicate_claim(self):
        from adp.operator_evidence import OperatorEvidence
        with patch.object(OperatorEvidence,'prepare',side_effect=OSError('fixture before private preparation')):
            with self.assertRaises(OSError): setup(self.profile,authorized=True)
        self.assertFalse((self.profile.state/'revocation.json').exists())
        recovered=load_profile(self.profile_path,self.trust,clock=lambda:self.now,
            retain_revocation=True,recover_initial_setup=True)
        from adp.execution_memory import ExecutionJournal
        with patch.object(ExecutionJournal,'upgrade_product_flow',side_effect=OSError('fixture interrupted')):
            with self.assertRaises(OSError): setup(recovered,authorized=True)
        generation=status(self.profile)['generation'];setup(self.profile,authorized=True)
        self.assertEqual(status(self.profile)['generation'],generation)

    def test_foreign_owner_and_changed_enrollment_refuse(self):
        setup(self.profile,authorized=True)
        from adp.memory import Memory
        memory=Memory(self.profile.memory_config())
        with patch.object(memory,'_owns',return_value=False), patch('adp.operator_setup.Memory',return_value=memory):
            with self.assertRaises(ADPError): setup(self.profile,authorized=True)
        self.body['delegation']['merge_mode']='DELEGATED';self.refresh_profile()
        with self.assertRaises(ADPError): verify_enrollment(self.profile)

    def test_revocation_and_expiry_during_setup_refuse(self):
        setup(self.profile,authorized=True)
        old=private_file(self.auth/'revocations.json')
        self.sign_write('revocations',{'repository_id':'17','sequence':2,'revoked':[]})
        self.profile.live(retain=True)
        self.write(self.auth/'revocations.json',old)
        with self.assertRaises(ADPError): self.profile.live()
        self.sign_write('revocations',{'repository_id':'17','sequence':3,'revoked':['delegation-one']})
        with self.assertRaises(ADPError): setup(self.profile,authorized=True)

    def test_missing_private_history_blocks_recovery(self):
        setup(self.profile,authorized=True)
        (self.profile.state/'revocation.json').unlink()
        with self.assertRaises(ADPError): verify_enrollment(self.profile)
        with self.assertRaises(ADPError): setup(self.profile,authorized=True)
        self.assertFalse((self.profile.state/'revocation.json').exists())


class OperatorAuthorityTests(OperatorFixture):
    def prepare(self):
        setup(self.profile,authorized=True)
        installed=self.installed(mutating=True)
        archive=TicketArchive(self.profile.state/'test-original',protected_roots=(self.product,))
        reference=archive.freeze(self.snap,self.snap.issues[0].identity)
        original=archive.original(reference)
        reviews=installed.providers.reviews((self.snap,))
        track=installed.planner.plan((self.snap,),reviews=reviews)
        inspection=installed.policy_factories[self.profile.tasks[0].task_id]().inspect_repository()
        inputs=installed.providers.assess(original,track,inspection,reference)
        return installed,archive,original,track,inspection,inputs

    def test_task_assessment_binds_original_scope_and_full_proposal(self):
        installed,archive,original,track,inspection,inputs=self.prepare()
        self.assertEqual(inputs.scope.goal,'Correct the existing answer')
        self.assertEqual(inputs.proposal.instructions,('Use prescribed project evidence',))
        self.assertEqual(inputs.proposal.policy_digest,inspection.digest)
        self.assessment['tasks'][0]['scope']['allowed_paths'].append('extra.py');self.sign_write('assessment',self.assessment)
        with self.assertRaises(ADPError): installed.providers.assess(original,track,inspection,inputs.scope.original_reference)

    def test_readiness_binds_current_remote_snapshot_and_dependencies(self):
        installed=self.installed();reviews=installed.providers.reviews((self.snap,))
        track=installed.planner.plan((self.snap,),reviews=reviews)
        self.assertEqual(str(track.candidates[0].status),'READY')
        changed=replace(self.snap,issues=(replace(self.snap.issues[0],body='Malicious newly added requirements'),))
        with self.assertRaises(ADPError): installed.providers.reviews((changed,))

    def test_changed_issue_scope_and_dependency_laundering_refuse(self):
        installed,archive,original,track,inspection,inputs=self.prepare()
        changed=replace(original,issue=replace(original.issue,body='expanded'))
        with self.assertRaises(ADPError): installed.providers.assess(changed,track,inspection,inputs.scope.original_reference)
        self.assessment['tasks'][0]['readiness']['confirmed_dependencies']=[{'repository_id':'17','issue_id':'foreign','forge':'github'}]
        self.sign_write('assessment',self.assessment)
        reviews=installed.providers.reviews((self.snap,));new=installed.planner.plan((self.snap,),reviews=reviews)
        self.assertNotEqual(str(new.candidates[0].status),'READY')

    def test_independent_assessment_identity_and_expiry_not_renewed(self):
        installed,archive,original,track,inspection,inputs=self.prepare()
        self.assertEqual(inputs.review.expires_at,self.now+300)
        self.assertEqual(inputs.scope.evidence.reviewer,'independent')
        self.now+=301
        with self.assertRaises(ADPError): installed.providers.assess(original,track,inspection,inputs.scope.original_reference)

    def test_unsigned_or_wrong_purpose_approval_refuse(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        fake=Attestation('independent','operator-proof:'+'a'*64,'b'*64)
        self.assertFalse(a.verify(fake,purpose='ticket/preparation',subject='b'*64))
        proof=a.proof('ticket/original-scope','b'*64,self.profile.evidence)
        self.assertFalse(a.verify(proof,purpose='ticket/preparation',subject='b'*64))
        def responder(challenge):
            return self.signed('decision',{k:challenge[k] for k in ('repository_id','purpose','subject','context_digest')})
        def invoke():
            current=OperatorAuthority(self.profile,mutating=True)
            proof=current.decision('track/change-scope','c'*64,{'diff':'one exact original-scope edit'})
            self.assertTrue(current.verify(proof,purpose='track/change-scope',subject='c'*64))
            return proof
        proof,challenges=self.serve_decision(responder,invoke)
        self.assertEqual(len(challenges),1);self.assertEqual(challenges[0]['context']['diff'],'one exact original-scope edit')
        # A genuine installed peer still cannot return another subject/purpose.
        def wrong(challenge):
            payload={k:challenge[k] for k in ('repository_id','purpose','subject','context_digest')}
            payload['subject']='d'*64
            return self.signed('decision',payload)
        def reject():
            with self.assertRaises(ADPError): OperatorAuthority(self.profile,mutating=True).decision('track/change-scope','c'*64,{'diff':'x'})
        self.serve_decision(wrong,reject)

    def test_token_issuance_pins_actual_repository_and_permissions(self):
        a=self.installed().authority
        token=a.credential(self.body['providers']['credentials']['read'],READ_PERMISSIONS)
        from adp.network_http import installation_scope_subject
        self.assertTrue(a.verify(token.evidence,purpose='github/installation-token-scope',subject=installation_scope_subject(token,permissions=READ_PERMISSIONS)))
        path=Path(self.body['providers']['credentials']['read']);raw=private_file(path)
        raw['payload']['issuance_response']['repository_ids']=[18];self.write(path,self.signed('credential',raw['payload']))
        self.assertFalse(a.verify(token.evidence,purpose='github/installation-token-scope',subject=token.evidence.subject))

    def test_policy_authority_uses_current_verified_documents_and_protection(self):
        installed=self.installed();provider=installed.providers.policy(MockRepositoryAdapter(self.policy_snapshot))
        self.assertEqual(len(provider.inspect_repository().sources),1)
        changed=replace(self.policy_snapshot,remote_refs=tuple(replace(r,revision='a'*40) for r in self.refs))
        with self.assertRaises(ADPError): installed.providers.policy(MockRepositoryAdapter(changed))

    def test_exact_runtime_reviewer_receipts_require_actual_role_sha_and_stop(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        with self.assertRaises(ADPError): a.runtime_fact('fixture:forged','worker:forged')
        with self.assertRaises(ADPError): a.grant(purpose='policy/review',subject='a'*64,
            context={'receipt':'fixture:forged','revision':self.head,'reviewer':'worker:forged'})

    def test_project_check_attestation_requires_authenticated_provenance(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        with self.assertRaises(ADPError): a.validate_gates({'gate':None,'policy':{}})
        # A caller positive boolean never authenticates a #21 gate.
        with self.assertRaises(ADPError): a.grant(purpose='policy/project-check',subject='a'*64,context={'gate':{'qualified':True},'policy':{}})

    def test_changed_sha_branch_and_pr_head_invalidate_grants(self):
        installed=self.installed();old=remote_semantics((self.snap,))
        from adp.discovery_types import PullRequest
        changed=replace(self.snap,repository=replace(self.snap.repository,checkout_sha='a'*40))
        self.assertEqual(remote_semantics((changed,)),old) # local source is separately bound by exact M3 plans
        changed=replace(self.snap,issues=(replace(self.snap.issues[0],revision='b'*64),))
        self.assertNotEqual(remote_semantics((changed,)),old)
        run(self.product,'branch','-m','foreign')
        with self.assertRaises(ADPError): self.profile.project_config(self.profile.tasks[0])

    def test_live_revocation_blocks_final_effect_and_replay(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        proof=a.proof('policy/operation','a'*64,self.profile.evidence)
        original=private_file(self.auth/'revocations.json')
        self.sign_write('revocations',{'repository_id':'17','sequence':1,'revoked':['delegation-one']})
        self.assertFalse(a.verify(proof,purpose='policy/operation',subject='a'*64))
        with self.assertRaises(ADPError):
            load_profile(self.profile_path,self.trust,clock=lambda:self.now,retain_revocation=True)
        self.write(self.auth/'revocations.json',original)
        with self.assertRaises(ADPError): self.profile.live()

    def test_durable_receipts_survive_restart_without_reissuing_effects(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        proof=a.proof('ticket/preparation','a'*64,a.signed('assessment'))
        other=OperatorAuthority(self.profile,mutating=True)
        self.assertTrue(other.verify(proof,purpose='ticket/preparation',subject='a'*64))
        self.assertEqual(other.store.find('ticket/preparation','a'*64),proof)
        self.assertEqual(status(self.profile)['task_stages'],{})

    def test_original_guard_and_owner_fences_cannot_be_overridden(self):
        setup(self.profile,authorized=True);controller=self.installed(mutating=True).build()
        controller.track._window(create=True)
        track=controller.conductor.readiness.observe()
        admission=controller.track._prepare(controller.track.tasks[0],track)
        self.assertIsNotNone(admission)
        project=controller.conductor.projects[admission.workspace_key]
        packet=project.lifecycle.packet()
        candidate=next(c for c in track.candidates if c.identity==admission.identity)
        subject=digest({'original':packet.original_reference,'preparation':packet.preparation_reference,
            'current_issue':data(candidate.issue),'revision':self.head,'goal':admission.product_goal,
            'acceptance':admission.requirement.acceptance,'paths':admission.allowed_paths,'checks':packet.checks})
        context={'packet':data(packet),'current_issue':data(candidate.issue)}
        self.write(self.auth/'decisions.json',{'schema_version':1,'decisions':[self.signed('decision',{
            'repository_id':self.profile.repository_id,'purpose':'github-product/scope','subject':subject,'context_digest':digest(context)})]})
        controller.conductor._admit(admission,track,controller.conductor.journal.inspect()['state']['generation'])
        self.assertEqual(controller.conductor._task(admission)['jobs'],{})
        from adp.guard_types import Requirement
        with self.assertRaises(ADPError): controller.conductor.authority.grant(purpose='admission',subject='a'*64,
            context={'task_id':self.profile.tasks[0].task_id,'requirement':data(Requirement('original','gate',('accept',),limits=Limits(failures=4)))})
        before=controller.conductor.journal.inspect()['state']['progress_guard']
        self.assertEqual(before,controller.conductor.journal.inspect()['state']['progress_guard'])

    def test_missing_unsupported_backends_do_not_gain_authority(self):
        setup(self.profile,authorized=True);a=self.installed(mutating=True).authority
        for purpose in ('release','deploy','unknown-backend'):
            with self.assertRaises(ADPError): a.grant(purpose=purpose,subject='a'*64)


class OperatorCLITests(OperatorFixture):
    def args(self,command,*extra):
        return parser().parse_args([command,'--operator-profile',str(self.profile_path),'--operator-trust',str(self.trust),*extra])

    def test_installed_entry_points_need_no_python_controller(self):
        for command,extra in (('setup',('--dry-run',)),('doctor',()),('preview',()),('status',()),('run',()),('resume',()),('handoff',())):
            args=self.args(command,*extra)
            self.assertIsNone(getattr(args,'controller',None));self.assertEqual(args.operator_profile,self.profile_path)

    def test_legacy_memory_and_controller_contracts_preserved(self):
        args=parser().parse_args(['run','--controller','/tmp/controller.py','--authorize-execution'])
        self.assertIsNone(args.operator_profile)
        self.assertTrue(parser().parse_args(['init','--dry-run']).dry_run)
        args=self.args('run','--controller','/tmp/controller.py','--authorize-execution')
        from adp.operator_cli import run as entry
        with self.assertRaises(ADPError): entry(args)

    def test_run_entry_uses_actual_ports_with_finite_profile_limits(self):
        setup(self.profile,authorized=True)
        controller=self.installed(mutating=True).build()
        from adp.codex_runtime import CodexExecRuntime
        from adp.network_git import GitHubGitExecutionPort
        from adp.github_product import GitHubProductForge
        self.assertIs(type(controller.conductor.runtime),CodexExecRuntime)
        project=next(iter(controller.conductor.projects.values()))
        self.assertIs(type(project.git_port),GitHubGitExecutionPort);self.assertIs(type(project.forge),GitHubProductForge)
        from adp.operator_cli import run as entry
        with patch('adp.operator_cli.load_profile',return_value=self.profile), patch.object(InstalledProject,'build',return_value=controller), \
                patch.object(controller.track,'run',return_value={'status':'PENDING_VALIDATION'}) as method:
            report,code=entry(self.args('run','--authorize-execution','--rounds','2'))
        self.assertEqual(method.call_args.kwargs,{'rounds':2,'maximum_parallel':1,'authorized':True})
        self.assertEqual(code,4);self.assertEqual(report['status'],'PENDING_VALIDATION')
        self.assertEqual(len(report['tasks']),1);self.assertEqual(report['tasks'][0]['status'],'NOT_ADMITTED')
        self.assertIn('exact-SHA',report['next_action'])

    def test_missing_execution_flag_and_excessive_bounds_refuse(self):
        from adp.operator_cli import run as entry
        for extra in ((),('--authorize-execution','--rounds','5'),('--authorize-execution','--maximum-parallel','2')):
            with patch('adp.operator_cli.load_profile',return_value=self.profile):
                with self.assertRaises(ADPError): entry(self.args('run',*extra))
        self.assertFalse(self.profile.state.exists())

    def test_resume_uses_existing_window_and_safe_owner_recovery(self):
        setup(self.profile,authorized=True);controller=self.installed(mutating=True).build()
        from adp.operator_cli import run as entry
        before=controller.conductor.journal.inspect()['state']['progress_guard']
        with patch('adp.operator_cli.load_profile',return_value=self.profile), patch.object(InstalledProject,'build',return_value=controller), \
                patch.object(controller.track,'resume',return_value={'status':'WAITING_HUMAN_APPROVAL'}) as method:
            result,code=entry(self.args('resume','--authorize-execution'))
        self.assertTrue(method.called);self.assertEqual(result['status'],'WAITING_HUMAN_APPROVAL')
        self.assertEqual(controller.track.window.id,self.body['window']['id'])
        self.assertEqual(before,controller.conductor.journal.inspect()['state']['progress_guard'])

    def test_handoff_preserves_unknown_stops_and_reviewed_sha_limit(self):
        setup(self.profile,authorized=True);controller=self.installed(mutating=True).build()
        from adp.operator_cli import run as entry
        with patch('adp.operator_cli.load_profile',return_value=self.profile), patch.object(InstalledProject,'build',return_value=controller), \
                patch.object(controller.track,'handoff',side_effect=ADPError('UNSUPPORTED_REVIEWED_SHA_HANDOFF')):
            with self.assertRaisesRegex(ADPError,'UNSUPPORTED_REVIEWED_SHA_HANDOFF'):
                entry(self.args('handoff','--authorize-execution'))

    def test_status_has_no_dispatch_and_honest_pending_outcomes(self):
        from adp.operator_cli import run as entry
        before=snapshot(self.base)
        with patch('adp.operator_cli.load_profile',return_value=self.profile),patch.object(InstalledProject,'build',side_effect=AssertionError('no build')):
            result,code=entry(self.args('status'))
        self.assertEqual(result['execution_liveness'],'UNKNOWN');self.assertEqual(snapshot(self.base),before)

    def test_output_and_worker_inputs_never_include_private_credentials(self):
        from adp.operator_cli import run as entry
        with patch('adp.operator_cli.load_profile',return_value=self.profile):
            result,code=entry(self.args('preview'))
        rendered=json.dumps(result)
        for value in ('fixture-private-',str(self.auth),self.keys['automation'].hex()): self.assertNotIn(value,rendered)
        # No worker was launched: existing lifecycle prompt preservation is part
        # of the accepted 400-test denominator, not a new runtime qualification.
        self.assertFalse(self.profile.state.exists())
