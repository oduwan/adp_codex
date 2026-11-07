# Progress Guard — mandatory anti-loop contract

**Status:** design specification for an executable guard, not yet implemented. Safety and honesty invariants are mandatory in all future execution modes.

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
