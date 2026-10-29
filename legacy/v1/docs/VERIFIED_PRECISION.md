# Verified decisions for ordered and aggregate resource observations

The implementation has two explicitly different relational judgments. The
ordered text-dataflow judgment preserves complete state-transformer semantics,
including response strings, subsequent requests and ordered billing events.
The aggregate judgment permits exchanging two independent closed calls when
only per-contract totals are visible. Neither decision overrides the C++ source
checker's content-confidentiality policy or proves a declared source budget.

## Ordered text-dataflow rewrites

`proof/DataflowCore.lean` proves these rewrites:

| Rule | Mechanized result |
|---|---|
| Append associativity, empty literals, adjacent literals | `appendText_correct`, `normalizeText_correct` preserve the constructed request string for every text store |
| Sequence with an empty program | `compose_unit_left`, `compose_unit_right`, `sequencePlan_correct` preserve the complete weighted execution list |
| A public conditional with equal normalized arms | `publicPlan_correct` preserves the selected state transformer for either public guard value |
| Composition through secret branches, sequence and lexical retry | `normalize_correct` preserves the complete state transformer |
| Successful plan-free decision | `checkProgram_sound`, `decoded_decision_sound` imply relational equality for all secret Boolean assignments, shared public inputs and full-request kernels |

The procedure still compares the resulting plans exactly. It does not decide
all semantic equivalences. Different response slots, contract fields, serialized
requests and observable call order remain distinct. A response's length cannot
replace its contents in a downstream request. No theorem claims a general new
relational logic or optimal precision.

`runtime/dataflow_gate.py` mirrors the new rewrites. Its source reader already
merged adjacent template literals before this revision, and the source language
has no append expression operator. Accordingly, append-rewrite precision gains
are reported as core cases. Source gains arise from redundant public control and
empty sequences, under the same ordered observation and primitive assumptions.

The primary interface requires no certificate:

```text
python scripts/dataflow_certificate.py decide SOURCE.orch --lean /absolute/path/to/lean
```

The legacy `issue`/`check` commands remain for compatibility. Their saved plan
is diagnostic output. Checking it recomputes normalization; it provides neither
a proof-carrying witness nor a search-versus-check complexity advantage.

## Independent closed calls under the aggregate observer

`proof/AggregateReordering.lean` defines a separate decision for exactly two
closed calls in each arm of one secret branch. A full action is the pair
`(contract, serialized request)`. The observer records, for each contract, input
bytes, output bytes, call counts and failure counts. An accepted pair has the
same actions in the same order, or the reversed order.

The kernel of each action is an arbitrary finite list of response text, status
and natural probability numerators, together with a common denominator. Each
finite rational distribution admits this representation. The independent product
semantics samples the two calls separately. Equal action names do not introduce
correlation, and neither call can use the other's response or mutate shared state.

`samples_comm` proves permutation of the weighted aggregate outcomes when the
calls are exchanged. `mass_perm` proves that permutations preserve the exact
weighted histogram numerator for every Boolean predicate of the full aggregate
observation. `independent_calls_aggregate` also proves equality of the product
denominators. Thus the result establishes equality of the finite probability
measure when each row is normalized and its denominator is positive. It does
not confuse different enumeration order with different probability mass.

`decision_sound` and `decoded_decision_sound` connect acceptance to that result.
The executable checks row normalization, nonnegative integral numerators,
positive denominators, duplicate/missing actions and operational limits. Kernel
validity is checked operationally rather than proved of a provider. The algebraic
theorem also holds for invalid tables; probability interpretation requires the
stated validity conditions.

```text
python scripts/decide_aggregate.py SOURCE.orch --lean /absolute/path/to/lean
```

The trusted Python reader permits only one secret branch with two literal-request
calls per arm. It rejects public inputs, response dependencies, nested branches,
retry, tools, and branch/nonliteral outputs. Literal outputs can occur only at
workflow root. There is no store-dependent continuation after the branch. The
theorem excludes timing and mutable provider state. Under a timing or ordered
account observer, exchanging the calls can reveal the secret schedule.

The three `examples/certificates/aggregate_*.orch` sources illustrate independent
document checks, classification labels and document summaries. They are authored
illustrations, not executions or faithful ports of external applications.

### Retaining results for a trusted caller

The source fragment's two branch-local result bindings do not escape their
lexical scope. A root completion string does not retain their contents. The
source examples therefore demonstrate a scheduling judgment, not complete
document-processing applications. This is a remaining source expressiveness gap.

The commutation rule itself need not discard useful results.
`independent_calls_private_results` proves equality of the joint distribution
of aggregate usage and a full-action-indexed multiset of complete response text
and failure status. `PrivateResults` is a count function on `(full action,
response, status)`, so equal actions with repeated responses retain multiplicity.
The proof transposes independent outcomes and preserves both the usage/response
association and its probability mass. `decoded_private_results_sound` connects
the richer observation to the decoded decision.

The isolated `private` executable mode exports those response archives for every
weighted finite outcome. A trusted host can associate independent results with
their requests while using the verified schedule-invariance judgment. This is
useful for a host that collects independent batch results, but it is not a source
language return statement or a public-output confidentiality guarantee. The
archive is finite-table execution, not a provider inference run.

