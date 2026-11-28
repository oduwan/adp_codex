# Issue65: one actual observation within each decision stage

This follows independently approved63/64 on Draft PR62. It changes no canonical
Memory/Guard/policy schema or default signed-provider decision. No positive
decision, snapshot or authority is stored across operations or restarts.

## Deleted repeated paths

Previously Product `local → review_seal` took an inspection for the seal, two
Guard `_snapshot` inspections, and (when idle) two more `allowed → inspect`
inspections. `_live_current` then inspected generation and computed the seal a
second time. The changing HTTP callback repeated `_live_current`, parsed its
record with another inspection and finally inspected again.

Now `local` consumes the actual `Coordinator.live` observation. A genuine cold
entry always obtains current authority and reobserves canonical Memory **after**
the original/code-review callbacks, which may checkpoint. Nested callers may
pass only the actual same-stage observation. `review_seal` validates both actual
assignments and Guard states against it using existing `_get/_active/_decision`.
Code review still requires the canonical committed SHA. Supplied observations
must be synchronized and owned. A new checkpoint requires a new observation.

`_live_current` obtains one actual `c.live` result, computes the seal once and
uses that same generation/source subject. Independent H3 frame opening/closing
checks remain. H3 Reviewer `_decision` still invokes the existing live accounting
qualifier, which can inspect Memory again; this work is **not** mislabeled zero
or a pure cached ALLOW. No general M2 qualification contract is changed.

For normal idle Reviewer guards, excluding the existing cold review callbacks:

| Boundary | Before65 actual Memory reads | After65 |
|---|---:|---:|
| Seal without caller snapshot |5|1|
| Seal with actual caller snapshot |5|0|
| Nested `_live_current` |13|1|
| Direct Product write callback |15|1|

These are source-derived multiplicities, not universal H3 runtime totals. Actual
cold qualification, attachment and permitted recovery paths add their own reads.
The small seeded fixture deliberately mocks the seal, so its operation telemetry
does not claim this table's full independent-Reviewer provenance workload.

## Single late mutation observation

The Product PR/MERGE/REPORT callback no longer calls `local`, `live`,
`_live_current`, `review_seal`, project discovery or a local Git source probe.
It validates exact active intent/action, selected service/transport/recipient,
approved source/ref, the private original intent and one-use claim, and current
credential. Record/REPORT identity parsing consumes the existing dispatch subject
without a hidden Memory inspection. Missing journals retain their original
synchronized/schema3 migration gates. REPORT task iteration remains bound.

The network service already refuses prior uncertainty **before** starting the
request. Inside the callback, its exact own `IN_FLIGHT_OR_UNKNOWN` marker and
recipient must remain present. Calling `_check_stop` here would incorrectly
reject this request's own marker. The gate never clears, relabels or retries it.
The existing service confirms a stopped response or retains UNKNOWN afterward.

After callbacks that could advance state, the gate takes **one actual late
Memory inspection**, compares the full expected canonical subject, checks owner,
generation, source, exact SUBMITTED action and the original permit via pure
`_get/_active`. It checks mode, started/deadline, current revocation and consent,
H3 invocation identity and the same original monotonic Budget. No earlier ALLOW
authorizes this request. Canonical drift during credential/private reads refuses.
Local cooperative single-writer trust does not freeze external GitHub, time,
revocation, canonical state or network uncertainty. The one source handoff and
independent native pre-effect policy/ref checks remain.

## M3 stages retained

Initial provider snapshot, initial plan and independent decide remain. After
PREPARED/SUBMITTED, an actual new plan must equal the original except its fresh
safety/checkpoint; its policy must ALLOW and its exact authorization/effect proof
are rebuilt. The immediately following redundant decide is deleted. The final
**default** decide independently rebuilds the plan after all forge prechecks and
immediately before POST/PUT, for PR/MERGE and REPORT. `PolicyProvider` itself is
unchanged; no previous verdict is reused. Any changed policy/ref/source/guard
there still refuses.

The first-Issue conditional64 model therefore becomes proposal16/24 and
intent53/74 (available/precisely verified plan-disabled). Five actual policy ref
snapshots remain instead of six. Larger page/closure and own-PR/recovery costs
remain subject to the single unchanged Budget, not a request predictor.

## Focused qualification

Controls exercise same-snapshot reviewers, assignment/source/owner/generation,
Guard stop, private-intent and credential callback canonical drift, exact own
network marker, recipient/transport/invocation mismatch, original claim/action,
M2 expiry/revocation and REPORT identity/iteration. Existing H3 cold/closing,
legacy, signed policy and final external-policy negatives remain relevant.
Exact results, source identity and measured costs are published per ticket.
No600-second, full58 or genuine Worker campaign is part of this scope. Malicious
same-UID changes to an already admitted worktree/history remain out of model.
