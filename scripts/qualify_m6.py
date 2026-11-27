"""Run the complete fixed M1–M6 inventory; write private evidence, never release."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
import unittest

from qualification_support import HonestResult,accounting,private_directory,private_file,sha256,test_ids,verify_test_sources,write_evidence

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))  # Test the pinned source; wheel isolation is a separate procedure.


def preflight():
    """Validate pinned sources/inventory without executing any test or effect."""
    source=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain']):raise ValueError('Qualify a clean committed source')
    baseline=json.loads((ROOT/'docs/qualification/M1_M5_TEST_INVENTORY.json').read_text())
    plan=json.loads((ROOT/'docs/qualification/M6_PLAN.json').read_text())
    verify_test_sources(ROOT,plan['accepted_base'])
    suite=unittest.TestLoader().discover(str(ROOT/'tests'))
    inventory=sorted(test_ids(suite))
    if len(baseline)!=193 or not set(baseline)<=set(inventory):raise ValueError('Accepted 193-test denominator changed')
    procedures=json.loads((ROOT/'docs/qualification/M6_PROCEDURES.json').read_text())
    expected={s for row in plan['requirements'] for s in row['scenarios']}
    if (len(inventory)!=procedures['current_test_denominator'] or {r['id'] for r in procedures['scenarios']}!=expected
            or procedures['plan_sha256']!=sha256(ROOT/'docs/qualification/M6_PLAN.json')
            or any(not set(row['tests'])<=set(inventory) for row in procedures['scenarios'])):
        raise ValueError('Frozen scenario/procedure inventory changed')
    return source,plan,inventory,suite


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args=parser.parse_args()
    source,plan,inventory,suite=preflight()
    directory=private_directory(args.evidence_dir,ROOT)
    write_evidence(directory/'inventory.json',{'source':source,'inventory':inventory,'accepted_denominator':193})
    with private_file(directory/'unittest.log','w') as output:
        result=unittest.TextTestRunner(stream=output,verbosity=2,failfast=False,resultclass=HonestResult).run(suite)
    summary=accounting(inventory,result.observations)
    summary.update(schema_version=1,source=source,python=platform.python_version(),platform=platform.system(),
        plan_sha256=sha256(ROOT/'docs/qualification/M6_PLAN.json'),log_sha256=sha256(directory/'unittest.log'),
        engine_tree=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD:adp'],text=True).strip(),
        tests_tree=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD:tests'],text=True).strip(),
        public_release='NOT_AUTHORIZED')
    digest=write_evidence(directory/'suite.json',summary)
    print(json.dumps({k:summary[k] for k in ('source','python','status','original_denominator','counts','public_release')},sort_keys=True))
    print('evidence_sha256='+digest)
    for case,status in summary['tests'].items():print(json.dumps({'test':case,'status':status},sort_keys=True))
    return 0 if summary['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
