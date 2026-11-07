# Contributing

Thank you for helping develop ADP Codex.

## Current phase

The project currently ships a **planning-only skill scaffold**. Please do not describe it as an autonomous developer or advertise unimplemented CLI commands.

Read [Architecture](docs/ARCHITECTURE.md), [Progress Guard](docs/PROGRESS_GUARD.md), [Policy Provider](docs/POLICY_PROVIDER.md) and [Roadmap](docs/ROADMAP.md) before proposing major changes.

## Workflow

1. Open an issue that states the observable requirement, constraints and bounded acceptance tests. For cross-cutting design changes, discuss the contract before implementation.
2. Create a focused branch. Keep changes limited to one coherent issue and preserve intended external project policies.
3. Update tests and docs alongside code. Use synthetic Git remotes, fixtures and disposable worktrees; never write to a production repository during automated tests.
4. Run local scaffold checks:
   ```bash
   python3 scripts/validate_scaffold.py
   python3 -m unittest discover -s tests -p 'test_*.py' -v
   ```
5. Open a PR describing purpose, changes, evidence, limitations and unresolved risks. Request independent review of the final exact revision. Any subsequent commit invalidates a prior exact-revision approval.

Do not weaken checks, count skipped/quarantined tests as PASS, or conceal uncertain outcomes. The Progress Guard is a core invariant and must be exercised with negative tests before autonomous execution is enabled.

The repository does not specify commit-message conventions for other projects. Their conventions must come through external policy providers.

## Coding standards

- Target Python 3.11+ for implementation unless a reviewed issue establishes another baseline.
- Prefer small typed modules, clear error types and explicit interfaces.
- Keep the runtime dependency graph minimal.
- Avoid filesystem assumptions, hard-coded Git remotes, repository names, branch conventions and fixed numeric issue IDs.
- Keep documentation in English.
- Do not publish secrets, private test data or sensitive machine paths.

## Legal

A public repository with no license does not imply permission to reuse code. Maintainers will select a license before presenting the package as an open-source release. Discuss substantial contributions with that limitation in mind.
