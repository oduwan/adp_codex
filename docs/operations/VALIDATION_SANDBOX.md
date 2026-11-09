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
process and zero writable scratch bytes**. The target is PID1 in its namespace
(`--as-pid-1`); its filter forbids all child creation, and the external accepted
M5 subreaper supervises namespace teardown. The optional bubblewrap PID1 reaper
is unnecessary for this profile and would require an extra internal eventfd
write permission. Checks needing children, threads,
native network or writable caches/scratch require a separately qualified profile;
they cannot silently fall back to the host. This is not a general container or
package-manager service.

The seccomp filter checks the x86_64 audit architecture, rejects x32/compat ABIs,
and defaults to KILL for every unlisted syscall, including unknown/future calls.
An explicit read-only query/memory/timer/lifecycle allowlist excludes filesystem
mutation, writable open/openat, process/thread creation, setsid, Internet/raw
sockets, namespace changes, tracing, alternate open and kernel/IPC mutation.
Mappings must have exactly MAP_PRIVATE type bits; MAP_SHARED, SHARED_VALIDATE,
mixed and absent mapping types are fatal. This also prevents a later mprotect
upgrade of a shared file mapping without pretending that the stateless filter
tracks mappings. Only NORMAL, DONTNEED and FREE advice is permitted on private
memory; MADV_REMOVE, privileged and unknown advice is fatal.
Writes are restricted to the original stdout/stderr pipes; closing/replacing/
duplicating those descriptors is forbidden. A caught write error followed by exit zero cannot
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

`capabilities(fresh=True)` runs a finite benign/write/network/fork probe against a
newly owned disposable directory and returns a typed `ValidationCapability`.
Successful proof may be cached in this process for at most300s, with at most32
entries, only while actual policy/image/binary/launcher bytes, protected roots,
kernel/boot/PID/UID/GID/groups, user/mount/network/PID namespaces and parent
seccomp/no-new-privs/capability state remain identical. A bounded lock prevents
concurrent duplicate probes. Every launch still revalidates actual bytes and
executes the exact mandatory namespace/mount/seccomp setup. Cache hits grant no
command authority and cannot conceal a durable in-flight or unknown-stop marker.
Only success is cached; failure/uncertainty is never cached as qualification,
and an uncertain launch invalidates its cache key. No persisted or caller-provided
positive flag or bare prefix bypasses those checks. Raw
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
actual stop status and bounded stdout/stderr, not public product comments. Every
probe and product launch first writes a durable in-flight marker; only a validated
actual stop clears it. Capability checks propagate unknown liveness rather than
downgrading it to unsupported, and probe restart cannot bypass a pending marker.
A per-source
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

The corrected first full run observed13PASS/1ERROR, zeroSKIP, in283.102s. Log SHA256
`9c1c4f6e62ba326b3eaa784ac57c39fe9628dd7625fd4a79e81337d3c3f5b1dd`.
The
error was an honest capability TimeoutExpired; its stage was not retained, so
the precise cause is UNKNOWN and no timeout increase is justified. Independent
reassessment also reproduced an uncertain-probe-stop propagation defect in the
candidate (one safety assertion FAIL, private evidence SHA256
`b1944a873497a797e593ffb2ffaa12a6fe9a11a93cc41a5661f50f9fd1570fb1`).
Its failing regression is preserved in the candidate commit before the correction.
The correction adds durable launch fencing and typed unknown-stop propagation;
final independent re-review remains mandatory.

The independent finite reassessment classified that timeout as
UNCLASSIFIED_ADMISSION_INFRA: no product check launched, exact timeout stage lost.
With stage labels and unchanged budgets, the one targeted accounting-method
proof completed1/1PASS in154.435s (private log SHA256
`84b2847b55527343f48601b62026601706fb08c7839c693c3c1a3c9ca824b5c7`).
A separate actual four-probe stage observation completed in10.808s under the
existing version2s/probe3s/total12s limits (private evidence SHA256
`fb43a11eecaeacc958c3cb4d137b28cba78921ff57a7430b7cb8f98c179babd8`).
These exploratory working-snapshot observations do not retroactively replace the
earlier ERROR or claim final exact-source qualification. No timeout was increased.

