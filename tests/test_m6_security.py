"""Q10: synthetic recognizable credentials must never reach portable memory."""
from dataclasses import replace
import json

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
