# Robust bounded usage-trace contract prototype

This directory contains a finite exact-rational checker for a deliberately narrow assurance claim: bound the total-variation distance between two bounded **observable trace** laws when each next-event kernel may differ from a declared center by a stated TV radius. The checker accepts history-dependent rows, a visible stop marker, and checks submitted certificates using local row obligations and required continuation coverage. It does not inspect OrchLang source, call a provider, estimate a provider law, or prove that a provider falls inside the supplied uncertainty sets.

The theory/literature risk assessment is in [OPPORTUNITY_RISK_MEMO.md](OPPORTUNITY_RISK_MEMO.md). The novelty assessment is intentionally modest: the proof below is a finite-horizon maximal-coupling argument using the triangle inequality. The practical extension is the explicit full-history uncertainty contract and its exact certificate boundary.

## Contract meaning

A contract names one finite alphabet `Σ` that contains the reserved event `__STOP__`, a positive horizon `H`, and (possibly partial) paired row entries for two scenarios. An event can be a structured record serialized as a symbol; it should include every field selected by the observer, such as call/retry identity, usage, visible error/return status, and any controller choice that affects later visible behavior. Exact usage counts require finite support or a declared finite abstraction; bucketing counts changes the observer and the theorem's subject. Omitting a field also changes the observer.

For scenario `s∈{left,right}` and each visible history `h` shorter than `H`, an entry gives a rational distribution `q[s,h]` and rational radius `ρ[s,h]∈[0,1]`. The contract asserts, as an external premise, that every concrete conditional row `p[s,h]` obeys

`TV(p[s,h], q[s,h]) ≤ ρ[s,h]`, where `TV(p,q) = (1/2) Σ_y |p(y)-q(y)|`.

The full TV ball is used: positive probability for an event `y` is possible exactly when `q(y)+ρ>0`. A missing paired row on a prefix that can still be shared receives local distance bound one. The checker never interprets missing data as a zero-radius row.

`__STOP__` is visible. Its **first occurrence** identifies the stop position; the bounded trace is padded by repeating `__STOP__` for the remaining slots. Thus a call attempt, retry, and terminal event can be distinguished if their observable event records use distinct alphabet symbols. Since STOP consumes one slot, a limit of `R` attempt records normally needs horizon `R+1` to include a final stop marker. A contract with `require_stop_by_horizon: true` is accepted only if every event sequence permitted by each scenario's row balls reaches `__STOP__` by slot `H`. With that flag false, the guarantee is only for the first `H` observed symbols; it does not imply eventual completion.

## Theorem checked

For each shared prefix `h`, let `q_0,q_1` be the declared centers and `ρ_0,ρ_1` their radii. Define

`d(h) = min(1, TV(q_0,q_1) + ρ_0 + ρ_1)`.

Let `I(h)` be the symbols that can have positive mass under a row in **both** TV balls at `h`. Define a survival lower bound from the leaves upward:

* `s(h)=1` when `|h|=H`;
* after the first `__STOP__`, the next symbol is deterministically `__STOP__`;
* if a live row is missing, or `d(h)=1`, set `s(h)=0`;
* otherwise set `s(h)=(1-d(h)) min_{y∈I(h)} s(hy)`.

Then for every pair of concrete history-dependent kernels satisfying all supplied row contracts,

`TV(P_left^H, P_right^H) ≤ 1 - s(ε)`.

Here `P_s^H` is the law of the length-`H` observer trace, including the first visible stop marker and the repeated-stop padding. The result is a distinguishability bound for this observer and these two scenarios. It becomes a symmetric `(0,β)`-DP statement only if the scenarios are a declared neighboring-input pair and all required neighbor pairs are checked; the checker does not establish either condition.

**Proof sketch.** At a shared prefix, the triangle inequality gives `TV(p_0,p_1)≤d(h)` for the two concrete conditional rows. A maximal coupling of those rows matches the next symbol with probability `1-TV(p_0,p_1)≥1-d(h)`. Any symbol on which a match can occur lies in `I(h)`, so after a match the probability of matching the remaining trace is at least `min_y s(hy)`. Backward induction therefore gives probability at least `s(ε)` that the coupled traces agree completely. The coupling inequality yields `TV(P_left^H,P_right^H)≤1-s(ε)`. If a row is missing, taking its distance as one gives no unsupported continuation claim. This proof is standard coupling machinery specialized to a finite observer-history trie; it is not claimed as a new coupling result.

The recurrence can be sharper than multiplying the worst `d(h)` from each depth: maxima from different histories need not occur along one common trace. It remains a sufficient upper bound and can still be loose because it forgets the exact common-event masses when it recurses using a minimum.

## Running it

The checked example has zero uncertainty radii and deliberately history-dependent centers:

```sh
python3 robust_usage.py certify examples/sharp_history_contract.json --out /tmp/robust-certificate.json
python3 robust_usage.py replay examples/sharp_history_contract.json /tmp/robust-certificate.json
```

Its pathwise certificate is `91/100`; the coarser per-level-max product is `99/100`. The center laws themselves have exact trace TV `91/100`, so this also witnesses sharpness of this instance of the recurrence. The examples are mathematical fixtures only.

The replay path has separate traversal and verifier control flow from certificate production. It shares the strict contract parser and exact row-arithmetic primitives, recomputes the local equations, required prefix closure, root bound, and stop proof, and is **not** a formally verified or structurally independent proof checker.

The implementation rejects horizons above 10,000, alphabets above 128 symbols, more than 50,000 explicit rows/nodes, JSON trees above 1,000,000 values or 64 nesting levels, and input or certificate files above 16 MB. `--max-nodes` is an additional caller-selected cap from 1 through 50,000; certificate construction, replay coverage, and complete-stop traversal each obey it. Both producer and verifier use explicit stacks, so valid horizons do not depend on Python recursion depth. The producer checks its certificate against the same JSON item/depth/byte limits as the reader. Oversize, malformed, incomplete, or over-budget inputs are rejected before any certificate is written; output replacement is atomic for file destinations.

Arithmetic uses Python `Fraction`. JSON probabilities and radii must be nonnegative integers or bounded integer/rational strings such as `3` or `3/7`; decimal and exponent notation, JSON floating-point values, duplicate object keys, invalid UTF-8, and escaped lone surrogates are rejected. Numerator and denominator strings are limited to 128 digits, and an intermediate numerator or denominator above 8,192 bits fails closed as unverifiable. These parsing and resource limits are implementation restrictions, not extra theorem premises.

## Scope and limits

The checker only verifies the finite row arithmetic and its certificate. In particular:

* The caller must justify that each row is the law **conditioned on the entire observer history**, after integrating over hidden workflow state and any posterior changes. Per-call unconditional marginals do not satisfy this premise.
* If a proof uses abstract states instead of actual observer-prefix rows, it needs a sound relation/refinement argument that preserves every synchronized visible history. Merely pairing same-named states is insufficient.
* A finite horizon bounds the certified observation prefix. `require_stop_by_horizon` adds a checkable termination premise; it does not establish behavior after the bound.
* Empirical calibration does not prove future kernels lie in a TV ball. This code neither estimates radii nor turns measurements into a theorem premise.
* Omitted observer fields, including text, latency, cache state, transport, provider billing rules, or other side channels, are outside the bound.
* Worst-case size is exponential in `H` and alphabet size. This prototype targets small explicit contracts, not general probabilistic-automata equivalence or robust model checking.
