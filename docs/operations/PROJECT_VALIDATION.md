# Project-owned validation evidence

Issue #21 adds an explicit project validation evidence port. The target project
owns its tests, CI procedures, languages, tools, environment, scheduling,
acceptance policy and environment security. ADP obtains and verifies prescribed
results. It does not install tools, write CI YAML, provision a runner/container,
choose test commands or certify a universal project sandbox. The abandoned
Issue #15 / unmerged PR #20 supplies no accepted runtime prerequisite.

## Interfaces and trust

`adp.project_validation_types` defines immutable `RequiredCheck`, `EvidencePolicy`,
`EvidenceRequest`, `ProjectResult`, `ProjectObservation` and `EvidenceGate` records.
`ProjectValidation` consumes the accepted M3 provider/task and an explicitly
installed source. There is no automatic controller, CLI switch or permissive
verifier. Source observations alone grant no execution or acceptance authority.

The trusted controller constructs an authenticated `EvidencePolicy` bound to the
current M3 `VALIDATE` plan, its exact policy digest and complete required check
names. Each phase-specific check additionally names its provider and canonical
origin. Requests bind repository, source ref, full SHA, task/generation/epoch/
iteration, phase and any PR identity. Only current M3 `Decision(ALLOW)` with actual
M1 ownership and M2 safety can admit an observation or project action. A caller's
positive boolean, issue text, credentials or a green aggregate cannot replace it.

The existing externally authenticated M3 authority also verifies these separate
purpose domains and exact public subject hashes:

| Purpose | Subject and required authority |
| --- | --- |
| `project-validation/policy` | `policy_subject(plan, policy)`; accepted project interpretation of phases, check identities, origins, original counts when supplied, native record provenance and optional action |
| `project-validation/observation` | `observation_subject(query, observation)`; actual project/provider provenance, exact source/run/attempt/current inventory, completeness and observation time |
| `project-validation/action` | `action_subject(request, action_id, key)`; separate explicit authority for this project-exposed action and durable exact request |

There is no default implementation of that authority. A verifier which accepts
arbitrary caller claims destroys the boundary. The trusted adapter/signer must
authenticate the actual provider data and canonical identity mapping; signing
whatever a worker supplies is insufficient. Worker/CI text never becomes code or
authority. Opaque run/attempt identifiers and the actual provider status survive;
recognized credential shapes in structured identifiers are refused without
echoing their contents. Raw CI descriptions, logs and provider error bodies are
not included in portable state or product comments.

`ReportedEvidence(observer)` supports project-reported local or external results
through a trusted bounded integration. The integration authenticates the receipt
and current inventory; receipt presence alone is not proof. It can support any
project language or CI provider. ADP contains no generalized command executor.

## GitHub read-only adapter

`GitHubEvidenceSource(name, repository_id, github_id, checks, transport, ...)`
binds the project's opaque M3 repository ID to an explicitly pinned GitHub REST
repository ID and canonical selected name. It uses GETs for repository metadata,
the exact source branch, optional current PR, per-commit statuses, check suites
and check runs. It never dispatches a workflow or creates/updates a GitHub object.
`GitHubValidationHTTP(token)` permits only fixed-origin HTTPS GET routes, rejects
redirects, bounds response sizes and propagates the observation's remaining time
to every request. It never follows a CI URL or retains an error body.

Both inventories and repository/ref/PR context are observed again. Drift makes
the observation incomplete. Complete bounded pagination is mandatory, with
duplicate/overlapping/unsafe links refused. Permission, rate-limit, unsupported
metadata and exhausted bounds remain incomplete/UNKNOWN; no retry sleeps or
permission escalation occur. The inventory bound is 256 records per endpoint,
1 MiB per response and at most 20 pages. Full terminal pages require another
page. The suite inventory prevents claiming completeness beyond the reference
endpoint's documented 1000-suite truncation envelope. REST is not a transaction;
future acceptance/merge execution must freshly reobserve its own exact gates.

Commit statuses use GitHub's documented newest-first order per context. Check
run ordering does not establish arbitrary rerun supersession: multiple records
for the same name/app remain ambiguous and cannot qualify. A project-specific
adapter may authenticate its own authoritative current-run selection instead.
Missing required checks, irrelevant green checks, wrong origins/repositories,
fork PRs, stale refs and earlier SHAs never qualify. Initial GitHub support
requires the PR head and base to belong to the pinned repository; cross-fork
validation is explicitly unsupported rather than guessed.

Generic check/status records do not inherently supply a workflow attempt number.
`attempt_id` remains unavailable (`None`). A project must explicitly authenticate
`native_record_is_attempt=True` if the concrete native record identity is an
acceptable equivalent provenance for its check. Otherwise the gate stays UNKNOWN.
This adapter does not infer GitHub Actions, workflow names or attempt1 from IDs.

