# Network runtime limits and operation costs

This is the operator-authorized resource-policy update to Draft PR #52, within
Issue #50. It grants no repository, recovery, Worker, merge or installation right.
Historical 45-second failures remain failures. Genuine M8 remains NOTRUN/HOLD.

## Static analysis before implementation

Examined revision: `e2693b114a4b40b06c688a2f548872c6df27a96a`.

| Definition at that revision | Consumers and propagation |
| --- | --- |
| `adp/network_git.py:156–173`: `bounded()` creates 45s; an unscoped request creates 20s; 128 request entries; transport receives at most 5s | GitHubCAS refs, Git Data upload, native CAS, M3 GitHub adapter; personal publication, PR/merge, reports and historical/native-track reads |
| `adp/personal_publication.py:267,446`: approved 45s/128 view and 45s M2 action | Publication preview, exact approval and durable reservation; these must change coherently for fresh proposals, never renew stored grants |
| `adp/personal_product.py:414,634`: 45s M2 actions | Product effects and post-PR CI observation; original consent/expiry and outstanding reservations remain authoritative |
| `adp/personal_network.py:105–113`: request deadline starts after authorization/probe, then repeats `min(5, remaining)` | gh credential lookup, personal/product/report HTTP children and supervisor |
| `adp/network_http_child.py:22,41`; `forge_http_child.py:19`; `ticket_http_child.py:18`: 5s grammar ceiling | Signed/personal Git Data and forge/ticket child validation; credentials, route grammars and stop allowances are separate constraints |
| `adp/personal_product_http.py:66–76`: 5s caller subdeadline, min with outer deadline, copy-back count | Existing project-owned validation read adapter; the caller's smaller budget must remain binding |
| `adp/discovery_github.py:71`, `personal_github.py:28`, `execution_github.py:28`: 30s HTTP timeouts | GET-only discovery/enrollment and legacy forge transport |
| `adp/project_validation_github.py:36,118–120`: 30s ceiling, shortened by evidence deadline | Actual project check observations; caller EvidenceRequest budget and coverage requirements remain binding |

Existing configuration uses closed JSON objects through `adp.config.load_json()`;
`.adp.json` describes repository/memory identity, and protected operator profiles
describe authority. Invalid authority must continue to fail closed. Runtime
preferences reuse the JSON reader but are separate optional operator data, so
their required fallback cannot turn an invalid authority profile into authority.

The captured diagnostic at this revision proves that request 42 entered with
`-5.0856270971708` seconds left in its original 45-second scope. All 18 subsequent
original-ticket reads were refused before a response; native submit took
50.090996s and never reached ref CAS. The earlier 613.161s run's missing immediate
cause remains UNKNOWN. No incorrect nested deadline propagation is established
as the cause of this captured failure: native submit had its own fresh scope.

Measured native-submit Memory inspection cost was 20.968609s, including
17.786274s of native Git and 1.651382s of bundle validation. Those are nested
times, not additive. Fresh ownership/provenance checks are essential. Static
inspection identifies avoidable process duplication in
`personal_recovery.administration_snapshot():114–122`: adjacent HEAD/ref reads
can be one fresh native query for each of two roots (nine processes become
seven). Entry and closing full proofs and their later input snapshots must stay
independent. The failing fixture has no governance blobs to batch; governance
batching is deferred. The observed failure is a fixed-budget refusal during
legitimate validation/orchestration; the fraction attributable to avoidable
duplication is not established by that one capture.

Independent follow-up static review also established that `publish()` rebuilds
the same full proposal outside and inside the invocation lock. The approved
token already hashes the complete view and actual credential binding. The
implementation retains one complete fresh reconstruction **inside** that lock,
checks its exact token before saving, and checks separate plan-disabled assent
before durable publication intent/admission. The existing-intent branch always
checks its original approval under the lock. No independent Reviewer, later
live proof, M3 authorization or native CAS fence is removed. This eliminates
one whole redundant preflight; it introduces no observation/ALLOW cache.

## Configuration contract

Exactly three integer parameters are supported. Booleans and numeric strings or
floats are not integers for this contract.

| JSON key | Minimum | Default | Maximum |
| --- | ---: | ---: | ---: |
| `request_timeout_seconds` | 3 | 10 | 30 |
| `operation_timeout_seconds` | 40 | 150 | 300 |
| `request_limit` | 64 | 128 | 256 |

The optional file uses the existing bounded, duplicate-key rejecting JSON reader:

