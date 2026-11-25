# D4 bounded deletions and complexity stop

Issue #57 follows independently reviewed #54–#56, stacked on frozen PR #52.
This is a partial engineering handback, **BLOCKED_COMPLEXITY**, not completed
legacy cutover, qualification, migration or release authority. The exact HEAD,
tree, focused results and private evidence hashes belong in the Draft PR and
Issue report after final review. Main and PR #52 are unchanged.

## Actual replacements

| Before | After | Retained boundary |
| --- | --- | --- |
| Product-history `_FACTS`, `_commit`, `_witness` and warm commit/index inference | Original native `observe`, then stateless actual bounded commit/tree/blob byte verification | Per-command physical Git pinning, current HEAD/ref, opening/closing context, hash integrity, original unsupported-envelope native behavior |
| Two archive worker/stop parsing bodies | Existing `retained` reader, exact archive proof digest, distinct contexts and measurements | Actual protected runtime/stop files, host, request, stopped status, raw NOTRUN and original counters |
| Overlapping H2/H3 and H0/H1/H2 capture operands replayed per POST | Pure same-observation union, separately for each store | Identical full context, conflicting OID/type/size refusal, actual bytes on every use; existing 32-object groups retained when union exceeds that bound |

No new historical identity, store, ref, journal, registry, authority, process or
positive cache is introduced. `_WITNESSES` was already removed and credited in
D2; it is not counted as another deletion here. Entry and independent closing
captures are never combined. The short write fence still checks actual context
before and after actual object bytes and makes one late actual Memory read.

The native Product-history reader deliberately does more work than a warm
positive cache. Its old warm-cache spawn comparison is retired with that cache,
not reported as a newly passing performance requirement. Its security and
filesystem/ref preservation assertions remain in the named stateless replacement
test. The old inventory count is preserved one-for-one; a new context-race test
and a separate witness-union test are additive. The original inventory/revision
remains in frozen history. Unsupported closing contexts refuse rather than
falling back after a supported observation has begun.

The two authorized historical fixture corrections use a real configured
GitHubCAS receiver for the read-barrier test and the effective positive remaining
request cap (at most the centralized default 10), replacing an obsolete exact30
expectation. Route/header/body/credential/redirect/paging and read-barrier
assertions remain. Earlier errors are historical nonpasses, never relabeled.
The Product read barrier again precedes its temporary accounting-writer gate.

## Measured source gate

Same counting rule as [the frozen baseline](GIT_NATIVE_BASELINE.json): physical
split lines, nonblank/noncomment code including docstrings, and static AST nodes
over all tracked `adp/*.py`. No import or product execution is used for counts.

| Measure | Frozen13fd | Reviewed D3 | Bounded D4 | Whole-track delta |
| --- | ---: | ---: | ---: | ---: |
| Modules | 100 | 100 | 100 | 0 |
| Physical lines | 26210 | 26504 | 26465 | +255 |
| Code lines | 23499 | 23782 | 23748 | +249 |
| Function nodes | 1240 | 1246 | 1245 | +5 |
| Class nodes | 249 | 249 | 249 | 0 |
| AST statements | 19325 | 19537 | 19503 | +178 |

These deletions reduce D3 by39 physical/34 code lines and one function, but do
**not** meet D1/D4's actual net-negative product-source gate. At least256 more
physical/250 more code lines must be removed **plus every still-needed writer
cutover addition**. Source counts are demonstrated; estimates below are not.

Independent static inspection found only modest further candidates: the second
private JSON hash mirror, some pure consent-window operands, and part of the
Product/REPORT dispatch sequence after exact checkpoint/order mapping. Their
combined savings have not been implemented or proved sufficient. The earlier
50–100-added/90–150-removed planning estimate did not predict the actual source
delta. It is not permission to waive this measured gate.

## Why remaining cold code cannot simply be deleted

`personal_read_frame` still serves Product, authority, adoption, track/history
and recovery reads. Its opened-byte/permission/size binding, closed optional-file
inventory and selector checks prevent demonstrated ABA and transient-byte
failures. Its independent final raw proof is not an object-POST replay. Removing
those hooks without equivalent direct authentication would weaken the approved
contract. H3-first loading and non-issuing literal historical ae1 decoding are
also required compatibility readers, not newly issuable authority.

The direct source/admin/index/host checks in the short fence protect mutable
facts and cannot be replaced with retained ALLOW. Remaining overlap needs an
explicit same-observation equivalence proof, not a broad cache or an assumption
that an invocation lock prevents external changes.

## Cutover deliberately remains blocked

The D2 staging gates remain closed for new accounting Product
PR/MERGE/CI/REVIEW/CORRECT, REPORT, corrected publication, completion and NEXT.
This branch does not promote them as a permanent supported product pathway.
Old rows remain literal observations; no new grant, window, nonce, intent,
history or acceptance is minted from them. The existing ordinary and signed
paths keep their prior rules.

Completing the approved cutover still needs current-reader/H3 bindings in those
existing consent views, Product2/report tokens, accounting completion and NEXT2,
including historical NEXT after owner release/expiry and observation-only legacy
recovery. Adding those writers now would increase an already positive delta;
opening the old writers would violate the approved D1 security contract. Neither
is used to claim completion.

**Stop for an operator design decision.** This is not a proof that a larger
safe refactor is impossible. It is a precise gap: no demonstrated complete
replacement/deletion plan currently meets the mandatory net reduction while
retaining the named cold consumers and compatibility obligations. The minimal
alternatives are an approved concrete cold-reader replacement plan preserving
all those protections, or an explicit decision to revise the net-source gate.
No such policy revision is inferred here. No new Issue/backlog is created.

## Qualification limits

Focused deterministic and disposable tests may qualify the bounded changes,
but cannot approve incomplete D4 or the umbrella. Old nonpasses remain private.
The D3 component evidence used declared current-source/review seams. Its
corrected child checkout and run-revision projection differ from the original
baseline fixture; timing is not an identical-fixture causal speedup result.
Any D4 component measurement must retain the same scope and disclosure.

Full #58 CI/integration is **NOTRUN / NOT_RELEASED**. The old Python3.11
qualifier descendant-stop receipt remains **UNKNOWN**; no process inspection or
stop is inferred. No real worker, HTTP target write, pilot, installation, live
archival application, deployment, release or merge is authorized.
