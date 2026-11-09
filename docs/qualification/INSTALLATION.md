# Local installation and qualification

Public release is NOT_AUTHORIZED. These procedures stage/install development
artifacts locally; they do not publish to a registry, plugin directory or Git tag.
Choose license/distribution terms separately. Use owned disposable projects only.

## Python engine

From a clean pinned ADP checkout with Python 3.11 or 3.12:

```text
python scripts/qualify_installation.py --source-ref FULL_GIT_SHA --evidence-dir /tmp/adp-install-unique
```

The script exports that exact Git archive, creates a fresh consumer venv without
system site packages, proves ADP is initially absent, builds a wheel with the
declared build dependencies, and installs that wheel offline without dependencies.
It checks isolated import and actual CLI/help invocations from an unrelated empty
working directory. Build dependencies may be downloaded; no target GitHub endpoint
or product system is contacted. Each command has a fixed finite budget. A failure
retains its private log and must be reported before a corrected bounded retry.

Evidence directories must be absent or owned mode0700 directories outside source;
files are exclusive mode0600. Existing results are never overwritten. The summary
records exact source, interpreter, archive/wheel and log hashes. No editable source
or current-directory import can substitute for the installed wheel probe.

For regular local engine setup, install the selected source into a fresh venv and
use `adp --help`. Start with `init --dry-run` or read-only `discover`/`plan`. Mutation
requires explicit operator/project evidence and configured qualified ports. The
package does not contain a permissive controller or production validation sandbox.

## Portable planning plugin

Current [official packaging guidance](https://developers.openai.com/plugins/build/plugins)
recognizes root `plugin.json` and root `skills/`. An OpenAI compatibility overlay is
optional; M6 does not invent a mandatory `.codex-plugin/plugin.json` requirement.
Keep the full portable root, including documentation referenced by SKILL.md.
Copying an isolated SKILL.md does not install the engine or its supporting docs.

Use a newly owned local catalog with a unique name and a relative source path to
the pinned package. The [Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference)
documents local plugin installation/listing/removal; no public listing is involved:

```text
codex plugin add adp-codex@YOUR_DISPOSABLE_CATALOG --json
codex plugin list --marketplace YOUR_DISPOSABLE_CATALOG --json
codex plugin remove adp-codex@YOUR_DISPOSABLE_CATALOG --json
```

The qualification procedure checks original bytes and metadata in the installed
copy, then actual enabled skill discovery through documented `skills/list` in a
fresh Codex app-server session scoped to the disposable project. It never starts a
model turn or a daemon. Enabled discovery is distinguished from untested GUI or
model-driven onboarding/skill usage. Unsupported surfaces must be reported as
UNSUPPORTED/NOTRUN, not as a successful install. Temporary namespace installation
is cleaned up with the supported CLI; existing unrelated plugin entries stay intact.

The packaged skill provides read-only analysis/setup guidance. Merely installing,
enabling or reading it cannot grant Git, memory, agent or release authority. It
registers no MCP service, hook or automatic command.

## Complete regression evidence

```text
python scripts/qualify_m6.py --evidence-dir /tmp/adp-suite-unique
```

Use clean committed source. This runs the accepted193 tests plus every new M6
method, retains original IDs, continues ordinary failures, and writes private raw
logs plus a hashed structured result. Missing, skipped or failed cases cannot be
reported PASS. Public output contains only test IDs/outcomes and sanitized summary
metadata. [The frozen plan](M6_PLAN.json) contains42 scenarios, separately from
unittest method counts. [The report](M6_REPORT.md) maps each scenario to actual
procedures/evidence and states host/backend limits, simulated versus real proof,
independent verdicts and the final integration-review boundary.
