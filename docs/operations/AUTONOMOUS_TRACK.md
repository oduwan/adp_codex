# Ticket preparation and bounded autonomous track

The preparation/admission slice was accepted through PR #23. Project evidence
#21 and GitHub product flow #16 are accepted dependencies at
`dddffdb5733c77a03d84499f1401aaf7df7f2553` (both post-merge Python jobs passed
356/356 tests). This branch adds the remaining **opt-in finite lifecycle** for
Issue #22; integration acceptance is pending. It adds no project test runner,
CI workflow, sandbox, worktree provisioner, daemon or release authority.

## Implemented preparation flow

`TicketArchive` and `TicketPreparer` implement:

```text
GET-only M4 observation
  -> freeze original ticket/version/identity before interpreting scope
  -> independently authenticate original scope interpretation
  -> classify exact proposed changes and prove scope conservation
  -> authenticate any particular external operator scope addition
  -> refresh actual M4 observations and independently assessed dependency DAG
  -> inspect current authenticated M3 policy and exact repository/ref/source
  -> independently approve the complete preparation subject
  -> retain reconstructible private evidence and bounded Codex packet
```

In the original preparation-only API, READY means a specification has passed preparation admission. Its packet
still says `execution_authority=UNKNOWN` and names the unavailable integrations.
It cannot launch a worker, run project checks, edit an Issue, create a PR, merge,
post a report or change product files. `execute` and `submit_ticket_changes`
explicitly return BLOCKED_DEPENDENCY. There is no fallback or background process.

The explicitly selected lifecycle composes these accepted interfaces:

```text
DISCOVER/REFRESH -> PREPARE -> ADMIT READY -> CODE -> PROJECT CHECKS
 -> CORRECT/RECHECK -> COMMIT -> INDEPENDENT EXACT-SHA REVIEW
 -> (CORRECT/CHECK/COMMIT/RE-REVIEW)* -> ACCEPT
 -> PROJECT-POLICY-GATED MERGE -> ONE PRODUCT UPDATE -> REFRESH
```

## Original authority and scope conservation

The first observed issue for an opaque provider identity is stored without
replacement. Its full normalized M4 issue includes title/body, semantic revision,
timestamps, comments, authors, relationships and repository identity. It remains
reconstructible through an opaque content hash reference. A later edited Issue
cannot replace the original baseline, even if a fresh M4 review calls it READY.

`OriginalScope` identifies the original goal, immutable objective/acceptance/
interface/check/dependency clauses, allowed paths, prescribed check names and
external prerequisites. `PreparationAuthority` must independently authenticate
that interpretation against the actual frozen original. Schema validation and a
matching hash alone cannot establish semantic completeness or scope authority.
No permissive verifier is provided. Issue text and caller-selected labels confer
no authority.

Every `TicketChange` records an exact before/after proposal and one category:

| Category | Admission rule |
| --- | --- |
| IN_SCOPE_CLARIFICATION | Independent proof that explanation preserves original requirements; no hidden new clauses, paths, checks or prerequisites |
| IN_SCOPE_SPLIT | Every original clause appears exactly once in bounded parts, no extra clause, acyclic internal order, independent semantic conservation review |
| OUT_OF_SCOPE_ADDITION | BLOCKED_OPERATOR unless an externally authenticated operator receipt names this original/version, exact change digest and particular added functionality |
| UNKNOWN | BLOCKED_OPERATOR until a concrete scope decision is available |

An addition extends an approved task; it never rewrites the original. Original
clauses are retained unchanged. Broad merge delegation or issue-edit permission
cannot substitute for the particular `ticket/scope-addition` receipt. Approval
does not itself execute or publish the proposed change.

Structural checks cannot understand arbitrary natural-language intent. The
external authority is responsible for canonical principals, independent roles,
original-scope completeness and the actual semantics of each exact diff and
partition. An always-true authority would destroy this boundary. Preparation
reviewers cannot be the named preparer or original issue/comment authors.

## Current track and Codex packet

The service uses the actual accepted `DependencyPlanner`, independently verified
M4 readiness reviews and freshly obtained snapshots. It admits only a unique,
observed READY candidate in the dependency order, with original acceptance still
present and approved prerequisites unchanged. Missing specifications, cycles,
duplicates, unresolved inferred edges, incomplete inventories and stale versions
retain M4's honest classification.

Current M3 inspection must have authenticated sources, no unresolved provenance,
the exact pinned policy digest and matching repository/ref/source SHA. Check
identities come from that project policy, never a language, CI provider or ADP
default. These observations grant no Git operation rights.

