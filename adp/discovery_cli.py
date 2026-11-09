"""Read-only discover/plan/refresh commands, isolated from memory writers."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .config import Config, load_json
from .guard_types import data
from .memory import Memory
from .schema import fields, require
from .discovery import DependencyPlanner, MemoryProgressAdapter, complete_snapshot
from .discovery_github import FixtureTransport, GitHubDiscoveryAdapter, GitHubHTTPTransport, Response
from .discovery_schema import MAX_BYTES, load_snapshot, load_track, typed
from .discovery_types import MemoryBinding, Status


def add_commands(commands, common):
    for name in ("discover", "plan", "refresh"):
        command = commands.add_parser(name, parents=[common], help="Read-only GitHub observation/planning preview")
        command.add_argument("--github-repository")
        command.add_argument("--github-id")
        command.add_argument("--token-env", default="GH_TOKEN")
        command.add_argument("--api-fixture", type=Path)
        command.add_argument("--snapshot", type=Path, action="append", default=[])
        command.add_argument("--previous", type=Path)
        command.add_argument("--memory-bindings", type=Path)
        if name == "discover":
            command.add_argument("--refresh", action="store_true")


def fixture(path: Path) -> FixtureTransport:
    payload = load_json(path, MAX_BYTES)
    fields(payload, "schema_version responses")
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1
            and type(payload["responses"]) is dict and len(payload["responses"]) <= 4096, "Invalid API fixture version/bounds")
    responses = {}
    for route, value in payload["responses"].items():
        def response(v):
            fields(v, "status body headers")
            require(type(v["status"]) is int and type(v["headers"]) is dict, "Invalid fixture response")
            return Response(v["status"], v["body"], tuple(v["headers"].items()))
        responses[route] = tuple(response(v) for v in value) if type(value) is list else response(value)
        require(responses[route] != (), "Empty fixture response sequence")
    return FixtureTransport(responses)


def run(args):
    refreshing = args.command == "refresh" or getattr(args, "refresh", False)
    require(not refreshing or args.previous is not None, "Refresh requires an explicit --previous track")
    previous = load_track(load_json(args.previous, MAX_BYTES)) if args.previous else None
    require(not args.snapshot or not (args.api_fixture or args.github_repository or args.github_id), "Choose frozen snapshots or GitHub discovery")
    config = None
    if args.snapshot:
        snapshots = tuple(load_snapshot(load_json(path, MAX_BYTES)) for path in args.snapshot)
    else:
        config = Config.discover(args.repo, remote=args.remote, repository_id=args.repository_id,
            branch=args.branch, storage=args.storage, config=args.config)
        from .git import value
        endpoint = value(config.root, "remote", "get-url", config.remote)
        match = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?", endpoint)
        name = args.github_repository or (match[1] if match else None)
        require(name is not None, "Select a GitHub remote/repository explicitly")
        if args.api_fixture:
            transport = fixture(args.api_fixture)
        else:
            require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", args.token_env), "Invalid token environment variable name")
            transport = GitHubHTTPTransport(os.environ.get(args.token_env, ""))
        snapshots = (GitHubDiscoveryAdapter(name, transport, expected_id=args.github_id, config=config).discover(),)
    if args.command == "discover" and not refreshing:
        require(len(snapshots) == 1 and args.memory_bindings is None, "Discovery emits one snapshot; use plan for memory reconciliation")
        return data(snapshots[0]), 0 if complete_snapshot(snapshots[0]) else 4
    ports = ()
    if args.memory_bindings:
        if config is None:
            config = Config.discover(args.repo, remote=args.remote, repository_id=args.repository_id,
                branch=args.branch, storage=args.storage, config=args.config)
        payload = load_json(args.memory_bindings)
        fields(payload, "schema_version bindings")
        require(type(payload["schema_version"]) is int and payload["schema_version"] == 1, "Unsupported memory binding version")
        bindings = typed(tuple[MemoryBinding, ...], payload["bindings"])
        ports = (MemoryProgressAdapter(Memory(config), bindings),)
    # CLI deliberately has no self-asserted review/verifier switch. Extensions
    # supply independent authenticated readiness through the importable API.
    track = DependencyPlanner().plan(snapshots, previous=previous, memory=ports)
    return data(track), 4 if any(not complete_snapshot(s) for s in snapshots) or any(c.status == Status.UNKNOWN for c in track.candidates) else 0
