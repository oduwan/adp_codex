"""Class/module setup failures cannot erase frozen M7 method denominators."""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from qualify_m7 import M7Result, summarize


class FixtureAccountingTests(unittest.TestCase):
    def run_fixture(self, cls):
        cases = unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        inventory = [test.id() for test in cases]
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=M7Result).run(cases)
        return summarize(inventory, result)

    def test_class_setup_error_keeps_all_original_methods_notrun(self):
        class Two(unittest.TestCase):
            @classmethod
            def setUpClass(cls):raise RuntimeError('synthetic fixture setup error')
            def test_one(self):raise AssertionError('must not run')
            def test_two(self):raise AssertionError('must not run')
        observed = self.run_fixture(Two)
        self.assertEqual(observed['original_denominator'], 2)
        self.assertEqual(observed['counts']['NOTRUN'], 2)
        self.assertEqual(observed['counts']['PASS'], 0)
        self.assertEqual(observed['fixture_counts']['ERROR'], 1)
        self.assertEqual(observed['status'], 'FAIL')
        class Spoof(unittest.TestCase):
            def id(self):return 'setUpClass (spoof)'
            def runTest(self):raise RuntimeError('ordinary method must not become fixture metadata')
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=M7Result).run(unittest.TestSuite((Spoof(),)))
        with self.assertRaisesRegex(ValueError, 'Original test inventory changed'):
            summarize(('ordinary:expected',), result)

    def test_class_setup_skip_is_not_a_qualification_pass(self):
        class Two(unittest.TestCase):
            @classmethod
            def setUpClass(cls):raise unittest.SkipTest('UNSUPPORTED fixture runtime')
            def test_one(self):raise AssertionError('must not run')
            def test_two(self):raise AssertionError('must not run')
        observed = self.run_fixture(Two)
        self.assertEqual(observed['counts']['NOTRUN'], 2)
        self.assertEqual(observed['fixture_counts']['SKIP'], 1)
        self.assertEqual(observed['status'], 'FAIL')

    def test_teardown_error_preserves_observed_pass_but_fails_qualification(self):
        class Two(unittest.TestCase):
            @classmethod
            def tearDownClass(cls):raise RuntimeError('synthetic fixture teardown error')
            def test_one(self):pass
            def test_two(self):pass
        observed = self.run_fixture(Two)
        self.assertEqual(observed['counts']['PASS'], 2)
        self.assertEqual(observed['fixture_counts']['ERROR'], 1)
        self.assertEqual(observed['status'], 'FAIL')
