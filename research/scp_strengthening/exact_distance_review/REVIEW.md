# Adversarial review: exact uncertain trace distance

**Review date:** 14 October 2026. **Review target at initial audit:** `exact_uncertain_distance.py` SHA-256 `0019dd5bf387f6fa39511777beba01e8c49ef863e897f2f4a49e09227da74ca3`; tests SHA-256 `b7d96310026998feb3f8909d20ca1c816b84fd634c0133128baa8c2a1a1c36da`; runner SHA-256 `7b06fa5a72192ce203849e5c3895ba9bb18f2ec89c023089ba6b2413ac8ab97b`; README SHA-256 `237e1610cef7d463a5b8bef03592cfa51c7f672c64210f88c01b3e4cd14a2042`. Source files were read-only during review. Only synthetic finite contracts and project-owned unit fixtures were exercised; no workflow/provider code or heldout material was read or run.

## Result

The Bellman recurrence, generator-pair reduction, rectangularity scope, STOP treatment, and all-state replay structure are consistent with the declared finite model. Fresh exhaustive enumeration agreed with the producer on 120 additional synthetic contracts, and selected local generator pairs reconstructed a full vertex policy attaining the reported optimum in all 120 cases. Three bounded-resource defects were found over review and follow-up: certificate item-count mismatch, generated prefix-rational mismatch, and a producer state cap that did not count unfinished ancestors. All three are repaired. A fixed JSON nesting limit was also added to make validation independent of interpreter recursion behavior. I independently reran the reproducers, 21 tests, and oracle checks against final audited implementation SHA-256 `d6136bed1de6fd5ba704a9bf1a79e4d20b6d942d771dba2c1d7460e2c561722c`.

This is a bounded exact result **over the submitted row-polytope contract**. It is not a provider-specific bound unless the real conditional rows are independently justified to lie in the declared contract. No probability model, uncertainty radius, or full-history row premise is calibrated by this artifact.

## Mathematical exactness audit

For scenario `s` and each complete live visible history `h`, the input declares a finite set of rational generator rows and permits every row in their convex hull. Define `C_h(a,b)` as the minimum weighted overlap of the two possible suffix laws from prefix masses `a,b`. The reference recurrence is

```text
C_h(a,b) = min_{p in U_left(h), q in U_right(h)}
             sum_y C_{hy}(a p(y), b q(y))
```

with `C_h(a,b)=min(a,b)` at the horizon and `min(a p(STOP), b q(STOP))` for the first STOP event. STOP is padded deterministically to the horizon. Consequently the root value `1-C_empty(1,1)` is the maximum TV distance, since overlap of two normalized laws is `1-TV`.

The row-generator reduction is valid under the documented finite, compact, rectangular product of row polytopes. For fixed full suffix laws `P,Q`,

```text
overlap(a,b; P,Q) = (a+b - ||aP-bQ||_1)/2.
```

The supremum over admissible suffix-law pairs of the weighted `L1` term is convex in `(a,b)`, being a supremum of convex functions. Thus `C_h(a,b)` is concave. At a current row pair `(p,q)`, each child term is a concave function of `(p,q)` by linear scaling of the two masses, so the local objective is concave on `U_left(h) × U_right(h)`. A concave function on a compact polytope has a minimum at an extreme point; the product polytope's extreme points are generator pairs. This justifies enumerating listed generator pairs even though the input permits all their convex mixtures. Rectangularity lets each distinct next-history subtree select its row independently. The proof is finite and exact; it is not mechanized in Coq.

That argument does not cover global/shared parameters, temporal coupling across histories, cross-scenario coupling, or any other nonrectangular feasible set. If the submitted polytopes are sound outer projections of such a true set, the independent row-product maximum is an upper bound for the smaller true feasible set, potentially very loose; it is not the exact maximum for that coupled set. If the true rows are outside the submitted polytopes, no bound follows. The checked shared-parameter example correctly reports TV `1` for the rectangular product of `{δ_A,δ_B}` rows while the tied model allowing only `(δ_A,δ_A)` or `(δ_B,δ_B)` has TV `0`.

Within the submitted contract, the answer is not merely an unachievable numeric ceiling: finite generator sets and compact row polytopes ensure an optimum exists. The `selected_pair` backpointers provide local minimizers, and following them from the root specifies one consistent vertex choice per reached history. My fresh harness reconstructed that pair of full vertex policies and measured its direct trace TV; all 120 witness TVs equaled the reported value. That feasibility is only with respect to the synthetic input contract, not an external service.

### Edge semantics checked

