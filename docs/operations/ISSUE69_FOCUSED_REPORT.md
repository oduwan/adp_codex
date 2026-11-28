# Issue69: owning-operation simplification and focused evidence

Engineering report; the Issue69 handback binds final readiness and exact-HEAD
review receipts. This report concerns the
expanded P0–P3 engineering scope of Issue69 in existing Draft PR62. It does not
qualify the installed runtime, a real pilot, full H3 integration or Issue58.

## Source and scope

Baseline: `f5457d8054e9a8e32a0b43a200af16de760db07c`, tree
`52435f7611919460bdb875b43d1cc5bfff3d9cc4`.
Tested product candidate: `deed0a2f13c2949914be8403677751edc1eb6d6a`, tree
`810d3a584f8dedb84d6baeb45bfe1093fba567a2`, product subtree
`e4b431af66f42fd27ee0a4d4c67fb22d5328d389`.
Any later documentation-only handback revision identifies that same product
subtree separately; tests are not relabeled as executions of a later commit.

The owning operation trusts its dedicated local product/service directories
against malicious same-UID historical interference. This is an explicit trust
assumption, not a tested protection. Cold/restart qualification authenticates
the historical basis. Cooperative canonical transitions, mutable external
GitHub conditions, current M1/M2, original deadlines and revocation still fence
each effect. Nothing renews an old grant or retries an uncertain mutation.

## Removed work and retained boundaries

The [call graph](EXTERNAL_LIFECYCLE_CALL_GRAPH.md) records baseline callers and
the replacement paths. Publication now reads the selected original and its
actual native prerequisite closure, using the original M4 decoder. All three
originals are supported; future unrelated Issues are not publication authority.
Cold independent stopped review is qualified once per owning operation;
subsequent raw scope, native prerequisite PR and actual Memory observations stay
fresh. Default/signed inventory and policy semantics remain independent.

Normal and H3 publication use one direct late write fence. Product stages share
their actual canonical snapshot, authenticated repository response and newly
built policy plan within the stage. Product uses the publication original
decoder; review-context binding uses its one qualified CI observation. New
execution confirmation reuses its completed cold admission; restart and stopped
recovery retain their existing checks. Completion drops whole-future discovery
but keeps checkout/admin/governance, current original, review and merge checks.
REPORT drops duplicate acceptance/discovery while retaining the full
after-reservation acceptance check and Issue67's pre-effect/in-flight distinction.
NEXT does not carry an accepted observation across owner release/handoff.

Preserved: independent exact-SHA judgments; selected scope/native edges; actual
required CI; M1 owner, generation, task epoch and assignments; current M2 permit,
limits, deadline and revocation; fresh policy after SUBMITTED; credential and
recipient binding; source/ref/index/worktree handoff; object integrity; one-use
dispatch; exact expected-old-SHA native CAS; current post-effect observation;
settlement; UNKNOWN/no-duplicate recovery; separate acceptance/NEXT consent.
No persistent positive cache, authority record, second journal or service was
added. P0's bounded latest diagnostic projection is never read as authority.

## Request model and measured margins

Limits stay **10 seconds/request, 150 seconds/operation, 128 attempts**. Existing
smaller query deadlines remain binding, including the five-second native CI
evidence query. Older stored consent limits are not enlarged.

For the measured one-page, one-governance/default-branch, three-original chain,
let `d = K - 1`, where K is selected Issue plus actual transitive predecessors.
Cold native accepted-PR observation uses five GETs per predecessor; the late
boundary uses one current exact-PR GET per predecessor. The historical Worker
and prior-Memory subjects in these small native fixtures are explicitly seeded
synthetic acceptance, not genuine historical runtime qualification.

| PR intent phase | Normal one-page HTTP | Freshness/meaning |
| --- | ---: | --- |
| Consent reconstruction | `17 + 11d` | Selected scope/closure, current rules, actual cold predecessor native observations, unique source PR inventory |
| Initial M3 plan | 1 | Same-stage actual adapter snapshot; late current safety before decision |
| PREPARED/SUBMITTED reauthorization | 1 | New plan after canonical transition |
| Final authorization | `17 + 7d` | Fresh scope, predecessor PR/Memory, policy/base/permissions, competing PR inventory and final default M3 decide |
| POST | 1 | Original one-use claim; current late fence |
| Observation/settlement | 12 | Exact marker/body/PR, current source/base and durable settlement |
| Total | `49 + 18d` | 49 / 67 / 85 for original Issues1 / 2 / 3 |

