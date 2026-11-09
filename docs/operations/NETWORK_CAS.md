# GitHub network CAS — implementation and qualification boundary

Issue #14, accepted entry: `16c7a4e103c6a824f361f96e2eb237fbbf4faf48`.
This is offline codework. No target GitHub write or M8 pilot is authorized.

## G0 feasibility, frozen before implementation

The official [GraphQL Git contract](https://docs.github.com/en/graphql/reference/git)
defines atomic `updateRefs`, exact `beforeOid`, all-zero absent-ref comparison,
and `force=false`. REST update-ref's fast-forward restriction is not CAS and is
never a fallback. Only one explicitly pinned `refs/heads/` ref may be changed.

Git Data [blob](https://docs.github.com/en/rest/git/blobs),
[tree](https://docs.github.com/en/rest/git/trees), and
[commit](https://docs.github.com/en/rest/git/commits) creation can populate immutable
objects without updating a ref. A bounded independent experiment reconstructed
seven actual Git objects (binary blobs, executable/nested trees, parented commits)
in an empty independent bare store: **7/7 identical OIDs, zero refs changed**.
This is an offline implementation of documented provider semantics, not evidence
of an actual GitHub upload. Private proof SHA256:
`dce4262cbd4fca2ae1aa5fbe612ef821c01f73d732517650add02d6aadaa6971`.
Independent G0 design assessment SHA256:
`3af7520aad714131c8ff37e3e2634d3db4c2d8048e0d927f0fba9d513c04d295`.

Initial supported envelope: github.com HTTPS remote, fixed api.github.com API,
SHA1 objects, canonical unsigned UTF-8 commits with explicit author/committer UTC
dates. Every reconstructed object and returned OID must equal the intended local
object before CAS. Unknown headers, signatures, encoding, non-UTC dates,
unrepresentable paths/objects and exhausted bounds refuse UNSUPPORTED_ATOMIC_REF.
There is no staging ref, force/lease, REST-ref fallback or substitute commit.

The new port must bind actual M5 journal intent, current M1 owner/generation,
M2 reservation and fresh M3 exact-operation authority. A private fsynced exclusive
claim precedes the first object mutation. After SUBMITTED, only an authenticated
observation of the exact intended ref value is PRESENT; old/absent/different
values remain UNKNOWN. Missing/corrupt claim never grants another attempt.

Remote policy observations must use the same bounded authenticated HTTP boundary,
not Git remote helpers. Existing/prospective branch rules and permissions must be
known. Ruleset branch observations also apply before creation; legacy protection
inventory must be provably empty for absent-ref creation, otherwise unsupported.
Protected/ruleset-constrained branches conservatively refuse. Credentials confer
no M3 operator authority, merge rights or policy bypass.

## Frozen qualification inventory

All accepted 210 tests and fixtures remain unchanged. New tests run separately
under tests_m7 on Python 3.11 and 3.12; accepted M6 qualification stays frozen.
The following required scenario inventory is fixed before execution:

1. Exact immutable object closure, including binary/executable/nested objects.
2. Unsupported header/date/signature/path/object forms refuse before upload.
3. Object count/bytes/depth and malformed/oversized responses refuse.
4. Existing ref exact-old success and authenticated absent-ref creation.
5. Atomic concurrent writer rejection even when an ordinary fast-forward works.
6. Non-ancestor target refusal, with all remote refs unchanged.
7. Wrong repository ID/name/endpoint/fingerprint/source/ref rejection.
8. Missing/partial protection, active rules and missing permission refusal.
9. API401/403/409/422/429 and malformed replies retain honest uncertainty.
10. Failed/mismatched object upload cannot update any ref.
11. Lost acknowledgement after actual CAS is reobserved exactly once.
12. Duplicate submit and restart cannot publish twice or retry ambiguous effects.
13. Missing owner/stale generation/current guard refusal prevents mutation.
14. Head/policy/ownership changes during uploads prevent final CAS.
15. Private claim creation/corruption/symlink/absence never authorizes replay.
16. No staging refs, force, REST ref mutation, helper or credential disclosure.
17. Trusted transport origin/method/path/body/redirect bounds.
18. Enforced whole-request timeout, bounded output and confirmed child stop.
19. Actual M1–M5 Conductor journal/recovery integration with fake atomic Git server.
20. Full210 accepted regressions plus new tests on both Python versions.

## Importable implementation

`adp.execution_types.GitEffectPort` is the narrow effect protocol.
`adp.network_git.GitHubTarget`, `GitHubCAS`, `GitHubPolicyAdapter` and
`GitHubGitExecutionPort` are explicit operator selections; no controller or
environment variable enables them automatically. Construct the service with the
trusted `GitHubHTTPTransport(scoped_token, authority=issuer_verifier)`, bind a
real M5 `ExecutionJournal` to the port, and select that same service for the
policy adapter. `ScopedInstallationToken` requires an independently authenticated
GitHub App installation issuance request **and** response, explicitly restricted
to exactly the selected immutable database ID, pinned node ID, contents-write and
metadata-read permissions, and a lifetime of at most one hour. The external
`TokenScopeAuthority` must verify the actual issuance records against the private
scope subject; there is no permissive default, PAT fallback, membership-only
proof, broad installation credential, token rotation or automatic refresh.
The authority and private issuance records belong outside product/worker roots.
A caller-supplied verifier that blindly approves claims is outside this trusted
boundary, just as an untrusted M3 authority cannot establish operator permission.
Actual App provisioning/token issuance is not implemented or authorized here.
The official [installation-token contract](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)
defines explicit repository-ID selection; current installation membership alone
cannot prove that the token was issued with that immutable restriction.
The exact canonical GitHub node/database IDs, full repository name, memory ID,
remote endpoint fingerprint and branch are pinned independently of credentials.

Only network PUSH is added. Local stage/commit/branch retain accepted behavior;
the original allowlisted local-bare PUSH implementation is unchanged. M3 actual
policy/guard decisions remain mandatory, including external review/check gates.
The network-aware policy seam and handoff ref observation never invoke a Git
network helper. Coordination memory must have a **separate local file remote**:
the existing M1 network transport is not requalified or silently replaced here.

The actual PREPARED transition creates a private exclusive fsynced intent claim
and an in-process one-use dispatch capability. Only that capability can submit
the matching canonical SUBMITTED action. A recreated port cannot mint it from
SUBMITTED, even if private claim state vanished. No schema/migration is added.
Claims are never automatically deleted, rewritten or treated as retry authority.

Every bound HTTP call also writes a durable in-flight marker **before launch**.
Only a conclusively stopped transport clears it. Crash, cancellation or missing
stop receipt retains UNKNOWN across restart, blocks later HTTP and handoff, and
is surfaced as an unconfirmed Conductor context. An exact target SHA cannot
conceal a potentially live transport. Operator stop verification/reconciliation
is required; there is no automatic reset API.

## Resource and credential boundary

Only verified HTTPS to api.github.com:443 is supplied. Redirects, proxy environment,
remote helpers, arbitrary methods/routes, multiple-ref CAS, zero afterOid, force,
delete and tags are refused. Blob/tree/commit POSTs cannot update refs. Returned
OIDs must match; any normalization difference stops publication. Full closure
preflight precedes uploads. Bounds: SHA1, at most16 missing commits/two parents,
512 objects, 32 levels, 1MiB per object and 8MiB total. Submodules, extra headers,
noncanonical dates/messages/order and unrepresentable path bytes are unsupported.

An operation has a fixed45s dispatch budget and128-call maximum; no further
request launches after the dispatch budget expires. Each request has at most5s
plus bounded stop cleanup and a1MiB response cap. Supervisor probing, bounded
stop/reaping and local journal bookkeeping can extend total wall time beyond45s;
45s is not an unconditional end-to-end wall-clock guarantee. The trusted HTTP child uses TLS
verification, private stdin credentials and a minimal environment. The accepted
Linux subreaper bounds blocking DNS, TLS and partial responses, then proves stop.
No token is in command arguments, worker environment/prompts, stop receipts,
portable memory or product comments. Raw API response/error text is not reported.

M3 source/policy, M1 owner/generation, endpoint and fast-forward ancestry are
rechecked after upload immediately before atomic CAS. Stale/racing expected-old
values cannot be replaced by fast-forward-only REST semantics. Only exact
authenticated reobservation yields PRESENT; attempted old/absent/different state
is UNKNOWN. Missing rules/protection/permissions, active branch constraints,
nonempty legacy protection inventory for creation and inaccessible metadata
refuse. GitHub Enterprise/SSH, SHA256 and other provider protocols are unsupported.

## Outcome taxonomy

| Outcome | Meaning / operator boundary |
| --- | --- |
| `PRESENT` | Authenticated exact intended ref SHA, current local binding, no unconfirmed transport |
| `ABSENT` | Only an unattempted PREPARED intent with no claim and exact expected old state |
| `UNKNOWN` / conflict | Attempted old/absent/different value, lost acknowledgement without exact proof, inaccessible/malformed metadata, or uncertain stop; no automatic replay |
| `UNSUPPORTED_ATOMIC_REF` | Unsupported provider/protocol/objects/protection/credential/runtime; fail closed, local backend remains available |
| Qualification `FAIL/ERROR/TIMEOUT/SKIP/NOTRUN/UNKNOWN/UNSUPPORTED` | Observed non-PASS, kept in the original denominator; no execution or integration authority |

A known exact SHA alone never clears an uncertain transport marker. Operator
reconciliation must establish process stop and intent effects externally before
any separately authorized recovery; this implementation offers no reset shortcut.

## Qualification status and retained corrections

The original frozen new-method inventory is
[NETWORK_CAS_TEST_INVENTORY.json](NETWORK_CAS_TEST_INVENTORY.json):33 methods.
Independent review adds12 security methods in the separate
[NETWORK_CAS_SECURITY_TEST_INVENTORY.json](NETWORK_CAS_SECURITY_TEST_INVENTORY.json).
The original33 and accepted210 denominators remain unchanged. Three runner
accounting tests are separately frozen in
[M7_ACCOUNTING_TEST_INVENTORY.json](M7_ACCOUNTING_TEST_INVENTORY.json), giving48
new methods in total (33original +12security +3accounting). Existing tests/fixtures,
frozen M6 scenario maps, state schemas and guard thresholds remain unchanged.
CI runs the accepted suite and separate honest M7 runner on Python3.11/3.12.

Initial focused object10/10 and HTTP8/8 methods PASS. These use real disposable
Git objects and actual Linux process stop supervision with synthetic provider
responses. Initial committed campaigns on both Python versions passed all210
accepted methods and installation6/6, but the new33 campaign observed32PASS/1FAIL.
CI run42664168585 (candidate a794d53904d985fa8e4ceca1b22e36c1fadd39d4), job logs:
3.11 SHA256 `8ea13297f48d248df381ad59b779552c9e675ae293103cddd48fe6ad8b166a74`;
3.12 `cfb792cf1306163d105362fad9dfe087a2d3db28fa5d3e52bf66e816bde11c56`.
Run42664704267 retained the same failure after selecting the supported UTC fixture.
Independent isolation found that accepted M5 `commit-tree` supplies a legitimate
message without a final LF. The object encoder now preserves those exact bytes;
it does not rewrite the reviewed commit. Unsupported headers/dates and NULs still
refuse. Independent one-case FAIL log SHA256
`e8a4ea527935df4aadb64eabf8861d666a69550172466c342987deb5130689e4`.
Run42666556368 at8f5ab1e2a4e7777d5d58a004d3d180c65804ec16 passed both
Python jobs, including accepted210 and then-new33. This historical green run is
**not final qualification**: subsequent independent security review found the
repository-path race below. Final clean committed CI and exact-HEAD review are
recorded in Draft PR metadata; this report does not pre-approve future commits.

Earlier development integration observations were4PASS/7FAIL of11, then
10PASS/1FAIL of11. The former included concurrent development edits and cannot
serve as exact-revision evidence (log SHA256
`3dfd83d932eca3c5f5e93dca19080aef713a55bb9fb526fb68d9060e32259746`).
Six failures exposed fixture product refs accidentally sharing coordination
memory; separate disposable stores correct the fixture without excluding refs
from assertions. The remaining failures exposed the UTC/message compatibility
cases above. These observations remain failures, not retrospectively relabeled.

Independent early review found unsafe recovered dispatch, Git-helper scope and
post-error-only transport stop persistence. Fresh dispatch capabilities, local
coordination restriction and write-ahead transport fencing correct these paths.
Original stop-durability repro observed2/2 FAIL (private SHA256
`b0caba7db4fa9bad1f833427ecc034b3dfa19c7bff3df0bf2516c062a569e1cf`).
Independent corrected proof: original2/2 plus added prelaunch-persistence case1/1
PASS, SHA256 `43912e4ff565d7b58b9d589ec045283ecd5d5d6bed55c5bff182893bf2fdb625`.

Independent review at8f5ab1e reproduced a repository rename/old-path reuse race:
seven immutable objects reached a different repository ID before later CAS
identity checks refused. No ref moved, but object disclosure was a blocking
failure. Private distinct-ID repro SHA256
`cf1886e281b04b2da95cd92de65059156573c3be0b25dc1cde359ff852cfc33e`;
CHANGES_REQUIRED review SHA256
`b3d7f6d16ca1f21afd89bacf68a19b175033c634343c1fe0e8c4f93834ec52db`.
The correction requires a verified single-ID installation issuance, so the
provider denies an old path routed to another repository before object creation.
The fake authenticated server now enforces that restriction and actual Git
fast-forward ancestry. Focused scope-race/broad-scope cases2/2 PASS, object10/10
PASS and expanded HTTP11/11 PASS; the latter log SHA256 is
`526773cbae3cdd1179e10f8863a6fd5644e0bed9855990f6c42827368bfa383c`.
A further independent real-child probe observed1FAIL: a symlink-corrupt private
network hazard raised before worker cancellation. Original repro SHA256
`ec16f618d3aa10437fd0dd2dd9fc8b552ef4fbb6e462ede95924d2e9cb48fd27`.
Conductor now retains a stable UNKNOWN Git context on observation failure and
continues cancellation of every tracked worker. The added actual-child regression
requires a confirmed stop while the hazard remains UNKNOWN. Focused proof1/1
PASS (Python3.11.10), log SHA256
`eb4ea86fb8b7e0599a8f7be7b63ed0f0510e2180c9fdf368eb5e47bc057d696f`.
The prior additional security campaign passed8/8 atb58dea72a8d106ad53044245e5f54033d15bdf5a,
log SHA256 `5f405ea5bc142b89fd3dfccb8a6460b692244bb73cbce1d2f0b7df87adeba645`.
Independent corrected cleanup replay1/1PASS SHA256
`f912d2b28cae73e3a03ae0880b15694c56b0f5b41cca58c51bf847528d8860b9`;
independent corrected repository-scope proof SHA256
`1e3aaa61f160104e960b5f2c4adc1e888af43caca57179d9d0614925f5ea216c`.
The shared M7 runner also now preserves class/module setup and teardown failures
as separate fixture observations: affected original method IDs remain NOTRUN,
and any fixture ERROR/SKIP prevents aggregate PASS. The accepted M6 helper is
unchanged. Independent runner proof3/3PASS includes spoofed lifecycle-looking
ordinary IDs, which still fail strict inventory accounting (private log SHA256
`d91de3bdbf69ebfee651d6d4582d26d685ee24c8e412ee8b83aaef7f5947b6a1`).
All new security cases and fresh independent assessment remain required at the
final committed revision. No timeout, guard threshold or assertion was relaxed.

## Scenario-to-evidence map

Method names below identify exact methods in the frozen inventories. Prefixes
`G`, `H`, `O`, `S` mean `test_network_git.NetworkExecutionQualification`,
`test_network_http.NetworkHTTPTests`, `test_network_objects.ObjectQualification`,
and `test_network_security.NetworkSecurityQualification`; prepend `test_` to each
method suffix. Each method is independently accounted; subcases are not extra
PASS results. A mapped test is a procedure, not a claim that a pending run passed.

| Scenario | Concrete procedure / test method suffix | Required observation |
| --- | --- | --- |
|1|O.actual_objects_preserve_oids_without_any_refs|Real empty Git store, binary/executable/nested closure, messages with/without LF, exact OIDs and unchanged refs|
|2|O.unrepresentable_commit_headers_dates_and_encoding_refuse; O.unsafe_tree_forms_refuse|Unsupported raw forms refused before publication|
|3|O.closure_preflight_bounds_before_any_mutation; O.entire_closure_is_checked_before_upload; H.redirect_and_oversize_response_do_not_retry_or_return_data|Closure/response bounds; no partial preflight upload|
|4|G.existing_and_verified_absent_refs_preserve_exact_oid; G.verified_absence_creation_has_zero_old_comparison|Actual exact Git ref update; all unrelated refs preserved|
|5|G.atomic_race_rejects_even_when_fast_forward_would_succeed|Concurrent ancestor insertion at CAS; exact-old refusal|
|6|S.diverged_target_refuses_fresh_policy_and_server_force_false|Actual sibling divergence; M3 and fake provider refuse|
|7|G.binding_and_authorization_negatives_cannot_mutate; G.mutated_revision_has_a_fresh_dispatch_and_cannot_mutate; G.mutated_source_has_a_fresh_dispatch_and_cannot_mutate; G.mutated_expected_old_has_a_fresh_dispatch_and_cannot_mutate; S.changed_remote_endpoint_or_memory_identity_refuses_before_http; O.ref_inventory_requires_complete_identity_and_pagination|Fresh capabilities per mutation; wrong identity, endpoint and source refused|
|8|G.absent_ref_legacy_protection_is_not_inferred_from_404; G.rules_permissions_upload_failures_and_uncertainty_refuse; H.broad_pat_unverified_and_incomplete_issuance_scopes_are_refused|Known permissions/protection and narrow authenticated issuance required|
|9|O.http_error_and_malformed_replies_remain_unknown; G.rules_permissions_upload_failures_and_uncertainty_refuse|401/403/409/422/429, incomplete/malformed reply never success|
|10|O.upload_mismatches_and_failures_preserve_all_refs; G.rules_permissions_upload_failures_and_uncertainty_refuse|Object failure or changed OID cannot publish|
|11|G.lost_acknowledgement_reobserves_once_and_restart_never_resubmits|One actual ref mutation, exact authenticated reobservation|
|12|G.submitted_old_absent_changed_or_missing_claim_never_retries|Restarted SUBMITTED remains uncertain; no fresh capability|
|13|G.mutated_generation_has_a_fresh_dispatch_and_cannot_mutate; S.actual_owner_credential_loss_during_upload_prevents_cas; accepted tests listed below|Actual owner loss and stale generation stop publication; mandatory guard preserved|
|14|G.source_drift_during_upload_prevents_cas; S.verified_policy_revocation_during_upload_prevents_cas; S.actual_owner_credential_loss_during_upload_prevents_cas|Post-upload reauthorization refuses drift before CAS|
|15|S.private_claim_corruption_refuses_before_any_object_upload; S.symlinked_private_claim_never_follows_an_outside_file; G.submitted_old_absent_changed_or_missing_claim_never_retries|Corrupt/symlink/missing claim grants no replay|
|16|S.reused_repository_path_is_denied_by_selected_id_before_object_write; H.repository_binding_and_mutation_node_cannot_escape_credential_scope; H.real_supervisor_response_and_secrets_never_enter_argv_environment_or_receipt|Zero wrong-repository objects, no staging refs/force/deletion/helper or token disclosure|
|17|H.routes_force_delete_and_credential_urls_refuse_before_token_access; H.child_uses_only_verified_fixed_https_origin_and_private_authorization; H.exact_cas_and_canonical_encoded_branch_routes_are_accepted|Fixed verified origin and constrained request grammar|
|18|H.real_whole_request_deadline_reaps_detached_child; H.unsupported_capability_and_unconfirmed_receipt_never_create_success; O.interrupted_transport_is_write_ahead_fenced_across_restart; O.failed_stop_boundary_persistence_never_launches_transport; S.unreadable_network_hazard_preserves_unknown_and_cancels_real_worker|Actual descendant stop or durable UNKNOWN, no retry/handoff|
|19|G.conductor_runs_and_reobserves_real_journal_without_helpers|Actual accepted M1–M5 Conductor, journal, policy and guard; controlled HTTP/local forge|
|20|Unchanged accepted210 inventory plus both M7 inventories, CI Python3.11/3.12|Every original method accounted; non-PASS never promoted|

Scenario13 also retains accepted `test_guard` coverage in the frozen inventory,
specifically method suffixes
`test_reservation_prevents_alternate_worker_or_duplicate_terminal_result`,
`test_generation_drift_requires_explicit_unknown_abandonment`, and
`test_two_bounded_proofs_then_terminal_operator_boundary`, plus all accepted
execution admission/guard regressions. These are not claimed as extra new tests.

Real GitHub write qualification: **NOTRUN**, reserved for separately authorized
M8. Offline provider-contract qualification cannot establish live GitHub behavior,
App permission availability or production latency. Missing actual metadata or a
provider-normalized object is a refusal, not an invented compatibility claim.
Private evidence is host-lifetime and must be retained by the operator for later
audit. Public release, merge, tag and deployment: **NOT_AUTHORIZED**.
