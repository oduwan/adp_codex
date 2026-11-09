"""Explicitly scoped memory commands. No product code or forge mutations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config, load_json
from .errors import ADPError, Conflict
from .git import author, value
from .memory import Memory
from .schema import MAX_RESULT


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", type=Path, default=Path.cwd())
    common.add_argument("--config", type=Path)
    common.add_argument("--remote")
    common.add_argument("--repository-id")
    common.add_argument("--memory-branch", dest="branch")
    common.add_argument("--storage", type=Path)
    root = argparse.ArgumentParser(prog="adp", description="Portable coordination memory; no autonomous execution")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", parents=[common], help="Inspect or explicitly initialize memory")
    mode = init.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    init.add_argument("--authorize-memory-write", action="store_true")
    for command in ("doctor", "status", "recover", "handoff", "release", "cleanup-inbox"):
        commands.add_parser(command, parents=[common])
    upgrade = commands.add_parser("guard-upgrade", parents=[common], help="Explicitly migrate owned memory to guard schema v2")
    upgrade.add_argument("--authorize-memory-write", action="store_true")
    claim = commands.add_parser("claim", parents=[common])
    claim.add_argument("--owner", required=True)
    claim.add_argument("--takeover", action="store_true")
    claim.add_argument("--confirm-stopped-owner")
    add = commands.add_parser("task-add", parents=[common])
    add.add_argument("task_id")
    add.add_argument("--revision")
    revision = commands.add_parser("task-revision", parents=[common])
    revision.add_argument("task_id")
    revision.add_argument("revision")
    assign = commands.add_parser("assign", parents=[common])
    assign.add_argument("task_id")
    assign.add_argument("--worker", required=True)
    deliver = commands.add_parser("deliver", parents=[common])
    deliver.add_argument("result_file", type=Path)
    accept = commands.add_parser("accept", parents=[common])
    accept.add_argument("assignment_id")
    discard = commands.add_parser("discard-inbox", parents=[common])
    discard.add_argument("assignment_id")
    discard.add_argument("--confirm-incomplete", action="store_true")
    retire = commands.add_parser("task-retire", parents=[common])
    retire.add_argument("task_id")
    retire.add_argument("--evidence", required=True)
    retire.add_argument("--confirm-disposition", action="store_true")
    from .discovery_cli import add_commands
    add_commands(commands, common)
    return root


def emit(data: dict) -> None:
    print(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True))


def check_product_worktrees(config: Config) -> None:
    for line in value(config.root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
            if path == config.storage:
                continue
            if value(path, "status", "--porcelain", "--untracked-files=all"):
                raise Conflict("A product worktree has uncommitted changes; doctor requires clean worktrees")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in ("discover", "plan", "refresh"):
            from .discovery_cli import run
            report, code = run(args)
            emit(report)
            return code
        config = Config.discover(args.repo, remote=args.remote,
            repository_id=args.repository_id, branch=args.branch,
            storage=args.storage, config=args.config)
        if args.command == "init" and args.dry_run:
            author(config.root)
            check_product_worktrees(config)
            # Suggestions are output only; they never silently become configuration.
            report = {"mode": "READ_ONLY", "repository_id": config.identity,
                "remote": config.remote, "memory_branch": config.branch,
                "storage": str(config.storage) if config.storage else None,
                "suggested_branch": "adp/state", "prerequisites": "Git and explicit author available",
                "missing_authority": "Initialization requires --apply --authorize-memory-write",
                "product_actions": "DENIED; no policy/execution provider in M1",
                "write_authentication": "UNKNOWN; read access does not prove push permission"}
            if config.branch and config.storage:
                report["memory"] = Memory(config).inspect()
            else:
                report["decision_required"] = "Select --memory-branch and --storage outside the product worktree"
            emit(report)
            return 0
        memory = Memory(config)
        command = args.command
        if command in ("status", "doctor"):
            if command == "doctor":
                author(config.root)
                check_product_worktrees(config)
            report = memory.inspect()
            report["product_actions"] = "DENIED; M1 only coordinates memory"
            if command == "doctor":
                report["authentication"] = "Remote read checked; push permission UNKNOWN"
                report["permitted_actions"] = "Read-only inspection; explicit memory commands only"
            emit(report)
            return 0 if report["health"] == "SYNCED" else 4
        if command == "init":
            result = memory.initialize(authorized=args.authorize_memory_write)
        elif command == "guard-upgrade":
            result = memory.upgrade_guard(authorized=args.authorize_memory_write)
        elif command == "claim":
            result = memory.claim(args.owner, takeover=args.takeover,
                                  confirmed_stopped_owner=args.confirm_stopped_owner)
        elif command in ("handoff", "release"):
            result = memory.handoff()
        elif command == "recover":
            result = memory.recover()
        elif command == "task-add":
            result = memory.add_task(args.task_id, args.revision)
        elif command == "task-revision":
            result = memory.set_revision(args.task_id, args.revision)
        elif command == "assign":
            result = memory.assign(args.task_id, args.worker)
        elif command == "deliver":
            result = {"delivery": str(memory.deliver(load_json(args.result_file, MAX_RESULT)))}
        elif command == "accept":
            result = memory.accept(args.assignment_id)
        elif command == "cleanup-inbox":
            result = memory.cleanup_inbox()
        elif command == "discard-inbox":
            result = memory.discard_inbox(args.assignment_id, confirmed=args.confirm_incomplete)
        elif command == "task-retire":
            result = memory.retire(args.task_id, evidence=args.evidence,
                                   confirmed=args.confirm_disposition)
        else:
            raise AssertionError("Unhandled CLI command")
        emit(result)
        return 0
    except ADPError as exc:
        print(f"REFUSED [{exc.code}]: {exc}", file=sys.stderr)
        return exc.code
    except (OSError, UnicodeError) as exc:
        print("REFUSED [3]: filesystem/encoding unavailable or changed; inspect configuration and recovery", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
