# Accepted M5 Conductor execution

M1–M5 are accepted through PRs #7–#11; M5 merged at
`1eb00b3e94151a16a621aab20e71943b3ea2c8a1`. The packaged planning skill remains read-only;
invoking it supplies no execution rights. M6 qualification is tracked separately in [the report](qualification/M6_REPORT.md);
public release remains NOT_AUTHORIZED.

## Entry points and authority

`Conductor.run(admissions, maximum_parallel=..., rounds=1, authorized=True)`,
`status()`, `resume(...)` and `handoff(authorized=True)` are synchronous, finite
invocations. There is no service, scheduler or background daemon. One invocation
lock and the accepted M1 checkpoint queue serialize canonical writes. Parallelism
is explicitly bounded to at most four isolated product workspaces, eight admitted
tasks and four cycles per invocation. A repeated invocation cannot reset M2.

The CLI exposes `run`, `status --controller`, `resume`, `handoff --controller` and
`execution-upgrade`. `run` and `resume` require an explicit `--controller FILE`
and `--authorize-execution`; `handoff --controller` requires the same authorization.
Without a controller, M1 `status` remains observational and labels runtime liveness
UNKNOWN. Read-only M4 `discover`, `plan` and `refresh` retain their accepted behavior.

An explicitly selected operator Python controller, outside product/memory roots,
exports `build(config) -> execution_cli.Controller`. It assembles actual `Memory`,
`ProgressGuard`, `M4ReadinessService`, `Conductor`, typed `Admission` objects,
projects, runtime and external authority ports. This is trusted installed operator
code, never code loaded from an issue, a discovered policy document or a target
repository. There is deliberately no implicit permissive controller.

```text
adp execution-upgrade --repo ... --memory-branch ... --storage ... --authorize-memory-write
adp run --repo ... --memory-branch ... --storage ... --controller /operator/controller.py --authorize-execution
adp status --repo ... --memory-branch ... --storage ... --controller /operator/controller.py
adp resume --repo ... --memory-branch ... --storage ... --controller /operator/controller.py --authorize-execution
adp handoff --repo ... --memory-branch ... --storage ... --controller /operator/controller.py --authorize-execution
```

`Controller.maximum_parallel` is the operator ceiling. `--test-runtime` explicitly
permits synthetic CLI qualification; a normal CLI execution requires the real
`CodexExecRuntime`. Unsupported capabilities return `UNSUPPORTED_RUNTIME`/exit 7.
A stopped or uncertain execution is not success. No command automatically merges,
releases, deploys, initializes memory, claims ownership or approves a migration.

## Admission and execution sequence

1. Current complete M4 snapshots and independently authenticated READY assessment
   bind the opaque issue identity, scope and acceptance to the admitted task.
   Duplicate issue identities with different task aliases are refused. Issue text
   cannot authorize execution; changed scope or missing metadata blocks a refresh.
2. Explicit `ExecutionAuthority` grants exact run/admission/dispatch/validation/
   effect subjects. It must independently authenticate operator decisions and
   actual independent reviewer receipts. Credentials, labels and exit zero never
   implement this authority. Workers never receive the authority object.
3. An actual M1 global assignment and generation, actual M2 reservation and exact
   request digest are durable before dispatch. Every Git/forge effect separately
   requires final M3 `Decision(ALLOW)` and exact operation authority.
4. Developer, Reviewer and Forensic use fresh runtime contexts. Developer gets
   only the admitted contract/paths; Reviewer sees the committed exact source,
   not Developer chat. Actual context reuse is rejected. A Developer cannot
   approve. Reviews and checks must match the current SHA; source changes return
   to development/review. M2 authors cannot approve their own work.
5. The independent Reviewer verdict and complete original validation accounting
   establish actual M2 progress. Missing criteria remain unresolved. Every check
   retains its denominator, all seven outcome counts and quarantine count.
   Non-PASS outcomes never become PASS from an exit code. Validation campaigns
   preserve later inventory after earlier failures/timeouts.
6. Policy-gated push/PR/report follows exact review. Gated pushes and ready PRs
   receive freshly bound checks/reviews too. No internal iteration creates forge
   effects. A product iteration produces at most one stable product summary.

The Conductor requires the accepted actual M4 planner and M1/M2 implementations;
`ReservedSafety` exposes an existing validated M2 token to M3 suboperations without
allocating another attempt, changing counters or relaxing thresholds. Forensic
inspection has its own current exact-context request and independent result.
Reviewed time, sample and payload bounds constrain recovery. Runtime elapsed time,
JSON event count and output bytes are included in guard observations. Repeated
failed bounded proofs reach the accepted operator stop, never an automatic reset.

## Supported Codex runtime

