# Stopped personal NOTRUN accounting and archival proposals

Issue #50 supplies a narrow personal Worker → M1 outcome bridge and a read-only
proposal for one original expired precommit Developer attempt. It supplies no
archival writer, new execution window, worker retry or product acceptance.
Actual historical state must remain untouched until separate operator authority
and a qualified exact-subject archival mutator exist.

## Result boundary and ordinary live accounting

WorkerResult and M2 admit NOTRUN; M1 deliberately accepts only PASS, FAIL, ERROR,
SKIP and UNKNOWN. A valid stopped, unapproved, empty-criteria personal NOTRUN is
delivered to M1 as UNKNOWN, with a fixed summary identifying the original NOTRUN
and the same runtime receipt. The raw worker observation, runtime record and stop
receipt retain NOTRUN. M2 observes the original NOTRUN during ordinary live
accounting. This verifies no criterion and supplies no review or product PASS.
Other outcomes are not coerced; in particular this is not a general TIMEOUT
normalizer. The signed Conductor's existing delivery policy is unchanged.

Before a new NOTRUN delivery, the personal path rechecks the original unexpired
window, exact assignment/generation, retained source/admin/outside seals, and
matching live reservation. An already consumed exact NOTRUN observation can only
reconcile its matching accepted M1 result; its forensic/terminal severity is not
reopened. Exact accepted leftover inbox files use existing M1 cleanup. Changed
or duplicate-conflicting results refuse. A clock crossing during canonical
publication still uses the actual current M2 clock and retains its unsafe stop;
there is no backdating or cross-checkpoint atomicity claim.

## Static feasibility and timing limits

Existing `ProgressGuard.abandon()` at a time after the original reservation
deadline records UNKNOWN and irreversibly latches STOP_UNSAFE. That is the only
supported terminal archival policy proposed here: the **reservation/accounting
window** was missed. It does not independently prove that the worker process
exceeded its execution deadline. The operator must explicitly acknowledge this
exact severity and meaning before any future archival mutation.

The existing runtime/stop schemas have no absolute completion timestamp. An EXITED,
CLI-zero, stopped receipt cannot reconstruct UTC stop time from elapsed duration,
file mtime or the request deadline. The proposal therefore keeps historical
execution timeliness UNKNOWN. Separately retained operator timing observations
remain attributed evidence, not synthesized receipt fields. Ordinary observation
while the trusted current clock is still within the original reservation is
qualified separately from post-expiry archival.

A neutral/non-unsafe terminal disposition, clearing a permit while retaining
normal mode, or resuming the expired window cannot be obtained through current
M2 policy. Such a requirement is `BLOCKED_OPERATOR_DESIGN_DECISION`; neither an
issue description nor a fresh execution approval can silently override it.

## Read-only operator interface

After separately authorized integration, and only with authority to read the
selected original private state, an operator may generate a local proposal:

```sh
adp personal archive-preview --repo OWNED_SOURCE --remote SELECTED_REMOTE \
  --directory ORIGINAL_PRIVATE_DIRECTORY --request ORIGINAL_REQUEST_ID
# The same read-only protocol is exposed by:
adp codex archive-preview --personal --repo OWNED_SOURCE --remote SELECTED_REMOTE \
  --directory ORIGINAL_PRIVATE_DIRECTORY --request ORIGINAL_REQUEST_ID
```

The supported case is the original isolated first Developer, STOPPED/NOTRUN with
no approval/criteria, pending M1 assignment and initially empty inbox; the original
scope Reviewer is already accepted. The original normal, unbounded M2 reservation
is expired, with no last observation, counters, forensic history or campaign.
The personal window has expired, source is still at the original base, and only
the already observed feature preparation exists. Unknown variants refuse rather
than acquiring a new request, task, owner or history.

The reader validates the current supported runtime host, protected raw runtime and
separate supervisor stop files, exact request/result/receipt/assignment/source/
generation/iteration/incarnation/permit bindings, original scope evidence, full
feature/outside and outer source seals, Git administration/ref/index bindings,
canonical synchronization and current local ownership. Both predicted canonical
bundles must satisfy the existing schemas and 64 KiB bounds. Fresh reobservation
detects changes during inspection. Missing or malformed evidence is UNKNOWN.

