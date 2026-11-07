# Implementation roadmap

**Status:** approved architecture direction, proposed implementation sequence. Issue links will be maintained in GitHub; no phase below is complete merely because its design exists.

The first supported provider is GitHub, with Python 3.11+ and a portable Codex skill. The separate engine must work on two synthetic repositories with different rules. ESO_control is a reference use case, not a dependency or test target for initial development.

## Milestones

### M0 — repository foundation and verified skill scaffold

Deliver a portable plugin manifest, a focused planning-only Codex skill, English architecture/guard/policy/discovery contracts, contribution and security rules, and an executable scaffold validation with CI. **Does not include autonomous execution.**

### M1 — portable memory engine and initialization

Extract the general single-writer state model, config storage, safe `init`, ownership claim/handoff, atomic inbox delivery, remote synchronization, rejection of stale results, and `doctor` checks. No ESO-specific paths, hard-coded Git remote, project Issue numbers or branch names.

**Gate:** synthetic two-clone conflict, crash/handoff, malformed schema, owner fencing and portability tests.

### M2 — executable Progress Guard and review contracts

Implement persistent guard counters, factual progress scoring, finite forensic response, classification taxonomy, safe retry gates and exact-revision review bindings. Test full-inventory campaigns that continue across ordinary FAIL while preserving NOTRUN and quarantine accounting.

**Gate:** synthetic spiral scenarios and all safety-negative cases must pass.

### M3 — GitHub discovery and external policy providers

Implement read-only `discover`/`plan`, pagination and dependency reconciliation, prompt-injection-resistant issue intake and an external Git workflow interface with safe-deny behavior.

**Gate:** two conflicting synthetic Git policy profiles; no write during discovery.

### M4 — skill-facing Conductor and bounded execution

Wire `run`, `status`, `resume`, `handoff`, independent reviewer delegation and one product-summary-per-iteration publishing. Execute only tasks admitted by policy, within explicit resource and operator limits.

**Gate:** end-to-end synthetic multi-worker task track, restart and recovered publication without duplicates.

### M5 — independent portability and release qualification

Demonstrate a clean install in a second unrelated repository, two-machine simulated handoff, history integrity and acceptance matrix. Final release decisions remain operator-authorized.

**Gate:** independent exact-revision security/code review, full intended-scope tests and an explicit release go/no-go.

## Development principles

- Work progresses through separately reviewable small PRs; do not build a monolithic engine before validating state and guard contracts.
- Avoid elaborate cryptographic manifests or redundant storage checks that do not protect a real boundary.
- Keep the existing project-specific ADP v2 operational; never force-migrate active work as part of extracting code.
- Maintain one truthful public product update per completed product iteration, not an internal status-receipt stream.
- Every feature must have a finite acceptance story and negative tests. Missing evidence is UNKNOWN, not PASS.
