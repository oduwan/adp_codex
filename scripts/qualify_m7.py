"""Preserve accepted M1–M6 blobs and run one frozen M7 inventory honestly."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys
import unittest

from qualification_support import HonestResult, accounting, private_directory, private_file, sha256, test_ids, write_evidence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "16c7a4e103c6a824f361f96e2eb237fbbf4faf48"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    require_clean = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"])
    if require_clean:
        raise ValueError("Qualify clean committed source")
    source = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    accepted = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "-rz", BASE, "tests"])
    for entry in filter(None, accepted.split(b"\0")):
        metadata, path = entry.split(b"\t", 1)
        blob = metadata.split()[2].decode()
        current = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD:" + path.decode()], text=True).strip()
        if current != blob:
            raise ValueError("Accepted M1–M6 test/fixture changed")
    inventory = json.loads(args.inventory.read_text())
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests_m7"))
    actual = sorted(test_ids(suite))
    if len(inventory) != len(set(inventory)) or sorted(inventory) != actual:
        raise ValueError("Frozen M7 test denominator changed")
    directory = private_directory(args.evidence_dir, ROOT)
    with private_file(directory / "unittest.log", "w") as output:
        result = unittest.TextTestRunner(stream=output, verbosity=2, failfast=False, resultclass=HonestResult).run(suite)
    summary = accounting(actual, result.observations)
    summary.update(source=source, python=platform.python_version(), accepted_denominator=210,
        inventory_sha256=sha256(args.inventory), log_sha256=sha256(directory / "unittest.log"),
        public_release="NOT_AUTHORIZED")
    digest = write_evidence(directory / "suite.json", summary)
    print(json.dumps({k: summary[k] for k in ("source", "python", "status", "original_denominator", "counts", "accepted_denominator")}, sort_keys=True))
    print("evidence_sha256=" + digest)
    for case, status in summary["tests"].items():
        print(json.dumps({"test": case, "status": status}, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
