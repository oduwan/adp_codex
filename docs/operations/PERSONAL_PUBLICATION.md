# Personal feature publication — M10-A

Issue #40 connects one exact-SHA reviewed personal local draft to the accepted
M7 object uploader and GraphQL expected-old-SHA CAS. It does not create a PR,
merge, report, accept a product or advance another issue. Those remain separate
dependent slices. Genuine GitHub/Codex M8 qualification is NOTRUN here.

The separate [M10-B product path](PERSONAL_PRODUCT.md) now proposes Draft PRs,
observes native project CI and gates a separately approved merge. Its corrected
SHA publication uses an append-only revision selection of this same publisher;
the original receipt and all counters remain intact. None of those additional
rights follows from the original #40 publication approval.

## Feasibility and explicitly approved security envelope

Accepted source was `df2d19baa8407c637b3257c4ef1780102e7fdcf9`. Its postmerge
Python 3.11/3.12 [CI](https://github.com/oduwan/adp_codex/actions/runs/45043376634)
passed the 210 core and 297 additive cases and six-case installation summaries.
The native engineering dependencies are #41 BLOCKED_BY #40 and #42 BLOCKED_BY #41;
their exact GitHub readbacks are retained privately. Dependent engineering work
still requires its predecessor on accepted main; code qualification is no merge
or M8 execution authority.

The accepted [M7 network contract](NETWORK_CAS.md) describes the reusable ports:

- `GitHubTarget` pins opaque memory identity, immutable GitHub node/database IDs,
  owner/name, one ref and its HTTPS endpoint fingerprint.
- `network_objects.closure` preflights the complete bounded missing object closure.
  `GitHubCAS.upload` preserves exact blob/tree/commit OIDs through Git Data POSTs.
- `GitHubCAS.cas` uses the immutable node ID, exact `beforeOid` (zero for verified
  absence), one desired OID and `force=false`. Plain Git push, force/lease, REST
  fast-forward updates, replacement commits and staging refs are not substitutes.
- `GitHubGitExecutionPort` requires an actual canonical M5 task/action, private
  exclusive claim, one in-process dispatch capability and durable SUBMITTED state.
  It checks actual M1 ownership, M2 and M3 before execution and again after uploads.
  Reconstructed actions cannot acquire a new dispatch capability.
- The supervised fixed-origin HTTP primitive retains request bounds and confirmed
  stop fencing. Unknown process stop blocks subsequent requests and handoff.

The signed transport still requires independently authenticated, single-repository
App issuance. Its confinement is important: the accepted M7 report records seven
objects reaching a replacement repository during owner/name reuse before a later
CAS identity rejection. Final ref CAS cannot undo that object disclosure.

Ordinary `gh auth` does not establish that token confinement. The pinned official
[REST specification](https://github.com/github/rest-api-description/blob/c9c95fe34ced05fe076001f5c55704742bc8e7f8/descriptions/api.github.com/api.github.com.json)
lists owner/name Git object POSTs and no `/repositories/*` route. Its SHA256 is
`6d9bbb20d8865b01464028937f2403954ad46598b4ebd3513dcb1a15b1a84aa7`.
This describes documented routes; it does not prove no undocumented route exists.
No immutable-ID upload alternative was qualified. A token prefix, permissions
label, settings screenshot or publication approval alone cannot authenticate a
fine-grained token's exact current selection.

The operator therefore explicitly approved this **personal-only** assumption:

> No repository rename, transfer, name reuse or credential-scope changes during
> the finite publication window.

Every publication approval visibly warrants that assumption again. This mode
does not claim signed-mode server confinement. If the guarantee is violated,
checks may detect drift and stop, but cannot prevent every object disclosure
before that detection. Current account, repository/default branch, permissions,
governance, native protections and expected ref are still checked; 403/UNKNOWN
never becomes absence. Policy observations are fresh observations, not an atomic
lock on every GitHub administrative setting. The signed mode and its stronger
wrong-repository negative controls remain unchanged.

## GitHub Free private repository rules availability (#46)

Personal inspection distinguishes `OBSERVED`, `PLAN_UNAVAILABLE` and `UNKNOWN`.
Only the exact GitHub.com HTTP 403 message
`Upgrade to GitHub Pro or make this repository public to enable this feature.`,
the endpoint-specific official documentation URL and string status `403` qualify.
The bounded closed JSON must have valid, unambiguous JSON/control headers and
no rate-limit, redirect or pagination indication. Other error bodies are discarded.
Signed-provider enrollment and transport retain their default behavior.

The fallback requires fresh personally owned private repository identity, matching
account/node/database IDs and current read/push/admin access. Publication observes
the default and exact feature refs with an independent limited GraphQL query;
GraphQL errors still block. Supported branch flags must be `protected=false`,
and REST commit IDs must agree with GraphQL. An absent feature requires observed
GraphQL absence, never a 404. Classic protection must independently return the
same precisely recognized plan limitation; ordinary permission failure blocks.
For an absent feature, the existing default branch supplies that repository-level
classic capability witness; it does not prove absent feature protection. An
existing feature requires its own classic-plan witness.
The canonical `classic_scope=REPOSITORY_PRIVATE_PLAN` records this permitted
witness scope, not a claim that feature-classic absence was observed.

The exact proposal carries `plan_policy` and a distinct operator warrant.
To approve that proposal, add `--accept-plan-unavailable` to the existing
`personal publish` (or `codex publish --personal`) command. This separate assent
waives no project requirement. Both upload/CAS boundaries reobserve the capability,
ownership, permission and protection state. Changed entitlement (including 403 to
200), owner, ref, protection or credential invalidates the approval.

`PLAN_UNAVAILABLE` is never `OBSERVED_EMPTY` or independently verified protection
absence. Its M3 reference is `personal:operator-plan-disabled-feature-policy`;
`known` denotes the current operator-approved operational envelope, not absent
native rules. Check requirements remain UNKNOWN unless actually prescribed or
selected; an unenforced workflow is not automatically required. Existing UNKNOWN
enrollments/receipts are immutable and need explicit operator disposition if fresh
facts differ; reads never migrate or reset them. Original M1/M2, independent
exact-SHA review, 45-second/128-request dispatch and uncertainty recovery remain.

This compatibility repair is qualified with synthetic responses only. Genuine
M8 remains NOTRUN; it authorizes no managed upgrade, pilot action or release.

## Operator flow

Use the managed launcher and the original private enrollment directory, after a
genuine independently reviewed local draft. Both command families share the same
protocol; Codex commands require explicit `--personal`:

```sh
adp personal publication-preview --repo /owned/project --remote origin --directory PRIVATE_DIRECTORY
adp codex publication-preview --personal --repo /owned/project --remote origin --directory PRIVATE_DIRECTORY
```

Read the exact original ticket and all current committed project governance.
The proposal identifies the repository/account/issue, exact source SHA and tree,
independent code-review reference digest, feature ref, expected old SHA or verified
absence, observed checks, native constraints, private-state checkpoint/generation,
credential provenance, effect, warrant and expiry. A selected ref must be
nondefault and supported by the actual project rules. No required check is invented.
An unmet or unrepresentable prepublication condition blocks approval; an operator
confirmation is not permission to waive project governance.

Setup or run consent does not authorize publication. After the operator separately
confirms the exact proposal, project-policy assent and quiescence warrant:

```sh
adp personal publish --repo /owned/project --remote origin --directory PRIVATE_DIRECTORY \
  --reviewed EXACT_PUBLICATION_APPROVAL --authorize-publication \
  --assume-administrative-quiescence --confirm-project-publication-rules
```

The proposal lasts at most 300 seconds and never extends the original personal
window. The original 45-second/128-request network dispatch, five-second request
limit and bounded stop allowances remain. M1/M2 ownership, thresholds and all
previous counters are preserved. This slice supports one publication intent;
unknown or changed evidence cannot silently create another window or intent.

Full native discovery validates admission before dispatch. Transparent digests of
the exact selected-ticket responses validated there are bound into consent.
Dispatch reobserves that ticket, comments, timeline, blocking and sub-issue
relationships with complete M4 pagination and before/after detail stability.
Every digest must match; unchanged timestamps alone are insufficient. It also
rechecks the original checkout/governance/rules, actual ownership/guard/review,
credentials and exact feature ref. Unrelated whole-track inventories are not
repeated inside each upload boundary. These REST observations do not create an
atomic lock on issue edits.

Full genuine original/code review verification seals the same canonical accepted
assignments, review guards and source/epoch before and after that verification.
Every immutable-object request rechecks those seals plus current source/tree/ref,
worker records, credentials, ownership, consent and the active publication permit.
Full runtime/role review is repeated at both batch boundaries before CAS; it is
not recursively repeated for every object. Revocation of either original-scope
or code approval stops the next object, without extending dispatch deadlines.

Read-only preflight and settlement each have a finite observation bound. The
accepted M7 port owns its unchanged dispatch bound; a restored expired preflight
context cannot be mistaken for the settlement window. Settlement has no mutation
capability and never renews the original M2 permit or publication consent. Any
terminal guard outcome is still accounted and exposed.

Project governance is interpreted through explicit operator assent to the exact
observed bytes and operation; it is not inferred from authentication or issue
prose. Actual M3 still decides the effect. Native protection must be positively
observed, and currently constrained/protected or inaccessible refs remain
unsupported by the accepted M7 envelope. Restore the required GitHub metadata
access or choose a genuinely supported feature ref; do not fabricate empty rules.

## Credential and process boundary

Personal publication reads the stored `gh auth token --hostname github.com --no-refresh` under
the same normal, nonprivileged Linux operator account. Direct credential/host/repo
environment overrides are excluded; there is no App issuer, credential refresh,
manual JSON, shell script, arbitrary issue command or token passed through argv.
The executable, configuration, UID/PID namespace and keyring context are bound.
Every executable/configuration ancestor is pinned and must be root/operator-owned
without group/other write access. Shared writable installations are unsupported.
The selected CLI must support the documented
[`--no-refresh`](https://cli.github.com/manual/gh_auth_token) option; an unsupported
option or expired credential fails closed without a refresh or legacy fallback.
Setuid/setgid executables, file capabilities and unqualified capability inspection
are refused. Normal session keyring settings are available only to the credential
child, not workers or the HTTP child.

The actual selected CLI version and executable hash are observed. A minimal
supervised credential child returns the secret through a private pipe, and the
fixed `api.github.com:443` HTTP child receives it through private stdin. Redirects,
proxy/helper fallback and unbounded replies are refused. Original M4 status and
header processing, including benign repeated/empty headers and strict control
headers, is preserved. Credentials, raw errors and private configuration never
enter worker prompts, portable memory, product source or GitHub comments.

## Outcomes, restart and qualification

The coordinator persists exact consent, a real canonical task/action, actual M2
reservation and the M7 exclusive one-use claim before submission. Exact native
ref reobservation is necessary for `PUBLISHED_UNACCEPTED`. No PR/check PASS,
product DONE, merge or successor readiness is inferred.

The old code Reviewer attested code, not a later publication observation. The
new action therefore records honest native effect presence without inventing a
new independent M2 progress claim or clearing acceptance criteria. A terminal M2
result is exposed as `PUBLISHED_GUARD_STOPPED` while preserving the observed ref.

```sh
adp personal publication-status --repo /owned/project --remote origin --directory PRIVATE_DIRECTORY
```

Status reobserves the exact ref without a new write. Recovered PREPARED/SUBMITTED
actions can only be observed; absence or a missing claim never authorizes replay.
Lost responses can reconcile only to the exact intended state with confirmed stop.
Missing private history, changed source/owner, expired consent, uncertain delivery
or exhausted M2 requires the retained disposition, not reset. Handoff requires
confirmed stopped processes and reconciled effects; safe release does not erase a
terminal guard result.

The accepted narrow object envelope remains SHA1, supported unsigned UTF-8/UTC
commits and bounded representable objects. Unsupported forms are not rewritten.
The local draft must originally be committed in UTC (for example, run its
approved local execution under `TZ=UTC`). A preexisting non-UTC or signed commit
is unsupported by this backend; publication must not rewrite it or reuse its
review for a different commit. The focused UTC fixture and the accepted non-UTC
negative controls exercise those distinct outcomes.
Tests use disposable local stores and explicitly synthetic API/worker records.
The original focused and additional security inventories are separate; historical
failures and independent findings remain retained. Exact final SHA, Python
3.11/3.12 results, CI and independent review are reported in the Issue/Draft PR.
Neither this document nor synthetic PASS is genuine M8 runtime qualification.
