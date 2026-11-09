"""Keep original denominators and every non-PASS outcome visible."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from adp.errors import ADPError
from adp.execution_ports import SubprocessValidation
from adp.execution_types import CheckCommand
from adp.guard_types import Outcome
from test_config import run


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='adp-validation-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        run(self.root,'init');run(self.root,'config','user.name','Fixture');run(self.root,'config','user.email','fixture@example.org')
        run(self.root,'commit','--allow-empty','-m','Synthetic baseline')
        self.sha=run(self.root,'rev-parse','HEAD')

    def validator(self, payload, **options):
        command=CheckCommand('unit',(sys.executable,'-c','print('+repr(json.dumps(payload))+')'),2,2)
        return SubprocessValidation((command,), **options)

    def receipt(self, outcome, **changes):
        return dict({'denominator':2,'counts':{v:2 if v==outcome else 0 for v in Outcome},'quarantined':0},**changes)

    def test_zero_exit_does_not_convert_nonpass_outcomes(self):
        for outcome in Outcome:
            with self.subTest(outcome=outcome):
                result=self.validator(self.receipt(outcome),trusted_disposable=True).run(self.root,self.sha,('unit',),seconds=3)[0]
                self.assertEqual(result.denominator,2)
                self.assertEqual(sum(c.count for c in result.counts),2)
                self.assertEqual(result.outcome,Outcome.PASS if outcome==Outcome.PASS else Outcome.FAIL)
                self.assertEqual(result.passed,2 if outcome==Outcome.PASS else 0)

    def test_original_denominator_and_quarantine_are_not_waived(self):
        for receipt in (self.receipt(Outcome.PASS,denominator=1),self.receipt(Outcome.PASS,quarantined=1),{'denominator':2,'counts':{'PASS':2},'quarantined':0}):
            with self.subTest(receipt=receipt):
                result=self.validator(receipt,trusted_disposable=True).run(self.root,self.sha,('unit',),seconds=3)[0]
                self.assertNotEqual(result.outcome,Outcome.PASS)
                self.assertEqual(result.denominator,2)

    def test_unqualified_host_execution_is_unsupported(self):
        with self.assertRaisesRegex(ADPError,'UNSUPPORTED_VALIDATION_RUNTIME'):
            self.validator(self.receipt(Outcome.PASS)).run(self.root,self.sha,('unit',),seconds=3)

    def test_campaign_does_not_fail_fast(self):
        commands=(CheckCommand('first',(sys.executable,'-c','raise SystemExit(1)'),2,1),
                  CheckCommand('second',(sys.executable,'-c','print('+repr(json.dumps({'denominator':1,'counts':{v:1 if v=='PASS' else 0 for v in Outcome},'quarantined':0}))+')'),2,1))
        result=SubprocessValidation(commands,trusted_disposable=True).run(self.root,self.sha,('first','second'),seconds=5)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0].outcome,Outcome.UNKNOWN)
        self.assertEqual(result[1].outcome,Outcome.PASS)

    def test_timeout_is_counted_and_next_case_remains_in_inventory(self):
        commands=(CheckCommand('slow',(sys.executable,'-c','import time;time.sleep(10)'),1,2),
                  CheckCommand('later',(sys.executable,'-c','print("not a receipt")'),1,3))
        result=SubprocessValidation(commands,trusted_disposable=True).run(self.root,self.sha,('slow','later'),seconds=2)
        self.assertEqual([v.denominator for v in result],[2,3])
        self.assertEqual(result[0].outcome,Outcome.TIMEOUT)
        self.assertNotEqual(result[1].outcome,Outcome.PASS)

    def test_expired_total_budget_does_not_launch_any_later_command(self):
        from unittest.mock import patch
        command=CheckCommand('unit',(sys.executable,'-c','raise AssertionError("must not run")'),2,2)
        validator=SubprocessValidation((command,),trusted_disposable=True)
        with patch('adp.execution_ports.time.monotonic',side_effect=[0,2]),patch('adp.execution_ports.subprocess.Popen') as process:
            result=validator.run(self.root,self.sha,('unit',),seconds=1)
        process.assert_not_called()
        self.assertEqual(result[0].outcome,Outcome.NOTRUN)
        self.assertEqual(result[0].denominator,2)
