"""Authenticated fake provider over real disposable immutable Git objects/CAS."""
import base64
import json
import os
import subprocess
from datetime import datetime, timezone

from adp.network_http import Response, NetworkTransportError, UPDATE_REFS_MUTATION


def git_bytes(root, *args, raw=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="CAS Fixture", GIT_AUTHOR_EMAIL="fixture@example.org",
        GIT_COMMITTER_NAME="CAS Fixture", GIT_COMMITTER_EMAIL="fixture@example.org",
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+0000", GIT_COMMITTER_DATE="2026-01-01T00:00:00+0000")
    return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                                   input=raw, env=env, stderr=subprocess.DEVNULL)


def gv(root, *args):
    return git_bytes(root, *args).decode().strip()


class ObjectServer:
    """Fake GitHub JSON semantics, real independent Git storage/update-ref CAS.

    No HTTP or remote Git command is used. Its token/authority is a fixture and
    grants no rights to the production port. Interleaving runs at the atomic
    Git update boundary, after every client-side observation has finished.
    """
    def __init__(self, root, target):
        self.root, self.target = root, target
        self.calls, self.mutations = [], []
        self.permission = "WRITE"
        self.protected = False
        self.rules = []
        self.legacy = 0
        self.wrong_identity = False
        self.failure = None
        self.mismatch = False
        self.before_cas = None
        self.after_upload = None
        self.lose_ack = False
        self.page_size = 100

    def refs(self):
        return dict(line.split(" ", 1) for line in gv(self.root, "for-each-ref", "--format=%(refname) %(objectname)").splitlines())

    @staticmethod
    def response(value, status=200):
        return Response(status, json.dumps(value).encode())

    def request(self, method, path, body, *, seconds):
        assert 0 < seconds <= 5
        self.calls.append((method, path, body))
        if self.failure is not None:
            selector, response = self.failure
            if selector(method, path, body):
                return response
        if path == "/graphql":
            if body["query"] == UPDATE_REFS_MUTATION:
                payload = body["variables"]["input"]
                assert payload["repositoryId"] == self.target.node_id and len(payload["refUpdates"]) == 1
                update = payload["refUpdates"][0]
                assert update["force"] is False and update["name"] == self.target.ref
                assert update["afterOid"] != "0" * 40
                if self.before_cas:
                    self.before_cas()
                # Actual Git compares the old SHA atomically, not a Python check.
                try:
                    gv(self.root, "update-ref", update["name"], update["afterOid"], update["beforeOid"])
                except subprocess.CalledProcessError:
                    return self.response({"errors": [{"type": "CONFLICT"}]})
                self.mutations.append(("ref", update))
                if self.lose_ack:
                    self.lose_ack = False
                    raise NetworkTransportError("Synthetic stopped transport lost actual update acknowledgement")
                return self.response({"data": {"updateRefs": {"clientMutationId": payload["clientMutationId"]}}})
            repo = {"id": self.target.node_id, "databaseId": self.target.database_id,
                    "nameWithOwner": self.target.owner + "/" + self.target.name, "viewerPermission": self.permission}
            if self.wrong_identity:
                repo["id"] = "another-canonical-repository"
            refs = self.refs()
            if "ADPRefs" in body["query"]:
                variables = body["variables"]
                prefix = variables["prefix"]
                items = [{"prefix": prefix, "name": name[len(prefix):], "target": {"oid": sha}}
                         for name, sha in sorted(refs.items()) if name.startswith(prefix)]
                start = int(variables["after"] or "0")
                end = start + self.page_size
                repo["refs"] = {"nodes": items[start:end], "pageInfo": {
                    "hasNextPage": end < len(items), "endCursor": str(end) if end < len(items) else None}}
            else:
                sha = refs.get(self.target.ref)
                repo["ref"] = None if sha is None else {"prefix": "refs/heads/", "name": self.target.branch,
                    "target": {"oid": sha, "__typename": "Commit"},
                    "branchProtectionRule": {"id": "protected"} if self.protected else None}
                repo["branchProtectionRules"] = {"totalCount": self.legacy,
                    "nodes": [] if not self.legacy else [{"id": "legacy"}], "pageInfo": {"hasNextPage": False}}
            return self.response({"data": {"node": repo}})
        if "/rules/branches/" in path:
            return self.response(self.rules)
        kind = path.split("/git/", 1)[1].split("/", 1)[0]
        if method == "GET":
            sha = path.rsplit("/", 1)[1]
            try:
                assert gv(self.root, "cat-file", "-t", sha) == "commit"
            except subprocess.CalledProcessError:
                return self.response({"message": "not available"}, 404)
            return self.response({"sha": sha})
        if kind == "blobs":
            assert body["encoding"] == "base64"
            sha = git_bytes(self.root, "hash-object", "-w", "--stdin", raw=base64.b64decode(body["content"], validate=True)).decode().strip()
        elif kind == "trees":
            entries = sorted(body["tree"], key=lambda e: e["path"].encode() + (b"/" if e["type"] == "tree" else b""))
            raw = b"".join(e["mode"].lstrip("0").encode() + b" " + e["path"].encode() + b"\0" + bytes.fromhex(e["sha"]) for e in entries)
            sha = git_bytes(self.root, "hash-object", "-w", "-t", "tree", "--stdin", raw=raw).decode().strip()
        else:
            assert kind == "commits"
            def actor(value):
                seconds = int(datetime.strptime(value["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
                return f"{value['name']} <{value['email']}> {seconds} +0000".encode()
            raw = (b"tree " + body["tree"].encode() + b"\n" + b"".join(b"parent " + p.encode() + b"\n" for p in body["parents"])
                   + b"author " + actor(body["author"]) + b"\ncommitter " + actor(body["committer"]) + b"\n\n" + body["message"].encode())
            sha = git_bytes(self.root, "hash-object", "-w", "-t", "commit", "--stdin", raw=raw).decode().strip()
        self.mutations.append((kind, sha))
        if self.after_upload:
            callback, self.after_upload = self.after_upload, None
            callback()
        return self.response({"sha": "d" * 40 if self.mismatch else sha}, 201)
