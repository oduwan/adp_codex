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

Python 3.11+ is required. The engine has no third-party runtime dependencies.
Install into a fresh virtual environment from the explicitly selected source:

```bash
python3.11 -m venv /tmp/adp-example-venv
/tmp/adp-example-venv/bin/python -m pip install .
/tmp/adp-example-venv/bin/adp --help
```

The Python wheel and portable planning plugin are separate installations. The
plugin keeps root `plugin.json`, `skills/` and its referenced documentation together;
see [installation qualification](docs/qualification/INSTALLATION.md). Installing
that read-only skill does not configure a Conductor or grant execution authority.
Versions identify local package metadata, not an authorized public release.

Inspect an explicitly selected disposable project without initializing memory:

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

Execution first requires separately authorized v1→v2→v3 memory migrations. An
operator supplies independently verified readiness/policy/evidence services and a
trusted controller outside product/memory roots. No permissive controller is
included. Developer, Reviewer and Forensic contexts are separate; source changes
invalidate review. Bounded concurrency does not imply a daemon or unattended work.

## Supported-host and backend limits

Memory writes require POSIX locking, atomic replacement, hard links and fsync.
Real Codex execution additionally requires Linux `/proc`, child-subreaper support,
a supported authenticated CLI and trusted OS/authentication installation. Missing
capabilities produce UNSUPPORTED_RUNTIME. A missing stop receipt remains UNKNOWN.

The supplied Git push backend supports explicitly allowlisted local bare remotes
with exact CAS; network push is UNSUPPORTED_ATOMIC_REF. Production validation
needs a separately qualified read-only/network-denied sandbox or port.
`trusted_disposable=True` is limited to owned synthetic projects. Uncertain
external delivery and unfinished old-generation approvals require explicit
reconciliation. No merge, deployment or release execution backend is supplied.

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
