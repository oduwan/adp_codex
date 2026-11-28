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

## Product lifecycle consolidation

`PersonalProduct.original` delegates to the publication original/closure decoder;
there is no second Product interpretation of native scope. A fresh consent
reconstruction captures only immutable original/prerequisite operands in a local
variable. Final authorization still obtains new selected/closure GETs and native
rules, compares their exact content, and observes each accepted predecessor's
current PR and canonical Memory. Retained/restarted intents start cold or take
their existing observation-only recovery route. No capture is persisted.

`facts` consumes the actual response authenticated by `owned_repository` rather
than immediately fetching that repository again. Only the same stage's exact
response is supplied to the existing Free-private-plan validator. Ordinary
standalone/signed observations remain independent. Personal PR detail validates
both head/base numeric ID, node ID and name itself; the redundant preceding
repository GET is removed only for the explicit personal forge mode.

Product `provider` constructs its initial plan from its actual adapter snapshot.
The initial exact decision evaluates that plan with a late actual M1/M2 safety
observation; the post-SUBMITTED plan and final default `decide` remain new
observations. PR intent therefore has three plans/three adapter inspections,
instead of four/five. No ALLOW verdict is cached.

PersonalAuthority proof creation and verification each obtain their own actual
`c.live` observation and pass it through the existing ProductAuthority validator.
Accounting `flow.live` still has its read-only wrapper, independent closing
Memory/identity/consent comparison and late expiry fence. Worker receipt checking
uses the one canonical snapshot obtained after runtime observation (the actual
episode view in accounting mode); assignment and Guard use that same subject.
Accounted receipts still require SYNCED ownership, generation, assignment result,
independent stopped context and current permitted Guard state.

New CI/REVIEW/CORRECT confirmation reuses its immediately completed cold preview
admission through an invocation-local argument. It still performs the native
current policy/base/PR/check observations and role-specific handoff. A retained
entry defaults to cold or its original stopped-stage recovery path. CI is
qualified once after review-context callbacks, then its deterministic binding
uses that exact result. A changed SHA, missing CI or rejected review still refuses.

Completion replaces whole-future-inventory `c.fresh` with the existing checkout,
administration/governance, cold Product review and selected native-closure checks.
Its final subject is taken after merge status observation, which may checkpoint.
REPORT preview consumes the acceptance already established by track status,
preserving the selected explicit runtime; confirmation consumes that same actual
original observation instead of discovering the track again. REPORT's later
after-reservation historical acceptance remains a full check: the active overlay
cannot borrow a pre-reservation subject. Its pre-effect/in-flight distinction,
actual comment observation and no-duplicate recovery remain unchanged.

Status consumes a successful acceptance's actual closing canonical subject;
unfinished windows still inspect actual Memory. NEXT keeps its independent
current native readiness, separate consent/window, base checks around owner
release and restart/handoff checks. No accepted snapshot is carried across that
canonical transition. The separate cold `accepted`, current late `accepted` and
REPORT-overlay judgments are retained because they have different subjects.

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

## Residual R1–R5 release after27ca278

This section supersedes the earlier execution-count projections, not the retained
historical measurements. The generic M3 policy/Memory APIs and persistent stores
are unchanged. `B` means same-stage observation reuse; `C` pure projection;
`A` a retained separate boundary; `D` an explicitly unoptimized possibility.

