"""Explicit synchronous execution entry points; operator code is never inferred."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from .codex_runtime import CodexExecRuntime
from .config import Config, safe_path
from .conductor import Conductor
from .errors import AuthorityError
from .execution_types import Admission
from .schema import require


@dataclass(frozen=True)
class Controller:
    conductor: Conductor
    admissions: tuple[Admission, ...]
    maximum_parallel: int = 1
    track: object = None


def add_commands(commands, common):
    for name in ("run", "resume"):
        command = commands.add_parser(name, parents=[common], help="One explicitly authorized finite Conductor invocation")
        command.add_argument("--controller", type=Path, required=True)
        command.add_argument("--authorize-execution", action="store_true")
        command.add_argument("--maximum-parallel", type=int)
        command.add_argument("--rounds", type=int, default=1)
        command.add_argument("--test-runtime", action="store_true", help="Explicit synthetic runtime qualification only")
    upgrade = commands.add_parser("execution-upgrade", parents=[common], help="Explicit owned v2 to v3 execution-journal upgrade")
    upgrade.add_argument("--authorize-memory-write", action="store_true")
    upgrade.add_argument("--track-lifecycle", action="store_true", help="Explicitly select product-flow v2 and finite track v3")


def load_controller(path, config):
    # This is explicitly selected operator Python, equivalent to installing a
    # PolicyAuthority extension. Never resolve it from repository/issue text.
    path = safe_path(path.absolute())
    require(path.is_file() and path.stat().st_size <= 65536, "Controller must be a bounded regular Python file")
    require(not path.is_relative_to(config.root) and not path.is_relative_to(config.storage),
            "Trusted controller code must be outside product and memory worktrees")
    spec = importlib.util.spec_from_file_location("adp_operator_controller", path)
    require(spec is not None and spec.loader is not None, "Cannot load selected operator controller")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    controller = module.build(config)
    require(type(controller) is Controller and type(controller.conductor) is Conductor, "Controller must build the typed Conductor")
    require(controller.conductor.memory.config == config, "Controller selected a different memory/repository")
    require(type(controller.admissions) is tuple and all(type(a) is Admission for a in controller.admissions), "Typed admitted tasks are required")
    return controller


def run(args):
    if args.command != "status" and not getattr(args, "authorize_execution", False):
        raise AuthorityError("Execution/resume/handoff requires explicit --authorize-execution")
    config = Config.discover(args.repo, remote=args.remote, repository_id=args.repository_id,
        branch=args.branch, storage=args.storage, config=args.config)
    config.require_storage()
    controller = load_controller(args.controller, config)
    conductor = controller.conductor
    selected = conductor
    if controller.track is not None:
        from .autonomous_track import AutonomousTrack
        require(type(controller.track) is AutonomousTrack and controller.track.c is conductor and not controller.admissions,
                "Select one actual track controller, not mixed admissions")
        selected = controller.track
    if args.command == "status":
        return selected.status(), 0
    if args.command == "handoff":
        return selected.handoff(authorized=True), 0
    if type(conductor.runtime) is not CodexExecRuntime and not args.test_runtime:
        return {"status": "UNSUPPORTED_RUNTIME", "reason": "A real supported Codex runtime is required", "background_work": False}, 7
    parallel = args.maximum_parallel if args.maximum_parallel is not None else controller.maximum_parallel
    require(1 <= parallel <= controller.maximum_parallel, "Requested parallelism exceeds explicit project/operator limit")
    method = selected.resume if args.command == "resume" else selected.run
    result = (method(controller.admissions, maximum_parallel=parallel, rounds=args.rounds, authorized=True)
              if selected is conductor else method(maximum_parallel=parallel, rounds=args.rounds, authorized=True))
    return result, 0 if result["status"] == "COMPLETE" else 7 if result["status"] in ("UNSUPPORTED_RUNTIME", "UNSUPPORTED") else 4
