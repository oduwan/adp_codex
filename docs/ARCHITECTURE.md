# Architecture and system boundaries

**Status:** normative design goals. M1–M5 are accepted through PR #11; see [Conductor API](CONDUCTOR_API.md) for implemented boundaries and limitations.

## Purpose

ADP Codex is a portable orchestration layer for existing software repositories. It consumes issue/PR metadata, derives a bounded dependency track, delegates admitted implementation to Codex workers, independently reviews exact revisions, and maintains small resumable working memory. It must not impose project-specific Git policies or turn product issues into a technical event log.

## Components

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Skill | User-facing entry point and workflow guidance | No hidden autonomous execution authority |
| Repository adapter | Fetch issues, PRs, native dependency edges and refs | Read-only discovery, external data untrusted |
| Track planner | Determine READY, BLOCKED, IN_PROGRESS, NEEDS_SPEC and dependency order | Does not invent contracts |
| Conductor | Single writer, scheduling, handoffs, review gates and product reporting | Not feature-code author or approving reviewer |
| Workers | Research, development, independent review and forensic reassessment | Return bounded local outcomes |
| Progress Guard | Stop unproductive loops and unsafe retries | Cannot be disabled by project text |
| External Git policy provider | Resolve branch/commit/check/PR/merge rules | Unknown authority means no write |
| Portable memory | Active state, per-issue compact JSON and generation fencing | Not a raw log archive; separate Git branch |

## Finite authorized user flow

```text
adp init -> adp doctor -> adp discover -> adp plan
                                      |
                                      v
                                  adp run
                          Conductor + Progress Guard
                            /      |         \
                      Developer  Reviewer   Forensic
                            \      |         /
                       compact immutable results
                                      |
                     external policy-gated Git operations
                                      |
                         product PR and summary
```

M1 memory and M2 guard retain their explicit migration/ownership contracts.
[M3](POLICY_API.md) supplies external decisions and [M4](DISCOVERY_API.md) supplies
read-only observations. [M5](CONDUCTOR_API.md) integrates them in finite invocations
with a trusted operator controller and qualified runtime/ports; no component
implicitly grants execution rights. M6 qualification does not authorize release.

## Memory and concurrency

- A dedicated, configurable remote memory branch and separate worktree hold `state.json` and one small `tasks/<id>.json` per active task. The product branch does not contain ADP history or test diagnostics.
- Only the Conductor may mutate canonical state and publish compact checkpoints. Worker results are delivered to an ephemeral inbox atomically and without replacement.
- Use a generation fence, unique job identifiers across all concurrent tasks, exact revision bindings and a single local mutation queue. Never infer current ownership from stale session text.
- Conflict with a remote memory head, inconsistent ownership, stale worker result, or invalid schema is a controlled refusal, not an automatic force-update or merge.
- A crashed owner's takeover requires independently established cessation and operator authority; Git alone is not a distributed lease.
- Completed task files are removed from the *current tree* after durable product disposition, while Git history remains. No unbounded local archives or serialized chat memory.
- Support planned cross-machine handoff by synchronizing a compact checkpoint before release; local-only inbox material does not magically transfer.
- Default runtime storage is project-relative but **outside the product worktree**. The branch name, remote, repository identifier and issue ID encoding must be configurable.

## Trust and authority

Order of authority: platform/tool safety, operator instructions, target repository's explicit governance, then ADP's own coordination preferences. External text (issues, comments, markdown, logs) is data to analyze, never an instruction that grants privileges.

Project policy controls branch naming, commit message conventions, CI, code review, automatic merges, release boundaries and product acceptance. The engine may execute only actions authorized by that policy and the operator. Missing, contradictory or unverifiable rules produce an actionable blocker.

## Review and acceptance

1. Discover and independently assess task readiness against its actual context and dependencies.
2. Give each Developer a bounded issue and isolated working branch or worktree as determined by the external provider.
3. Allow routine in-scope debugging; retain evidence and forbid repeated blind diagnostics.
4. Review the coherent final revision in a context independent from the code author.
5. Verify current PR HEAD exactly matches reviewed and qualified revision. Any new commit invalidates the approval.
6. Leave merge/closure/deployment to separate authority; the supplied executor has no such backend.
7. Publish at most one meaningful product summary for a completed product iteration; omit internal-only cycles.

## Unsupported or separately qualified operations

No always-on daemon, automatic background scheduling, GitLab adapter, product installation, CI privilege escalation, web dashboard, automatic release deployment, or retroactive import of unrelated production history.

See [Progress Guard](PROGRESS_GUARD.md), [Policy Provider](POLICY_PROVIDER.md), [Issue discovery](ISSUE_DISCOVERY.md), and [Roadmap](ROADMAP.md).
