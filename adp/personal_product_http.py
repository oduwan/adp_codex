"""Same personal credentials, supervisor and stop fence, explicitly selected."""
from .personal_network import PersonalDiscoveryRead, PersonalGitHubTransport
from .personal_product_child import validate_product
from .schema import require
from .network_git import _Budget
from .network_http import NetworkTransportError
from .discovery_github import GitHubDiscoveryAdapter, Response
from types import SimpleNamespace
import time


class PersonalProductTransport(PersonalGitHubTransport):
    validator = staticmethod(validate_product)
    http_child = "personal_product_child.py"

    def request(self, method, path, body, *, seconds):
        response = super().request(method, path, body, seconds=seconds)
        native = Response(response.status, None, self.last_response[2])
        parser = GitHubDiscoveryAdapter(self.target.owner + "/" + self.target.name,
            SimpleNamespace(get=lambda _: native), max_requests=1)
        parser._halt, parser._requests = False, 0
        checked = parser._get(path)
        if checked.status == 0 or checked.status == 200 and parser._halt:
            raise NetworkTransportError("UNKNOWN: native control headers or rate budget unavailable")
        return response


class PersonalProjectRead(PersonalDiscoveryRead):
    def get(self, path, *, seconds=5):
        require(0 < seconds <= 5, "Project reads retain the five-second request bound")
        outer = self.service._budget.get()
        budget = _Budget(min(outer.end if outer else float("inf"), time.monotonic() + seconds), outer.calls if outer else 0)
        token = self.service._budget.set(budget)
        try:
            return super().get(path)
        finally:
            if outer is not None:
                outer.calls = budget.calls
            self.service._budget.reset(token)