For this same bounded closure/object shape, publication totals are 56 / 81 /
106; the verified private-plan-disabled Issue3 case uses111. Each includes
object upload, exactly one expected-old CAS and OBSERVED settlement. Issue3
normal PR leaves43 requests; private-plan-disabled publication leaves17. These
are measured fixture margins, not a promise about arbitrary repository sizes.
The supported Free-private PR source path adds at most11 reads in this stated
shape (three facts boundaries and two original-rule boundaries): at most96,
leaving32. That last figure is a static bound, not a measured private-PR run.

General paging is finite and still validated. M4 original reads use
`2K + sum(pages of four collections per Issue)` plus repository/control reads;
the raw-map bound remains81. Filtered PR inventories retain complete paging,
unique identities and their256-row bound; rule inventories keep their existing
bounds and refuse incomplete evidence. Additional pages consume the same Budget.
The same Budget admits at most128 requests/transports; a subsequent refused
entry may be recorded as attempt129 and must not dispatch. This is not a
guarantee that every maximum-page input completes. No scenario-specific predictor or
second budget ledger was added. The existing negative object-count lower bound
still refuses if known object POSTs plus the mandatory CAS cannot fit.

## Comparable measurements

CPython3.11.10; owned disposable Git fixtures; synthetic native transport;
actual Git objects, canonical Memory and CAS. Setup is excluded from operation
times. Each complete-publication comparison has one sample per revision, so
neither a median nor a causal speedup is claimed for it. The supported Issue1
fixture, component and effect are matched; source revisions differ and timing
conditions are uncontrolled. Call-count reductions are observed directly.

| Equal-work full-cold Issue1 component | Baseline f5457d8 | Candidate deed0a2 |
| --- | ---: | ---: |
| Publication wall seconds | 49.6407 | 33.0833 |
| HTTP attempts/transport calls | 102/102 | 56/56 |
| M3 plan constructions | 7 | 5 |
| ADP Git helper invocations | 3432 | 2285 |
| Memory inspections | 165 | 100 |
| Parent CPU seconds | 5.3121 | 3.0092 |
| Reaped-child CPU seconds | 13.8288 | 8.6998 |
| Git helper inclusive seconds | 16.0903 | 10.0320 |
| Memory inclusive seconds | 13.1965 | 7.3915 |
| Request latency median / p95 / max seconds | .1003 / .4206 / .8190 | .0994 / .3345 / .4241 |
| Result | CAS1, settled | CAS1, settled |

The earlier72-request intermediate sample is retained separately and is not
substituted for the final56-request sample. Cumulative diagnostic snapshots are
selected by matching operation name, never summed with their preceding preview.
Git, Memory, provider and other work spans overlap; their inclusive durations
cannot be added to estimate wall time. Git-helper counts exclude uninstrumented
fixture-server commands. Parent and reaped-child CPU are reported separately;
child CPU includes fixture-server Git helpers.

A separate equal seeded-PR fixture measured53→49 transports,1243→1203 Git
helpers and42→42 actual Memory inspections. Logical plan constructions fell
4→3 and adapter observations5→3. The corresponding single wall samples were
26.547→24.366 seconds; those seeded samples omit genuine cold Worker verification.

A real-Memory, zero-HTTP proof+verify component, five samples per revision,
measured10→5 Memory inspections and160→80 Git helpers per pair. Wall
median/p95/max: .7718/1.1757/1.1757→.3824/.8038/.8038 seconds. Parent CPU
medians: .1900→.0936 seconds; reaped-child CPU medians: .6127→.3047.
The first sample includes creating the immutable proof; subsequent samples
read the same immutable proof. With n=5, p95 is descriptive nearest-rank/max,
not a reliable population estimate. Request latency uses nearest-rank p95.

Configuration-loading cost inside these injected root operation measurements
is0; initial configuration/construction outside that scope is not inferred.
P0 separately tests bounded fallback/loading diagnostics. Native CI's inner
query remainder is unavailable where not retained; no sub-budget margin is
invented from the root operation's remainder.

The small three-Issue fixtures measured the following root operation costs.
Each cell is actual HTTP transports / wall seconds, not an end-to-end pilot.
Every normal PR leaves at least43 requests; every publication leaves at least17.

| Operation | Python3.11.10 | Python3.12.16 |
| --- | ---: | ---: |
| Issue1 publication | 56 / 48.09 | 56 / 27.75 |
| Issue2 publication | 81 / 31.61 | 81 / 32.78 |
| Issue3 publication | 106 / 34.79 | 106 / 35.62 |
| Issue3 verified private-plan-disabled publication | 111 / 50.18 | 111 / 35.59 |
| Issue1 PR | 49 / 24.62 | 49 / 30.97 |
| Issue2 PR | 67 / 25.82 | 67 / 34.05 |
| Issue3 PR | 85 / 40.87 | 85 / 26.80 |
| Native CI with seeded exact PR | 49 / 37.53 | 49 / 19.59 |

