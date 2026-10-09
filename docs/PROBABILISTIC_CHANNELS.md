# Exact finite usage channels

Candidate 0.5.0-rc1 · 9 October 2026

## Research question

Can a declared, finite probabilistic model quantify the information that a usage observer learns about a private workflow choice, including cases where exact request equality is too conservative?

The structural graph checker establishes a sufficient **universal shared-outcome** property. This analyzer answers a different question: for a fixed public input, selected secret assignments, a declared success-only outcome kernel, and a finite call horizon, what is the exact distribution of the selected usage observation? A zero result is conditional on this model and selected assignments. It does not override a structural rejection or validate provider probabilities.

## Artifacts

- `audit/probabilistic_channels.py`: strict kernel validation and state-merging exact dynamic programming.
- `audit/probabilistic_reference.py`: independently written graph/kernel parser and exhaustive path enumeration, importing no graph producer, structural replayer, or channel analyzer.
- `audit/evaluate_probabilistic_channels.py`: controlled synthetic corpus, differential checks, expected-usage ablation, and observer-coarsening checks.
- `examples/channels/`: 11 authored graph/kernel pairs.
- `bench/results/probabilistic_channels.json`: study provenance, all comparisons, and resource probes.
- `bench/results/probabilistic_channels/`: per-case, per-horizon, per-observer exact channel reports.

The optional report replayer independently re-executes the declared finite model. Its attestation concerns semantic distributions and exact leakage quantities; producer implementation counters and approximate logarithm displays are advisory.

## Model

Let `C` be a resolved model contract and `Q` the exact template and ordered full-text argument tuple. Let `k` be the per-contract call ordinal, and `h_w` the last `w` complete request/outcome events, in chronological order. The user supplies

`K(C,k,Q,h_w) -> finite distribution over (response text, output usage)`.

Probabilities are positive integer/fraction strings, sum exactly to one, and use arbitrary-precision rational arithmetic within an explicit precision cap. Responses are valid Unicode scalar text. Their abstract token estimate must fit the reported output usage, which must fit the declared output cap. Input usage is the sum of the individual UTF-8 ceiling estimates of the template and arguments; it is not the ceiling of a concatenated envelope. This is a declared accounting model, not provider tokenization.

Rules use exact optional-field conjunction and **first matching rule in supplied order**; otherwise the resolved-contract default applies. Alias defaults must agree after contract normalization. History matching uses the whole retained list, not a suffix or a partial event. The window is 0–4 events. Conditional draws are fresh given this explicitly declared state. Provider randomness or hidden persistent state outside the window is excluded.

Price, when supplied, is nominal finite binary64 configuration metadata used in resolved identity. The analyzer does not multiply tokens by price or compute currency, rounding, error charges, retry outcomes, cache discounts, timing, traffic, output quality, or provider invoices. Only successful call outcomes are modeled. A graph can express call-bearing control cycles; native retry success/failure events are not present.

## Observer and horizon

Two selectable observations are supported:

1. **Aggregate usage**: for every unique resolved contract, including zero rows, `(call_count, sum(input_tokens), sum(output_tokens))`, plus `stopped`.
2. **Ordered usage trace**: each call's `(contract,input_tokens,output_tokens)` in execution order, plus `stopped`.

Neither observation contains request text, response text, internal state or branch labels. Those may affect future calls and are retained in the semantic state.

`H` is a call-count horizon, between 1 and 32. After the Hth call, deterministic control continues until a stop or the next call. A reached stop yields `stopped=true`; another pending call yields a truncated prefix with `stopped=false`. Truncation is never relabeled termination. Control/resource exhaustion produces `unknown` with no histogram, mass or leakage conclusion. The tool does not prove an infinite-run distribution or a finite whole-cycle budget.

## Algorithm and exactness argument

A DP state contains control position, every currently initialized input/register value, per-contract ordinals, accumulated usage, selected ordered usage trace, retained complete history, and accumulated trace bytes. States at the same call depth merge only when all these components agree.

For a fixed complete input assignment:

1. Start with mass one at the entry state.
2. Normalize deterministic control to a call or stop using concrete values.
3. At a call, construct `C,k,Q,h_w`, choose the unambiguous kernel, and distribute mass by exact multiplication over all finite outcomes.
4. Update the result register, ordinal, usage, history, and resource state; merge identical successors by exact addition.
5. Project stopped or horizon-truncated states onto the selected observation.
6. Require total terminal mass to be exactly one before reporting `complete`.

**Induction invariant.** At depth `d`, each DP state's mass is the sum of probabilities of all concrete execution prefixes of `d` calls with exactly that complete semantic/resource state. Deterministic normalization preserves the invariant. The kernel's unit mass and state update preserve it by distribution over successors; merging adds disjoint path masses. Complete state equality entails the same future control, request, conditional outcome law and resource behavior, so merging loses no future distinction. At the horizon, projection sums exactly the probabilities of concrete observations. The independently written no-merge evaluator computes the same path measure directly.

This is an implementation-level proof argument. There is no mechanized metatheory proof or verification of the Python implementation. Differential testing corroborates selected finite cases and cannot prove general correctness.