```text
python scripts/decide_aggregate.py SOURCE.orch --lean /absolute/path/to/lean --finite-kernels TABLE.json --private-results NEW-ARCHIVE.json
```

The kernel file is an array of rows
`[contract, request, denominator, [[response, failed, numerator], ...]]`.
Contracts use the full canonical strings reconstructed from source. Each row
must have positive denominator and numerator mass equal to it. The output is a
new JSON file bound to the source digest. Its `private_results` arrays represent
multisets; their serialization order carries no guarantee. The original command
and ordinary JSON execution format remain unchanged.

## Retained development results

All campaigns below use exact finite enumeration and Lean 4.19.0. They are
authored development grammars, not held-out or external workload evaluations.
Fresh executable and source-file hashes are recorded in each manifest.

| Campaign | Cases | Baseline accepts | Verified accepts | Additional accepts | Rejected |
|---|---:|---:|---:|---:|---:|
| Ordered source control/sequence forms | 80 | 8 | 64 | 56 | 16 |
| Ordered core request expressions | 72 | 8 | 64 | 56 | 8 |
| Aggregate closed-call action pairs | 256 | 16 | 28 | 12 | 228 |

The first two rows compare against the historical syntactic normalizer with
the same ordered semantics. The third row changes the observer from ordered to
aggregate: it is an observer-specific relaxation, not an advantage for preserving
ordered traces. All twelve aggregate gains have different ordered distributions
under the supplied kernels, as expected. Finite checks found no accepted aggregate
counterexample. The universal claims come from the proofs, not that absence.

The ordered precision campaign checked 3,648 contexts across Lean, the independent
reference and replay. The aggregate campaign checked 512 contexts and 2,048
weighted paths, plus eight malformed-input rejections and three illustrative
source decisions. Both completed with zero decision/execution disagreements.

A separate `aggregate-private-results-v1` campaign reuses all 256 aggregate
sources and their finite kernels. Its 512 contexts and 2,048 weighted paths
compare the joint usage/complete-response archive across Lean, reference and
replay. All 28 accepted cases preserve the joint distribution; there are zero
accepted joint counterexamples or cross-implementation disagreements. The same
run checks that ordinary aggregate JSON outputs are unchanged. Earlier example
source bytes remain in `aggregate-reordering-v1/illustrative-sources`; the new
scenario records include current full source text and hashes.

The unchanged historical pipeline grammar was rerun after the new normalizer:
256 source programs, 16 accepted, 3,072 execution contexts, eight core boundary
cases, 32 source changes, 16 altered plans and eight invalid evaluator inputs.
All checks completed without disagreements or accepted finite counterexamples.
There is no acceptance improvement on that grammar, which has no new rewrite
opportunities. Results reside in:

```text
research/revision-2026-10-24/dataflow-precision-v2/manifest.json
research/revision-2026-10-24/dataflow-regression-v1/manifest.json
research/revision-2026-10-24/aggregate-reordering-v1/manifest.json
```

The first precision attempt is retained as failed. Its independent expected-core
builder associated a trailing empty conditional to the left of a two-call
pipeline, whereas the source reader produces right-associated sequences. The
32 source reconstruction mismatches caused a failed manifest despite successful
execution comparisons. The amended v2 builder uses the source grammar's stated
association; all source texts, kernels and selection criteria are unchanged.
One duplicate core request variant was replaced with a distinct identity form,
so the v2 core baseline census is eight rather than the first attempt's ten.

## The eight historical C++/Lean policy differences

These cases are identified from the original retained 256-source campaign, not
selected from the new precision grammar. In every row, the left and right arms
have identical contract/request/dependency structures. The first response feeds
the second request. C++ assigns the response the secret branch's PC label and
reports E230 once in each arm; the resource-only Lean decision accepts matched
request distributions under its secret-Boolean model.

| Original ID | Revision | Cap | First request | Second request | C++ | Ordered Lean |
|---:|---|---:|---|---|---|---|
| 0 | A | 4 | public input | first response | E230 in both arms | accept |
| 34 | A | 4 | fixed | first response | E230 in both arms | accept |
| 68 | A | 8 | public input | first response | E230 in both arms | accept |
| 102 | A | 8 | fixed | first response | E230 in both arms | accept |
| 136 | B | 4 | public input | first response | E230 in both arms | accept |
| 170 | B | 4 | fixed | first response | E230 in both arms | accept |
| 204 | B | 8 | public input | first response | E230 in both arms | accept |
| 238 | B | 8 | fixed | first response | E230 in both arms | accept |

Each row's reason is the same policy distinction: C++ rejects the secret-PC
response at its downstream prompt, while Lean establishes only the matched
resource-distribution judgment. A Lean acceptance cannot authorize transmitting
a response rejected by C++ IFC. The product's source-level content policy remains
the C++ judgment. The explicit verified decision commands provide separately
named restricted-core guarantees.

The complete source and original stderr of every differing case are retained in
`dataflow-precision-v2/historical-policy-differences.json`, with the SHA256 of the
historical input file. The fresh 256-case regression reproduces the same counts:
C++ accepts eight and the ordered dataflow decision accepts sixteen.
