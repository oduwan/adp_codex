# Personal project enrollment

Issue #37 adds an explicit operator-managed backend for one personally owned
GitHub.com HTTPS repository and one original open issue. It needs the existing
`gh auth login`, supported Codex CLI login and an explicit Git author. It does
not require external trust providers, a daemon, an issuer, hand-written JSON or
a custom Python controller. Signed-provider enrollment remains separate.

Use the managed `adp` launcher. Both `adp personal ACTION` and
`adp codex ACTION --personal` call the same protocol. Start read-only:

```sh
adp codex inspect --personal --repo /absolute/project --remote origin
adp codex plan --personal --repo /absolute/project --remote origin \
  --github-id OBSERVED_ID --issue 1 --path src \
  --feature-branch SELECTED_FEATURE --commit-message 'Selected project subject'
```

These are examples of selected operands, not repository-wide policy defaults.
Read the actual original issue, AGENTS/config/governance and workflows before
choosing paths, commit text and existing project `--check NAME` values. The
read-only plan includes numeric and opaque identities, native blockers, exact
branch/SHA, proposed private paths, uncertainty, actual known check origins,
all local operations, role bounds and expiry. An omitted directory proposes
an owned path below `~/.local/state/adp-personal`. No setup writes, product
branches or workers occur during inspect/plan/preview/status.

Review and confirm the complete plan and its `approval`. Only then repeat the
same plan arguments with `apply --approve APPROVAL --authorize-memory-write`.
The approval encodes the original finite window and plan digest, so changed
operands, original ticket, source or evidence are rejected. Apply automatically
creates owned mode-0700 local coordination checkout, bare coordination remote
and private evidence, initializes actual M1, claims only pristine ownership and
performs the accepted guard/execution migration. It creates no product branch
and launches no model. A small private pointer in the original Git common
directory prevents silently renewing the same issue in another directory.

Keep the returned directory. Use `status`, `doctor` or `reconnect` with it.
These commands preserve counters and ownership. `doctor --check-runtime` on
the `personal` entry point additionally checks capabilities without a worker.
Setup writes require a valid window. Interrupted pristine setup can resume
with the original approval; foreign, released or nonpristine M1 state cannot
be adopted. Missing private history requires reconciliation, never reset.

For execution, obtain a distinct invocation proposal:

```sh
adp personal preview --repo /absolute/project --remote origin --directory PRIVATE_DIRECTORY
adp personal run --repo /absolute/project --remote origin --directory PRIVATE_DIRECTORY \
  --reviewed PERSONAL_RUN_APPROVAL --authorize-execution
```

The second command requires a separate explicit operator confirmation after
seeing the invocation proposal. A setup approval cannot authorize a run.
`preview --for-operation resume` or `status --for-operation resume` proposes
the original window's resume; never create a new enrollment to replenish it.
`status --for-operation handoff` proposes safe owner release, including after
execution expiry; every process, assignment, action and guard reservation must
be reconciled first. Released ownership is not automatically reclaimed.

Consent also pins physical checkout, Git common/directory and `.git` entry
identities. Workers and local effects recheck these bindings. Local Git writes
use the explicit pinned Git directory and worktree, so a late `.git` redirect
cannot send the CAS to another repository. Unknown worktree submission is not
retried: only its complete existing bound result can be observed. Coordinator
permits and result transitions use write-ahead private intents so interrupted
allocation/accounting recovers the same canonical M2 token and observation.
A missing check delivery remains UNKNOWN and does not cause another observation.

The foreground coordinator runs one task iteration with concurrency one. The
approved upper bounds are one original-scope Reviewer, two Developers, two
staged-scope Reviewers and two exact-SHA code Reviewers, each at most 300 seconds;
the original window defaults to 1800 seconds and cannot exceed 3600. M2's
unchanged limits may stop earlier. These caps do not authorize a second issue,
unbounded retries or background work. M2 forensic/terminal dispositions stop
this minimal backend for existing guard/operator recovery; it does not invent
a replacement forensic campaign. The plan retains the existing two-forensic
upper bound but this backend never automatically dispatches those contexts.

The first genuine read-only Codex Reviewer must independently judge the complete
original scope, native dependencies, chosen local operations and all committed
governance. Only then can an approved isolated feature branch/worktree be
prepared. Native prerequisites are never satisfied by issue closure alone;
this minimal path blocks any such issue pending independent accepted dependency
evidence. Developer and every Reviewer use distinct actual supervised runtime
contexts. The Developer cannot self-approve, stage or commit. An independent
staged-diff judgment precedes commit through actual M3 and GitExecutionPort
CAS. A fresh exact-committed-SHA Reviewer supplies code approval. Requests,
results, context IDs and bound stop receipts remain private and generation
fenced. Unknown delivery or stop evidence never permits replacement dispatch.

The original setup/run delegation produces **local drafts only**. M10-A adds a
separate [feature publication approval](PERSONAL_PUBLICATION.md), requiring its
explicit project-policy assent and personal administrative-quiescence warrant;
setup/run consent never grants that right. The separate
[M10-B product path](PERSONAL_PRODUCT.md) adds its own PR/merge approvals and
project-evidence sequence. Original setup/run consent grants none of those
external rights. No issue edit, product comment, release or deployment port is
wired by this slice. Explicitly absent rules remain optional; selected
local branch/commit choices are not invented project conventions. Present
governance applies. The original-scope and staged-scope reviews must reject
unsupported requirements, including mandatory precommit checks that the native
committed-SHA evidence port cannot supply. Personal mode supports the accepted
bounded M3 branch slug/template and commit operand formats; unsupported policy
expressions remain blocked rather than rewriting project rules.

Required check names are retained even if origins are unavailable. Actual
known native checks are observed through #21 ProjectValidation at the exact
new commit, without running tests or managing project infrastructure. Existing
workflow/check context discovery does not prescribe extra tests. The operator
can select existing required names and explicitly accept native job records as
attempt evidence with `--accept-native-job-records`; this does not invent test
counts. FAIL, ERROR, UNKNOWN, partial, pending and missing evidence retain their
status. A local unpublished SHA often has no native CI result; it is not a PASS.
Unknown protection blocks external writes, which are not delegated here anyway.
No checks are fabricated when requirements are verified absent.

`LOCAL_DRAFT_CODE_REVIEWED` means a real exact-SHA **code** verdict, with actual
check dispositions shown separately. It always remains `NOT_ACCEPTED`; the M1
product acceptance criterion is unresolved and no product COMPLETE/DONE or
dependency acceptance is manufactured. Ordinary observed failures and code
change requests become feedback within the original role/time/M2 budgets.
Resume reobserves the original ticket and exact source. It cannot reuse a code
review after a source change or renew the finite window.

Credentials are obtained from the named environment variable or fixed
`gh auth token --hostname github.com` outside chat. They enter only fixed-origin
read transports, never command arguments, prompts, portable memory or reports.
Private local receipts authenticate actual operator consent/runtime/transport
observations; they are not signatures or external independent providers.
Keep this state outside every product checkout, Git admin and installed engine.

Qualification uses focused synthetic repositories and mocked runtime methods
explicitly labeled as offline tests. Genuine Developer → checks → Reviewer
runtime qualification and any pilot operation require a later separately
authorized M8 gate. No installation, pilot enrollment or pilot execution is
part of implementing this backend.
