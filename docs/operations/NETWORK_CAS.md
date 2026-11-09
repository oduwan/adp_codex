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

Implementation and final qualification: **NOTRUN at this G0 commit**.
Real GitHub write readiness: **NOTRUN**, reserved for separately authorized M8.
Public release, merge, tag and deployment: **NOT_AUTHORIZED**.
