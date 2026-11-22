# Issue #37: personal enrollment contract decision

**Disposition: BLOCKED_ARCHITECTURE under the issue's explicit fallback.**
Personal enrollment is **not implemented** by this change. It records the
source-level boundary, reusable ports, focused characterization evidence and a
bounded decomposition for operator review. Passing characterization or legacy
tests does not satisfy the requested personal-mode acceptance matrix.

Baseline: `84506489802c732bcfc1bf89a5bfdbcba29d78b5`.
Scope: the original [Issue #37](https://github.com/oduwan/adp_codex/issues/37),
created and frozen before development on 2026-11-22. Its scope and acceptance
requirements have not been rewritten. No GitHub ticket/dependency edits or
new implementation issues have been created.

The existing composition cannot provide this workflow through a frontend or
provider-removal adapter alone. This is **not** evidence that a separate personal
backend is fundamentally impossible or outside the issue's scope. It identifies
the additive policy, evidence and execution contracts needed before that backend
can truthfully promise a usable finite lifecycle. No production code, signed
provider behavior, memory schema, guard threshold or packaged Skill is changed.

## Existing call chain and enforced boundaries

| Entry | Current implementation | Enforced contract |
| --- | --- | --- |
| Skill / managed CLI | [Skill](../../skills/adp-codex/SKILL.md), [Codex frontend](../../adp/codex_cli.py) | Versioned observations, exact setup digest, a separate reviewed invocation and execution confirmation |
| `inspect` | [enrollment CLI](../../adp/enrollment_cli.py#L96), [inspection](../../adp/enrollment.py#L152) | GET-only canonical identity and complete native discovery; no setup authority |
| `plan` | [prepare](../../adp/enrollment.py#L490) | Existing trust root, signed proposal, current independent provider bindings and pre-existing coordination checkout |
| `apply` | [apply_plan](../../adp/enrollment.py#L579), [setup](../../adp/operator_setup.py#L149) | Exact approved intent, final reobservation, M1 ownership and explicit migrations; no worker start |
| status / preview / reconnect | [read_enrollment](../../adp/enrollment.py#L621), [operator setup](../../adp/operator_setup.py) | Retained original profile/trust/intent, checkpoints, current providers and no read-side budget reset |
| finite `run` | [installed composition](../../adp/operator_controller.py), [track](../../adp/autonomous_track.py) | Actual M1/M2/M3/M4, independently prepared ticket, actual worker receipts, project evidence and product effects |

### G1: verified absence has no accepted check gate

[PolicyProvider.plan](../../adp/policy.py#L302) returns UNKNOWN for VALIDATE with
an empty required-check set, even when a current authenticated policy source
explicitly contains `checks=()`. [ProjectValidation.policy_subject](../../adp/project_validation.py#L39)
requires one or more checks. [TaskLifecycle._validator](../../adp/lifecycle.py#L163)
requires the actual `ProjectValidation` type and the original check inventory;
[Conductor._policy](../../adp/conductor.py#L387) requires the actual M3 provider.
Substituting a permissive provider does not preserve these contracts.

A new personal backend cannot truthfully represent “the project prescribes no
checks” through this gate today. Adding a placeholder check, calling independent
code review a project test, or making empty inventories globally PASS would
violate Issue #37. UNKNOWN/403 is also not evidence of verified absence.

Optional commit conventions need a similar explicit treatment. Missing scalar
rules remain UNKNOWN in [M3](../../adp/policy.py#L148), including branch and commit
templates. However, M3 already supports authenticated `OPERATOR` claims: an
explicitly chosen branch/message can be an operation instruction rather than a
fictitious repository rule. This is a useful existing extension point, not a
reason to impose ADP's own conventions on a personal project.

### G2: initial independent semantic review precedes current runtime receipts

[M4](../../adp/discovery.py#L108) rejects readiness receipts from issue authors.
[TicketPreparer](../../adp/ticket_preparation.py#L324) excludes original authors
and the preparer from original-scope and preparation review and requires READY
before producing a packet. [PreparationAuthority](../../adp/ticket_types.py#L94)
requires actual independent interpretation and scope-conservation judgments;
schema validity and matching hashes alone cannot supply those judgments.

An owner who authored the issue may approve operations, but that approval cannot
stand in for the independent semantic reviewer. Generating local HMAC keys under
different role names would not create independent people or review evidence.

The existing genuine [runtime receipt verifier](../../adp/operator_authority.py#L212)
authenticates stopped, generation-fenced jobs already recorded under an admitted
execution task. [Conductor._job](../../adp/conductor.py#L346) creates those jobs
after admission. Current grant routing still uses independently signed decisions
for Developer scope and other semantic decisions. A later exact-SHA code review
cannot retrospectively authenticate initial original-scope interpretation or
before-Developer scope authorization.

A provider-free mode needs a bounded, read-only preparation review stage, with
real Codex contexts, actual M1 assignments, mandatory M2 reservations, exact
purpose-bound subjects and confirmed stop receipts. It also needs equivalent
current evidence for later actual-diff scope decisions. These capabilities are
not supplied by removing the trust/socket arguments from the CLI.

### G3: the installed track has no local-only product disposition

[AutonomousTrack._attach](../../adp/autonomous_track.py#L157) always attaches
`GitHubProductFlow` and `TaskLifecycle`.
[Product scope context](../../adp/product_flow.py#L123) requires the qualified
GitHub forge. Legacy [PRODUCT publication](../../adp/conductor.py#L912) requires
observed PUSH, PR and REPORT effects. A local draft is not product DONE, and
calling a user issue INTERNAL would misclassify it.

The personal default explicitly grants none of those external effects. It needs
an honest local-draft/pending-publication stop with independent review and actual
check status retained, without inventing acceptance or automatic advancement.

### G4: signed installed credential provisioning is not ordinary gh login

[Provider preflight](../../adp/enrollment.py#L300) requires independently
provisioned policy/scope/issuer roles and read/CAS/forge credentials. The
[installed readers](../../adp/operator_controller.py#L49) construct CAS credentials
even before a write operation is selected; build also constructs the forge.
[Profile validation](../../adp/operator_profile.py#L273) requires nonempty checks
and constrains native GitHub validation to POST_PR.

These are constraints of the signed composition. They must remain intact for
existing profiles. Copying a broad gh credential into `ScopedInstallationToken`,
inventing issuance records or automatically minting all signed provider roles
would counterfeit its guarantees. Personal mode must be distinctly opted in,
with its own protected state and authority provenance, and must not construct
unapproved or unused mutation ports.

## Reusable capabilities established now

- Native discovery already accepts a bounded read credential from the existing
  gh authentication path without an external issuer. Native dependency edges and
  complete inventories remain observations, not admission or operation rights.
- Optional governance files can be observed absent without creating documents
  or changing the checkout. Existing governance is still data whose actual
  constraints must be interpreted and honored.
- Authenticated M3 OPERATOR claims can express exact choices and operation
  permission without a project policy file. An unapproved plan remains UNKNOWN.
- The general [GitHub evidence source](../../adp/project_validation_github.py#L170)
  can observe checks for an already-published exact SHA before a PR; it verifies
  PR identity only when a PR is supplied. The POST_PR-only restriction belongs
  to the signed installed profile, not this general port. A workflow file alone
  proves no success or required-check inventory. Unpublished/stale source,
  missing checks and pending runs must retain their actual outcomes. Native
  unknown test denominators and attempt IDs remain unknown.
- Existing M1 ownership/generation, M2 anti-loop limits, exact-SHA code review,
  source sealing, Git CAS and durable effect-recovery contracts remain reusable.

## Proposed bounded decomposition — no ticket edits applied

These cuts preserve Issue #37's original scope; they add no CI infrastructure,
project test runner, sandbox, broad scheduler or pilot execution.

1. **Personal policy/evidence and local-draft contracts.** Define a separately
   authenticated distinction between PRESENT, VERIFIED_ABSENT and UNKNOWN for
   relevant requirements. Define a truthful no-prescribed-check disposition
   without a synthetic check PASS. Separate selected operation details from
   discovered project rules. Specify local draft versus independently accepted
   product completion and pending publication/check evidence. Use an explicit
   new purpose domain/version wherever needed; preserve all existing signed
   bytes, UNKNOWN meanings and refusal tests.
2. **Genuine independent preparation and scope receipts.** Define the finite
   pre-admission review stage and later scope decisions, bound to the complete
   frozen issue/proposal/policy/diff, actual role/context, source, generation and
   stopped runtime result. Preserve original authorship exclusions and never
   reuse a changed-SHA review. Setup must not start this stage: the separate
   finite run approval is mandatory. Clarify one round versus worker-stage
   accounting and explicit per-role limits while retaining one task and one
   concurrent worker by default. Do not increase or reset M2 limits.
3. **Distinct personal enrollment/backend and both frontends.** After the above
   contracts are reviewed, wire read-only inspect/plan, exact approved automatic
   private coordination setup and optional local feature preparation, retained
   status/doctor/reconnect and finite run/resume/handoff. No manual provider JSON,
   trust root or daemon is required for this path. Keep signed configuration
   visibly separate; never auto-convert it. No merge, issue-edit, push, PR or
   report right is implied. Unknown protection blocks the affected external
   effects; missing actual CI remains pending. Unsupported external credential
   or mutation capabilities remain explicit blockers.

The first two contracts are prerequisites for claiming that the final backend
supports the finite personal lifecycle. Enrollment/preview can be developed
separately, but would be **PARTIAL** until those prerequisites are implemented.
The requested operator decision is whether to proceed with this bounded
decomposition and its explicit contract changes; no split/dependency edit or
implementation of those new contracts is claimed here.

## Qualification and remaining acceptance

The four cases in `PERSONAL_CONTRACT_GAPS_TEST_INVENTORY.json` characterize the
existing ports and the identified gap. They establish explicit operator-choice
support, rejection of an authenticated empty check inventory, real native
evidence-port handling of synthetic pre-PR/pending/stale observations, and
read-only absence observation in a disposable repository. All receipt issuers
and GitHub responses in these tests are synthetic. No real worker, live GitHub
target, installation or enrollment is exercised by these four cases.

Relevant existing enrollment, Codex frontend, signed operator, ticket
preparation, project-evidence, policy/security and Progress Guard regressions
provide compatibility evidence. Original test files and denominators are
unchanged. Exact candidate SHA, Python versions, commands, outcomes, evidence
hashes, CI results and independent exact-HEAD review belong in Issue #37 and its
Draft PR; they must not be inferred from this plan.

| Original acceptance | Disposition at this boundary |
| --- | --- |
| Fresh provider-free inspect/plan/apply and decline | Inspection primitives exist; personal plan/apply are NOT_IMPLEMENTED, blocked by G1–G4 |
| Existing governance/checks; absence differs from unknown | Existing strict gates preserved; new verified-absence policy/evidence semantics NOT_IMPLEMENTED |
| All personal-mode negative/refusal cases | Existing signed/core refusals can be qualified; personal-mode implementation tests NOTRUN |
| Personal setup/reconnect/stop/resume with retained ownership/budget | NOT_IMPLEMENTED; existing M1/M2/signed behavior remains mandatory |
| Native three-issue graph and separated one-worker preview/run approval | Existing discovery/approval behavior can be qualified; personal preview/run and actual contexts NOTRUN |
| Python 3.11/3.12 and separate review | Characterization/compatibility evidence only, never a personal implementation or M8 PASS |

The original Issue #37 remains open and incomplete. A green CI or approved
decision packet does not mean that personal enrollment is supported. No ADP
reinstall, pilot modification/enrollment, worker launch, merge or M8 gate change
is authorized by this packet. Stop for operator review.
