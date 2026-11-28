# Issue #68 — scoped qualifier and fixture maintenance

The operator accepted #67's two product fixes at `eb24548a6ce1c606c3fdf74b045c0d27ca339ba9`
and explicitly admitted #68 without repeating the expensive REPORT prerequisites.
The product subtree remains `2a685de734ebf7678bedbaa854e290b885dc2e63`.
This maintenance changes tests and qualification metadata/scripts only.

## Original and current inventories

- The original M1–M5 denominator remains **193**, with the original inventory
  and immutable M6 plan unchanged.
- Accepted M1–M6 qualification historically reported **210** methods. Its report
  remains historical. The current core inventory is **211** after the already
  approved five-line additive discovery regression.
- The previously listed M7 inventory contains **566** unique IDs. The D4 source
  actually contained **606** methods; the 40 omitted D4 IDs are now explicit.
  Five #67 phase tests and four narrow qualifier tests bring the current M7
  inventory to **615**. The new [additive inventory](../operations/D4_REMEDIATION_TEST_INVENTORY.json)
  supplies exactly the 49 formerly unlisted IDs. All 566 prior IDs remain.

Only `tests/test_discovery_github.py` has a seal amendment: original blob
`a9f39bebac1f171835068b46f6a00f9041d6cf9c` becomes the already accepted blob
`8668c94be92edec6f2c1e5e4792a4dfabb5c3521`. The entire original file survives
byte-for-byte around the one added test. Both qualifiers use the same explicit
pin; an unrecognized original blob or any other current blob refuses. Every
other original test/fixture keeps its original seal. No seal is computed from
arbitrary current source in order to accept it.

## Scoped repaired tests

The six existing method identities are retained. Handoff tests assert actual
acceptance/refusal and no source/index/config writes, rather than comparing an
implicit `None` return. The surviving literal historical-consent decoder rejects
an altered original engine; current handoff rejects changed source and physical
administration. These unit boundaries do not claim a complete cold-H3 replay.
Continuous malicious same-UID local-history interference is outside the accepted
trusted-worktree model, not a passing security control.

The remaining repairs supply the actual `_observed` keyword interface, immutable
repository identity and well-formed native metadata. Malformed/partial/unstable
metadata still refuses. The legacy-cap fixture reaches its actual first read
and executes the unchanged original 5/45/128 assertions, even with wider selected
configuration. No real grant, deadline, budget or product code is changed.

## Pre-execution checks are not qualification PASS

`qualify_m6.preflight()` and `qualify_m7.preflight(paths)` expose their existing
source/inventory checks without running the discovered suites. Their ordinary
CLI entry points still execute full qualification and are **not authorized** by
#68. Focused harness tests call only preflight and install a runner refusal in
the positive check. Negative controls reject changed seals, dirty source,
missing/duplicate/foreign IDs, and denominator/scenario/plan-hash drift.

Discovery enumerates methods; it does not execute them. Neither the 211 core
methods nor the 615 M7 methods receive a new PASS from enumeration. Full CI and
#58 stay paused. All previous nonPASS results, including the pre-REPORT CI UNKNOWN
and publication-budget failures, remain preserved. REPORT recovery is deferred
to #70 by the operator; #69/#70 and pilot execution are not part of this change.
