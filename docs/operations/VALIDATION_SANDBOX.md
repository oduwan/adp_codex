# Explicit Linux validation sandbox

Issue #15 adds a candidate `adp.validation_sandbox.BubblewrapValidation` port.
It is selected by trusted operator controller code; installation, repository
files, issue prose, environment variables and credentials cannot enable it.
No existing live product is a qualification target. Public release, installation
on live projects, merge and deployment remain NOT_AUTHORIZED.

## Supported profile and trust boundary

The supported profile is Linux x86_64, non-setuid bubblewrap, mandatory user,
network, PID, IPC and UTS namespaces, and the accepted M5 child-subreaper.
There is no `--unshare-*-try`, privilege fallback, host-root bind or automatic
dependency installation. A failed real probe produces a typed unsupported
capability; `run` raises `UnsupportedValidation` with
`UNSUPPORTED_VALIDATION_RUNTIME` before any product check. The existing Conductor
keeps that invocation blocked rather than inventing a successful validation.

The operator supplies a dedicated credential-free runtime image and its exact
digest, the exact bubblewrap executable/digest, registered executable/argv and
original check denominators, protected memory/controller/authentication roots,
and an owned mode0700 private receipt directory outside the source and image.
The image contains only the chosen runtime closure, never a whole `/usr`, host
home, credential store, trusted controller, memory or unrelated worktree.
Image symlinks, hardlinks, devices and other special files are refused; every
image byte/mode/path is bound to the policy. Replacing the launcher invalidates
the configured policy too. This is an integrity digest, not an invented signing
key or external execution-authorization receipt.

Bubblewrap mounts that image read-only at `/`, the explicit product read-only at
`/work`, a new PID-namespace procfs read-only at `/proc`, and minimal devices
read-only at `/dev`. The original host paths, temporary directories, IPC/socket
stores and authentication files are not mounted. `/tmp` is an empty read-only
image directory. The initial qualified profile deliberately supports **one
process and zero writable scratch bytes**. Checks needing children, threads,
native network or writable caches/scratch require a separately qualified profile;
they cannot silently fall back to the host. This is not a general container or
package-manager service.

The seccomp filter checks the x86_64 audit architecture, rejects x32/compat ABIs,
and kills filesystem mutation, writable open/openat, process/thread creation,
setsid, Internet/raw sockets, namespace changes, tracing, alternate open and
selected kernel/IPC interfaces. A caught write error followed by exit zero cannot
manufacture PASS: the mutation syscall kills the process before its handler can
emit a receipt. AF_UNIX socket creation returns EPERM, still denied, because libc
NSS performs that harmless startup probe; no host Unix socket path is mounted.
Network namespace isolation is separately demonstrated with an actual fixture
listener and an outside positive control, not only a missing token or unused port.

Linux resource limits bound per-process address space, CPU, descriptors, regular
file size (zero), and core size (zero). Default address space is256MiB, CPU10s,
descriptors64 and combined output64KiB, each with explicit upper bounds. Wall time
is further limited by each registered command and the invocation/M2 budget.
The no-fork filter gives a hard one-check-process bound even when root-UID
RLIMIT_NPROC would not enforce it. Trusted supervisor/bubblewrap setup processes
remain outside that target limit. The trusted CLI/OS/runtime image and hostile
same-user administration or kernel replacement remain outside this boundary.

