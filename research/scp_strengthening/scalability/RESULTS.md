# Structured scalability study results

## Coverage and outcomes

The frozen matrix contains 27 non-primary cases. It varies secret fan-out, public control context, dependent requests over retained history, mutable result registers, productive cycles, finite response support, usage-label alphabet, and the resulting reachable stochastic closure sizes. The structured groups contain 27 current cases across exact analysis, exact replay, bisimulation analysis, and bisimulation replay, plus seven preregistered pre-optimization pairs for exact analysis and replay. This yields 122 version/operation groups and 732 raw rows: one warmup and five measured workers per group. The raw data are in [`structured_results.json`](../../../output/scp_strengthening/scalability/structured_results.json); inputs and digests are in [`frozen_inputs.json`](../../../output/scp_strengthening/scalability/frozen_inputs.json).

Measured status counts (warmups excluded) are:

| Implementation and operation | Status counts |
|---|---|
| Current exact producer, 27 cases | 125 `proved_equal`; 5 `unequal`; 5 `unknown` |
| Current exact replay, 27 cases | 130 `verified`; 5 `unknown` |
| Current bisimulation producer, 27 cases | 120 `proved_equal`; 10 `inconclusive`; 5 `unknown` |
| Current bisimulation replay, 27 cases | 130 `verified`; 5 `unknown` |
| 5aa pre-optimization exact producer, 7 fixed cases | 30 `proved_equal`; 5 `unequal` |
| 5aa pre-optimization exact replay, 7 fixed cases | 35 `verified` |

No measured row was an admission failure, invalid result, worker error, or timeout. The resource probe deliberately reaches `STATE_CAP`: exact and bisimulation analysis and both replay operations retain `unknown` in all five measured repetitions. UNKNOWN raw stop times and diagnostics remain in the result rows; those rows contribute no completed-result latency samples and are never represented as zero.

The required semantic checks were retained. For `history_conditioned_unequal`, exact analysis returns a two-observation witness with probability 1 on one secret route and 0 on the other; the usage observations each have input/output tokens `(1, 1)`. Independent exact replay verifies it in all five measured repetitions. Bisimulation is inconclusive on this unequal case. On `bisim_inconclusive_exact_equal`, exact analysis proves equality and exact replay verifies, while bisimulation is inconclusive and its independent replay verifies the certificate's inconclusive classification. These cases distinguish exact trace equality, exact finite witnesses, and the sufficient-but-incomplete bisimulation proof.

## Structural work and timing

The table reports the range of per-case medians across each preregistered family, not a pooled timing estimate. Exact analysis and exact replay each use five fresh measured workers per case. State/transition counts are from the current exact producer's raw rows. All timed inputs are finite synthetic schema-valid graphs and rational kernels.

| Family and levels | Reachable states / transitions | Exact producer median range | Exact replay median range |
|---|---:|---:|---:|
| Secret fan-out, 2/4/8 leaves | 4–16 / 2–8 | 0.83–2.38 ms | 0.90–3.65 ms |
| Public guards, 0/2/4 | 4 / 2 | 0.91–1.28 ms | 0.95–1.07 ms |
| Mutable registers, 1/2/4 | 10–190 / 12–316 | 1.89–77.53 ms | 2.47–164.82 ms |
| Productive cycle, 1/2/4 call states | 68–74 / 68–74 | 10.35–11.72 ms | 28.34–32.14 ms |
| Outcome support, 1/2/4/8 responses | 4–18 / 2–16 | 0.86–2.18 ms | 0.94–2.51 ms |
| Usage alphabet, 1/2/4/8 labels | 18 / 16 | 2.14–2.81 ms | 2.52–3.81 ms |
| Retained-history window, 0/1/2/3 | 16–46 / 24–44 | 2.72–11.57 ms | 3.51–10.09 ms |

Reachable closure size varied from 4 to 190 states across the controlled structural families. The largest current exact producer median among completed structured cases was 77.53 ms (`mutable_registers_4`, 190 states and 316 transitions); its independent exact replay median was 164.82 ms. This points to dependent mutable-register closure and certificate checking as a measured work hotspot in these fixtures. Productive cycles remained finite under the registered ordinal saturation at 33; adding call states from one to four changed the observed closure only from 68 to 74 states. Increasing the observation alphabet from one to eight held closure size fixed at 18 states and 16 transitions while both exact analysis and replay medians increased modestly.

The unchanged primary symmetric-chain scripts provide the paired scaling baseline. Current exact analysis and replay prove/verify at five of five repetitions through 128 calls per arm; both return UNKNOWN at 256. At 64 calls per arm, current versus the frozen 5aa baseline has exact replay medians of 86.98 ms versus 138.77 ms and independent-work bytes of 1,784,025 versus 9,972,749. At 128, current completes at 82.83 ms analysis and 320.02 ms replay, while 5aa is UNKNOWN and therefore has no completed-result timing comparator. At 256, current and 5aa are both UNKNOWN; the current rows retain the `BYTE_WORK_CAP` diagnostic (67,108,864-byte limit; 67,116,168 observed) and the 514-state/512-transition closure. The current cap-stop time is preserved as raw diagnostic data, not counted as a completed-result latency.

The frozen rc2/dd97 source snapshot and current checkout have identical relevant audit source (the preregistered worker confirms no diff in the six compared modules). In particular, exact producer and exact replay source digests are identical. Duplicating timings for identical code would not estimate a version effect, so dd97 is a source-identity/parity reference rather than a second timed arm. The separate 5aa pre-optimization comparison is timed on the same frozen input bytes for the original family and the seven registered structured cases.

## Interpretation limits

These results cover only frozen synthetic graphs on this local macOS ARM64 / Python 3.14.6 environment. They do not estimate real workflow distributions, provider behavior, execution cost, retries, failures, termination probabilities, or infinite-run costs. Public-guard levels did not increase the reachable closure in this fixture. Structural parameters also change multiple closure properties together; the observed 4–190 state range is not an isolated state-count scaling law. Wall times and RSS are environment-specific; deterministic bounded-work counters and input hashes are retained to support later comparisons. The algorithmic setting and proof assumptions are described with primary citations in the [preregistration](PREREGISTRATION.md).

The reporting regression and raw-result checks are executable with:

```sh
python3 research/scp_strengthening/scalability/validate_structured_results.py
```

It exercises the real aggregation function on six synthetic version/case groups with known distinct medians for equal and unequal outcomes, confirms UNKNOWN never enters completed latency, checks saved summaries against the raw rows, and asserts the preregistered repetition count for every final group.
