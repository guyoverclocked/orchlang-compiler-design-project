# Mathematical and novelty review of the strengthened SCP candidate

**Review date:** 14 October 2026. **Reviewed snapshot:** `submission/research/manuscript/OrchLang_SCP_Strengthened.tex` (SHA-256 `3c45a39432ba78f21074a16ab10729f97a3f4e92eabd6c6a200c96cf1e3850da`) and `OrchLang_SCP_Technical_Supplement.tex` (SHA-256 `fe78c3f83c3e7a836b2021559c585373e16ca33b178f3b2ce295b0559b9b1553`). Both identify source revision `8533214105aad0cc015ea1e1c2aad4057515aff7`. The shared manuscripts were subsequently edited during review; the earlier snapshot hashes bind the text inspected here, not necessarily the current final paper bytes. At a later check the main and supplement hashes were `3cb755b3dd761a601b9cba7a9252cca519c4c0832ceb43685876cb88d3a60b7e` and `fc60db556a925045043e3a10df5d528ead42a6435d1f8cbad809ca9a4388b995`. This is a read-only mathematical, scope, cap, and bibliography review; no manuscript or executable source was edited. I relied on the retained independent implementation review and reproduction evidence rather than starting another full reproduction run.

## Assessment

The exact-distance theorem and the conservative full-history bound are stated with the premises needed for their conclusions. I found no mathematical counterexample to either derivation in the manuscript. The strongest contribution claim is the current bounded software integration; its explicit disclaimer against a new general verification/robust-Markov algorithm or a firstness claim is well judged. The paper also correctly says that the finite laws are supplied models, not provider measurements, and that neither offline capsules nor a future small API sample establish a probability-radius premise.

At the reviewed snapshot, the `coupling` entry pointed to an unrelated ACM DOI; the later shared-worktree supplement now has the correct Dagstuhl LIPIcs DOI `10.4230/LIPIcs.ICALP.2017.102`. Several newer references still use descriptive shorthand as though it were a paper title. Full verified citation strings are below for direct substitution. The root task owner has also been notified of the Ngo correction.

## Exact finite row-polytope result

The displayed overlap recurrence follows by partitioning suffix traces by their next visible event. For fixed suffix laws (Q_0,Q_1), weighted overlap is

\[
\sum_z \min(aQ_0(z),bQ_1(z))=\tfrac12(a+b-\lVert aQ_0-bQ_1\rVert_1).
\]

Taking the infimum over allowed suffix-law pairs makes the norm term a supremum of convex functions of $a,b$, hence convex; the overlap value is concave and positively homogeneous. Recursively, each child value after linear mass scaling is concave in the current row pair. Its sum therefore attains a minimum at an extreme point of the product row polytope. Every extreme row of a finite convex hull of supplied generators is one of those generators, so enumerating generator pairs is exact. The recurrence then computes the minimum overlap, and for normalized complete trace laws $1-C_\epsilon(1,1)$ is the maximum total-variation distance.

This exactness depends on the manuscript’s stated finite, compact, **rectangular** product of independently selectable rows. It does not cover a shared/global latent parameter, temporal row coupling, or cross-scenario coupling. If the declared rectangular contract is a sound outer superset of a coupled feasible family, its maximum is an upper bound for that smaller family and may be loose; if actual rows fall outside the declared rows, no transfer follows. The text states this correctly. Unequal prefix masses, terminal overlap, immediate STOP overlap and deterministic STOP padding are also consistent with the recurrence and implementation. With universal STOP-by-horizon disabled, the output concerns the first $H$ slots only.

The replay claim is appropriately qualified: it rebuilds the complete state closure under all generator pairs and recomputes minima, but shares parser, row lookup and rational arithmetic with the producer. The robust prototype is more coupled internally: producer and replay share its local obligation helper. The documented injected helper fault producing a false zero is valuable evidence for this common-mode risk. Keep “separately structured executable replay” and “not formally verified” wording; do not call either checker wholly independent.