The adapter uses documented noninteractive `codex exec --json --output-schema`,
with `--ephemeral`, `--ignore-user-config` and separate processes/thread IDs.
Developer uses `workspace-write`; Reviewer/Forensic use `read-only`. Approval is
`never`, direct worker network is disabled, and broad temporary-directory write
roots are excluded. No dangerous sandbox bypass, model override, private host
protocol or shared conversation implements delegation.

The CLI, model-authentication installation, OS sandbox and explicit operator
extensions are trusted. The CLI frontend receives a minimal environment containing
basic process settings and required model authentication; Git/forge/ADP/cloud/SSH
mutation credentials and Git execution overrides are removed. Worker shell commands
use explicit core inheritance and secret-variable exclusions. Filesystem access to
the trusted Codex authentication/config installation remains an OS/CLI boundary;
these environment filters do not certify an arbitrary host's filesystem isolation.
Capability flags alone do not prove an authenticated model execution;
a launch failure is UNSUPPORTED_RUNTIME. Supported operation currently requires
Linux/POSIX, `/proc`, child-subreaper support and local durable runtime receipts. Receipts
live outside worker roots. Worker prompts are at most 32 KiB, output at most 1 MiB,
and execution at most 300 seconds, further limited by the actual M2 deadline and
forensic plan. A bounded per-request Linux child-subreaper supervises the unchanged
documented CLI invocation. It kills and reaps all descendants, including detached
`setsid`/double-fork children, before recording a confirmed stop. A missing bound
supervisor stop receipt remains UNKNOWN; a vanished process group is no proof.
Runtime host identity includes the PID namespace. Install trusted ADP code outside
product workspaces so workers cannot replace their own supervisor implementation.
A lost launch identity, unavailable host or missing terminal receipt remains
UNKNOWN and is never silently redispatched. Unknown cancellation refuses handoff.

Bounded source/admin seals detect changes to non-admitted files, including ignored
files, Git index/config/refs and read-only review source. The supported OS sandbox
is the enforcement boundary; post-execution seals are additional detection, not a
substitute for containment. Workspaces are limited to 4096 inspected files and
32 MiB outside admitted paths. Executable Git clean/smudge filters are unsupported.

