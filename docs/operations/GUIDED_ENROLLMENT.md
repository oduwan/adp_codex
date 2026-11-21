# Guided project enrollment

Use `adp enroll` from the managed [ADP installation](INSTALL_ADP.md), or use
its absolute launcher path. Enrollment supports explicitly selected GitHub.com
projects with canonical HTTPS remotes. First-use setup selects one open issue
and one existing feature checkout. The native discovery inventory may contain
many issues and their dependency edges. An existing multi-task profile can be
reconnected through the accepted operator interface.

## Inspect and propose

```bash
adp enroll inspect --repo /owned/project --remote origin
adp enroll plan --repo /owned/project --remote origin --issue 7 \
  --directory /owned/setup/project \
  --operator-trust /owned/authority/trust.json \
  --operator-socket /owned/authority/enrollment.sock
```

Add `--github-id` when you already know the immutable repository database ID.
The bootstrap read credential comes from `GH_TOKEN` or
`gh auth token --hostname github.com`. Use `--token-env` to select a different
environment variable name. Pass only the variable name. The bootstrap token
serves GitHub discovery. Provider credentials for installed operations come
from the independent issuer.

Inspection observes the canonical database and node IDs, checkout branch and
SHA, native issue dependencies, committed governance and workflow files,
visible branch rule and required-check contexts, and Codex CLI capabilities.
Missing or incomplete observations remain `UNKNOWN`. A workflow file or
native check name supplies an observation. Project-owned providers establish
the check contract and its evidence.

The plan uses an explicitly selected operator service and independently
provisioned trust root. The service chooses the bounded delegation, local
coordination and evidence paths, and provider bindings for review. A proposal
selects an existing owned local coordination checkout and its direct local
bare Git remote with an explicit Git author. The operator selects the feature
checkout, issue, service, trust root and destination, then approves or
declines the proposed effects. Keep protected paths outside product, installer,
coordination and evidence roots as required by the
[installed operator contract](OPERATOR_SETUP.md).

## Operator service protocol

The service is installed and controlled by the operator. ADP connects using
the existing owned mode-`0600` Unix socket protocol with same-user peer
authentication, a bounded JSON exchange and the existing deadline. Its
parent directory must be owned and mode `0700`. The v1 request contains
`schema_version`, `purpose` with value `enrollment/profile`,
`required_kind` with value `profile`, `repository_id`, `trust_digest`,
`context_digest`, and `context`. Context contains the selected repository
identity, checkout path, branch and SHA, selected issue identifiers and native
edges, complete discovery digest, and proposed local enrollment directory.
It carries no issue bodies, credentials, verifier keys or execution requests.

Return one standard signed `profile` envelope from the trusted operator
principal. Its payload must identify the exact repository, issue and feature
checkout. Return the same envelope for the same unchanged selection within
its lifetime so a plan can be approved and rechecked. The operator service
supplies current revocation data and references to protected bootstrap feeds.
Separate project authorities supply signed policy, independent issue
assessment and repository-scoped installation credentials under the existing
schemas. A signed check backend also needs a current project-check bootstrap
for the selected repository, exact source ref and SHA, task and prescribed
phase. It may report incomplete coverage and zero results. The bootstrap
demonstrates authenticated configuration and is never a check pass. The
accepted native post-PR evidence backend uses its existing conditions.

The project service may connect the accepted ongoing decision socket for later
exact requests. Guided setup binds the signed policy and assessment bootstrap
actually consumed by accepted preview. Keep material in protected files
outside the product checkout and M9-A installation. The interactive client
handles selection, review and approval. The independently trusted services
supply and sign the envelopes. Missing issuers or providers produce actionable
`BLOCKED` or `UNKNOWN` results.

## Apply or reconnect

```bash
adp enroll apply --repo /owned/project --remote origin --issue 7 \
  --directory /owned/setup/project \
  --operator-trust /owned/authority/trust.json \
  --operator-socket /owned/authority/enrollment.sock \
  --approve APPROVAL_FROM_PLAN --authorize-memory-write

adp enroll status --repo /owned/project --remote origin \
  --directory /owned/setup/project --operator-trust /owned/authority/trust.json
```

Review the paths, finite delegation, prescribed checks, and selected source
in the plan before approving. Apply recomputes and compares its digest before
creating the protected enrollment directory. The directory stores one original
intent and the matching protected profile. The accepted setup writes local
coordination memory, private enrollment and revocation records, and the existing
M1–M7 checkpoints. It requires the same observed discovery and independent
provider bindings before those writes. Apply checks the approved control paths
and pins the Git transport to the selected local bare remote. Guided ownership
claim is limited to a pristine unowned checkpoint under the M1 lock.

Rerun with the original approved digest if enrollment was interrupted. The
retained proposal can be used without the proposal socket. If the retained
intent, independently signed inputs, source, trust or ownership differ, inspect
the blocker before proceeding. Use the [accepted memory recovery](../MEMORY_CLI.md)
for interrupted M1 checkpoints. Completed enrollment is reused without
claiming released ownership. The current signed window still applies.
If an incomplete enrollment already has an unowned memory checkpoint, confirm
its provenance and use the separately authorized M1 ownership procedure before
resuming setup.
Use `reconnect`, `doctor`, or `preview` with the same selectors. Read-only
commands also accept `--operator-profile` in place of `--directory` for an
existing installed profile. Reconnect verifies locally retained enrollment and
the canonical remote identity with the accepted scoped read credential. Guided
reconnection also checks the original local coordination destination, including
when selected through `--operator-profile`. Preserve `guided-enrollment.json`
in the private state directory alongside the original enrollment intent.

All command results have version `schema_version: 1`, `command`, `mode`,
`status`, optional structured `facts`, `plan`, `approval` and `result`
values, and arrays of `questions` and `blockers`. A question has an ID, type,
CLI argument and action. A blocker has a code and action. Successful
observations, proposed plans and established enrollment return exit code 0.
A missing, blocked, pending or unknown outcome returns 4. The
`execution_authority` field stays `UNKNOWN` throughout this protocol.
The separate accepted execution entry point requires current explicit
delegation and M1–M7 gates.

Run focused checks with
`python -m unittest discover -s tests_m9 -p test_enrollment.py -v`.
