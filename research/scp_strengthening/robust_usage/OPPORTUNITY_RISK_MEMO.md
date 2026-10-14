# Opportunity and risk memo: robust declared usage kernels

## Recommendation

The best near-term strengthening is a **finite, bounded, misspecification-aware trace contract**: instead of claiming exact equality for two declared usage kernels, accept a rational total-variation radius around each history-conditioned row and certify an upper bound on distinguishability for every concrete kernel inside those row balls. Include retry/call records, visible termination, and the observer's complete bounded history in the finite alphabet. The result is conditional on those row contracts.

This is a useful upgrade to the assurance boundary, but the mathematical ingredients are established. I do **not** recommend claiming a new coupling theorem, new adaptive-composition theorem, new probabilistic-automata result, or a provider guarantee. The sound contribution would be an inspectable finite contract and replayable bound integrated with the source-to-observer pipeline, plus a study showing exactly when it returns a useful bound. The checker prototype in this directory explores that claim without touching the core solver.

## Why this avenue is the strongest practical opportunity

Exact rational usage-law equivalence presumes that each supplied row is the law to be analyzed. A row-wise total-variation (TV) allowance makes misspecification explicit: for scenario `s` and every observed prefix `h`, the concrete next-observation kernel `P_s(·|h)` must satisfy `TV(P_s(·|h), Q_s(·|h)) ≤ ρ_s(h)`, where `Q` and `ρ` are rational and part of the checked contract. At a common prefix, triangle inequality yields the local cross-scenario bound

`d(h) = min(1, TV(Q_0(·|h), Q_1(·|h)) + ρ_0(h) + ρ_1(h))`.

A finite-horizon maximal-coupling recurrence composes these bounds over **shared observable prefixes**, rather than comparing unconditional per-call marginals. A prefix-tree recurrence can preserve history-dependent local bounds and be tighter than taking one worst-case bound per level. Its contract is finite and executable, while missing or unvalidated rows must become `d=1`/unknown rather than silently becoming exact. Exact arithmetic avoids numerical rounding in the certificate.

For a fixed horizon `H`, a visible `STOP` symbol followed by deterministic `PAD` symbols makes stop position part of the trace. A call/retry attempt is one observable symbol (or a finite record of fields selected by the declared observer). If completion by `H` is required, the contract must prove that no scenario can emit a non-`STOP` event at the final slot; otherwise the result concerns only the first `H` observations and says nothing about later behavior. A retry cap is therefore a semantic assumption, not a sampling convenience.

## Novelty and risk assessment

| Candidate | Assessment | Main reason |
|---|---|---|
| Robust TV balls around declared rows, with bounded history and stop events | **Best artifact-level extension; weak theory novelty** | TV triangle inequality plus sequential maximal coupling is standard. The value is a finite contract that keeps model uncertainty, observed history, stop/retry behavior, and replay evidence explicit. |
| Report a single per-call marginal TV and sum it | **Reject as unsound for history-dependent traces** | Equal marginals do not imply equal joint laws. Conditioning on the full shared observer prefix is essential. |
| Claim generic adaptive TV/privacy composition | **Reject as novel** | Approximate relational logics and tight adaptive DP composition already give powerful compositional theories. The TV bound discards likelihood-ratio structure and is not a substitute for advanced DP accounting; it may be weaker when a richer `(ε,δ)` contract is available. |
| General set-valued probabilistic automata / robust model checking | **Known neighborhood; scope is too broad for this patch** | Interval and imprecise Markov models already quantify over transition uncertainty. A competitive new decision procedure would require more than adding row radii. |
| Learn or statistically calibrate provider kernels and call the result a guarantee | **Reject without a separate coverage theorem and sampling design** | Empirical fit, confidence intervals, or held-out calibration do not imply that the real future provider kernel lies inside the declared set. Any calibration evidence must remain an external premise, separately reported and labeled. |
| Abstraction-refinement for hidden workflow state | **Promising follow-on, high semantic risk** | It could derive sound history-conditional row envelopes from hidden states, but must account for posterior changes after each visible history. A statewise bound alone can fail if the two scenarios couple different hidden states or if abstraction merges states with different future laws. |

