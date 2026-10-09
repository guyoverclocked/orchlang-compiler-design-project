# OrchLang: final upgrade assessment

9 October 2026 · Candidate 0.5.0-rc1 · Audited baseline
`a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9`.

## Decision

The project is substantially stronger and is ready for a serious compiler
project presentation and a public technical report. The selected journal
route is **Science of Computer Programming (SCP), Software Track / Original
Software Publication (OSP)**. A focused official-template manuscript and a
reproducible software artifact have been prepared. Publication remains a peer
review decision. The requested novelty-based score of 8 is **not supported**;
no acceptance probability, author approval or journal decision is invented.

## Initial and current scores

These are subjective internal review aids on the same prior 0–10 scale. The
independent final assessment is [FINAL_PUBLICATION_REVIEW.md](FINAL_PUBLICATION_REVIEW.md).
They are not measurements or journal ratings. Historical initial values come
from the preceding project brief; the earlier interim 5.5 has been superseded.

| Dimension | Initial | Current | Reason |
|---|---:|---:|---|
| Overall applied-project novelty | **4.5** | **5.8** | A broader, usable and inspectable specialization; foundations remain established |
| Applied analysis method | **3.5** | **5.9** | Exact request/model identity, dependent results, productive cycles and supplied-model usage laws |
| Fundamental theory | 2.5 | 3.0 | Conditional semantics and proof sketches; no new general NI/QIF/bisimulation theory |
| Research-software contribution | 4.0 | 6.5 | Compiler, graph/stochastic checkers, independent replay, source paths, wheel and demo |
| Evaluation evidence | 2.0 | 7.0 | Substantial replay/differential evidence; primarily authored and synthetic |

The overall novelty increase is **1.3 points**, and the applied-method increase
is **2.4 points**. Engineering repairs, more seeds and polished slides are not
counted as new theories.

| SCP-specific judgment | Current score | Meaning |
|---|---:|---|
| OSP originality/novelty/significance | **6.2/10** | Useful software specialization with unmeasured external impact |
| Equal-weight six-criterion candidate quality | **7.4/10** | Internal proxy over the track's stated review dimensions |
| Scope fit | **8.5/10** | A programming-language/compiler/verification tool fits the journal |
| Engineering evidence | **7.5/10** | Strong checks for declared offline semantics |
| Narrative/manuscript | **7.0/10** | Precise software claim and boundaries; several components in a short paper |

Scope fit above 8 does not mean novelty above 8. The publisher defines neither
this scale nor an acceptance threshold. The independent reviewer initially
rated submission readiness 5.5 while immutable public identity, author facts,
declarations and final packaging remained pending. The release/compliance
records identify subsequently completed items; human facts and review cannot
be supplied by an agent.

## What was built and repaired

- The compiler admits matched dependent model chains under private routing by
  separating explicit-data labels from effective labels carrying the program
  counter. Outputs and effects still enforce the effective policy.
- Resolved provider/model/cap/price identity, exact templates, ordered typed
  literals, lexical bindings and prior-result correspondence replace weaker
  matching. Boolean `true` and text `"true"` no longer collide.
- Scopes, retries, call ordinals, saturation, JSON/numeric/input handling and
  normal execution gates were audited. Unsupported token-unit conversion
  rejects with E267.
- Certificate v3 binds source bytes. The independent source-cost auditor
  parses source and checks every cost derivation; it does not verify security.
- A graph product checker handles productive cycles and mutable registers,
  removes stale equality relations, and emits independently replayed closure.
- Exact finite rational usage channels model complete values and bounded
  outcome history, compute exact leakage facts, and have independent DFS and
  report replay.
- A finite stochastic transducer and exact stable partition can establish
  equal ordered usage laws at every finite call horizon. Its independent
  replayer reconstructs closure; split partitions are inconclusive.
- Exact rational row-span checking decides trace-law equality for the supplied
  finite model and selected stores. It emits independently replayed equality
  certificates or finite witnesses, resolving an equal-law example that
  sufficient strong bisimulation misses.
- Narrow bounded OrchLang and actual Python LangGraph source adapters provide
  provenance, immutable snapshots and replay gates. A pinned actual LangGraph
  backend executes offline.
- A nine-module/eight-command wheel, functioning seven-story HTML demo, 32-slide
  editable presentation, timed scripts, official-template journal paper and
  extended technical report complete the package.

The theories are attributed to established resource noninterference,
relational cost analysis, QIF, coupling, probabilistic bisimulation and
weighted-automaton equivalence. The
new value is their specific inspectable workflow tool arrangement.

