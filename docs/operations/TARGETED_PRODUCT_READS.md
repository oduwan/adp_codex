# Issue64: targeted current Product evidence

This follows independently approved Issue63 on the same Draft PR62. It changes
no M1/M2 schema, grants, deadline, persistent store, journal or positive authority
cache. The operation Budget remains the only request/time accounting mechanism
(defaults10/150/128). Full admission/re-admission still uses M4 discovery.

## Exact call paths

`PersonalProduct.proposed` performs cold `local`, `facts`, `original` and PR
`forge.inventory`. `facts` observes account/repository identity, the pinned
feature/default pair and current base policy. `original` first uses
`track.publication_prerequisites`, then passes that same-stage closure into
`publication.current_original → original_bases` to select the original Issue
plus its frozen native prerequisite closure. Actual
accepted predecessor receipts are checked once; each selected Issue uses the
same M4 before/four-collections/after decoder as full discovery. Actual typed
Issue scope/native edges and literal enrollment branch rules must still match.
Unrelated successors are not reobserved to authorize the selected task.
Publication's original full-preflight/default read set is unchanged; only the
explicit Product caller selects this narrower closure.

`intent` reconstructs the exact proposal at later consent. Its M3 provider,
plan and decide retain all six existing independent snapshot positions. At the
external effect, `forge.submit → final_boundary` reobserves original/facts and
the exact-head PR inventory, then performs final M3 decide before POST. Actual
forge observation and settlement follow POST. No external result crosses a
proposal/consent/pre-effect boundary as a cached positive decision.

`GitHubPolicyAdapter(product_base=...)` is selected only by the closed personal
Product provider. Its rules allow the exact active Product operation plus
VALIDATE, not arbitrary PUSH/BRANCH/RELEASE/DEPLOY. Its snapshot binds the known
feature/default pair, **not global absent-ref knowledge**. Both refs must exist,
have exact prefix/name/Commit/OID and writable viewer permission in the existing
pinned `PERSONAL_REF_QUERY`. Signed/default and publication adapters retain full
refs. The normal Product `facts` uses the same exact-pair function. Plan-disabled
fallback retains its independent permission/ref/protection witness.

`GitHubProductForge(personal=True)` selects the existing backend's exact
`state=all&head=OWNER%3AFEATURE` inventory. All returned rows must match the source
repository ID/name and exact branch; foreign/fork/mismatching/duplicate results
are UNKNOWN, not silently filtered. Both head-filtered list and existing REPORT
routes retain explicit pagination. Child grammars admit canonical encoding only;
Link controls must preserve the entire head/state/per_page query. Detail reads
still bind exact source SHA, head/base repository IDs, node IDs and PR identity.
Empty inventory after possible submission remains UNKNOWN.

A retained canonical action selects original attempted observation/settlement
only. Its old wider receipt map, token, payload and one-use claim are not upgraded
or rewritten into new write authority. If no action exists, fresh original/facts
equality remains mandatory. Expiry/owner/source/review and settlement gates are
unchanged. Interrupted PREPARED/SUBMITTED/UNKNOWN cannot mint another dispatch.

## Endpoint model and bounds

Count actual transport calls, including read-only POST /graphql. For a first PR
in the original three-Issue chain, selected Issue1 has no predecessors. Assume
one page per collection, one enrollment branch, unprotected base, no own-PR
relation delta and initially absent PR. Let K=closure size, B=planned branches,
H=facts, O=original reads, R=literal branch rules, I=forge inventory, F=policy refs.

| Component | Available rules | Precisely verified plan-disabled |
|---|---:|---:|
| H: GET user +2 repository, GraphQL pair, GET branch + paged rules |6|11|
| O: Issue detail twice +4 native collections, K=1 |6|6|
| R: branch + rules, B=1 |2|5|
| I: GET repository + exact-head PR page |2|2|
| F: pinned exact pair GraphQL |1|1|

| Phase | Available | Plan-disabled |
|---|---:|---:|
| Standalone proposal, or its fresh intent reconstruction |16|24|
| Initial M3 provider/plan/decide |3|3|
| Post-SUBMITTED plan/decide |2|2|
| Native pre-submit identity |1|1|
| Final original/facts/inventory/M3 |17|25|
| Actual POST |1|1|
| Actual observe: identity/list/detail |3|3|
| Settlement facts/detail/pull/inventory |11|16|
| **New intent through settlement** |**54**|**75**|

Ordinary and H3 have this same conditional HTTP graph. H3's independent cold
history and canonical frame checks contribute local work, not extra HTTP in this
first-Issue case. This is an endpoint model, not genuine H3 runtime qualification.
Before64 the same first-Issue attached track model was87/108 and proposal29/37.
The older informal148 is not a measured denominator.

For finite pages, O=2K+sum(all4K page counts), each collection≤20. Existing raw-map
cap81 also requires K+sumPages≤81, hence successful O≤81+K. I=1+J with successful
J≤3 (100/page,256 total rows); no response >100/page is complete. H=5+P+C with
successful normal rules P1..2 and classic protection C0..1, hence H6..8; exact
plan-disabled H11. R=2B or5B. Replace each phase's component by its actual bounded
value: intent=3H+2O+2R+4I+6F+6. Accepted predecessors add their actual existing
receipt/remote verification costs; own-PR deltas and recovery have their actual
additional detail paths. A larger supported endpoint envelope can exceed128.
There is no universal promised completion: the original Budget refuses safely,
and partial/unknown effects are observed without blind retry.

## Qualification boundary

Focused tests exercise closure/native-chain retention, new/changed blocker and
scope, incomplete metadata, exact filtered pagination, fork/foreign candidates,
duplicate PRs, permission/ref/policy changes, lost response and legacy observation.
The small seeded Product fixture uses real local Memory/Guard/journal/Git and
actual Product/M3/forge methods with explicitly synthetic approval/Worker seams.
It is not Codex runtime or live GitHub qualification. Exact tested revisions,
denominators, endpoint counts, timing and independent reviews are published on
Issue64. No600-second campaign or full58 release is implied.