The Issue1 3.11 publication method completed before its two-method group's
outer watchdog interrupted Issue2. That individual result is retained as a
completed method; its aggregate remains TIMEOUT/NONPASS. Issue2 was later
completed separately. The isolated CI312 pass does not erase its earlier
UNKNOWN/refusal. These synthetic native checks exercise #21, not live project CI.

## Focused tests and historical outcomes

| Focused method inventory | Python3.11.10 | Python3.12.16 |
| --- | ---: | ---: |
| Runtime/diagnostic controls | 32 PASS | 32 PASS |
| Current lifecycle/canonical/read/recovery boundaries | 80 PASS | 80 PASS |
| Publication controls, including four complete CAS/settlement cases | 11 PASS | 11 PASS |
| Three original PR operations, permission-change refusal and native CI | 5 PASS | 5 PASS |
| Applicable M3, native rules, publication-fence/original/recovery regressions | 43 PASS | 43 PASS |
| Distinct qualified methods | **171** | **171** |

This is a union of documented focused results and audited unchanged-source/
called-branch reuse, **not one171-method run at the final HEAD**. The80-method
3.11 selection ran on the subsequently committed identical product/test bytes;
3.12 ran at deed0a2. P0 results remain bound to b5baacc and unchanged called
branches; applicable P1 controls remain bound to c51ed60 and unchanged called
branches. Changed fixture-dependent controls were run separately on deed0a2.
Source/fixture applicability and each original outcome are retained privately
and independently audited. Six selected 3.11 PASS observations come from
nonzero aggregate runs: five completed unaffected P1 methods and the completed
Issue1 publication method above. Neither aggregate is called PASS. No selected
3.12 PASS comes from a nonzero aggregate. Unfinished or
unentered affected methods were later run on fresh disposable fixtures with
unchanged product limits and bounded supervision. No old intent, counter or
execution was reset.

Each selected qualification record is a PASS observation. This does not erase
the separate historical FAIL/ERROR, interrupted UNKNOWN/NOTRUN or outer TIMEOUT
outcomes described below; no SKIP is credited PASS. Group denominators are
parent methods; subtests do not enlarge them. The retained engineering index
has25 nonzero supervised runs, including deliberately red baseline controls,
fixture/procedure errors and outer watchdog interruptions. This is a process
count, not25 product defects or25 distinct failed methods.

Static prescribed inventory preflight validates39 manifests/678 M7 method IDs
and preserved accepted source seals without executing that inventory. The
portable scaffold check passes. Full CI, full M1–M7, Issue58, installation and
genuine pilot execution are **NOTRUN** for this task.

Preserved development failures include the reproduced missing diagnostic,
late credential-callback canonical-fence defect, restored default independent
private-plan observation, fixture interface/shape/clock errors, and a private
measurement driver's missing argument. Later passes do not rewrite those runs.
The CI312 concurrent run returned UNKNOWN with an observed inner
REQUEST_DEADLINE_EXHAUSTED event (47 attempts/46 transports,53.630 seconds at the
root), not a proven150-second or128-request exhaustion. An inner deadline
refusal was observed and the operation returned UNKNOWN; no typed budget
refusal propagated from the root (`final_refusal=null` was recorded). The
underlying slowdown remains UNKNOWN. Bounded outer test-watchdog timeouts are
separate nonPASS outcomes.
Fresh isolated focused runs use unchanged source, assertions and deadlines;
no historical campaign or M2 state is reset.

A/A2/A3 evidence is unchanged. A3's actual exception and request/effect history
remain UNKNOWN. Its expired uncertain PUSH has not been retried or reconciled.

## Architecture census and review

Counted all100 `adp/*.py` files. Nonblank/noncomment counts include docstrings;
function counts include nested definitions. `require` calls/if statements are
syntactic counts, not an invented count of independent security guarantees.

| Metric | Frozen PR52 13fd859 | Issue69 baseline f5457d8 | Candidate deed0a2 |
| --- | ---: | ---: | ---: |
| Physical lines | 26210 | 26726 | 27034 |
| Nonblank/noncomment lines | 23499 | 23994 | 24271 |
| Functions | 1240 | 1245 | 1257 |
| Classes | 249 | 248 | 249 |
| If statements | 1931 | 1997 | 2024 |
| require calls | 2324 | 2399 | 2401 |

Growth versus this release's baseline is308 physical/277 nonblank lines and12
functions. It is disclosed, not claimed as a LOC reduction. Retained additions
are bounded diagnostic retention/privacy, explicit same-stage observation
carriers, the single late current fence and invocation-local prerequisite
qualification. They replace repeated whole discovery, duplicate Product scope
interpretation, normal/H3 per-object verification paths and equivalent M3 plan
reconstruction. The policy engine, canonical Memory, existing private consent
and execution journal remain the same authorities. There is no parallel
permanent implementation or authority cache.

