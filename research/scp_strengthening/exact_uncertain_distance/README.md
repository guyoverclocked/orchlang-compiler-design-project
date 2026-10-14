# Exact bounded trace distance for rectangular row polytopes

This directory prototypes an exact-rational checker for the worst-case total-variation distance between two bounded observable-trace laws. At every scenario and complete visible history, the input declares a finite list of rational probability vectors. The allowed row is their convex hull. A missing live row means the full simplex over the declared alphabet. The result is exact for that finite row contract; it does not show that a provider or workflow satisfies the contract.

The result improves on the older sufficient pathwise bound in `../robust_usage/`: it carries both scenario prefix masses through the overlap calculation, rather than replacing each next-prefix value by the minimum continuation survival. It is a bounded artifact-level checker, not a source adapter or provider validator.

## Recurrence and premises

For a common visible history `h`, let `a` and `b` be the masses reaching it in the left and right laws. Let `U_left(h)` and `U_right(h)` be the declared row polytopes. With `C_h(a,b)` denoting the minimum weighted overlap of all suffix laws, use

```text
C_h(a,b) = min_{p0 in U_left(h), p1 in U_right(h)}
            sum_y C_{h y}(a p0(y), b p1(y))
```

At horizon `H`, `C_h(a,b)=min(a,b)`. If `y` is `__STOP__`, the trace is padded with `__STOP__` and that branch contributes `min(a p0(y), b p1(y))` immediately. The reported worst-case trace TV is `1 - C_empty(1,1)`.

The exactness premises are explicit:

* The alphabet is finite, shared by both scenarios, and contains every event the observer can see. Outputs outside it violate the model premise.
* The row for a history conditions on that entire visible prefix. Row uncertainty is compact and convex; this prototype represents each polytope as the convex hull of the listed rational generators.
* Choices are rectangular: each scenario/history row can be selected independently of every other row and of the other scenario's rows. A shared hidden parameter, shared randomness, temporal parameter, or cross-scenario coupling is not represented.
* The horizon is finite. `require_stop_by_horizon: true` additionally checks that every possible trace in each scenario emits `__STOP__` by slot `H`. Otherwise the result covers only the first `H` symbols. After the first stop, the trace is padded deterministically with `__STOP__`.

An error, retry, route choice, or usage record is an ordinary visible alphabet symbol. Its status and any fields to be compared must be encoded in the symbol. An error does not implicitly terminate; a terminal path must emit `__STOP__`. The checker does not infer retries, exceptions, or provider billing semantics.

### Why the generator-pair reduction is valid

For fixed normalized suffix laws `Q0,Q1`, weighted overlap is

```text
sum_z min(a Q0(z), b Q1(z)) = (a+b - ||a Q0 - b Q1||_1) / 2.
```

Taking the minimum over all rectangular suffix-law pairs is therefore `(a+b - D(a,b))/2`, where `D` is the supremum of convex weighted `L1` norms. Thus `D` is convex and `C` is concave and positively homogeneous in the two masses. Assuming the child values are concave, each local objective is a sum of concave functions of the current row pair, after linear mass scaling. A concave function on a compact polytope has a minimum at an extreme point. More directly, because each row set is defined as the convex hull of its supplied generators, the minimum over a row-pair hull is attained at one of the listed generator pairs. The recursion follows by partitioning suffix overlap by the next visible symbol; rectangularity lets each child row subtree be minimized independently.

This argument does **not** apply to a nonrectangular set where a hidden/global parameter ties rows together. For example, if one shared parameter forces both scenarios to choose `δ_A` or both to choose `δ_B`, their paired-law worst TV is `0`; giving each scenario the row projection `{δ_A,δ_B}` and treating choices independently instead computes `1`. The latter is exact only for the rectangular product contract. It is a conservative superset if the true paired set is the tied subset, but it is not an exact answer about that subset.

## A strict improvement over the pathwise bound

`examples/unequal_prefix_mass.json` has horizon two. Both models choose `A` or `B` with probability `1/2`; after `A`, left emits `C` and right emits `D`, while after `B` both emit `C`. The exact trace TV is `1/2`: only the `A` half of the probability mass distinguishes the laws. The previous pathwise recurrence sees child continuation bounds `0` and `1`, takes their minimum at the root, and reports `1`. This is a concrete case where retaining the unequal masses is useful.

Run the producer and independent certificate replay with:

```sh
python3 exact_uncertain_distance.py certify examples/unequal_prefix_mass.json --out /tmp/exact-distance.json
python3 exact_uncertain_distance.py verify examples/unequal_prefix_mass.json /tmp/exact-distance.json
python3 -m unittest -v test_exact_uncertain_distance.py
```

