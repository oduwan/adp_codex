# Executable Progress Guard API and migration

M2 is an implementation candidate for Issue #2. The accepted M1 behavior remains
available, and no autonomous execution is enabled. Runtime integration belongs to
its separately admitted milestone. The module uses the standard library only.

## Explicit v1 to v2 migration

Existing M1 memory remains schema version 1. `init`, `status`, `doctor` and guard
inspection never silently migrate, fetch or write it. Every original M1 task
file stays at task schema version 1, including assignments and accepted results.
The upgraded reader validates both closed state versions. Unknown fields and
future versions fail closed.

The owning Conductor must explicitly authorize the upgrade:

```bash
adp guard-upgrade --repo ./project --remote team \
  --memory-branch coordination/current --storage ../project-memory \
  --authorize-memory-write
```

The importable equivalent is `memory.upgrade_guard(authorized=True)`. It uses the
same ownership credential, generation, serialized lock, atomic journal, commit,
remote-parent check and normal push as M1. State version 2 adds only
`progress_guard`: `{schema_version: 1, requirements: {...}, task_epochs: {...}}`.
Migration leaves owner, generation, assignment sequence and task contents intact;
only the coordination revision advances. Repeating a synchronized upgrade is a
no-op. Missing ownership, dirty memory or remote divergence is refused.

The v2 reader recovers interrupted v1 journals and v1-to-v2 upgrade journals.
An unsuccessful upgrade push leaves a recoverable pending checkpoint; a second
clone can synchronize it only after publication. There is no downgrade path.
An older M1 binary rejects version 2; upgrade all writers before enabling v2.
Do not edit version fields or strip guard state to make an old client accept it.

`task_epochs` maps current task keys to monotonic creation/checkpoint revisions.
New task incarnations get a new value, including reuse of the same task ID and
SHA after retirement. This metadata does not alter M1 task records. Historical
guard records remain bounded and retain stalls across aliases or retirement.

## Typed boundary and external evidence

`ProgressGuard(memory, authority=..., clock=...)` wraps the M1 canonical writer.
Every mutating operation requires its current local owner and synchronized remote.
`inspect`, evidence-subject construction, `campaign_summary` and
`require_approval` are observational. A `Decision` contains a `DecisionKind`, reason,
operation scope and exact `Baseline`: contract/gate, canonical task key, source
SHA, task iteration/incarnation, ownership generation, requirement sequence,
record digest and unresolved acceptance set.

The four decisions are ALLOW, FORENSIC_REQUIRED, STOP_UNSAFE and
OPERATOR_DECISION_REQUIRED. A denied attempt raises `GuardRefusal` carrying that
typed decision; it cannot return a usable permit. Normal configuration/schema,
ownership and authorization errors retain M1 exit/error codes. This milestone
exposes the reusable API plus the migration command; it adds no run command.

A caller-supplied `EvidenceAuthority.verify` must validate the authenticated
principal, role, provenance, reference and exact subject digest, returning a bool.
There is **no default verifier** and no inference of authority from issue text,
reviewer labels, worker output or a `verified: true` field. Operator authority is
required for requirement admission and campaigns. Independent reviewer authority
is required for progress and forensics. All recorded source actors are excluded
from independent review. The production integration must supply authenticated
actor identities and a trusted observational verifier. Synthetic test authorities
are fixtures, not shipped authorities or proof of real-world independence.

Construct subjects with `admission_subject`, `progress_subject`, `forensic_subject`
or `campaign_subject`; obtain evidence outside the guard; then submit an
`Attestation(reviewer, reference, subject)` to the matching operation. The subject
binds the complete payload and exact current baseline/request, preventing stale
or edited evidence from advancing state. Review evidence is supplied by an
independent context; the guard never creates its own reviewer or attestation.

## Requirement and attempt lifecycle

