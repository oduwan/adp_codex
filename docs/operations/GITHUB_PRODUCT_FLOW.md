# GitHub product flow

Issue #16 adds individually invocable PR, project-check, review acceptance,
merge and product-report transitions. They use the actual accepted Conductor,
ExecutionJournal, M1 owner/generation and M2 reservations. They do not implement
#22's remaining autonomous worker/correction scheduler, #17 enrollment or an M8
pilot. Real GitHub target writes remain **NOTRUN**; release and deployment remain
**NOT_AUTHORIZED**.

## Explicit selection and compatibility

An installed trusted controller selects `GitHubProductFlow` on
`conductor.Project.product_flow`. It supplies `PreparedScope`, a factory for the
actual #21 `ProjectValidation`, a project delegation factory and
`GitHubProductForge`. No CLI default, token, issue prose or green badge enables
this flow. The unchanged legacy Project path remains available.

First explicitly opt into internal execution schema v2 with
`ExecutionJournal.upgrade_product_flow(authorized=True)`. This owner-authorized
migration adds bounded `product_flows` and permits MERGE actions. Outer memory
state v3, M1 tasks, M2 guard, legacy jobs/actions and their original limits remain
unchanged. Read commands never migrate; old binaries refuse the internal version.
Existing internal v1 remains closed and its default authorizations retain their
original serialized bytes. There is no downgrade or history rewrite.

V2 retains at most eight product flows, two phase gates per flow, 32 total actions
and eight publications under the existing **64 KiB** canonical state cap. Full
bounded #21 receipts may exhaust that cap; the checkpoint refuses rather than
truncating evidence or increasing accepted limits. Keep the same private scope,
validation and effect directories across restart. Lost history is not absence
proof and requires external reconciliation.

## Original scope and identity

`PreparedScope` reads the accepted #22 original, packet and reconstructible
preparation proof. It authenticates the existing scope and preparation subjects,
particular additions and exact goal, acceptance, paths and prescribed checks.
Initial execution needs current preparation and the prepared source SHA. Ongoing
operations retain that immutable admission provenance and obtain a fresh
`github-product/scope` receipt over the actual current M4 issue and source.
Unchanged title/body with new PR links or comments does not silently add scope;
changed title/body, acceptance, paths or checks is refused. The existing fresh M4
independent specification assessment still applies. A historical packet, whose
execution authority remains UNKNOWN, is never an operation grant.

The initial supported #22 mapping requires the explicitly configured M3/memory
repository ID to equal the M4 canonical provider repository ID. Configure
`Config.repository_id` before initializing memory; this flow never rewrites an
existing identity. The forge independently pins the GitHub database ID, node ID
and canonical owner/name. The prepared project name/URL must match that target.
Distinct-ID legacy M5 planning remains supported by its existing path; a new
cross-identity execution bridge is not supplied here.

## Pre-PR and post-PR project checks

Projects configure BEFORE_PR, AFTER_PR or both through #21. Only configured
phases are queried. A pre-PR-only project is not forced to wait for post-PR CI.
A post-PR project can publish the exact branch through #14 and create one marked
Draft PR before checks exist. That PR is **PENDING_VALIDATION** until its exact
current HEAD has qualified results. The project owns all check procedures,
languages, runners and safeguards. This feature adds no CI YAML, test command,
runner, sandbox or workflow dispatch.

The independent code Reviewer job remains an actual isolated exact-SHA result.
Its code approval can establish M2 CORRECTION_APPROVED progress, with
`validation_stop=NOT_STARTED`: no ADP check process has been launched. Every
admitted acceptance criterion remains unresolved. `qualify_review` requires all
prescribed #21 phases before clearing any criterion through the accepted M2 API.
It binds the actual project gates and actual Reviewer receipt to those proofs.

