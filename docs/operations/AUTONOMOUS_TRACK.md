# Ticket preparation and bounded autonomous track

Issue #22 supplies the independently reviewable **preparation and admission**
slice permitted by its final dependency clause. Project evidence #21 and GitHub
execution #16 are not accepted dependencies of this source revision. Their full
execution, check/correction/review, Draft PR, merge and reporting integration stays
**BLOCKED_DEPENDENCY**. This document does not claim the complete lifecycle works.

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

READY here means a specification has passed preparation admission. Its packet
still says `execution_authority=UNKNOWN` and names the unavailable integrations.
It cannot launch a worker, run project checks, edit an Issue, create a PR, merge,
post a report or change product files. `execute` and `submit_ticket_changes`
explicitly return BLOCKED_DEPENDENCY. There is no fallback or background process.

The future complete lifecycle remains:

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

Artifacts are at most 1 MiB each; an archive holds at most 64 files and 16 MiB.
Capacity or unsafe paths/links cause refusal, never truncation or deletion of the
authority baseline. Protect and retain the private archive across handoff when its
references are needed. No raw ticket body, credential or diagnostic evidence is
written to product Git or canonical portable memory by this service.

There is no new canonical state version, owner, assignment, progress counter,
effect journal or migration. Accepted M1/M2/M3/M4/M5/M6 and #14 source/contracts
remain unchanged. Restart reads the original and proof but must obtain fresh
observations and verify all current context again. A saved packet is historical
evidence, not reusable execution approval.

Actual ticket submission is unavailable until accepted owner/generation-fenced,
Progress-Guard-reserved, idempotent external-effect integration exists. It must
separately check issue-edit authority and exact live version. Lost responses must
be reobserved rather than blindly resubmitted. This slice supplies no live forge
write transport and does not invent #16's API.

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

Future project merge is permitted only by specific external delegation and fresh
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

The full dependent execution/review/correction, post-PR checks, authorized merge
and reporting cycle is NOTRUN/BLOCKED_DEPENDENCY on #21/#16. A new genuine Codex
Developer-to-Reviewer execution for this dependent cycle is likewise NOTRUN;
synthetic preparation tests do not establish real delegation. Historical M5/M6
runtime evidence remains historical. Do not invoke an unrelated whole-system
campaign to convert this dependency boundary into PASS.