See the [bubblewrap project security model](https://github.com/containers/bubblewrap)
and [0.6.1 flags](https://github.com/containers/bubblewrap/blob/v0.6.1/bwrap.xml).
The actual selected flags, runtime version and policy digest must be observed;
the presence of the binary is not qualification.

## Operator API

Create a `SandboxPolicy` with explicit image/binary hashes and registered image
executable. Construct `BubblewrapValidation(commands, policy=...,
protected_roots=(memory, controller, authentication_root, ...), receipts=...)` and
assign that port to the existing `Project.validation` interface. `commands` is a
tuple of accepted `CheckCommand` records, not commands extracted from an issue.
No shell interprets the argv. The policy image's `/work`, `/proc`, `/dev` and
`/tmp` mount slots must exist and be empty before execution.

`capabilities()` runs a finite benign/write/network/fork probe against a newly
owned disposable directory and returns a typed `ValidationCapability`. Every
`run` performs a fresh probe before launching its registered product matrix.
No positive flag, old receipt or bare prefix bypasses that check. Raw
`SubprocessValidation.sandbox_prefix` is refused. Explicit
`trusted_disposable=True` remains available only for owned synthetic fixtures;
it is not used to implement this production port.

The supplied source must be a standalone Git checkout with ordinary private Git
objects. A linked `.git` file, outside symlink, hardlinked source/administrative
file, special file, credential-bearing Git configuration or executable Git filter
is unsupported. These additional preflight refusals prevent aliasing outside
data; read-only OS mounts remain the enforcement boundary. Source/admin seals
and exact HEAD are checked too, but their post-run hashes are not presented as
containment by themselves. Source inventory is bounded at8192entries/64MiB and
the runtime at4096entries/128MiB.

## Stop, restart and accounting

The port reuses M5 `supervised_validation` and `validation_stopped`; every process
must have a request-bound supervisor stop receipt. Private receipt copies contain
actual stop status and bounded output, not public product comments. A per-source
nonblocking lock and durable RUNNING record prevent duplicate or interrupted
validation from blindly launching again. A missing stop, stale RUNNING record,
or concurrently held lock raises `UnconfirmedValidation`. No PID disappearance
is reclassified as a successful stop. Operator reconciliation is required; this
port does not guess that an old process is dead or silently clear its record.

Ordinary measured FAIL/ERROR/TIMEOUT/SKIP/NOTRUN/UNKNOWN/quarantined outcomes retain
the original denominator. An ordinary failure continues the finite safe matrix.
Only complete counts, the original positive denominator, zero quarantines, all
PASS and actual exit zero can yield PASS. Malformed/empty output never passes.
OS policy violations, output containment or unconfirmed stops raise a safety
exception with the affected check UNKNOWN and all later checks NOTRUN. The
Conductor's accepted exception path latches M2 containment and refuses reuse or
handoff. There is no guard reset, new schema or automatic migration.

## G0 observations and qualification matrix

Accepted source admission: `16c7a4e103c6a824f361f96e2eb237fbbf4faf48`.
Actual host: Linux6.18.33.2-microsoft-standard-WSL2 x86_64; bubblewrap0.6.1,
non-setuid mode0755. No installation/global privilege modification was made.
The assistant's nested sandbox denied bubblewrap namespace setup; that context
remains UNSUPPORTED. Running the same bounded probe on the actual host succeeded.

Before implementation, actual writes to tracked, untracked and `.git/config`
fixture paths failed with EROFS; a host-only fixture was absent inside. Result
SHA256 `c7ec84e3990df1f1fc855cc4a9c010e14865c90c138ae0b5b66dc66bee850c29`.
The first unused-port observation was insufficient network proof and was not
counted as listener qualification. A second bounded proof used a listening
loopback fixture: outside positive control connected, the isolated connection
failed, and the listener received no sandbox connection. Evidence SHA256
`dca97cab533c9d6d5ecfc390ded0ecded0df25001e4fdf2a6e20a40a63d8b623`.
Both proofs and exact argv remain private outside Git.

The initial14-method focused run observed5PASS/9SKIP, **not qualification PASS**.
Its private log SHA256 is
`b29aa8f4b128afc5885137db8a52d1eb6d2711d12b0a2453741afcaead127eca`.
One bounded strace established that libc NSS startup attempted an AF_UNIX socket;
the first fatal socket rule prevented benign Python startup. The corrected rule
returns EPERM for AF_UNIX without allowing any socket, while Internet/raw sockets
remain fatal. The corrected actual benign/write/network/fork probe succeeded.
The first-observation record SHA256 is
`306be170643d3f42229e4475e185ca471ec6ab33cfa00675676a710f4e26ebcc`.

The corrected first full run observed13PASS/1ERROR, zeroSKIP, in283.102s. The
error was an honest capability TimeoutExpired; its stage was not retained, so
the precise cause is UNKNOWN and no timeout increase is justified. Independent
reassessment also reproduced an uncertain-probe-stop propagation defect in the
candidate (one safety assertion FAIL, private evidence SHA256
`b1944a873497a797e593ffb2ffaa12a6fe9a11a93cc41a5661f50f9fd1570fb1`).
Its failing regression is preserved before the correction; this candidate must
not be accepted until every probe has durable launch fencing and lost-stop
propagation is corrected and independently re-reviewed.

Independent review also demonstrated a modern fchmodat2 attempt returning an OS
read-only error, caught by a command that then emitted a false PASS under the
first denylist. Source bytes remained unchanged, but terminal-attempt accounting
was defective. Private reproduction SHA256
`cd0168b60766fc64c97cb16a8685ceef31b76874556c797637b8e7225f8dacdd`.
The preserved modern-mutator regression requires a default-deny syscall domain;
no unsupported or future mutation syscall may evade the terminal boundary.

The focused inventory is `tests_m7/test_validation_sandbox.py` (16 methods: the
original14 plus independently reproduced lost-stop and modern-mutator regressions),
separate from all210 byte-preserved accepted M1–M6 tests. Required observations:

| Boundary | Actual procedure | Required result |
| --- | --- | --- |
| Qualified/unsupported host | Real namespace/probe execution; false runtime fixture | Supported only after actual OS proof; no product execution when unsupported |
| Filesystem/admin/runtime | Tracked/untracked/.git/runtime/private write with exit-zero handler | OS refusal; terminal UNKNOWN/NOTRUN, outside hashes/refs unchanged |
| Host data/credentials | Actual reads of protected fixture, trusted-controller and host temp paths | Paths inaccessible, no credential inheritance |
| Network | Live listener G0 plus Internet socket attempt in final filter | No connection/no inherited host socket; terminal refusal |
| Alias/path trust | Outside symlink/hardlink, parent symlink, Git filter, changed runtime | Refuse before product launch |
| Process/lifecycle | fork/double-fork/setsid, timeout and missing stop | No escaping child or false stop; later inventory blocked when uncertain |
| Resources | Memory/CPU/descriptor/output/file bounds | Actual limit observation; no false PASS or infinite continuation |
| Accounting | Two matrices, every non-PASS, quarantine, malformed result | Original denominators and complete honest outcomes |
| Restart/concurrency | Durable RUNNING and held source lock | No duplicate launch or automatic reset |
| Policy/API | Raw prefix, edited runtime hash, shell-looking argv | Explicit pinned selection only; no shell or implicit authority |

Final exact-source Python3.11/3.12 results, actual OS qualification, CI capability
limits and independent security/code review must be attested in this issue's
Draft PR after final source is committed. No future PASS or approval is claimed
here. Private temporary evidence is host-lifetime material; retain it privately
for later audit. Unsupported CI/host scenarios remain SKIP/NOTRUN/UNSUPPORTED,
never substituted with mocks or hidden inside a green count.
