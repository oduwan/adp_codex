# Progress Guard — mandatory anti-loop contract

**Status:** binding contract with the accepted M2 implementation described below (PR #8). Safety and honesty invariants remain mandatory; accepted M5 finite execution calls this boundary before work.

## Goal

A long-running development agent must detect when another retry cannot reasonably improve confidence, distinguish test methodology from product behavior, and recover through bounded independent analysis rather than looping indefinitely or prematurely escalating ordinary failures to a human.

## Observation model

Each material cycle records the task/acceptance requirement, tested source revision, hypothesis, observed result, classification, remaining requirements, next discriminating question, attempt counter and evidence reference. Events are compact and do not accumulate as an unbounded archive in active memory. Guard accounting must survive a Conductor restart.

**Progress is not just PASS count.** Count as useful progress a verified root cause, a falsifiable narrower hypothesis, a newly satisfied acceptance requirement, an independently approved correction, or a resolved dependency. Merely changing fixture wording, running another identical test, or producing more logs does not reset a stall counter.

## Default guard triggers

| Trigger | Suggested default | Required transition |
| --- | --- | --- |
| Same acceptance gate fails without a new narrower established cause | 3 consecutive attempts | Independent forensic reassessment |
| Corrections to the same gate fail to resolve or narrow it | 2 attempts | Independent contract/methodology review |
| Next step is repeatedly an open-ended diagnostic | More than 2 proposals without a falsifiable exit | Block another blind diagnostic |
| Identical blocking review finding persists | 3 consecutive reviews | Escalate after bounded independent reassessment |
| Evidence grows while unresolved requirements do not shrink | Stalled across a bounded work cycle | Reassess plan and scope |
| Safety, authority, or evidence contamination risk | Immediate | Stop affected operation |

These thresholds are defaults for implementation and may be made **stricter** by a target project's explicit policy. No silent disabling, no reset through cosmetic test edits and no numerical threshold relaxation just to obtain PASS.

## Required forensic response

An independent, non-editing reviewer inspects: the accepted requirement, exact failing assertion, actual product behavior, prior hypotheses and evidence. Classify as:

- `PRODUCT_DEFECT`: confirmed in-scope violation; authorize one bounded corrective proof, then normal acceptance.
- `TEST_CORRUPTED`: demonstrated broken test/fixture/methodology; repair in its own stream, then requalify. Do not count excluded tests as PASS.
- `INFRA_DEFECT`: runner/environment problem; resolve internally without inventing product failure.
- `SCOPE_MISMATCH` or `DEPENDENCY_DEFECT`: route to owner of the actual requirement; do not shift obligations between issues.
- `UNCLASSIFIED`: honest unknown; one bounded discriminating plan if possible, otherwise a specific operator decision.

The reviewer returns a finite next action, explicit expected PASS/FAIL/UNKNOWN meanings and stop conditions. If that bounded action fails without narrowing the cause, allow one renewed independent assessment; persistent ambiguity, material contract changes or authority conflicts require operator escalation.

## Full diagnostic campaign exception

For a deliberately authorized, finite inventory (for example, hundreds of test methods), **an ordinary assertion failure does not stop the campaign**. Continue through planned cases, collect every actual PASS/FAIL/ERROR/TIMEOUT/SKIP/NOTRUN, and classify after the run. Stop the campaign early only if continuing is unsafe, destroys evidence, contaminates subsequent results or exceeds explicit containment bounds.

A diagnostic census is **not** formal release acceptance. Preserve original coverage denominators and honest exclusions; quarantined and unsupported tests cannot produce a fictitious green suite.

## Never permit

- Repeating a failed command until it turns green without a new evidence-based hypothesis.
- Treating `SKIP`, `ERROR`, `NOTRUN`, `TEST_CORRUPTED` or `UNCLASSIFIED` as successful product verification.
- Auto-raising timeouts, freshness windows, concurrency limits or sample sizes to hide a defect.
- Self-approval by the Developer or reuse of an approval after the source revision changes.
- An issue comment overriding the Conductor's safety limits or the project's external authority policy.

## Acceptance tests for this component

Synthetic fixtures must prove all triggers, restart-persistent counters, genuine-progress resets, cosmetic-change non-resets, bounded forensic exit, protected full-survey continuation, safe escalation and non-pass accounting. No real product diagnosis is required to qualify the guard.

## Accepted M2 executable implementation

Issue #2 implements this contract in `adp.guard.ProgressGuard`, with typed inputs
and decisions in `adp.guard_types`. It is a standalone offline boundary backed
by the accepted M1 Conductor checkpoint writer. It does not invoke workers,
GitHub, repairs, product Git operations, policy decisions or unattended execution.
The later execution integration must call this boundary before each action.
M1 assignment records remain coordination metadata and grant no execution authority.

See [Guard API and migration](GUARD_API.md) for the exact state machine, trust
boundary, accounting, limits, upgrade commands and qualification commands.

The executable defaults are the table above: 3 failed/stalled cycles, 2 unproductive
corrections, a refusal of the third unfalsifiable exploratory proposal, and 3
unresolved blocking review observations. Distinct wording of a blocking finding
also counts conservatively until verified progress. Repeated PASS with no newly
verified requirement, cause, dependency or correction still counts as stalled
work; increasing PASS counts alone cannot reset the guard. Thresholds may only be
made stricter when the accepted requirement is first admitted.

A mandatory reservation permits exactly one observation. A second worker, new
hypothesis, task alias, restart or source revision cannot bypass a pending
reservation or its counters. Operator-verified contract/gate identity determines
the requirement key; aliases bind the same durable record. Retirement retains
that bounded record. Recreating a task creates a new incarnation and cannot make
an old action or approval current. No reset or override API is provided.

An independent, externally verified progress claim resets counters only after
its exact baseline and measured transition are checked. Reused evidence and
renamed cause facts cannot reset a stall. Requirement verification requires PASS
and removal of precisely one admitted criterion; dependency resolution must name
an admitted pending dependency. CORRECTION_APPROVED binds the exact source SHA,
task iteration, incarnation and ownership generation. Source drift, including a
change away and back to the same SHA, invalidates current approval.

The first forensic request admits at most one reviewed discriminating action. If
it produces no verified narrowing, one renewed independent review can admit one
final bounded action. A second inconclusive proof produces the terminal
OPERATOR_DECISION_REQUIRED boundary. Scope/dependency ownership conflicts or a
review without a finite plan go directly to that boundary. UNCLASSIFIED with a
finite plan defers uncertainty honestly; it does not become a product diagnosis.
TEST_CORRUPTED requires positively evidenced external review and cannot relabel a
failed or quarantined observation as PASS. A safety, authority, contamination or
containment violation produces STOP_UNSAFE and cannot be reset by a proof.

A campaign requires separately verified operator authority, an immutable inventory,
quarantine set, evidence reference and containment budget. Its ordinary FAIL,
ERROR and TIMEOUT results update counters but do not terminate its remaining
inventory. Each next-case admission durably reserves exactly one method and checks current
revision/generation and time. Duplicate admissions and unsolicited completions
are refused, including after restart.
Safety, contamination, clock/deadline or budget violations stop the campaign and
leave remaining cases NOTRUN. Original inventory order and denominator never
shrink. Quarantined observations retain raw outcomes and are counted separately
from effective PASS. Campaigns are diagnostic censuses, never formal acceptance.
Only one census is admitted without new independently verified progress.
