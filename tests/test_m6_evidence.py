"""Qualification must preserve denominators and fail closed on unsafe evidence."""
import io
import os
import stat
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts.qualification_support import HonestResult,STATUSES,accounting,extract_archive,private_directory,write_evidence

ROOT=Path(__file__).resolve().parents[1]


class EvidenceQualificationTests(unittest.TestCase):
    def test_all_nonpass_outcomes_and_missing_results_keep_original_denominator(self):
        inventory=tuple('case:'+str(i) for i in range(len(STATUSES)+1))
        result=accounting(inventory,dict(zip(inventory,STATUSES)))
        self.assertEqual(result['original_denominator'],9)
        self.assertEqual(result['counts']['PASS'],1)
        self.assertEqual(result['counts']['NOTRUN'],2)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(sum(result['counts'].values()),9)

    def test_duplicate_invented_or_unrecognized_outcomes_are_refused(self):
        for inventory,observations in ((('one','one'),{}),(('one',),{'other':'PASS'}),(('one',),{'one':'QUARANTINED_PASS'})):
            with self.subTest(inventory=inventory),self.assertRaises(ValueError):accounting(inventory,observations)

    def test_subtest_errors_and_skips_cannot_be_overwritten_by_parent_success(self):
        class Mixed(unittest.TestCase):
            def runTest(self):
                with self.subTest(case='failure'):self.fail('synthetic failure')
                with self.subTest(case='error'):raise RuntimeError('synthetic error')
                with self.subTest(case='skip'):self.skipTest('synthetic skip')
        case=Mixed()
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=HonestResult).run(unittest.TestSuite((case,)))
        report=accounting((case.id(),),result.observations)
        self.assertEqual(report['counts']['ERROR'],1)
        self.assertEqual(report['counts']['PASS'],0)

    def test_expected_failure_is_not_a_qualification_pass(self):
        class Expected(unittest.TestCase):
            @unittest.expectedFailure
            def runTest(self):self.fail('preserved expected failure')
        case=Expected()
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=HonestResult).run(unittest.TestSuite((case,)))
        self.assertEqual(accounting((case.id(),),result.observations)['status'],'FAIL')

    def test_private_evidence_refuses_source_tree_symlinks_and_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='adp-m6-evidence-') as directory:
            base=Path(directory);(base/'link').symlink_to(ROOT,target_is_directory=True)
            for target in (ROOT/'qualification-private',base/'link'/'evidence'):
                with self.assertRaises(ValueError):private_directory(target,ROOT)
            target=private_directory(base/'safe',ROOT)/'evidence.json'
            first=write_evidence(target,{'status':'FAIL'})
            self.assertEqual(len(first),64)
            with self.assertRaises(FileExistsError):write_evidence(target,{'status':'PASS'})
            self.assertEqual(json.loads(target.read_text())['status'],'FAIL')

    def test_source_archive_refuses_traversal_links_and_duplicates(self):
        for name,kind in (('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('duplicate',tarfile.REGTYPE)):
            with self.subTest(name=name),tempfile.TemporaryDirectory(prefix='adp-m6-archive-') as directory:
                buffer=io.BytesIO()
                with tarfile.open(fileobj=buffer,mode='w') as archive:
                    item=tarfile.TarInfo(name);item.type=kind;item.linkname='/outside'
                    archive.addfile(item)
                    if name=='duplicate':archive.addfile(item)
                with self.assertRaises(ValueError):extract_archive(buffer.getvalue(),Path(directory)/'source')

    def test_existing_public_evidence_directory_is_refused_and_files_are_private(self):
        with tempfile.TemporaryDirectory(prefix='adp-m6-permissions-') as directory:
            base=Path(directory);public=base/'public';public.mkdir(mode=0o755)
            with self.assertRaises(ValueError):private_directory(public,ROOT)
            private=private_directory(base/'private',ROOT)
            write_evidence(private/'record.json',{'status':'FAIL'})
            self.assertEqual(stat.S_IMODE((private/'record.json').stat().st_mode),0o600)

    def test_frozen_matrix_and_accepted_denominators_are_complete(self):
        plan=json.loads((ROOT/'docs/qualification/M6_PLAN.json').read_text())
        accepted=json.loads((ROOT/'docs/qualification/M1_M5_TEST_INVENTORY.json').read_text())
        self.assertEqual(len(accepted),193);self.assertEqual(len(set(accepted)),193)
        self.assertEqual([r['id'] for r in plan['requirements']],[f'Q{i:02}' for i in range(1,13)])
        scenarios=[s for row in plan['requirements'] for s in row['scenarios']]
        self.assertEqual(len(scenarios),42);self.assertEqual(len(set(scenarios)),42)
        self.assertEqual(plan['public_release'],'NOT_AUTHORIZED')
