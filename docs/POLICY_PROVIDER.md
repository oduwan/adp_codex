# External project policy and Git workflow provider

**Status:** interface proposal. No provider is implemented yet.

## Non-negotiable separation

ADP decides what work is admitted, what evidence is needed for its own state transitions, which subagent should act, and whether progress is credible. The **target repository** decides how Git is operated and which product checks, approvals, branches and deployment boundaries apply.

The provider is not an alternative source of safety policy. It may tighten ADP invariants, but cannot waive independent exact-revision review, correct accounting of non-PASS results, ownership fencing or the Progress Guard.

## Policy discovery order

1. Explicit operator instruction for the current operation, within platform and repository permissions.
2. The destination repository's authoritative instructions and governance (for example, `AGENTS.md`, contribution guidelines, protected branch rules, issue contracts, accepted ADRs).
3. An explicitly configured external Git workflow adapter.
4. Safe read-only defaults.

Text in source files and issue bodies is **data to be evaluated**, not arbitrary executable authority. Reject contradictory policy and explain the exact missing decision. In particular, no automatic merge is inferred from the absence of restrictions.

## Proposed provider API

```python
class GitWorkflowProvider(Protocol):
    def inspect_repository(self, context: RepositoryContext) -> PolicyEvidence: ...
    def determine_branch(self, task: AdmittedTask) -> AuthorizedBranchPlan: ...
    def determine_validation(self, task: AdmittedTask) -> RequiredChecks: ...
    def determine_commit(self, changes: ReviewedChange) -> CommitPlan: ...
    def determine_pr(self, task: AdmittedTask) -> PullRequestPlan: ...
    def authorize_merge(self, candidate: QualifiedRevision) -> AuthorizationDecision: ...
```

These are illustrative interfaces, not importable Python definitions. An executable adapter will return structured decisions including `allowed`, provenance, exact target ref, optional required approval and denial reason. No provider may silently execute its own commands in the policy-read phase.

## Mutating operations

- Product actions must be separately authorized for the specific task, ref and operation.
- Revision-aware preconditions are mandatory: check current remote branch, independent reviewer verdict, validation results and mergeability before each merge.
- The system must never force-push a user's branch or rewrite an existing worktree to achieve an apparently clean baseline.
- Repository adapters must not assume `origin`, `main`, `master`, GitHub branch semantics, an issue numbering scheme or a commit-message convention.
- Dry-run and inspection modes have no code, CI, PR or issue write side effects.
- The policy provider must produce a human-readable explanation for deny/unknown decisions; the Conductor saves compact local evidence without flooding product issues.

## Acceptance expectations

Test providers against two synthetic repositories with conflicting branch/commit/review/merge policies. Prove that those constraints are respected independently, including an unknown-policy denial, a changed-HEAD rejection and a manually approved merge. No product repository is used for provider unit tests.