Every product-file net addition is accounted for below (unchanged-net files
still contain replacements). This is a source census, not a claim that adding
lines by itself simplifies architecture.

| Retained change | Net physical lines versus f5457d8 | Replaced work |
| --- | ---: | --- |
| runtime_limits, personal_cli, personal_network | 186 | Lost deque-only measurements and opaque budget refusals; one bounded diagnostic projection, closed labels and typed refusal accounting |
| network_git | 21 | Duplicate personal target-ref read and global PUSH ref inventory; same-boundary native observation with unchanged signed fallback |
| personal_publication | 39 | Repeated full discovery/stopped review, separate normal/H3 write paths and duplicate count-admission branches; shared selected original and checkout functions |
| personal_track | 27 | Repeated cold predecessor verification and whole-future completion scan; explicit immutable operands plus actual late PR/Memory checks |
| policy, authority, product review/read frame, workers, report, metadata/rules and forge | 35 | Equivalent plan reconstruction, proof/generation/assignment snapshot fan-out, duplicate Product original implementation and same-stage repository reads |

Independent original semantic implementations fall from two (Product and
Publication) to one. Per-object publication write implementations fall from
two (normal and H3) to one. The M3 decision engine remains one. Entry/closing
and pre/post-upload fences remain distinct; consolidation does not count their
deletion as an optimization. New persistent authority records/journals/services:
zero. New bounded latest diagnostic projections: one, observational only.

Independent combined source/security review approves exact deed0a2 without
blocking findings. Receipt SHA256:
`6a7d0385b4c7f79b81258d72d0982656151b641405f5888492c0a9e71e270231`.
323-path source-manifest SHA256:
`1bf666771869d23c2a8d3944455f878c25cfedf156e37ebe16cbb580170afdaf`.
The final exact-HEAD source and independent evidence receipt hashes are bound
by the Issue69 handback after this report is frozen. Private raw evidence and
receipt hashes remain outside Git; no credentials, host identities or
transcripts are published here. Operator integration and later separately
released pilot B remain external decisions.

## Residual R1–R5 engineering revision

The operator's later static findings supersede any implication that the27ca278
handback completed MERGE/completion/REPORT/NEXT qualification. Original results,
failed attempts and review receipts remain historical; no prior FAIL, ERROR,
TIMEOUT, UNKNOWN or missing evidence becomes PASS.

