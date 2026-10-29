# Independent adapter/accounting review, 24 October 2026

This review covered `runtime/local_model.py`, `runtime/workflow_kernels.py`,
the original/port orchestration, replay and repeatability runners, the revision
table generator and the exact-accounting manuscript claims. It did not run new
model inference. Historical run files remain unchanged.

## Observed token accounting

An independent inspection of the v3 local-model results found 24 pairs,
48 completed arms and 88 dispatched generation events. All 88 full-request
token-ID lengths matched server prompt counts. No event exceeded its declared
generated-output cap. In 44 events the server's generated-token count differed
from recounting the decoded response. The experiment correctly uses the former
for output usage; decoded response text is not a replacement for generation
accounting.

The recorded bound is `maximum_calls * (input_ceiling + output_cap)`. Requests
are explicitly serialized, sent with `raw=True`, and admitted before dispatch.
No implicit conversation context is passed. This establishes the documented
deployment guard under the server's cap contract. It is not the C++ synthetic
source bound and is not a Lean theorem about this model server.

## Concrete findings and repairs

1. The first extraction retained the routing example's optional
   `display(Image(...))` call after removing its display import. The failed
   original executions were retained; the next corpus removed visualization
   without changing graph, predicate or prompt behavior.
2. All four v3 basic-flow differences were actual request differences: the port
   prepended a newline absent from Prompt Flow's rendered request. They must not
   be attributed to model nondeterminism. The owner amended only this whitespace
   and froze a fresh v4 comparison. The other three v3 differences begin with
   equal HTTP request bodies producing different model responses; the chaining
   example then propagates the different response into its next request.
3. The initial reusable adapter treated `upstream_cap=0` as the full deployment
   cap, accepted fractional/Boolean caps, and dispatched `num_predict=-1`
   before rejecting the response. The hardened adapter now rejects unsupported
   caps before dispatch. The positive 64/120 source caps in the retained model
   campaigns are unaffected.
4. A simulated post-dispatch transport failure originally reported zero token
   usage. The hardened adapter now retains the attempted call and reports
   `usage_complete=false`, an unconfirmed-attempt count, and unknown input/output
   totals. Missing server counters must never be interpreted as zero consumed
   tokens. A response/server accounting failure also cannot establish complete
   actual usage merely from the declared cap.
5. The hardened adapter validates the Tokenizers 0.21.4 dependency and rejects
   tokenizer configurations with truncation or padding enabled. The original
   actual-run implementations are separately snapshotted and hash-bound.

The no-inference probes, before/after source hashes and raw observations are in
[`research/revision-2026-10-24/adapter-review-v1/`](../research/revision-2026-10-24/adapter-review-v1/).
The hardened probes reject zero, negative, fractional and Boolean upstream caps
with zero dispatches. Thirteen dependency-free adapter/kernel/replay tests also
passed in this review.

## Claims checked

The manuscript's exact-accounting section correctly restricts its compositional
byte rule to the audited **plain** GPT-2 tokenizer, with special-token insertion
disabled. Closed-source output caps are conditional assumptions in the selected
accounting policy. Finite replay validates all alternative outcomes against
token and required byte caps. No source-to-tokenizer Lean refinement is claimed.

Captured-response conformance must remain labeled as replay with zero new
generations, exact request/schema/cap matching and complete tape consumption.
Only the explicitly independent parallel calls may reorder. It is a separate
endpoint from independent original/port generation and from repeatability
controls. The new amended run, rather than the known newline-mismatched v3
basic-flow result, must support the final direct-port claim.

## Check of the amended run

The completed v4 run was also independently inspected: 24 pairs, 48 completed
arms and 88 generation events; zero full-request tokenizer/server count
disagreements and zero output-cap violations. The leading-newline discrepancy
is absent. Twenty-two independent-generation pairs agree exactly. The remaining
two basic-flow pairs at output cap 64 have identical complete HTTP bodies but
different responses; neither is represented as successful independent output
equivalence. Captured-response conformance passes all 24 comparisons, matching
44 requests with zero new generations. The separate original/original control
has one response disagreement among eight identical-request pairs (16 actual
generations). These endpoints are consistent with a faithful port under common
outcomes and observed local-generation nonrepeatability, not a determinism
guarantee.