`CodexPacket` includes original and prepared issue revisions, repository identity,
base ref/SHA, policy and preparation subjects, immutable original reference,
reconstructible preparation-evidence reference, goal/clauses, allowed edits,
prescribed checks, dependencies/parts, project instruction references and exit
conditions. It is bounded task data, not a system prompt or executable authority.
Credentials-shaped prepared output is refused without echoing the content.

`ready_window` proposes at most eight selected currently READY identities in the
existing M4 order, excluding explicitly consumed identities. It has no scheduler,
task-completion authority or mutable progress registry. Execution integrations
must refresh/revalidate again and use M1 assignments and mandatory M2 permits.

## Durability and compatibility

Private evidence lives in an explicit owned mode0700 directory outside product
and memory roots, with mode0600 regular non-linked files. Original, preparation
proof and packet artifacts are immutable and content addressed. The proof retains
the scope interpretation, full proposed changes, specific operator approvals,
independent preparation review and current track observations; a hash alone is
not used as a replacement for this evidence.

Artifacts are at most 1 MiB each; an archive holds at most 64 artifact files
(plus its lock) and 16 MiB. Freeze preflights both original copies together before
writing either; repeat calls account only for missing files.
Capacity or unsafe paths/links cause refusal, never truncation or deletion of the
authority baseline. Protect and retain the private archive across handoff when its
references are needed. No raw ticket body, credential or diagnostic evidence is
written to product Git or canonical portable memory by this service.

The preparation-only API creates no canonical state version, owner, assignment,
progress counter, effect journal or migration. The opt-in execution extension
below adds bounded fields inside the existing M1 transaction, not a second writer. Accepted M1/M2/M3/M4/M5/M6 and #14 source/contracts
remain unchanged. Restart reads the original and proof but must obtain fresh
observations and verify all current context again. A saved packet is historical
evidence, not reusable execution approval.

Preparation resamples its clock after discovery, policy and external evidence
observations. Discovery, policy claims, the independent readiness/preparation
reviews and any particular scope-addition approval must still be current before
the packet is persisted; entry-time freshness alone is insufficient.
The actual M4 planner rechecks the same frozen observations and reviews at that
time. An expired prerequisite DONE disposition blocks the dependent task; a
changed ordered track cannot reuse the preparation approval. The complete
prerequisite closure remains subject to the final freshness check.

The original `TicketPreparer.submit_ticket_changes()` and `.execute()` methods
remain fail closed for legacy callers. Explicitly installed `TicketPublisher`
and `AutonomousTrack` supply execution; a saved packet never selects them.

## Project checks, merge and product reporting boundaries

The project owns its language, tools, CI, runtime and security. ADP may observe or
request only prescribed, authorized checks through accepted #21; it does not add
CI YAML, runners, containers, test suites or integration campaigns. Ordinary
within-ticket FAIL/ERROR and reviewer rejection are corrective development work
under existing M2 attempt/time/resource bounds, not automatic operator stops.

Missing authority, scope additions without approval, unsafe or uncertain effects,
irreconcilable evidence, unavailable required capabilities and exhausted guard
limits remain stops. This preparation slice cannot reset counters or accept a
failed check, stale SHA or mock Reviewer as success.

Project merge is permitted only by specific external delegation and fresh
exact-SHA checks/review/protection gates through accepted #16. This feature does
not authorize merging ADP contributor PRs, live target work, release or deployment.
Issue edits, dependency edits, closure and labels each require appropriate project
delegation. A project report is at most one substantive completed-iteration outcome;
internal harness, retries, agent handoffs and debug evidence remain private.

## Qualification

The focused committed `AUTONOMOUS_TRACK_TEST_INVENTORY.json` covers the original
Issue #22 preparation positives and adversarial cases with two disposable Git
projects and explicitly synthetic GitHub/policy authorities. It is exercised by
the existing M7 runner; no new CI workflow or integration campaign is added.
Accepted 210 M1–M6 tests and 48 #14/M7 accounting tests retain their inventories.

The additional frozen `AUTONOMOUS_LIFECYCLE_TEST_INVENTORY.json` contains 44
focused methods for the remaining lifecycle. The original 356 methods and their
inventories are retained unchanged: 210 M1–M6 and 146 accepted M7 methods. The
existing Python 3.11/3.12 workflow runs the combined 400-method denominator and
six installation cases. Actual results and independent review belong to the
exact PR HEAD; synthetic ports do not prove genuine Codex or live GitHub writes.

## Explicit controller and state machine