API semantics: [check runs](https://docs.github.com/en/rest/checks/runs),
[commit statuses](https://docs.github.com/en/rest/commits/statuses).

## Outcomes, counts and phases

Results retain `PASS/FAIL/ERROR/TIMEOUT/SKIP/NOTRUN/UNKNOWN/PENDING/CANCELLED`, native
status, complete/current markers, run/attempt identity and provider record time.
GitHub queued/in-progress/waiting/requested/pending are PENDING; skipped/neutral
are SKIP; stale is UNKNOWN; action-required is ERROR. Neither cancellation nor
skip/neutral yields PASS. Pending records without provider start/completion time
use the actual observation time; this does not invent a run start timestamp.

Where supplied, the original positive denominator, all seven original outcome
counts and quarantine count must agree exactly. All-PASS and no quarantines are
required for PASS. Job-only success retains `denominator=None` and empty counts;
it is never rewritten as one passing test. Only a project policy accepting that
job-level evidence can qualify it. Observation attestation freshness is bounded
separately from the optional project-owned `result_maximum_age`: freshly
reobserved current-SHA evidence is not arbitrarily expired by ADP just because
the underlying check completed earlier.

`observe(BEFORE_PR, ...)` supports prescribed pre-PR checks. `AFTER_PR` requires a
specific PR identity and its current exact HEAD; an earlier phase never satisfies
the later one. `EvidenceGate.qualified` qualifies only that configured phase.
It does not establish independent Reviewer approval, final product acceptance,
M3 merge authorization or a completed product iteration. Required post-PR
evidence can remain PENDING after a Draft PR. Missing/unverified evidence remains
UNKNOWN. Completed FAIL/ERROR/TIMEOUT/CANCELLED is actionable development feedback,
not an automatic unsafe/operator latch; normal in-ticket correction remains
bounded by accepted M2.

The accepted M3 `Check` and M5 `ValidationResult` require per-case denominators.
This new port deliberately does not fabricate those records for job-only CI.
No M1/M2/M3 schema or accepted Conductor behavior is changed. Final Conductor,
Draft-PR-before-CI, merge and report wiring remains **BLOCKED_DEPENDENCY on #16**;
Issue #21 does not implement or presume that unmerged interface. The old
trusted-disposable validator remains available solely for its accepted fixtures,
not as a required universal project environment.

## Finite observation, restart and actions

The controller supplies an owned mode0700 private journal directory outside
product/memory/controller/authentication roots. Journal files are mode0600,
bounded, atomic and locked. At most32 contexts and32 observations per context are
admitted. The configured limit is preserved on restart. The journal stores only
request/session hashes, counters, observation digest/time and action delivery
state; no raw check text, credentials or transcripts. Accepted M1 owner/generation
and M2 counters remain authoritative and cannot be reset through these files.

`observe` writes an in-flight observation and consumes its counter before calling
the source. A restart performs a new nonce-bound authoritative observation; it
never promotes a cached old PASS. Missing replies remain incomplete. Every
returned observation is checked against the exact query nonce, current policy,
source and ownership/guard context. An interrupted read consumes budget without
inventing a completed result. `poll(maximum=..., seconds=...)` is synchronous,
finite and does not sleep or become a daemon. The built-in GET adapter shares
the remaining deadline across requests; late results cannot qualify. Custom
trusted integrations must honor the query budget and return synchronously. ADP
does not claim to contain arbitrary installed controller code. The urllib socket
timeout is not a process-level hard preemption guarantee for slow reads or host
resolver behavior; the result deadline is checked on return. Deployments needing
hard request preemption must supply an appropriately bounded trusted transport.

`request_action` is optional and requires both current exact M3 authorization
and a separate exact project-action attestation. The controller supplies the
project-owned action adapter; ADP never invents argv or prepares its environment.
`action_key` prepares its durable subject. The journal records SUBMITTED before
the callback. A returned request is only an acknowledgment, not job completion.
Lost/unknown delivery never causes automatic resubmission, including after
restart. Results must authoritatively bind the submitted action key before they
can reconcile it; an unrelated earlier green run is insufficient. Generic
GitHub records do not provide this binding automatically. No API claims to stop,
cancel, kill or reap externally managed jobs. Operator recovery uses the actual
project/provider receipt; it never clears uncertainty by claiming cessation.

## Qualification

The frozen additive inventory is `PROJECT_VALIDATION_TEST_INVENTORY.json` (24
methods). It covers a real disposable non-Python project's prescribed shell
check/evidence and an unrelated synthetic GitHub post-PR profile; the latter is
not live GitHub qualification. Positive/negative evidence binding, all statuses,
counts, missing/stale/superseded/duplicate data, partial/rate/permission failures,
finite polling, restart, lost action response and strict discovery preservation
are included. Existing210 M1–M6 and48 M7-A/accounting cases remain unchanged.

Use existing repository checks on Python3.11 and3.12; no new CI workflow or test
infrastructure is introduced. The existing M7 inventory wildcard includes these
focused checks. Full M8 integration, existing live projects, real GitHub target
writes, merge/release/deployment and automatic enablement are not authorized.
