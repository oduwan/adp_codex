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