## Quantitative outputs

Fix a public store and 2–64 distinct explicit secret assignments with positive exact priors summing to one. No claim is made about other public stores or unlisted secrets.

For channel rows `P_s(b)` and prior `pi_s`, the analyzer reports:

- Pairwise total variation `TV(s,t) = (1/2) sum_b |P_s(b)-P_t(b)|`, exactly rational.
- Symmetric maximum likelihood ratio, with an explicit infinite flag when a positive-probability observation has zero probability in the other row. This statistic is not a differential privacy guarantee; no adjacency relation is supplied.
- Posterior Bayes vulnerability `V = sum_b max_s pi_s P_s(b)` and prior vulnerability `max_s pi_s`, exactly rational.
- Exact vulnerability ratio `V/V_prior`; the min-entropy leakage in bits is its base-2 logarithm, shown as a floating approximation.
- Mutual information as an exact finite expression `sum_{s,b} pi_s P_s(b) log2(P_s(b)/P(b))`, preserving rational coefficients/ratios, plus an explicitly approximate floating display. No certified logarithm interval is claimed.

Singleton analyses reject rather than displaying vacuous pairwise equality. General quantitative information-flow metrics, probabilistic path enumeration, coupling and state merging are established methods. The software specialization is the complete request/history-indexed, source-linked success-only LLM usage observer and its independent checking pipeline.

## Recorded controlled evidence

The current study contains **11 authored graph/kernel fixtures**, three structurally accepted and eight structurally rejected. Across selected horizons 1–6, and 1/2/4/8/12 for the merging stress case:

- 130 two-scenario channel analyses;
- 260 producer/independent-DFS histogram comparisons, all equal with exact unit mass;
- zero distribution mismatches;
- 17 analyses with equal expected usage totals but a positive distributional difference;
- all 11 state-cap probes return unknown without a histogram or leakage metric.

Hand-derived cases demonstrate the boundaries:

| Case | Aggregate TV | Ordered-usage TV | Meaning |
|---|---:|---:|---|
| Different one-call requests, declared equal usage laws | 0 | 0 | Model-specific equality is weaker than universal request equality |
| Usage probabilities 3/4 vs 1/4 | 1/2 | 1/2 | Posterior vulnerability is 3/4 under a uniform binary prior |
| Outputs 1/3 with probability 1/2 each vs deterministic 2 | 1 | 1 | Equal expected output usage does not imply equal laws |
| Two-call usage sequences (1,3) vs (3,1) | 0 | 1 | Aggregate totals hide order that a trace observer sees |
| Equal first-call usage with distinct retained outcomes | 1 after call 2 | 1 after call 2 | Explicit response history can affect later usage |
| Public argument equal to a literal in one fixed store | 0 | 0 | Fixed-store analysis does not generalize to all public inputs |
| Same public argument changed to a longer value | 1 | 1 | The preceding equality was conditional on its public store |

The entire study expands 1,132 DP outcome transitions versus 35,692 independent DFS transitions, with 18,056 DFS leaves. These are algorithmic work counts on constructed small cases, not a real-world speed claim. Timing fields are advisory, environment-sensitive measurements. The study is not a held-out benchmark, an empirical fit to LLM distributions, or independent user evidence.

## Fail-closed limits

Each graph/kernel source is bounded to 16 MiB; each text value/request to 1 MiB; each trace to 16 MiB. The DP has a state-count cap, an 8,192-bit rational precision cap, and a configurable cumulative canonical serialization-work estimate (64 MiB by default, at most 1 GiB). The estimate limits retained-state/observation work but is not an operating-system RSS bound. These limits can cause unknown or input rejection; neither outcome means safe. The independent DFS has separate explicit path, control/work-step and byte-work limits and may be unknown when the DP completes.

Reports bind exact graph/kernel/analyzer bytes, canonical public/scenario inputs and priors, observer, horizon, budgets, histograms and metrics. Input values are deliberately included for reproducibility; use synthetic secrets for shareable evidence.

## Primary foundations and nearby work

- G. Smith, *On the Foundations of Quantitative Information Flow*, FOSSACS 2009, [DOI](https://doi.org/10.1007/978-3-642-00596-1_21).
- C. Braun, K. Chatzikokolakis and C. Palamidessi, *Quantitative Notions of Leakage for One-try Attacks*, ENTCS 2009, [DOI](https://doi.org/10.1016/j.entcs.2009.07.085).
- K. Schröer et al., *Symbolic Quantitative Information Flow for Probabilistic Programs*, 2024, [author preprint](https://arxiv.org/abs/2412.00907).
- G. Barthe et al., *Relational Reasoning via Probabilistic Coupling*, LPAR 2015, [DOI](https://doi.org/10.1007/978-3-662-48899-7_27).
- L. Mandel et al., *PPDL: LLM-Based Flows as Probabilistic Programs*, ICML 2026, [PMLR](https://proceedings.mlr.press/v306/mandel26a.html). PPDL already models uncertain multi-call LLM flows and uses token budgets/usage in its examples. The delta here is a secret-conditioned usage-only observer and explicit confidentiality quantities; it is not the introduction of probabilistic LLM workflows.
