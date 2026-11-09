# ADP Codex

[![Scaffold CI](https://github.com/oduwan/adp_codex/actions/workflows/scaffold.yml/badge.svg)](https://github.com/oduwan/adp_codex/actions/workflows/scaffold.yml)

**ADP Codex** is an architecture-first project for a repository-agnostic, Codex-assisted development orchestrator. Its intended workflow is to discover existing GitHub issues, assemble a dependency-aware task track, execute admitted tasks with independent review, and publish only meaningful product outcomes.

> **Status: accepted M1 portable memory and M2 Progress Guard, with an M3 external policy provider candidate.** Autonomous execution, issue discovery and scheduling remain unavailable. Memory writes require explicit authorization; no product-code, issue or infrastructure execution authority is granted.

## Principles

- **Use the repository's existing work queue.** Read issues, pull requests, dependencies, and current refs; never require proprietary issue syntax.
- **Keep Git policy external.** Branch conventions, commit rules, merge permissions, acceptance checks, and release authority belong to the target project.
- **Keep control state separate.** A single Conductor will own compact, portable, Git-backed working memory, independent of product branches and agent-chat history.
- **Prove progress.** A mandatory Progress Guard will detect repeated unproductive cycles, direct independent forensic reassessment, and never treat skipped or quarantined tests as passing.
- **Keep product history human-readable.** Internal test repairs, diagnostics, agent handoffs, and orchestration states stay out of product issue comments. Publish no more than one concise product summary per completed product iteration.
- **Start read-only.** Repository inspection and planning cannot execute issue-body instructions, mutate resources, or assume merge/deploy permissions.

## Accepted M1 portable memory

Issue #1 ships a Python 3.11+ package for explicitly authorized portable
memory, `init`, `doctor`, `status`, ownership and handoff. See the
[CLI and API guide](docs/MEMORY_CLI.md) and [v1 state contract](docs/STATE_CONTRACT.md).
M1 does not execute product code, discover issues or decide Git policy. It was
reviewed and merged in PR #7; accepted `main` remains non-autonomous.

```bash
python3 -m pip install .
adp --help
```

## Accepted M2 Progress Guard

Issue #2, accepted through PR #8, adds a standalone executable guard
with durable counters, externally verified forensic evidence, bounded
recovery and finite diagnostic censuses. It requires an explicit memory upgrade;
read-only M1 behavior is preserved. See [the Guard API and migration guide](docs/GUARD_API.md).
No worker execution or unattended operation is enabled.

## M3 external policy provider candidate

Issue #3 adds an importable typed provider for project-owned Git conventions,
policy provenance and exact-plan authorization decisions. Read-only inspection
and planning neither execute Git writes nor grant permissions from repository
text or credentials. See [the Policy API](docs/POLICY_API.md) for trust ports,
profile schema, M1/M2 compatibility and limits. This candidate requires independent
exact-revision review and separate integration.

## Planned commands

```text
adp init       inspect a target repository; propose initial configuration
adp doctor     inspect Git identity, memory health and remote read access
adp discover   read current issues, PRs, and native relationships
adp plan       construct and refresh a dependency-aware task track
adp run        execute authorized work through the Conductor
adp status     inspect current jobs and blocked decisions
adp resume     recover safely after an interrupted run
adp handoff    transfer ownership to another machine
adp audit      validate evidence, state, and acceptance coverage
```

**This roadmap includes accepted M1 memory commands and planned execution/discovery interfaces.** The packaged Codex skill is intentionally read-only and limited to explaining and reviewing project/track readiness.

## Project layout

```text
plugin.json                  portable Agent Plugins manifest
skills/adp-codex/SKILL.md    Codex skill (read-only scaffold)
docs/ARCHITECTURE.md        core components and ownership boundaries
docs/PROGRESS_GUARD.md      non-optional anti-loop behavior
docs/POLICY_PROVIDER.md     external Git workflow integration
docs/ISSUE_DISCOVERY.md     issue intake and dependency evidence
docs/ROADMAP.md             independently testable milestones
AGENTS.md                   contributor and coding-agent rules
scripts/validate_scaffold.py
tests/test_scaffold.py
.github/workflows/scaffold.yml
```

See [Architecture](docs/ARCHITECTURE.md), [Progress Guard](docs/PROGRESS_GUARD.md), [External policy](docs/POLICY_PROVIDER.md), [Repository Git workflow](docs/GIT_WORKFLOW.md), and [Roadmap](docs/ROADMAP.md).

## Getting started (scaffold)

Clone the repository and validate its packaging:

```bash
python3 scripts/validate_scaffold.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Python 3.11+ is the runtime baseline; the package has no third-party runtime dependencies. See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.

## Origin and scope

This design builds on earlier field experience with compact single-writer coordination and independent exact-revision review, but it does **not** copy any target repository's project-specific safety, deployment, or release policy. The first integration target is GitHub; the system is designed to accommodate other repository providers later. Initial implementation and testing must use disposable synthetic Git repositories and fixture issues, not production worktrees.

## Security and licensing

See [SECURITY.md](SECURITY.md). A public GitHub repository is not an authorization to execute arbitrary issue instructions or use private state.

**License:** not selected yet. No license is granted beyond applicable law. Choose and add a license explicitly before presenting the project as redistributable open-source software.