A `Requirement(contract, gate, acceptance, dependencies, limits)` has an immutable
accepted contract reference and gate ID. The key hashes those stable identifiers;
task IDs, actors, hypothesis wording and evidence filenames do not define it.
`register(task_id, requirement, operator_evidence)` binds an active task to it.
Re-registering or binding an alias preserves counters, facts and forensic rounds.
Admitting a truly different contract/gate requires new external operator evidence;
the guard cannot determine semantic equivalence of dishonest external contracts.
Existing contracts, criteria and limits cannot be overwritten in place.

```python
from adp.guard import ProgressGuard
from adp.guard_types import Action, ActionKind, Observation, Outcome

# memory is explicitly upgraded and owned; trusted_verifier and the admitted
# requirement_id come from the surrounding trusted application.
guard = ProgressGuard(memory, authority=trusted_verifier)
permit = guard.begin(task_id, requirement_id,
    Action(actor_id, ActionKind.CHECK, "A falsifiable hypothesis", "A finite exit"))
decision = guard.observe(task_id, requirement_id, permit,
    Observation(Outcome.FAIL, ("artifact:case-and-assertion",), ("criterion-A",)))
```

`begin` durably reserves an exact bounded action before returning its permit.
Another actor cannot replace it. `observe` consumes the permit once, validates
revision/generation/incarnation and accounts the measured outcome. FAIL, ERROR
and TIMEOUT increment failures. Every cycle without verified progress increments
stalls; unproductive corrections and unresolved review findings have their own
counters. The third exploratory proposal without an exit is blocked before it
can run. Counters persist across restart, handoff and source changes.

`Observation.progress` may carry a `Progress` claim for CAUSE_NARROWED,
REQUIREMENT_VERIFIED, DEPENDENCY_RESOLVED or CORRECTION_APPROVED. It needs positive
references and independent exact-subject evidence. Cause narrowing extends the
accepted cause chain and cannot reuse its evidence under another label. A
correction at the same SHA cannot be repeatedly renamed to reset counters. The
unresolved set changes only by the proved transition. Invalid evidence leaves the
reservation pending and cannot silently admit another attempt. A reported hazard
takes priority over contradictory progress, removed criteria or malformed
ancillary data: the guard consumes the permit, preserves the unresolved baseline
and latches STOP_UNSAFE. Such a hazard cannot disappear through resubmission.

Use `abandon(..., evidence_reference=...)` to acknowledge interrupted work as
UNKNOWN. It preserves counters and consumes a bounded proof if one was reserved.
Stale work must be abandoned explicitly; recovery never invents its result.
`require_approval` refuses absent or invalidated exact-source approval and revalidates the persisted receipt with the external authority. It grants
no Git/merge authority and does not replace other acceptance requirements.

## Finite forensic recovery

`request_forensic` returns a typed request with exact source context, baseline
digest, accepted contract/gate, hypothesis, measured outcome, counters, unresolved
criteria, accepted cause, excluded authors and durable evidence references.
The request separately names the actual observation context, which may precede
the current source context. After a census it uses the current census artifact
and latest method outcome, never an older ordinary attempt as if it were current.
It does not spawn a reviewer. Repeated reads of the same current request do not
consume another round. Stale source/generation requires a new request.

`accept_forensic` requires a `ForensicReport` and independent external attestation.
Its classification is PRODUCT_DEFECT, TEST_CORRUPTED, INFRA_DEFECT,
SCOPE_MISMATCH, DEPENDENCY_DEFECT or UNCLASSIFIED. Positive review evidence and a
short diagnosis are mandatory. A `ForensicPlan` names one discriminating action,
PASS/FAIL/UNKNOWN interpretations, stop conditions and immutable upper budgets.
The reserved action must match that plan, including its falsifiable exit and
budgets. The guard executes none of its text.

