# Issue69: external lifecycle observation boundaries

Baseline: `f5457d8054e9a8e32a0b43a200af16de760db07c`, tree
`52435f7611919460bdb875b43d1cc5bfff3d9cc4`. Prior frozen
[publication investigation](PUBLICATION_CALL_GRAPH.md) remains historical;
its older threat model and multiplicities are not this release's claims.
This release uses the operator's dedicated, cooperative, single-writer product
and service-directory model. Immutable stopped receipts, reviewed source,
interpreted policy and accepted history are authenticated at entry/restart.
Current external GitHub state, canonical transitions, time, revocation,
credentials and uncertainty remain live. No old ALLOW is reused.

## Baseline paths and replacement

Line references here are to the immutable baseline, not shifted candidate lines.
All counts are per reached normal path; arbitrary paging/branch/callback totals
are UNKNOWN until observed. Inclusive spans overlap and cannot be added.

| Baseline caller → callee | Multiplicity / boundary | Replacement / retained condition |
| --- | --- | --- |
| publication.publish633 → proposed244 → local140 → c.fresh267 → selection / complete M4 | Once at fresh entry; entire repository, future Issues and PRs | Selected original + transitive admitted native closure through the same M4 decoder; original checkout/admin/governance and cold independent reviews retained |
| publication.validate_dispatch402 → publication_prerequisites416, then current_original418 | Twice, before/after upload; closure computed but ignored by raw read | Use that exact closure; changed selected/prerequisite scope or edges refuse; unrelated future Issues are not publication authority |
| local → workers.fence / original_approval / verify_local_review; validate_dispatch repeats them | Entry plus first dispatch | One cold batch bound lexically to the exact owning Budget/runtime/task/consent/SHA/seal; restart has no such operands |
| publication.provider568 → adapter.inspect575 → plan592 → decide596 → plan | Three policy repository inspections in the initial stage | One actual snapshot consumed by plan; a late current M1/M2 safety observation before pure decision evaluation |
| publication.reauthorize599 → plan601 → decide604 → plan | Two inspections after PREPARED/SUBMITTED | One new exact checkpoint-bound plan plus late safety; no pre-checkpoint safety/auth reused |
| native submit → _authorize461/468/473 → decide → plan | Three distinct points around closure/upload/CAS | Keep fresh native M3 decisions; explicit personal PUSH snapshot observes only its target, while default/signed global inspection remains unchanged |
| validate_dispatch → remote → inspect_ref(writable); native submit immediately repeats inspect_ref | Twice in one pre/post-upload boundary | Callback returns its actual native ref observation, not an authorization; signed/default callbacks still independently inspect; expected-old comparison and atomic CAS unchanged |
| publication.proof / verify → live → review_binding → Worker/private/M1 projections | Per source/protection/admission/operation proof | Closed exact typed proof identity/generation/expiry checks consume the existing receipt; actual operation entry, current M3 safety and late write fence remain independent |
| normal publication.write_authorized → live + Guard snapshot + journal inspection | Every object and CAS | Use the existing H3 direct fence for both modes: one late actual Memory subject, exact SUBMITTED action/claim, owner/source/generation, active original permit/time/revocation, transport/credential and original Budget |
| original / facts / private plan fallback → repository metadata read again | Same-stage metadata projection | Pass the actual authenticated response explicitly; no persisted observation or cached permission; default standalone fallback's independent checks remain |
| publication_prerequisites → accepted | Up to each native predecessor at every internal boundary | Full accepted qualification once per owning operation; later use the exact captured immutable operands, actual Memory.inspect and a targeted current PR check; no ref/stat substitute for Memory health |
| Product proposed271 / intent481 / final_boundary464 → local/facts/original/PR inventory | Admission, consent reconstruction, pre-effect, observation | These are distinct boundaries. Reuse only their internal identical inputs; current scope/dependencies, policy/base/PR/permissions and effect observation stay fresh |
| ProductAuthority._validate178 / PersonalAuthority._proof58 / verify77 → c.live / Memory.inspect / flow.live | Nested proof projections | Same-stage source/generation/approval derivations can share their actual canonical observation; no reuse across M2 or journal transitions |
| CI / REVIEW / CORRECT / MERGE / REPORT / completion / NEXT | Conditional; actual CI, role and recovery branches vary | Independent semantic gates and finite original windows remain. No Worker dispatch, acceptance, merge or successor admission is implied by a historical observation |

## Request bounds

Let K be selected original plus actual native prerequisite count. The existing
M4 read is `O = 2K + sum(pages of each of 4K collections)`; for the one-page
three-Issue chain, O is 6,12,18. Each collection retains its existing finite
paging/control checks; the raw receipt map is bounded at81 keys. Incomplete,
ambiguous, changed or foreign metadata refuses, never becomes absence.

PUSH has three independent original observations: fresh consent reconstruction,
before upload, and after upload/before CAS. Immutable predecessor receipts are
qualified once; each subsequent prerequisite boundary still observes actual
Memory and exact PR identity/head/base/merge/actor/text. Object closure keeps its
original object/byte/depth/commit bounds. The only count admission is the existing
Budget's negative lower bound: known object POSTs + mandatory CAS must fit its
remaining allowance. Unknown future reads consume that same original Budget.
No scenario-specific tail predictor or completion promise is introduced.

Actual endpoint/stage counts, source manifests, measured margins and negative
controls accompany the Issue69 handback. Synthetic transport calls are not live
GitHub operations, synthetic review/acceptance seams are not genuine Codex or
historical acceptance qualification, and fixture setup time is separate from
product-operation wall time. Large supported paging/closure cases can still
refuse at128; no limit is increased to make them pass.

## Mandatory boundaries retained

Cold historical H0→H3/source/Worker authentication and restart qualification;
independent exact-SHA review; M1 owner/generation/epoch/assignment/health;
M2 original active permit, counters and deadline; fresh safety after canonical
PREPARED/SUBMITTED; current native repository/permission/rules/ref checks on both
sides of upload; exact expected-old CAS; bounded object integrity; original
one-use dispatch/stop hazard; actual observation and settlement; missing CI,
rejected/stale review and uncertain effects remain nonPASS. Legacy wider consent
is never silently upgraded. REPORT's pre-effect/in-flight distinction is retained.

Invocation-local immutable operands expire on return, exception or restart.
They are not a persistent cache, second journal, authority record or trust
service. Historical A/A2/A3 and prior qualification outcomes remain unchanged.
In particular, A3's exact exception/request/effect history remains UNKNOWN and
its expired uncertain PUSH is not retried or reconciled by this engineering.
