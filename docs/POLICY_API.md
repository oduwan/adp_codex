# External Git workflow policy API

Issue #3 supplies a typed, standard-library policy provider candidate. M1 memory
and M2 guard are accepted through PRs #7 and #8. This module neither executes
Git writes nor enables `discover`, `run`, workers, CI, comments or deployments.

## Importable interfaces

```python
from adp.config import Config
from adp.policy import PolicyProvider
from adp.policy_adapters import GitPolicyAdapter, MockRepositoryAdapter, M2SafetyAdapter
from adp.policy_types import (
    Authorization, Effect, GitWorkflowProvider, Operation, Request, Task,
)

# The remote and policy paths are explicitly selected by the destination project.
adapter = GitPolicyAdapter(
    Config.discover("./project", remote="team"),
    profiles=(".project/workflow.json",),
    contracts=("docs/accepted-contract.md",),
)
provider = PolicyProvider(adapter)
inspection = provider.inspect_repository()  # observation only, no authority
```

The example deliberately supplies no verifier or safety port. Documents alone
cannot authorize anything. `PolicyProvider.plan(task, request)` returns a frozen
`Plan`; `decide(plan, authorization)` returns a `Decision` with `ALLOW`, `DENY`
or `UNKNOWN`. Only a final `Decision(ALLOW)` qualifies an operation. A plan's
`policy_effect=ALLOW` describes policy completeness, not permission to execute.
Malformed or oversized inputs raise `ADPError` and confer no rights. Operational
Git failures may raise `GitError`; inaccessible remote refs are instead recorded
as unknown metadata. Extension callers must treat errors as refusals.

`GitWorkflowProvider` defines `inspect_repository`, `plan` and `decide`.
`PolicyProvider` also offers `determine_branch`, `determine_commit`,
`determine_validation`, `determine_pr` and `authorize_merge`. The generic method
supports every `Operation`. There is no execution method.

Every plan carries the admitted task's opaque ID, stable repository ID, source
ref and exact SHA, selected remote and its identity fingerprint, target ref and
expected remote revision, policy/snapshot hashes, provenance, required checks,
review count and current safety observation. Commit plans also bind the exact
staged index. A changed HEAD, ref, index, policy, protection or guard checkpoint
invalidates a saved plan. `decide` inspects again and compares the complete plan.
Two calls against unchanged inputs produce equal plans.

## Observation and trust ports

- `RepositoryAdapter.inspect() -> RepositorySnapshot`: trusted observational
  implementation. `MockRepositoryAdapter` accepts an explicit validated snapshot
  for offline callers. Neither adapter grants policy authority.
- `GitPolicyAdapter`: uses M1 `Config` discovery with a selected remote, reads
  committed policy blobs, refs, index and worktree status. Governance paths default
  to `AGENTS.md` and `CONTRIBUTING.md`; profiles/contracts require explicit paths.
  `injected` documents support pre-fetched, provenance-labeled observations.
  Committed symlinks, executable policy files, unsafe paths and duplicate sources
  are refused. Unstaged or untracked product files prevent qualified plans.
  Staged changes are allowed and hashed for a commit plan.
- `SafetyAdapter.observe(task) -> Safety`: trusted current ownership/guard port.
  `M2SafetyAdapter(guard)` reads synchronized M1 ownership and actual typed M2
  decisions, detects inconsistent reads, and requires the current canonical M2
  approval for acceptance operations. It never upgrades memory or reserves work.
  Original v1 memory therefore needs its separately authorized M2 upgrade before
  it can qualify execution; provider inspection itself needs no memory.
- `PolicyAuthority.verify(evidence, purpose=..., subject=...) -> bool`: trusted,
  observational external verifier. There is no permissive default implementation.
  It must authenticate canonical principals, their roles and the provenance of
  the exact subject. An always-true implementation destroys the trust boundary.
  Git credentials, document filenames and caller-chosen reviewer strings are
  insufficient authentication.