Only two forensic rounds and two bounded proofs are available without verified
progress. If the first proof fails to narrow, one renewed review remains. If the
second fails, stops without progress or is abandoned, further execution is denied
at the operator-only boundary. No plan or a scope/dependency ownership conflict
also requires operator disposition. There is no automatic escalation reset,
threshold increase or override API. A genuine independently verified advance
starts a new productive cycle while retaining accepted facts and evidence.

## Diagnostic campaigns and accounting

`Campaign(inventory, evidence_reference, quarantined, seconds, samples,
payload_bytes)` fixes its original finite inventory and containment. `start_campaign`
requires exact operator evidence. `next_case` durably reserves only the next original method and returns a typed
`CasePermit`. Repeated admission, including after restart, is refused until that
permit is consumed. `record_case(task_id, requirement_id, campaign_token,
case_permit, outcome)` requires that exact permit and stores the actual
PASS/FAIL/ERROR/TIMEOUT/SKIP/NOTRUN outcome. Unsolicited or duplicate results cannot
consume inventory. `abandon_case(..., evidence_reference=...)` explicitly records
an interrupted runner result as ERROR and stops the census; it infers no method
PASS or completed external action. The evidence reference records the missing
runner observation, rather than asserting a product assertion failure. Ordinary
assertions, errors and timeouts do not abort the finite survey, even when their
counters require forensics outside the survey. Other attempts and forensic work
are blocked while an inventory is active. A terminal operator/unsafe decision
cannot be bypassed by starting a campaign.

No inventory replacement, duplicate terminal result, reordered method or increased
budget is admitted. Safety/authority, evidence contamination, source/generation
drift, clock regression, deadline or sample/payload exhaustion stops it. An
observed violating case keeps its actual result; remaining methods stay NOTRUN.
`next_case` checks current containment before a method is admitted. The surrounding
runner must call it before every method and enforce in-method cancellation;
M2 does not execute or interrupt code. The clock is a trusted UTC-seconds provider;
using untrusted timestamps is outside this boundary.

`campaign_summary` reports original denominator, original inventory digest,
observed/attempted counts, separate effective outcomes and QUARANTINED count, plus
raw outcomes including exclusions. Unobserved and explicitly NOTRUN methods remain
NOTRUN. A quarantined PASS never increases effective PASS. `all_observed_pass` is
only a census fact; `formal_acceptance` is always false. No test-census result
silently verifies an acceptance requirement or resets a stall.

## Bounds and qualification

All original M1 file, task, assignment and journal bounds remain. State JSON stays
at 64 KiB. There are at most 16 requirement records, 16 acceptance criteria and
16 dependencies per record, 16 recorded authors, 32 accepted fact fingerprints,
64 task aliases per requirement, and one current campaign of at most 256 methods.
Only the latest observation, review/plan and census are retained. No raw logs,
chat history or unbounded event archive is serialized. Full JSON/schema validation, including consistency between modes, finite plans,
requests and in-flight reservations, runs before every checkpoint; capacity exhaustion fails closed and requires
operator disposition. Campaign admission preflights its maximum result footprint.

Defaults: failed/stalled cycles 3; corrections 2; blocking reviews 3; exploratory
proposals without an exit at most 2. Accepted limits may be stricter, never looser.
Actions/forensic proofs use at most 300 seconds, campaigns 3600 seconds, and both
at most 10,000 samples and 1 MiB of observed payload. Smaller reviewed bounds cannot
be raised. POSIX durability/locking and local administration trust remain as M1.

```bash
python -m pip install .
adp --help
python scripts/validate_scaffold.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

The original 32 M1 tests remain unchanged. New synthetic tables cover each trigger,
verified and forbidden resets, independent evidence, finite forensics, census
outcomes and negative input. Synthetic Git fixtures exercise explicit migration,
interrupted commits/pushes, two-clone handoff and source/task incarnation fencing.
Run on Python 3.11 and 3.12; exact tested/reviewed SHA and any non-PASS observations
belong in the scoped Draft PR. No product runtime or live forge is required.
