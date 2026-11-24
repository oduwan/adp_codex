"""Personal-only semantic receipts; raw discovery observations remain untouched."""
from __future__ import annotations

import re

from .discovery_github import API, GitHubDiscoveryAdapter
from .discovery_schema import NAME
from .schema import require, string


class PersonalGitHubDiscoveryAdapter(GitHubDiscoveryAdapter):
    """Ignore one established transport field in qualified repository slots.

    This is not a recursive redactor or an alternative authority provider.
    Unknown fields and user content remain bound. Historical/default receipts
    are deliberately not migrated to this personal observation contract.
    """

    def _repository(self, value, *, selected):
        if type(value) is not dict or "temp_clone_token" not in value:
            return value
        # Validate before projecting: a lookalike object cannot shed fields.
        message = "Malformed personal repository transport metadata"
        rid, name, owner = value.get("id"), value.get("full_name"), value.get("owner")
        require(type(rid) is int and rid > 0 and type(name) is str and NAME.fullmatch(name), message)
        string(value.get("node_id"), 256)
        require(value.get("name") == name.split("/")[1] and value.get("url") == API + "/repos/" + name
                and type(value.get("private")) is bool, message)
        require(type(owner) is dict and type(owner.get("id")) is int and owner["id"] > 0
                and owner.get("login") == name.split("/")[0] and owner.get("type") in ("User", "Organization"), message)
        if "html_url" in value:
            require(value["html_url"] == "https://github.com/" + name, message)
        if "permissions" in value:
            require(type(value["permissions"]) is dict
                    and all(type(v) is bool for v in value["permissions"].values()), message)
        matches_name = name.lower() == self.name.lower()
        matches_id = self.expected_id is not None and str(rid) == self.expected_id
        require(not selected or matches_name and (self.expected_id is None or matches_id), message)
        # A fork may have its own identity, but cannot contradict the selected
        # repository's name/ID binding even in a head.repo slot.
        require(self.expected_id is None or matches_name == matches_id, message)
        token = value["temp_clone_token"]
        string(token, 4096)
        return {k: v for k, v in value.items() if k != "temp_clone_token"}

    def _pull(self, value):
        if type(value) is not dict:
            return value
        result = dict(value)
        for side in ("head", "base"):
            ref = value.get(side)
            if type(ref) is dict:
                result[side] = {**ref, "repo": self._repository(ref["repo"], selected=side == "base")} if "repo" in ref else ref
        return result

    def _semantic(self, path, values):
        prefix = "/repos/" + self.name
        if path == prefix:
            return self._repository(values, selected=True)
        if path == prefix + "/pulls":
            return [self._pull(v) for v in values] if type(values) is list else self._pull(values)
        if re.fullmatch(re.escape(prefix) + r"/pulls/[1-9][0-9]*", path):
            return self._pull(values)
        return values
