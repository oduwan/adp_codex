# Portable working memory — proposed v1 state contract

**Status:** design contract. The initial repository does not implement Git-backed memory.

## Physical layout

One configurable Git branch dedicated to small ADP state, in a separate worktree from the product:

```text
adp-memory-worktree/
  state.json              one Conductor-owned registry
  tasks/<stable-id>.json  one compact record per active task
  inbox/                  ignored immutable local delivery files (not portable)
```

`state.json` includes schema version, revision, owner identity, generation and an ordered list of active task IDs. Task entries identify repository, issue ID, iteration, phase, current exact source revision or null, worker assignments, blockers, accepted outcomes and the last published product iteration.

The default storage branch may be `adp/state` but cannot be hard-coded into the portable engine. The memory worktree need not live inside the product checkout. A product repository with multiple remotes or non-GitHub origins requires explicit repository selection.

## Mutation contract

- Only one Conductor owns canonical write authority; all canonical mutation operations are serialized.
- Each update is validated, written atomically, committed and pushed with a remote-head precondition. A divergent remote head is a refusal, not an automatic rebase or force-push.
- Workers deliver bounded immutable job results by no-replace atomic writes to ignored local inbox paths. A job ID must be unique across all active tasks.
- Assignments and results bind generation, stable task ID, worker identity and exact source revision. Stale generation, mismatched SHA or duplicate terminal results must never advance the task.
- An independent review approval becomes invalid on any subsequent source change.
- Local-only inbox results must be processed before a voluntary machine handoff; if the old environment is destroyed, lost results remain honestly incomplete.
- Conductor ownership is not proven by Git fast-forward rules alone. An exceptional takeover requires an explicit operator confirmation that the prior owner has stopped.
- Retirement removes a task from the **current tree**, only after verified terminal disposition. Git history is not rewritten as a garbage-collection scheme.

## Recoverability

The new Conductor reconstructs live work from the synced state, then revalidates remote issue and PR refs, accepted policies and nonexpired assignments. A checkpoint is a statement about coordination, not proof that an external command completed. External mutations require idempotency keys and observation of actual remote outcomes to prevent duplicate issue comments or PR actions after interruption.

## Limits

Implement strict size caps, schema/version checks, path validation, symlink refusal, no secrets or raw traces in remote memory, and bounded disk use. Prefer short current-state descriptions and references to durable product evidence over growing archives. A portable working memory is **not** a full event log, backup service or permission broker.

## M1 v1 implementation candidate

Issue #1 adds an implementation candidate in `adp.memory.Memory` and
`adp.schema`; acceptance still requires exact-revision independent review and
separate integration. See [CLI and API](MEMORY_CLI.md) for operation and exit codes.
No issue, PR, product-code execution or external outcome is performed by these APIs.

### Exact schema and bounds

Unknown fields, duplicate JSON keys, non-finite numbers, booleans as integers,
unsupported versions, special files and symlinks are refused. Integers are below
10^18. Each JSON canonical file is at most 64 KiB; there are at most 64 active tasks
and 128 assignments across them. Compact strings exclude control characters.

`state.json` fields are `schema_version` (1), `repository_id` (opaque string),
`revision` (positive checkpoint counter), `generation` (ownership fence),
`owner` (null or `{id,label,token_hash}`), sorted unique `task_keys`, and
`assignment_sequence` (monotonic across retirement and handoff). The credential
itself stays local under Git administrative data. Owner labels are operator-chosen
public identifiers, not inferred machine identities. Credentials prevent accidental
cross-session ownership; they do not defend against an attacker controlling the
same OS account or Git administration.

Task filenames are the SHA-256 digest of the opaque UTF-8 task ID, never the ID
itself. Each task has `schema_version`, `key`, `id`, `repository_id`, `iteration`,
`phase` (`active`), `source_revision` (full Git object ID or null), `assignments`,
`blockers` (up to eight 512-character strings), and `last_published_iteration`
(always null in M1). Issue IDs can be nonnumeric and include path-like text.

Assignment IDs are generated as `<generation>-<global-sequence>`; callers cannot
reuse an ID. Each assignment contains `generation`, `worker`, `source_revision`,
`status` (`pending`, `accepted`, `incomplete`) and `result` (null unless accepted).
An accepted result contains `outcome` (`PASS`, `FAIL`, `ERROR`, `SKIP`, `UNKNOWN`),
`summary` (up to 2048 characters), and `evidence` (up to eight 512-character
references). Outcomes are observations, not verified external product dispositions
or independent approval gates. Accepted jobs are immutable even after source drift.
Consumers must check their exact revision; an old PASS is never current approval.

An inbox envelope contains `schema_version`, `task_key`, `assignment_id`,
`generation`, `worker`, `source_revision`, `result`. At most 128 local delivery
files of 16 KiB each are allowed; filenames hash the assignment ID. Delivery uses
an atomic hard-link without replacement. It cannot update canonical state.
Only the owning Conductor can accept a matching pending assignment.

### Transactions, recovery and handoff

Every canonical writer holds an OS-backed local advisory lock shared by linked
worktrees. A bounded, atomically replaced local `pending.json` records the complete
next checkpoint and its exact parent before touching canonical files. Individual
JSON files use fsync and atomic replacement; a commit is the portable transaction
boundary. Recovery validates and completes that same transaction without inventing
an owner or rewriting a terminal job. The local journal is deleted only after
remote publication is observed. Dirty files without a matching journal require
operator inspection; arbitrary uncommitted changes are never silently adopted.

A normal explicit-ref push follows a remote-head check. Competing sibling commits
are rejected by Git; no force, rebase or automatic divergent merge is used. Git
fast-forward rules are not a distributed lease or proof of prior-owner cessation.
A takeover needs an explicit confirmation naming the observed prior owner ID.
Concurrent deletion/recreation by an external Git administrator is outside this
coordination protocol; stop all owners and reconcile manually after such changes.

`recover` may also fast-forward a clean local memory worktree to a validated
remote checkpoint. Divergence, missing owner credentials, stranded inbox results
and a deleted owned memory branch are controlled refusals. A failed initial push
of the pristine unowned root checkpoint can be explicitly republished.

Voluntary release/handoff requires an empty local inbox and a synchronized remote.
It marks pending assignments incomplete and releases ownership. The next clone
initializes its own worktree and claims a new generation. A confirmed takeover
also invalidates unfinished assignments. Lost or discarded results stay incomplete;
no external side effect is inferred from a checkpoint. Stale deliveries require an
explicit local discard acknowledgement and are never silently accepted.

Retirement requires operator confirmation of an observed durable disposition and
a compact evidence reference, with no pending assignment or inbox. M1 has no forge
adapter to independently verify that observation. The retired task leaves the
current tree and remains in normal Git history. There is no raw-log archive or
history rewrite. Current assignment/file bounds fail closed when exhausted.

The implementation requires a POSIX filesystem with `flock`, atomic rename,
hard links and directory fsync. Unsupported platforms fail closed for writes.
Read-only inspection does not acquire locks or fetch. Hostile same-user concurrent
filesystem replacement is outside the isolation model; use OS access controls.
