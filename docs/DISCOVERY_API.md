# Read-only GitHub discovery and dependency planning

Issue #4 provides the accepted Python 3.11+ implementation for observation and
planning (PR #10). M1 memory, M2 Progress Guard and M3 policy decisions are accepted through
PRs #7–#9. No worker, Conductor, mutation executor or execution authorization is
added. The implementation uses the standard library only.

## Commands and output

```bash
# Explicitly select a GitHub remote. The token is read from the named environment
# variable, never a command-line value or repository document.
adp discover --repo ./project --remote team --token-env GH_TOKEN
adp plan --repo ./project --remote team --token-env GH_TOKEN

# Read an existing frozen discovery JSON file without Git or network access.
adp plan --snapshot inventory.json

# Reconcile against an existing preview, writing only JSON to stdout.
adp discover --repo ./project --remote team --refresh --previous prior-track.json
adp refresh --repo ./project --remote team --previous prior-track.json
```

`discover` emits a closed version-1 `DISCOVERY` snapshot. `plan`, `refresh` and
`discover --refresh` emit a version-1 `TRACK` with `mode=READ_ONLY` and
`execution_authority=UNKNOWN`. `--snapshot` is repeatable for explicitly selected
repositories. `--github-id` pins the stable REST repository ID; the adapter also
pins and rechecks the identity within each observation. Local selection uses M1
`Config` and refuses ambiguous remotes or an endpoint inconsistent with the
requested GitHub repository. It never assumes a remote or branch name.

There is no `--save`, automatic checkpoint, agent launch, comment, label, Issue,
PR or Git write. Paths passed as inputs must be bounded regular files without
symlinks. Output is local stdout; callers must protect private issue contents and
must not publish snapshots in public diagnostics. Normal Python installation and
import caching are outside target-repository operations; use Python's `-B` or
`PYTHONDONTWRITEBYTECODE=1` when inspecting a Python source installation itself.

Exit 0 means a preview was generated, not that tasks passed acceptance or may
execute. Incomplete inventories and UNKNOWN candidates return 4 while preserving
the available preview, including an incomplete inventory with zero candidates.
Invalid schemas, unresolvable repository identity and
unsafe inputs return a controlled ADP refusal. NEEDS_SPEC, BLOCKED_DEPENDENCY and
BLOCKED_OPERATOR remain explicit classifications, never successful product work.

## Observation ports

```python
from adp.discovery import DependencyPlanner, MemoryProgressAdapter, review_subject
from adp.discovery_github import GitHubDiscoveryAdapter, GitHubHTTPTransport, FixtureTransport
from adp.discovery_types import DiscoveryAdapter, ReadinessAuthority

# Token comes from the caller's authenticated secret provider.
adapter = GitHubDiscoveryAdapter("team/product", GitHubHTTPTransport(token),
                                 expected_id="stable-rest-repository-id")
snapshot = adapter.discover()
track = DependencyPlanner().plan((snapshot,))
```

`ReadOnlyTransport.get(path) -> Response` is the only transport method. The live
transport constructs fixed-origin `https://api.github.com` GETs, sends a bearer
token, rejects redirects and caps response size/time. It never uses a shell,
executes repository code or follows URLs extracted from issues. Local Git calls
only read selected configuration, endpoint, symbolic HEAD and SHA.

`FixtureTransport` supplies explicit response objects and optional bounded
response sequences. Missing entries are unknown observations, not empty-success
defaults. `--api-fixture fixture.json` uses the same adapter without networking;
its closed schema is `{schema_version: 1, responses: {path: response}}`, where a
response has exactly `status`, `body` and `headers` (a name/value object). A path
may instead contain a nonempty response list for drift/pagination fixtures.
Fixtures grant no trust or operation rights.

The adapter observes:

- Repository identity, all-state issue and PR inventories, and current PR details.
- Per-issue comments, timeline PR cross-references, native `blocked_by`
  dependencies and native sub-issues, each with independent pagination coverage.
- Semantic issue revision hashes and updated timestamps; PR source/base refs,
  exact HEADs, fork repository IDs, draft state and merge observations.
- Duplicate timeline history and tentative duplicate/superseded textual links.

Inventory membership/revisions and repository/local context are checked again
before emitting the snapshot. List/detail incidental representation differences
do not count as issue edits. PR HEAD drift, inaccessible or deleted forks,
malformed records, overlapping pages and changing inventory remain explicit.
REST observations are not an atomic transaction. A later executor must refresh
and revalidate all affected refs and authority immediately before an action.

Each coverage record carries status, source endpoint, observed-data digest,
page count, reason and any retry delay. No rate-limit error is retried silently.
401/403/429 and exhausted rate budget contain further requests; reset/retry
headers are reported without sleeping or escalating permissions. Pagination
follows only validated, sequential same-endpoint links or explicitly constructed
next page numbers. A full terminal page is checked with another page rather than
assuming it is complete. Bounds stop collection with PARTIAL/NOTRUN coverage.

Unsupported native endpoints, including 404, mean UNKNOWN. They never prove an
issue has no prerequisites. A repository identity failure refuses discovery
instead of inventing a repository or returning an apparently complete empty list.

## Identity, graph and readiness

`Identity` includes forge, stable repository ID and opaque issue/PR object ID.
Display numbers and mutable repository names are navigation fields. Hashing a
structured identity avoids concatenation, cross-repository and path collisions.
Native targets resolve only against explicit selected snapshots and matching
provider object IDs. External/missing targets stay unresolved; discovery does
not silently traverse private repositories or expand its selected scope.

Native blocking edges enter the prerequisite graph. Sub-issues are authoritative
hierarchy observations, not invented execution dependencies; an independent
scope assessment must distinguish parent work from child work. Ordinary prose
mentions remain RELATED. `depends on`, `blocked by`, `requires`, `duplicate of`
and `superseded by` references are INFERRED and need independent confirmation or
dismissal. Marking text as imperative, trusted, READY or PASS grants nothing.
Timeline PR cross-references prove a link, not that the PR implements the task.

The planner retains all confirmed graph edges, finds strongly connected
components including self-cycles, and produces a stable prerequisite-first order.
Cycle members and their dependants remain unordered with explicit diagnostics;
no edge is removed to manufacture a DAG. Missing prerequisites and confirmed
duplicates are blocked. Identical titles are flagged for scope assessment;
title equality alone does not establish a canonical duplicate.

| Status | Required interpretation |
| --- | --- |
| READY | Current independent bounded specification, known external policy, complete observations and DONE prerequisites |
| IN_PROGRESS | Current explicitly mapped M1 assignment or independently confirmed linked open PR at the observed SHA |
| BLOCKED_DEPENDENCY | Confirmed unresolved/missing prerequisite, cycle or canonical duplicate |
| NEEDS_SPEC | Missing/ambiguous independent scope or acceptance, unresolved tentative dependencies or scope conflicts |
| BLOCKED_OPERATOR | Missing/denied external policy knowledge or required operator decision |
| DONE | Current independently verified completed product disposition; closure or merged PR alone is insufficient |
| UNKNOWN | Incomplete, inaccessible, stale, changed or contradictory observations |

`ReadinessReview` carries actual externally accepted scope/acceptance, policy
references, optional confirmed dependencies/canonical task/current PRs,
disposition, conflicts and freshness. `ReadinessAuthority.verify` must authenticate
the independent canonical reviewer, role, provenance and exact
`discovery/readiness` subject. The issue/comment authors cannot self-approve.
`review_subject` binds the entire selected snapshot set and review payload.
It is separate from M2/M3 purpose domains. Receipts expire after at most one hour;
changed issue bodies, links, PR HEADs or repository contexts invalidate them.
Claims read from a JSON file are not independently verified by their presence.

The CLI intentionally exposes no self-asserted approval switch. Without a trusted
assessment extension it emits NEEDS_SPEC/BLOCKED/UNKNOWN, not fabricated READY or
DONE. An API caller supplies an observational authenticated verifier and real
project contract evidence; no special issue template is required. Policy references
establish planning knowledge only. M3 remains the authority for every proposed
Git operation, and M1/M2 ownership, guards and independent code approval remain
mandatory at accepted M5 execution admission.

## Refresh and accepted memory compatibility

`plan(..., previous=track)` reconciles by provider identity, not titles/numbers.
Missing issues remain UNKNOWN candidates with their earlier evidence. PR drift
retains prior HEAD history and forces reassessment; changed issue observations
retain digest references. Reviews and exact M1 task records are retained without
relabeling outcomes. Old reviews can qualify only if the verifier confirms the
unchanged current context and freshness. A saved status is never current authority.
Every candidate retains its source repository descriptor so semantic issue schema
validation still applies after that repository is removed from a refresh.

`MemoryProgressAdapter(memory, bindings)` calls only accepted `Memory.inspect()`
and schema validation. Explicit `MemoryBinding(identity, task_id)` maps provider
IDs to opaque M1 task IDs; the snapshot's `memory_id` must match. It preserves
task iteration, exact source, live assignments, accepted outcomes and evidence
as canonical task JSON plus checkpoint/generation. Current memory must be synced.
Stale assignments and previously live assignments without a new M1 observation
block new work; accepted PASS/FAIL/ERROR/SKIP/UNKNOWN outcomes remain unchanged.
There is no implicit memory initialization, fetch, recovery, upgrade or write.

CLI memory reconciliation is opt-in with the accepted `--memory-branch`,
`--storage` and `--memory-bindings` input. That file has exactly `schema_version: 1`
and `bindings`, an array of `{identity: {repository_id, issue_id, forge}, task_id}`.
M1 state/task versions, M2 guard schemas/counters/migration and M3 plans are unchanged.

## Bounds, qualification and remaining limits

There are at most 16 selected repositories and 256 combined proposed tasks,
256 issues/PRs per inventory, 20 pages per endpoint, 2048 total requests,
100 items per page, 1 MiB per API response, 30 seconds per HTTP request and
16 MiB per normalized snapshot/track. Untrusted text is limited to 64 KiB per
body. Native relationships/comments are bounded at 256 per issue. Each candidate
retains at most eight progress records, eight reviews, eight issue observation
digests and 64 PR HEAD observations. Capacity exhaustion refuses rather than
discarding accepted evidence. No unbounded diagnostic log is stored.

Qualification uses synthetic API responses and disposable Git remotes/worktrees.
It exercises pagination, rate/permission failures, native versus inferred edges,
cycles, duplicates, identity collisions, issue/PR drift, exact review replay,
malicious text, deterministic ordering and strict file/ref preservation. Live
GitHub calls, real private data and production mutations are not test prerequisites.
The first adapter targets github.com REST; Enterprise hosts, GraphQL, automatic
prose acceptance, cross-repository crawling and persistent track saving are out
of scope. Trusted transport/verifier/clock and local administration are explicit
boundaries. M5 execution and all product writes remain separately admitted work.

API references: [issue dependencies](https://docs.github.com/en/rest/issues/issue-dependencies),
[sub-issues](https://docs.github.com/en/rest/issues/sub-issues),
[timeline events](https://docs.github.com/en/rest/using-the-rest-api/issue-event-types),
[rate-limit handling](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api).
