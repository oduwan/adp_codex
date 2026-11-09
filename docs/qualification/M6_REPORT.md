# M6 qualification evidence

Public release: **NOT_AUTHORIZED**. This is a qualification candidate for
independent integration review, not acceptance into main, publication, tagging,
deployment, license selection or authority to operate any live product.

## Revision and evidence boundary

Accepted base and fetched remote main: `1eb00b3e94151a16a621aab20e71943b3ea2c8a1`.
The accepted [main CI](https://github.com/oduwan/adp_codex/actions/runs/42630969929)
was independently observed completed/success for that SHA. The issue worktree is
isolated on `feature/6-portability-qualification`; other worktrees were untouched.

Qualification code freeze **S**: `01263e65fa02de411190db29a9b79e37732f39c4`.
CI executed exact integration revision **T**: `02c4654c50859c415b65e03b24ae05d1412dd98b`, with the same Git
tree as S. Source binding was checked using the Git commit/tree API, not inferred
from a green badge. Engine tree: `4c9cba9228afa1bf052edf1a33a8338b3971d697`;
tests tree: `2de525f1d96401c2f605ecc8a9dfca7804345e42`.

The report is written after the observations below. Its own future commit SHA,
CI and approval cannot be embedded in these bytes. Therefore **Q12 is NOTRUN at
this evidence freeze: three scenarios PASS, two final reviews NOTRUN**. After
committing this report, the final exact report-bearing HEAD must receive fresh
Python 3.11/3.12 CI and both independent reviews. Their exact HEAD, CI URLs,
verdicts, integrity hashes and completed Q-matrix must be attested in
[Draft PR #12](https://github.com/oduwan/adp_codex/pull/12) without changing source
after approval. This report does not claim those future approvals. A changed
source/report invalidates the corresponding approval. A missing final attestation
means qualification remains incomplete, regardless of earlier green runs.

## Frozen denominators and observed tests

The [plan](M6_PLAN.json) was committed before qualification execution. It retains
**42 scenarios**, separately from **193 accepted regression IDs** and **17 added
M6 test methods**. All original accepted test and fixture Git blobs remain
unchanged. [The procedure map](M6_PROCEDURES.json) enumerates every scenario's
exact test IDs/external procedure; the runner checks that mapping before execution.
No exclusions, quarantines or expected failures are accepted as a suite PASS.

| Inventory | Python 3.11.18 | Python 3.12.16 |
| --- | --- | --- |
| Accepted M1–M5 | 193/193 PASS | 193/193 PASS |
| Added M6 | 17/17 PASS | 17/17 PASS |
| Complete suite | 210/210 PASS | 210/210 PASS |
| FAIL / ERROR / TIMEOUT / SKIP / NOTRUN / UNKNOWN / UNSUPPORTED | All zero | All zero |
| Fresh consumer installation | 6/6 PASS | 6/6 PASS |

CI environment: isolated GitHub-hosted Ubuntu 26.04.1 Linux jobs, Git 2.56.0,
fresh setup-python interpreters, fail-fast disabled between interpreters and
within unittest. [Code-freeze CI](https://github.com/oduwan/adp_codex/actions/runs/42643108208)
includes wheel installation, actual CLI invocation, scaffold validation and all
210 tests. Test-case statuses are public sanitized output; raw private test logs
and worker state never enter Git. Hashes below bind retained logs and structured
results. No mock is counted as genuine Codex runtime proof.

Plan SHA-256: `70e1a4aa476ebb0ffe952a590181be29b4fdb57356dbc4000dfb26f1ce31cf9c`.
Accepted inventory SHA-256: `7acfdd8147ccc138800866c366f16ea838d7d3623063fc232fa10a36f138a2d9`.
Procedure map SHA-256: `b29a94738a8f6e58eb663873dc22527130a097b3760727a3980b95cc0e4ae349`.

## Q01–Q12 requirement matrix

S/T mean the exact revisions above, not an unpinned checkout. R is the real-run
engine revision `7ec107534ee5acd8add576e94819163111ade6eb`. P is plugin revision S.
Evidence IDs below identify hashed private artifacts or public CI job logs. Each
scenario's concrete test IDs are retained in M6_PROCEDURES.json. PASS for a
negative case means the required refusal was actually asserted.

| Requirement | Status at evidence freeze | Exact source / environment | Executed procedure and observed result | Evidence | Original denominator and limitations |
| --- | --- | --- | --- | --- | --- |
| Q01 — Clean installation | PASS | S/T; CPython 3.11.18/3.12.16 Linux; P with Codex CLI 0.167.0 | Export pinned archive, empty outside cwd, ADP initially absent, fresh non-system-site consumer venv, build wheel then offline install, isolated import and actual CLI/help; install portable bundle in new local catalog, observe exact installed skill bytes/path enabled, remove only own plugin/catalog | E311/E312, I311/I312, PLUGIN | 5/5; existing trusted Codex/auth host, fresh project/catalog and package consumer. GUI UNSUPPORTED; model-driven skill use NOTRUN, not counted as PASS |
| Q02 — Unrelated policies | PASS | S/T; both CI interpreters | Independently initialize Atlas/Boreal identities/remotes/roots; differing base/branch/commit/check/PR/review/merge policies; Atlas completes, Boreal safely refuses publication with one of two required reviews; cross-repository replay and missing/conflicting authority refuse | E311/E312, mapped policy and cross-project tests | 4/4; verified synthetic external authority, not live branch protection; no second reviewer fabricated |
| Q03 — Read-only discovery | PASS | S/T; both CI interpreters | Controlled paginated GitHub fixtures produce native/inferred edges, ready/blocked/cyclic/duplicate/superseded/done/in-progress/needs-spec/unknown; permission/404/rate/partial and refreshed issue/PR SHA drift retained; byte/ref preservation tested | E311/E312, mapped discovery tests | 4/4; synthetic GET transport, no live target GitHub mutation |
| Q04 — Migration/recovery | PASS | S/T; both CI interpreters | Explicit v1→v2→v3 preservation, original assignments/counters, release/confirmed stopped-owner takeover, new generation, stale result refusal, interrupted journal replay and divergent remote refusal | E311/E312, mapped memory/fencing tests | 3/3; competing-clone/process-death simulation, no physical power-loss or separate-machine proof |
| Q05 — Concurrent lanes | PASS | S/T; both CI interpreters | Two unrelated projects enter a real thread barrier concurrently with isolated worktrees/control/memory/remotes; actual M1 assignments and M2 reservations, distinct synthetic Developer/Reviewer contexts; restart/delivery/HEAD drift cannot reuse approval | E311/E312, cross-project and fencing tests | 3/3; composite repository+assignment uniqueness; synthetic parallelism, not real concurrent Codex proof |
| Q06 — Genuine runtime | PASS | Historical f1ce67e6706c49b612e3fb1d09226b35745f6269; fresh R; Linux, Codex CLI 0.167.0 | Independently inspect retained original proof, transcripts, exact source/ref/check/stop receipts; one bounded post-fix authenticated codex exec Developer then independent Reviewer, actual check and approved exact product SHA | HIST, REAL, REAL_AUDIT | 2/2; one fresh invocation budget consumed1/1, parallel1, rounds2, worker300s; serial disposable contract only |
| Q07 — Guard/forensics | PASS | S/T; both CI interpreters | Exercise all accepted stall thresholds, finite proof and bounded reassessment then terminal refusal; only independently verified meaningful progress resets, changed-SHA review invalidated | E311/E312, mapped guard/recovery tests | 2/2; thresholds and schemas unchanged; no open-ended diagnostics |
| Q08 — Honest campaigns | PASS | S/T; both CI interpreters | Actual durable seven-case M2 campaign continues ordinary failure across restart; validation census includes UNKNOWN; quarantine/nonpass cannot count as effective PASS; safety/contamination/lost-stop halts remainder | E311/E312, accounting/campaign/validation tests | 3/3; seven-case rawPASS2 but effectivePASS1, FAIL1/ERROR1/TIMEOUT1/SKIP1/NOTRUN1 and quarantinedPASS1 retained. These inner negative outcomes are not suite failures |
| Q09 — Idempotency/reporting | PASS | S/T; both CI interpreters | Lost Git/forge/dispatch responses and crash/restart reobserved by CAS, exact PR marker/body/HEAD and comment; uncertain delivery refuses blind retry; source drift invalidates evidence; INTERNAL publishes zero reports | E311/E312, mapped ports/forge/recovery tests | 3/3; allowlisted bare Git and controlled forge fixtures; no live target GitHub write qualification |
| Q10 — Adversarial safety | PASS | S/T; both CI interpreters; R supported-host proof | Assert issue/comment/README injection cannot grant rights; paths/symlinks/Git administration/credential environment/permissions/self-review/stale SHA/containment and unsupported runtime refuse; fresh/cached/forensic secret-shaped summaries block before further checkpoint | E311/E312, REAL, preserved failures F1–F3 | 4/4; bounded recognizable-secret detector, not universal DLP or hostile-kernel/same-user defense; legacy disclosure requires operator remediation |
| Q11 — Unauthorized operations | PASS | S/T; both CI interpreters | Missing rights refuse force/rewrite/merge/deploy/release; even synthetically verified merge policy has no supplied execution backend; network push refuses before transport; unqualified validation refuses; no public tag/release/listing | E311/E312, mapped policy/refusal tests | 4/4; authorized local CAS only; refused network/production sandbox operations are not successful implementations |
| Q12 — Final integration/review | NOTRUN | S/T observations; final report-bearing SHA must be externally attested | Full210 both versions, clean installation/CLI/scaffold/docs CI PASS. Both independent final report-bearing HEAD reviews remain NOTRUN at report creation; external exact-HEAD attestation required | E311/E312, I311/I312; final PR attestation | 5 original scenarios: 3PASS, 2NOTRUN; no future approval inferred |

At this committed evidence freeze: **40/42 scenarios PASS, 2/42 NOTRUN**. This is
not a completed final qualification claim. Final status is resolved only by the
external exact-HEAD attestations described above; missing evidence is a blocker.

## All 42 scenario observations

| Frozen scenario | Status at freeze | Exact procedure evidence |
| --- | --- | --- |
| Q01.host-enabled-skill-discovery | PASS | PLUGIN |
| Q01.host-plugin-install | PASS | PLUGIN |
| Q01.portable-layout | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q01.wheel-311 | PASS | I311 |
| Q01.wheel-312 | PASS | I312 |
| Q02.cross-repository-replay | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q02.distinct-repositories-and-plans | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q02.independent-review-counts | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q02.missing-contradictory-policy | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q03.mixed-native-inferred-graph | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q03.pagination-incomplete-inventory | PASS | T: 3 mapped test IDs, both interpreters, E311/E312 |
| Q03.permission-rate-limit-404 | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q03.refresh-source-and-pr-drift | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q04.explicit-v1-v2-v3-preservation | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q04.handoff-takeover-generation-fence | PASS | T: 3 mapped test IDs, both interpreters, E311/E312 |
| Q04.interrupted-journal-divergence | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q05.bounded-concurrency-and-reservations | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q05.restart-and-exact-sha-review | PASS | T: 3 mapped test IDs, both interpreters, E311/E312 |
| Q05.two-unrelated-concurrent-lanes | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q06.historical-retained-artifact-audit | PASS | HIST |
| Q06.single-post-fix-real-runtime-proof | PASS | REAL_AUDIT |
| Q07.all-stall-thresholds-finite-terminal | PASS | T: 7 mapped test IDs, both interpreters, E311/E312 |
| Q07.independent-progress-reset-and-sha-invalidation | PASS | T: 6 mapped test IDs, both interpreters, E311/E312 |
| Q08.durable-finite-campaign | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q08.safety-lost-stop-halts-inventory | PASS | T: 3 mapped test IDs, both interpreters, E311/E312 |
| Q08.validation-all-outcomes-and-quarantine | PASS | T: 3 mapped test IDs, both interpreters, E311/E312 |
| Q09.forge-pr-comment-restart-drift | PASS | T: 9 mapped test IDs, both interpreters, E311/E312 |
| Q09.git-cas-lost-response | PASS | T: 2 mapped test IDs, both interpreters, E311/E312 |
| Q09.internal-zero-publication | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q10.credential-env-permissions-independent-review | PASS | T: 6 mapped test IDs, both interpreters, E311/E312 |
| Q10.paths-symlinks-git-administration | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q10.untrusted-issue-comment-readme | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q10.worker-output-credential-refusal | PASS | T: 5 mapped test IDs, both interpreters, E311/E312 |
| Q11.force-merge-deploy-no-authority | PASS | T: 4 mapped test IDs, both interpreters, E311/E312 |
| Q11.network-push-unsupported | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q11.public-release-not-authorized | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q11.unqualified-validation-unsupported | PASS | T: 1 mapped test IDs, both interpreters, E311/E312 |
| Q12.clean-install-cli-docs-ci | PASS | I311; I312; E311/E312 (S/T freeze; final CI external) |
| Q12.full-suite-311 | PASS | E311 |
| Q12.full-suite-312 | PASS | E312 |
| Q12.independent-final-head-code-schema-evidence-review | NOTRUN | Final PR attestation required |
| Q12.independent-security-design-review | NOTRUN | Final PR attestation required |

## Integrity references

Private evidence is retained outside Git in owned private temporary directories.
The operator can resolve the following IDs through the private evidence index;
public CI URLs make the sanitized test outcomes independently retrievable. Hashes
are SHA-256 unless explicitly called a Git tree/object ID. Raw transcripts,
credentials, ownership tokens and local worker/runtime state are never committed.
Private temporary retention is host-lifetime evidence, not a public archive;
the operator must retain it privately if later audit is required.

| ID | Evidence reference and integrity |
| --- | --- |
| E311 | [CI job129249083579](https://github.com/oduwan/adp_codex/actions/runs/42643108208/job/129249083579); retained decoded log `e70d44be12307d7f283eb931782b27af52077bbbdaa1de01fab3453d0cb4d0f2`; suite.json digest `5fad2df947db9fcdf4c9fe0fce032b12c5bd56b50eb4488a456f1ee0921a31c2` |
| E312 | [CI job129249083969](https://github.com/oduwan/adp_codex/actions/runs/42643108208/job/129249083969); retained decoded log `0dac072b53a18f0147d6821d5619201e85a96157f62eb870ff67d99a85ece2a9`; suite.json digest `ce604ecf205eb9a2911d268e2366a2788b5bb9e8e0973467f6f3af8a22c092a5` |
| I311 | CI clean-install6/6 evidence `e19323113038134da030a6d55f83dc8ca6a0d76b8cd2a07582de253164946531`; additionally local Python3.11.10 source0cca0d8b7abb6deec7642a8e2df9507ee5ac3054 clean-install6/6 evidence `2d9c74e7f4d10f873ca71e723dc6a6d96a5c6dd139c84e5735d84ad43ab32843` |
| I312 | CI clean-install6/6 evidence `06300fc7ec52882689c9d7207516182db4d91a922526604a19584ee772ca975e` |
| PLUGIN | `plugin.json` private summary, exact P: `e96ed9f9a98d6943c55ed822073e0e588c1c418c55fbd75573ae03853005e802`; installed portable manifest `dde81b34a484893bf308b27945088bb011174106cde795c9577b4f0a968c3589`; skill `46cb45fa6c3b68cc57129262508f1b2167c56862638820c20e3eacaa75a56824`; actual install/discovery/removal JSON retained privately; independent audit `167906e510f0125b4a7b6e7d1fd3185ae2f09d6a93a1ccd621a946125d460076` (cache removed after observation) |
| HIST | Independent original M5 artifact audit `f330790981ac5e50ee78e1518dee4948c5426ad9299cd15cf5e0b7128d94e267`; original raw proof `9b59f91437a060fbf7498f812422fcfaf667aecdbc3f84b5a8ba7c9b8dea80fb` |
| REAL | Fresh raw proof `1035b1116e89caf4c4643dfcd3222b9b4845b18dd1ea6ba3eeb7dc237ff1b23b`; internal evidence digest `b2be92137070fb12c791ff9bb7136a7dcab72aece396f41a14b514aab01b963b` |
| REAL_AUDIT | Independent fresh runtime audit `771ac9603798e9fa3bea9c34159e6f913a15d38325701e2aa92d31b0684688e6`; independent checker1/1PASS; no additional model run |
| PLAN_REVIEW | Independent approved plan with initial securityCHANGES_REQUIRED `47fc98fe019955c7465a74290888c4072cfc773d1742af9ceb70e2becae13ddd`; pre-runtime corrected privacy/lifecycle/helper13/13PASS `37a5590c925643f376b440509fdaf11338b6736eae707796516ecc3532536603` |
| INITIAL_CODE_REVIEW | Independent9768c9c reviewCHANGES_REQUESTED for exact skill binding `8248f5837ca7ae2eb876fde0937d92c570388a543c250fb5fa3f9b3f1e62d2d4`; corrected in S and actual probe rerun PASS; final review still required |

## Real runtime details and source binding

Historical Developer context `01a1c046-5bd1-78c0-bdea-92fab03172c3` and Reviewer
`01a1c047-11bd-7593-a71d-457d18c276f8` reviewed product
`c4556f4e9995b660f6c41c4ee6c6d216a5029db9`. The original engine/tests match
accepted main1eb; a PR description alone was not accepted as proof.

Fresh Developer context `01a1c0d1-4870-75b2-9024-c734b9b1bff1` started at
`b7af2d5f943da50d38a1fabb001420a71d9fa55d`. Independent Reviewer context
`01a1c0d2-44e7-7ff1-adf8-31f4b5e41e4b` approved exact final product
`411fe0149a5c32cce527cac943f7a9942bd26983`. Both runtime outcomes COMPLETED;
no background work/unconfirmed contexts. Actual result: answer() returns42,
validation1/1PASS; local published branch matches product SHA. Independent raw
audit checks the supervisor stop receipts, immutable requests, canonical
assignments/generation, reviewer approval and checker rather than only summaries.

R, S and T share the same `adp/` tree and unchanged real-qualification script
Git blob `2ebbddcd92b72c5ffe47411d0c0dd31c4a83cc34`. Later harness/docs/report
changes do not silently rerun or relabel that real proof as a different engine.
One invocation is evidence of supported real serial delegation, not real parallel
workers, Windows-native support or unattended/always-on execution.

## Preserved failures and bounded corrections

| Observation | Actual result and correction | Retained evidence |
| --- | --- | --- |
| F1 accepted-engine worker summary | 1FAIL: synthetic credential-shaped worker output reached canonical/remote memory. Failing regression committed in e7e3c0a88c5eae4e92a0b5ffe8b3479ab5c96293, before enginefix7ec1075. Fresh output now blocks before checkpoint with contamination/terminal operator boundary | Before log `72469045171adb1ab0b02ee62dbad00674352a76b716c7c4d3c4a8a4432f49e2`; independent sanitized repro `5af30a9626b4cffb12ae15315fdf08b6a8a458bd013284f3824cea52c047d2a3` |
| F2 legacy cached output | Independently reproduced tainted cache recopy through run/resume/handoff; corrected read-only preflight refuses before recovery/checkpoint, no automatic history rewrite | Repro `f70a57b994d52b09ad1ca3036b7073e6ac1ca44971b2edea1e0689c4a8ef31db` |
| F3 forensic terminal lifecycle | Independently reproduced blocked secret-shaped forensic path reopening after handoff; BLOCKED now precedes orphan/forensic routing, no new context | Repro `4f4177cef3735da49ffbbcb76b39adc8f4835e13c8d7c0a1679b7f9971a27495`; corrected five-test privacy/lifecycle PASS log `ac6d1134a8200c802070a35445abbc31a409b3df323962039bbf3c58ad122f88` |
| Cross-project diagnostic assertion | Initial1FAIL expected word “review”; actual correct refusal was “independent exact-sha approvals required:2”. Corrected assertion requires the precise two-approval diagnostic; policy threshold unchanged | Initial log `b1b3d196d00783fe265c276102517e2f3e598681c5b75e77eb43869fa5120413`; corrected1/1PASS `11d191a41542343268a7ebc55d46d9131857bf1f399656c44bef341ddc3aa2fa`; finalCI repeats full expanded test |
| Initial CI checkout | Both jobs ERROR at baseline-object integrity check, suite210/210NOTRUN for each, install6/6PASS. Corrected checkout fetch-depth0; baseline check retained | [Failed run42641893863](https://github.com/oduwan/adp_codex/actions/runs/42641893863), logs312 `49498304c2e1beec6a7b7e72cdb4f68692fb2522d60ada2079f244b2a92c23d0`,311 `c9e384dcab803a69ebfd711a2cff389b1074c4c97a9f00aa676ef9344736b414` |
| Initial plugin catalog | ERROR “plugin not found”; CLI did not implicitly discover desktop repo catalog. Supported explicit local catalog registration corrected it; own namespace reconciled/removed | Initial evidence `130fc141c8c0941b795dfb38f180e92a65e64a996240894dce9dc079510f6a49`; corrected intermediatePASS `d40653b9dc367980f6baae7e18260cbe39b87a8d604d08a567ef61dc58f93e94` |
| Independent helper findings | Existing nonprivate evidence directory could be accepted; now require owned0700 and exclusive0600 files, with regression. Initial plugin matcher could accept unrelated same-name skill; now exact installed path/hash, corrected probePASS. No denominator/assertion/timeout weakened | Initial review and final PLUGIN evidence above; helper8/8 independentlyPASS |

The initial local baseline observation reported193/193PASS in1761.360s on
Python3.11.10 (log `51e4b38d5b578526986ae9a1567e5f38160ae7104e4c74823fc7c297a47f622e`).
That run started on accepted source but overlapped local documentation/codework;
it is not relabeled an immutable final qualification. Clean pinned CI above is
the full acceptance evidence. Earlier corrected candidates b80ffe1 and9768c9c
also completed210/210 on both interpreters; they do not replace final-HEAD CI.

## Supported scope, gaps and operator decisions

- Portable root plugin.json plus root skills/ follows current
  [official packaging guidance](https://developers.openai.com/plugins/build/plugins).
  Actual CLI catalog/install/list/remove and documented app-server skills/list
  were tried. A compatibility overlay was not invented. Full referenced docs
  travel with the bundle. The skill grants no agent, memory, Git or release rights.
- Host assumptions are Linux/POSIX locking/fsync/atomic replace, /proc/subreaper,
  trusted Codex CLI0.167.0/auth installation, operator/verifier code and OS. No
  arbitrary hostile same-user/kernel or universal secret-classification guarantee.
- Supplied push is allowlisted local bare exact CAS. Network push remains
  UNSUPPORTED_ATOMIC_REF; production validation needs a separately qualified
  sandbox. Merge/release/deployment backends are not supplied. These refusals
  are successful safety tests, not claimed support for those operations.
- Discovery/GitHub write-idempotency qualification uses synthetic transports and
  disposable repositories. No existing live product repository was accessed,
  installed into, migrated, mutated, merged or deployed. ADP feature-branch push
  and this single Draft PR are the only authorized external repository publication.
- Cross-clone and interrupted recovery are simulations; no actual cross-machine
  hardware power-loss claim. Real Codex proof is one serial Developer→Reviewer
  contract. GUI/model-driven plugin usage and live forge mutation remain
  UNSUPPORTED/NOTRUN as stated, not hidden exclusions or global capability claims.
- Unknown delivery/stop evidence and unfinished old-generation review require
  operator reconciliation. A historical leaked real credential would need
  rotation and explicitly authorized remediation; M6 does not rewrite history.
- Final independent integration acceptance, license/distribution terms, merge,
  tag, release, public plugin listing and any deployment require separate operator
  decisions. **Public release remains NOT_AUTHORIZED even after all technical
  qualification and reviews pass.** Leave the PR Draft and Issue6 open.
