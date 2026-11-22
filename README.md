# ADP Codex

[![Qualification CI](https://github.com/oduwan/adp_codex/actions/workflows/scaffold.yml/badge.svg)](https://github.com/oduwan/adp_codex/actions/workflows/scaffold.yml)

ADP Codex provides portable Git-backed coordination memory, an executable Progress
Guard, external Git policy decisions, read-only GitHub discovery/planning, and
finite explicitly authorized Codex orchestration. M1–M5 are accepted through
[PR #11](https://github.com/oduwan/adp_codex/pull/11), merged at
`1eb00b3e94151a16a621aab20e71943b3ea2c8a1`.

**M6 is qualification codework. Public release is NOT_AUTHORIZED.** No license has
been selected. A green test, installed skill, Git credential or issue description
never authorizes execution, merge, deployment or release.

## Installation and first inspection

Install the Python 3.11+ engine and Codex plugin together from a selected local
development archive. The [installer guide](docs/operations/INSTALL_ADP.md)
covers the one-command install, verification, upgrades and removal.

Open your project in a fresh Codex session and invoke `$adp-codex` for guided
inspection and setup. The [first-use walkthrough](docs/operations/CODEX_FIRST_USE.md)
covers explicit setup approval, diagnostics and bounded execution.

For a personally owned GitHub.com project, the explicit
[personal backend](docs/operations/PERSONAL_ENROLLMENT.md) provides automatic
local coordination setup and one finite local-draft workflow without external
providers or hand-written JSON. Existing governance applies; unknown checks
remain unknown. Setup and execution need separate exact operator approvals.
It grants no push, PR, report or merge rights and never marks a draft accepted.
Genuine runtime/pilot qualification remains a separately authorized M8 gate.

With the managed engine on PATH, inspect an explicitly selected disposable
project without initializing memory:

```bash
adp init --repo ./project --remote team --memory-branch coordination/state --storage ../project-memory --dry-run
adp discover --repo ./project --remote team --token-env GH_TOKEN
adp plan --snapshot inventory.json
```

Those names are examples selected by the operator, never ADP defaults. Discovery
and planning do not mutate files, memory, Git refs or GitHub resources. Missing
metadata/authority remains UNKNOWN; issue prose never becomes instructions.

## Supported interfaces

| Component | Available behavior | Authority boundary |
| --- | --- | --- |
| [Memory](docs/MEMORY_CLI.md) | init, doctor, status, claim, tasks, immutable inbox, recover, handoff/release | Explicit initialization/write authority and current owner/generation |
| [Progress Guard](docs/GUARD_API.md) | durable counters, finite forensics, diagnostic censuses | Mandatory reservations; no automatic reset/threshold relaxation |
| [External policy](docs/POLICY_API.md) | typed inspect/plan/decide | Target-owned branch/commit/check/review rules; final exact-plan ALLOW |
| [Discovery](docs/DISCOVERY_API.md) | discover, plan, refresh | Read-only observations and independently assessed readiness |
| [Conductor](docs/CONDUCTOR_API.md) | finite run, status, resume, handoff | Explicit trusted controller/operator evidence, qualified runtime/ports |

The signed-provider execution path requires separately authorized v1→v2→v3 memory migrations. An
operator supplies independently verified readiness/policy/evidence services.
The [installed operator profile](docs/operations/OPERATOR_SETUP.md) wires standard
ports without a custom Python controller; the advanced trusted controller remains
available. Developer, Reviewer and Forensic contexts are separate; source changes
invalidate review. Bounded concurrency does not imply a daemon or unattended work.

## Supported-host and backend limits

Memory writes require POSIX locking, atomic replacement, hard links and fsync.
Real Codex execution additionally requires Linux `/proc`, child-subreaper support,
a supported authenticated CLI and trusted OS/authentication installation. Missing
capabilities produce UNSUPPORTED_RUNTIME. A missing stop receipt remains UNKNOWN.

Explicitly selected [#14 GitHub network CAS](docs/operations/NETWORK_CAS.md)
and [#16 product flow](docs/operations/GITHUB_PRODUCT_FLOW.md) extend the original
local bare-remote backend. The target project owns check execution and security;
[#21](docs/operations/PROJECT_VALIDATION.md) verifies its evidence and supplies no
test runner or sandbox. `trusted_disposable=True` remains limited to owned
synthetic projects. Uncertain
external delivery and unfinished old-generation approvals require explicit
reconciliation. #16 supports explicitly delegated native merge within its stated
limits; credentials alone grant no permission. No deployment or release backend
is supplied. This branch's [#22 finite lifecycle](docs/operations/AUTONOMOUS_TRACK.md)
adds accepted track preparation/selection, correction, independent re-review and
next-task refresh. Genuine full lifecycle proof remains NOTRUN, deferred to M8.
Issue #17's installed operator interface on this branch awaits integration acceptance.

## Qualification and contribution

The [M6 report](docs/qualification/M6_REPORT.md) records Q01–Q12, original
inventories, exact tested revisions, evidence hashes and remaining limitations.
It distinguishes synthetic tests, actual installation, historical/fresh real
Codex proof and independent review. Cross-clone simulation does not prove physical
power-loss or real cross-machine behavior.

```bash
python scripts/validate_scaffold.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

See [Contributing](CONTRIBUTING.md), [Security](SECURITY.md),
[Architecture](docs/ARCHITECTURE.md) and [Roadmap](docs/ROADMAP.md).
The [Git workflow](docs/GIT_WORKFLOW.md) governs contributions to ADP Codex only;
target repositories retain their own policies. No existing live product repository
is a qualification target. License/distribution terms, publication, tagging and
integration remain separate operator decisions.
