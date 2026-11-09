"""Q08 exercises accepted real Git-backed campaign and validation boundaries."""
from adp.guard import ProgressGuard
from adp.guard_types import Campaign,DecisionKind,Outcome
from execution_fixtures import ExecutionFixture


class DiagnosticQualificationTests(ExecutionFixture):
    def test_real_memory_campaign_preserves_inventory_across_restart_and_failure(self):
        admission=self.admissions[0];generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        rid=self.conductor._requirement(admission)
        outcomes=(Outcome.FAIL,Outcome.ERROR,Outcome.TIMEOUT,Outcome.PASS,Outcome.SKIP,Outcome.NOTRUN,Outcome.PASS)
        inventory=tuple('method:'+str(i) for i in range(7))
        spec=Campaign(inventory,'fixture:original-census',(inventory[-1],))
        subject=self.guard.campaign_subject(admission.task_id,rid,spec)
        token=self.guard.start_campaign(admission.task_id,rid,spec,self.authority.grant(purpose='campaign',subject=subject))
        guard=self.guard
        for index,(case,outcome) in enumerate(zip(inventory,outcomes)):
            if index==3:guard=ProgressGuard(self.conductor.memory,authority=self.authority,clock=lambda:100)
            permit=guard.next_case(admission.task_id,rid,token)
            self.assertEqual(permit.case_id,case)
            guard.record_case(admission.task_id,rid,token,permit,outcome)
        result=guard.campaign_summary(admission.task_id,rid)
        self.assertEqual(result['original_denominator'],7)
        self.assertEqual(result['observed'],7)
        self.assertEqual(result['counts']['PASS'],1)
        self.assertEqual(result['raw_counts']['PASS'],2)
        self.assertEqual(result['counts']['QUARANTINED'],1)
        self.assertEqual(sum(result['counts'].values()),7)
        self.assertFalse(result['formal_acceptance']);self.assertFalse(result['all_observed_pass'])
        self.assertEqual(guard.inspect(admission.task_id,rid).kind,DecisionKind.FORENSIC_REQUIRED)
