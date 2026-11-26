# Git-native historical basis and publication cutover contract

> **D4 operator revision (Issue #57):** The historical D1/D2/D3 account
> below is retained for evidence. Its repeated historical-byte/closed-private-
> inventory replay, independent closing historical reconstruction, finite-U
> request predictor and net-negative-LOC intermediate STOP are superseded by
> the approved [personal trust boundary](../ARCHITECTURE.md#personal-historical-trust-boundary--d4-operator-revision).
> Full entry/restart authentication remains; mutable current authorization and
> original budgets remain live. N+1 is a negative lower bound only. This does
> not release #58, change old grants or authorize any live product effect.


Status: selected D1 engineering contract for Issues #53–#57; not integration,
installation, publication, migration or execution authority. Full qualification
is Issue #58 and requires a separate operator release.

Reference source: 13fd8595e301bfc7e1428a96774ae9663669b716, tree
1fe94f0a26656325c969cbc04ef8497aca9cafa9. Function/line references below are
to that immutable source. The already published
[call graph](PUBLICATION_CALL_GRAPH.md) remains the detailed graph; this document
selects its replacement boundaries rather than repeating that audit.
[Baseline](GIT_NATIVE_BASELINE.json) records reproducible static measurements.

## 1. Selected identity: REUSE_EXISTING_H3_V1

**Reuse the existing H3 episode-install checkpoint. Create no additional Git
object, ref, remote, journal, database, authority service or background process.**

H3 is already an ordinary canonical Memory commit, with direct parent H2. Its
existing state/tree commits the fixed accounting relation, frozen parent
task/guard, initial child and immutable assignment lineage. H0/H1/H2 are existing
ancestor checkpoints. The existing canonical branch, refs/heads/adp/personal,
retains H3 in both the coordination checkout and pinned bare coordination.git.

The sole historical identity is H3. The fixed-relation digest is a deterministic
projection of that identity, not another writable truth:

    basis = {schema_version: 1, checkpoint: H3, relation_digest: R}
    R = digest(H3.progress_guard.accounting_continuation with usage excluded)

Use the existing closed canonical codec and OID validation. No qualified=true,
ALLOW result, credential, fresh permit or product acceptance is represented by
this value. H3 cannot authenticate an absent private receipt or current working
tree and cannot certify current GitHub permissions.

Physical stores must not be confused: Memory.common is coordination/.git;
PersonalState.memory() pins the separate existing bare coordination.git
(personal_storage:220–229). A loose object written in just one replica or an
OID string in JSON would not establish reachability. This design writes neither:
normal M1 publication already retained H3 and its actual parent closure.

### D2 interpretation of creation requirements

Issue #55 permits a retained ref only if necessary. Here it is unnecessary.
Consequently new-anchor expected-absent ref creation, object-write/ref-publication
crash windows and a new-ref namespace are **not implemented**, not tests marked
PASS. Their requirements are satisfied by selecting existing canonical identity,
with explicit substitutes: exact H3/direct-H2/ancestry/closed-state verification,
actual object corruption/absence, current branch rollback/deletion/replacement,
normal GC reachability in both existing stores and read interruption without
authority. Existing H3 installation/activation still uses the unchanged
expected-H2 M1 transaction, exact-purpose recovery and original one-use approval.
A basis reader cannot recreate H3, activate an episode or repair missing state.

Adding a new anchor writer later requires returning to D1; it is not a fallback.

## 2. One source-of-truth matrix

A digest binds content; it does not replace required authenticity or availability.
All local paths below are symbolic paths within an enrolled private directory,
not instructions to inspect any real target.

| Fact | Current storage / change authority | Canonical Git binding | Why outside Git, when applicable | Consumer / freshness | Replacement operation |
| --- | --- | --- | --- | --- | --- |
| H0 initial reservation | Memory state/tasks; owning M1 writer | Existing H0 commit | No additional copy | Recovery/history; full cold entry/reentry/closing | Read actual H0 and exact parent chain from H3 basis |
| H1 overdue accounting | Canonical guard-first checkpoint | H1 direct child of H0; original STOP_UNSAFE remains | Not an execution-timeout claim | History and episode; cold proof | Verify actual objects and literal frozen guard |
| H2 original UNKNOWN delivery | Canonical task/guard | H2 direct child of H1; original assignment unchanged | Raw NOTRUN remains private | History and episode; cold proof | Read existing H2; no simulated PASS or budget reset |
| H3 episode and fixed relation | Canonical registry2 state/tasks; original one-use installer | H3 direct child of H2, retained by current Memory ancestry | Activation locator remains private | Episode/publication; cold proof plus actual object binding in write fence | Sole historical OID; no extra ref |
| Original Worker request/result/stop | Protected runtime and worker records; original supervisor/Conductor | H3 relation.archive → archive.master → original master proof digests | Contains prompts, host/PID/context/result and private provenance | retained/_archived_view; authentic full cold proof, actual-byte seal at writes | Keep original bytes; no Git copy or remembered stop verdict |
| Original independent scope review | Protected Worker/runtime receipts and canonical M1 result | Same immutable chain plus accepted original assignment | Context and raw review remain private | Scope/adoption/history; cold auth, live unchanged-record check | Exact request/role/context/stop and assignment; no self-review |
| Historical grants/reconciliation | Protected original ae1 bodies, submitted/observed/recovery records | Their exact digests are transitively bound by H3 | Original consent token and local provenance are not Git data | History; cold non-issuing verification | Authenticate literal recorded-engine bytes at original time |
| Episode descriptor/activation | Protected immutable descriptor, intent and activation | Fixed H3 relation plus activation.checkpoint == H3 | Approval and local locator stay protected | Episode; full entry/reentry/closing, direct protected equality at writes | Existing records only; never create activation on read |
| Retained candidate origin | Original two files, seals, adoption proof; explicit operator/adoption Reviewer | Parent/child lineage and existing accepted source-origin assignments | Unaccepted source material and raw adoption receipt are private | Source authors/review; cold proof and actual source/admin seals | No automatic copy, commit or promotion |
| Current original/code review | Current canonical assignments/guards and protected receipts | Current exact Memory checkpoint, not H3 | Raw evidence and current consent stay private | Fresh batch review; each write checks exact current snapshot and protected bytes | Reuse immutable comparison operands only while current head/state/tasks match |
| Current M1 health/owner/generation | Existing state, owner token, working tree, pending/inbox/control | Actual local and pinned remote current HEAD | Owner secret, pending transaction and inbox stay outside Git | Every write; one late actual Memory.inspect | Pure same_observation against post-SUBMITTED subject; no cached owner |
| Current M2 permit/counters/deadlines | Current guard registry and exact reservation | Same current canonical checkpoint | Live wall clock is external | Every write and M3 boundary | _get/_active/_context on that fresh snapshot; no begin/reset/re-reservation |
| Enrollment/track/marker | Protected original intent, links, original packet and Git admin marker | Original identity and existing canonical relation | Contains local paths and scope/operator data | Each write direct bounded equality/seal; full admission at cold boundaries | Existing input readers, no second enrollment |
| Revocation and expiry | Existing protected revoked path, current UTC/monotonic clock | Never inferred from H3 | Mutable negative authority cannot be committed as a positive grant | Last checks before transport | Existing episode_fence and exact publication expiry; absence remains actual |
| Credential/recipient/rules | Selected gh context/token; current native observations | None: Git is not GitHub authority | Token/config/provenance remain private | Credential/recipient each request; full native policy at batch/M3/pre-CAS | Existing transport and quiescence warrant; never infer rights from credentials |
| PREPARED/SUBMITTED/claim | Existing canonical execution action and protected no-replace claim | Current execution action_id and full effect fields | Claim is one-use local control, not portable approval | Durable before mutation; exact current check at every write | Existing journal/claim only; consumed dispatch cannot be reminted |
| Network stop | Existing control marker and in-process service state | None | Mutable stop/liveness hazard | Existing request entry and confirmed-stop exit | Preserve existing owner marker ordering; no second stop journal |
| Runtime request/time budget | Existing validated settings and active Budget | Stored consent caps remain literal | Monotonic deadlines and request count are invocation state | Every request/operation; final admission check | Same Budget, never another root or request_deadline charge |

The closed in-Git historical set is **only the existing H0/H1/H2/H3 canonical
data above**: fixed relation fields, historical parent task/guard, initial child,
assignments, hashes and approved nonsecret identifiers already encoded there.
Mutable usage is read from current Memory, not frozen as future allowance.
Current reviews after H3, external CI, PR/merge/report outcomes, current
credentials, revocation, claims and network hazards are not historical H3 facts.

## 3. Cold qualification and protected raw bytes

There is one cold historical verifier, invoked at operation entry, interrupted
reentry and required independent batch closing. Preserve full original host,
request, stop, independent context, assignment, source/admin, consent and
H0→H1→H2→H3 checks. Unknown stop or unavailable original host refuses; do not copy
raw evidence into another context or spoof host identity.

Factor the actual existing activation/H3 verification in Episode._active_view
(personal_episode:118–130), using its existing _capture output. Capture the H3
which that proof ACTUALLY consumed, not a later unrelated activation read.
Verify closed expected H3 state/tasks using Memory._read_ref, direct H3→H2,
repository/episode/parent/child/generation, fixed relation/descriptor and actual
ancestry to the qualified current checkpoint. Pin both existing Git storage
contexts and reject graft/replace/shallow/alternate/promisor interpretation.

Use the existing bounded object byte reader to authenticate actual OID/type/body
of the selected historical commit/tree/blob groups. Preserve the existing
32-object/64-KiB-per-object group bounds; combine only within those bounds.
The object-ID groups are explicit immutable input witnesses, local to this
operation. They are not a module-global cache or another canonical identity.
Required current object bytes/presence in the actual selected stores are checked
again at write admission; missing/corrupt objects do not inherit a prior PASS.

Select the private capture keys historical_basis, historical_engine and
historical_objects. historical_basis has exactly the three fields in section1;
historical_objects contains the existing bounded actual-byte witness groups,
not another identity. For proposal construction, thread an optional private
_history_capture through PersonalPublication.local → PersonalCoordinator.fresh
→ its EXISTING final live call → Episode._active_view(_capture=...). Do not
add another full historical proof solely to retrieve this metadata. Compare
the captured current subject with the already existing final proposal Memory
inspection before using it. For dispatch, expose the successful closing proof's
capture through the existing live/validate_dispatch boundary; no public runtime
controller or persistent context object is added.

Raw evidence must be read through owned, bounded, protected actual file
descriptors with exact typed contents and hashes. A later file hash cannot
authenticate a different transient record previously consumed.
CodexExecRuntime._read/_stop_receipt currently rely on frame hooks for protected
FD checks in this path; do not delete those hooks until the single cold reader
provides equivalent opened-byte protection. Do not relax generic runtime or
signed-provider semantics. Missing raw receipts remain UNKNOWN.

No dispatch or new grant is produced by a cold proof. A restart has no surviving
in-process basis and must qualify again; an existing action still observes only.

### Historical-engine interpretation, not consent renewal

The old implementation compares master.engine to CURRENT engine_digest and
reconstructs old grants using the CURRENT engine (history:68/87, recovery:85).
That must not be bypassed by silently regenerating test grants under new code.

Select a non-issuing read rule for the exact existing accounting schema1 / ae1
grammar. First validate the canonical H3→archive→master integrity chain and exact
raw records. Reconstruct the ORIGINAL purpose/subject/body/token using the
recorded engine bound by that chain and ORIGINAL submitted_at/issued/expires/nonce.
Compare literal tokens, bodies, measurements, source seals and provenance;
return no approval, nonce, new deadline or permission. Reject unknown schemas,
wrong purpose, unbound engine/body or any changed original record.

For an existing episode, read its protected activation locator as UNTRUSTED
input first. Check actual H3 against the current canonical fixed relation,
direct H2 parent, selected repository and ancestry BEFORE using its bound
recorded engine to interpret a grant. Afterwards recompute/compare the full
expected relation and state from the authenticated raw inputs. Missing or
not-yet-activated H3 is not a migration bootstrap: the original installer and
archival mutation path still require current-engine consent and existing exact
recovery. No generic allow_legacy/ignore_engine flag is introduced.

This includes load_episode's descriptor/base.engine comparison and original
episode ae1 grant (episode:148–167), not just the archive's guard/result grants.
The loader first rejects an episode descriptor in the original ancestor (no
recursive load_state dispatch). Protected descriptor and activation are locators,
not authentication: load the original root, inspect its actual canonical Memory,
read H3, compare its fixed relation with the current fixed relation excluding
usage, check direct H2 parent and ancestry, and bind actual archive/master and
descriptor episode/plan/grant/blueprint hashes. Pin both existing storage
interpretations and authenticate actual object bytes before using a recorded
engine. Only this established chain permits literal historical descriptor/grant
decoding; full expected_relation/episode_intent and raw provenance qualification
still follow at the cold boundary. No active view or archive recursion is needed
to bootstrap that Git binding. Missing activation may use ONLY the unchanged
current-engine preactivation installer/status path, never historical decoding.

Live Recovery.grant/issuance/apply still binds the current engine and trusted
current clock. A new publication view separately binds the actual current reader
engine plus the existing H3/R. Actual current engine bytes remain freshly checked;
HEAD alone is not an engine seal. This is a closed read-only historical format
interpretation, not an allow-any-engine issuance option or additional trust root.
Replace _legacy_inputs' current-engine-equals-master assertion with two distinct
operands: the authenticated immutable historical engine and freshly hashed actual
current reader bound to the new consent. A changed historical engine or a changed
current reader during that consent still refuses. Do not delete the engine seal.

## 4. Operation-local subject and the short write fence

Use one invocation-local value on the current PersonalPublication/dispatch.
Its operands are H3/R and actual object witnesses, existing exact private-input
seals, current reader/source/admin/index/working-file seals, actual review
binding, current canonical post-SUBMITTED subject, exact action/claim/permit and
the same transport/Budget. It stores expectations, **not ALLOW**.
Clear it on every return/error/cancellation. Never serialize it or reuse it on
another invocation, thread, coordinator, source or generation.

Seed the current subject only after the original initialize/register/reserve,
PREPARED, exclusive claim and SUBMITTED transitions and full pre-upload checks.
The earlier view.checkpoint is NOT that subject. Use the actual returned
checkpoint from the existing transaction protocol; unexpected advancement fails.
During object transfer there is no permitted canonical mutation. A post-upload
full fence cannot silently adopt a foreign new checkpoint.

The short callback REPLACES:

    write_authorized → live(review=False) → _live_current → Coordinator.live
      → Episode._active_view → _archived_view / raw history replay

It must not call that chain under a new helper name. It also must not call
Guard._decision, _qualified_accounting, ReservedSafety.observe, journal.inspect
or guard._snapshot to recreate the recursion or duplicate Memory inspections.

Required order for each real object POST and CAS admission:

1. Require the active exact one-use dispatch, same selected service/target,
   current action identity and protected claim body. It is already consumed by
   submit; do not look for or mint a new ticket in _dispatches.
2. Read current source HEAD/ref/tree, index/flags, bounded working-file and
   administration/config/governance seals. Clean status alone is insufficient.
   Read direct original-material/source/admin seals and exact protected
   enrollment/episode/activation/review/worker/consent/authority inputs, including
   declared inventory and required absence. Reuse existing pure input readers;
   no c.live or historical semantic replay. Unsupported hidden index/source
   states remain UNKNOWN rather than being certified from HEAD.
3. Verify actual H3/object witnesses and pinned storage interpretation and
   compare all input operands with the qualified subject.
4. Take **one actual late Memory.inspect**. Require SYNCED/local_owner, then
   same_observation(expected,current) over full heads/state/tasks/owner/inbox.
   This catches changed unrelated guards/assignments too; do not check only
   generation or source SHA.
5. On that same snapshot use existing pure _get/_active/_context validators.
   Require exact task/epoch/iteration/owner/generation, requirement, token,
   reservation/context/counters, allowed mode and original absolute deadlines,
   exact canonical action_id/SUBMITTED/effect fields, current review assignments
   and approval context. The action's original plan_digest is not necessarily
   the reauthorized Plan digest after safety-head advancement; compare the
   existing claimed effect fields and separately current exact M3 Plan.
6. Finish with actual UTC, episode/publication revocation/expiry, current
   credential/recipient and remaining original Budget checks. Any mismatch
   refuses before the transport child. No new HTTP request, grant or reservation
   is performed by this callback.

Existing _inputs/_private_digest and direct legacy source/admin checks are
shared factual primitives, not another verifier stacked on top of the old
unframed live. Full review stays at cold/batch boundaries. Actual GitHub
permissions/protection are freshly observed through existing native/M3 gates;
the short callback cannot claim atomic knowledge of server policy between
requests. Preserve the finite administrative-quiescence assumption, native
server refusal and post-upload/pre-CAS checks.

### The current request already owns its hazard marker

GitHubCAS._request first checks old stop state, charges the existing request and
persists its own IN_FLIGHT_OR_UNKNOWN marker, THEN calls PersonalGitHubTransport
and authorize_write. The short hook must not call _check_stop or require marker
absence there: that would refuse every valid write. Preserve the preceding
_check_stop plus exclusive marker creation, same synchronous request/service
and actual confirmed-stop cleanup. A prior/broken/unconfirmed marker still blocks
the NEXT admission. Never clear or relabel an uncertain hazard to get permission.

Likewise request_allowance/transport remaining-time checks still cover callback,
credential lookup, child execution and decoding. Do not call request_deadline
again, create another root Budget, round up time, refund requests or renew a
stored 120-second/legacy45 grant.

## 5. Required independent boundaries and uncertainty

Keep full operation entry and interrupted reentry qualification. Keep every
existing M3 decision/plan comparison, the native three _authorize calls, full
pre-upload and post-upload validate_dispatch, current exact remote/policy
inspection, pre-CAS expected-old comparison, atomic updateRefs CAS, actual
post-CAS observation and M2 settlement. Validate_dispatch refreshes direct
private/source comparison operands only after its full proof; it does not adopt
an unexpected canonical head or issue another authorization.

Effects remain PREPARED→claim→SUBMITTED before native upload. Lost responses,
post-upload refusal, missing confirmed stop or mismatched refs remain UNKNOWN.
An existing intent after restart uses observe/settle only; no new dispatch,
duplicate upload/CAS or inferred success from H3/credential/CI.

## 6. Side-effect-free request feasibility

The existing object closure is complete before any object POST. Use that tuple
and the SAME active Budget. Define R = maximum_calls - calls, N = len(objects),
L = N + 1 (at least all object POSTs and one CAS). A stronger proven lower bound
may be used, never an estimate. Let U be a proved upper bound for all remaining
mandatory requests EXCLUDING the N object POSTs.

- L > R: INSUFFICIENT, refuse before the first object POST.
- A complete U is available and N + U <= R: count-feasible only; all live,
  time, authority and response checks still apply.
- Otherwise UNKNOWN, refuse before the first object POST. U > R does NOT prove
  actual insufficiency. An observed page count is not a future bound.

No reservations, extra requests, configured limit, planner database or new
persistent counter are introduced. Failure-path reads must be included.

### Explicit negative-only fresh-read envelope

Apply these restrictions only to the new qualified personal publication path;
signed/default readers keep their previous behavior.

- OriginalRead already binds an approved exact URL→body/Link-digest map.
  current_original refuses a successor path outside that map BEFORE fetching it,
  still performs all M4 checks and before/after root reads, and still compares
  all actual responses. With P approved distinct paths and K original roots,
  the bound is P+K. No old response is returned as a new observation.
- Bind a defensive immutable actual RepositorySnapshot/Ref tuple to
  Plan.snapshot_digest. Plan has no recoverable ref list in its digest.
  The provider's earlier snapshot is usable only if its actual digest matches
  that exact Plan; a mismatch refuses before objects.
- Every fresh GraphQL ref page is actually fetched/validated. Continuing pages
  must contribute distinct previously unseen EXPECTED refs, with fresh cursors;
  unseen/duplicate/nonprogress nodes or a request beyond the finite envelope
  refuse before another fetch. Do not follow hasNextPage when that prefix has
  no unseen expected refs left. The actual completed tuple must still equal the
  expected tuple. With n_h heads and n_t tags, the enforced bound including
  refused pages is F = max(1,n_h) + max(1,n_t), at most n+2. This follows from
  progress and early refusal, never from a prior observed page count.
- This intentionally makes formerly accepted empty continuing ref pages
  UNKNOWN. It is an explicit fail-closed supported-read refinement under #56,
  not a cached permission or an implicit unchanged-behavior claim.

The same negative-only principle applies to already approved rule modes.
In enrollment_rules, refuse an unavailable mode inconsistent with the expected
branch row before doing fallback reads. In writable inspect_ref, use the existing
personal_policy_binding to refuse an inconsistent normal/plan-disabled mode
before doing the alternative branch. Never skip actual policy reads or accept
an expected mode without fresh evidence. This only shortens paths which would
already fail the final exact policy comparison; defaults/other consumers remain
unchanged. Feature presence may still change, so fallback costs use PRESENT's
worst bound regardless of the earlier absent state.

For the existing one post-upload global-ref pass, a conservative tail is:

    U = M + F + (P + K) + sum(branch_rule_bounds)
        + remote_bound + writable_inspect_bound + settlement_remote_bound + 2

The last2 are CAS1 and observation1. With the explicit early mode refusal,
normal-mode branch_rule_bound is2 and a normal remote/inspect/settlement uses
6/3/6 respectively. The bounded Free-private fallback uses branch_rule_bound5
and remote/inspect/settlement at most11/8/11. Without those early restrictions,
the general conservative expression is M+(n+2)+(P+K)+5*B+32, where B is the
original branch-rule inventory length. Do NOT select normal-only/absent costs
from old observations without enforcing their negative branch restrictions.

M must bound all additional native-prerequisite/authority HTTP, including any
recursive historical/later-window consumers. The explicit current native
prerequisite tail is at most9 requests per deduplicated prerequisite ONLY when
its cold prefix is proven local-only and exact repository/PR IDs, original
completion, closed merge/squash method/envelope and payload identities are
validated. No REPORT overlay or unbounded/unclassified authority branch is
admitted under that formula. A graph containing additional unbounded reads
returns UNKNOWN; it may not silently use M=0. For the fixed first accounting
Issue with no native prerequisites/later accepted windows, the closed prefix
has no such HTTP and M=0.

This is an executable classifier over already qualified inputs, not a runtime
configuration system or a guarantee that a changing server will complete:

    >>> def count_admission(n, remaining, tail):
    ...     if n + 1 > remaining:
    ...         return "INSUFFICIENT"
    ...     if tail is None or n + tail > remaining:
    ...         return "UNKNOWN"
    ...     return "COUNT_FEASIBLE"
    >>> count_admission(512, 128, 17)
    'INSUFFICIENT'
    >>> count_admission(2, 20, 17)
    'COUNT_FEASIBLE'
    >>> count_admission(2, 20, 19)
    'UNKNOWN'
    >>> count_admission(2, 20, None)
    'UNKNOWN'
    >>> count_admission(0, 1, 1)
    'COUNT_FEASIBLE'
    >>> count_admission(0, 0, None)
    'INSUFFICIENT'

Do not infer wall-time fit from count feasibility or use a partial upload as
qualification. Unknown required classes remain a disclosed capability gate.

## 7. Exact version and legacy cutover

D2 selects accounting-publication record schema_version2 with publish2 approval
prefix. Its view adds historical_basis (exactly the section1 value),
historical_engine (bound original master.engine) and reader_engine (actual
current engine_digest). The EXISTING view/token/action_id digest binds all
three; no additional approval file is created. Old readers refuse schema2.
No M1/M2 schema, separate consent journal or additional effect record is added.
D2 does not shorten the mutation fence; D3 replaces it only after D2 review.

### Close the existing accounting writer families

Historical decoding removes an old global current-engine rejection. Therefore
publish2 alone is insufficient: Product.local calls Coordinator.live and does
not transitively bind a publication view. Apply the SAME three fields to the
EXISTING accounting Product PR/MERGE/CI/REVIEW/CORRECT and REPORT approval views.
Select product record schema2 and product2 token grammar for accounting only;
the independent report.json parser must enforce the same view/token gate.
RevisionPublication inherits publish2 and cannot use an old Product correction
consent to mint a replacement. Old accounting Product/report rows remain literal
observation-only history; a retained legacy intent blocks any replacement writer
and returns an explicit disposition blocker when observation cannot reconcile it.
Ordinary personal product1 and signed-provider behavior are unchanged. Fresh
consents require the current reader at issuance AND at the actual write boundary.

Completion and NEXT can mutate authority without Product.live. Bind the same
three fields into the EXISTING accounting completion approval view/digest, with
personal-completion2 prefix; no additional acceptance journal is introduced.
For an accounting parent, select next view schema2 and include the same three
fields in its existing normalized-snapshot approval digest. Revalidate them before
handoff, enrollment or attachment; old pending next intents permit observation or
reconnection to an already COMPLETE exact successor only, never finish/remint an
incomplete successor. A changed reader requires explicit disposition, not silent
new consent over the same pending intent. Ordinary completion/NEXT formats stay
unchanged. Existing accepted() receipts remain valid historical observations;
reading them grants no permission and does not require a fresh-reader token.
NEXT derives its H3 binding through that authenticated historical acceptance/
cold path, including after parent expiry or owner release; it does not demand
an unexpired parent Product grant. The new ordinary successor plan/window/setup
approval remains independently literal and finite.
An active accounting episode already requires its original track attachment;
new registration cannot replace it and must refuse rather than invent a link.

These are version/field replacements within existing approvals, not a second
policy, store or live backend. D2 must fail closed at all affected writer entries
while this cutover is staged; D4 must leave one qualified writer family, with no
legacy live fallback. Add focused changed-reader, old-token, pending-NEXT and
historical-read negatives for each affected consumer before final cutover.

- Fresh qualified view: H3/R and current reader engine are part of the exact
  existing view/token/action_id. Old source, time and role grants stay literal.
- Existing episode, no publication intent/action: an operator may select a new
  qualified proposal using the same H3/window/owner/budgets. The proposal never
  activates an episode, refreshes a deadline or migrates state on read.
- Any old PREPARED/SUBMITTED/claim/hazard or existing v1 accounting-publication consent:
  no automatic upgrade/replacement/new dispatch. Preserve the row and original
  token, observe the exact existing effect only, or return an explicit operator
  disposition blocker. Never delete the old row to make a new attempt.
- Missing/partial/foreign H3, unsupported schema, absent raw provenance,
  changed reader or expired/revoked window: refuse. No legacy fallback writer.
- Ordinary signed-provider protocols stay unchanged. Ordinary personal state
  cannot invent H3 or acquire accounting continuation rights. Do not reinterpret
  an unrelated ordinary grant as a historical-format migration.

The only lasting compatibility reader is the closed NON-ISSUING original ae1/
accounting-schema1 verifier needed to authenticate unchanged original bytes.
It is not a second execution backend. The old v1 publication write route and
temporary D2/D3 staging selections must be removed in D4 BEFORE #58. Read-only
status/observation of an old intent retains no mint/dispatch operation; a state
which cannot be reconciled by existing exact-purpose rules stays blocked.
No real operator-state migration is performed by this engineering track.

## 8. Replacement/deletion and complexity gates

Current product measurements at the frozen reference: 100 Python modules,
26,210 physical lines, 23,499 nonblank/noncomment lines (including docstrings),
1,240 function nodes, 249 classes and 19,325 AST statements. D1 changes product
counts by ZERO. The baseline file defines the counting algorithm.

| Mechanism | Before | Selected after D1–D4 |
| --- | --- | --- |
| Canonical runtime history store | Existing M1 branch, synchronized local/bare replicas | Same; ZERO added stores/refs/objects |
| Historical basis identity | H0/H1/H2/H3 plus repeatedly derived private proof | Existing H3 is the one binding; originals remain authentication witnesses |
| Module-global historical witnesses | history_git._WITNESSES and history_product_git._FACTS | Remove both; no replacement global cache |
| Object POST historical semantic path | write_authorized→unframed live→Coordinator→Episode→archive | ZERO calls to that path; one direct current fence |
| Per-write canonical observations | Recursive guard/journal/history fan-out | ONE coherent late actual Memory.inspect plus explicit actual object/input checks |
| Live rights/stop/recovery | Existing M1/M2/M3/consent/transport/CAS | Retained fresh; no cached ALLOW or extra authority |
| Compatibility writer | Old and staged candidates while developing | One new personal writer; old intent observation only |

Concrete cutover edits, not an additional framework:
1. D2 factors existing H3 capture/validation in personal_episode/history and
   removes the module-global history_git witness cache in favor of explicit
   bounded actual-byte witnesses. The public state and existing Git primitives
   stay unchanged. Historical-engine read authentication is separated from
   live grant issuance.
2. D3 replaces write_authorized's old unframed replay, shares existing direct
   input/source primitives and uses pure validators on one late actual snapshot.
   Remove live(review=False) as an effect-admission route at final cutover.
   Keep the existing real transport callback; fixture-only fast paths are invalid.
3. D4 deletes _FACTS and commit/index witness bypasses made redundant by
   authoritative native observation plus actual object-integrity checking.
   Remove obsolete _commit/_witness/cache branches only after equivalent
   native entry/closing and corruption controls are proven. Do not replace
   them with another parser/cache registry.
4. personal_read_frame still has required cold/Product/track consumers.
   Do not claim its400lines are dead simply because POST stops calling it.
   Delete only proven unused plumbing, or replace a cold reader only with
   equivalent direct protected opened-byte authentication and explicit consumer
   coverage. No silent removal of config/runtime byte hooks.
5. Correct the two known #50 TEST_DEFECT fixtures in D4 only: valid GitHubCAS
   receiver for the read-refusal test, and effective remaining10-second cap
   rather than exact30. Preserve negative assertions and historical nonpasses.

Anticipated concentrated edits add the H3 projection, non-issuing historical
decoder and short current fence while deleting the two global witness/cache
branches and obsolete replay calls. The shared direct-input reader replaces
duplicated source/admin assertions; do not keep a second independent definition
of those checks in the old unframed body. Layout estimates are roughly50–100
added/factored product lines versus90–150 removed cache/bypass/replay/duplicate
lines; these ranges are NOT measured deltas or permission to add a layer. Cold
consumer obligations take priority over achieving a number. D4 acceptance
requires ACTUAL net product physical and code-line
reduction, no additional module/store/ref/authority path and demonstrably lower
hot-path history/Git/Memory fan-out. Compare functions/classes/statements too;
do not compress unsafe logic to game LOC. Any net addition or unresolved
permanent duplicate mechanism is BLOCKED_COMPLEXITY and needs operator decision.

Unreplaced cold consumers include PersonalProduct.live/product_live,
PersonalAuthority accounting qualification, Episode.active/effective,
Recovery preview/reconciliation, retained adoption/source authors and
PersonalTrack accepted/later-window proofs. Each remains named and tested;
none may be silently dropped from the deletion inventory.

## 9. Focused implementation qualification and handback order

D1: validate this document's executable count cases, existing scaffold/link
checks and static baseline. No product runtime, Worker or full CI proof.

D2 focused controls: same actual H3 returns same binding; wrong original/episode/
generation/engine or unavailable raw files refuse; H3→H2/ancestor mismatch;
missing/damaged commit/tree/blob; rewrite/alternate/promisor contexts; GC retains
both replicas; branch rollback/deletion/replacement; interrupted read grants
nothing; no refs/files/old consent modified; old readers fail closed on new
private view version. The new-anchor creation cases are replaced as specified
in section1, never silently counted PASS.

D3 focused controls: actual personal transport callback order; stable finite
object sequence; one actual per-call Memory observation; zero archived semantic
replay per object; between-object Memory/owner/epoch/permit/revoke/source/index/
credential/recipient/claim/hazard/deadline drift; unsupported metadata envelope;
512-object/128-request refusal before POST; UNKNOWN versus insufficient count;
post-upload and just-before-CAS mutation; lost responses and observe-only recovery.
Measure exclusive per-call counts/cost on controlled equal fixtures; latency
under an unconfirmed unrelated process cannot prove a causal speedup.

D4: all remaining cold/legacy/signed consumers, explicit cutover, two narrowly
repaired fixture defects, code/API/store/ref deltas and mapped superseded tests.
Original coverage/failures remain recorded; retired tests are not PASS.

Each issue uses a separate clean stacked branch and Draft PR, normal English
Conventional Commits with Refs #N, focused checks and independent exact-HEAD
source/security review. Per the operator's explicit engineering sequence,
reviewed unmerged predecessors may be used as STACKED ENGINEERING bases, not
accepted main or execution authority. No merge, issue closure or silent rebase.

## 10. Baseline evidence and unreleased qualification

The preserved #50 CI accounting case measured publication.publish151.036673s,
90/128 requests,15,606 ADP Git helper calls/78.578620s,1,003 Memory inspections/
58.373001s and31 publication.live calls/100.295959s. Those intervals overlap;
do not add them or infer individual paths/full raw-proof counts. Upload method
returned; post-upload M3 refused, CAS/settlement NOTREACHED.
[Published evidence](https://github.com/oduwan/adp_codex/issues/50#issuecomment-7165149157).

No new whole-operation timing or speedup is claimed by this design.
The previous Python3.11 qualifier's descendant stop remains UNKNOWN. No status,
PID or quiet-log inference is made here. This does not block isolated static
engineering, but #58's full CI/integration cannot start without original-context
stop/reap evidence and a SEPARATE operator release. No pilot, runtime installation,
archival apply, external product write, merge, deployment or release is authorized.

