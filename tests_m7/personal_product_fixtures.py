"""Synthetic GitHub/project checks and patched real-runtime type; no live proof."""
import copy
import json
from subprocess import CalledProcessError
from dataclasses import replace

from adp.network_http import Response, NetworkTransportError
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from personal_publication_fixtures import PersonalObjectTransport, PublicationFixture
from network_fixtures import gv


class ProductTransport(PersonalObjectTransport):
    def __init__(self, f, root, target):
        super().__init__(f, root, target)
        self.pulls, self.effects, self.reviews = [], [], []
        self.loss, self.denial, self.hook = None, None, None
        self.conclusion, self.app, self.ci_sha = "success", 9, None
        self.rules = []
        self.native_permission = "write"

    def request(self, method, path, body, *, seconds):
        if method == "POST" and path == self.target.api + "/pulls" or method == "PUT" and path.endswith("/merge"):
            assert self.authorize_write() is True
        if self.hook is not None:
            self.hook(method, path)
        base = self.target.api
        data, status = None, 200
        if self.denial is not None and self.denial(method, path):
            status, data = 403, {}
        elif method == "POST" and path == base + "/pulls":
            self.effects.append((method, path, copy.deepcopy(body)))
            if self.loss == "before":
                raise NetworkTransportError("Synthetic confirmed-stop lost request")
            number = len(self.pulls) + 10
            repo = {"id": self.target.database_id, "node_id": self.target.node_id, "full_name": self.f.name}
            data = {"id": number + 2000, "node_id": "PR-native-" + str(number), "number": number,
                "url": "https://api.github.com" + base + "/pulls/" + str(number),
                "html_url": "https://github.com/" + self.f.name + "/pull/" + str(number),
                "title": body["title"], "body": body["body"], "draft": True, "state": "open", "merged": False,
                "updated_at": "2026-11-09T08:00:00Z", "user": {"id": 91}, "mergeable": True, "mergeable_state": "clean",
                "head": {"ref": body["head"], "sha": gv(self.server.root, "rev-parse", self.target.ref), "repo": repo},
                "base": {"ref": body["base"], "sha": gv(self.server.root, "rev-parse", "refs/heads/" + body["base"]), "repo": repo}}
            self.pulls.append(data)
        elif method == "PUT" and path.endswith("/merge"):
            self.effects.append((method, path, copy.deepcopy(body)))
            if self.loss == "before":
                raise NetworkTransportError("Synthetic confirmed-stop lost merge")
            p = self.pulls[0]
            assert p["head"]["sha"] == body["sha"] and p["draft"] is False
            old = gv(self.server.root, "rev-parse", "refs/heads/trunk")
            args = ["commit-tree", gv(self.server.root, "rev-parse", body["sha"] + "^{tree}"), "-p", old]
            if body["merge_method"] == "merge":
                args += ["-p", body["sha"]]
            result = gv(self.server.root, *args, "-m", "Synthetic native merge")
            gv(self.server.root, "update-ref", "refs/heads/trunk", result, old)
            p.update(merged=True, state="closed", merge_commit_sha=result, merged_by={"id": 91})
            data = {"merged": True, "sha": result}
        elif method == "GET" and path.startswith(base + "/pulls?"):
            for p in self.pulls:
                p["head"]["sha"] = gv(self.server.root, "rev-parse", self.target.ref)
            data = copy.deepcopy(self.pulls)
        elif method == "GET" and "/reviews?" in path:
            data = self.reviews
        elif method == "GET" and path.startswith(base + "/pulls/"):
            data = copy.deepcopy(next(p for p in self.pulls if str(p["number"]) == path.rsplit("/", 1)[1]))
            data["head"]["sha"] = gv(self.server.root, "rev-parse", self.target.ref)
        elif method == "GET" and "/collaborators/" in path:
            data = {"user": {"id": 102}, "permission": self.native_permission}
        elif method == "GET" and "/rules/branches/trunk?" in path:
            data = copy.deepcopy(self.rules)
        elif method == "GET" and "/git/ref/heads/" in path:
            data = {"ref": self.target.ref, "object": {"sha": gv(self.server.root, "rev-parse", self.target.ref)}}
        elif method == "GET" and path.partition("?")[0].endswith("/statuses"):
            data = []
        elif method == "GET" and path.partition("?")[0].endswith("/check-suites"):
            data = {"total_count": 1, "check_suites": [{"id": 71}]}
        elif method == "GET" and path.partition("?")[0].endswith("/check-runs"):
            data = {"total_count": 1, "check_runs": [{"id": 72, "name": "unit", "app": {"id": self.app},
                "head_sha": self.ci_sha or gv(self.server.root, "rev-parse", self.target.ref), "status": "completed",
                "conclusion": self.conclusion, "url": "https://api.github.com" + base + "/check-runs/72",
                "started_at": "1970-01-01T00:16:30Z", "completed_at": "1970-01-01T00:16:35Z"}]}
        elif method == "GET" and "/git/commits/" in path:
            revision = path.rsplit("/", 1)[1]
            try:
                data = {"sha": revision, "tree": {"sha": gv(self.server.root, "rev-parse", revision + "^{tree}")},
                    "parents": [{"sha": p} for p in gv(self.server.root, "show", "-s", "--format=%P", revision).split()]}
            except CalledProcessError:
                status, data = 404, {"message": "Not Found"}
        else:
            return super().request(method, path, body, seconds=seconds)
        self.last_response = (status, json.dumps(data).encode(), ())
        if method in ("POST", "PUT") and path != "/graphql" and self.loss == "after":
            self.loss = None
            raise NetworkTransportError("Synthetic confirmed-stop lost effect response")
        return Response(status, json.dumps(data).encode())


class ProductFixture(PublicationFixture):
    def enroll(self, ci_transport=None):
        if self.choices.checks and ci_transport is None:
            from personal_fixtures import NativePersonalReads
            ci_transport = NativePersonalReads(self)
        return PublicationFixture.enroll(self, ci_transport)

    def product_ready(self):
        pub = self.ready()
        proposal = pub.preview()
        self.assertEqual(self.publish(proposal["approval"])["status"], "PUBLISHED_UNACCEPTED")
        self.c = ProductCoordinator(self.personal, self.transport, None, runtime=self.runtime, clock=lambda: self.now)
        self.http = ProductTransport(self, self.store, pub.target)
        repo = self.transport.api.responses[self.prefix].body
        repo.update(allow_merge_commit=True, allow_squash_merge=True)
        self.product = self.reconnect_product()
        return self.product

    def reconnect_product(self):
        product = PersonalProduct(self.c, transport=self.http)
        self.http.authorize_write = product.write_authorized
        return product

    def create_pr(self, *, loss=None):
        self.http.loss = loss
        proposal = self.product.proposed("PR", title="Original task implementation", body="Implement the admitted task. Refs #1")
        result = self.product.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, title=proposal["result"]["title"], body=proposal["result"]["body"])
        self.assertEqual(result["status"], "PR_PRESENT")
        return proposal

    def execute_product(self, purpose, *, accept_native=False, confirm_no_checks=False):
        proposal = self.product.execution_preview(purpose, accept_native=accept_native, confirm_no_checks=confirm_no_checks)
        return self.product.execute(purpose, reviewed=proposal["approval"], authorized=True,
            accept_native=accept_native, confirm_no_checks=confirm_no_checks)

    def merge_product(self, proposal):
        return self.product.intent("MERGE", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, method="merge", delegate=True, accept_envelope=True)
