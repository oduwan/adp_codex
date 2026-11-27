# Personal external-operation diagnostics

Personal publication, Product and track commands retain the existing bounded
operation summaries in `private/runtime-diagnostics.json` of the already
authenticated enrollment. This is one **latest invocation projection**, replaced
on the next invocation, never an action journal, acceptance record or authority
input. It is not portable memory or a GitHub product comment. Keep a private
copy and its returned SHA256 when retaining an unsuccessful invocation.

The CLI reports `runtime_diagnostics` as RETAINED or UNAVAILABLE. If no protected
enrollment has already been authenticated, it makes no destination or additional
observation. Diagnostic failure cannot turn an operation into success, change its
exit code, mask cancellation or authorize a retry. A process killed before scope
finalization may have no new projection; the diagnostic is not crash-recovery
authority. Original durable dispatch/stop records remain authoritative.

Each finalized existing operation scope records its actual allowance and
remainder, request attempts, transport-method entries, request latency samples,
parent CPU and wall time, available Git/Memory/work spans, known refusal
predicates and actually reached boundaries. Invocation wall time excludes
diagnostic retention. Work spans are inclusive and overlap; their sum is not
total wall time, exclusive work, or proof of wasted work. Parent CPU excludes
children. Work outside an existing operation scope is unmeasured, not zero-cost.

CAS latency covers request setup through transport return, excluding subsequent
stop persistence/JSON validation. A decorated read's latency includes that
adapter's own processing. Neither is a uniform wire-latency distribution.
Transport entry does not prove an HTTP child launched or a request reached
GitHub. `http.supervision_requested`, `http.supervision_returned`, validated
response, acknowledged immutable object, CAS acknowledgement, observed target
and settlement are distinct observations. Missing markers prove no absence.

RETURNED is a scope outcome, **not PASS**. An observed inner refusal can be
translated by an existing read/recovery adapter to UNKNOWN; it is retained as an
observation, not promoted to the final exception's cause. Only a propagated typed
budget refusal has a final known code. Time/count co-exhaustion, operation time,
individual request deadline and validated consent expiry have distinct codes.
Expired derived allowances or arbitrary product exceptions remain UNKNOWN unless
their actual source establishes a more precise cause. The A3 historical exception
and request/effect history remain UNKNOWN; this change cannot reconstruct them.

The projection has a closed field/label schema, at most 64 summaries, 256 latency
samples and 16 refusal events per summary, and the existing 131072-byte private
file bound. It exposes truncation, dropped operations/refusals and recording
errors. It excludes exception strings, routes, request bodies, credentials,
configuration rejected values, host identities and Worker content. Preserve raw
private evidence separately where independently authorized.

Limits remain centrally resolved at **10 seconds/request, 150 seconds/operation,
128 attempts**. Diagnostic collection creates no execution budget and does not
extend original consent, legacy 45/120-second allowances, M2 permits or Workers.
No old positive observation or diagnostic is used to authorize an effect.
