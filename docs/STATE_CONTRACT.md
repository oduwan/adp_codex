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
