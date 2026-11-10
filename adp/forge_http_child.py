"""Narrow forge grammar using the accepted supervised fixed-origin exchange."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import sys

# This script is launched with -I from the trusted ADP installation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from network_http_child import exchange, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
else:
    from .network_http_child import exchange, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES


def validate_request(method, path, body, seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 5
            or type(path) is not str or len(path) > 1024
            or method not in ("GET", "POST", "PUT")):
        raise ValueError("Unsupported bounded forge request")
    match = re.fullmatch(r"/repos/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})(.*)", path)
    if match is None or match[2] in (".", ".."):
        raise ValueError("Unsupported forge repository")
    tail = match[3]
    if method == "GET":
        allowed = (tail == "" or re.fullmatch(r"/pulls/[1-9][0-9]*(?:/reviews\?per_page=100&page=[1-9][0-9]*)?", tail)
            or re.fullmatch(r"/(?:pulls\?state=all&|issues/[1-9][0-9]*/comments\?)per_page=100&page=[1-9][0-9]*", tail)
            or re.fullmatch(r"/git/commits/[0-9a-f]{40}", tail))
        if body is not None or not allowed:
            raise ValueError("Unsupported forge observation")
    elif method == "PUT":
        if (re.fullmatch(r"/pulls/[1-9][0-9]*/merge", tail) is None or type(body) is not dict
                or set(body) != {"sha", "merge_method"} or body["merge_method"] not in ("merge", "squash")
                or type(body["sha"]) is not str or re.fullmatch(r"[0-9a-f]{40}", body["sha"]) is None):
            raise ValueError("Only exact-head merge/squash is supported")
    elif tail == "/pulls":
        if (type(body) is not dict or set(body) != {"head", "base", "title", "draft", "body"}
                or body["draft"] is not True or any(type(body[k]) is not str for k in ("head", "base", "title", "body"))
                or any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,239}", body[k]) is None
                    or any(x in body[k] for x in ("..", "//", "@{")) for k in ("head", "base"))):
            raise ValueError("Only explicit Draft PR creation is supported")
    elif re.fullmatch(r"/issues/[1-9][0-9]*/comments", tail):
        if type(body) is not dict or set(body) != {"body"} or type(body["body"]) is not str:
            raise ValueError("Explicit product body required")
    else:
        raise ValueError("Unsupported forge mutation")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > 8192:
        raise ValueError("Forge request exceeds bound")
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
