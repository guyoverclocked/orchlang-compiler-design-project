# Completed-state source differential review

This directory holds an independent audit of the completed-state output, a
separate truth-table supplement, and focused checks. It does not alter the
primary study protocol or its results. The supplemental protocol records the
primary protocol/result hashes and the run confirms those hashes stayed
unchanged. Only the six already-authored `token_route_*` development fixtures
are used; this is not the disjoint held-out cohort.

## Primary study findings

The frozen primary result contains 104 pairs: 96 normal stops and 8 call-cap
cutoffs, with 224 source request events and no failed checks. The audit
recomputes the six recorded checks, verifies artifact hashes against the
protocol, and checks that the source-visible final fields map completely and
exactly to backend final values on normal stops. It reports the backend's
extra `lg_temp_0000` in `multi_result_node` separately: this hidden local
register carries an intermediate response into the next request but is not a
source state field. In `mutable_result_chain`, the final source `draft` and
backend draft slot contain the later `revise` response, confirming last-write
projection.

The primary inputs exercised both routes for five operators. `token_route_eq`
had only the false case (12 of 12), so the primary result alone did not test
`tokens(draft) == 2` taking the true branch. The separate supplement closes
that coverage gap over counts 1, 2 and 3 for each of the six operators.

On cutoffs the source harness returns no final state, and the backend returns
`final_values: null`; its internal eager registers are not published as a
completed result. The audit's in-memory corruption checks detect a changed
answer register, a removed mapped result slot, a removed source-field mapping,
and publication of a register on a cutoff. A focused real-backend test also
injects a failure on the second request after the first eager write and
confirms `runtime_error`, one recorded call and `final_values: null`.

The comparison's projection is deliberately source-visible: it verifies every
mapped source field, while allowing compiler-internal local registers such as
`lg_temp_0000`. The mutation tests preserve the saved source result while
corrupting backend output; they do not authenticate a jointly corrupted source
outcome and graph outcome. The primary harness still supplies the actual
source execution record. These authored, offline checks provide finite
differential evidence, not a provider guarantee or a proof of arbitrary source
translation.

The current
[`integrations/langgraph/README.md`](../../../integrations/langgraph/README.md)
does not yet document result schema version 2 or `final_values`'s normal-stop
only behavior. Runtime and call-cap failure semantics are described, and the
backend tests cover existing stop/cutoff/error behavior, but the new serialized
completed-state field deserves a documentation update in a separate change.

The normalized Coq development establishes finite graph-trace/state/status
refinement under the graph model's assumptions. It does not cover Python AST
translation, LangGraph runtime exceptions or the output serializer's
`final_values` projection. The completed-state differential checks therefore
remain empirical evidence outside that theorem.

## Truth-table supplement

The initial frozen attempt failed during replay preparation, before an
authored source app was compiled or invoked and before backend execution. The
preserved `truth_table_initial_protocol.json` and
`truth_table_preflight_failure.json` record that byte-serialization mismatch.
The corrected `truth_table_protocol.json` was then frozen with the amended
runner hash before the 18 runs. It records the explicit expected route matrix:

| Operator | 1 token | 2 tokens | 3 tokens |
|---|---|---|---|
| `== 2` | no | yes | no |
| `>= 2` | no | yes | yes |
| `> 2` | no | no | yes |
| `<= 2` | yes | yes | no |
| `< 2` | yes | no | no |
| `!= 2` | yes | no | yes |

Each run uses the exact deterministic outcome `response = "r" * (4*n)` and
`output_tokens = n`, with the same pure oracle callable passed to the source's
`OfflineRequestSession` and `execute_verified`. The result stores full source
and backend traces, completed states, state projections, per-check outcomes,
operator branch counts and failures. All 18 runs passed; all six operators
observed both branches, including the previously missing `== 2` true case.
This adds a focused development fixture coverage check and does not change the
primary study's 96 completed plus 8 cutoff rows.

## Reproduction

Use the pinned runtime used for the source study:

```sh
"/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade/.venv/bin/python" \
  research/scp_strengthening/completed_state_review/completed_state_review.py
"/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade/.venv/bin/python" \
  -m unittest -v research.scp_strengthening.completed_state_review.test_completed_state_review
"/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade/.venv/bin/python" \
  -m unittest -v integrations.langgraph.test_backend
```

The frozen supplemental results are checked into this research workspace as
`truth_table_results.json`; the runner refuses to overwrite an existing
protocol or result. Reproducing source/backend execution from the same frozen
protocol requires removing neither outcome nor plan; make a fresh named
replication outside this directory instead.