The residual call paths and retained boundaries are documented in the updated
[call graph](EXTERNAL_LIFECYCLE_CALL_GRAPH.md#residual-r1r5-release-after27ca278).
No generic M3/Memory observation protocol, new persistent cache, journal, store,
provider, role or execution controller is introduced. Existing private evidence
is authenticated at entry/restart; invocation-local typed operands cannot be
used by a new public operation's Budget. Current mutable source, native policy,
credentials, owner/generation, M2/deadline/revocation, dispatch and uncertainty
fences remain authoritative.

Focused late-stage fixtures explicitly seed stopped Codex-shaped receipts,
reviewed local source, published refs and existing PRs. They execute production
MERGE/native observation/settlement, completion, REPORT/comment reconciliation
and actual NEXT enrollment/owner release for the original three-Issue graph.
They do NOT qualify Worker execution, source development, publication/PR creation,
real GitHub CI, full H3, #58 or M8. No actual Worker dispatch is permitted by the
fixture. Query allowance5000ms and product10/150/128 remain unchanged.

Historical development observations include an aggregate300s supervisor TIMEOUT
and a later Case2 MERGE refusal before submission. Independent forensic analysis
established the immediate5s native-observation deadline failure after
`source.observe` returned, with aggregate time/request allowance still available.
It did not establish complete native evidence, nor attribute the overrun to
fsync, storage, scheduling or attestation. That underlying cause remains UNKNOWN.
Fresh disposable RAM-backed fixtures may qualify process-restart/Git/CAS behavior;
they do not qualify disk latency or host power-loss durability. Before/after
comparisons must use the same fixture/storage environment; a disk-to-RAM change
is not evidence of a product speedup.

Final source identities, focused counts, comparative measurements, private
integrity manifests, final review and readiness are supplied by the consolidated
Issue69 handback. Missing mandatory results remain nonPASS until actually run.

## Consolidated residual R1–R5 qualification

This is focused Issue69 engineering evidence, not #58, M8, installation, real
Codex execution, live GitHub CI, or pilot acceptance. Original A/A2/A3 and all
nonPASS records remain unchanged. No expired intent is retried or reconciled.

Source attribution is explicit. The complete positive late-stage component
runs tested clean `d0ce3ea8f57f39123aec963c5013a8211f211ca1` (tree
`df0b270be692e7b959f96791023a98ce80ada614`, product
`60baedb45760075e7d302066db6a5178fd6d1893`). Subsequent product changes are
only five lines: typed `BudgetRefusal` passthroughs in publication and
enrollment, plus the existing-type import. No successful operation path, limit,
fixture or assertion changed. Those measurements retain their exact d0 identity;
independent branch-equivalence review establishes applicability, not execution
on a later SHA. Directly affected checks tested `bb610c6064f0d1398df5a30101315e30a9673f59`
(tree `06a8d19feb8344c748ccc00a5ce27030691e0192`, product
`49096d8630a19b2faf7f4f8de0d41be3a93bbb1b`). The final handback binds the
subsequent documentation-only HEAD/tree. No source approval is silently reused
for an unreviewed changed HEAD.

| Finding | Disposition |
| --- | --- |
| R1 publication | Same-subject row supplies proof construction and dispatch projections. The personal callback skips only adjacent initial native reauthorization; four full plans/two native authorizations remain, including fresh pre-first-POST and post-upload/pre-CAS checks. Each object still checks actual canonical subject, permit/deadline/revocation, claim, credentials, transport and uncertainty. No ALLOW is memoized. |
| R2 MERGE/REPORT | Authenticate actual independent Worker and applicable CI once at the owning stage; existing ProductAuthority carries only typed immutable operands bound to exact active Budget/view/receipt/assignment/Guard. Current native principals remain fresh. Borrow initial actual validation plan only within the exact provider/task/request/Budget; closing query/request remains independent. Default/signed/candidate semantics stay unchanged. |
| R3 completion/REPORT/NEXT | Completion shares one CI operand. REPORT authenticates selected acceptance and its closing subject, without whole-future-track discovery or successor READY claims. Post-reservation acceptance and both stable comment inventories remain. NEXT shares adjacent confirmed admission only before release; retained/restart reobserves, current parent checkpoint/generation and post-release enrollment remain fresh. Existing selected historical read port is GET-only, eliminating an actual wrong-port defect. |
| R4 diagnostics | Known terminal budget reasons survive discovery, native/proof adapters, publication policy and successor discovery. Opaque errors remain fail-closed. Legitimately caught inner refusals remain observed events. Dispatch-request, acknowledgment, observation and settlement markers are distinct; dispatch-request does not prove on-wire delivery. A3's historical exception remains UNKNOWN. |
| R5 evidence | Actual production MERGE/observation/settlement, acceptance, REPORT/comment/settlement, and NEXT enrollment/owner transition executed for the three originals on both Python versions. Seeded stopped receipts/source/published refs/PRs and synthetic transport are disclosed; no complete-operation mock or actual Worker dispatch. |

Fresh boundaries retained: cold entry/restart; initial ticket/native prerequisite
closure; current source/index/worktree and policy/ref/permission/credential
checks; each actual write's canonical M1/M2/claim/stop/budget fence; pre-upload
and post-upload/CAS; fresh pre-merge native CI and final native review eligibility;
post-effect observation/settlement; REPORT reserved overlay; parent release and
new successor enrollment/scope. Full next discovery is necessary to establish
new original scope. Generic M3 verifier-to-Memory reads remain explicitly D
(unproven optimization): this release adds no cross-layer observation protocol
or general Memory redesign, and does not portray those costs as independent new
security judgments. The call graph lists every removed and retained path.

### Focused outcomes and provenance

Selected denominator **90 distinct methods per interpreter**, all PASS; FAIL,
ERROR, SKIP, TIMEOUT, NOTRUN and UNKNOWN are each0 **within this selection**.
This is not a claim about the full unexecuted suite.

| Selection | Python3.11.10 | Python3.12.16 |
| --- | --- | --- |
| Snapshot/review/CI/diagnostic/NEXT controls | 48 unchanged9f PASS + changed terminal diagnostic1bb PASS | 49bb PASS |
| Affected publication/CAS/CI/accounting/rules/PR/report methods | 39bb PASS (167.464s) | 39bb PASS (171.069s) |
| Changed inventory/seal preflight; full runner explicitly trapped | 1bb PASS | 1bb PASS |
| Actual three-original late stages | 1d0 PASS (423.574s),27 completed operations | 1d0 PASS (352.839s),27 completed operations |
| Scaffold check, separate from method denominator | PASS | PASS |

The 3.11 unit run actually executed49 methods at9f; its one subsequently
extended diagnostic method is superseded by the bb run, not counted twice.
The other48 are reused with unchanged method bodies and demonstrated
exception-only source applicability. No repeated171-method campaign occurred.
The additive M7 inventory is694 distinct IDs (previous678 all retained), D4 is99
(previous83 retained). Accepted193 M1–M6 source seals remain intact; full suites
and CI workflows are NOTRUN under this release. No SKIP is promoted to PASS.

On bb both lanes separately completed publication originals1/2/3 and the private
Free Issue3 case through native Git upload/CAS/settlement: full Budget attempts
and transport calls55/80/105/110; remaining73/48/23/18. Exactly four plans/two
native authorizations each. 3.11 publication operation wall seconds
8.907/9.595/9.023/9.498;3.12 9.352/9.499/9.247/9.534. Direct native wrapper
counts55/73/91/96 exclude the other selected predecessor-read port; total Budget
transport counts are authoritative. The retained prior full totals56/81/106/111
are historical measurements, not same-environment fresh baseline timing.

The new NEXT negative method invokes actual `next()` with narrow admission
prerequisites and unreachable effect sentinels, real immutable intent storage
and lock. Changed parent head/generation refuses before handoff/enrollment;
retained snapshot/completion requires fresh status and refuses drift. It does
not qualify successful reconnect or lost response. Separate retained controls
cover unknown REPORT/no replay, lost Git acknowledgment, exact CAS race, source
and dependency drift, credentials/permissions/policy, current owner/generation,
expiry/revocation, missing/stale/foreign CI and original finite accounting.

Independent raw evidence audit verifies both actual handoffs preserve the
entire Guard tree, tasks/assignments and execution history; released parents
remain unchanged at final Issue3. All12 stopped contexts per lane are distinct
and internally bound to request/raw/stop/receipt records. These are synthetic
receipt bindings, not genuine supervisor/Worker proof. Native loose merge
objects have exact [base,source] parents and reviewed tree. Successor links,
plans, base, setup consent and generation1 owner match; there is no run/tasks
before new scope. REPORT success-repeat snapshots are byte-identical and no
second comment is created. That success repeat is not a lost-response experiment.

### Measured operations

Both lanes use the same existing owned tmpfs for fresh disposable state, real
fsync/Git/Memory/Guard, query allowance5000ms, and unchanged10/150/128. No mount,
privilege, tool, security or product-limit change occurred. Disk latency and
host power-loss durability remain NOTRUN. Cold historical H3 and real Codex
Workers are not qualified by these component fixtures.

Each row below is a completed actual operation; tuples are original1/2/3, or
1→2/2→3 for NEXT. Attempts equal actual transport calls in every positive row.
All27 roots/lane returned, telemetry dropped/errors/refusals were zero.

| Operation | HTTP | M3 plans | Memory inspections | Git helper invocations | Wall seconds 3.11 | Wall seconds 3.12 |
| --- | --- | --- | --- | --- | --- | --- |
| MERGE preview | 22/33/44 | 0 | 32/36/40 | 572/726/888 | 4.341/5.250/5.836 | 3.331/4.339/5.266 |
| MERGE effect + settlement | 82/100/118 | 5 each | 193/198/203 | 3792/3961/4139 | 30.076/27.943/28.101 | 22.390/23.507/25.487 |
| Completion preview | 20/31/42 | 0 | 34/38/42 | 621/775/937 | 5.064/5.114/5.568 | 3.505/4.933/5.616 |
| Completion apply | 25/36/47 | 0 | 39/43/47 | 784/938/1100 | 7.499/6.884/6.627 | 4.553/5.537/6.445 |
| REPORT preview | 22/33/44 | 0 | 5/9/13 | 148/302/464 | 1.252/2.115/2.896 | 1.035/1.870/2.906 |
| REPORT POST + settlement | 67/89/111 | 3 each | 102/110/118 | 2251/2559/2883 | 18.887/18.005/20.497 | 13.919/15.484/17.667 |
| REPORT reobserve | 6 each | 0 | 6 each | 96 each | 0.757/0.611/0.555 | 0.521/0.574/0.528 |
| NEXT preview | 53/59 | 0 | 5/9 | 234/410 | 1.919/2.860 | 1.481/2.462 |
| NEXT enroll + release | 114/121 | 0 | 26/30 | 1058/1234 | 7.194/8.779 | 6.101/7.449 |
| New unreviewed successor status | 36/42 | 0 | 5/9 | 255/435 | 1.688/2.882 | 1.563/2.608 |

Worst positive request margin is NEXT2 with7 requests; MERGE3 leaves10 and
REPORT3 leaves17. Minimum measured operation time remaining is119.925s on3.11
and124.513s on3.12. These finite single-page fixture paths complete; seven
requests is narrow headroom, not a guarantee for arbitrary additional pages,
checks or concurrent changes. Larger/incomplete paths remain bounded/refuse;
no speculative request predictor or additional accounting system was added.

Parent CPU, waited-child CPU, endpoints and actual remaining allowances are
retained per operation in the sealed measurement evidence. Existing Git,
Memory, policy and network work durations are inclusive/nested; do not sum them
or infer exclusive time. No exclusive nested attribution was fabricated. With
one sample per revision/workload, no operation p95 or causal speedup is claimed.
Request latency median/p95/max uses actual per-root samples and nearest-rank p95.
| Lane | Pooled request samples | Median seconds | p95 seconds | Max seconds |
| --- | --- | --- | --- | --- |
| 311 | 1409 | 0.000819 | 0.011262 | 0.159088 |
| 312 | 1409 | 0.000643 | 0.009728 | 0.124860 |

These are pooled mixed-operation synthetic request samples, not real GitHub network latencies. Per-root distributions are retained separately.

### Comparable historical baseline

Same Python3.11, tmpfs, fixture bytes, one original, private Free policy and
actual component implementations: historical production `27ca278` is unchanged
(the two new test files are explicitly untracked). Comparison data are samples,
not a controlled host-load experiment; identical work counts are stronger than
wall-time attribution.

| Original1 operation | HTTP before → after | Plans | Memory | Git | Wall seconds before → after |
| --- | --- | --- | --- | --- | --- |
| MERGE preview | 22 → 22 | 0 → 0 | 40 → 32 | 700 → 572 | 3.843 → 4.341 |
| MERGE effect/settlement | 89 → 82 | 8 → 5 | 263 → 193 | 4978 → 3792 | 28.419 → 30.076 |
| Completion preview | 20 → 20 | 0 → 0 | 42 → 34 | 749 → 621 | 4.490 → 5.064 |
| Completion apply | 25 → 25 | 0 → 0 | 47 → 39 | 912 → 784 | 5.876 → 7.499 |
| REPORT preview | 54 → 22 | 0 → 0 | 26 → 5 | 584 → 148 | 3.545 → 1.252 |
| REPORT POST/settlement | 99 → 67 | 3 → 3 | 169 → 102 | 3429 → 2251 | 19.859 → 18.887 |
| NEXT | 129 attempts/128 transports ERROR → 114/114 completed | 0 | Not comparable: baseline stopped early | Not comparable | Baseline4.553 refused; candidate7.194 completed |

The baseline NEXT refused during successor discovery with145.448s still
available, after parent release and before enrollment completed. Its terminal
error was DISCOVERY_UNAVAILABLE wrapping demonstrated REQUEST_COUNT_EXHAUSTED.
There was no uncertain GitHub mutation or retry. Baseline full-NEXT cost is
NOTRUN; its shorter refused prefix is not a speedup. The retained observation
led only to the narrow typed-refusal repair, not new product functionality.

| Original1 component | Parent CPU before → after | Waited-child CPU before → after | Inclusive Git seconds before → after | Inclusive Memory seconds before → after |
| --- | --- | --- | --- | --- |
| merge.intent | 9.228 → 11.352 | 21.312 → 20.845 | 24.240 → 24.541 | 21.791 → 21.152 |
| completion.apply | 2.090 → 2.961 | 4.202 → 4.922 | 4.831 → 5.946 | 4.412 → 5.343 |
| report.intent | 6.804 → 7.586 | 14.488 → 12.622 | 16.563 → 14.851 | 14.044 → 11.740 |

Do not add nested Git and Memory spans to wall time. Host load was not exclusively controlled; the first candidate also overlapped a read-only source-metric collection. Call-count differences are demonstrated; causal runtime speedup is not established.

### Complexity and retained limitations

| Source | Physical / nonblank / nonblank-noncomment lines | Functions | Classes | AST if/ifexp | require calls |
| --- | --- | --- | --- | --- | --- |
| `13fd859` | 26210 / 23892 / 23499 | 1240 | 249 | 2503 | 2324 |
| `ac5ca6d` | 26365 / 24055 / 23662 | 1238 | 248 | 2554 | 2366 |
| `27ca278` | 27034 / 24692 / 24271 | 1257 | 249 | 2678 | 2401 |
| `bb610c6` | 27173 / 24828 / 24393 | 1259 | 249 | 2698 | 2409 |

All rows cover100 product Python modules. Against the residual start, physical lines grow139, nonblank-noncomment122, functions2 and classes0; against frozen PR52, physical lines grow963. No deleted test ID or denominator change hides that growth. New persistent mechanisms/authority records:0. The final five-line exception-only adjustment adds no function/class.

No new persistent authority record, cache, journal, database, policy engine,
service or controller. ProductAuthority remains the existing verifier with
invocation-local typed evidence; PersonalWorkers.accounted extracts the existing
canonical checks for reuse. These are the two added product functions. The
retained additions enforce exact operand lifetime/subject and refusal provenance;
they replace repeated stopped-Worker/CI authentication, adjacent policy planning,
self-generated proof reads and future-track discovery. Product code grew; this
is scoped duplication reduction, not a claim that global architecture or every
M3/Memory path shrank. AST branch/require counts are mechanical proxies, not
counts of independent semantic security judgments.

Historical nonPASS remain preserved and excluded from the final selected PASS
ledger. Early missing branch/PR fixture fields, clock mismatch and a mock field
were TEST_DEFECT; corrected within these focused fixtures. The discarded broad
controller-based builder is not R5 proof. Aggregate300s supervision TIMEOUT is
separate from product150s and native CI5000ms. The native CI overrun is proven at
the post-observe deadline predicate, but fsync/storage/scheduling/attestation
attribution remains UNKNOWN; no limit was increased. The wrong selected
historical transport is a source-confirmed in-scope PRODUCT_DEFECT, repaired via
the existing GET-only port. Its old underlying transport response is UNKNOWN.

Two terminal budget-mask regressions were reproduced as ERROR, preserved, then
corrected: publication FEATURE_POLICY_UNVERIFIED and enrollment
DISCOVERY_UNAVAILABLE. The first reproduction also emitted a secondary unittest
context-access error after its failing subtest; assertion nesting was corrected,
not acceptance weakened. The first private baseline driver accidentally queued
an imported class; it was stopped before any measured stage, with actual
wait/reap and descendant receipt retained. Its23.065s INTERRUPTED outcome is a
selection/procedure TEST_DEFECT, never PASS. Corrected baseline v2 remains ERROR1/1
at request exhaustion. An earlier unsupervised canceled development selection
has no confirmed stop receipt and is not qualification evidence. No historical
failure, uncertain effect, expiry or counter is reset by this work.

Private raw evidence remains outside Git. Public references are opaque artifact
IDs and SHA256, not host identities, paths, credentials or transcripts:

| Artifact | SHA256 |
| --- | --- |
| FINAL_FOCUSED_LEDGER.json | b57f0892f9bea19d5e755e758dc53a6420335a3d27bd67d93e4439693354aedb |
| d0 three-original3.11 log | 35eda5b55e2fe902965040553dfe5b7bb13ffb47d75aa5584911348ff8a1ce46 |
| d0 three-original3.12 log | 731d317fb1be2e8c660ee59e176b858981c9e57a9c84d77a99e105c17778bd80 |
| bb affected3.11 log | 50ce95fc4fffa3fd2c10ab094216b4b925e614c8bd98b430d1e6bf8b171a825b |
| bb affected3.12 log | 218d168d0e4750ac969764be6a498b63af534968f5f41ccfd7fea0491543af3d |
| historical baseline v2 log | 374fc29ce546876d5530f1d0a6c6810a572cf695e4ef1faad45db0ef27611164 |
| both-lane component evidence review | 89116d00139b46ca4e347a3192bf2c17abdddbd65ba19347881793b838001788 |
| baseline/applicability evidence review | 434e17332373eb51dbaaeec12f1dd4f37898baca42621d223030799a1aae804d |
| source metrics | 758858a1f99141ff414856f6bce7312aff838efec21ca60e16af7c699ec412c6 |

The ledger binds all selected log/stop/source manifests and historical log
hashes. Existing supervisor receipts record actual normal wait/reap or explicit
interruption; raw fixture Worker-shaped stops are not substituted for supervisor
receipts. Reviews are independently produced SHA-sealed records, not asserted
cryptographic signatures. Final exact-HEAD source/security and consolidated
evidence reviews, exact tree/product tree and the final readiness verdict are
bound in the Issue69/PR62 handback after this documentation is frozen.

Full qualification/#58, real GitHub/CI/Workers, disk/power-loss qualification,
managed installation, pilot B execution, #70 and #72 remain NOTRUN/outside this
release. Old qualifier descendant status remains UNKNOWN; no investigation or
termination assumption was made. Further pilot B preparation/execution requires
separate operator release. PR62 remains Draft, Issue69 open, no merge/install or
live pilot state change.

Changed-file inventory versus27ca278:15 product modules
`discovery_github`, `enrollment`, `execution_github`, `github_product`,
`network_git`, `personal_authority`, `personal_cli`, `personal_network`,
`personal_product`, `personal_product_review`, `personal_publication`,
`personal_report`, `personal_track`, `personal_workers`, `project_validation`.
Six focused test/fixture files: `residual_stage_fixtures`, `test_lifecycle_reuse`,
`test_publication_work`, `test_residual_reuse`, `test_residual_stages`,
`test_runtime_work`. Documentation: this report, the external lifecycle call
graph and additive D4 inventory. No core Memory/Guard or policy-engine source
change, new runtime store or unrelated fixture maintenance.