The retained review record documents 120 newly cross-checked contracts, 1,888 direct policy-law pairs and 120 attaining witnesses, in addition to 26 whole-law contracts / 20,739 law pairs. It records the three repaired exact-producer cap defects and current exact module SHA-256 `d6136bed1de6fd5ba704a9bf1a79e4d20b6d942d771dba2c1d7460e2c561722c`. The manuscript’s 21-test exact-suite count matches that review. These are bounded implementation checks; the recurrence’s mathematical proof is still an ordinary paper proof, not Coq-checked.

## Conservative row-ball result

At a common complete visible prefix $h$, the triangle inequality gives

\[
\operatorname{TV}(p_0(h),p_1(h)) \leq \min(1,\operatorname{TV}(q_0(h),q_1(h))+\rho_0(h)+\rho_1(h)).
\]

A maximal coupling therefore matches the next symbol with probability at least $1-d(h)$. Conditional on a match, the declared full-history rows apply to the common observed prefix; the least child survival bound over symbols that can occur in both row balls is conservative. Backward induction yields a complete-horizon coupling with agreement probability at least $s(\epsilon)$, and the coupling inequality gives the stated TV upper bound. Missing rows and empty shared support are handled as distance one / zero survival rather than as an unsupported equality. The proof relies on row-ball inclusion at every reachable complete history, finite observer-alphabet completeness, and the visible STOP convention. These are caller premises, not empirical consequences.

The manuscript accurately calls this a sufficient bound and reports that it can be loose. For the stated zero-radius history-dependent fixture, the reported `91/100` agrees with the exact trace TV; `99/100` is the coarser per-depth product. The independent quarter-grid probes are finite falsification checks, not proof over all real rows. The 23-test count and retained shared-helper fault result match the implementation review. Current robust module SHA-256 recorded there is `0c31a674ecd1f56729c500909f4aa01942be75648388139546d7e17bcdfa958d`.

## Resource limits and replay boundaries

The exact cap table in the supplement matches the reviewed code: 4,000,000-byte input; output ceiling 3,999,999 bytes to leave room for the CLI newline; 200,000 JSON-tree items and depth 64; horizon 10; alphabet size 8 and symbol length 128 UTF-8 bytes; 20,000 rows; 32 generators per row and 100,000 total generators; 30,000 DP states and 30,000 STOP-check states; 2,000,000 charged symbol evaluations; 48-digit input rational parts and 4,096-bit intermediate arithmetic. The certificate parser’s separate decimal allowance covers the configured intermediate arithmetic domain. The exact suite count of 21 and the repaired output-tree, prefix-rational, reserved-ancestor and explicit-depth behavior are consistent with the reviewed implementation and retained review record.

The robust paragraph’s stated $H\leq10{,}000$ limit is accurate. The underlying implementation also enforces: 16,000,000-byte input/output; 1,000,000 JSON-tree items and depth 64; alphabet size 128 and symbol length 256 UTF-8 bytes; 50,000 explicit rows/nodes; caller-selected `max_nodes` from 1 through 50,000 across construction, replay coverage and stop proof; 128-digit rational components; and 8,192-bit exact arithmetic. JSON integer inputs are separately limited by digit and 512-bit guards. The paper does not currently enumerate this full robust limit set. That is an omission, not a mismatch in a stated cap; a compact supplement cap sentence/table would make the robust artifact’s supported range as reproducible as the exact prototype’s. The current producer now checks generated JSON item/depth/byte limits before returning a certificate; the retained review reports the default-cap 1,002-horizon probe fails closed and the 23-test robust suite passes.

Both cap sets delimit accepted artifact sizes, not general complexity guarantees. The exact prototype can be exponential in horizon/alphabet/generator choices. The robust prototype’s explicit prefix tree can also grow rapidly. Avoid interpreting the numeric maxima as demonstrated practical capacity.

## Positioning