`ProjectCheck`/`ProjectQualifications` are a separate M3 representation. Legacy
`Check`, `ValidationResult` and `Qualifications` keep their original numeric
contracts. Job-only CI retains `denominator=None` and empty counts. Partial,
non-PASS or quarantined accounting never becomes comprehensive PASS. The
`policy/project-validation` verifier authenticates the complete configured phase
inventory and acceptance of job-level evidence. `policy/project-check`
authenticates each actual #21 receipt, provider/origin/run and current source.
An always-true signer destroys this trust boundary; none is provided. The flow
also checks the retained #21 journal digest/time and current prescribed identities.

Pending/missing/stale/incomplete results remain pending or UNKNOWN. Ordinary
FAIL/ERROR/TIMEOUT/CANCELLED is REQUIRES_CORRECTION, preserving unresolved criteria
and M2 bounds. Source changes invalidate review and gates. The original creation
intent and one PR identity survive correction; a separate current-PR observer
checks the newly pushed HEAD without creating another PR.

## Delegation and native merge envelope

`DelegationProfile` is externally authenticated task-specific data, not enrollment
or token provisioning. `github-product/delegation` binds the canonical repository,
issue, task/iteration, current source/ref/base, policy digest, original scope,
permitted effects, methods and validity interval. Every forge write also requires
fresh exact M3 ALLOW, execution/effect authority and a real reserved M2 permit.
Actual project review inventory is authenticated under `github-product/reviews`;
canonical authorship and project-specific native review requirements belong to
that external verifier. A current requests-changes record refuses merge.

Absent or manual merge delegation yields **WAITING_HUMAN_APPROVAL**, with zero
merge writes. A still-Draft PR also waits for a separately authorized external
actor to mark it ready. There is **no PR_READY operation** and merge permission
never implies readiness permission. Queue, stacked and asynchronous merges are
unsupported. The qualified native methods are `merge` and `squash`; rebase remains
forbidden by M3 and `ff_only` is UNSUPPORTED without a fallback.

GitHub's [native merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)
atomically checks the submitted head `sha`, but has no expected-base parameter.
Only explicit authenticated **HEAD_ATOMIC_BASE_OBSERVED** project assent qualifies
this envelope. ATOMIC_BASE, unknown or absent assent returns UNSUPPORTED. This
is not #14 exact-old ref CAS; #14 PUSH semantics are unchanged.

The flow freshly checks expected base, policy/protection, checks, review and PR
identity. It preflights that the observed base is an ancestor of the reviewed
HEAD, so the supported resulting tree is the reviewed source tree. Divergent or
unprovable combined source is refused before submission. Native server protections
remain mandatory. A base/policy race after observation is outside atomic-base
semantics: reobservation must prove merged state, resulting SHA, exact parents and
reviewed tree. A mismatch remains UNKNOWN and never authorizes another merge.

## Effects, restart and reporting

M5 checkpoints PREPARED/SUBMITTED before any write. `GitHubProductForge` mints one
private, fsynced, exclusive claim and one in-process dispatch capability at the
actual PREPARED transition. Recovered SUBMITTED never mints another capability.
PR/report marker inventories use complete bounded pagination; duplicate or changed
markers/bodies and foreign PR identity remain UNKNOWN. A found exact result can
reconcile a lost response. Absence after a possible request never permits retry.

`GitHubForgeHTTPTransport` reuses the accepted Linux supervised fixed-origin HTTP
exchange and #14 write-ahead stop hazard, with a separate narrow forge grammar.
Its independently verified installation issuance is restricted to one immutable
repository and contents-write, issues-write, metadata-read and pull-requests-write.
Default CAS transport grammar/permissions are unchanged. No unsupervised fallback
qualifies. An unknown transport stop blocks subsequent HTTP and handoff, even when
a result happens to appear. Unreconciled forge delivery also refuses handoff.

A PRODUCT iteration can publish one deterministic substantive summary naming the
change, exact qualified source, review and resulting PR/merge or human-merge
limitation. INTERNAL creates zero forge effects. Raw logs, CI descriptions,
worker chats, retries, secrets and infrastructure chatter are not copied into it.
Issue closure, labels and other issue edits are not implemented.

