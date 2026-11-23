# Implementation roadmap

**Status:** M0 scaffold and M1–M5 are accepted. M6 qualification is under review; public release is NOT_AUTHORIZED. The first target is GitHub with Python 3.11+ and a portable Codex skill, validated against unrelated synthetic repositories.

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

### M3 — External project policy provider (accepted, [#3](https://github.com/oduwan/adp_codex/issues/3))

Extract branch, commit, validation, PR, merge and release rules from project-owned policies. ADP provides coordination, not a competing Git workflow.

**Gate:** two incompatible synthetic policy profiles; unknown authority is denied, never invented.

Accepted through [PR #9](https://github.com/oduwan/adp_codex/pull/9), merged at
`81a327b01b42b8ae24f592734e2d3c2c72200c75`. The provider supplies
[typed policy decisions](POLICY_API.md) and read-only Git/mock adapters.

### M4 — GitHub issue discovery and planning ([#4](https://github.com/oduwan/adp_codex/issues/4))

Implement read-only `discover`, `plan` and refresh: issue and PR ingestion, native and confirmed dependency edges, cycles, readiness classification and deterministic reconciliation.

**Gate:** pagination, permissions, stale-HEAD, dependency-cycle and prompt-injection fixtures; zero discovery writes.

Accepted through PR #10 at `ca44b1f319c1facb4154fd8015072ba3c5d0407d`.
The [M4 API](DISCOVERY_API.md) supplies GET-only GitHub discovery,
deterministic dependency proposals and evidence-preserving refresh previews.

### M5 — Conductor execution and product reporting ([#5](https://github.com/oduwan/adp_codex/issues/5))

Wire policy-gated `run`, `status`, `resume`, `handoff`, bounded parallel subagents, independent exact-revision review and idempotent one-summary-per-product-iteration publication.

**Gate:** synthetic multi-worker track, restart, reviewer rejection and recovered publication without duplicates.

Accepted through PR #11 at `1eb00b3e94151a16a621aab20e71943b3ea2c8a1`.
The [M5 API](CONDUCTOR_API.md) integrates accepted M1–M4 and a real
capability-checked Codex adapter. Independent exact-revision review and genuine runtime evidence qualified M5; no merge or deployment authority is supplied.

### M6 — Cross-repository portability and release qualification ([#6](https://github.com/oduwan/adp_codex/issues/6))

Demonstrate clean installation on unrelated repositories, cross-clone handoff, external policy differences, execution authorization boundaries and honest acceptance accounting. Keep real product repos unchanged during tests.

**Qualification gate:** the fixed Q01–Q12 matrix, full accepted regressions and new
M6 tests on Python 3.11/3.12, installation and independent security/design plus
exact-HEAD review. See [M6 report](qualification/M6_REPORT.md).

**Separate publication gate:** NOT_AUTHORIZED. License/distribution terms and
release/tag/listing approval require an explicit operator decision; technical
qualification, CI and review cannot supply it.

## Development rules

- Every implementation milestone has a bounded scope and negative tests.
- Review the final exact revision independently. Re-review after changes.
- Preserve the existing target project's working state during adaptation.
- No raw diagnostic log streams or test-infrastructure work in product Issues/PR status comments.
- Never count `SKIP`, `NOTRUN`, `ERROR`, `TEST_CORRUPTED` or `UNCLASSIFIED` as an accepted PASS.
- No automatic merges, deployment or release permissions without an explicit external policy.

## M7 accepted Issue #22 lifecycle

Accepted #14, #21, #16 and preparation PR #23 are composed by the opt-in
[finite track](operations/AUTONOMOUS_TRACK.md). This branch implements the
remaining original Issue #22 scope, now accepted on main.
Its controlled project qualification is separate from the unstarted M8 pilot;
no live project, issue closure, release or deployment is authorized here.

## Issue #17 operator interface

The accepted #22 code is merged; genuine full lifecycle qualification remains
NOTRUN and is explicitly deferred to M8. Issue #17 adds installed operator data
profiles, read-only enrollment/preview, finite explicit delegation and safe CLI
composition of the accepted ports. See [Operator setup](operations/OPERATOR_SETUP.md).
It adds no CI, sandbox, language-specific runner, project environment or M8 pilot.
Its code and focused qualification await independent integration acceptance.

## M10-B single-Issue personal product lifecycle (#41)

Accepted #40 publication is the code prerequisite. Accepted main
`b93d592909315bf952343fca82591d1fbca77feb` includes the
[personal PR/check/review/merge composition](operations/PERSONAL_PRODUCT.md),
with separate exact operator consent, current native evidence, original finite
M1/M2/role budgets and verified native results. The candidate
[#42 personal track](operations/PERSONAL_TRACK.md) adds evidence-qualified native
progression, separate reporting/next-scope consent and durable bounded recovery.
It preserves per-Issue windows and requires an already local exact merged base.
Its code and evidence need fresh independent review and operator integration.
Genuine M8, managed upgrade,
pilot mutation, release and deployment remain NOTRUN/unauthorized.