Independent review also demonstrated a modern fchmodat2 attempt returning an OS
read-only error, caught by a command that then emitted a false PASS under the
first denylist. Source bytes remained unchanged, but terminal-attempt accounting
was defective. Private reproduction SHA256
`cd0168b60766fc64c97cb16a8685ceef31b76874556c797637b8e7225f8dacdd`.
The preserved modern-mutator regression is followed by an explicit allowlist and
default-KILL syscall domain; no unsupported/future syscall is silently allowed.

The focused inventory is `tests_m7/test_validation_sandbox.py` (17 methods: the
original14, independently reproduced lost-stop and modern-mutator regressions,
and a cache freshness/uncertainty regression),
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

## Retained qualification status before final review

Clean candidate `c770f790dbf4b372153dd6ce4da61f322400d89c` completed its native
Python3.11.10 inventory: **16PASS/1SKIP of17**, aggregateFAIL, in257.123s.
Evidence SHA256 `59b714330913e4491d6099cb64b7bbb311b6f16cd4828459ad0c573b58d6b896`.
The accounting method's capability admission stopped at probe-network/ADPError,
before any of its product checks. That failed fixture's transient receipt was
cleaned by unittest, so the exact stop mismatch is UNKNOWN; no cause or PASS is
invented. The other actual OS/limit, alias, modern-mutator, lost-stop/interruption,
fork/network, resource, cache and independent-matrix methods passed.

