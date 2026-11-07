# Git workflow and commit policy — ADP Codex

**Status: binding contributor policy for `oduwan/adp_codex`.** This is an *external project policy* for developing ADP Codex. The future ADP engine must **not** impose this policy on repositories it manages; each target repository supplies its own workflow provider.

## Branch and worktree discipline

- Before coding, fetch and inspect the current remote `main` HEAD and confirm the selected issue's prerequisites. Use a clean, **isolated** issue worktree. Never reset, clean, stash, or overwrite another contributor's working tree.
- **One coherent issue per branch and Draft PR.** Name branches `feature/<issue>-<slug>` for features, `fix/<issue>-<slug>` for fixes, or `docs/<issue>-<slug>` for documentation. Example for [Issue #1](https://github.com/oduwan/adp_codex/issues/1): `feature/1-portable-memory`.
- The PR base is `main`. Do not commit directly to `main`, use `main` as a scratch branch, or retarget a PR to avoid acceptance rules.
- No force-push, `git push --force-with-lease`, history rewrite, destructive reset, or amendment of already-pushed commits without a separate operator decision. If the base has moved, inspect the actual diff and conflicts before selecting a non-destructive integration strategy.
- Normal push is authorized **only** for an explicitly assigned issue/branch and its Draft PR. PR merge, issue closure, release and deployment require separate authority.

## Commit messages — Conventional Commits

Use an English subject in this form:

```text
<type>(<scope>): <imperative summary>

[Why the change is needed, when useful]

Refs #<issue-number>
```

Accepted types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`, `perf`. Use a concise lowercase scope such as `memory`, `cli`, `guard`, `policy`, `discovery`, `runner` or `docs` (the scope is descriptive, not a hard-coded implementation enum).

- Subject: present-tense imperative, no trailing period, ideally 50 characters and **at most 72 characters**.
- Each commit must be meaningful and reviewable. Keep unrelated work out of the commit and PR. Include the test or documentation changes needed to explain the behavior.
- Use `Refs #N` in the commit body for traceability. Avoid `Closes #N` / `Fixes #N` in an intermediate commit; use `Closes #N` in the final PR description when the PR actually resolves the complete issue.
- Configure and inspect `user.name` and `user.email` before the first commit. Use an approved public or project-safe identity; never allow a hostname-derived automatic identity or expose private usernames, machine paths or tokens. Do not forge a co-author or reviewer.
- Never commit raw test evidence, logs, secrets, .env files, virtual environments, local ADP runtime memory or production data.

Example:

```text
feat(memory): add revision-fenced state checkpoints

Persist compact task records with atomic replacement and reject a
divergent remote head before the next state mutation.

Refs #1
```

## Draft PR, review and acceptance

1. Open **one Draft PR** against `main` linked to the issue. Use the repository PR template; include purpose, exact HEAD, changed files, testing and known limitations. A Draft PR may contain intermediate scoped commits without claiming acceptance.
2. Run relevant focused tests plus directly affected regressions, and the required scaffold checks. Record actual PASS/FAIL/ERROR/SKIP/NOTRUN rather than treating exclusions as success.
3. Request **independent** review of the final exact PR HEAD, including scope, safety, accepted requirements and evidence. The author cannot be the approving reviewer. Any commit after approval invalidates it.
4. After tests and review pass, leave the PR for separately authorized merge. Neither a green CI run, an issue description, nor a completed Codex response grants permission to merge or deploy.
5. Keep GitHub progress **product-focused**. Internal harness corrections, worker handoffs, Progress Guard records and diagnostic chatter stay local; the Conductor may publish one concise meaningful product summary per completed iteration.

## Conflict resolution

The selected issue and this repository policy govern development **in this repository**. If an operator instruction or branch protection conflicts with a proposed step, do not guess: report the precise conflict and seek authorized resolution. Hard safety/ownership/review invariants remain mandatory. Target-repository policy is always discovered independently and cannot be overridden by this file.