The current novelty boundary is credible: a restricted source/compiler model exposes request-sensitive paired call checks, a supplied-kernel ordered usage-law analyzer, two uncertainty-contract analyzers, normalized-IR refinement evidence, and scoped source-slice executions. Prior work covers important ingredients and close objectives: RelCost and resource-aware information flow; rational weighted/probabilistic automata; imprecise Markov and TV-ambiguity models; precise labelled-chain trace TV; probabilistic LLM-flow semantics; cost ceilings; workflow trace assurance; static workflow checks; and agent information-flow defenses. None of that comparison licenses a priority claim. The paper’s wording that it found no checked source making precisely the whole combination “for this abstraction,” immediately followed by “this is not a firstness result,” is appropriately bounded.

The new source references matter to that boundary, but should be cited under their exact titles and evidence classes. MAT is an ENASE 2026 proceedings paper as well as an accessible arXiv v1, rather than merely an accessible preprint. CaMeLoT’s arXiv record says it was accepted at CAMLIS 2026. The ACL Anthology gives full publication metadata for ProMCP. Lamina remains an author-hosted research note; typed-resources and Costwright are software/preprint records. Preserve those distinctions and do not imply that repository descriptions are peer-reviewed papers. The CACM article page gives accessible article text/metadata and the companion repository describes its implementation; if the paper retains its caveat, “full article-level technical comparison not undertaken” is more precise than implying the publisher page exposed metadata only.

The API paragraph also draws the right boundary. Four prompts under two OpenAI Responses profiles would exercise those mapped OpenAI request envelopes only. It would not establish fidelity to the original Gemini/AWS/provider-plus-SDK/model call paths in the capsules. Request equivalence in the DSL is not equality of the fully serialized provider request; wrapper `.content` is not a usage receipt; and neither an eight-case descriptive sample nor the capsule’s authored finite support supports a stochastic row-TV premise, future confidentiality guarantee, or invoice conclusion.

## Verified bibliography corrections

The following primary records provide exact titles, names and status. These replacements fix metadata only; they do not expand the manuscript’s claims.

