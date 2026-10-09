# Sources for the current OrchLang review deck

This register supports the revised 32-slide deck source. The deck source puts project paths and this register in speaker notes for the relevant slide. Rebuild/export only after all project result files match the refreshed final `audit/final/manifest.json`.

## Relational security and resource reasoning

1. Gilles Barthe, Pedro R. D'Argenio and Tamara Rezk. “Secure Information Flow by Self-Composition.” IEEE Computer Security Foundations Workshop, 2004. [DOI](https://doi.org/10.1109/CSFW.2004.1310735). Foundational two-run reduction.
2. Gilles Barthe, Juan Manuel Crespo and César Kunz. “Product Programs and Relational Program Logics.” Journal of Logical and Algebraic Methods in Programming 85(5), 2016. [DOI](https://doi.org/10.1016/j.jlamp.2016.05.004). Product constructions and relational verification.
3. Van Chan Ngo, Mario Dehesa-Azuara, Matthew Fredrikson and Jan Hoffmann. “Verifying and Synthesizing Constant-Resource Implementations with Types.” IEEE Symposium on Security and Privacy, 2017, pp. 710–728. [DOI](https://doi.org/10.1109/SP.2017.53) · [extended author version](https://arxiv.org/abs/1801.01896). Resource-aware information-flow reasoning.
4. Ezgi Çiçek, Gilles Barthe, Marco Gaboardi, Deepak Garg and Jan Hoffmann. “Relational Cost Analysis.” POPL 2017, pp. 316–329. [DOI](https://doi.org/10.1145/3009837.3009858) · [author paper](https://people.mpi-sws.org/~dg/papers/popl17.pdf). Relational cost reasoning.
5. Van Chan Ngo, Fabio Carbonneaux and Jan Hoffmann. “Bounded Expectations: Resource Analysis for Probabilistic Programs.” PLDI 2018, pp. 496–512. [DOI](https://doi.org/10.1145/3192366.3192394) · [preprint](https://arxiv.org/abs/1711.08847). Expected resources for probabilistic programs.

## Quantitative information flow and probabilistic bisimulation

6. Geoffrey Smith. “On the Foundations of Quantitative Information Flow.” FOSSACS 2009. [DOI](https://doi.org/10.1007/978-3-642-00596-1_21).
7. David Basin and Boris Köpf. “An Information-Theoretic Model for Adaptive Side-Channel Attacks.” ACM CCS 2007. [DOI](https://doi.org/10.1145/1315245.1315282) · [author PDF](https://people.inf.ethz.ch/basin/pubs/ccs07.pdf).
8. Kim Guldstrand Larsen and Arne Skou. “Bisimulation through Probabilistic Testing.” Information and Computation 94(1), 1991. [DOI](https://doi.org/10.1016/0890-5401(91)90030-6). Foundational probabilistic bisimulation.
9. Kamaleson, Parker and Rowe. “Finite-Horizon Bisimulation Minimisation for Probabilistic Systems.” SPIN 2016. [DOI](https://doi.org/10.1007/978-3-319-32582-8_10) · [author-hosted paper](https://www.cs.ox.ac.uk/david.parker/papers/spin16fh.pdf). Finite-horizon probabilistic partition refinement.
10. Gilles Barthe et al. “Relational Reasoning via Probabilistic Coupling.” LPAR 2015. [DOI](https://doi.org/10.1007/978-3-662-48899-7_27). Standard coupling foundation for the conditional kernel corollary.

## LLM workflow and security systems

11. Louis Mandel, Guillaume Baudart, Mandana Vaziri and Martin Hirzel. “PPDL: LLM-Based Flows as Probabilistic Programs.” ICML 2026, PMLR 306:86172–86197. [PMLR proceedings](https://proceedings.mlr.press/v306/mandel26a.html) · [arXiv preprint](https://arxiv.org/abs/2608.05234). Models uncertainty across multi-call LLM/tool flows; this deck does not claim probabilistic LLM analysis is absent.
12. Kevin Dickerson. “Statically Bounding Resource Accumulation in LLM Agent Workflows: The Cost Case.” Loom Research, 18 May 2026. [Author-hosted note](https://loom.technology/research/bounded-llm-cost/). Restricted Petri-net method for unary cumulative resources. This was author-reported and unrefereed in the literature review.
13. Melwin Xavier et al. “Agentproof: Static Verification of Agent Workflow Graphs.” 2026. [arXiv:2603.20356](https://arxiv.org/abs/2603.20356). Preprint; adjacent graph and policy checks.
14. Basavesh Ammanaghatta Shivakumar, Swarn Priya and Peng Gao. “AgentFlow: A Flow-Centric Policy Language and Framework for Securing LLM Agent Systems.” 2026. [arXiv:2608.22868](https://arxiv.org/abs/2608.22868). Preprint; includes bounded verification and runtime monitoring.
15. Roy Weiss, Daniel Ayzenshteyn, Guy Amit and Yisroel Mirsky. “What Was Your Prompt? A Remote Keylogging Attack on AI Assistants.” USENIX Security 2024, pp. 3367–3384. [USENIX paper](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss). Motivation for observable output length channels; its observer differs from this project's usage records.

## Probabilistic automata and weighted trace equivalence

16. Wen-Guey Tzeng. “A Polynomial-Time Algorithm for the Equivalence of Probabilistic Automata.” *SIAM Journal on Computing* 21(2), 1992, pp. 216–227. [DOI](https://doi.org/10.1137/0221017). Foundational finite-word equivalence algorithm.
17. Stefan Kiefer, Andrzej S. Murawski, Joël Ouaknine, Björn Wachter and James Worrell. “Language Equivalence for Probabilistic Automata.” CAV 2011, LNCS 6806, pp. 526–540. [DOI](https://doi.org/10.1007/978-3-642-22110-1_42) · [author paper](https://people.mpi-sws.org/~joel/publications/langeqprobaut11.pdf). Describes basis exploration over word-generated distribution vectors.
18. Stefan Kiefer et al. “APEX: An Analyzer for Open Probabilistic Programs.” CAV 2012, LNCS 7358, pp. 693–698. [DOI](https://doi.org/10.1007/978-3-642-31424-7_51). Applies probabilistic-program equivalence checking to security properties including anonymity.
19. Stefan Kiefer et al. “On the Complexity of Equivalence and Minimisation for Q-weighted Automata.” *Logical Methods in Computer Science* 9(1), article 8, 2013. [DOI](https://doi.org/10.2168/LMCS-9(1:8)2013). Rational weighted-automata equivalence and minimisation.
20. Nathanaël Fijalkow, Stefan Kiefer and Mahsa Shirmohammadi. “Trace Refinement in Labelled Markov Decision Processes.” *Logical Methods in Computer Science* 16(2), 2020, article 10. [DOI](https://doi.org/10.23638/LMCS-16(2:10)2020). Defines finite trace probabilities and studies equivalence/refinement.

## Project artifacts and result provenance

- [`docs/FINAL_PUBLICATION_REVIEW.md`](../../docs/FINAL_PUBLICATION_REVIEW.md): final independent publication assessment; numerical ratings are internal review aids, not journal ratings or acceptance probabilities, and are kept off the main slides.
- [`docs/PAPER.md`](../../docs/PAPER.md) and [`submission/research/manuscript/OrchLang_SCP_OSP.tex`](manuscript/OrchLang_SCP_OSP.tex): current method, assumptions and contribution boundary.
- [`docs/FORMAL_CONTRACT.md`](../../docs/FORMAL_CONTRACT.md): bounded and cyclic relational contracts.
- [`docs/PROBABILISTIC_CHANNELS.md`](../../docs/PROBABILISTIC_CHANNELS.md): exact finite usage-channel model, observers, metrics and limitations.
- [`docs/TRACE_EQUIVALENCE.md`](../../docs/TRACE_EQUIVALENCE.md): finite row-span method, independent replay contract and scope limits.
- [`docs/SOURCE_GRAPH_BRIDGE.md`](../../docs/SOURCE_GRAPH_BRIDGE.md): supported OrchLang source subset and bridge evidence.
- [`integrations/langgraph/source_frontend/README.md`](../../integrations/langgraph/source_frontend/README.md): restricted source AST scope.
- [`bench/results/relational_stress.json`](../../bench/results/relational_stress.json): independent full-text bounded stress report.
- [`bench/results/graphs.json`](../../bench/results/graphs.json): cyclic fixture report and finite witnesses.
- [`bench/results/langgraph_source_study.json`](../../bench/results/langgraph_source_study.json) and [`bench/results/langgraph_integration.json`](../../bench/results/langgraph_integration.json): source-level and pinned-runtime studies.
- [`bench/results/probabilistic_channels.json`](../../bench/results/probabilistic_channels.json): finite channel aggregate; selected hook reports are in the adjacent `probabilistic_channels/` directory.
- [`bench/results/stochastic_bisimulation.json`](../../bench/results/stochastic_bisimulation.json): final all-horizon stochastic-bisimulation fixture and replay report, bound by the 44-stage final manifest.
- [`bench/results/trace_equivalence.json`](../../bench/results/trace_equivalence.json): final exact finite-word equivalence cases, witness cases, cap probes, and independent replay attestations; SHA-256 `9dddb048e411960b07c070c7fff2b169361c1df84ce786cfdb73b524bb56c861`.
- [`research/trace_equivalence_primary_sources.md`](../../research/trace_equivalence_primary_sources.md): source verification and the exact prior-art boundary for row-span equivalence.
- [`audit/final/manifest.json`](../../audit/final/manifest.json): final 44-stage reproduction gate; SHA-256 `65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035`. The presentation builder verifies complete sanitized/package-validated status and hashes for all reports used on slides.

## Claim boundary

The software specializes established relational verification, quantitative information flow, probabilistic bisimulation and weighted-automata equivalence to an explicit model-call usage observer. The cyclic static result is conditional on model-to-graph fidelity and a shared complete-outcome relation; productive cycles support finite usage prefixes only. The strong-bisimulation checker proves equal ordered success-only laws only when its sufficient stable relation succeeds; a split is inconclusive. The exact rational row-span checker can prove all finite ordered words equal in some split cases or return a finite distinguishing word. It compares stopped and nonterminal mass under a finite supplied success-only kernel, and reports no partial claim at resource caps. The channel analyzer computes selected finite observations under supplied rational kernels. None validates a provider distribution, request serialization, invoice, termination probability or cumulative cost for an infinite cycle. The row-span decision method and security use of equivalence predate this project; the contribution is a finite LLM-usage specialization and replayable certificate path.