A trusted external controller selects `Controller(conductor, (), track=track)`.
`AutonomousTrack` requires the actual `Conductor`, a `TrackWindow` and typed
`TaskSpec`s. A spec selects an existing isolated workspace, actual
`TicketPreparer`, independent assessment callback, packet-to-`Admission` factory,
project `ProjectValidation` factory, #16 delegation factory and preparation
policy factory. The same project supplies all authenticated M3/M4/M2 evidence;
there is no permissive authority or issue-text-based adapter loader.

`assess(original, track, inspection)` returns `PreparationInputs`: the existing
original scope, exact proposal, independent review, any specific external scope
approvals and exact existing native-edge edits. It must analyze the complete
retained original. An assessment service is not a worker and is not granted
permission to implement unapproved additions. The admission's goal, paths,
acceptance and M2 prerequisites must exactly conserve the resulting packet.

The coordinator refreshes actual M4, freezes the first original, separately
checks the task-local checkout/DAG, and holds those snapshots for the exact
independent preparation subject. It then reobserves live M4 before actual M5
admission/dispatch. Ticket effects always observe the **live** M4 service; frozen
preparation snapshots cannot masquerade as fresh effect observations.

```text
PREPARING -> independently READY -> actual M1 assignment + M2 permit
 -> DEVELOPER -> prescribed project evidence -> COMMIT -> REVIEWER
     ^              | ordinary FAIL/ERROR           | rejection
     +--------------+------------------------------+
 -> #16 exact-SHA acceptance / Draft PR / pending project CI
 -> explicitly delegated merge or human approval wait -> one product outcome
 -> fresh independently observed DONE -> next independently READY task
```

`TaskLifecycle` supplies hooks to the existing M5 worker/commit/review methods,
not an alternate worker executor. Worker requests name the original clauses,
project instruction references, exact source, acceptance IDs and actual feedback.
They do not impose Python or a universal test command. Every correction gets
fresh project authority; every new commit invalidates prior review/check gates.
Ordinary failed checks and rejected reviews continue through these same methods,
including mandatory M2 forensic reassessment when its unchanged thresholds fire.
Optional correction progress requires independently authenticated M2 cause-chain
proof; changed bytes or PASS alone do not reset counters.

## Project validation timing and candidate evidence

The project explicitly chooses one sequence:

| Mode | Prescribed sequence |
| --- | --- |
| CANDIDATE | project-attested checked candidate content/index/worktree -> stage/commit -> exact committed-SHA Reviewer and #16 committed-SHA gates |
| COMMITTED | policy commit -> project checks of that exact SHA -> independent Reviewer -> #16 gates |
| POST_PR | policy commit/review -> authorized Draft PR -> pending current exact-SHA project evidence; FAIL returns to correction/re-review |

A project whose prescribed checks require a committed SHA selects COMMITTED;
POST_PR does not invent pre-PR checks. CANDIDATE requires a separately supported
project-owned observer/action. Native GitHub check records alone cannot attest
dirty content. Separate `CandidateEvidenceRequest`, query/result/gate and M3
request/plan variants bind base SHA **and** actual content/index/worktree hashes.
They cannot deserialize as, or satisfy, accepted committed-SHA #21/#16 gates.
There is no conversion of a dirty PASS into a commit PASS. The pre-commit gate
also verifies every staged blob/mode, content, freshness and current project
policy. Hidden index flags, unexpected files or content drift refuse execution,
including the no-change review path.

Project actions remain separately authorized through #21 `request_action` and
the actual reserved M1/M2 context. A pending/lost action is reobserved using its
retained request and original key/observation budget under a fresh independently
verified policy bridge. An actual NOT_REQUESTED action may be requested once
following a pre-action crash. SUBMITTED/RETURNED delivery is never retried or
silently rebound to another SHA/generation. Complete FAIL/PENDING evidence is
replayed exactly when finishing an interrupted immutable M1/M2 delivery; a newer
observation cannot contradict that same accepted result.

## Finite windows, restart and handoff

Explicit migration: `adp execution-upgrade --authorize-memory-write
--track-lifecycle` (after accepted M2 upgrade). This selects the existing outer
state-v3 and internal execution-v2 product fields, then internal execution-v3
`track`, `lifecycles`, `ticket_effects`. No M1 task or M2 record is rewritten.
Legacy internal-v1/v2 readers/writers remain supported. Reads never migrate.
#21 private request retention is explicitly selected v2 for lifecycle actions;
legacy v1 bytes/subjects stay unchanged. Missing old intent payloads require
external reconciliation, never an inferred successful migration.

A window binds one exact repository/configuration/generation, explicit issue
identities and distinct existing workspaces. It lasts at most one hour, admits
at most eight tasks/four lanes and has at most 32 total rounds across restarts;
one foreground invocation consumes at most four rounds. Existing M1 journal,
eight-jobs-per-task, 32 combined effects, eight reports, private evidence and M2
limits remain enforced and may stop a smaller practical window. No implicit
budget renewal, archival, branch creation or worktree provisioning is performed.