After a confirmed merge, #21's open-PR query is no longer applicable. Reporting
retains the qualified, still-fresh pre-merge receipt and independently reviewed
source, obtains current scope/policy authority and reobserves immutable merge
parents/tree/result. It never substitutes a new fabricated closed-PR check result.
A stale receipt or unproven result blocks reporting. Manual merge remains
WAITING_HUMAN_APPROVAL even when its one useful limitation summary is published.

`advance` performs one finite publication step with actual coordination assignments
and guard reservations. It returns VALIDATED, PENDING_VALIDATION,
REQUIRES_CORRECTION, WAITING_HUMAN_APPROVAL, UNSUPPORTED or a proven completion;
it is not a daemon and claims no cancellation of project-managed CI. The existing
Conductor routes ordinary in-ticket corrections back to development under M2.
The complete autonomous #22 execution lifecycle remains separately unqualified.

## Focused qualification

The frozen additive inventory is
[GITHUB_PRODUCT_FLOW_TEST_INVENTORY.json](GITHUB_PRODUCT_FLOW_TEST_INVENTORY.json):
42 individual method IDs. It exercises owned disposable Git/M1/M2/M3/M5 state,
accepted #21/#22 services and synthetic authenticated provider states. It is
included by the existing M7 runner and unchanged CI inventory wildcard. Accepted
210 M1–M6 and 104 M7 cases and their source/inventories remain unchanged.

Initial development evidence: the first42 run recorded **42 setup ERRORs** from a
missing fixture preparation exit condition. Its retained raw log SHA256 is
`77f4cb8ce9ece20317a81f70496cf3c540e4991b2adfa4c64b8dea02338f8d26`.
A subsequent one-case proof exposed a tuple-normalization error. The corrected
single pre-PR/merge interface proof passed in146.834s on Python3.11.10 before later
source corrections; it is historical, not final exact-HEAD acceptance. Final
Python3.11/3.12 focused/full CI, clean installation and independent exact-HEAD
code/schema/security review remain required and are reported in the Draft PR.
Real GitHub target writes and the whole-track M8 pilot are **NOTRUN**.

Independent review of candidate `a43a923` found durable code-review/acceptance
crash windows, historical Draft observation on completed resume, persistence of
same-SHA rerun failures and authorization freshness after provider reads. The
correction keeps code-review jobs nonterminal until their M2 observation is
proven, then checkpoints the real review link and next stage atomically. A bounded
pending acceptance subject lives in the existing product-flow row before permit
consumption; recovery proves the actual last M2 observation, resumes an existing
exact criterion reservation and skips already verified facts. It never replaces
an unresolved permit or resets counters. When no reservation remains, accepted
M2 inspection is used solely to reconstruct and reauthenticate retained evidence;
new effects still require their own real reservation. An expired gate blocks
recovery. New observations cannot overwrite a pending acceptance transition.

A nonqualified same-SHA check atomically removes current `task.review` and records
the correction/pending phase; accepted M2 facts remain historical. Final forge
callbacks recheck actual owner/generation, reservation/deadline, source, exact M3
policy and delegation after provider reads immediately before POST/PUT. Completed
resume observes the current PR/result and preserves old creation/PUSH intents.
An unchanged immutable code-review receipt is freshly authenticated against the
current policy; this is not a new runtime review or an invented universal review
expiry. External project revocation and freshness rules remain binding.

Candidate `a43a923` CI recorded accepted210/210 plus accepted104/104 PASS, focused
5/42 PASS and37 ERROR on each Python3.11/3.12 job, with installation6/6 and scaffold
PASS. These red focused results remain failures. The local restricted host could
not build fresh installations (3.11 build-dependency retrieval unavailable,
3.12 lacked pip); CI supplies the independently observed installation evidence.
Final corrected focused and CI results remain pending.