The response is `ARCHIVAL_PROPOSAL_ONLY`, `execution_authority=NOT_DELEGATED`,
`apply=UNSUPPORTED_READ_ONLY_INTERFACE`, and `product_acceptance=NOT_ACCEPTED`.
Its reference is a hash binding, **not** an approval token. No Codex capability
probe, credential lookup, network GitHub request, process launch/cancellation,
lock creation, inbox write, checkpoint recovery or other mutation occurs.
Exit zero means a read-only proposal was produced. Keep this local operator
evidence private outside Git; do not publish raw receipts, host fingerprints or
worker content in product comments.

## Proposed separately authorized sequence and interruption states

This is a design for a future separately authorized application, not a command
implemented by this repair:

1. Obtain exact operator approval of the original immutable request, NOTRUN and
   supervisor evidence, full source/admin/outside seals, owner/generation, source,
   assignment, checkpoint, active permit, original deadlines, and all budgets.
   Retain that full immutable private intent before canonical mutation.
2. Revalidate the approved baseline/permit **inside** the existing M1 mutation
   lock. Current public `abandon()` does not accept that precondition; the future
   qualified mutator needs a narrow in-lock expected-subject fence. A preflight
   hash or the invocation lock alone is insufficient. Do not nest public calls
   inside another `storage.locked` descriptor: its flock is not reentrant.
3. At the actual current time, use existing guard abandonment **first** with the
   exact `abandon_evidence_reference` shown in the proposal (the original runtime
   receipt). This leaves UNKNOWN/STOP_UNSAFE, unchanged unresolved criteria, and
   normal accounting increments. No reset, new progress or on-time result occurs.
   Keep the richer archival intent separately; substituting its reference for
   the proposed runtime reference changes the predicted observation.
4. Verify the exact guard-only canonical checkpoint and confirmed CAS publication.
   Then deliver/accept only the same original assignment as M1 UNKNOWN, or observe
   its byte-equivalent durable delivery. Do not blindly repeat uncertain effects.
5. Verify the final canonical checkpoint; clean only identical accepted inbox
   residue through existing M1 cleanup. Retain original private worker/run records,
   receipts, refs, deadlines, source seals, generation and budgets. Do not call
   ordinary expired `resume`, mark the product accepted, or admit another Issue.

The proposal can reobserve this exact predicted sequence with the original
`--checkpoint` and `--expected-proposal` reference. It recognizes guard-only,
matching pending delivery, accepted-before-cleanup, and terminal-UNKNOWN states.
It verifies linear parents and the intermediate guard-only checkpoint, rather
than inferring order from a final tree. M1-first history, changed evidence, a
different permit, unrelated checkpoints or lost authority remain blocked.
Pending/dirty canonical journals require existing explicit M1 recovery; a preview
never performs recovery or declares an unpublished effect successful. Observing
the terminal state does not itself prove separate operator authorization.

## Eventual source reuse and remaining operator decisions

The original Issue remains NOT_ACCEPTED and successors remain blocked. A terminal
guard and the same-Issue enrollment marker have no reset/renewal API. A future
distinct finite plan therefore requires a separate operator design decision;
this repair neither implements nor authorizes it. Retained admitted files may
be considered **unaccepted candidate input** under that future plan, bound to the
old base/full source seal and original NOTRUN evidence. Any adoption needs fresh
scope/authority, genuine independent review and actual project checks at its
new committed SHA. It cannot treat the old files as approved work, erase the
old attempt, alias its requirement to replenish counters or silently reset budgets.

Qualification here uses synthetic receipts and owned disposable Git only. It
does not contact or reconcile the real M8 pilot. Genuine M8 acceptance and an
actual separately authorized archival application remain NOTRUN.

The later operator-approved continuation is documented separately in
[ACCOUNTING_EXPIRY_CONTINUATION](PERSONAL_RECOVERY.md). It adds new explicit
guard/result/episode/candidate approval verbs while retaining this original
read-only proposal and NOTRUN→UNKNOWN bridge unchanged. This historical repair's
qualification and limitations are not retroactively upgraded to live recovery
or genuine M8 success.
