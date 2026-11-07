# Security policy

## Status

ADP Codex is a research/architecture-stage project, not a production-grade autonomous execution system. The current skill is read-only. Do not use this scaffold to authorize changes to product repositories.

## Threat model

This project will ingest **untrusted** issue bodies, comments, pull requests, repository text, test logs and tool results. Such content can contain prompt-injection attempts, misleading links, forged instructions or malicious commands. It must never be promoted into operator, system, repository governance or tool authority merely because it appears in an Issue.

Future engine boundaries must enforce:

- Explicit repository and user authorization for each mutating action.
- Separation of independent review from the authoring context.
- Exact-revision validation and refusal after HEAD drift.
- Git and memory ownership fencing, no force-push/rewrite on conflicts.
- No secrets, personal data, production documents or raw diagnostics in portable memory.
- Data minimization and bounded retention of working state.
- A mandatory Progress Guard that blocks unproductive or unsafe retries.
- No deployment, account administration, credential handling or release merge without separately established authority.

## Reporting a vulnerability

Do not post exploit instructions, credentials, tokens, private data or sensitive logs in public issues. If GitHub private vulnerability reporting is available for this repository, use it. Otherwise request a private disclosure channel from the maintainer without sharing exploit detail publicly.

As the project matures, this file will document supported versions and a formal response policy. No security support SLA is currently promised.
