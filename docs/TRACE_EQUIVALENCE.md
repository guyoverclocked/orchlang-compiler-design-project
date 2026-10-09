# Exact finite trace equivalence

`audit/trace_equivalence.py` decides equality of ordered successful-call usage traces for a finite request graph and a supplied rational outcome kernel. It compares one fixed public input store across two or more explicit secret assignments. The result applies to that closed model and those assignments.

This checker completes a gap in the companion strong probabilistic bisimulation check. Bisimulation is a sufficient relation for equality of trace laws, but it can split states whose observable trace distributions are equal. The row-space checker decides equality of the specified finite-state trace laws directly.

## Run it

From the repository root:

```sh
python3 audit/trace_equivalence.py \
  examples/channels/trace_equal_not_bisimilar.graph.json \
  examples/channels/trace_equal_not_bisimilar.kernel.json \
  --public-json '{}' \
  --scenarios-json '[{"secret":false},{"secret":true}]' \
  --report /tmp/trace-equivalence.json

python3 audit/replay_trace_equivalence.py \
  /tmp/trace-equivalence.json \
  examples/channels/trace_equal_not_bisimilar.graph.json \
  examples/channels/trace_equal_not_bisimilar.kernel.json \
  --public-json '{}' \
  --scenarios-json '[{"secret":false},{"secret":true}]'
```

The producer prints a JSON report and can also write that report with `--report`. Exit codes are `0` for `proved_equal`, `1` for `unequal`, `2` for invalid input, and `3` for `unknown`. The independent replayer returns `verified`, `rejected`, or `unknown`, with exit codes `0`, `1`, and `2`.

The producer accepts `--max-states`, `--max-work-bytes`, `--max-matrix-entries`, and `--max-rational-bits`. Defaults are 10,000 states, 64 MiB of deterministic byte-work, 10,000,000 matrix entries, and 8,192 rational bits. The checker also inherits finite closure limits from the graph/kernel implementation: at most 1,000,000 call-outcome transitions and deterministic control steps, a 16 MiB source document, a 1 MiB individual value/request, a 16 MiB serialized semantic-state key, and a 64 MiB complete report. `max-matrix-entries` has a hard ceiling of 100,000,000; `max-work-bytes` has a ceiling of 1 GiB.

The byte-work meter charges closure work, rational-vector storage and updates, matrix scans, and report construction. It is a deterministic work estimate, not a claim about process RSS, wall-clock time, or an operating-system resource limit. A cap returns `unknown`; the producer withholds the partial closure, alphabet, result, and equality claim. The replayer independently reconstructs the finite system and verifies the complete closure and the proof or witness. Producer and closure source digests are recorded, but the replayer checks their digest syntax only; they are provenance fields, not a proof that a particular executable was run.

## Observation and claim

Each successful call contributes one ordered label:

```json
{
  "contract": {"provider": "…", "model": "…", "max_tokens": 8,
                "has_unit_price": false, "unit_price": 0.0},
  "input_tokens": 2,
  "output_tokens": 1
}
```

The contract is resolved and normalized, so model aliases do not affect the label. Template and argument text select the finite kernel outcome, but the observer sees only the resolved contract and integer usage. Thus two distinct modeled requests can have the same usage label. Input usage is the graph model's abstract estimate, `ceil(UTF-8 request-fragment bytes / chars_per_token)` for the template and each argument separately; it is not a real tokenizer or provider-envelope guarantee. Output usage is the integer supplied by the finite kernel.

At each finite word, the analysis records two masses separately: mass that is at a stop state after producing the word, and mass that remains at a call state after producing it. This distinguishes a successful stop from a live prefix at a call horizon. If an execution stopped after a shorter word, its stopped observation is represented at that shorter word. Only successful model outcomes are in the state system.

The finite kernel uses exact rational probabilities and first-match rule precedence, followed by the resolved-contract default. Matching uses the complete modeled request, the resolved-contract call ordinal saturated at 33, and the retained complete-event history. The graph semantics also updates result registers and history with each response. The declared kernel and graph are inputs to the claim; the checker does not validate whether their probabilities describe a provider.

The exact `proved_equal` claim is:

> exact all-finite-horizon success-only ordered usage-trace laws for every supplied secret scenario under the declared finite rational kernel

The exact `unequal` claim is that a supplied scenario and scenario 0 have a finite ordered-usage observation with different rational probabilities. The report includes the word, whether its endpoint is `stop` or `nonterminal`, and both probabilities. A witness may be the empty word when the initial scenarios already differ in stopped versus live status.

