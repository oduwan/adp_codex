# Portable memory CLI and API

M1 portable memory is accepted on `main`, which remains non-autonomous.
Discovery, policy decisions and worker execution remain unavailable. Issue #2
adds a separate [Progress Guard candidate and explicit upgrade](GUARD_API.md). Python 3.11+ and Git are required. The runtime uses only
the Python standard library.

## Configuration and identity

Install with `python -m pip install .`. An importable `adp` package and an `adp`
entry point are provided. Configuration is discovered at the selected Git
worktree root in `.adp.json`, or selected with `--config`. Explicit command-line
values override configuration:

```json
{
  "schema_version": 1,
  "remote": "team",
  "repository_id": "forge:project/opaque",
  "memory_branch": "coordination/current",
  "storage": "../project-memory"
}
```

Repository selection uses `--repo` (default current directory). With more than
one remote, select one explicitly. Fetch and push endpoints must match exactly.
The default repository identity is a SHA-256 digest of the normalized endpoint;
provide a shared explicit identity when machines use different endpoint aliases.
Neither a remote name, product branch, forge nor numeric issue syntax is assumed.
The branch `adp/state` is a suggestion only: both branch and external storage
must be selected. Relative storage resolves against the product worktree root.
All configuration and storage ancestors must be free of symlinks, and memory
must not overlap any product worktree or Git administrative directory.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Successful operation or healthy read-only inspection |
| 2 | Usage, missing/ambiguous configuration or unsafe author identity |
| 3 | Invalid schema, unsafe path, unexpected files or storage corruption |
| 4 | Ownership, generation, revision or remote-head conflict |
| 5 | Git/transport/authentication failure; pending writes need inspection |
| 6 | Explicit memory-write authorization missing |

Errors are controlled refusals with human-readable explanations. No external
product action is authorized by a successful memory command.

## Initialization, inspection and ownership

All repository options follow the subcommand. Example using a disposable target:

```bash
adp init --dry-run --repo ./project --remote team \
  --memory-branch coordination/current --storage ../project-memory
adp init --apply --authorize-memory-write --repo ./project --remote team \
  --memory-branch coordination/current --storage ../project-memory
```

Use the same options for subsequent commands, or an external configuration file.
Dry-run never writes a configuration file. It reports missing selections, external
write authority and authentication uncertainty. `doctor` and `status` also never
fetch, refresh the index, create a lock/token/worktree or change refs. `doctor`
checks explicit Git author identity and cleanliness of all product worktrees.
Remote read access is checked using `ls-remote`; push permission remains UNKNOWN
until an authorized push is observed. No forge API is called by any M1 command.

`status`/`doctor` return 0 for synchronized memory and 4 for uninitialized,
remote-only, dirty, pending or mismatched memory. Unsafe schemas/paths return 3.
`init --dry-run` returns 0 for a successful proposal, even with missing decisions.
`init --apply` validates before creating only the selected memory branch/worktree.
Repeat initialization reuses a clean identical checkpoint; mismatches are refused.
Set an explicit project-safe `git config user.name` and `user.email` first.

`claim --owner public-label` establishes ownership and advances the generation.
An existing owner cannot be inferred from Git or a session label. A missing local
credential is a refusal. Exceptional `claim --takeover
--confirm-stopped-owner OWNER_ID` is an operator attestation that the named owner
has ceased; Git cannot establish cessation independently. `handoff` (alias
`release`) publishes release only after all local deliveries are processed.
Initialize the second clone with matching repository identity/branch, then claim.
Use `recover` to explicitly synchronize a previously initialized clone.

## Compact task/result API

```python
from pathlib import Path
from adp.config import Config
from adp.memory import Memory

config = Config.discover(Path("project"), remote="team",
    branch="coordination/current", storage=Path("../project-memory"))
memory = Memory(config)
memory.initialize(authorized=True)  # requires actual operator authority
memory.claim("public-conductor-label")
memory.add_task("forge:opaque/task-A", source_revision="a" * 40)
assignment = memory.assign("forge:opaque/task-A", "worker-label")
envelope = {"schema_version": 1, **assignment, "result": {
    "outcome": "FAIL", "summary": "Observed synthetic assertion failure",
    "evidence": ["fixture:case-A"]}}
memory.deliver(envelope)             # worker: ignored local inbox only
memory.accept(assignment["assignment_id"])  # owner: canonical checkpoint
```

`task-add ID --revision SHA`, `task-revision ID SHA`, `assign ID --worker LABEL`,
`deliver RESULT_JSON`, and `accept ASSIGNMENT_ID` expose the same API. They do not
execute a worker or verify the source revision externally. Revision changes mark
unfinished assignments incomplete; accepted historical results remain unchanged.
The assignment counter is global and does not reset when tasks are retired.

`task-retire ID --evidence REF --confirm-disposition` requires an operator-observed
durable disposition; it removes only that current task. This command does not
close an issue. M1 does not independently query an external forge.

## Interrupted operations

`recover` validates the exact local journal, owner credential and remote parent,
then finishes the pending commit/push, or fast-forwards a clean synchronized clone.
It never invents credentials, rebases or reconciles divergent histories. A failed
push leaves a pending local checkpoint, not a claim of published success. If an
acceptance was pushed before inbox cleanup was interrupted, `cleanup-inbox`
removes only byte-equivalent accepted results. A malformed or stale delivery can
be explicitly removed by `discard-inbox ID --confirm-incomplete`; this local
acknowledgement accepts no result and grants no canonical ownership.

For divergence or dirty files without a validated journal, stop all writers and
inspect the two histories before an operator chooses reconciliation. Retain the
local checkpoint as evidence; do not repeatedly retry or force-push.

See [the state contract](STATE_CONTRACT.md) for exact fields, size caps, schema
semantics, durability boundaries and filesystem/platform limits. Public labels,
results and references must contain no secrets or raw diagnostic traces.

## Qualification scope

The synthetic suite uses local bare remotes, two independent clones with different
remote names, non-default product branches, opaque task IDs and disposable memory
worktrees. It covers first/repeat initialization, real server-side push rejection,
interruption before commit and after commit/before push, divergence, missing local
credentials, confirmed takeover, exact generation/revision checks, immutable
results, global assignment IDs, threads/processes, cleanup and negative schemas.
Read-only checks compare files, directories, metadata and all local/remote Git refs;
the CLI test also allowlists observational Git operations. No live forge is used.

Run the same checks as CI on Python 3.11 or 3.12:

```bash
python -m pip install .
adp --help
python scripts/validate_scaffold.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

Actual qualification results, exact tested/reviewed SHA, failed attempts and
remaining limitations belong in the scoped Draft PR. A successful test run does
not authorize integration, issue closure or autonomous execution.
