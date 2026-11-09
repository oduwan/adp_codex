"""A valid M3 plan cannot authorize an edited target, payload or CAS value."""
import copy
from adp.guard_types import data
from adp.execution_types import Role
from adp.errors import ADPError
from adp.policy_types import Operation, Request
from execution_fixtures import ExecutionFixture
from test_config import run


class PortTests(ExecutionFixture):
    def test_mutated_plan_fields_cannot_change_any_ref(self):
        admission=self.admissions[0]
        generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        _,job=self.conductor._job(admission,Role.DEVELOPER,generation)
        from adp.discovery_schema import typed
        from adp.guard_types import Permit
        provider,plan,auth=self.conductor._authorize_policy(admission,typed(Permit,job['permit']),Request(Operation.PUSH))
        action={'operation':Operation.PUSH,'revision':plan.task.revision,'source_ref':plan.task.source_ref,
                'target':plan.target_ref,'expected_target':plan.expected_target,'payload':data(plan.payload)}
        before=run(self.remote,'show-ref')
        mutations=[{'target':'refs/heads/unauthorized'}, {'expected_target':'d'*40},
                   {'source_ref':'refs/heads/trunk'}, {'payload':{**action['payload'],'remote':'other'}}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ADPError):
                    self.projects['one'].git_port.submit({**action,**mutation},provider,plan,auth)
                self.assertEqual(run(self.remote,'show-ref'),before)
