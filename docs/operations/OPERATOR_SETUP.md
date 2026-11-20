# Installed operator setup and finite project delegation

Issue #17 adds a data-configured entry point to the accepted #22 lifecycle. It
composes the existing M1/M2/M3/M4, network Git CAS (#14), project evidence (#21)
and GitHub product flow (#16) ports. It does not provision a project environment,
interpret issue text as permission, or supply a test runner. The advanced
`--controller /absolute/operator/controller.py` interface remains available.

This interface requires project-owned, authenticated policy, independent scope
assessment and check evidence providers. The installed JSON format below is the
standard data boundary for those providers: a user does not implement a Python
controller. A project without those mandatory providers remains `UNKNOWN` or
`BLOCKED_OPERATOR`; installing a token/profile does not invent them. Providers
may refresh their protected data files through the project's own trusted tools.
Their refresh is not an ADP background service or authority renewal.

## Trust and installation

Select an operator-owned installation directory outside every product checkout,
shared Git administration directory, coordination repository/remote, memory
worktree and private execution-evidence directory. JSON files and verifier keys
must be owned, regular, single-link files with mode `0600`; directories should be
`0700`. Paths are absolute and normalized; symlinks are refused. Never put these
files in Git, worker prompts, shell arguments containing a token, or portable
memory. Keep the entire installation outside source roots even for a disposable
project. Do not use a root account for routine target work.

`--operator-trust` selects the trust root explicitly. A profile cannot select or
replace its verifier. Its closed schema is:

```json
{"schema_version":1,"principals":[
  {"id":"canonical-operator","roles":["operator"],"repositories":["123"],"key_file":"/owned/operator/keys/operator.json"},
  {"id":"installed-automation","roles":["automation"],"repositories":["123"],"key_file":"/owned/operator/keys/automation.json"}
]}
```

Also install distinct canonical principals for `project-policy`,
`scope-reviewer`, `project-check` and `token-issuer` as required. Each key file is
`{"schema_version":1,"key_hex":"<64 lowercase hexadecimal digits>"}`. Duplicate
key material cannot masquerade as an independent principal. Canonical identity
mapping is a trusted operator responsibility: an issue author cannot be renamed
into an independent approver. Only install principals actually authorized by the
project; credentials alone do not establish that authority. HMAC verification
keys are signing-capable secrets, available only to trusted operator/provider
code. These are not public-key signatures or untrusted plugin inputs.

Every signed document has exactly `schema_version`, `kind`, `signer`, `issued_at`,
`expires_at`, `payload`, `signature`. Version is integer 1; timestamps are UTC
integer seconds, with lifetime at most 3600 seconds. `payload.repository_id` is
the immutable GitHub database ID as a string. Signature is HMAC-SHA256 of the
UTF-8 string `adp/operator/v1:` followed by the SHA256 digest of the canonical
unsigned document. Canonical JSON uses ADP's `schema.encode`: sorted keys,
ASCII escaping, compact separators and a final newline. Signatures cover kind,
repository, all payload bytes and original times. Use the existing trusted issuer
or operator tooling; ADP neither mints GitHub credentials nor installs an issuer.
Do not hand an automation key to a project worker.

Roles by document kind: `profile`, `revocations`, `operator-decision` and
`scope-addition` require `operator`; `policy` requires `project-policy`;
`assessment` and `decision` require `scope-reviewer`; `project-evidence` requires
`project-check`; `credential` requires `token-issuer`. Private internal receipts
are separately domain-bound to the selected automation principal and profile.
They are evidence, not a new capability or a reset of any M2 counter.

## Profile schema

The signed `profile.payload` has these required fields; no executable fields,
imports, shell expressions, arbitrary endpoints, callbacks or extra keys exist:

```json
{
  "id":"project-window-1", "repository_id":"123", "authority":"installed-automation",
  "repository":{"name":"owner/project","node_id":"R_actual","database_id":123,"remote":"origin"},
  "memory":{"repo":"/owned/coordination","remote":"memory","branch":"coordination/track",
    "storage":"/owned/memory","private_state":"/owned/private-evidence","owner":"operator-session"},
  "window":{"id":"<64 hex>","issued_at":1,"expires_at":301,
    "maximum_rounds":8,"maximum_tasks":1,"maximum_parallel":1},
  "delegation":{"issues":["I_actual"],"operations":["INSPECT","EDIT","STAGE","COMMIT","VALIDATE","PUSH","PR","REPORT"],
    "branches":["refs/heads/work/task"],"merge_mode":"MANUAL","merge_methods":["merge"],
    "merge_envelope":"HEAD_ATOMIC_BASE_OBSERVED","ticket_envelope":null,"allow_setup":true,"allow_claim":true,"reviews":1},
  "providers":{"policy":"/owned/operator/policy.json","assessment":"/owned/operator/assessment.json",
    "decisions":"/owned/operator/decisions.json","decision_socket":null,"revocations":"/owned/operator/revocations.json",
    "validation":{"kind":"signed","path":"/owned/operator/results.json","mode":"COMMITTED","maximum_age":300,
      "result_maximum_age":300,"maximum_observations":8},
    "credentials":{"read":"/owned/operator/read.json","cas":"/owned/operator/cas.json",
      "forge":"/owned/operator/forge.json","ticket":null}},
  "tasks":[{"issue_id":"I_actual","number":1,"task_id":"issue:1","slug":"task",
    "workspace":"/owned/project-lane","expected_revision":"<exact commit SHA>"}],
  "checks":[{"name":"unit","provider":"project","origin":"project:owned-ci","phase":"BEFORE_PR",
    "denominator":null,"native_record_is_attempt":false}]
}
```

Replace placeholders and timestamps with authenticated actual facts. The ID,
window, original scope and baseline are frozen before execution. Profile expiry
also bounds the track window: at most one hour, eight tasks, four parallel lanes,
32 total rounds, four rounds per invocation. M2's original failure/correction/
review/stall limits remain unchanged. Tasks, issue IDs and workspaces must be
unique. Existing isolated checkouts must already be on explicitly delegated
feature branches with the correct canonical HTTPS GitHub remote. This interface
does not create worktrees or give a worker Git-administration access.

Memory uses an existing owned local Git coordination checkout and local bare
remote, separately from all product sources. This preserves #14's current network
M1 limitation. For an owned new project on Linux/WSL Bash, an operator can prepare
those locations using normal Git, for example:

```bash
git init --bare --initial-branch=trunk /owned/coordination.git
git init --initial-branch=trunk /owned/coordination
git -C /owned/coordination config user.name 'Approved identity'
git -C /owned/coordination config user.email 'approved@example.org'
git -C /owned/coordination remote add memory /owned/coordination.git
```

These are operator preparation commands, not commands inferred from the target
issue or run by `preview`. Use the project's own approved author identity.

## Provider data and provenance

`policy.payload` contains `repository_id`, `document_inventory_digest`, `paths`
(`governance`, `profiles`, `contracts` arrays), `sources` (accepted M3
`SourceClaim` values with `evidence:null`) and `protections` (accepted M3
`Protection` values with `evidence:null`). The digest is
`operator_providers.policy_semantics(actual_snapshot)`: repository identity,
canonical remote fingerprint and every selected committed document, including
its hash and parsed profile. Only unchanged reviewed policy semantics may be
mechanically bound to the current local SHA/ref. Original source/protection
observation times and expiry are retained. Protected remote revisions must
still match. Unknown protection/permission fields remain unknown; the native
#14/#16 backends also perform their own current provider checks. A provider must
actually verify governance acceptance and GitHub permissions/protection; a
caller positive label is not that verification. A policy feed cannot extend
profile delegation or grant release/deployment/force rights.

`assessment.payload` contains `repository_id`, `snapshot_digest` and `tasks`.
The digest is `operator_authority.remote_semantics(snapshots)`: the full sorted
M4 remote inventory including issue bodies, source references, versions,
authors, relations, PR HEADs and coverage, excluding only top-level observation
time and repository `memory_id`/`checkout_ref`/`checkout_sha`. Those local fields
are separately bound by M1/M3. Each task row contains:

- `issue_id`, `original_issue_digest` (full frozen original `Issue` digest),
  `policy_semantics` (`operator_providers.assessment_policy(inspection)`, covering the document identity, every selected interpreted rule and canonical policy principal; observation times and local revision bindings are excluded).
- `scope`: the complete accepted `OriginalScope` value, including all clauses,
  paths, checks and dependencies. Only `original_reference` and `evidence` are
  null; the archive reference is assigned after matching the frozen original.
- `proposal`: the complete accepted `Proposal`, including exact current issue
  revision, parts, changes, instructions and exit conditions. Only
  `original_reference` and `policy_digest` are null mechanical bindings.
- `readiness`: the complete accepted M4 `ReadinessReview`, with `evidence:null`;
  all semantics and its original timestamps are signed.
- `dependency_edits`: the complete reviewed list of accepted native `DependencyEdit` values (empty when no existing edge changes).
- `preparer`: the canonical preparer identity, distinct from the independent
  signer and all original issue authors.

The first original interpretation is retained privately. A refreshed assessment
cannot add paths, checks, dependencies, acceptance or functionality to it. The
independent signer remains visible in every derived receipt and expiry is never
renewed by rebinding. A missing, stale or contradictory assessment remains
`UNKNOWN`/`BLOCKED_OPERATOR`. It cannot authorize a code worker merely by
classifying an issue `READY`.

`decisions.json` is an unsigned container with exactly `schema_version:1` and
`decisions`, a bounded array of individually signed `decision` or
`operator-decision` envelopes. Each payload has `repository_id`, `purpose`,
`subject`, `context_digest`; all three exact approval bindings must match the
accepted port's actual request. No wildcard approval, path-only semantic scope
approval or global `approve_scope` flag exists. Independent project services
supply semantic within-ticket classification (including actual change scope)
through this boundary. Unknown/new functionality needs its own external
operator approval; a profile never supplies it automatically. Missing semantic
provider capability blocks that action; do not manufacture approvals to advance
a demonstration. Ticket splitting conserves the original scope; this interface
does not create replacement issues or supply a closure backend.

The signed `revocations.payload` is `repository_id`, monotonic `sequence`, and
`revoked` profile IDs. Its current signed inventory is consulted at grants and
verification, including final external-effect checks. Setup/execution retain a
high-water sequence and refuse rollback or different bytes at an equal sequence.
A read-only command compares existing retained state without writing it. Retain
revocation data until all associated execution/effect history is reconciled.

Each `credential.payload` has `repository_id`, the complete private accepted
`ScopedInstallationToken` value (`evidence:null`), and authenticated actual
`issuance_request` and `issuance_response` records. Request fields are
`installation_id`, singleton `repository_ids`, exact permission map. Response
fields are `token_sha256`, singleton `repository_ids`, `repository_node_id`,
exact permissions, `issued_at`, `expires_at`. The external issuer must verify the
actual GitHub App issuance request/response and token bytes, not merely sign
unverified caller labels. Both original issuance provenance references remain in
the typed token. Tokens are pinned for their instance, at most one hour, without
refresh/fallback to PATs or broad credentials. Separate files are required for:

- Discovery/evidence read: checks, contents, issues, metadata, pull_requests,
  statuses, all `read`.
- CAS: contents `write`, metadata `read`.
- Forge: contents/issues/pull_requests `write`, metadata `read`.
- Optional ticket edits: issues `write`, metadata `read`.

Credential material and issuance proof stay in these protected files. They never
enter internal receipt storage, portable memory, stdout, product reports or
worker prompts. Only content-addressed provenance references leave a provider.

## Project checks and merge boundaries

The target owns its languages, commands, CI, runner and execution security.
Signed `project-evidence.payload` has `repository_id`, the exact accepted
`EvidenceRequest` in `request`, `results` (actual `ProjectResult` values),
`observed_at`, `complete`, `coverage`. The source rebinds only the fresh
observation nonce; request SHA/ref/phase/generation/attempt, origins, original
counts and all results remain authenticated. A failed/error check is ordinary
feedback to #22 within the same M2 budget. Missing/pending/partial/quarantined
results never become PASS. No check command is accepted in a profile.

The standard signed sequence is `COMMITTED`: commit, obtain prescribed pre-PR
project evidence, review, then use #16. `validation.kind:"github"` supports
`mode:"POST_PR"` and AFTER_PR checks only. It observes actual native GitHub
check/status records, preserving unknown case denominators and attempt numbers.
A project must explicitly accept native job identity as an attempt when that is
its rule. `CANDIDATE` execution and project action dispatch require an advanced
explicitly installed project port; this standard interface does not invent one.

Automatic merge additionally requires `MERGE` in delegated operations,
`merge_mode:"DELEGATED"`, an allowed merge/squash method, fresh actual PR identity,
ready (not Draft) state, exact HEAD, current branch/protection/check evidence and
independent exact-SHA approval. GitHub's native merge has atomic HEAD but only an
observed base precondition: explicitly accepted `HEAD_ATOMIC_BASE_OBSERVED` is
required. `ATOMIC_BASE` remains unsupported. Human-merge projects wait at
`WAITING_HUMAN_APPROVAL`; credentials and green CI are never merge authority.
Draft readiness is a project decision, not silently changed by this CLI.

## Commands and restart

All selectors are installed absolute paths; examples use placeholders, not live
product authority:

```bash
adp setup --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json --dry-run
adp doctor --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json
adp preview --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json
adp setup --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json --apply --authorize-memory-write
adp status --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json
adp run --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json --authorize-execution --rounds 1 --maximum-parallel 1
adp resume --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json --authorize-execution --rounds 1
adp handoff --operator-profile /owned/operator/profile.json --operator-trust /owned/operator/trust.json --authorize-execution
```

Setup apply writes only owned coordination/private state, explicitly upgrades
M1→M2→execution→product→track, and reobserves an interrupted setup without
reclaiming/resetting a generation or existing counters. Status/doctor/preview do
not claim, recover, migrate, reserve, create archives or change refs/memory.
Status reports liveness `UNKNOWN`; it does not promise continuing work. Run and
resume are synchronous finite commands using the actual Codex runtime and
accepted stop supervision. They do not spawn a daemon. This Issue17 qualification
uses synthetic focused cases; genuine full lifecycle proof remains **NOTRUN,
deferred to M8**. Capability support is checked by the existing execution entry
before worker dispatch, not inferred from a successful preview.

Keep the installed profile/trust, private enrollment, revocation high-water mark,
original/packet archive, authority receipts, runtime stop receipts and project
observation/action journals across restart. Missing history blocks recovery.
Never recreate it or change a window ID to reset a consumed budget. Source
changes invalidate review; unresolved external effects are observed using their
original durable intents and never blindly resubmitted. Profile/policy/key
changes, expiry, revocation, foreign owners and incompatible history require
explicit operator reconciliation. Use accepted M1 confirmed-stop handoff and
#22 generation adoption; already reviewed-SHA ownership transfer retains its
documented unsupported boundary. Public product comments remain one substantive
outcome per completed iteration, with no raw transcripts or orchestrator chatter.

## Qualification

The focused inventory is frozen in `OPERATOR_SETUP_TEST_INVENTORY.json`. It
covers protected profiles, two policy configurations, admission/scope/evidence
refusal, idempotent enrollment, actual installed port construction, legacy CLI
compatibility and bounded CLI routing. The accepted 400-test baseline is retained
unchanged. Tests use disposable sources and synthetic data; they do not establish
live GitHub effects or a genuine Codex lifecycle PASS. Existing Python 3.11/3.12
CI runs the inventories; no new CI infrastructure is added.

## Live decision transport

`providers.decision_socket` is either null or an absolute protected Unix-domain
socket path for an **already installed project authority provider**. ADP starts
no process or service and implements no semantic classifier. On Linux the peer
must have the operator UID, an owned mode-0600 socket and mode-0700 parent; peer
credentials and the socket inode are checked before/after the exchange. The
exchange is limited to one second and 1 MiB each direction, within the existing
M2 action deadline. Unsupported platforms/providers fail closed.

If no exact static decision exists, the installed port connects once, sends
canonical JSON then shuts down its write side. The challenge has exactly
`schema_version:1`, `repository_id`, `profile_digest`, `purpose`, `subject`,
`context`, `context_digest`, `required_kind`. It contains the actual complete
private port context, so the project authority can independently classify the
original scope and actual diff/review facts. The peer returns one signed
`decision`/`operator-decision` envelope using the schema above, then EOF. The
signature must bind the precise purpose, subject and full context digest, have
the required canonical independent/operator role, and be current. No response is
accepted simply because the peer's UID matched. Signed responses are retained
immutably as private provenance. Missing/unavailable evidence identifies the
required purpose and provider action, never becomes permission, and never resets
a window, reservation or worker budget. This data adapter makes ordinary
project-provider decisions available synchronously without a custom Python
controller or manual per-commit operator approval. A missing genuine semantic
provider remains a mandatory capability limitation.

Use `doctor --check-runtime` for an optional bounded **capability-only** observation
of the installed Codex CLI version/help and accepted child-supervisor support.
It launches no model worker, creates no runtime directory and is not genuine
lifecycle proof. Without this option each runtime feature is explicitly UNKNOWN.
Run still rechecks its own runtime instance rather than reusing a doctor receipt.
After an independently confirmed M1 handoff/claim, `resume --adopt-generation
--authorize-execution` calls the accepted finite-window adoption path. It requires
an authenticated `track/adopt-generation` decision and preserves all counters,
expiry and unknown-effect/reviewed-SHA limits.

The same installed data socket can answer `policy/inspect` (`required_kind:policy`,
actual typed policy snapshot), `track/assessment` (`required_kind:assessment`,
actual remote snapshots), and `project-validation/observe`
(`required_kind:project-evidence`, actual typed #21 query). Signed static files
are used when they match; unavailable/stale bindings request fresh actual data.
Responses retain each kind's closed payload schema above and are revalidated
against the actual request before use. The provider must independently observe
project policy/check provenance and review semantic scope; it must not echo
caller claims as approval. No ADP command executes project checks or starts this
provider. Initial configured policy-selection data must already be installed.

Ordinary existing-ticket edits require `TICKET_EDIT` plus explicit
`delegation.ticket_envelope:"OBSERVED_VERSION"`, actual independently authenticated
preparation, and current M3/M1/M2 gates. The accepted native publisher performs its
fresh read/compare/write checks; there is no claimed atomic issue-version CAS.
New functionality still requires a separate current operator decision bound to
the exact original/version/change, obtained through `ticket/scope-addition`.
`maximum_age`, `result_maximum_age` and `maximum_observations` explicitly configure
the project's evidence acceptance/finiteness within the installed supported
bounds; they are not a CI procedure or an instruction to run tests.

Issue #17 scope was frozen before implementation at accepted main
`04f4a8a0ef870dd188dc965b4f0f130d4b7edb0a`; the original issue snapshot digest is
`be7d8348d96da87882e72736eddd4c3585aec67afa40727a9135e2d081dd667f`.
No ticket/dependency edits, scope additions, new CI workflow, sandbox, test runner,
live target access or M8 qualification were performed. The 44 focused test IDs
were frozen before their first run; all 400 accepted regressions are retained.