| Owning path | Removed execution / actual replacement | Class and boundary |
| --- | --- | --- |
| `PersonalPublication.provider → proof → validate_proof` | Pass its actual admitted row for source/protection/operation proof construction instead of inspecting Memory again for each artifact | B; no canonical write in that construction |
| `validate_dispatch → record/live/current_source/record/record` | The actual live row supplies original/source/ref operands; full cold entry and independent post-upload observation remain | B inside each boundary; A between boundaries |
| `reauthorize → native submit → initial _authorize → decide → plan` | Qualified personal callback supplies its actual same-stage ref observation; omit the adjacent initial plan. Invalid/absent callbacks and signed ports retain the original full authorization | B only on the closed personal callback path |
| `submit → closure → _authorize → upload → _authorize → checked_ref → CAS` | Full M3 before FIRST object POST and independently after upload are retained; both exact action IDs and expected-old checks still fence mutation | A; normal fresh personal publication has four full plans and two native authorizations |
| `write_authorized → record` | Compare the actual private row with the already qualified immutable consent; do not reparse/hash its self-generated token per object | B/C; one fresh actual Memory inspection, current claim/credential/permit/deadline/hazard/Budget per write remain |
| `Product.qualifications → qualified / verify_review → review_context → qualified` | Authenticate one actual latest CI and one stopped independent review; pass CI into context/binding projections | B/C after fresh pre-merge CI |
| `qualifications → proof / verify → qualifications again` | Existing ProductAuthority consumes deep-copied typed facts, exact view, current latest receipt/worker identity, actual canonical assignment/Guard and UTC. It is bound to the SAME active Budget; defaults/restart still authenticate fully | B/C, never a cached ALLOW or persisted authority |
| `qualified → record + allowed + ci_identity` | One actual canonical snapshot supplies those projections; protected #21 receipt and exact PR/SHA/status/age checks remain | B |
| `native observation proof → ci_identity → record` | Use the actual post-query canonical observation already supplied to the semantic validator | B; native stability checks remain independent |
| `validation_context → provider.plan → observe → request → plan → decide → plan` | Borrow ONLY the initial actual plan with exact active Budget/provider/task/request binding; each personal request consumes one full plan with late actual Safety | B; signed/candidate/default paths unchanged |
| `native source.observe → evaluate → closing request` | ALWAYS construct a new full closing plan, compare the exact EvidenceRequest, recheck policy/provenance/source/owner/Guard | A; no borrowed operand in closing/reobserve/recovery |
| `fresh MERGE proposed → native_reviews; refresh_merge_ci → native_reviews again` | Reuse entry's raw native review operands for internal proof projections. Retained/restart observes them anew. Final boundary always refreshes eligibility; removed/replaced actors cannot satisfy old evidence | B inside fresh preparation; A at final effect boundary |
| `completion_preview → qualified → verify_review / validation_binding` | One actual CI operand supplies both projections | B/C; source/Memory lock handoff, fresh merged result and newly written completion receipt validation remain A |
| `REPORT preview → local cold roles + full track.status` | Qualify only the selected accepted receipt, actual closing canonical subject and current source/Guard seal; targeted native original/closure, no unrelated future discovery | B; report makes no successor READY claim |
| `REPORT reserve → SUBMITTED → final_boundary → accepted` | Full selected acceptance check AFTER reservation is retained, including #67's exact submitted overlay; pre-reservation snapshot is not borrowed here | A, different canonical subject |
| `REPORT POST → observed_report inventories → own_report_delta → settlement` | Keep both consecutive comment inventories, exact target/body/actor and causal original delta, original claim and durable action/publication/Guard settlement | A; reobservation never POSTs again |
| `NEXT → next_preview/status → status again` | Fresh confirmation consumes that same actual admitted status; retained/restart obtains a new one | B only before release |
| `NEXT → handoff → apply_personal` | Keep current parent checkpoint/generation, stopped/effect checks, release, fresh base facts, complete actual successor discovery/policy/enrollment and attachment | A; no authority across owner release/new window |
| `historical accepted → default transport` | When an authenticated read port is already selected, use the existing read-only context instead of constructing a second credential/transport path | Replaces an in-scope wrong-port defect; GET only, exact repository checks retained |

Remaining D: default `PolicyProvider.plan/decide → authority.verify → record`
Memory reads are NOT eliminated by a global envelope-only verifier. Supplying
canonical observations across generic M3 inspection would introduce another
cross-layer operand contract. No such protocol or generic Memory redesign is
part of this release; those repeated reads remain disclosed costs, not new
independent security judgments.

Diagnostics preserve typed BudgetRefusal through discovery, personal reads,
forge response/proof adapters and actual known deadline paths. Inner refusals
followed by legitimate observation remain events. `effect.dispatch_requested`
means entering the effect adapter, not proof of on-wire delivery;
`effect.acknowledged`, `effect.observed`, and `effect.settled` identify separate
actual boundaries. Only the existing bounded private diagnostic whitelist is
extended. No A3 exception or remote outcome is reconstructed.
