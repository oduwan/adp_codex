"""Fresh-read parity, explicit preflight gates and paired disposable costs."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.errors import ADPError
from adp.git import git, value
from adp.personal_publication import PersonalPublication
from adp.personal_recovery import administration_snapshot, _head_ref
from adp.runtime_limits import DEFAULTS
from test_config import run, snapshot
from test_runtime_limits import service


def baseline(personal):
    # Exact e269 administration algorithm; no old runtime campaign is replayed.
    def one(root):
        return {"config":hashlib.sha256(git(root,"config","--null","--list")).hexdigest(),
                "index":hashlib.sha256(git(root,"ls-files","--stage","-z")).hexdigest(),
                "head":value(root,"rev-parse","HEAD"),"ref":value(root,"symbolic-ref","HEAD")}
    refs = dict(line.split(" ",1) for line in value(personal.feature,"for-each-ref","--format=%(refname) %(objectname)").splitlines())
    return {"feature":one(personal.feature),"outside":one(Path(personal.plan["checkout"]["path"])),"refs":refs}


class RuntimeWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def project(self):
        roots=[]
        for name in ("feature","outside"):
            root=self.root/name; root.mkdir(); roots.append(root)
            run(root,"init","--initial-branch=trunk")
            run(root,"config","user.name","Fixture"); run(root,"config","user.email","fixture@example.org")
            (root/"product").write_text("fixture\n"); run(root,"add","product"); run(root,"commit","-m","fixture")
        return SimpleNamespace(feature=roots[0],plan={"checkout":{"path":str(roots[1])}})

    def test_actual_administration_parity_nine_to_seven_processes_and_read_only_preservation(self):
        personal=self.project(); before=snapshot(self.root)
        from adp import personal_recovery
        calls=[]
        def actual(*a,**k): calls.append(a); return git(*a,**k)
        # value() is the original git wrapper; count both actual native paths.
        with patch("adp.personal_recovery.git",side_effect=actual), patch("adp.git.git",side_effect=actual):
            optimized=administration_snapshot(personal)
        self.assertEqual(len(calls),7)
        self.assertEqual(optimized,baseline(personal))
        self.assertEqual(snapshot(self.root),before)

    def test_combined_head_ref_refuses_malformed_detached_and_changed_input(self):
        personal=self.project(); root=personal.feature
        for raw in (b"missing\nrefs/heads/trunk\n", b"a"*40+b"\nHEAD\n", b"a"*40+b"\nrefs/heads/trunk\nextra\n",b"\xff\nrefs/heads/trunk\n"):
            with self.subTest(raw=raw), patch("adp.personal_recovery.git",return_value=raw):
                with self.assertRaises((ADPError,UnicodeError)): _head_ref(root)
        first=administration_snapshot(personal)
        run(root,"checkout","-b","new-admitted-fixture")
        second=administration_snapshot(personal)
        self.assertNotEqual(first,second); self.assertEqual(second,baseline(personal))
        run(root,"checkout","--detach")
        with self.assertRaises(ADPError): administration_snapshot(personal)

    def test_full_and_later_administration_snapshots_remain_independently_fresh(self):
        personal=self.project()
        from adp import personal_recovery
        original=personal_recovery._head_ref
        with patch("adp.personal_recovery._head_ref",wraps=original) as reads:
            one=administration_snapshot(personal)
            run(personal.feature,"config","fixture.changed","yes")
            two=administration_snapshot(personal)
            self.assertEqual(reads.call_count,4)
            self.assertNotEqual(one,two); self.assertEqual(two,baseline(personal))

    def test_paired_actual_costs_under_identical_defaults(self):
        personal=self.project(); rows={"baseline":[],"optimized":[]}; client=service()
        before=snapshot(self.root)
        for index in range(20):
            order=("baseline","optimized") if index%2==0 else ("optimized","baseline")
            results=[]
            for name in order:
                function=baseline if name=="baseline" else administration_snapshot
                with client.bounded(name="paired.administration"):
                    started=time.perf_counter(); results.append(function(personal)); rows[name].append(time.perf_counter()-started)
            self.assertEqual(results[0],results[1])
        self.assertEqual(snapshot(self.root),before)
        def stats(values):
            return {"n":len(values),"median_seconds":statistics.median(values),
                    "empirical_p95_seconds":sorted(values)[math.ceil(.95*len(values))-1],"maximum_seconds":max(values)}
        print("PAIRED_DISPOSABLE_COSTS "+json.dumps({"limits":DEFAULTS.values(),"scope":"same two disposable roots; alternating order; actual native Git; no HTTP/Workers",
            "baseline":stats(rows["baseline"]),"optimized":stats(rows["optimized"]),"samples_seconds":rows},sort_keys=True),flush=True)

    def publication(self):
        pub=PersonalPublication.__new__(PersonalPublication)
        pub.c=SimpleNamespace(memory=SimpleNamespace(control=self.root))
        pub.service=service(); pub.record=Mock(return_value=None)
        pub.save=Mock(); pub.initialize=Mock(); pub.local=Mock(); pub.remote=Mock()
        return pub

    def test_exact_fresh_proposal_is_computed_once_inside_lock_before_saving(self):
        pub=self.publication(); sentinel=RuntimeError("stop after observed intent")
        view={"runtime_limits":DEFAULTS.values(),"fixture":"original-scope-and-source"}
        def proposed(reviewed):
            with (self.root/"conductor-invocation.lock").open("rb") as handle:
                with self.assertRaises(BlockingIOError): fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(reviewed,"exact"); return view,"exact","actual-binding"
        pub.proposed=Mock(side_effect=proposed); pub.save.side_effect=sentinel
        with self.assertRaises(RuntimeError) as raised:
            pub.publish(reviewed="exact",authorized=True,assume_quiescence=True,confirm_project_rules=True)
        self.assertIs(raised.exception,sentinel); pub.proposed.assert_called_once_with("exact")
        self.assertIs(pub.save.call_args.args[0]["view"],view)
        self.assertEqual(pub.save.call_args.args[0]["credential_binding"],"actual-binding")
        pub.initialize.assert_not_called()

    def test_changed_token_source_or_credential_proposal_cannot_save_an_intent(self):
        for changed in ("source","credential","checkpoint","original","review"):
            pub=self.publication(); pub.proposed=Mock(return_value=({"changed":changed},"changed-exact-token","binding"))
            with self.subTest(changed=changed),self.assertRaises(ADPError):
                pub.publish(reviewed="exact",authorized=True,assume_quiescence=True,confirm_project_rules=True)
            pub.proposed.assert_called_once(); pub.save.assert_not_called(); pub.initialize.assert_not_called()

    def test_locked_existing_intent_refuses_a_different_approval_without_replay(self):
        pub=self.publication(); pub.record.return_value={"approval":"original-one-use"}; pub.proposed=Mock()
        with self.assertRaisesRegex(ADPError,"original publication intent"):
            pub.publish(reviewed="foreign",authorized=True,assume_quiescence=True,confirm_project_rules=True)
        pub.record.assert_called_once(); pub.proposed.assert_not_called(); pub.save.assert_not_called()
        pub.initialize.assert_not_called(); pub.local.assert_not_called(); pub.remote.assert_not_called()

    def test_missing_canonical_history_and_required_flags_refuse_without_proposal(self):
        pub=self.publication(); pub.record.side_effect=ADPError("canonical missing history"); pub.proposed=Mock()
        with self.assertRaisesRegex(ADPError,"canonical missing history"):
            pub.publish(reviewed="exact",authorized=True,assume_quiescence=True,confirm_project_rules=True)
        pub.proposed.assert_not_called(); pub.save.assert_not_called()
        for flag in ("authorized","assume_quiescence","confirm_project_rules"):
            pub=self.publication(); pub.proposed=Mock()
            arguments=dict(reviewed="exact",authorized=True,assume_quiescence=True,confirm_project_rules=True); arguments[flag]=False
            with self.subTest(flag=flag),self.assertRaises(ADPError): pub.publish(**arguments)
            pub.record.assert_not_called(); pub.proposed.assert_not_called(); pub.save.assert_not_called()
