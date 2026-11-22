# First use in Codex

For a personally owned GitHub.com project without independent providers,
choose [personal enrollment](PERSONAL_ENROLLMENT.md) inside `$adp-codex`.
It uses the same managed launcher with an explicit personal backend, no manual
JSON, automatic approved local coordination and a separate finite-run approval.
A main checkout can propose an approved isolated feature worktree. Existing
rules apply and missing/unknown checks never become PASS. The signed-provider
walkthrough below remains available unchanged for that mode.

## Install and open your project

Follow the [installation guide](INSTALL_ADP.md) once using the approved archive,
reviewed installer, full revision and trusted archive digest. Install the
engine and plugin under the account that runs Codex. The installer will show
its effects before requesting confirmation.

Open your existing project in a fresh Codex session on the feature checkout
you intend to use. In the skill picker select `$adp-codex`. Codex may show
the namespaced label `adp-codex:adp-codex`. Start with a request such as
“Use $adp-codex to inspect the project open in this session.” The Skill calls
the managed engine and shows the observed GitHub repository, exact branch
and revision, native dependencies, visible check contexts and blockers.

If the Skill is missing, run the installer’s `verify` action under the same
`HOME` and `CODEX_HOME` and start another fresh session. It checks the exact
engine files, plugin registration, enablement and Skill discovery. If the
engine and Skill are incompatible, verify or repair the paired installation
before continuing. A runtime capability observation depends on the CLI and
host features exposed in that session.

## Set up one issue

Say “Set up ADP for this project.” Select the remote if the checkout has
multiple remotes. The Skill asks for any missing choices, including the open
issue and where to retain private enrollment state. Use a private directory
outside the project. Authenticate `gh` for `github.com` outside chat or
tell the Skill the name of an environment variable holding an appropriate
read credential. Enter credentials only into your trusted login or secret
management tool.

Select the protected trust root and proposal service supplied by the project
operator. The service uses the [guided enrollment protocol](GUIDED_ENROLLMENT.md)
to provide the signed profile. The project and its independent authorities
supply policy, scope review, project checks and narrowly scoped credentials.
The proposal names the existing owned coordination checkout and local bare
remote. You select and approve these paths in Codex. The project operator
prepares the service and coordination storage. You do not need to construct
signed JSON or set up a separate memory worktree yourself.

Review the plan before confirming. It names the project, issue, exact
feature revision, delegated operations, required checks, finite window,
and every proposed local destination. If you choose to proceed, explicitly
approve the displayed plan and its coordination-memory writes. A missing
provider leaves setup blocked with the appropriate next action. Resolve it
with the independent provider before approving a fresh plan. Setup itself
initializes protected ADP state through the installed engine.
If the service is running but the Codex session cannot reach its local socket,
check the session's tool permissions. Approve access only for the selected
managed command and the trusted provider.

## Inspect, start, and return later

Ask for “ADP status,” “ADP doctor,” or “preview ADP for this issue.” In a
new session reselect the same project, enrollment directory and trust root.
Choose reconnect for an existing enrollment. Diagnostics check current
independent provider inputs. A verified configuration and supported
runtime still require separate authorization for work.

To start, ask “Preview a one-round ADP run with one worker at a time.”
After the Skill shows the operation, target, revision, possible effects,
ownership and finite limits, explicitly authorize that invocation if the
scope is correct. A run is synchronous and bounded. Pending CI needs current
project evidence. A human-required merge waits for the project’s decision.

If a command is interrupted, use status and diagnose the original
enrollment or execution before attempting a retry. Resume is a separate
confirmation for the same retained window and budget. Handoff is a separate
confirmation to relinquish ownership through the existing stop checks.
Preserve the private state, trust, evidence and receipts. The established
[operator recovery procedures](OPERATOR_SETUP.md#commands-and-restart)
cover expired windows, lost or foreign ownership, missing stop evidence and
earlier M7 profiles.

## Supported inputs

First-use enrollment currently selects one open issue on an existing
GitHub.com HTTPS feature checkout. It expects an independently provisioned
trust root and proposal service, protected local paths and the accepted
project providers. The Skill reads native dependency information and visible
branch rules. Project policy and signed provider evidence establish the
actual gates. The support and qualification limits of the installed engine
still apply.