| Entry | Correction / verified status | Primary record |
|---|---|---|
| `ngo` | Exact title and authors; IEEE S&P 2017, pp. 710–728; DOI `10.1109/SP.2017.53`. The title/author text is correct in the current entry; add DOI/pages. | [IEEE S&P proceedings manuscript](https://www.ieee-security.org/TC/SP2017/papers/408.pdf), [author manuscript](https://www.cs.cmu.edu/~mfredrik/papers/Ngo17Oakland.pdf) |
| `coupling` | The reviewed snapshot’s DOI was wrong; the current worktree citation now uses the correct DOI. Full metadata: `*-Liftings for Differential Privacy`; authors Gilles Barthe, Thomas Espitau, Justin Hsu, Tetsuya Sato, Pierre-Yves Strub; ICALP 2017, LIPIcs 80, article 102, pp. 102:1–102:12; DOI `10.4230/LIPIcs.ICALP.2017.102`. | [Dagstuhl publisher record](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICALP.2017.102) |
| `mat` | Exact title/authors and ENASE 2026 publication metadata below. Publisher pages 420–427; arXiv is v1, submitted 18 Mar 2026. | [SciTePress record](https://doi.org/10.5220/0014840300004015), [arXiv v1](https://arxiv.org/abs/2603.18096v1) |
| `agentproof` | Exact title: `Agentproof: Static Verification of Agent Workflow Graphs`; Melwin Xavier, Vaisakh M A, Melveena Jolly, Midhun Xavier; arXiv v1, 20 Mar 2026. No venue should be added absent a publisher record. | [arXiv v1](https://arxiv.org/abs/2603.20356v1) |
| `camelot` | Exact title/authors below. arXiv v1, submitted 16 Sep 2026; arXiv comments state accepted at CAMLIS 2026. | [arXiv v1](https://arxiv.org/abs/2609.18674v1) |
| `appa` | Exact v2 title/authors below; v2 was revised 26 Aug 2026. | [arXiv v2](https://arxiv.org/abs/2607.24625v2) |
| `flowseal` | Exact title is not simply “FlowSeal, agent information-flow…”; title/authors below; arXiv v1, 12 Sep 2026. | [arXiv v1](https://arxiv.org/abs/2609.14003v1) |
| `promcp` | Exact title/authors below; Findings of ACL 2026, pp. 39476–39487; DOI `10.18653/v1/2026.findings-acl.1967`. | [ACL Anthology publisher record](https://aclanthology.org/2026.findings-acl.1967/) |
| `guardians` | Full article title is “Guardians of the Agents: Formal Verification of AI Workflows”; Erik Meijer; CACM 69(1), pp. 46–52, Jan. 2026. ACM lists the article publication date as 16 Dec. 2025 / online first; that is consistent with its January 2026 issue. | [ACM publisher article](https://doi.org/10.1145/3777544), [companion repository](https://github.com/metareflection/guardians) |
| `lamina` | Author and exact title are Kevin Dickerson, “Statically Bounding Resource Accumulation in LLM Agent Workflows: The Cost Case,” author-hosted note dated 18 May 2026. Current institutional attribution and shortened title should be corrected. | [Author-hosted research note](https://loom.technology/research/bounded-llm-cost/) |
| `typed` | Repository paper’s exact title is “A Lean-Checked Potential Calculus for Bounded-Cost LLM-Agent Workflows: A Sequential Core”; author Hernán Inverso, preprint v4 dated 12 June 2026. Cite a version record/DOI as well as the pinned software commit if available. | [Pinned `PAPER.md`](https://github.com/eleata/typed-resources/blob/9ef2ee9bf9d97d6b125963a7dee9de2703f93f00/PAPER.md), [pinned software commit](https://github.com/eleata/typed-resources/tree/9ef2ee9bf9d97d6b125963a7dee9de2703f93f00) |

Suggested full LaTeX entries for the presently abbreviated 2026 items:

```latex
\bibitem{mat} C. Paduraru, P.-L. Bouruc, and A. Stefanescu, ``A Trace-Based Assurance Framework for Agentic AI Orchestration: Contracts, Testing, and Governance,'' in \emph{Proceedings of the 21st International Conference on Evaluation of Novel Approaches to Software Engineering (ENASE 2026)}, vol. 1, pp. 420--427, 2026. doi:10.5220/0014840300004015. Preprint: arXiv:2603.18096v1.
\bibitem{agentproof} Melwin Xavier, Vaisakh M A, Melveena Jolly, and Midhun Xavier, ``Agentproof: Static Verification of Agent Workflow Graphs,'' arXiv:2603.20356v1, 20 Mar. 2026.
\bibitem{camelot} E. Nikolaou, M. W. Eckhoff, R. Flood, G. Grov, V. Mavroeidis, and D. Aspinall, ``CaMeLoT: CaMeL orchestrated with Temporal logic for static verification and liveness,'' arXiv:2609.18674v1, 16 Sep. 2026. Accepted at CAMLIS 2026 (per arXiv record).
\bibitem{appa} A. Kravchenko, V. Liventsev, I. Konstantinov, I. Iskhakov, and M. Kukuy, ``APPA: Recoverable Information-Flow Control for Real-World LLM Agents,'' arXiv:2607.24625v2, revised 26 Aug. 2026.
\bibitem{flowseal} M. Shim, R. R. Karim, R. Jakkula, K. Zhou, X. Liu, X. E. Wang, and Z. Li, ``Confuse the Model, Control the Flow: Understanding and Mitigating Privacy Leakage from LLM Agents with Information Flow Control,'' arXiv:2609.14003v1, 12 Sep. 2026.
\bibitem{promcp} S. Anjum, W. Zheng, R. Kettimuthu, H. Fan, and Y. Feng, ``ProMCP: Profiling Token Flows and Latency Costs in Model Context Protocol--Based LLM Agents,'' in \emph{Findings of the Association for Computational Linguistics: ACL 2026}, pp. 39476--39487, 2026. doi:10.18653/v1/2026.findings-acl.1967.
\bibitem{guardians} E. Meijer, ``Guardians of the Agents: Formal Verification of AI Workflows,'' \emph{Communications of the ACM}, vol. 69, no. 1, pp. 46--52, Jan. 2026. doi:10.1145/3777544.
\bibitem{lamina} K. Dickerson, ``Statically Bounding Resource Accumulation in LLM Agent Workflows: The Cost Case,'' author-hosted research note, 18 May 2026. \url{https://loom.technology/research/bounded-llm-cost/}.
\bibitem{typed} H. Inverso, ``A Lean-Checked Potential Calculus for Bounded-Cost LLM-Agent Workflows: A Sequential Core,'' preprint v4, 12 June 2026. Software at pinned revision 9ef2ee9. \url{https://github.com/eleata/typed-resources/tree/9ef2ee9bf9d97d6b125963a7dee9de2703f93f00}.
```

The `PPDL` entry’s authors, title, PMLR volume, year and pages are confirmed by the [PMLR publisher record](https://proceedings.mlr.press/v306/mandel26a.html); use its exact capitalization, “PPDL: LLM-Based Flows as Probabilistic Programs.” The current main-paper page range and volume are correct. The `ProMCP` publisher record also confirms the exact title above, Findings venue and pages. The CACM publisher page labels Guardians as a research article and contains more than bare metadata; it should not be represented as an inspected peer-reviewed proof paper.

## Suggested claim wording

The supplement’s existing bounded-integration paragraph is close to the safest concise statement. If shortened, retain the following qualifications:

> OrchLang is a restricted workflow-analysis prototype that combines request-sensitive paired call checks, supplied-kernel ordered usage-law comparison, finite trace-distance analysis under explicit row contracts, normalized-IR refinement, and scoped execution evidence. It applies established relational, automata, coupling, and refinement methods to this declared abstraction; it does not establish provider-complete request equality, provider-law calibration, future row-set coverage, a source-to-IR compiler theorem, or priority over related work.

No reviewed evidence supports weakening those boundaries. In particular, a four-public-prompt by two-profile API exercise would be source-derived envelope-shape calibration for that tested OpenAI Responses path, not validation of capsule calls through original provider/SDK/model paths and not empirical support for stochastic row-TV premises.

## Final TeX delta audit (14 October 2026)

This final read-only audit checked the citation and cap/complexity edits in the current TeX inputs. Their SHA-256 identities at the time of the audit are:

| Input | SHA-256 |
|---|---|
| `OrchLang_SCP_Strengthened.tex` | `b9dad88f388d0e29b9ab843fd1a5aeebeaa99dbd9aa1484304109be5270b23f1` |
| `OrchLang_SCP_Technical_Supplement.tex` | `3244d07937a56dd9bb732da04aa381dd7ebcd3d01455ea9fe8955e1069f7c52d` |

The requested changes are present. Ngo's IEEE S&P entry now has the correct proceedings DOI and page range; the conference-archive paper confirms its title and author names. The `*-Liftings` citation uses the correct ICALP 2017 LIPIcs record and DOI. The typed-resources entry includes the v4 version DOI and pinned source. The 2026 citation records now carry the checked authors, titles, versions, dates and publication status; Agentproof's names match its arXiv v1 record. The CACM comparison explicitly says that no full article-level technical comparison was undertaken. The PPDL bibliographic identity is correct, with one minor house-style discrepancy retained: the PMLR publisher title capitalizes “Based,” while the TeX entry has “based.”

The exact-prototype paragraph now states that work can grow exponentially and disclaims a polynomial-complexity claim. The robust paragraph now identifies its principal acceptance maxima and explicitly says they are not demonstrated practical capacities; the supplement also describes rapid prefix-tree growth. The robust list is a headline cap summary rather than an enumeration of every lower-level parser guard/configuration detail (for example, the caller-selected `max_nodes` range and JSON-integer guards remain in the implementation/review record). That is a reproducibility-detail limitation, not a contradiction of the stated caps. The earlier mathematical and implementation caveats in this report remain in force.

**Final verdict:** these citation and cap/complexity edits introduce no new mathematical-claim or novelty-positioning blocker in the reviewed text. The manuscript remains appropriately scoped as a bounded integration of established methods, without a priority claim or a claim that the exact prototype is polynomial-time. The SHA values identify the TeX inputs checked here; they do not identify or validate the separately built PDF.