* A missing row is the full simplex over the whole declared alphabet, not a zero row or a zero-radius guess.
* A child is entered only when both scenario prefix masses are positive; zero-overlap branches need no suffix state. STOP is handled immediately with weighted `min` and excluded from post-STOP states.
* `require_stop_by_horizon` explores all support in every row generator at reachable histories. The support of a convex mixture is the union of generator supports, so checking that union is sufficient. When the flag is false, the law covers the first `H` symbols and does not imply termination.
* Errors, retries, and statuses have no implicit control behavior. They must be represented as visible symbols; the contract must explicitly emit STOP to terminate.
* History keys distinguish ordered prefixes; unequal left/right prefix masses remain in the DP key. The unequal-mass fixture reports exact TV `1/2`, versus `1` from the earlier coarser pathwise bound.

## Replay audit

`verify` does not call `certify`. It derives the expected reachable DP-state closure from the root by expanding every left/right generator pair and every symbol with positive mass on both sides; it rejects both missing states and extra states. It then processes the closure deepest-history-first, recomputes every generator-pair objective and local minimum, checks each recorded state value and selected pair, and verifies the declared root overlap and `TV = 1 - overlap`. With finite row products and a strict history depth increase, deepest-first order is topological. STOP branches are checked directly; terminal horizon states are checked against `min(left_mass,right_mass)`. This is enough to prevent a stale root claim or a certificate that omits a candidate branch.

Replay is separately structured but shares implementation primitives with production: contract parsing and `Contract`, `_row`/full-simplex expansion, `_mul`, `_add`, STOP, and state sorting. It does not share the producer's recursive memoized `solve` routine. The exhaustive development oracle also reconstructs policies and trace laws directly, but imports the production parser/row lookup through the test module. Describe these as executable replayers/oracles with shared parsing/row primitives, not as formally verified or wholly independent implementations.

Malformed duplicate keys, non-UTF-8, lone surrogates, floats/exponents, strict types (including Boolean-as-integer traps), invalid rationals, duplicate rows/generators, contract-digest mismatch, invalid certificate types, altered totals, and cap exhaustion have targeted tests. Atomic output tests confirm an existing certificate file is not replaced when the computation or output cap fails. The JSON CLI path is bounded before decode and uses atomic replace after complete output construction.

## Findings at initial revision and follow-up repair verification

**[Fixed; no error found in accepted mathematical values] Certificate item-count cap was not closed across producer/parser/direct replay.**

At the audited source revision, `MAX_JSON_ITEMS` is 200,000; `MAX_DP_STATES` is 30,000; the maximum serialized certificate body is 3,999,999 bytes plus the CLI newline. `_certificate_bytes` checks serialized bytes but does not check JSON-tree items. `verify` checks certificate-specific list and field limits but does not call `_validate_json_tree` for a direct `raw_certificate` object.

The concrete valid contract below uses alphabet `{"A", __STOP__}`, horizon 3, and `require_stop_by_horizon=true`. Each scenario's root row has 32 positive `A/STOP` generator distributions (`i/33`, respectively `i/35`, for `i=1..32`); each scenario's row after `A` has five positive distributions (numerators `37,41,43,47,53` over denominators `107` and `109`); and both `AA` rows deterministically emit STOP. It creates 26,625 reachable certificate states and a 2,951,087-byte certificate, within the DP-state and output-byte limits. But `parse_json_bytes(encoded + newline)` rejects the same generated certificate with `ContractError: ... exceeds the 200000-item limit`. The direct `verify(raw, cert)` path accepts it when the active item limit is set to 1,000 even though the raw contract is below 1,000 items and the parser rejects that certificate. Thus the documented bounded-JSON roundtrip is not guaranteed, and API versus CLI verification behavior diverges.

Reproducer: [`cap_regression.py`](cap_regression.py). It constructs only this public synthetic contract and writes no files. A safe fix should either reject over-item-count certificates during `certify`/serialization before output replacement, or otherwise constrain generated state count so every emitted certificate fits both the byte and tree-item limits. `verify` should enforce the generic tree/item bound for direct-object callers as well as the CLI parser. Add a regression requiring either fail-closed generation or successful bounded-parser roundtrip, plus direct verifier rejection of an oversized raw certificate. Re-run the atomic-existing-output test after repair.

This was a finite resource/readability defect, not a counterexample to the Bellman value for accepted contracts. In the repaired revision, certificate serialization validates the strict JSON tree/item/estimated-size limits before returning bytes, and direct-object replay applies that same serialization guard. The large repro now has three observed behaviors: the bounded parser rejects the manually oversized certificate, direct `verify` rejects it under the default item cap, and `certify` fails closed under default caps before returning the artifact.

