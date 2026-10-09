# Finite stochastic bisimulation

## What the certificate establishes

For one request graph, one fixed public store, a finite rational outcome kernel, and a finite list of explicit secret assignments, the analyzer constructs the reachable finite transition system and refines a partition until it is stable. Calls are visible actions labelled by the resolved model contract and the integer input and output token counts. A stop state is terminal and cannot share a block with a call state.

For each call state, the partition signature sums exact transition probability by `(visible call label, target block)`. A partition is stable when every state in a block has the same signature, and terminal states remain in terminal blocks. This is the standard strong probabilistic-bisimulation pattern for labelled probabilistic transition systems; the transition label here is the usage observation defined by OrchLang. The general theory is due to Larsen and Skou, “Bisimulation through Probabilistic Testing,” *Information and Computation* 94(1), 1–28 (1991), [doi:10.1016/0890-5401(91)90030-6](https://doi.org/10.1016/0890-5401(91)90030-6).

### Finite-horizon consequence

If two initial states are in the same stable block, their distributions over ordered usage traces agree at every finite call horizon, including whether execution stopped before the horizon or was truncated because another call remained. The argument is induction on the horizon:

1. Terminal states have the same terminal observation within a terminal block.
2. At a call state, stability gives equal probability mass for every visible label and target block.
3. By the induction hypothesis, states in a target block induce the same remaining finite-horizon trace distribution. Summing those distributions with the equal signature masses gives equal distributions from the source states.

The equality is exact for the supplied finite rational kernel. It applies to ordered traces of `(resolved contract, input tokens, output tokens)` plus the stop/truncation bit. The analyzer does not include response text, request contents, or cumulative cost in the observation.

A split between initial blocks is **inconclusive**. Strong probabilistic bisimulation is sufficient for equality of these trace laws, not a complete decision procedure for trace-law equality. The analyzer therefore does not report different blocks as a leakage witness.

## Why the state space is finite

The state key contains the normalized next-call-or-stop program counter, all current input/register values, one ordinal per resolved contract, and the retained complete-event history. The finite kernel has finitely many response outcomes. Its ordinal selectors and complete-history event literals are bounded by 32; the analyzer saturates counts at 33, since values at or above 33 match the same set of kernel rules. The history window is bounded by four events. Thus the state key preserves all information used by graph control and kernel selection while allowing productive cycles to close without a call-horizon bound.

The quotient can merge states whose hidden register values or prior requests differ when their future visible transition distributions agree. Those values remain in the unquotiented semantic state so that future guards, requests, and history-conditioned rules are evaluated exactly.

## Reproduction

From the repository root, run:

```sh
python3 audit/evaluate_stochastic_bisimulation.py
```

The driver uses the 11 graph/kernel fixture pairs in `examples/channels/`. It takes the explicit secret values from `audit/evaluate_probabilistic_channels.py` and removes the prior weights, which are unnecessary for pairwise bisimulation. It checks each fixture against the authored case definition, runs the producer on the fixture files so the certificate binds their exact raw bytes, and invokes the independent replayer with the expected public store and secret assignments.

Every `proved_equal` fixture is also checked against exact finite dynamic-programming distributions for horizons 1, 2, 4, 8, 16, and 32 under both aggregate billing and ordered usage-trace observers. These checks validate the selected finite horizons; the certificate’s stable partition is the basis for the all-finite-horizon conclusion.

For every fixture the driver separately runs the producer with `max_states=1`, saves the resulting UNKNOWN certificate, and starts a fresh independent replay process on that report. UNKNOWN reports contain no partial closure or partition claim, and the fresh attestation carries no equality claim. A previous successful attestation is never reused for a cap-limited report.

Generated certificates, replay attestations, per-fixture inputs, finite-DP cross-check evidence, exact source hashes, and resource caps are saved under `bench/results/stochastic_bisimulation/`. The aggregate counts and artifact hashes are in `bench/results/stochastic_bisimulation.json`.

At the current fixture revision, the run covers 11 cases: 5 `proved_equal`, 6 `inconclusive`, and 0 normal-run `unknown`; all 11 normal certificates independently replay, and all 11 state-cap probes return UNKNOWN with a fresh UNKNOWN attestation. The five equal cases have 60 exact histogram-equality checks (six horizons by two observers per case), comparing 120 scenario histograms of unit mass. The cases and kernels are authored synthetic fixtures, not external-workflow adoption measurements.

## Limits of the result

The statement is conditional on the supplied graph, fixed public store, secret assignments, and finite kernel. It does not validate provider probabilities or predict real-provider behavior. Only successful model outcomes are represented; errors, retries, currency, termination probability, cumulative bills, infinite executions, and differential-privacy guarantees are outside the model. Resource-limit exhaustion returns UNKNOWN without a partial proof. The byte-work budget is a deterministic serialization-work estimate, not an RSS or CPU-time bound.

The evaluation’s finite-DP comparisons are produced by the separate `probabilistic_channels.producer_histogram` implementation and cover only the listed horizons. They corroborate those rows but are not an independent proof of the bisimulation theorem. Certificate replay reconstructs the finite state closure and checks transition masses and partition stability independently; it reports the producer’s checker digest as unverified metadata.

## Reference

Larsen, K. G., and A. Skou. “Bisimulation through Probabilistic Testing.” *Information and Computation* 94, no. 1 (1991): 1–28. [https://doi.org/10.1016/0890-5401(91)90030-6](https://doi.org/10.1016/0890-5401(91)90030-6).
