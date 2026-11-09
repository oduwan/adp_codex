"""Preserve accepted M1–M6 blobs and run one frozen M7 inventory honestly."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import subprocess
import sys
import unittest

from qualification_support import HonestResult, STATUSES, accounting, private_directory, private_file, sha256, test_ids, write_evidence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "16c7a4e103c6a824f361f96e2eb237fbbf4faf48"


def fixture_event(test, status, error_type):
    if not isinstance(test, unittest.suite._ErrorHolder):
        return None
    identifier = test.id()
    phase, separator, scope = identifier.partition(" (")
    if separator and scope.endswith(")") and phase in ("setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
        return {"phase": phase, "scope": scope[:-1][:512], "status": status, "error_type": error_type}
    return None


class M7Result(HonestResult):
    """Fixture lifecycle errors are evidence, never invented method IDs."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixture_events = []

    def addError(self, test, error):
        event = fixture_event(test, "ERROR", error[0].__name__)
        if event is None:
            return super().addError(test, error)
        unittest.TextTestResult.addError(self, test, error)
        self.fixture_events.append(event)

    def addSkip(self, test, reason):
        event = fixture_event(test, "SKIP", "SkipTest")
        if event is None:
            return super().addSkip(test, reason)
        unittest.TextTestResult.addSkip(self, test, reason)
        self.fixture_events.append(event)


def summarize(inventory, result):
    summary = accounting(inventory, result.observations)
    summary["fixtures"] = result.fixture_events
    summary["fixture_counts"] = {status: sum(row["status"] == status for row in result.fixture_events) for status in STATUSES}
    if result.fixture_events:
        summary["status"] = "FAIL"
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, nargs="+", required=True)
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
    inventories, inventory = {}, []
    for path in args.inventory:
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(ROOT / "docs/operations"):
            raise ValueError("Use committed operation inventories inside source")
        relative = resolved.relative_to(ROOT).as_posix()
        subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", relative], stderr=subprocess.DEVNULL)
        cases = json.loads(resolved.read_text())
        if (type(cases) is not list or not 1 <= len(cases) <= 512
                or any(type(case) is not str or not 1 <= len(case) <= 512 or "\0" in case for case in cases)
                or len(cases) != len(set(cases)) or set(cases) & set(inventory) or relative in inventories):
            raise ValueError("Invalid, duplicate or overlapping frozen M7 inventory")
        inventories[relative] = cases
        inventory.extend(cases)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests_m7"))
    actual = sorted(test_ids(suite))
    if len(inventory) != len(set(inventory)) or sorted(inventory) != actual:
        raise ValueError("Frozen M7 test denominator changed")
    directory = private_directory(args.evidence_dir, ROOT)
    with private_file(directory / "unittest.log", "w") as output:
        result = unittest.TextTestRunner(stream=output, verbosity=2, failfast=False, resultclass=M7Result).run(suite)
    summary = summarize(actual, result)
    summary.update(source=source, python=platform.python_version(), accepted_denominator=210,
        inventories={name: {"sha256": sha256(ROOT / name),
            **{key: value for key, value in accounting(cases, {case: result.observations[case] for case in cases if case in result.observations}).items() if key != "tests"}}
            for name, cases in inventories.items()}, log_sha256=sha256(directory / "unittest.log"),
        public_release="NOT_AUTHORIZED")
    digest = write_evidence(directory / "suite.json", summary)
    print(json.dumps({k: summary[k] for k in ("source", "python", "status", "original_denominator", "counts", "fixture_counts", "fixtures", "accepted_denominator")}, sort_keys=True))
    print("evidence_sha256=" + digest)
    for case, status in summary["tests"].items():
        print(json.dumps({"test": case, "status": status}, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