The novelty bar should be framed as: **Does OrchLang construct or check the complete finite row contract from its accepted source fragment and observer, then replay a nontrivial robust bound?** If it only accepts hand-written rows and evaluates the recurrence, call it a robust checker feature or worked application, not a new formal method. The existing checked corpus had no admitted external Python candidate, so it cannot carry an external-transfer claim.

## Relation to established work

* **Probabilistic automata and weighted automata.** Kiefer et al. already decide equivalence for rational weighted automata, including expectation and distribution equivalence for probabilistic reward automata. OrchLang's exact law checker is an application of this established family of results. Chen and Kiefer study the quantitative full-trace TV distance for labelled Markov chains, including approximation and hardness results. A finite bounded-horizon contract should not be sold as a new automata-distance theory.
* **Probabilistic noninterference and coupling.** Barthe et al.'s approximate probabilistic relational Hoare logic relates output distributions quantitatively and subsumes important DP/noninterference statements. Barthe et al.'s probabilistic product-program account constructs couplings and uses them compositionally. The proposed recurrence is a specific finite-horizon coupling argument; coupling itself is not the contribution.
* **Approximate/differential privacy.** For an adjacent pair of worlds, `TV(P_0,P_1) ≤ β` implies symmetric `(0,β)`-DP for that pair. That conversion is not general confidentiality, does not establish a neighbor relation, and may be much weaker than a useful `(ε,δ)` guarantee. Kairouz, Oh, and Viswanath give tight adaptive composition for `(ε,δ)` mechanisms, so a simple additive-TV result is not a replacement for modern privacy accounting. Rogers et al.'s filters/odometers explicitly study adaptively selected length/privacy parameters and stopping rules; visible stop-time inclusion is already a recognized privacy issue.
* **Uncertainty in probabilistic models.** Sen, Viswanathan, and Agha study interval-valued Markov chains under uncertainty/IMDP semantics and adversarially selected transition distributions. Later imprecise Markov model-checking work continues this line. Thus “robust under uncertain kernels” is established in general; a domain-specific contract must be distinguished by its observer-indexed, full-history usage rows and its source/certificate connection.

## Soundness hazards that the contract must expose

1. **History measurability.** A bound on the unconditional usage distribution of call 2 is insufficient after call 1 is observed. The row must condition on the complete prior observer trace (including request identity, call/retry labels, result-derived control choices, errors, and stop state if those belong to the observer).
2. **Hidden state and coupling alignment.** A per-hidden-state comparison is usable only with an explicit relation/coupling and proof that synchronized observations preserve that relation. Equal state names, equal one-step marginals, or an informal pairing of paths do not establish this. The robust contract avoids requiring hidden-state coupling only if it constrains the actual conditional law of the next observed symbol given the entire visible prefix, after marginalizing hidden states and posterior mixtures.
3. **Adaptive control.** The next request, retry, or exit decision can depend on prior outputs. If it affects the selected observer, it must be present in the history or represented by an abstraction whose conditional rows are proved sound for every hidden posterior.
4. **Stopping and truncation.** A cap on observations does not prove completion by the cap. Include `STOP` and its position. If the result is only an `H`-symbol prefix law, label it that way. A workflow with unbounded retries needs an explicit truncation or a separate termination argument.
5. **Calibration premise.** The theorem says “for every concrete kernel satisfying the row-TV contract.” It does not prove that a vendor satisfies the contract. Measurement data can motivate `ρ`, but making that implication requires its own statistical assumptions and coverage guarantee, which the kernel theorem must not hide.
6. **Observer scope.** The alphabet must explicitly name what is observable. Equality/TV bounds for declared token and stop observations says nothing about output text, latency, cache effects, transport, billing quirks, or other omitted fields.

## Minimal decisive experiment

Use finite exact-rational trees with a declared alphabet and horizon. Compare:

1. the existing exact nominal law result;
2. a structural/request-equality baseline;
3. the robust contract result and its replayable local-row certificate.

Include at least: (a) zero-radius equal laws; (b) two identical per-slot marginals but mutually singular joint traces, proving marginal-only accounting fails; (c) a visible retry/stop-position leak; (d) a case where a shared-history recurrence is strictly tighter than the per-level worst-row product; (e) a sharpness witness where the robust recurrence is attained; (f) a missing-row case returning bound one/unknown; and (g) invalid row/radius and malformed stop-padding rejection. Report certificate size/visited prefix count and runtime as `H` and alphabet size grow. Keep any provider calibration data separate from all theorem inputs.

