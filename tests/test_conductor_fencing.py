"""Explicit generation, delivery, containment and interrupted-criterion checks."""
from dataclasses import replace

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_types import Role, RuntimeObservation, RuntimeStatus
from adp.guard_types import DecisionKind, Outcome, ProgressKind
from adp.schema import key
from execution_fixtures import ExecutionFixture


class FencingTests(ExecutionFixture):
    def prepare(self):
        admission=self.admissions[0]
        generation=self.memory.inspect()['state']['generation']
        self.conductor._admit(admission,self.readiness.observe(),generation)
        return admission,generation

    def test_duplicate_worker_delivery_is_immutable(self):
        admission,generation=self.prepare()
        aid,job=self.conductor._job(admission,Role.DEVELOPER,generation)
        result,job=self.conductor._worker(admission,aid,job,generation)
        self.conductor._deliver(admission,aid,job,result.outcome)
        head=self.memory.inspect()['local_head']
        self.conductor._deliver(admission,aid,job,result.outcome)
        self.assertEqual(self.memory.inspect()['local_head'],head)
        with self.assertRaises(ADPError): self.conductor._deliver(admission,aid,{**job,'receipt':'different:receipt'},result.outcome)
        self.assertEqual(self.runtime.dispatch_count,1)

    def test_stale_generation_cannot_dispatch_after_observed_handoff(self):
        admission,generation=self.prepare()
        aid,job=self.conductor._job(admission,Role.DEVELOPER,generation)
        self.conductor.handoff(authorized=True)
        self.memory.claim('replacement')
        with self.assertRaises(ADPError): self.conductor._worker(admission,aid,job,generation)
        self.assertEqual(self.runtime.dispatch_count,0)

    def test_unknown_runtime_does_not_claim_stopped_or_redispatch(self):
        def dispatch(request):
            self.runtime.dispatch_count+=1
            answer=RuntimeObservation(request.id,self.runtime.host,RuntimeStatus.UNKNOWN,None,None,'fixture:unknown-delivery',0,digest(request))
            self.runtime.observations[request.id]=answer
            return answer
        self.runtime.dispatch=dispatch
        result=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['background_work'],'UNKNOWN')
        self.assertEqual(len(result['unconfirmed_contexts']),1)
        self.conductor.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(self.runtime.dispatch_count,1)
        with self.assertRaises(ADPError): self.conductor.handoff(authorized=True)

    def test_ignored_nonadmitted_write_latches_guard_unsafe(self):
        project=self.projects['one']
        (project.root/'.git/info/exclude').write_text('ignored.tmp\n')
        original=self.runtime.dispatch
        def dispatch(request):
            result=original(request)
            (project.root/'ignored.tmp').write_text('unauthorized synthetic write')
            return result
        self.runtime.dispatch=dispatch
        result=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(result['status'],'STOPPED',result)
        admission=self.admissions[0]
        self.assertEqual(self.guard.inspect(admission.task_id,self.conductor._requirement(admission)).kind,DecisionKind.STOP_UNSAFE)
        self.assertEqual(len(self.forge._read()['items']),0)

    def test_crash_after_criterion_reservation_recovers_same_token(self):
        original=self.guard.observe
        lost=[]
        def observe(task,rid,permit,measured,**kwargs):
            if measured.progress and measured.progress.kind==ProgressKind.REQUIREMENT_VERIFIED and not lost:
                lost.append(permit.token)
                raise OSError('synthetic crash after durable criterion reservation')
            return original(task,rid,permit,measured,**kwargs)
        self.guard.observe=observe
        first=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(first['status'],'STOPPED',first)
        admission=self.admissions[0]
        _,_,item=self.guard._snapshot(admission.task_id,self.conductor._requirement(admission))
        self.assertEqual(item['active']['id'],lost[0])
        self.guard.observe=original
        second=self.conductor.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(second['status'],'COMPLETE',second)
        self.assertEqual(self.runtime.dispatch_count,2)

    def test_unreadable_memory_cannot_hide_a_launched_worker_from_stop(self):
        from unittest.mock import patch
        rid='c'*64
        self.conductor._launched.add(rid)
        self.runtime.observations[rid]=RuntimeObservation(rid,self.runtime.host,RuntimeStatus.RUNNING,None,None,'fixture:running',0)
        cancelled=[]
        def cancel(request_id):
            cancelled.append(request_id)
            return RuntimeObservation(request_id,self.runtime.host,RuntimeStatus.CANCELLED,None,None,'fixture:stopped',0)
        self.runtime.cancel=cancel
        with patch.object(self.conductor,'_task',side_effect=ADPError('synthetic memory unavailable')):
            self.assertEqual(self.conductor._quiesce(self.admissions),[])
        self.assertEqual(cancelled,[rid])

    def test_observed_publication_cannot_complete_after_local_sha_drift(self):
        from test_config import run
        original=self.conductor._measured
        injected=[]
        def measured(admission,job,*args,**kwargs):
            if job['role']==Role.COORDINATION and not injected:
                injected.append(True)
                # Every external result already exists; local source is now stale.
                run(self.projects['one'].root,'update-ref','refs/heads/work/one',self.initial)
                raise OSError('synthetic crash and local source drift after reporting')
            return original(admission,job,*args,**kwargs)
        self.conductor._measured=measured
        first=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(first['status'],'STOPPED',first)
        self.assertEqual(len(self.forge._read()['items']),2)
        self.conductor._measured=original
        again=self.conductor.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(again['status'],'STOPPED',again)
        self.assertNotEqual(self.conductor._task(self.admissions[0])['stage'],'COMPLETE')
        self.assertEqual(self.runtime.dispatch_count,2)

    def test_unconfirmed_validation_is_durable_execution_hazard(self):
        from adp.conductor import Conductor
        from adp.execution_ports import UnconfirmedValidation
        project=self.projects['one']
        class LostValidation:
            commands=project.validation.commands
            def run(self,*args,**kwargs):
                raise UnconfirmedValidation('validation:synthetic-lost-stop','fixture:private-artifact')
        self.projects['one']=replace(project,validation=LostValidation())
        first=self.conductor.run(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(first['status'],'UNKNOWN',first)
        self.assertEqual(first['background_work'],'UNKNOWN')
        self.assertTrue(any(r.startswith('validation:') for r in first['unconfirmed_contexts']))
        before=self.runtime.dispatch_count
        restarted=Conductor(self.memory,self.guard,self.readiness,self.runtime,self.authority,self.projects,clock=lambda:self.now)
        again=restarted.resume(self.admissions[:1],maximum_parallel=1,authorized=True)
        self.assertEqual(again['status'],'UNKNOWN',again)
        self.assertEqual(self.runtime.dispatch_count,before)
        with self.assertRaises(ADPError):restarted.handoff(authorized=True)