**[Fixed; no error found in accepted mathematical values] Generated prefix-mass rationals could exceed the parser's input-token digit cap.**

At the audited revision, both input rows and certificate state masses pass through `_fraction(..., certificate=True)` with the same 48-decimal-digit numerator/denominator limit. The arithmetic layer separately permits exact numerators and denominators up to 4096 bits. The limits are inconsistent: multiplying two legal 47-digit input denominators can produce a legal 93-digit prefix denominator, well below 4096 bits. `certify` emits that exact state mass, then `verify` rejects its own output using the input-rational cap.

Reproducer: [`rational_roundtrip_regression.py`](rational_roundtrip_regression.py). It uses horizon 3 and alphabet `{"A", __STOP__}`. In both scenarios, the root row emits `A=1/d1`, `STOP=(d1-1)/d1`, and the row after `A` emits `A=1/d2`, `STOP=(d2-1)/d2`, with `d1=10^46+33` and `d2=10^46+79`; the row after `AA` emits STOP deterministically. Every input rational has at most 47 digits per part; the contract parses, and `certify` emits three states, including exact mass `1/(d1*d2)` with a 93-digit denominator. `verify(raw, certificate)` then raises `ContractError: certificate.states[2].left_mass exceeds the 48-digit rational limit`. The generated state arithmetic is around 310 bits, comfortably below the 4096-bit bound.

The repaired revision separates input-token and certificate-rational budgets. Certificate parsing bounds decimal parts by the configured arithmetic-bit representation and checks parsed/reduced numerator and denominator sizes against `MAX_ARITHMETIC_BITS`, preserving exact arithmetic within the stated bound. The 93-digit-prefix-mass reproducer now certifies and replays successfully (`TV=0`). This was independent of the item-count/output-byte issue above; both repairs were verified.

**[Fixed; no error found in accepted mathematical values] The producer state cap did not reserve states still being evaluated.**

At the prior revision, the recursive producer enforced `MAX_DP_STATES` using the count of completed memo entries. Ancestor states were not added to the memo until their child recursion returned, so the depth-first call stack could have more live states than the configured cap. The minimal counterexample is a horizon-one contract with a deterministic `A` row in each scenario: there is a root state and a terminal `A` state. Under `MAX_DP_STATES=1`, the earlier producer could return a two-state certificate; replay's state-list/closure cap rejected it. The repaired producer monotonically reserves each unseen state before descending. The new test confirms cap 1 fails closed and cap 2 emits and verifies exactly two states. Histories strictly increase on recursion, so there is no same-prefix re-entrant state reservation.

### Follow-up validation at repaired revision

| Check | Result |
|---|---|
| `python3 -B -m unittest -v test_exact_uncertain_distance.py` from the implementation directory | 21/21 pass, including item-cap, generated-rational, reserved-ancestor, and interpreter-independent JSON-depth regressions |
| [`cap_regression.py`](cap_regression.py) | 26,625-state / 2,951,087-byte manually materialized certificate is rejected by parser and direct `verify`; default `certify` fails closed under the item cap |
| [`rational_roundtrip_regression.py`](rational_roundtrip_regression.py) | 3 states; 93-digit prefix denominator accepted within arithmetic bits; cert/verify roundtrip passes, TV `0` |
| [`independent_crosscheck.py`](independent_crosscheck.py) | 120 fresh seeded contracts; 1,888 direct policy-law pairs; 120 values and selected-policy witnesses match; four tamper cases rejected |
| `run_experiments.run()` in memory | 26 contracts; 20,739 exhaustive cross-scenario law pairs; zero mismatches; no result file written |
| Final implementation SHA-256 | `d6136bed1de6fd5ba704a9bf1a79e4d20b6d942d771dba2c1d7460e2c561722c` |
| Final unit-test source SHA-256 | `fced91fde0760e3951797baa6ad8953770947dcb1354784838a0bb66a696bbff` |

### Adjacent producer cap check: robust usage

A separate read-only check found and then verified a repair to the neighboring `robust_usage` producer. Before its patch, a synthetic chain with horizon 1,002 and 1,000 explicit `A^k` rows (each scenario has the same `A=1/2, B=1/2, __STOP__=0` center and zero radius) had 513,509 input-tree items and 2,149,126 compact input bytes. Under the actual defaults, `certify` returned 2,001 certificate rows with 1,029,028 JSON-tree items and 13,748,735 pretty-printed bytes, within its 16 MB output limit; `replay` rejected that returned object at the 1,000,000-item cap. Thus the old producer's byte-only check did not ensure its certificate was readable under the item cap.

