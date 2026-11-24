"""Personal selection of the existing forge/#21 grammars; no reporting rights."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adp.forge_http_child import validate_request as forge_request
from adp.personal_network_child import exchange_http, validate_personal
from adp.network_http_child import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
from adp.project_validation_github import validate_get
from adp.policy_schema import ref
from adp.network_git import REF_QUERY, REFS_QUERY
from adp.personal_rules import PERSONAL_REF_QUERY


def validate_product(method, path, body, seconds):
    if method == "POST" and path == "/graphql":
        if type(body) is not dict or body.get("query") not in (REF_QUERY, PERSONAL_REF_QUERY, REFS_QUERY):
            raise ValueError("Product selection has read-only GraphQL")
    elif method in ("POST", "PUT"):
        # Publication stays on the separately approved #40 transport. A PR or
        # merge callback cannot authorize even immutable Git-object uploads.
        if method == "POST" and not re.fullmatch(r"/repos/[^/]+/[^/]+/pulls", path or ""):
            raise ValueError("Only the approved Draft PR POST is supported")
        return forge_request(method, path, body, seconds)
    # Reuse the original finite bounds and Git/discovery selection first.
    try:
        return validate_personal(method, path, body, seconds)
    except (ValueError, TypeError):
        pass
    if method == "GET":
        try:
            validate_get(path, seconds)
        except Exception:
            match = re.fullmatch(r"/repos/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}/(?:branches/([^/?]+)/protection|rules/branches/([^/?]+)\?per_page=100&page=([1-9][0-9]*)|collaborators/[A-Za-z0-9][A-Za-z0-9-]{0,38}/permission)", path or "")
            if match is None or match[3] is not None and int(match[3]) > 20:
                return forge_request(method, path, body, seconds)
            encoded = match[1] or match[2]
            if encoded is not None:
                decoded = unquote(encoded)
                if quote(decoded, safe="") != encoded:
                    raise ValueError("Noncanonical project branch")
                ref("refs/heads/" + decoded)
        # Apply the accepted forge's common <=5s/body/size checks.
        if body is not None:
            raise ValueError("Read-only evidence has no payload")
        return forge_request("GET", "/repos/owned/selected", body, seconds)
    if method == "POST" and not re.fullmatch(r"/repos/[^/]+/[^/]+/pulls", path or ""):
        raise ValueError("Personal product selection does not authorize reports")
    return forge_request(method, path, body, seconds)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            return 78
        result = exchange_http(json.loads(raw), validate_product)
        output = (json.dumps(result, separators=(",", ":")) + "\n").encode()
        if len(output) > MAX_OUTPUT_BYTES:
            return 78
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
