# Implementation roadmap

**Status:** M0 scaffold, M1 portable memory and M2 Progress Guard are accepted. M3 has an implementation candidate; M4–M6 remain planned milestones. The first target is GitHub with Python 3.11+ and a portable Codex skill, validated against unrelated synthetic repositories.

## Milestones

### M0 — Architecture and skill scaffold (complete)

Deliver portable `plugin.json`, focused read-only `SKILL.md`, English architecture/guard/policy/discovery contracts, contributor/security rules, executable scaffold validation and CI.

**Evidence:** [scaffold commit](https://github.com/oduwan/adp_codex/commit/6d404f2d37061a0b33e6d168868cc48141e4b823) and its successful GitHub Actions run. No autonomous execution is included.

### M1 — Portable memory, initialization and doctor (accepted, [#1](https://github.com/oduwan/adp_codex/issues/1))

Implement configurable single-writer working memory, `init`, `doctor`, claiming and handoff, atomic inbox delivery, stale-result refusal and restart recovery. Do not hard-code remotes, branch conventions or repository identity.

**Gate:** synthetic two-clone conflict, safe takeover, malformed-schema and portable handoff tests. Accepted through [PR #7](https://github.com/oduwan/adp_codex/pull/7), merged at `2064fdf83c540e761ef55f3bc394fe625cd20df4`.

### M2 — Executable Progress Guard (accepted, [#2](https://github.com/oduwan/adp_codex/issues/2))

Implement persistent anti-loop counters, progress evidence, independent forensic reassessment, bounded exits, exact-revision approval guards and non-fail-fast diagnostic campaign semantics.

**Gate:** synthetic diagnostic-spiral and false-PASS adversarial tests. Accepted through [PR #8](https://github.com/oduwan/adp_codex/pull/8), merged at `7412af056967e161db54f6111a5b02ab8a8dcf88`.

### M3 — External project policy provider ([#3](https://github.com/oduwan/adp_codex/issues/3))

Extract branch, commit, validation, PR, merge and release rules from project-owned policies. ADP provides coordination, not a competing Git workflow.

**Gate:** two incompatible synthetic policy profiles; unknown authority is denied, never invented.

The Issue #3 candidate provides [typed policy decisions](POLICY_API.md) and
read-only Git/mock adapters. Execution and live forge discovery remain separate.

### M4 — GitHub issue discovery and planning ([#4](https://github.com/oduwan/adp_codex/issues/4))

Implement read-only `discover`, `plan` and refresh: issue and PR ingestion, native and confirmed dependency edges, cycles, readiness classification and deterministic reconciliation.

**Gate:** pagination, permissions, stale-HEAD, dependency-cycle and prompt-injection fixtures; zero discovery writes.

### M5 — Conductor execution and product reporting ([#5](https://github.com/oduwan/adp_codex/issues/5))

Wire policy-gated `run`, `status`, `resume`, `handoff`, bounded parallel subagents, independent exact-revision review and idempotent one-summary-per-product-iteration publication.

**Gate:** synthetic multi-worker track, restart, reviewer rejection and recovered publication without duplicates.

### M6 — Cross-repository portability and release qualification ([#6](https://github.com/oduwan/adp_codex/issues/6))

Demonstrate clean installation on unrelated repositories, cross-clone handoff, external policy differences, execution authorization boundaries and honest acceptance accounting. Keep real product repos unchanged during tests.

**Gate:** all intended tests, independent exact-revision security/code review, documented limits and explicit operator release authorization. Select license before advertising an open-source release.

## Development rules

- Every implementation milestone has a bounded scope and negative tests.
- Review the final exact revision independently. Re-review after changes.
- Preserve the existing target project's working state during adaptation.
- No raw diagnostic log streams or test-infrastructure work in product Issues/PR status comments.
- Never count `SKIP`, `NOTRUN`, `ERROR`, `TEST_CORRUPTED` or `UNCLASSIFIED` as an accepted PASS.
- No automatic merges, deployment or release permissions without an explicit external policy.