The provider emits hashes using `source_subject`, `protection_subject`,
`check_subject`, `review_subject` and `authorization_subject`. The verifier must
validate the independently obtained evidence against those hashes and these
distinct purpose domains:

| Purpose | Required external authority |
| --- | --- |
| `policy/operator` | Operator's exact project instruction and authorized role |
| `policy/governance` | Accepted repository governance and its exact interpretation |
| `policy/profile` | Project-owned configured profile and exact parsed rules |
| `policy/contract` | Accepted task contract; constraints only |
| `policy/protection` | Authenticated current protection and mergeability metadata |
| `policy/check` | Authenticated validation provenance and original coverage denominator |
| `policy/review` | Authenticated independent canonical reviewer and exact-SHA verdict |
| `policy/operation` | Explicit operator authorization of the complete plan and qualifications |

Source/protection hashes include the repository identity, remote name and
fingerprint, source ref and SHA. Check/review hashes also include task, operation,
target ref and policy digest. The operation hash includes the entire plan and
qualification evidence. M2 attestations cannot be replayed as M3 attestations.
Verifiers must normalize aliases to canonical principals before admission;
authors in both task context and the trusted guard observation are excluded.

## Supported sources and precedence

`SourceClaim` binds a `Rules` interpretation to the exact observed document hash,
reference, kind and validity interval. Governance prose is hashed, never executed
or automatically promoted to authority. An external verifier can approve `Rules()`
to affirm that a governance document adds no supported constraints; omitting its
interpretation produces `UNKNOWN`. Profiles must match the closed parsed rules
exactly. Missing sources, conflicting interpretations, unknown provenance and
expired evidence cannot qualify operations. Injecting data never verifies it.

For scalar conventions, authenticated operator instructions precede verified
repository governance, which precedes the explicitly configured profile. Equal
authority disagreement is `UNKNOWN`; the provider identifies the conflicting
field and references. Lower conventions may be superseded with provenance.
Any verified explicit operation `DENY` remains a denial. Required checks and
gate operations combine by union; review counts combine by maximum with an
independent-review floor of one. Deployment environments follow scalar priority,
then intersect accepted contract restrictions. Accepted contracts cannot supply
conventions or positive operation permissions. Protection metadata restricts
operations and cannot grant rights. `UNTRUSTED` issue/PR observations are ignored
as authority regardless of their text or claimed identity.

Provenance identifies observed, verified, unverified, ignored, selected,
superseded, conflicting and required sources. Mandatory ADP safety appears as a
separate invariant, granting no Git rights. ADP's own repository Git workflow,
branch names, commit conventions and PR preferences are never loaded as defaults.

## Closed profile schema version 1

A profile is UTF-8 JSON with exactly `schema_version` and `rules`. Rule fields
are optional; absent required semantics remain unknown. This example describes
one hypothetical project, not an ADP default:

```json
{
  "schema_version": 1,
  "rules": {
    "permissions": [
      {"operation": "BRANCH", "effect": "ALLOW"},
      {"operation": "COMMIT", "effect": "ALLOW"},
      {"operation": "PR", "effect": "ALLOW"},
      {"operation": "MERGE", "effect": "DENY"}
    ],
    "base_branch": "trunk",
    "branch_template": "work/{slug}",
    "subject_template": "change({task}): {summary}",
    "body_template": "Work: {task}",
    "subject_limit": 72,
    "pr_title_template": "Work {task}: {summary}",
    "pr_draft": true,
    "merge_method": "squash",
    "release_template": "release-{version}",
    "environments": ["sandbox"],
    "checks": ["unit", "integration"],
    "reviews": 1,
    "gate_operations": ["PUSH"]
  }
}
```