This experiment can demonstrate that the contract adds a useful robust mode and rejects unsafe simplifications. It cannot demonstrate vendor-kernel coverage, external source applicability, or novelty of the coupling argument.

## Verified primary sources and discovery trail

OpenAlex was used to discover/resolve the formal-methods and composition references below; bibliographic identifiers were then checked against the linked primary paper/proceedings/publisher/author pages. The previous `research/publication_upgrade/literature_verified.md` is the source for the existing LLM-workflow context and current external-corpus limitations.

1. Gilles Barthe, Boris Köpf, Federico Olmedo, and Santiago Zanella-Béguelin. “Probabilistic Relational Reasoning for Differential Privacy.” *ACM TOPLAS* 35(3), 2013. DOI [10.1145/2492061](https://doi.org/10.1145/2492061). The primary author-hosted PDF defines α-distance, approximate probabilistic relational Hoare logic, and quantitative relational output-distribution bounds: [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/2012.POPL_.pdf).
2. Gilles Barthe, Benjamin Grégoire, Justin Hsu, and Pierre-Yves Strub. “Coupling proofs are probabilistic product programs.” *POPL 2017*. DOI [10.1145/3009837.3009896](https://doi.org/10.1145/3009837.3009896); 2016 arXiv preprint [arXiv:1607.03455](https://arxiv.org/abs/1607.03455). Establishes explicit, compositional program-level coupling reasoning.
3. Peter Kairouz, Sewoong Oh, and Pramod Viswanath. “The Composition Theorem for Differential Privacy.” *ICML 2015*, PMLR 37, 2015. [PMLR paper](https://proceedings.mlr.press/v37/kairouz15.html), [PDF](https://proceedings.mlr.press/v37/kairouz15.pdf), DOI [10.1109/TIT.2017.2685505](https://doi.org/10.1109/TIT.2017.2685505). Gives tight adaptive composition and makes clear that DP privacy-region composition is a richer analysis than adding TV radii.
4. Ryan Rogers, Aaron Roth, Jonathan Ullman, and Salil Vadhan. “Privacy Odometers and Filters: Pay-as-You-Go Composition.” *NeurIPS 2016*. [Primary author project page](https://privacytools.seas.harvard.edu/publications/privacy-odometers-and-filters-pay-you-go-composition). Studies adaptive composition where length/parameters depend on previous outcomes and distinguishes stopping filters from odometers.
5. Koushik Sen, Mahesh Viswanathan, and Gul Agha. “Model-Checking Markov Chains in the Presence of Uncertainties.” *TACAS 2006*, LNCS 3920, 394–410. DOI [10.1007/11691372_26](https://doi.org/10.1007/11691372_26); [author record and abstract](https://osl.cs.illinois.edu/publications/conf/tacas/SenVA06.html). Studies interval DTMCs under uncertain-chain and interval-MDP semantics.
6. Taolue Chen and Stefan Kiefer. “On the Total Variation Distance of Labelled Markov Chains.” *LICS 2014*, 33:1–33:10. DOI [10.1145/2603088.2603099](https://doi.org/10.1145/2603088.2603099); [author PDF](https://chentaolue.github.io/pub-papers/lics14.pdf). Studies quantitative trace-law distance and its complexity; this is directly relevant prior art.
7. Stefan Kiefer, Andrzej S. Murawski, Joël Ouaknine, Björn Wachter, and James Worrell. “On the Complexity of Equivalence and Minimisation for Q-weighted Automata.” *LMCS* 9(1:8), 2013. [Primary LMCS article](https://lmcs.episciences.org/908), [PDF](https://lmcs.episciences.org/908/pdf), DOI [10.2168/LMCS-9(1:8)2013](https://doi.org/10.2168/LMCS-9(1:8)2013). Covers rational weighted automata, and probabilistic reward expectation/distribution equivalence.

OpenAlex returns broad cross-topic hits for unquoted queries and was used only as a literature-discovery/metadata tool, not as evidence that the coverage is exhaustive. This is an opportunity memo, not a systematic review or a priority search.
