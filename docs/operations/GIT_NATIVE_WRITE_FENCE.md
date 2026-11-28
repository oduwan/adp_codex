# D3: current publication admission replaces per-object history replay

> **Issue63 trusted-worktree amendment:** The [explicit stage matrix](TRUSTED_WORKTREE_STAGES.md)
> supersedes prior per-helper/per-HTTP local source, index, administration and
> old-history replay requirements below. The actual cold proof and immutable
> handoff remain; current canonical/external authority, deadlines, revocation,
> one-use claims, CAS and uncertainty recovery remain fresh. The historical
> descriptions/evidence below are retained, not represented as current controls.
> This does not qualify all of #57 or authorize #58, installation or live effects.

> **D4 operator revision (Issue #57):** The historical D1/D2/D3 account
> below is retained for evidence. Its repeated historical-byte/closed-private-
> inventory replay, independent closing historical reconstruction, finite-U
> request predictor and net-negative-LOC intermediate STOP are superseded by
> the approved [personal trust boundary](../ARCHITECTURE.md#personal-historical-trust-boundary--d4-operator-revision).
> Full entry/restart authentication remains; mutable current authorization and
> original budgets remain live. N+1 is a negative lower bound only. This does
> not release #58, change old grants or authorize any live product effect.


Issue #56 implements the independently approved
[D1 contract](GIT_NATIVE_EVIDENCE_CONTRACT.md) over the reviewed
[D2 substrate](GIT_NATIVE_BASIS.md). This is engineering qualification, not a
release, installation, live authorization or #58 integration qualification.

## Replaced call path

The qualified accounting path previously executed, for every object POST/CAS:

```text
PersonalGitHubTransport.request → write_authorized → live(review=False)
  → Coordinator.live → Episode._active_view → _archived_view
  → Guard._snapshot → ExecutionJournal.inspect
```

It now executes:

```text
PersonalGitHubTransport.request → write_authorized
  → actual private/current source/index/engine/host/credential inputs
  → actual bounded historical objects and opening/closing storage contexts
  → ONE late actual Memory.inspect → same_observation
  → pure Guard._get/_active/_context + current SUBMITTED/claim
  → actual permit interval, revocation, consent, own request marker and Budget
```

No historical semantic verifier, live callback, Guard decision/snapshot or journal
inspection is called inside that qualified write fence. Ordinary/signed callers
retain their existing default paths. D4 removes obsolete accounting staging and
superseded APIs; no legacy accounting writer is restored.

## Invocation-local operands

The existing independent closing read proof exposes the actual H3 witnesses,
current canonical subject and actual input seals already consumed. After the
unchanged pre-upload validation callbacks, direct input equality and a late
actual canonical observation bind the post-SUBMITTED subject. The value belongs
only to the current publisher, service, transport, target, process/thread and
Budget. It is cleared on every submit return/error/cancellation. It is never
serialized, inherited by a restart or interpreted as ALLOW.

Post-upload validation must equal that existing subject and inputs. It cannot
adopt an unexpected newer checkpoint. A changed unrelated guard, assignment,
inbox, owner, source, ref, index flag, private receipt or credential refuses.
Working-file and index observations use the existing bounded source seal plus
actual index flags; unsupported hidden flags are UNKNOWN. The original runtime
host fingerprint calculation is shared without changing its format, and actual
host identity is observed afresh instead of constructing another runtime or
trusting a retained host field.

The request already owns its exclusive IN_FLIGHT_OR_UNKNOWN marker when the
transport invokes admission. The callback verifies that exact marker, not its
absence. The existing pre-start stop check and confirmed-stop cleanup remain.
Request deadline and cancellation continue through the existing transport; the
callback cannot refund requests, create another Budget or extend original caps.
Actual UTC must remain within both the original M2 permit start/deadline and
publication consent interval, including at the final gate.

## Mandatory independent boundaries retained

Full operation entry/reentry and independent closing raw proofs remain. The
native port still executes all three M3 authorizations, both full dispatch
validations, fresh writable ref/rules/owner checks before upload and CAS, exact
expected-old updateRefs CAS, actual observation and existing settlement. Durable
PREPARED/claim/SUBMITTED precede mutation. Lost responses and changed state remain
observation-only; a consumed dispatch is never reminted.

## Finite request-count admission

The actual provider snapshot is bound to Plan.snapshot_digest. Only the current
adapter receives its immutable expected Ref tuple as a negative read envelope;
the service does not cache refs or permissions. Every continuing page must add
new expected refs, and the complete fresh tuple must match. Thus the remaining
ref pass has bound F=max(1,heads)+max(1,tags), including refused pages.

The original-ticket reobserver rejects an unapproved URL before fetching it and
compares every actual body/Link digest. Existing M4 pagination and independent
root reads remain; the bound is P distinct approved paths plus K repeated roots.
Rule-mode changes refuse before fallback reads only on the qualified path;
ordinary v1 and signed default observations are unchanged.

Immediately after the second native authorization, the existing completed object
tuple and SAME Budget enter a side-effect-free classifier:

```text
R = maximum_calls - calls; N = object count
L = N + 1  # object POSTs and CAS
U = M + F + (P+K) + sum(branch costs) + remote + inspect + settle_remote + 2
L > R                    → INSUFFICIENT, before any object POST
unknown U or N + U > R   → UNKNOWN, before any object POST
otherwise               → COUNT_FEASIBLE, never authority or wall-time proof
```

Normal costs are branch2, remote6, inspect3, settlement6. The verified
plan-disabled profile uses worst-case branch5, remote11, inspect8, settlement11,
even if the earlier feature was absent. No additional configurable limit exists.

M=0 is supported only for the installed, closed first-accounting-issue route:
exact original identity/first index/parent, a single equality-bound shared link,
no native prerequisites, the existing validated empty prerequisite result and no
Product/republication/REPORT or custom authority/runtime/controller overlay.
Other required HTTP classes remain UNKNOWN rather than assuming zero. Closure
known-commit reads and the first two authorizations have already been charged.

## Evidence scope

The [focused inventory](GIT_NATIVE_FENCE_TEST_INVENTORY.json) adds only callback,
read-envelope and native-port sequencing controls required by #56. Actual native
port tests retain real disposable Git objects/ref CAS and durable one-use claims;
transport/worker evidence is explicitly synthetic, not genuine execution.

The separately retained bounded cost probe compares three historical/canonical
admission components per source with identical declared current-product-source/
review seams. Real historical, Git-object, Memory, Guard, claim and stop checks
remain in the measured subgraph. Setup is excluded. It makes zero HTTP/transport,
upload or CAS calls and cannot qualify full publication or its 150-second fit.
Returned 10-second request deadlines and the single 150-second operation Budget
must both be enforced; a failed source part stops without retry. Raw samples,
source/import/procedure hashes and nested inclusive/exclusive spans stay private.
Three-sample timings are observations, not causal speedup or tail guarantees.

Historical failures, interim static findings and original budgets are preserved.
Full CI/integration remains separately unreleased #58; the old qualifier's
descendant-stop status remains UNKNOWN. No pilot, archival application,
installation, merge, deployment or release is authorized.
