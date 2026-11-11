"""Only existing issue text and native blocking-edge operations are admitted."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from network_http_child import exchange, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
else:
    from .network_http_child import exchange, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES


def validate_request(method, path, body, seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 5
            or type(path) is not str or len(path) > 1024 or method not in ("GET", "PATCH", "POST", "DELETE")):
        raise ValueError("Unsupported bounded ticket request")
    match = re.fullmatch(r"/repos/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})(.*)", path)
    if match is None or match[2] in (".", ".."):
        raise ValueError("Unsupported ticket repository")
    tail = match[3]
    issue = r"/issues/[1-9][0-9]*"
    if method == "GET":
        if body is not None or not (tail == "" or re.fullmatch(issue, tail)):
            raise ValueError("Unsupported ticket observation")
    elif method == "PATCH":
        if (re.fullmatch(issue, tail) is None or type(body) is not dict or not body
                or not set(body) <= {"title", "body"} or any(type(v) is not str for v in body.values())):
            raise ValueError("Only explicit existing issue text is supported")
    elif method == "POST":
        if (re.fullmatch(issue + r"/dependencies/blocked_by", tail) is None or type(body) is not dict
                or set(body) != {"issue_id"} or type(body["issue_id"]) is not int or body["issue_id"] <= 0):
            raise ValueError("Only an existing native blocking dependency is supported")
    elif body is not None or re.fullmatch(issue + r"/dependencies/blocked_by/[1-9][0-9]*", tail) is None:
        raise ValueError("Only an existing native blocking edge can be removed")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > 65536:
        raise ValueError("Ticket diff exceeds bound")
    return raw


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            return 78
        result = exchange(json.loads(raw), validate_request)
        output = (json.dumps(result, separators=(",", ":")) + "\n").encode()
        if len(output) > MAX_OUTPUT_BYTES:
            return 78
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