Candidate [CI42668252955](https://github.com/oduwan/adp_codex/actions/runs/42668252955)
passed all210 accepted methods and clean installation6/6 on Python3.11/3.12.
Its Python3.11 M7 inventory observed5PASS/11SKIP/1ERROR of17 (private evidence
SHA256 `59d2819052b9668c5af04bd60f655665aae92099a4cff8b98d8d47d3882f12d5`);
the unsupported-runtime method errored. Python3.12's M7 runner errored on a
unittest fixture-lifecycle placeholder before a summary, so its original17 method
outcomes from that ephemeral private log remain UNKNOWN. The correction records actual
class/module fixture ERROR/SKIP separately, leaves unlaunched original methods
NOTRUN and forces aggregateFAIL. It rejects an ordinary test spoofing a lifecycle
ID. Three pure accounting tests are separately frozen in
`M7_ACCOUNTING_TEST_INVENTORY.json`; the original17 IDs remain unchanged.

Independent corrected-defect retest observed3/3PASS: typed unknown-stop
propagation, durable prelaunch marker/restarted-port refusal, and actual
fchmodat2+exit-zero terminal refusal with unchanged outside source. Private audit
SHA256 `51d587358a86699222f040bfc721cda92c3725757b14b3c0d2b8d4218b8a0d64`.
Independent narrow harness review approved3/3 pure tests, including the spoofed
ordinary-ID rejection; private log SHA256
`d91de3bdbf69ebfee651d6d4582d26d685ee24c8e412ee8b83aaef7f5947b6a1`.
These are scoped observations, not final acceptance of the whole issue.

The one authorized retained accounting discriminator on clean
`b1825d7b17b3126cfea1b10e5000dd300163a654` completed1/1PASS in58.898s with
unchanged budgets and assertions. Private log SHA256
`2da5c9c9217663ffe10ac1ecd14bbdb0823b68040021f2da86aab7a7c97b0dd6`.
Its disposable source/image and actual per-launch stop receipts are retained
outside Git. It narrows the accounting uncertainty without replacing the
earlier full17 result or claiming a final whole-suite PASS.

The qualification-only `ADP_M7_SANDBOX_EVIDENCE` option retains owned private
test fixtures/images/receipts outside source for the one bounded accounting
discriminator. The production port does not read this option. Runtime setup
failure emits only safe stage/binary-presence/error-type metadata; absent OS
capability never becomes a passing synthetic fixture. Final clean-source CI,
the bounded discriminator and independent exact-HEAD verdict/blocker are attached
to the Draft PR after this report commit; no future qualification is claimed here.

## Preserved final-review corrections

Independent exact-revision review of `aa227446126695c70eba4f773fcabbde3d001ba8`
returned CHANGES_REQUIRED: emitted CBPF allowed shared-file mmap and MADV_REMOVE,
contrary to the terminal mutation-attempt contract. Its controls confirmed private
anonymous mapping ALLOW, modern fchmodat2 KILL and unknown syscall KILL. Private
filter-domain proof SHA256
`e206a09966d81ff04a5a6e2da22fcbc7b45d1cc6ec65a452fb534e27a0eaff90`;
review packet SHA256
`7a513be1e7a17e4c658282376b030f2fd84a4bbec22063f5591ebcc3db5fc644`.
The actual end-to-end mapping discriminator was NOTRUN after a fresh
probe-network TimeoutExpired under the existing3s budget. No OS false PASS or
filesystem mutation is claimed; retained observation SHA256
`e35731c31d5f873c7c4ee13c5ac7ef688ce974d9887af073df0f4adaa9c3d8ba`.

The privately built official Python3.12.16 runtime initially produced a
134,952,451-byte image, rejected by the unchanged128MiB bound. An unused static
compilation archive alone contributed65,778,798bytes. This was a fixture closure
defect, not proof of unavailable kernel isolation. Admission FAIL SHA256
`6d061555739f1ed287d966b050a9c5219338bc0b09340c0bbb7d19b496b45437`.
The fixture now excludes compilation-only `config-*` directories while retaining
all required runtime modules; the production bound is unchanged. Official source
archive SHA256 `710c3e75dac8b2f258d9cd0f76e5c4c2e9175fac9e249c98901552f7cf33b7dd`;
private native binary SHA256
`49044f1960912bd14a167a805b39e3a88796ebf1636632db5a919c3cbd843cd7`.

Two pure regression methods failed before correction (nine failing subtest
assertions), private log SHA256
`5f4777b093a9f5f0b5040d9012af77220553dad0dfbfe206df59968af3dfaa50`.
They passed2/2 after the narrow filter/fixture correction on both native versions.
A separate frozen three-method security inventory adds those two pure methods
and an actual OS shared-mapping/removal refusal case. The original17 sandbox,
three accounting and210 accepted inventories remain unchanged. Final native
23-method campaigns, normal-push CI and fresh exact-HEAD review remain required.

The prior aa22744 CI3.12 run passed210/210 and installation6/6; M7 recorded
3PASS/17NOTRUN of20 with a separate class-fixture SKIP at policy admission
(binary present, ADPError). Evidence SHA256
`fa3d68fedb0be4a574dd075d13ecdb0aa39d3769d87a1237d14ca08c4e085d5e`.
That run exposed only one3.12 job despite the two-version matrix;3.11 inventory
is UNKNOWN, not inferred from earlier CI. Subsequent complete qualification and
review attestations belong to the exact final Draft PR revision.

## Final finite reassessment and retained campaign evidence

The clean `8aa900c1384b763104afd5c0d6c6b0363bd21787` native campaigns are
preserved in full, not replaced by later targeted proofs:

| Runtime | Original denominator | Observed outcomes | Aggregate | Suite SHA256 |
| --- | --- | --- | --- | --- |
| Python3.11.10 | 23 =17 sandbox+3 accounting+3 security | 22PASS/1SKIP | FAIL | `87b506cf011660b59420c3eba45ba85ebdc078b765cffa65d8c5669931ec06b9` |
| Python3.12.16 | Same23 | 21PASS/1FAIL/1ERROR | FAIL | `b9c20603c0576090e3c8663c09aca2c11ffcba965de72feb3ce528594532040d` |

The3.11 accounting admission timed out at probe-fork; retained receipts show
EXITED159, so no fork-denial failure is inferred. Exact timing cause remains
unclassified. The3.12 benign two-project check timed out under its original2s
budget. Neither observation authorizes increasing a limit or rerunning a full
campaign to erase the failure.

Independent review bound all three new mapping payloads to stopped=true,
EXITED159, zero stdout and unchanged tracked bytes at that revision (review
SHA256 `bebc32a01f4eb990e640ac86e7537ef2e5fe92a3410e66b1b92c10f94a42ee3e`).
Actual native images, standalone source fixtures and all89/97 per-launch stop
records remain private. Their integrity index SHA256 is
`2e42fa689098383b6d1a0dbe4cc50335bfe7cc033fc1f925914a58e999ede332`.
Representative observed digests, not portable authorization tokens:

| Runtime | Image digest | Policy digest |
| --- | --- | --- |
| 3.11 | `74c5c17357e61990acc13b9ed0265b501e7a1b7f27f5bcced52b5802d3ffe431` | `b5788bba3267f9ea749439cc41185e4a10c67b560bf88c4b8e62f262a654b162` |
| 3.12 | `e367ea5eaffe8fce3879f9a9078a3362053f4a3665465f8a740485098c644d59` | `05ab90812880a2dc16fb3c7194ec760576c70eedadf2df6836653b8bce1d42e9` |

The3.12 setsid case exposed a fourth candidate source defect: a confirmed SIGSYS
receipt was followed by another check because a parent read-deadline exception
took ordinary TIMEOUT precedence. Independent retained-receipt proof SHA256
`5e8b09489eb41e0218b6de32a201914843858fe0d684a04343cd9702294f0032`.
This is a source safety defect, not merely an unavailable host. The correction
prioritizes confirmed SIGSYS/unexpected/cancelled stops over observation deadlines;
remaining checks become NOTRUN. Genuine confirmed timeouts remain TIMEOUT and
missing stops remain UnconfirmedValidation with durable fencing. Original time
limits and assertions are unchanged. Nested subtest structure now prevents a
failed assertRaises from producing a collateral missing-exception AttributeError.
The failing deterministic stop regression is retained (log SHA256
`44e48ddccb2cdaa9f8358b727ce6c5e64c293f95c202d9ac366c46f4484d0856`).

One bounded owned ELF discriminator proved a fixture loader-closure defect:
the original executable with literal `$ORIGIN/../lib` RUNPATH exited0, but the
relocated image executable exited127 because its unique libpython SONAME was
copied only at the original absolute prefix. Before proof SHA256
`c7152508c6118c874a8d17933ce31b2c4244cb187d0d0200df100eb18f16077a`.
Copying that trusted library into the dedicated `/runtime/lib` closure made the
same retained executable exit0 with a minimal environment; after proof SHA256
`aaccb0d3b5e86d54ed6b87deed6570509e67d560027ba08b279b2b34991bfeaf`.
No namespace, product, network or model was involved in that loader proof.

One owned false-backend alias discriminator showed constructor refusal for a
symlink and success for an identical regular copy, before any probe/product
execution (proof SHA256
`9258a2b14be1cb905c560c9165416ec800ea846ff6e6a7f98f5df6e3aff2514c`).
The negative fixture now uses an owned regular copy, and only the trusted test
policy helper normalizes its explicit binary path. Production symlink refusal
is preserved. These proved fixture defects do not establish the exact cause of
the previous CI errors; their historical cause remains UNKNOWN.

[CI42673351397](https://github.com/oduwan/adp_codex/actions/runs/42673351397)
tested merge revision `17a943a09fb0016659aa863dd7098a37bc82e49b` for8aa900c.
Both Python3.11.18/3.12.16 passed all210 accepted methods and installation6/6;
both M7 inventories observed10PASS/12SKIP/1ERROR of23, aggregateFAIL. The negative
false-backend case errored;12 actual-OS methods skipped. The raw private CI test
tracebacks were ephemeral, so no kernel/loader-specific cause is invented.
CI suite evidence hashes are respectively
`1b1f2a7b618894ccc1dba06ad3c2596145d87df83c2ecd7fdc674392da45ea49`
and `aebfd0fa0a285ef20a8069c1493b6966de872bb522f44b0101f100bf969ce7db`.

Four separately frozen recovery/fixture methods bring the additive inventory to
27, preserving all original23 IDs and accepted210 bytes. Final verification is
bounded to corrected deterministic lifecycle/fixture checks on each native
Python version, one normal-push both-version full CI campaign and independent
exact-final-HEAD review. No additional full native WSL campaign is scheduled to
erase the known failures. Qualification cannot PASS while required actual OS
coverage is unavailable/incomplete; persistent non-PASS stops at
BLOCKED_RUNTIME_QUALIFICATION pending a stable qualified Linux host and pinned
runtime closure. Safe CI admission metadata exposes only stage/type/version,
policy digest and observed stop status/exit, never raw transcripts or credentials.
