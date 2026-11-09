"""M6 cross-project execution qualification, explicitly synthetic workers."""
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from adp.policy_types import Operation
from adp.policy_types import Effect,Request
from adp.policy_adapters import M2SafetyAdapter
from adp.execution_policy import policy_task
from adp.guard_types import data
from adp.errors import ADPError
from m6_fixtures import DisposableLane
from test_config import run


class CrossRepositoryQualification(unittest.TestCase):
    def test_two_unrelated_concurrent_lanes_respect_different_review_policies(self):
        with tempfile.TemporaryDirectory(prefix='adp-m6-cross-project-') as directory:
            barrier=threading.Barrier(2,timeout=60)
            lanes=[DisposableLane(Path(directory),name,barrier) for name in ('atlas','boreal')]
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending=[pool.submit(lane.conductor.run,(lane.admission,),maximum_parallel=1,authorized=True) for lane in lanes]
                results=[f.result() for f in pending]
            self.assertEqual(results[0]['status'],'COMPLETE',results)
            self.assertEqual(results[1]['status'],'STOPPED',results)
            self.assertIn('independent exact-sha approvals required: 2',results[1]['tasks'][lanes[1].admission.task_id]['reason'].lower())
            self.assertNotEqual(lanes[0].config.identity,lanes[1].config.identity)
            self.assertNotEqual(lanes[0].initial,lanes[1].initial)
            assignments,contexts=set(),[]
            for lane in lanes:
                observed=lane.memory.inspect()
                for task in observed['tasks'].values():
                    for aid in task['assignments']:
                        identity=(lane.config.identity,aid)
                        self.assertNotIn(identity,assignments);assignments.add(identity)
                contexts.extend(o.context_id for o in lane.runtime.observations.values())
                self.assertEqual(lane.runtime.dispatch_count,2)
                commit=next(p for p in lane.plans if p.request.operation==Operation.COMMIT)
                self.assertEqual(commit.payload.subject,'Meet the bounded contract' if lane.name=='boreal' else 'Work opaque/task/atlas: Meet the bounded contract')
                self.assertEqual(commit.required_reviews,2 if lane.name=='boreal' else 1)
                self.assertEqual(run(lane.root,'symbolic-ref','HEAD'),'refs/heads/'+lane.branch)
            self.assertEqual(len(contexts),len(set(contexts)))
            self.assertEqual(len(lanes[0].forge._read()['items']),2)
            self.assertEqual(len(lanes[1].forge._read()['items']),0)
            self.assertEqual(run(lanes[1].remote,'rev-parse','refs/heads/'+lanes[1].branch),lanes[1].initial)
            self.assertEqual(run(lanes[0].remote,'rev-parse','refs/heads/'+lanes[0].branch),run(lanes[0].root,'rev-parse','HEAD'))
            self.assertNotEqual(lanes[0].rules.merge_method,lanes[1].rules.merge_method)
            self.assertNotEqual(lanes[0].rules.permissions,lanes[1].rules.permissions)
            # A verified project merge policy is only a decision. The supplied
            # executor still refuses merge and never changes either base ref.
            atlas=lanes[0];rid=atlas.conductor._requirement(atlas.admission)
            provider=atlas.policy(atlas.admission,M2SafetyAdapter(atlas.guard))
            task=policy_task(atlas.conductor.memory,atlas.admission,rid,'refs/heads/'+atlas.branch)
            plan=provider.plan(task,Request(Operation.MERGE))
            review=atlas.conductor._task(atlas.admission)['review']
            qualifications=atlas.conductor._qualifications(provider,plan,review)
            authorization=atlas.project.policy_authorizer.authorize(plan,qualifications)
            self.assertEqual(provider.decide(plan,authorization).effect,Effect.ALLOW)
            before=run(atlas.remote,'show-ref')
            action={'operation':Operation.MERGE,'revision':plan.task.revision,'source_ref':plan.task.source_ref,
                    'target':plan.target_ref,'expected_target':plan.expected_target,'payload':data(plan.payload)}
            with self.assertRaises(ADPError):atlas.project.git_port.submit(action,provider,plan,authorization)
            self.assertEqual(run(atlas.remote,'show-ref'),before)
