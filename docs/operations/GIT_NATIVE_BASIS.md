# Existing H3 historical basis — D2 engineering implementation

> **D4 operator revision (Issue #57):** The historical D1/D2/D3 account
> below is retained for evidence. Its repeated historical-byte/closed-private-
> inventory replay, independent closing historical reconstruction, finite-U
> request predictor and net-negative-LOC intermediate STOP are superseded by
> the approved [personal trust boundary](../ARCHITECTURE.md#personal-historical-trust-boundary--d4-operator-revision).
> Full entry/restart authentication remains; mutable current authorization and
> original budgets remain live. N+1 is a negative lower bound only. This does
> not release #58, change old grants or authorize any live product effect.


Issue #55 implements the independently approved
[D1 contract](GIT_NATIVE_EVIDENCE_CONTRACT.md). It is a stacked engineering
change over #54 and frozen PR #52, not installation, migration or runtime
qualification. No new Git object, retained ref, store or authority cache is
created. The original M1 H3 checkpoint is the historical identity.

## Read path and cutover

The protected activation is only a locator. The reader first checks the actual
H3/direct-H2/current fixed relation and lineage, both pinned Git storage contexts
and actual retained object bytes. Archive/master and descriptor/plan/grant hashes
must match that canonical relation before interpreting their recorded engine.
Full raw original host/request/stop/source and independent-role evidence remains
mandatory. Missing or corrupt evidence refuses; a Git OID alone grants nothing.

The existing `verify` primitive now returns explicit operation-local actual-byte
witnesses for both replicas. Its module-global `_WITNESSES` cache and unused
engine/host cache-key arguments are removed. These witnesses contain no ALLOW
result and are not written to disk. Actual storage interpretation and bytes are
checked on every verification; GC uses the unchanged canonical branch.

The closed non-issuing historical decoder authenticates original guard, result,
episode and guard/result reconciliation ae1 values. It uses their original
times, nonce and canonically bound engine. Current `grant`, recovery application,
preactivation installation and revocation retain their existing current-engine
and actual-time rules. The shared protected restoration parser has one set of
identity checks; historical decoding cannot issue a replacement grant.

| Existing state | Supported behavior in D2 |
| --- | --- |
| Ordinary personal or signed-provider | Existing formats and live rules unchanged |
| Unactivated accounting episode | Original current-engine installer/status only |
| Activated exact H3, raw evidence available | Historical authentication and fresh publish2 proposal within original limits |
| Accounting publication schema2/publish2 | H3, original engine and actual reader bound in existing view/token/action; full existing mutation fence retained |
| Old accounting publication intent | Preserve literal row/token; observation only or explicit disposition blocker; no replacement |
| Accounting Product/execution/REPORT/completion/NEXT/corrected publication | Explicit temporary `ACCOUNTING_WRITER_CUTOVER_PENDING` before new intent, reservation, dispatch or mutation; D4 replaces these gates with the approved existing-view cutover |
| Missing activation/H3/raw evidence, wrong lineage/engine, expired/revoked live consent | Refuse; no historical migration bootstrap, deadline renewal or new episode |

Historical reads preserve the existing recovery observation of an exact pending
checkpoint. Opening and closing health, journal, slots and full canonical subject
must match. This confers no live authority: ordinary live entry still requires
SYNCED ownership, and the existing lock-held checkpoint fence retains exact
purpose/owner/baseline/expiry checks.

## Focused qualification boundaries

The [new frozen inventory](GIT_NATIVE_BASIS_TEST_INVENTORY.json) covers actual
disposable local/bare Git objects, GC reachability, concurrent read stability,
corruption/absence, rewrite/promisor/alternate refusal, read interruption, literal
historical consent, changed reader/basis and staged writer refusal. The episode
case uses explicitly synthetic stopped receipts, never genuine Codex execution.
No secret/raw receipt is put in portable evidence or Git.

New-anchor creation, expected-absent ref CAS and write-before-anchor crash cases
are **not implemented or counted PASS**: D1 selected existing H3 instead. Their
approved substitutes are existing direct-parent/ancestry/lineage checks, both
replicas' reachability and actual object corruption/availability controls.

Original test IDs remain present. The former memo test now checks returned local
witnesses and actual opening/closing context on every read; it does not claim a
removed cache-hit path passed. Historical failures remain private and are reported
separately. The known bare-GitHubCAS fixture defect remains unrepaired until #57.

D2 adds explicit binding/compatibility checks while deleting the first global
cache. Net product-code reduction is a D4 measured gate, not a D2 claim. D3 alone
may replace the hot mutation fence. Full CI/integration is #58, separately
unreleased; the prior qualifier's descendant stop remains UNKNOWN.
