"""Separately selected product-comment grammar, not a general write transport."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adp.personal_product_child import validate_product
from adp.forge_http_child import validate_request
from adp.personal_network_child import exchange_http
from adp.network_http_child import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES


def validate_report(method, path, body, seconds):
    if method in ("POST", "PUT") and path != "/graphql":
        if method != "POST" or not re.fullmatch(r"/repos/[^/]+/[^/]+/issues/[1-9][0-9]*/comments", path or ""):
            raise ValueError("Only a separately approved product comment is supported")
        return validate_request(method, path, body, seconds)
    return validate_product(method, path, body, seconds)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            return 78
        result = exchange_http(json.loads(raw), validate_report)
        output = (json.dumps(result, separators=(",", ":")) + "\n").encode()
        if len(output) > MAX_OUTPUT_BYTES:
            return 78
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
