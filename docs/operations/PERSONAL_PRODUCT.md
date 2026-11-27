# Personal single-Issue product flow — M10-B

Issue #41 composes the actual M7 forge/CAS, #21 native evidence and M1/M2/M3
with personal enrollment and #40 publication. No second GitHub backend,
external trust service, manual JSON, CI runner, workflow dispatch or sandbox is
added. M10-B is accepted at `b93d592909315bf952343fca82591d1fbca77feb`.
The separately selected [#42 track](PERSONAL_TRACK.md) extends its operator flow;
this one-Issue port alone grants no reporting or next-task rights.
Genuine M8 remains **NOTRUN**.

## Operator sequence

Use the managed launcher and the original project/private directory. Both
`adp personal` and `adp codex … --personal` expose these steps. Every command
needs `--repo ABSOLUTE_PROJECT --remote SELECTED_REMOTE --directory ORIGINAL`.

1. `pr-preview --title 'Selected product title' --body 'Approved product text'`
   shows the original issue/repository, published reviewed SHA/tree, feature,
   base SHA, policy, text, ownership checkpoint, expiry and quiescence warrant.
2. Separately confirm `pr-create` with the same text, returned `--reviewed`
   token, `--authorize-pr --authorize-memory-write --confirm-project-rules
   --assume-administrative-quiescence`. Memory approval explicitly selects the
   accepted internal execution v1→v2 migration. Reads never migrate.
3. `ci-preview`, then `check-ci --reviewed TOKEN --authorize-execution`, observes
   project checks. Show any selected `--accept-native-job-records` in both calls;
   it accepts actual job records with unknown counts, not invented test counts
   or Actions attempt IDs. Original selected and native required checks apply.
4. `product-preview --for-operation review`, then `product-resume
   --for-operation review --reviewed TOKEN --authorize-execution`, obtains a
   distinct actual independent Codex product judgment at the committed SHA,
   complete original scope and current project evidence.
5. `merge-preview --merge-method merge` defaults to `WAITING_HUMAN_APPROVAL`.
   A proposal with `--delegate-merge` alone grants no authority. Executing an
   explicitly delegated proposal needs its distinct `--reviewed` token and
   `--authorize-merge --delegate-merge --authorize-memory-write
   --confirm-project-rules --assume-administrative-quiescence
   --accept-head-atomic-base-observed`, with the same method.
6. `product-status --merge-method merge` verifies actual PR/result identity,
   parents and tree. It distinguishes an externally/manual merged result from
   a recorded delegated effect. Native actor identity does not prove who
   physically operated a UI. No report, issue closure or next task follows.

Setup/run/push consent cannot authorize PR or merge. Closing directives in PR
text and merge-triggering commit messages are refused: issue closure belongs to
separate authority. No issue text or returned instruction becomes an operand.

## Policy, project checks and independent review

Present committed governance and positively observed native policy apply.
403/UNKNOWN is never absence. Unknown rules, code-owner/actor-specific review
obligations, queues or unrepresented constraints block the affected operation.
Native approvals require exact current SHA, non-authorship and actual eligible
collaborator permissions; Codex does not fabricate GitHub approvals.

Empty names with UNKNOWN governance stay UNKNOWN. Verified absent requirements
produce `NOT_REQUIRED`, never a fabricated zero-test PASS. An operator who has
actually interpreted current governance as adding no checks can explicitly
select `--confirm-no-required-checks` in the CI proposal/action. That records
the exact interpretation, cannot waive native conditions and remains subject
to independent product review. Workflow YAML alone prescribes no status.

#21 receives the actual opaque PR node ID; the forge retains its separate REST
ID from the same verified detail. Current SHA/repository/PR/origin, run identity,
completeness, timestamps and unknown denominators are preserved. PENDING, FAIL,
ERROR, SKIP, TIMEOUT, CANCELLED, UNKNOWN, missing, stale, partial and foreign
records cannot merge. Native identity attempts consume the same original
observation before their first read. Missing, ambiguous or unavailable origins
retain UNKNOWN and close that exact M2 attempt; no policy/result is invented.
Saved live permits are validated before reads. Lost delivery never restarts the
observation; a saved accounted result reconciles locally without another HTTP
request, charge or begin. Counter checkpoints recover the same original charge.
Native evidence is freshly observed again before merge,
charged to the original aggregate observation cap. Changed native result
identities invalidate review; a new nonce for identical results invents none.
ADP never executes or changes target CI.

## Bounded correction and durable recovery

Actual failed checks/rejected review are same-ticket feedback. Use
`product-preview --for-operation correct` and its authorized `product-resume`.
Original scope, paths, task, role counts and expiry remain. Protocol-2 Product
corrections use the same [logical development accounting](../PROGRESS_GUARD.md)
as local personal development. The separate Product compound-correction path is
removed. A prospective logical attempt includes Developer, independently scoped
staging/commit and exact-SHA evaluation, with separate bounded stage permits.
Successful internal stages preserve counters until independent evaluation;
failed stages account normally. Actual Worker metrics are charged once, without
adding overlapping whole-attempt elapsed time. No old permit is extended or
rebound across a source transition. Historical attempts never combine.

Original publication receipts stay immutable. A corrected-SHA publication needs
new exact consent and an append-only revision intent, reusing #40 expected-old
CAS. The same PR is reobserved at the new head; never POST another one. Old
CI/review/merge approvals stay historical. Code and product judgments share
the original two code-Reviewer slots. A correction may complete publication but
exhaust the remaining product-Reviewer slot; retain that genuine stop instead
of adding a context or resetting counters.

PR and post-PR CI are distinct admitted functional M2 requirements. Existing
product/publication counters and aggregate observation/role/window limits stay
consumed. Native effect presence invents no independent progress; guard stops
remain visible beside any actual external result.

Each PR/merge has exact immutable consent, canonical PREPARED/SUBMITTED intent,
private exclusive one-use claim and authenticated observation. Lost responses
reconcile only to the exact original effect. Missing history, duplicates,
alternate PR, changed identity/head/base/permissions, uncertain process stop or
ambiguous result grants no replay. Forge PR/review pagination is checked before
header-dropping reducers: canonical sequential full pages remain supported;
short/empty-next, malformed/foreign/duplicate controls refuse completeness.
A confirmed completed/stopped pending product review can finish only its same
immutable request/context under the original live permit, approved source/review
seal and current CI/policy. It cannot redispatch, renew a deadline or allocate
a replacement role. Normal approval checks run again after accounting.
Status never migrates, resets or writes
GitHub. Handoff requires reconciled effects/reservations and confirmed stops.
Completed execution replay returns `RETAINED_OBSERVATION`, with its actual
historical disposition nested and `NOT_REOBSERVED` freshness; it never claims
current PASS. Unknown latest evidence invalidates previous product review.
An externally merged result without accepted CI/review stays unqualified.
An unresolved own merge intent stays uncertain and is never credited to a human.

A new native link to the exact authenticated own PR is retained privately and
reconciled only as a relation delta. Original links, scope, acceptance, source
version and timestamps remain exact. A changed Issue timestamp or revision has
no qualified causal explanation in this port and still requires operator
reassessment; no global discovery observation is normalized.

## Native and credential limits

The accepted merge port supports merge/squash, atomic HEAD and **observed,
non-atomic base**. The base must be a locally known ancestor; resulting parents
and reviewed tree must match. Base races can only be detected. Rebase/ff-only,
unknown mergeability and unsupported protections need a supported alternative
or human action. A Draft waits for separately authorized external readiness;
no PR_READY endpoint is added.

Normal-user stored `gh auth`, private pipes, fixed origin, supervised requests
and durable unknown-stop fencing are reused. The centralized
[runtime profile](RUNTIME_LIMITS.md) bounds fresh operations; old consent/M2
reservations retain their original ceilings. Reviewer/Developer execution budgets
remain separate; these preferences never grant or extend Worker execution. Product
mutation selection permits only Draft PR POST and exact-head merge PUT, not
Git uploads, reports or issue writes. The [personal quiescence
warrant](PERSONAL_PUBLICATION.md) remains conditional; it is not signed-App
server-side credential confinement. Signed mode and M1–M6 contracts are intact.

The [original focused inventory](PERSONAL_PRODUCT_TEST_INVENTORY.json) freezes
31 methods separately from all 533 accepted methods. Additional narrowly focused
[security](PERSONAL_PRODUCT_SECURITY_TEST_INVENTORY.json),
[recovery](PERSONAL_PRODUCT_RECOVERY_TEST_INVENTORY.json) and
[own-PR relation](PERSONAL_PRODUCT_RELATION_TEST_INVENTORY.json) inventories freeze
5, 3 and 2 methods respectively. Three direct
[CI availability and recovery](PERSONAL_PRODUCT_AVAILABILITY_TEST_INVENTORY.json)
regressions cover the independently confirmed missing-origin accounting boundary
(44 new methods total). The original 31/5/3/2 inventories remain unchanged. Exact source, failures, Python3.11/3.12,
CI and independent review are reported in Issue #41 and its Draft PR. Synthetic
workers/API records are not genuine Codex/GitHub qualification. Engineering
merge, installation, pilot, release and deployment remain unauthorized.

## Private Free-plan rules API (#46)

Base-branch PR/check/merge policy uses the same exact plan-error classifier as
[feature publication](PERSONAL_PUBLICATION.md).
It requires fresh private personal owner/admin identity, current exact base SHA,
supported `protected=false` and separately verified classic-plan unavailability.
The limited independent GraphQL observation must also confirm current ADMIN
permission and both exact published feature/default commit IDs; contradictions
with REST ownership or ref evidence block the fallback.
`availability` and its digest remain in every current policy/approval observation.
Protected, inconsistent, incomplete or permission-denied metadata blocks writes.
HTTP 200 rules retain all existing supported requirements and unsupported-rule
refusals; no generic 403 becomes an empty rule inventory.

For a proposal carrying the plan-disabled warrant, `pr-create` and `merge` each
require their own `--accept-plan-unavailable`, in addition to their existing
separate exact approvals and delegation flags. Neither publication assent nor
credentials authorize either operation. Recovery retains the original immutable
assent and observes an uncertain effect without another POST/PUT. A new policy or
SHA invalidates the old approval. M3 fallback provenance is explicitly
`personal:operator-plan-disabled-base-policy`, never actual-native absence.

The fallback's empty observed-check set and zero native-review minimum are not
absence claims. Original governance/selected check names remain mandatory, genuine
post-PR evidence is still bound to current SHA/PR, independent Codex review is
still required and merge remains manual without separate delegation. Missing,
stale, failed or pending project CI never becomes PASS. No target CI is changed.
