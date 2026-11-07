"""Hostile bounded input must refuse without blocking or leaking exceptions."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from adp.config import load_json
from adp.errors import ADPError
from adp.schema import MAX_JSON, decode, result_schema


class InputBoundsTests(unittest.TestCase):
    def test_oversized_json_and_special_files_refused(self) -> None:
        payload = b'{"summary":"' + b'x' * MAX_JSON + b'"}'
        with self.assertRaisesRegex(ADPError, "size limit"):
            decode(payload)
        with tempfile.TemporaryDirectory(prefix="adp-bounds-") as directory:
            path = Path(directory) / "result.json"
            path.write_bytes(payload)
            with self.assertRaises(ADPError):
                load_json(path)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ADPError):
                load_json(path)  # O_NONBLOCK: a FIFO can never stall ingestion.

    def test_crafted_result_types_are_controlled_refusals(self) -> None:
        for invalid in (
            [], {"outcome": [], "summary": "x", "evidence": []},
            {"outcome": "PASS", "summary": {"crafted": True}, "evidence": []},
            {"outcome": "PASS", "summary": "x", "evidence": [None]},
            {"outcome": "PASS", "summary": "x", "evidence": [], "execute": "ignored"},
        ):
            with self.assertRaises(ADPError):
                result_schema(invalid)
