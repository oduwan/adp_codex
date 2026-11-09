# Contributing

M1–M5 are accepted through PRs #7–#11. M6 is qualification and documentation work,
not publication or deployment authority. The Python engine supports finite,
explicitly authorized execution; the packaged planning skill remains read-only.

Read [Architecture](docs/ARCHITECTURE.md), [Security](SECURITY.md),
[Progress Guard](docs/PROGRESS_GUARD.md), [External policy](docs/POLICY_PROVIDER.md),
[Conductor API](docs/CONDUCTOR_API.md), [Git workflow](docs/GIT_WORKFLOW.md) and
[Roadmap](docs/ROADMAP.md). The memory, guard, policy and discovery APIs document
accepted schemas and explicit migrations. Preserve their safety contracts.

## Workflow and verification

1. Fetch current main, verify prerequisites and create an isolated issue worktree.
2. Follow the binding repository Git policy: English Conventional Commits with
   `Refs #N`, a safe public Git identity, normal issue-branch pushes and one Draft
   PR against main. Never modify another contributor's checkout or force history.
3. Keep work scoped and tests falsifiable. Qualification targets must be newly
   disposable Git repositories and controlled API fixtures. Existing live product
   repositories are never automated test targets.
4. Freeze inventories before execution. Preserve failures, original denominators
   and quarantines; SKIP/NOTRUN/ERROR/TIMEOUT/UNKNOWN never become PASS. Do not
   increase timeouts or weaken assertions to conceal a defect.
5. Verify installation/CLI, scaffold and all regressions on Python 3.11 and 3.12:

   ```bash
   python scripts/validate_scaffold.py
   python -m unittest discover -s tests -p 'test_*.py' -v
   ```

   M6 adds private evidence runners and a fixed scenario matrix; see
   [qualification procedures](docs/qualification/INSTALLATION.md) and
   [the report](docs/qualification/M6_REPORT.md). Keep raw evidence outside Git.
6. Obtain independent security/design and exact-final-revision code/schema/evidence
   review. A later source or report commit invalidates the corresponding approval;
   repeat affected qualification/review. Leave integration to separate authority.

Use small typed standard-library interfaces, bounded schemas and explicit errors.
ADP's own contributor branch/commit conventions apply only to this repository.
Never impose them on targets or infer rights from credentials, prose or CI.

## License and release

No license has been selected; public repository access grants no additional reuse
license. Do not invent license metadata, claim a redistributable open-source
release, publish a tag/listing, deploy or merge from qualification success. Public
release remains NOT_AUTHORIZED until the operator selects terms and explicitly
approves publication separately.
