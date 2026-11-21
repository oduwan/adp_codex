# Install ADP Codex

Use the installer from an approved development distribution. The supplier
provides the reviewed `install_adp.py`, an uncompressed `git archive` of the
selected commit, its full Git SHA and a SHA-256 digest obtained through a trusted
channel. Keep these files outside your target project. The installer compares
the archive digest and Git commit recorded in the archive before using the
package. The digest is an integrity check against the identity you selected.
Public distribution still requires separate authorization.

Run this as your normal user on Linux or WSL2, with Python 3.11+ and its
`venv` and `ensurepip` support, a signed-in Codex CLI, and `gh` authenticated for
`github.com`.

```bash
python3.11 -I /path/to/install_adp.py install --source /path/to/adp.tar --revision FULL_GIT_SHA --sha256 ARCHIVE_SHA256
```

The installer prints the selected identity, existing installation state and
planned effects before prompting. Add `--dry-run` to see the plan without applying
it. Use `--yes` for an explicitly authorized noninteractive install. Preflight
queries `GET /user` through `gh` and checks native marketplace and plugin
registration, discovery and removal in a disposable Codex home. Package building may download the build dependencies
declared in `pyproject.toml`. The engine has no third-party runtime dependencies.

After installation, open a fresh Codex session and select the ADP skill from
the skill picker. The CLI may display its namespaced name
`adp-codex:adp-codex`. Check the engine from any working directory with

```bash
"$HOME/.local/share/adp-codex-install/current/bin/adp" --help
```

To use the short command name, prepend
`$HOME/.local/share/adp-codex-install/current/bin` to the PATH of the
shell where you launch Codex. The installer leaves shell startup files alone.
The skill provides read-only guidance. Project enrollment, authenticated
providers, execution authority and memory operations still follow the
[operator setup contract](OPERATOR_SETUP.md).

## Verify, repair, upgrade or remove

Use the same installer entry point, under the same `HOME` and `CODEX_HOME`.

```bash
python3.11 -I /path/to/install_adp.py verify
python3.11 -I /path/to/install_adp.py upgrade --source /path/to/new-adp.tar --revision NEW_FULL_GIT_SHA --sha256 NEW_ARCHIVE_SHA256
python3.11 -I /path/to/install_adp.py uninstall
```

- **Verify** checks installed package files, version, interpreter and launcher,
  runs `adp --help`, and
  reports Codex plugin installation, enablement and exact skill discovery in a
  new local app-server session. It does not start a model turn. Project-specific
  visibility can still depend on that project's Codex configuration.
- **Repair** by rerunning `install` with the active archive and digest. A healthy
  installation is reused. A missing or disabled managed component is replaced
  with a verified installation after confirmation.
- **Upgrade** stages and verifies the selected archive before changing the
  launcher. The previous engine stays active if staging fails. Codex may briefly
  list both managed plugins during the switch.
- **Uninstall** removes only receipt-owned managed generations, their launcher,
  and their Codex plugin and catalog registrations. It retains the private
  installer receipt directory. Operator profiles, trust material, memory,
  evidence and other Codex entries are outside the removal scope.

The fixed managed root is `$HOME/.local/share/adp-codex-install`. Each
generation contains its own Python environment and local plugin catalog.
`state.json` records the source SHA, archive digest, version, file digests and
managed Codex namespace. The catalog uses the user's existing `CODEX_HOME`
(default `$HOME/.codex`). Keep the managed root free of personal files.

## Troubleshooting

- If Python or Codex preflight refuses, use a supported Python installation
  and a Codex CLI that exposes JSON plugin listing, add/remove and marketplace
  registration plus stdio `skills/list`. Compatibility is checked at runtime.
- Authenticate through the existing Codex and GitHub CLI login interfaces if
  their checks fail. The installer does not persist credentials or establish
  their project authority. Verify and uninstall do not require the GitHub
  authentication check.
- If source acquisition fails, obtain the same local archive and trusted digest.
  On a build dependency download failure, restore access to the Python package
  index and retry. Check permissions and free space in the home and temporary
  directories.
- An independently installed enabled ADP plugin is reported before mutation.
  Disable that copy through Codex before installing a managed one. An
  independently installed `adp` on PATH is preserved.
- If an interruption leaves a pending generation, `verify` reports it. Rerun
  the requested operation to reconcile receipt-owned entries. If a marketplace
  was repointed or Codex cannot confirm removal, inspect the reported
  namespace before retrying. Missing managed catalog or cache files can be
  reconciled from the receipt and the remaining Codex state. Wait for an active
  mutation to release its lock before retrying. An interrupted command can
  finish under that lock. When a changed Codex format
  leaves ownership uncertain, the installer retains the receipt and refuses
  cleanup. Use `install` to recover an interrupted first install with no active
  launcher.

## Prepare the local development distribution

From a trusted ADP source checkout, the supplier selects a reviewed commit and
prepares the artifacts for transfer. These are maintainer steps.

```bash
git archive --format=tar FULL_GIT_SHA > /path/to/adp.tar
git show FULL_GIT_SHA:scripts/install_adp.py > /path/to/install_adp.py
sha256sum /path/to/adp.tar
```

Run the focused installer checks with
`python -m unittest discover -s tests_m9 -v`.