Unknown keys, versions, duplicate JSON keys, NaN, expression/template execution,
unknown operations and unsafe refs are rejected. Templates perform one literal
substitution pass only. Branch templates require one `{slug}`; release templates
one `{version}`. Subject/body/PR templates accept `{task}` and `{summary}`.
No shell commands, regular expressions or executable validation definitions are
part of the schema. Check names identify an externally defined validation matrix.
Supported merge methods are `merge`, `squash` and `ff_only`.

Source blobs are at most 64 KiB. There are at most 16 documents/claims, 4096 refs
per side, 32 checks, 16 reviewers, and 1 MiB canonical hashed data. Evidence
lifetimes must be positive, at most one hour, and current according to the trusted
clock. The external verifier controls whether an observation is authentic and
whether a coverage denominator is the original one; self-reported counts alone
never prove that. Unrepresentable constraints must be labeled unsupported rather
than dropped. Unsupported protection metadata produces `UNKNOWN`.

## Operation and acceptance semantics

| Operation | Typed payload and additional boundary |
| --- | --- |
| `BRANCH` | External template, explicit slug, exact start SHA; no overwrite of a differing branch |
| `COMMIT` | External subject/body/limit, admitted task branch, exact staged-index hash |
| `VALIDATE` | Required check identifiers; no command invocation |
| `PR` | External head/base/title/draft mode; authenticated base protections |
| `PUSH` | Explicit remote/ref/SHA and expected remote SHA; ordinary fast-forward/create only |
| `MERGE` | Exact source and base SHA, explicit method, method-specific verified mergeability |
| `RELEASE` | External version/tag template, policy base branch; no existing tag rewrite |
| `DEPLOY` | Explicit external environment and base branch; data-only plan |

Each operation, including validation, requires a separate exact-plan operator
authorization and fresh ownership/guard observation for `Decision(ALLOW)`.
Merge/release/deployment and ready PRs additionally require current canonical M2
approval, no unresolved acceptance criteria, all required checks PASS with their
original denominator and no quarantines, and enough independent exact-SHA
approvals. An authenticated requests-changes verdict denies acceptance. Draft PR
and preparatory operations retain the obligations without requiring the task to
be accepted already; external `gate_operations` can tighten this boundary for
commit, push, branch, validation or Draft PR creation.

`Protection` binds the exact target ref/revision and source SHA to authenticated
metadata. It carries known/unknown status, push/merge restrictions, checks,
review counts, allowed methods, unsupported constraints, freshness and provenance.
`mergeable_methods=None` is unknown; an empty tuple denies every merge method.
No mutation or trial merge is used to infer mergeability. `GitPolicyAdapter`
observes ancestry for ordinary push only, without fetching missing objects.
Mergeability is supplied by the trusted external metadata port.

`FORCE_PUSH`, `REBASE` and `REWRITE` always deny. Missing metadata never selects a
fallback. No Git credential can authorize a merge, release or deployment.

## Compatibility, qualification and limits

M3 uses new dataclasses and a separate profile version. It does not change M1
task/state versions, M2 guard records, thresholds, approval subjects or migration.
The provider has no state serializer, migration command or mutable memory cache.
Accepted M1/M2 source and tests remain unchanged.

The policy tests use two disposable repositories with different remotes, base
branches, branch/commit/PR conventions, review counts and merge permissions.
They verify read-only file/ref/worktree observations, current exact-SHA grants,
M1/M2 refusal, missing/inaccessible metadata, source precedence, injection,
malformed schemas, non-PASS accounting and cross-repository replay refusal.

```bash
python scripts/validate_scaffold.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

A future execution integration must obtain a fresh decision immediately before
each action and enforce Git/forge compare-and-swap preconditions, M2 action
reservation, replay consumption and idempotence. `ALLOW` is observational and
is not a durable, one-use execution capability; this provider does not consume
authorizations or close race windows with an external forge. Local Git config,
transport/credential helpers, trusted adapters, verifier and clock are inside
the deployment trust boundary inherited from M1. No live GitHub adapter,
automatic prose interpreter, issue discovery, Conductor, shell runner or
production qualification is included in M3.
