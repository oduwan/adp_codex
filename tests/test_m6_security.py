"""Q10: synthetic recognizable credentials must never reach portable memory."""
from dataclasses import replace
import json
import unittest

from adp.errors import ADPError
from adp.execution_types import Role
from adp.guard_types import DecisionKind
from execution_fixtures import ExecutionFixture
from test_config import run


class PortableOutputSecurityTests(ExecutionFixture):
    def test_worker_credential_shape_is_refused_before_any_checkpoint(self):
        admission=self.admissions[0]
        generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        assignment,job=self.conductor._job(admission,Role.DEVELOPER,generation)
        original=self.runtime.dispatch
        sentinel='ghp_'+'A'*36  # Synthetic marker, no credentials or permissions.
        def dispatch(request):
            observed=original(request)
            observed=replace(observed,result=replace(observed.result,summary='Accidental synthetic credential '+sentinel))
            self.runtime.observations[request.id]=observed
            return observed
        self.runtime.dispatch=dispatch
        refused=False
        try:self.conductor._worker(admission,assignment,job,generation)
        except ADPError:refused=True
        for revision in run(self.remote,'rev-list','refs/heads/coordination/current').splitlines():
            self.assertNotIn(sentinel,run(self.remote,'show',revision+':state.json'),
                             'credential-shaped worker output reached a portable checkpoint')
        self.assertTrue(refused,'credential-shaped output must be explicitly refused')
        self.assertEqual(self.guard.inspect(admission.task_id,self.conductor._requirement(admission)).kind,
                         DecisionKind.STOP_UNSAFE)
        self.assertEqual(len(self.forge._read()['items']),0)


    def test_legacy_cached_secret_refuses_without_creating_more_copies(self):
        from adp.execution_types import WorkerResult
        from adp.execution_containment import source_seal
        from adp.guard_types import Outcome,data
        from adp.schema import key
        admission=self.admissions[0];generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        aid,job=self.conductor._job(admission,Role.DEVELOPER,generation)
        sentinel='github_pat_'+'B'*60
        legacy=data(WorkerResult(Outcome.PASS,False,(),'Legacy synthetic credential '+sentinel))
        # Simulate a pre-fix checkpoint, never erase its history or call it safe.
        self.conductor.journal.change(lambda execution,state,tasks:
            execution['tasks'][key(admission.task_id)]['jobs'][aid].update(result=legacy,
                result_digest=source_seal(self.projects['one'].root),status='OBSERVED'))
        job=self.conductor._task(admission)['jobs'][aid]
        head=self.memory.inspect()['remote_head']
        with self.assertRaises(ADPError):self.conductor._worker(admission,aid,job,generation)
        with self.assertRaises(ADPError):self.conductor.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        with self.assertRaises(ADPError):self.conductor.handoff(authorized=True)
        self.assertEqual(self.memory.inspect()['remote_head'],head)
        self.assertEqual(self.runtime.dispatch_count,0)

    def test_forensic_secret_block_survives_handoff_without_another_context(self):
        from adp.guard_types import Action,ActionKind,Observation,Outcome
        admission=self.admissions[0];generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        rid=self.conductor._requirement(admission)
        for _ in range(3):
            permit=self.guard.begin(admission.task_id,rid,Action('fixture:author',ActionKind.CHECK,'bounded check','one observation'))
            self.guard.observe(admission.task_id,rid,permit,Observation(Outcome.FAIL,('fixture:failure',),('criterion:answer',)))
        original=self.runtime.dispatch
        sentinel='sk-proj-'+'C'*32
        def dispatch(request):
            observed=original(request)
            observed=replace(observed,result=replace(observed.result,forensic=replace(observed.result.forensic,diagnosis=sentinel)))
            self.runtime.observations[request.id]=observed
            return observed
        self.runtime.dispatch=dispatch
        first=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(first['status'],'STOPPED')
        self.assertEqual(self.conductor._task(admission)['stage'],'BLOCKED')
        self.assertNotIn(sentinel,(self.memory.path/'state.json').read_text())
        self.assertEqual(self.runtime.dispatch_count,1)
        self.conductor.handoff(authorized=True);self.memory.claim('qualification:replacement')
        second=self.conductor.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(second['status'],'STOPPED')
        self.assertEqual(self.runtime.dispatch_count,1)
        self.assertEqual(self.conductor._task(admission)['stage'],'BLOCKED')


class CredentialShapeTests(unittest.TestCase):
    def test_credentials_are_detected_in_nested_forensic_fields(self):
        from adp.execution_privacy import credential_shaped
        markers=('ghp_'+'B'*36,'github_pat_'+'C'*60,'sk-proj-'+'D'*32,
                 'AKIA'+'E'*16,'-----BEGIN RSA PRIVATE KEY-----',
                 'https://account:synthetic-password@example.invalid','API_KEY=synthetic-secret-value')
        for marker in markers:
            with self.subTest(shape=marker.split('_')[0]):
                self.assertTrue(credential_shaped({'forensic':{'plan':{'action':marker},'evidence':[marker]}}))

    def test_public_hashes_and_finite_plan_text_are_not_secrets(self):
        from adp.execution_privacy import credential_shaped
        self.assertFalse(credential_shaped({'summary':'Bounded independent correction verified',
            'request_id':'a'*64,'forensic':{'plan':{'action':'Check one admitted assertion','seconds':30}}}))
