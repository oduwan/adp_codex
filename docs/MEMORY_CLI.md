# Portable memory CLI and API

This issue branch implements the M1 coordination kernel. Accepted `main` remains
non-autonomous; discovery, policy decisions, Progress Guard and worker execution
are not implemented here. Python 3.11+ and Git are required. The runtime uses only
the Python standard library.

## Configuration and identity

Install with `python -m pip install .`. An importable `adp` package and an `adp`
entry point are provided. Configuration is discovered at the selected Git
worktree root in `.adp.json`, or selected with `--config`. Explicit command-line
values override configuration:

```json
{
  "schema_version": 1,
  "remote": "team",
  "repository_id": "forge:project/opaque",
  "memory_branch": "coordination/current",
  "storage": "../project-memory"
}
```

Repository selection uses `--repo` (default current directory). With more than
one remote, select one explicitly. Fetch and push endpoints must match exactly.
The default repository identity is a SHA-256 digest of the normalized endpoint;
provide a shared explicit identity when machines use different endpoint aliases.
Neither a remote name, product branch, forge nor numeric issue syntax is assumed.
The branch `adp/state` is a suggestion only: both branch and external storage
must be selected. Relative storage resolves against the product worktree root.
All configuration and storage ancestors must be free of symlinks, and memory
must not overlap any product worktree or Git administrative directory.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Successful operation or healthy read-only inspection |
| 2 | Usage, missing/ambiguous configuration or unsafe author identity |
| 3 | Invalid schema, unsafe path, unexpected files or storage corruption |
| 4 | Ownership, generation, revision or remote-head conflict |
| 5 | Git/transport/authentication failure; pending writes need inspection |
| 6 | Explicit memory-write authorization missing |

Errors are controlled refusals with human-readable explanations. No external
product action is authorized by a successful memory command.