The result is scoped to the provided public store and every listed distinct secret assignment. It makes no claim about unsupplied inputs or secret values.

## Row-space proof outline

The producer first constructs the complete reachable semantic system for all supplied scenarios. Its states retain normalized control position, initialized values, saturated per-contract ordinals, and retained complete-event history. A transition labeled `a` carries the kernel probability for one successful call with usage label `a`.

For each scenario `i > 0`, let `e_i` and `e_0` be unit rows for the two initial states, and set `μ = e_i - e_0`. For every usage label `a`, let `A_a` be the sparse rational transition matrix whose `(s,t)` entry is the probability of moving from state `s` to state `t` with label `a`. Let `t_stop` and `t_live` be the indicator columns for stop and call states. For a finite word `w = a₁…aₖ`, its two probability differences are:

```text
μ A_a₁ … A_aₖ t_stop
μ A_a₁ … A_aₖ t_live
```

The producer explores a basis of the exact rational span generated by the rows `μ A_w`, starting with the empty word and closing every independent row under every label matrix. If every basis row has zero dot product with both output columns, linearity gives zero for every generated row and therefore every finite word. If a generated row has a nonzero output, its stored word is a finite counterexample. A finite-dimensional row span has rank at most the number of closed-system states, so exploration terminates unless a declared resource limit is reached.

An equality certificate lists generator words and exact rows in the closed-system state order. The independent replayer recomputes each `μ A_w`, checks the rows are independent and span `μ`, verifies closure under every label matrix, and checks both output columns vanish. For an unequal result it recomputes both scenario probabilities for the reported word and endpoint. The replayer also reconstructs all reachable states and transitions from the exact graph and kernel bytes. It does not trust producer status fields or row values.

This is an application of established weighted-automaton equivalence methods. Tzeng gave a polynomial-time equivalence algorithm for probabilistic automata; Kiefer et al. describe linear-dependence exploration and finite distinguishing words for probabilistic automata; later work treats equivalence for automata over rational weights. Here the specialized alphabet is ordered model-usage labels, and the two output columns distinguish stopped and nonterminal prefix mass. This project does not claim a new general weighted-automaton algorithm.

- Tzeng, “A Polynomial-Time Algorithm for the Equivalence of Probabilistic Automata,” *SIAM Journal on Computing* 21(2), 1992, pp. 216–227. [SIAM article](https://doi.org/10.1137/0221017).
- Kiefer, Murawski, Ouaknine, Wachter, and Worrell, “Language Equivalence for Probabilistic Automata,” CAV 2011, LNCS 6806, pp. 526–540. [Publisher DOI](https://doi.org/10.1007/978-3-642-22110-1_42).
- Kiefer, Murawski, Ouaknine, Wachter, and Worrell, “On the Complexity of Equivalence and Minimisation for Q-weighted Automata,” *Logical Methods in Computer Science* 9(1), 2013. [LMCS article](https://doi.org/10.2168/LMCS-9(1:8)2013).

## A trace law that bisimulation separates

The authored pair `examples/channels/trace_equal_not_bisimilar.{graph,kernel}.json` uses two branches and stops after two calls. Both branches first emit the same usage label. The dependent branch uses the first response (`red` or `blue`) in its second request: `red` produces one output token and `blue` produces three, each with probability one half. The other branch makes a fixed `pink` request whose second-call output usage is independently one or three with equal probability. The second request has the same estimated input usage in all cases.

Both scenarios therefore have the same exact ordered usage-trace law: the first call is common, and the second call has one or three output tokens with equal probability. The dependent continuation state after `red` or `blue` does not match the independent branch's distribution state, so strong probabilistic bisimulation separates the roots. The exact trace-equivalence checker proves the supplied pair equal and the independent replayer verifies its certificate.

The regression suite also exercises a non-equal usage channel, an ordered-trace witness hidden by aggregate totals, an empty-word stop/live witness, certificate tampering, and fail-closed resource caps:

```sh
python3 -m unittest audit.test_trace_equivalence -v
```

## Scope limits

The proof is conditional on the supplied finite rational kernel and the existing request-graph semantics. It concerns successful calls, ordered usage labels, and separate finite-prefix stop/live masses. It does not cover provider probability validity, actual billing or currency, provider failures, retry behavior, cumulative cost or execution budgets, termination probability, or infinite-run trace laws. Resource `unknown` is not evidence for equality or inequality. A finite separating word is a counterexample only within the declared model and observation.
