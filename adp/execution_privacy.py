"""Bounded credential-shape refusal before untrusted output becomes portable.

This is defense in depth, not universal secret or private-data classification.
The trusted runtime keeps raw output locally; operator evidence classification
and OS/credential isolation remain required. Never include a match in errors.
"""
from __future__ import annotations

import re

_CREDENTIAL = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}"
    r"|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b"
    r"|-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"
    r"|https?://[^/\s:@]+:[^/\s@]+@"
    r"|(?i:\b(?:api[_-]?key|access[_-]?token|password|secret|token)\s*[=:]\s*[^\s,;]{8,}))"
)


def credential_shaped(value: object) -> bool:
    if isinstance(value, str):
        return _CREDENTIAL.search(value) is not None
    if isinstance(value, dict):
        return any(credential_shaped(k) or credential_shaped(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(credential_shaped(v) for v in value)
    return False