`run` and `resume` use the actual invocation lock and Conductor. `resume` first
uses actual M1 recovery; current slots restore immutable packets/admissions.
Consumed identities cannot alias a new task or workspace. Pending project CI and
human approval wait once per invocation, with independently READY work still
eligible. Local completion/merge receipts do not mark prerequisites DONE: actual
M4 independent disposition must do so. Incomplete inventories stop advancement.

`status` inspects state without discovery, claiming, migration or dispatch; runtime
liveness is explicitly UNKNOWN. Any Conductor UNKNOWN stop and its unconfirmed
contexts remain UNKNOWN through the track wrapper. No stopped-background claim
is fabricated. Handoff refuses unconfirmed workers/network effects, unresolved
project/ticket actions, dirty/unpublished source or missing private evidence.
After a confirmed M1 handoff and new claim, `adopt_generation(authorized=True)`
requires fresh exact external authority for the **same** configuration/deadline
and remaining counters, all old assignments/effects reconciled and private
history present. Unfinished acceptance/check/review grants are invalidated and
must be freshly qualified. Completed product/ticket history stays historical.

## Authorized existing-ticket publication

`TicketPublisher` reuses actual M1 ownership/assignments, M2 bounded reservations,
M3 `Operation.TICKET_EDIT`, exact private diff references, one-use dispatch claims
and #14 supervised fixed-origin transport/stop fencing. It supports existing
issue TITLE/BODY PATCH and existing native blocked-by POST/DELETE. Dependency
node/database IDs are independently reobserved and must match the approved
original or specifically approved dependency meaning. It creates no issue, label,
closure, arbitrary route or new implementation obligation.

Native GitHub issue edits/dependency endpoints provide no atomic version CAS.
The only supported envelope is separately authenticated **OBSERVED_VERSION**:
complete live GET/version compare, current exact M3 operation authority and
separate `ticket/edit` plus `ticket/observed-version` assent immediately before
one dispatch. ATOMIC_VERSION requirements fail closed before a write. A token's
repository scope is not edit authority. `GitHubTicketHTTPTransport` requires a
verified one-repository installation token restricted to issues:write and
metadata:read; no credentials enter argv, portable state or product reports.

Multi-effect bundles are not atomic transactions. Each canonical effect retains
its exact reconstructible private proposal and generation-fenced intent before
submission. A stopped/lost response is reobserved, never blindly retried. Durable
canonical intents are reconciled **before** refreshed ticket preparation, so a
new issue revision/bundle cannot hide an old uncertain write. Immutable inbox
replay finishes interrupted M1 acceptance without duplicate delivery. Unknown
transport liveness blocks all further effects/handoff. Actual M2 preparation
stops remain binding on later ticket writes **and product admission**. A complete
fresh independently approved DAG/packet is still required after a partial or
complete edit bundle; no rollback or atomic-bundle guarantee is invented.

## Native GitHub and qualification limits

All PR/check/merge/report effects go through accepted #16. Its supported native
merge/squash envelope remains HEAD_ATOMIC_BASE_OBSERVED, not atomic base CAS.
Queues/stacked PRs, rebase, ff_only and automatic PR readiness transitions remain
unsupported. Draft readiness requires a separately authorized project actor;
human-required merge waits at WAITING_HUMAN_APPROVAL. No actual target GitHub
mutation, M8 pilot, live product change, issue closure, release or deployment is
authorized by this contributor implementation. Public release stays NOT_AUTHORIZED.

An accepted M2 constraint limits owner handoff after a source SHA has already
been code-approved but the iteration is unfinished. M2 de-duplicates
CORRECTION_APPROVED by SHA and binds approval to owner generation. This adapter
cannot renew that old fact for a new generation without changing the accepted
M2 contract. It refuses that handoff/adoption as
UNSUPPORTED_CURRENT_CONTEXT_REAPPROVAL before release; finish the iteration under
the current owner. A direct externally forced owner change at that point needs a
separate operator/M2 contract decision. No counter/fact reset or cosmetic commit
is manufactured. Same-generation independent re-review of unchanged source may
use the still-current approval context, but counts no new M2 progress/reset.
New commits always require new independent exact-SHA review.

The current binary supports legacy execution-v1/v2 plus opt-in v3; an older
binary must refuse the new closed schema. This is not reverse readability by
an older installed package. Preserve private original, preparation, check/action
and transport-stop evidence when transferring a qualified state.
