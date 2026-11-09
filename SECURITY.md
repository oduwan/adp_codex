# Security policy

## Supported scope and release boundary

M1–M5 are accepted implementations, including finite policy-gated execution.
M6 independently qualifies the stated host/backend envelope; it does not certify
production deployment, select a license or authorize a public release. The
packaged planning skill remains read-only. No security support SLA is promised.

## Trust and containment

Issue/comment/README text, policy prose, PR metadata, worker output and test logs
are untrusted data. They cannot grant execution rights or authenticate a reviewer.
The operator, supported Codex CLI/authentication installation, OS controls, Git
administration, external evidence verifiers and explicitly configured extensions
are trusted. A verifier that accepts arbitrary labels invalidates that boundary.

- M1 has one owner, generation fencing, immutable assignments/results and strict
  checkpoint/CAS recovery. Git is not a distributed lease; takeover requires a
  separately confirmed stopped owner. Read-only inspection never claims ownership.
- M2 reserves material execution, retains stall counters, requires independent
  exact-context evidence and stops unsafe/unproductive attempts. No reset or
  threshold bypass is available. Diagnostic censuses retain non-PASS denominators.
- M3 requires verified external project rules and exact operation authorization;
  credentials and green CI confer no merge, release or deployment rights.
- M4 intake/planning is GET-only and cannot execute embedded commands, mutate
  canonical memory or manufacture readiness from incomplete observations.
- M5 isolates workspaces and Developer/Reviewer/Forensic contexts, binds review to
  exact SHA, checks every effect and persists intent before external submission.
  Linux subreapers must kill/reap detached descendants before stop confirmation.
  Missing worker/validation stop evidence remains UNKNOWN across restart/handoff.

The trusted engine must be installed outside worker roots. Developer sandbox
writes are admitted narrowly; review/forensics are read-only. Direct worker
network and broad temporary write roots are disabled. The CLI frontend receives
minimal process/model-auth settings; Git/forge/ADP/cloud/SSH environment credentials
are excluded. Shell inheritance is restricted. These filters do not prove an
arbitrary host's filesystem/authentication isolation or defend against hostile
same-user administration, kernel compromise or replacement of trusted binaries.

## Private evidence and output

Raw worker transcripts, credentials, diagnostic logs, local ownership tokens and
runtime state stay outside Git. Only bounded structured public summaries, hashes
and approved identifiers belong in portable memory/product reporting. Recognizable
credential/private-key shapes in worker results, including nested forensic fields,
are refused before checkpointing; the affected work is blocked and ordinary
reservations receive a contamination stop. This bounded detector is defense in
depth, not universal secret detection or proof that arbitrary prose is public.
Trusted output classification and operator review remain necessary. Existing
historical disclosure cannot be repaired by hiding a later result; stop, rotate
any real exposed credential and obtain explicit disposition without rewriting
history under this qualification task.

Qualification uses synthetic credential markers and newly disposable repositories
only. Real production records, tokens and raw artifacts must never enter tests,
commits or public reports. Live GitHub mutation qualification is not supplied.
Local CAS push and trusted-disposable validation cannot be relabeled production
network/sandbox qualification. Unsupported environments/operations fail closed.

The optional [validation sandbox](docs/operations/VALIDATION_SANDBOX.md) requires
explicit pinned runtime-image and binary selection plus real OS capability probes.
Its initial Linux x86_64 profile permits one process and no writable scratch;
namespace mounts and seccomp enforce its boundary. Raw command prefixes do not
qualify production validation. A supported probe grants no M1/M2/M3 or operator
execution authority, and an unavailable host never silently executes checks.

## Reporting a vulnerability

Do not post private data, credentials or sensitive logs in public issues. Use
GitHub private vulnerability reporting when available; otherwise request a private
channel from the maintainer without disclosing exploit detail publicly.
