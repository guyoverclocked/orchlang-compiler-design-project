# Sources for the provisional cyclic-graph deck

This register supports the current 18-main-slide candidate. The paper title is
frozen as “OrchLang: Replayable Contracts for Token Usage and
Request-Equivalent LLM Workflows.” The novelty assessment remains provisional.
The graph checker is an explicit JSON model; this deck does not claim
framework-to-graph fidelity.

## Relational verification and resource reasoning

1. Gilles Barthe, Pedro R. D'Argenio, and Tamara Rezk. “Secure Information
   Flow by Self-Composition.” *IEEE Computer Security Foundations Workshop*,
   2004. [DOI: 10.1109/CSFW.2004.1310735](https://doi.org/10.1109/CSFW.2004.1310735).
   Foundational self-composition method for information-flow properties.

2. Gilles Barthe, Juan Manuel Crespo, and César Kunz. “Product Programs and
   Relational Program Logics.” *Journal of Logical and Algebraic Methods in
   Programming* 85(5), 2016.
   [DOI: 10.1016/j.jlamp.2016.05.004](https://doi.org/10.1016/j.jlamp.2016.05.004).
   Studies product constructions and relational reasoning, including
   synchronization for loops.

3. Van Chan Ngo, Mario Dehesa-Azuara, Matthew Fredrikson, and Jan Hoffmann.
   “Verifying and Synthesizing Constant-Resource Implementations with Types.”
   *IEEE Symposium on Security and Privacy*, 2017, pp. 710–728.
   [DOI: 10.1109/SP.2017.53](https://doi.org/10.1109/SP.2017.53) ·
   [author-hosted extended version](https://arxiv.org/abs/1801.01896).
   Resource-aware information-flow/noninterference analysis.

4. Ezgi Çiçek, Gilles Barthe, Marco Gaboardi, Deepak Garg, and Jan Hoffmann.
   “Relational Cost Analysis.” *POPL 2017*, pp. 316–329.
   [DOI: 10.1145/3009837.3009858](https://doi.org/10.1145/3009837.3009858) ·
   [author-hosted paper](https://people.mpi-sws.org/~dg/papers/popl17.pdf).
   Relational reasoning about resource use across executions.

## LLM workflow cost and security neighbors

5. Kevin Dickerson. “Statically Bounding Resource Accumulation in LLM Agent
   Workflows: The Cost Case.” Loom Research, 18 May 2026.
   [Author-hosted article](https://loom.technology/research/bounded-llm-cost/).
   Uses restricted Petri-net analysis for unary cumulative bounds on
   monotone resources, including token cost. This is author-reported;
   no peer-reviewed venue or DOI was located in the review. It is directly
   relevant graph-level unary cost work, so the presentation distinguishes it
   from the relational request/event property rather than implying that
   cyclic cost analysis is absent.

6. Louis Mandel, Guillaume Baudart, Mandana Vaziri, and Martin Hirzel. “PPDL:
   LLM-Based Flows as Probabilistic Programs.” *Proceedings of the 43rd
   International Conference on Machine Learning*, PMLR 306:86172–86197, 2026.
   [PMLR proceedings](https://proceedings.mlr.press/v306/mandel26a.html) ·
   [arXiv:2608.05234](https://arxiv.org/abs/2608.05234).
   Propagates uncertainty in LLM/tool workflows; it does not itself establish
   pathwise usage-trace equality under the graph checker's shared-oracle
   coupling.

7. Melwin Xavier et al. “Agentproof: Static Verification of Agent Workflow
   Graphs.” arXiv:2603.20356, 2026.
   [arXiv preprint](https://arxiv.org/abs/2603.20356). Adjacent static graph
   and policy verification; the properties differ from this usage-event
   relation.

8. Basavesh Ammanaghatta Shivakumar, Swarn Priya, and Peng Gao. “AgentFlow: A
   Flow-Centric Policy Language and Framework for Securing LLM Agent Systems.”
   arXiv:2608.22868, 2026.
   [arXiv preprint](https://arxiv.org/abs/2608.22868). Includes bounded
   verification for a structured fragment and runtime monitoring; do not
   describe static agent-workflow checking as absent.

9. David Basin and Boris Köpf. “An Information-Theoretic Model for Adaptive
    Side-Channel Attacks.” *ACM Conference on Computer and Communications
    Security*, 2007. [DOI: 10.1145/1315245.1315282](https://doi.org/10.1145/1315245.1315282) ·
    [author-hosted PDF](https://people.inf.ethz.ch/basin/pubs/ccs07.pdf).

10. Roy Weiss, Daniel Ayzenshteyn, Guy Amit, and Yisroel Mirsky. “What Was
    Your Prompt? A Remote Keylogging Attack on AI Assistants.” *USENIX Security
    Symposium*, 2024, pp. 3367–3384.
    [USENIX paper](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss).

## Project and evaluation artifacts

- [`docs/CYCLIC_METHOD_REVIEW.md`](../../docs/CYCLIC_METHOD_REVIEW.md) —
  graph-method contract, transition rules, cycle limits, evidence boundary,
  and prior-work framing.
- [`docs/RELATIONAL_STRESS.md`](../../docs/RELATIONAL_STRESS.md) — full-text
  stress semantics and limitations.
- [`bench/results/graphs.json`](../../bench/results/graphs.json) — authored
  graph corpus and finite probes.
- [`bench/results/graph_adversarial.json`](../../bench/results/graph_adversarial.json)
  — supplementary small-graph probe; shares producer reference semantics.
- [`bench/results/relational_stress.json`](../../bench/results/relational_stress.json)
  — generated bounded-AST stress study.
- [`audit/orchgraph.py`](../../audit/orchgraph.py) — JSON graph producer.
- [`audit/replay_graph_certificate.py`](../../audit/replay_graph_certificate.py)
  — separate product-certificate replayer.

## Claim boundary

The product worklist, cycle handling, and register relation are applications of
established relational verification ideas. The project's method contribution
is the finite LLM-workflow graph specialization: resolved model-call events,
exact DSL request descriptors, a request-linked result-register relation,
coinductive closure of productive cycles, and a separately replayed product
certificate. The check is conditional on the graph accurately modeling the
workflow, equal public inputs by declared identity, shared `Ω(contract, index,
request)`, and complete-request accounting. It does not establish a finite
total-cost bound for cycles, termination, deployed workflow fidelity, or real
provider billing.
