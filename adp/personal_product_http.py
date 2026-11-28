"""Same personal credentials, supervisor and stop fence, explicitly selected."""
from .personal_network import PersonalDiscoveryRead, PersonalGitHubTransport
from .personal_product_child import validate_product
from .errors import ADPError
from .schema import require
from .network_http import NetworkTransportError
from .discovery_github import GitHubDiscoveryAdapter, Response
from types import SimpleNamespace
import json
import re
from urllib.parse import parse_qs, urlsplit
from .runtime_limits import request_allowance


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
        if method == "GET" and response.status == 200 and re.fullmatch(
                re.escape(self.target.api) + r"/(?:pulls(?:/[1-9][0-9]*/reviews)?|issues/[1-9][0-9]*/comments)\?(?:state=all&(?:head=[A-Za-z0-9_.%~-]+&)?)?per_page=100&page=[1-9][0-9]*", path):
            try:
                page = int(parse_qs(path.partition("?")[2])["page"][0])
                rows = json.loads(response.body)
                require(type(rows) is list and len(rows) <= 100 and page <= 20, "Incomplete forge page")
                expected = parse_qs(path.partition("?")[2], strict_parsing=True)
                relations = set()
                targets = {}
                link = dict(checked.headers).get("link")
                for entry in (() if link is None else link.split(",")):
                    require(bool(entry.strip()), "Empty pagination entry")
                    match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="(next|prev|first|last)"\s*', entry)
                    require(match is not None and match[2] not in relations, "Malformed or duplicate pagination control")
                    relations.add(match[2])
                    url = urlsplit(match[1])
                    query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                    number = query.get("page", [])
                    require(len(number) == 1 and re.fullmatch(r"[1-9][0-9]*", number[0]) is not None, "Ambiguous page")
                    target = int(number[0])
                    targets[match[2]] = target
                    require(1 <= target <= 20 and url.scheme == "https" and url.netloc == "api.github.com"
                            and url.path == path.partition("?")[0] and not url.fragment
                            and query == {**expected, "page": [str(target)]}, "Unsafe or unsupported pagination URL")
                    require((match[2] != "next" or target == page + 1 and len(rows) == 100)
                            and (match[2] != "prev" or target == page - 1)
                            and (match[2] != "first" or target == 1)
                            and (match[2] != "last" or target >= page and (target == page or len(rows) == 100)),
                            "Nonsequential or contradictory forge pagination")
                require("next" not in targets or "last" not in targets or targets["next"] <= targets["last"],
                        "Next page contradicts final page")
            except (ADPError, ValueError, TypeError, KeyError):
                raise NetworkTransportError("UNKNOWN: incomplete or ambiguous forge pagination") from None
        return response


class PersonalProjectRead(PersonalDiscoveryRead):
    def get(self, path, *, seconds=None):
        seconds = self.service.limits.request_timeout_seconds if seconds is None else request_allowance(seconds)
        # One shared operation budget. Only this request's allowance is shorter;
        # every persistent profile/M2/count tightening stays on the same object.
        return super().get(path, seconds=seconds)
