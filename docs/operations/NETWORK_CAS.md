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
trusted `GitHubHTTPTransport(token_provider)`, bind a real M5 `ExecutionJournal`
to the port, and select that same service for the policy adapter. The token
provider is trusted, nonblocking operator code outside product/worker roots.
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

An operation has a fixed45s/128-call ceiling; each request has at most5s plus
bounded stop cleanup and a1MiB response cap. The trusted HTTP child uses TLS
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

## Qualification status and retained corrections

The frozen new-method inventory is [NETWORK_CAS_TEST_INVENTORY.json](NETWORK_CAS_TEST_INVENTORY.json):
33 methods, in addition to all210 accepted M1–M6 methods. Existing tests/fixtures,
frozen M6 scenario maps, state schemas and guard thresholds remain unchanged.
CI runs the accepted suite and separate honest M7 runner on Python3.11/3.12.

Initial offline transport8/8 and object10/10 focused methods PASS. These use real
disposable Git objects and actual Linux process stop supervision, but synthetic
authenticated provider responses. No actual target GitHub write occurred.
Full33-method integration campaign and both-Python regressions are **NOTRUN at
this implementation checkpoint**, pending the clean committed CI candidate.
Independent final exact-HEAD review is also pending; Draft PR metadata will carry
the final source/CI/verdict attestations without embedding future approvals here.

Independent early review found unsafe recovered dispatch, Git helper scope and
post-error-only transport stop persistence. Fresh dispatch capabilities, local
coordination restriction and write-ahead transport fencing correct these paths.
Original stop-durability repro observed2/2 FAIL (private SHA256
`b0caba7db4fa9bad1f833427ecc034b3dfa19c7bff3df0bf2516c062a569e1cf`).
Independent corrected proof: original2/2 plus added prelaunch-persistence case1/1
PASS, SHA256 `43912e4ff565d7b58b9d589ec045283ecd5d5d6bed55c5bff182893bf2fdb625`.
First integration observations include ordinary FAIL and remain retained, not
counted as PASS. Fixture isolation and fresh-capability assertions are being
qualified; no timeout/threshold/assertion is weakened to hide them.

Real GitHub write qualification: **NOTRUN**, reserved for separately authorized
M8. Offline provider-contract qualification cannot establish live GitHub behavior,
App permission availability or production latency. Missing actual metadata or a
provider-normalized object is a refusal, not an invented compatibility claim.
Private evidence is host-lifetime and must be retained by the operator for later
audit. Public release, merge, tag and deployment: **NOT_AUTHORIZED**.
