"""Private supervised gh credential/read-HTTP child for personal publication.

Tokens exist only in private pipes. This is trusted operator code, never a
worker command or a GitHub App issuance/scoping implementation.
"""
from __future__ import annotations

import base64
import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import ssl
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adp.discovery_github import ENROLLMENT_PATH, PATH
from adp.network_http_child import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES, validate_request
from urllib.parse import quote, unquote


def validate_personal(method, path, body, seconds):
    if method == "GET" and type(path) is str:
        match = re.fullmatch(r"/repos/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}/branches/([^/?]+)/protection", path)
        if match:
            from adp.policy_schema import branch
            decoded = unquote(match[1])
            branch(decoded)
            if quote(decoded, safe="") != match[1]:
                raise ValueError("Noncanonical protection branch")
            return validate_request("GET", "/repos/owned/selected/git/commits/" + "1" * 40, body, seconds)
    if method == "GET" and type(path) is str and (path == "/user" or PATH.fullmatch(path) or ENROLLMENT_PATH.fullmatch(path)):
        # The original validator supplies shared bounds; only this separate
        # personal child admits the accepted discovery GET grammar.
        return validate_request("GET", "/repos/owned/selected/git/commits/" + "1" * 40, body, seconds)
    return validate_request(method, path, body, seconds)


def file_identity(path, maximum=64 * 1048576):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError("Unqualified credential path")
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid())
            or info.st_mode & 0o022 or info.st_size > maximum):
        raise ValueError("Unqualified credential file")
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise ValueError("Credential file exceeds bounds")
    return {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid,
            "mode": stat.S_IMODE(info.st_mode), "sha256": hashlib.sha256(raw).hexdigest()}


def executable_identity(path):
    identity = file_identity(path)
    if identity["mode"] & (stat.S_ISUID | stat.S_ISGID):
        raise ValueError("Privilege-changing gh executable is unsupported")
    try:
        capability = os.getxattr(path, "security.capability", follow_symlinks=False)
    except OSError as exc:
        if exc.errno != errno.ENODATA:
            raise ValueError("Cannot qualify gh file capabilities") from None
        capability = b""
    if capability:
        raise ValueError("File-capability gh executable is unsupported")
    return identity


def trusted_ancestry(path, *, directory=False):
    """Pin root/operator-owned directories that cannot be renamed by others.

    Even a safe leaf can be replaced through an attacker-writable parent.
    Shared writable trees (including /tmp) are not credential installations.
    """
    path = Path(path)
    ancestors = (path, *path.parents) if directory else path.parents
    result = []
    for parent in ancestors:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                or info.st_mode & 0o022):
            raise ValueError("Untrusted credential ancestry")
        result.append({"path": str(parent), "device": info.st_dev, "inode": info.st_ino,
                       "uid": info.st_uid, "mode": stat.S_IMODE(info.st_mode)})
    return result


def context(gh, config):
    uid = os.getuid()
    if uid == 0 or uid != os.geteuid() or os.getgid() != os.getegid():
        raise ValueError("Use the normal nonprivileged operator account")
    directory = Path(config)
    if (not directory.is_absolute() or directory.resolve() != directory or directory.is_symlink()
            or directory.stat().st_uid != uid or directory.stat().st_mode & 0o022):
        raise ValueError("Unqualified gh configuration")
    executable_ancestry = trusted_ancestry(gh)
    configuration_ancestry = trusted_ancestry(directory, directory=True)
    files = {}
    for name in ("hosts.yml", "config.yml"):
        path = directory / name
        if path.exists() or path.is_symlink():
            files[name] = file_identity(path, 65536)
    keyring = {name: os.environ[name] for name in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR") if name in os.environ}
    return {"uid": uid, "gid": os.getgid(), "pid_namespace": os.stat("/proc/self/ns/pid").st_ino,
            "gh": str(gh), "executable": executable_identity(gh), "config": str(config), "files": files,
            "executable_ancestry": executable_ancestry, "configuration_ancestry": configuration_ancestry,
            "keyring_context": hashlib.sha256(json.dumps(keyring, sort_keys=True).encode()).hexdigest()}


def credential(value):
    if set(value) != {"kind", "context"} or type(value["context"]) is not dict:
        raise ValueError("Invalid private credential request")
    expected = value["context"]
    if context(expected["gh"], expected["config"]) != expected:
        raise ValueError("Credential execution context changed")
    env = {name: os.environ[name] for name in ("LANG", "LC_ALL", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR") if name in os.environ}
    env.update(HOME=pwd.getpwuid(os.getuid()).pw_dir, GH_CONFIG_DIR=expected["config"], GH_PROMPT_DISABLED="1")
    # No GH_TOKEN/GITHUB_TOKEN/GH_HOST/GH_REPO, Git helper, shell or issue text.
    process = subprocess.Popen((expected["gh"], "auth", "token", "--hostname", "github.com", "--no-refresh"),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=env["HOME"], env=env)
    raw = process.stdout.read(4097)
    if len(raw) > 4096 or process.wait() != 0:
        raise ValueError("Stored github.com gh credential unavailable")
    token = raw.decode("ascii").strip()
    if not token or not all(33 <= ord(c) < 127 for c in token) or context(expected["gh"], expected["config"]) != expected:
        raise ValueError("Credential identity or context changed")
    version_process = subprocess.Popen((expected["gh"], "--version"), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=env["HOME"], env=env)
    version_raw = version_process.stdout.read(1025)
    if len(version_raw) > 1024 or version_process.wait() != 0:
        raise ValueError("Cannot identify selected gh CLI")
    match = re.match(rb"gh version ([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$)", version_raw)
    if match is None or context(expected["gh"], expected["config"]) != expected:
        raise ValueError("Selected gh CLI changed")
    return {"context": expected, "token": token, "version": match[1].decode("ascii")}


def exchange_http(value, validator=validate_personal):
    if set(value) != {"kind", "method", "path", "body", "seconds", "token"}:
        raise ValueError("Invalid private HTTP request")
    body = validator(value["method"], value["path"], value["body"], value["seconds"])
    token = value["token"]
    if type(token) is not str or not 0 < len(token) <= 4096 or not all(33 <= ord(c) < 127 for c in token):
        raise ValueError("Invalid private credential")
    connection = http.client.HTTPSConnection("api.github.com", 443, timeout=value["seconds"], context=ssl.create_default_context())
    try:
        connection.request(value["method"], value["path"], body=body if value["method"] != "GET" else None,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10", "Content-Type": "application/json", "User-Agent": "adp-personal-publication"})
        response = connection.getresponse()
        if not 100 <= response.status <= 599 or 300 <= response.status <= 399:
            raise ValueError("Redirects unsupported")
        headers = response.getheaders()
        if len(headers) > 128 or sum(len(k) + len(v) for k, v in headers) > 65536:
            raise ValueError("Response headers exceed bounds")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Response exceeds bounds")
        return {"status": response.status, "body_base64": base64.b64encode(raw).decode("ascii"), "headers": headers}
    finally:
        connection.close()


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("Private input exceeds bound")
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError("Invalid private input")
        result = credential(value) if value.get("kind") == "credential" else exchange_http(value) if value.get("kind") == "http" else None
        if result is None:
            raise ValueError("Unsupported private operation")
        output = (json.dumps(result, separators=(",", ":")) + "\n").encode()
        if len(output) > MAX_OUTPUT_BYTES:
            raise ValueError("Private output exceeds bound")
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 78  # No exception, credential, stderr or payload is reported.


if __name__ == "__main__":
    raise SystemExit(main())