## Certificates and resource behavior

The certificate binds to the canonical input SHA-256 digest and records the exact overlap value and selected generator pair for each memoized `(history, left_mass, right_mass)` state. Replay derives the complete subproblem closure from every row-pair generator, then recomputes all local minima bottom-up. It checks that no subproblem was omitted and that the reported TV is exactly one minus root overlap. This is an independently structured executable replay, not a formally verified checker.

JSON duplicate keys, invalid UTF-8, escaped lone surrogates, floats/exponents, wrong JSON types (including Boolean values where integer indexes are required), malformed rational strings, duplicate histories or generator distributions, and rows outside the declared alphabet fail closed. Duplicate distributions are compared after rational normalization, so `1/2` and `2/4` cannot list the same generator twice. Missing rows conservatively become full-simplex generator rows. Input/output bytes, tree items and nesting (64 levels), alphabet/horizon, rows, generators, DP states, stop-check states, row-pair work, rational digits and intermediate arithmetic bits are bounded. Each row-pair candidate charges work proportional to alphabet width before evaluating its children. Every produced certificate must satisfy the reader's tree and byte caps, including direct-object replay. Unfinished recursive states are reserved before descent. Input row rationals are limited to 48 digits per part; certificate rationals may use the full 4,096-bit intermediate domain, with a bounded decimal representation. The output byte cap leaves room for the CLI newline under the same input parser limit, so emitted certificates remain replayable. Cap exhaustion raises an unverifiable error before a certificate is returned or an output file is replaced. File output is staged and atomically replaced only after full construction.

The explicit alphabet still is an external premise: a finite contract cannot conservatively account for an unmodeled output token unless the observer first maps it to a declared symbol. Likewise, `require_stop_by_horizon` proves termination only in this finite contract, not for the original system beyond its declared event model.

## Reproducible bounded experiments

Run the independent whole-law oracle and certificate replay suite with:

```sh
python3 -m unittest -v test_exact_uncertain_distance.py
python3 run_experiments.py
```

The runner writes `experiment_results.json`. The checked development run covers 26 finite contracts: the decisive fixture, uncertainty-set expansion/order and projection checks, STOP/error handling, the shared-global-parameter counterexample, and 18 deterministic random tiny contracts. The exhaustive reference enumerates complete deterministic row-generator policies, constructs the padded trace laws, and compares every left/right law pair by direct finite-alphabet TV. It shares the strict contract parser, but uses neither the production Bellman recurrence nor certificate replay. The checked run enumerated 201 left policies and 361 right policies and compared 20,739 cross-scenario policy-law pairs, with zero exact/oracle mismatches and zero certificate replay failures. The H=10 test separately exercises the maximum supported recursion depth. These are bounded implementation checks, not a proof for unbounded instances.

The sanity fixtures check that expanding a row uncertainty set cannot lower worst-case TV, permuting generator order preserves the value, and a deterministic symbol projection cannot increase TV. They also show why shared latent parameters are outside the rectangular exactness claim: the tied paired model has worst TV 0 while its independent row-product projection has TV 1.

## Prior-art boundary

This recurrence uses established ingredients rather than claiming a new theorem. Work on total-variation ambiguity already develops dynamic programming for uncertain conditional distributions ([Tzortzis, Charalambous & Charalambous](https://arxiv.org/abs/1402.1009)). Imprecise Markov chains and probability trees already represent row-wise credal sets and local uncertainty models ([de Cooman, Hermans & Quaeghebeur](https://arxiv.org/abs/0801.0980), [de Cooman & Hermans](https://arxiv.org/abs/0801.1196)); ergodicity coefficients for imprecise Markov chains are an adjacent distance-related line ([Škulj & Hable, ISIPTA 2009](https://leo.ugr.es/sipta/isipta09/proceedings/039.html)). For precise models, quantitative full-trace TV for labelled Markov chains is established ([Chen & Kiefer, LICS 2014](https://arxiv.org/abs/1405.2852)), as are finite-horizon trace bounds from approximate bisimulation ([Bian & Abate](https://arxiv.org/abs/1701.04547)).

OpenAlex was used to discover and cross-check this neighborhood, then claims were checked against primary arXiv/proceedings sources. The search was not systematic or exhaustive. A defensible description is an exact bounded checker for a particular full-history rectangular rational row contract, with a useful unequal-mass result. Do not claim a new robust-Markov, credal-network, coupling, or automata-distance theorem; do not claim provider validation or a breakthrough.
