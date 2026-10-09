# Provisional review deck: OrchLang request-equivalent workflows

**Status:** historical 18-slide planning draft, superseded by
[`outline.md`](outline.md) and the final 32-slide presentation. It predates the
source bridge, finite-channel additions, exact trace-law extension and final
evidence gate. Retain it only as a record of the earlier graph-focused story;
its pending statuses and counts do not describe the final candidate.

## Claim and scope

The candidate centers on equality of modeled per-call usage-event prefixes
across executions with equal public-input identities and arbitrary secret
choices, under a shared `Ω(resolved contract, per-contract index, exact DSL
request)`. The frozen C++ OrchLang compiler remains a bounded-AST analysis.
The cyclic checker is a separate experimental JSON graph model. Product
programs, self-composition, relational cost analysis, and resource-aware
noninterference are established foundations; the graph checker is a narrow
workflow specialization, not new general theory.

The accepted-cycle result is finite usage-prefix equality only. It establishes
neither termination nor finite total tokens, price, or call count. The graph
does not prove fidelity to an upstream source/workflow, provider serialization,
real invoices, timing, tools, or output confidentiality.

## Main talk (18 slides, including cover)

| # | Headline / purpose | Evidence object |
|---|---|---|
| 1 | Can a secret change the model-usage trace? | Cover names the observer and two analysis artifacts. |
| 2 | A secret can change when a call loop stops | `private_termination_count`: seed 1, fixed empty public query; one trace stops as the other reaches a second call. |
| 3 | The cyclic checker is a separate JSON graph front end | Side-by-side frozen C++ AST and experimental JSON graph pipelines. |
| 4 | Compare usage-event prefixes under a shared oracle | Event `(contract, input usage, output usage)` and relation `Ω(c,k,Q)`. |
| 5 | The product state pairs control and related registers | `(pcL,pcR,R)` diagram with a request-linked result relation. |
| 6 | Every secret successor pair must be checked | Local rules for secret/public guards, matched calls, stop, goto, and fail-closed cycle handling. |
| 7 | A productive cycle can close coinductively | Accepted two-call cycle; finite prefix theorem separated from 120-call simulation cap. |
| 8 | A separate replayer reconstructs the product closure | Source hash, product certificate, independent closure replay, limited attestation. |
| 9 | Overwriting a result must erase its old pairing | Concrete stale-result mutation; event 2 input usage 10 vs 15 in one mock witness. |
| 10 | Unary bounds and relational checks answer different questions | One-run bound versus two-run trace relation; no graph-cycle budget theorem. |
| 11 | Equal caps still do not imply equal realized usage | Existing OrchLang counterexample remains the bounded-AST baseline. |
| 12 | The existing compiler remains a finite OrchLang pipeline | C++ lexer/parser, semantic facts, analyses, certificate, offline mock. |
| 13 | Generated C++ cases were checked against full request text | 264 cases; independent Python full-text reference; exact accepted/rejected denominators and unknown mutations. |
| 14 | Eight rejected graph fixtures have billing-vector witnesses | 17 fixtures, six accepted certs replayed, finite grid; stopped witnesses are complete and other witnesses stop at 120 calls. |
| 15 | The delta is relational request matching, not unary graph cost bounding | Directly compare against product-program/RelCost/resource-aware IFC and Dickerson's unrefereed Petri-net cost-bound work. |
| 16 | A generated graph probe adds coverage, with a shared reference | 3,000 generated small graphs; explicitly supplementary, not independent semantics. |
| 17 | The result is a checked graph model, not a verified deployment | Explicit oracle, accounting, source-fidelity, and no-budget limits. |
| 18 | A narrow relational check can cover cycles without promising a budget | Conclusion returns to the exact claim and evidential boundary. |

## Appendix (8 slides)

| # | Topic | Evidence |
|---|---|---|
| A1 | Version-1 JSON graph schema | Inputs, resolved contracts, call nodes, guard nodes, register units. |
| A2 | Product worklist and cycle rules | Universal secret choices, public synchronization, calls, stop, call-free/productive cycles. |
| A3 | What certificate replay verifies | Source binding, full closure, tampering, remaining trust. |
| A4 | Full-text stress study | 264 C++ checks, Python full-text reference, 13,824 comparisons, 66,240 accounting checks, 117 witnesses / 3 unknown. |
| A5 | Supplementary graph property probe | 3,000 generation, 11,696 pairs, shared producer/reference caveat. |
| A6 | Earlier source-derived bounded-pattern study | 15 partial source projections, repeated oracle grids reported separately. |
| A7 | Likely examiner questions | Cycle semantics, source fidelity, Ω, certificate scope, overwritten registers, novelty. |
| A8 | Selected references and contribution boundary | Self-composition, product programs, IFC/RelCost, unary graph cost bounds, PPDL and graph-security neighbors; no score yet. |

## Experimental numbers and denominator rules

- **C++ full-text stress:** 264 generated source cases: 144 accepted and 120
  mutations rejected. The independent Python interpreter performed 24,192
  runs, compared 13,824 accepted secret-assignment pairs, and ran 66,240
  per-call accounting checks; it saw zero accepted request/usage mismatches.
  It found request-and-usage witnesses for 117 rejected mutations; three retry
  mutations had no witness in the finite grid and remain unknown. Synthetic
  ASTs and one-byte-per-token input charging do not imply provider behavior.
- **Graph fixtures:** 17 authored JSON cases: 6 accepted, 8 rejected, 3
  invalid. All 6 accepting certificates replayed. The accepted probe ran 1,400
  executions and 800 secret comparisons; 28,580 accounting checks; zero
  request, billing-vector, or complete-trace mismatches. All 8 rejected cases
  had billing-vector witnesses. A witness covers the complete run when both
  sides stop; otherwise it covers at most 120 calls.
- **Generated graph probe:** 3,000 small graphs, 11,696 paired stores, and zero
  observed complete-observation mismatches; this shares the producer reference
  implementation and is supplemental only.
- The three study families have different semantics and denominators. Do not
  combine them into one total.

## Related-work positioning

The nearby Petri-net paper addresses unary cumulative resource/token-cost
bounds on LLM workflow graphs and is author-reported/unrefereed. Agentproof and
AgentFlow are preprints with static workflow verification elements. PPDL
models probabilistic LLM/tool flows. Product programs, self-composition,
resource-aware IFC, and relational cost analysis are established. The
defensible delta is an executable per-call model/request/event product with a
register relation, coinductive productive-cycle closure, and a separate
replayer for the certificate. No literature review can erase the model's
source-fidelity assumptions.

## Freeze gate before final export

1. Parent freezes manuscript title, formal contract, aggregate report hashes,
   exact graph billing-witness totals, and venue/novelty assessment.
2. Source register and slide notes match that frozen text; author-reported and
   peer-reviewed statuses are visibly distinguished.
3. Rebuild PPTX from the candidate deck data with hash checks enabled.
4. Export PDF, render every slide, inspect all full-size PNGs and the montage,
   and resolve any wrapping/clipping. No visual QA claim is implied by this
   provisional source file.
5. Regenerate the 8- and 15-minute scripts and all artifact checksums.