See [Codex noninteractive mode](https://developers.openai.com/codex/noninteractive)
and [Codex security](https://developers.openai.com/codex/security).

## External effect and validation ports

`GitExecutionPort` implements real stage, commit, branch and push effects. The
entire payload, source/target refs, revision and expected remote SHA must match
the authorized M3 plan. It disables hooks through the accepted Git wrapper,
uses `commit-tree` and exact `update-ref` CAS, and never invokes force/lease.
The supplied push backend only accepts explicitly allowlisted local bare remotes:
immutable objects transfer before exact old-SHA CAS. Network push fails with
`UNSUPPORTED_ATOMIC_REF`; supporting it requires a separately qualified exact-CAS
port. There is no fallback to an unchecked normal push.

`GitHubForgeBackend` is separate from M4 GET-only discovery. An explicit mutation
transport supports only PR creation and product comments on the pinned GitHub
repository ID. An exact execution receipt is mandatory; a token alone is useless.
Bounded complete pagination verifies unique stable markers, exact body and PR
SHA/ref/repository/draft details. Permissions, malformed data and partial inventory
remain UNKNOWN. The qualification suite uses synthetic HTTP only: no live target
GitHub writes are authorized or performed.

Every external action is durably PREPARED/SUBMITTED before submission. Recovery
observes actual index/ref/commit or forge marker before deciding anything. Local
forge fixtures use a durable atomic key. GitHub supplies no atomic create-if-absent
comment key: after an uncertain submission, absence is UNKNOWN, never permission
to POST again. A found exact result reconciles a lost response without a duplicate.
Completed-task resume also reobserves source and external results, so accepted
historical evidence cannot conceal a changed current PR HEAD.

`SubprocessValidation` accepts registered argv and strict JSON outcome receipts;
commands never come from issue text. It strips inherited forge/ADP credentials,
limits IO/time, supervises/reaps detached validation descendants too, and continues
the original matrix. Host subprocesses are **only**
allowed with explicit `trusted_disposable=True` for owned synthetic projects.
Production use must explicitly supply an independently qualified sandbox prefix
or validation port enforcing read-only filesystem and denied network. Without
one, it fails `UNSUPPORTED_VALIDATION_RUNTIME`. An argv prefix is trusted operator
configuration; ADP cannot certify an arbitrary extension or its isolation.
Validation is durably RUNNING before launching commands. Missing supervisor stop
evidence is an execution-liveness hazard, not an ordinary failed check: later
inventory stays NOTRUN, guard containment stops, and run/resume report UNKNOWN
with unconfirmed validation references. Handoff and blind validation retry are
refused. A crash between launch and confirmed receipt requires explicit operator
reconciliation; neither a failed check nor an expired supervisor proves a stop.

## Durability and migration

State v3 is an explicit extension, not a reinterpretation of accepted M1/M2 data.
First perform the accepted owner-authorized v1→v2 `guard-upgrade`, then opt into
v2→v3 `execution-upgrade`. Both are idempotent; no read path upgrades. V3 retains
all v2 fields and unchanged M1 task files/M2 guard records, adding only closed
`execution` schema version 1. V3-capable readers replay v1/v2/v3 checkpoints;
older binaries refuse v3. Upgrade every writer before migration. No downgrade,
history rewrite, reset of criteria, owner, counters or accepted results exists.

The bounded extension stores at most eight tasks, eight jobs per task, 32 external
actions and eight product publications under M1's existing 64 KiB state bound.
Exhaustion fails closed and requires operator disposition. Jobs bind global M1
assignment IDs, generation, exact SHA/ref, request/context/host, actual resources,
validation receipts and M2 permits. Actions/publications have referential integrity.
Immutable worker deliveries still use M1 inbox acceptance, not direct worker writes.

Pre-dispatch assignment crashes are explicitly accounted UNKNOWN without inventing
external execution or replacing an active token. Durable validation receipts and
criterion reservations recover the same observation after a crash. Cancellation
or uncertain effects never imply completion. Handoff requires observed stopped
workers, an empty inbox, reconciled effects and clean source already available at
the remote SHA. It delegates ownership generation changes to M1. Accepted history
survives cross-clone handoff; a changed generation invalidates unfinished approvals.
An unfinished old-generation job requiring new approval remains blocked for explicit
reconciliation rather than reusing an approval or resetting M2 seen facts.

## Qualification and limitations

Run the complete suite on Python 3.11 and 3.12:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/validate_scaffold.py
```

Real runtime qualification is deliberately opt-in, outside unattended CI:

```bash
python scripts/qualify_codex_runtime.py --authorize-disposable-execution --keep-artifacts --evidence /tmp/adp-real-proof.json
```

This provisions actual disposable Git repos, real M1–M4, explicit synthetic project
policy/operator authority, a real Codex Developer then independent Reviewer,
actual source commit/checks and an idempotent local forge. It records CLI version,
ADP source HEAD, genuine thread IDs, product SHA and compact audit evidence outside
history. `--keep-artifacts` retains the private disposable Git/memory/runtime
receipts for independent audit; omit it to delete the disposable fixture on exit.
Fixture-runtime unit tests are explicitly synthetic and never substituted
for this proof. Raw runtime records/logs, tokens and local memory are not committed.

Strict production network-CAS, arbitrary validation sandbox qualification, public
release execution and unattended scheduling remain outside the supplied backend. No
ongoing work is promised after invocation exit; unobserved process state is reported
explicitly rather than claiming a background worker or successful cancellation.

## M6 privacy qualification correction

Recognizable credential/private-key shapes in fresh or cached worker results
(including nested forensic output) are refused before a portable checkpoint.
Raw responses stay in private runtime evidence; contamination blocks the work.
This is a bounded detector, not universal secret detection or a substitute for
trusted output classification. M1–M5 schemas and guard thresholds are unchanged.

## Explicit M7 GitHub CAS port

Issue #14 adds the typed `GitEffectPort` boundary and an opt-in
`GitHubGitExecutionPort`; the existing local-bare port retains its behavior.
See [network CAS](operations/NETWORK_CAS.md) for the narrow supported object
forms, authenticated HTTP policy adapter, explicit canonical target binding,
resource bounds and offline qualification. Actual GitHub writes remain NOTRUN
pending separately authorized M8; credentials never replace M3 authority.

A network action prepares a private one-use dispatch capability at the actual
canonical PREPARED transition, then checkpoints SUBMITTED before execution.
Reconstructed SUBMITTED actions cannot acquire another capability. Every HTTP
launch also has private write-ahead stop fencing. Unconfirmed transport liveness
is retained across restart, included in Conductor unconfirmed contexts and blocks
later HTTP and handoff, even if the target ref happens to equal the intended SHA.
No canonical schema, guard threshold, forced update or automatic retry is added.

## Opt-in M7 GitHub product transitions

Issue #16 adds an explicitly selected `Project.product_flow` using the actual
Conductor journal/owner/guard, accepted #22 preparation and #21 project evidence.
It supports one Draft PR, exact-SHA project gates, independently authenticated
review acceptance, explicit project-delegated native merge and one product report.
Legacy execution remains unchanged. See [GitHub product flow](operations/GITHUB_PRODUCT_FLOW.md)
for the explicit internal execution-v2 migration, unknown-count representation,
manual merge wait, native merge race envelope, durable recovery and NOTRUN limits.
The complete #22 autonomous lifecycle and live M8 qualification are not supplied.