The current producer validates the full certificate tree before returning it and includes its trailing newline in the output-byte budget. The retained synthetic probe [`robust_usage_cap_probe.py`](robust_usage_cap_probe.py) now confirms that the same 513,509-item input fails closed with `UnverifiableContract: certificate exceeds the 1000000-item limit`. The neighboring robust-usage suite passes 23/23, including producer/replay cap consistency and nesting-depth tests. Audited robust producer SHA-256 `0c31a674ecd1f56729c500909f4aa01942be75648388139546d7e17bcdfa958d`; test SHA-256 `e4f7da1c6b9286d3dc797505c93c48295884485c14ac137607e7489bcff40a49`.

## Validation performed

| Check | Result |
|---|---|
| `python3 -B -m unittest -v test_exact_uncertain_distance.py` | 17/17 pass |
| `run_experiments.run()` called in memory (not `main`; did not rewrite `experiment_results.json`) | 26 contracts, pass; 201 left policy-laws and 361 right policy-laws enumerated in aggregate; 20,739 cross-scenario policy-law pairs; 0 mismatches |
| Fresh direct vertex-policy/law enumeration | 120 seeded contracts; 1,888 policy-law pairs; all 120 producer values matched direct whole-law TV; all 120 selected-pair witnesses attained the result |
| Fresh certificate attacks | Omitted closure state, extra unreachable mass state, wrong generator-pair index, and wrong terminal Bellman value all rejected |
| Generated-certificate cap reproduction | Finding reproduced as described above |
| Source/heldout/provider activity | No provider call, credential access, heldout read, or original workflow execution |

The fresh crosscheck script is [`independent_crosscheck.py`](independent_crosscheck.py); it constructs its raw contracts, row lookup, missing-row simplex, trace laws, padding, and direct TV without calling the subject parser, `_row`, certifier recurrence, or test oracle. It uses `certify` only to compare the value/backpointers, then invokes `verify` as a separate check.

## Nearby primary theory and positioning

These sources establish close ingredients and constrain novelty; none should be presented as identical to this finite output objective:

* Tzortzis, Charalambous & Charalambous, [“Dynamic Programming Subject to Total Variation Distance Ambiguity,” SIAM J. Control Optim. (2015), DOI 10.1137/140955707](https://doi.org/10.1137/140955707), with detailed [arXiv primary text](https://arxiv.org/html/1402.1009). It studies minimax control/expected cost under TV ambiguity of conditional distributions and derives dynamic-programming recurrences. This is a substantial prior for conditional TV-ball dynamic programming, although the payoff and optimization are different. Its TV **norm** convention has range up to 2, while this implementation's probability TV is `1/2 L1` in `[0,1]`; radius numbers require normalization before comparison. OpenAlex cross-check: W1584593412 for the SIAM record and W2950828668 for arXiv.
* de Cooman, Hermans & Quaeghebeur, [“Imprecise Markov chains and their limit behaviour,” arXiv:0801.0980](https://arxiv.org/html/0801.0980), develops credal transition sets and lower/upper expectation analysis. This is direct background for uncertain Markov rows, not this exact trace-overlap objective.
* de Cooman & Hermans, [“Imprecise probability trees: Bridging two theories of imprecise probability,” arXiv:0801.1196](https://arxiv.org/html/0801.1196), treats imprecise probability trees/local uncertainty.
* Chen & Kiefer, [“On the Total Variation Distance of Labelled Markov Chains,” DOI 10.1145/2603088.2603099](https://doi.org/10.1145/2603088.2603099), with [arXiv primary text](https://arxiv.org/html/1405.2852), analyzes trace TV for precise labelled Markov chains. It is close in observer/metric but not a row-uncertain robust contract.
* Bian & Abate, [“On the Relationship between Bisimulation and Trace Equivalence in an Approximate Probabilistic Context,” arXiv:1701.04547](https://arxiv.org/abs/1701.04547), is relevant to finite trace-TV and approximate probabilistic bisimulation.

The existing README's cautious positioning is right: this is a small exact artifact-level checker built from known TV, coupling/overlap, credal-row, and finite-trace methods. Do not claim a new robust-Markov, imprecise-probability, coupling, or automata-distance theorem, or a provider-calibration result. The useful engineering delta is exact weighted-overlap DP for a declared **rectangular** pair of rational row-polytope trace models, with unequal prefix masses retained and replayed.
