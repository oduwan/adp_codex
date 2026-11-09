"""Real M1–M4 and disposable Git integration; fixture runtime is explicit."""
from __future__ import annotations
from dataclasses import replace
import threading

from adp.errors import AuthorityError
from adp.execution_memory import ExecutionJournal
from adp.guard_types import data
from adp.execution_types import Role, RuntimeObservation, RuntimeStatus
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.policy_types import Operation
from test_config import run
from execution_fixtures import ExecutionFixture


class ConductorTests(ExecutionFixture):
    def test_two_independent_tasks_run_and_report_once(self):
        # Contrast external policies: a ready PR and a gated push need actual
        # fresh review/check qualifications, never a provider-side waiver.
        self.rules['two'] = replace(self.rules['two'], pr_draft=False, gate_operations=(Operation.PUSH,),
                                    subject_template='deliver: {summary}')
        underlying = self.runtime
        barrier = threading.Barrier(2, timeout=60)
        class ConcurrentRuntime:
            def __init__(self): self.pending={}
            def __getattr__(self,name): return getattr(underlying,name)
            def observe(self,rid):
                if rid in self.pending:
                    return RuntimeObservation(rid,underlying.host,RuntimeStatus.RUNNING,None,None,'fixture:pending',0,digest(self.pending[rid]))
                return underlying.observe(rid)
            def dispatch(self,request):
                self.pending[request.id]=request
                return self.observe(request.id)
            def wait(self,rid):
                request=self.pending[rid]
                if request.role==Role.DEVELOPER: barrier.wait()
                answer=underlying.dispatch(request)
                del self.pending[rid]
                return answer
        self.conductor.runtime=ConcurrentRuntime()
        report = self.conductor.run(self.admissions, maximum_parallel=2, authorized=True)
        self.assertEqual(report["status"], "COMPLETE", report)
        self.assertFalse(report["background_work"])
        self.assertEqual(self.runtime.dispatch_count, 4)
        execution = self.memory.inspect()["state"]["execution"]
        self.assertEqual(len(execution["publications"]), 2)
        self.assertEqual(len(self.forge._read()["items"]), 4)
        before=self.memory.inspect()['local_head']
        self.conductor.status()
        self.assertEqual(self.memory.inspect()['local_head'],before)
        # Current completion requires observation, even after accepted history.
        ledger=self.forge._read()
        pr=next(v for v in ledger['items'].values() if v['operation']==Operation.PR)
        saved=pr['revision'];pr['revision']='f'*40
        from adp.storage import atomic
        from adp.schema import encode
        atomic(self.forge.directory/'forge.json',encode(ledger,1048576))
        with self.assertRaises(ADPError): self.conductor.resume(self.admissions,maximum_parallel=2,authorized=True)
        pr['revision']=saved
        atomic(self.forge.directory/'forge.json',encode(ledger,1048576))
        # A clean cross-clone handoff preserves all accepted evidence/progress.
        from adp.config import Config
        from adp.memory import Memory
        from adp.guard import ProgressGuard
        from adp.conductor import Conductor
        self.conductor.handoff(authorized=True)
        clone=self.base/'new-control'
        run(self.base,'clone','--origin','team',str(self.remote),str(clone))
        run(clone,'config','user.name','Fixture');run(clone,'config','user.email','fixture@example.org')
        config=Config.discover(clone,remote='team',branch='coordination/current',storage=self.base/'new-memory')
        memory=Memory(config);memory.initialize(authorized=True);memory.claim('new-conductor')
        guard=ProgressGuard(memory,authority=self.authority,clock=lambda:self.now)
        projects={}
        from adp.execution_ports import GitExecutionPort
        for name,old in self.projects.items():
            root=self.base/('new-'+name)
            run(self.base,'clone','--origin','team','--branch','work/'+name,str(self.remote),str(root))
            cfg=Config.discover(root,remote='team',repository_id=config.identity)
            factory=lambda admission,safety,fn=old.policy_factory,cfg=cfg:fn(admission,safety,cfg=cfg)
            projects[name]=replace(old,root=root,policy_factory=factory,git_port=GitExecutionPort(cfg,local_remotes=(self.remote,)))
        resumed=Conductor(memory,guard,self.readiness,underlying,self.authority,projects,clock=lambda:self.now)
        self.assertEqual(resumed.resume(self.admissions,maximum_parallel=2,authorized=True)['status'],'COMPLETE')
        self.assertEqual(underlying.dispatch_count,4)
        contexts = [j["context"] for t in execution["tasks"].values() for j in t["jobs"].values() if j["context"]]
        self.assertEqual(len(contexts), len(set(contexts)))
        with self.assertRaises(ADPError):
            self.conductor.resume(self.admissions, maximum_parallel=2, authorized=True)
        again = resumed.resume(self.admissions, maximum_parallel=2, authorized=True)
        self.assertEqual(again["status"], "COMPLETE")
        self.assertEqual(self.runtime.dispatch_count, 4)
        self.assertEqual(len(self.forge._read()["items"]), 4)

    def test_no_execution_or_upgrade_without_explicit_authority(self):
        with self.assertRaises(AuthorityError):
            self.conductor.run(self.admissions, maximum_parallel=1)
        with self.assertRaises(AuthorityError):
            ExecutionJournal(self.memory).upgrade()
        self.assertEqual(self.runtime.dispatch_count, 0)