```json
{
  "request_timeout_seconds": 10,
  "operation_timeout_seconds": 150,
  "request_limit": 128
}
```

The single loading entry point is `load_runtime_limits()`. Selection order is an
explicit embedding path, then `ADP_RUNTIME_LIMITS_FILE`, then
`$XDG_CONFIG_HOME/adp-codex/runtime-limits.json` (otherwise the owning account's
`.config/adp-codex/runtime-limits.json`). This is optional operator data, not a
target-source or Issue-text authority feed. Use an owned protected regular file
outside product and memory roots. No CLI numeric overrides or additional
configurable limits are introduced. A client/outer-operation holds one immutable
snapshot; a new client/invocation reloads it. No process-global positive cache.

| Input | Effective result | Diagnostic |
| --- | --- | --- |
| Valid known integer values | Supplied values; omitted keys default | None for valid values |
| Missing file | All defaults | Missing-file event |
| Malformed/unreadable/unsafe/oversized file, wrong root, duplicate or unknown keys | All defaults | Underlying loading/structural error |
| Individual wrong type, null, boolean, malformed numeric string or out-of-range value | That parameter defaults; other valid parameters survive | Parameter, rejected value, reason, effective fallback |
| Unexpected loading exception | All defaults | Underlying loading failure |

Values are never clamped. Fallback is confined to configuration loading and
validation, not operation execution. Cancellation and unrelated product errors
still propagate. Detailed diagnostics remain private, outside portable memory,
Worker prompts and GitHub product reports.

The operator-approved default is now 150 seconds. A valid configured 120-second
value remains 120. Previously issued consent, grants, permits and absolute
deadlines keep their exact original caps; changing a default cannot renew them.
The failed 120-second capture at `2b0ecd6` remains historical failure evidence.
Neither the new default nor focused tests qualify complete publication under
150 seconds. That integration rerun needs separate operator release. See the
[static publication call graph](PUBLICATION_CALL_GRAPH.md) for freshness classes
and the two local snapshot reuses.

## Deadline and measurement semantics

The outermost public network operation owns one absolute monotonic deadline and
request counter. Nested scopes/services share that budget and may only tighten
it. Fresh consent records bind the three effective values. Legacy consent keeps
its historical 5s/45s/128 ceilings; stored M2 permits, expiry, evidence budgets and
revocation never grow. Configured minima do not apply to remaining time: a
remaining allowance below three seconds is passed through, never rounded up.

Project-evidence reads shorten one request on that same budget instead of
copying/restoring counters or profiles. Retained profiles bind before the first
resumed read, including observation-only recovery/status. An immutable selected
consent resource context carries only these ceilings around Reviewer/correction
work; it starts no clock/counter and grants no authority. Each actual native
phase starts/joins its network budget, while Worker execution keeps its original
independent reservation. Standalone forge inventories/observations/submissions
and multi-object uploads also establish one shared logical-operation scope.

The request deadline includes authorization, credential and supervised I/O work;
the existing bounded cancellation/stop-confirmation allowances remain unchanged.
The child imports only the central hard ceiling and uses the parent's already
bounded allowance. It never loads external configuration.

Cost records contain no routes, tokens, payloads or host identities. They record
operation wall time, attempted/transport request counts, request latencies,
configuration loading cost and named repeated-work spans. Nested span times must
not be summed. Supervised network-child time is distinguished from orchestration;
it is not a measurement of external project tests or Codex Worker execution.
`configuration_loading_seconds` is actual loading inside that operation;
`profile_initial_loading_seconds` separately records the client's initial load
and must not be charged repeatedly when that immutable client is reused.
Local validation is cooperatively checked at scopes/request boundaries; existing
Git and stop/reaping bounds are not replaced by a new global preemption policy.
The legacy urllib ports retain their socket-based blocking semantics and reject
late returns; they are not the M7 supervised whole-request process transport.
Baseline/optimized observations must use the same disposable data and budget;
historical single-sample failures are reported separately. Empirical median/p95/
maximum require their sample count and procedure, not an inferred speedup from
different limits. The default budget is not a performance target.

Body/header sizes, pagination/data inventories, M2 attempts/resources, Worker
and project-validation grants, approval lifetimes and supervisor cancellation
allowances remain independent existing contracts, not additional configurable
runtime parameters. CI fixtures declare deterministic resource defaults; their
directly affected old five-second assertions are updated to the approved model
while route, scope, stop, CAS and authority assertions remain intact.