## Frozen evidence

| Evidence | Recorded result |
|---|---|
| C++ / audit / demo / optional integration tests | 112 / 203 / 8 / 31 passing; shipped examples and ASan/UBSan pass |
| Identical balanced partial source projections | 8/15 baseline admissions → 15/15 current |
| Each source oracle mode | 1,500 base runs without bound violation; 2,250 balanced pairs without difference; all 2,250 extra-call pairs differ |
| Independent bounded full-text stress | 13,824 accepted secret pairs without request/usage mismatch; 117 negatives witnessed, three retry mutants unknown |
| Graph fixtures | Six accepted certificates replay; eight rejected cases have finite billing witnesses; three invalid cases |
| Bounded source bridge | 17/20 exports; 720 source/graph run pairs agree; three retry exclusions |
| Actual LangGraph backend | 888 runs / 4,528 call-event pairs agree; 24 call-cap prefixes |
| Actual Python source | 30 accepted trace pairs and six rejected value probes agree |
| Exact finite channels | 130 analyses / 260 exact independent histogram comparisons agree |
| Independent finite report replay | 130 verify at explicit larger caps; 129 verify and one UNKNOWN at default caps |
| Stochastic closure | Five proved equal / six inconclusive; all 11 independently replay |
| Corroboration/cap behavior | 60 finite DP checks / 120 unit-mass histograms; all 11 fresh cap probes UNKNOWN |
| Exact all-finite-horizon trace laws | 12 cases: six proofs/six finite witnesses, all replay; 48 equality DP checks/six witness checks; 12 fresh UNKNOWN probes and 12 semantic tamper rejections |
| Isolated package | 23 offline build/install/CLI stages pass, including equality, witnesses, wrong-source rejection and UNKNOWN |
| Combined reproduction | 44 stages pass; inputs unchanged during run; sources/results bound in manifest |

[REPRODUCIBILITY.md](REPRODUCIBILITY.md) explains the stages and budgets.
Repeated seeds, inputs, observers and horizons are not separate applications.
The 15 patterns are partial authored reductions from three frameworks, not
full ports. The separate catalog of 17 candidate files is not an evaluation
count. Provider distributions and invoices were not measured.

## Importance and presentation narrative

A token ceiling and secret-independent usage answer different questions.
This matters when a per-run usage observer knows public context and private
routing changes requests, model selection or continuation. Real deployment
impact depends on that access; a coarse invoice may hide the modeled records.
No prevalence, production attack or external-user study is claimed.

The strongest sequence is:

1. Hold the public inputs fixed; flip a secret and show equal caps but unequal
   input usage (37 versus 61 input-length pins).
2. Show why exact request identity is stronger than equal rounded estimates.
3. Admit the matched dependent chain; demonstrate a tiny template/model/typed
   literal change being rejected.
4. Extend to a productive cycle and independently replay its finite product.
5. Give equal-mean output laws `(1 or 3)` versus `2`: total variation is 1.
6. Give ordered `(1,3)` versus `(3,1)`: aggregate TV 0, trace TV 1.
7. Explain the supplied-model proof for every finite horizon and the meaning
   of INCONCLUSIVE and UNKNOWN.
   Show the seventh HTML story: strong bisimulation is inconclusive, while
   exact trace equivalence proves the authored usage laws equal.
8. Connect source to actual LangGraph execution; show frozen evidence.
9. End with the functioning HTML demo and a precise software contribution.

This is a stronger narrative than an unsupported claim that current agent
frameworks lack analysis. The slides and scripts preserve prior art and limits.

## Remaining substantive holes

| Limit | Meaningful next evidence |
|---|---|
| Abstract additive accounting and request representation | Verified provider envelope/tokenizer/conversion contract |
| Supplied successful-outcome kernels | Faithful provider evidence and explicitly modeled failures/state |
| Proof sketches and independent implementations | Mechanized soundness or a verified source-translation theorem |
| Authored/projection-heavy evaluation | An independently developed unmodified workflow and independent reuse |
| Sufficient request/bisimulation checks | Proven normalization or stronger trace-equivalence analysis |
| Trusted explicit release reasons | Executable validator/release-policy contracts |

Adding more synthetic fixtures will not by itself justify novelty 8. The
material gap is independent utility or a genuinely stronger verified method.
The current artifact can be described and submitted honestly through the OSP
route after author completion; an academic review paper would instead need a
systematic review protocol, which this targeted audit does not provide.
