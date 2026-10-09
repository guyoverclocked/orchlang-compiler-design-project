# Novelty assessment and residual gap

**Review date:** 9 October 2026  
**Target:** Science of Computer Programming, Software Track, Original Software
Publication (OSP)

## Current judgment

The exact finite trace-law checker is implemented and included in the current
artifact. It closes the companion bisimulation checker’s observed precision
gap for the declared finite model: strong bisimulation leaves one authored
equal-law case inconclusive, while the exact rational row-span checker proves
the two selected scenarios have the same ordered usage-trace law at every
finite horizon. It also returns and independently replays finite witnesses
when the selected laws differ.

The result materially improves the software, but it does not introduce a new
equivalence algorithm. Tzeng’s probabilistic-automata equivalence result and
the subsequent finite-dimensional span method are established. APEX already
applies program-to-automata equivalence to probabilistic security analyses
including anonymity. The OrchLang delta is the compilation of a finite LLM
request graph and conditional rational kernel into a selected usage observer,
separate stop/live output masses, exact certificate and witness replay, and
integration with the surrounding workflow compiler and source adapters. The
reviewed citations and ready-to-use related-work paragraph are in
[`trace_equivalence_primary_sources.md`](../research/trace_equivalence_primary_sources.md).

On the stable 12-fixture authored study, six cases are proved equal and six
have exact finite separating words; all twelve certificates or witnesses
independently replay. The six equality cases have 48 exact finite-DP
cross-checks covering 96 scenario histograms at horizons 1, 2, 4, and 8. All
six witnesses distinguish in a finite-DP check with matching probabilities.
Twelve cap probes return `unknown`; twelve semantically tampered reports are
rejected. In one case the checker proves equality where the strong
bisimulation check is inconclusive. These results show a concrete precision
gain in a controlled model, not external use or a deployed privacy finding.

The claim remains restricted to success-only finite rational kernels indexed
by complete modeled request, saturated contract ordinal, and retained bounded
history, for one fixed public store and the listed secret assignments. The
observer is the ordered sequence of resolved contract and integer input/output
usage labels, with stop and live-prefix mass checked separately. Errors,
retries, termination probability, infinite-run laws, cumulative bills, and
provider behavior are outside it. The models and the equal-law case are
authored.

## Same-scale novelty scores

These subjective 0–10 scores are not journal ratings or acceptance
probabilities. The scale treats 5 as a focused contribution substantially
built from established ideas. The historical overall self-assessment of 4.5
and applied-method rating of 3.5 are retained as the initial baseline.

| Dimension | Initial | Current | Why it changed |
|---|---:|---:|---|
| Fundamental theory | 2.5 | 3.0 | The formalization is clearer and now includes exact all-finite-horizon reasoning, but relational analysis, quantitative information flow, and weighted-automata equivalence are established. The proof is not mechanized. |
| Applied analysis method | 3.5 | 5.9 | Resolved request identity, aligned dependent results, cyclic graph reasoning, exact finite-channel metrics, and a complete row-span decision for the selected finite usage observer make a useful integrated method. The new decision procedure is a specialization of known methods. |
| Research-software contribution | 4.0 | 6.5 | The compiler, graph tools, separate replay implementations, restricted source paths, packaged commands, and local demonstration are a coherent reusable artifact. It remains a research prototype without independent adoption. |
| Evidence | 2.0 | 7.0 | The hash-bound 44-stage reproduction, sanitizer, 203 audit tests, replay checks, source/backend studies, and exact trace-law study support the declared semantics. The studies are controlled or authored and do not validate providers or independent applications. |
| Overall applied-project novelty | **4.5** | **5.8** | The complete software path and demonstrated precision improvement raise the contribution. Established foundations and unmeasured practical impact keep the increase moderate. |

The SCP OSP originality/novelty/significance criterion is assessed separately
at **6.2/10**. The new checker merits a small increase from the earlier 6.0
assessment: it proves one concrete equality that the sufficient bisimulation
relation cannot establish, and independently replayable finite witnesses
clarify negative results. It does not merit 8 because the algorithmic
foundation is known and the demonstrated precision gain is an authored finite
case. No journal-specific numeric threshold is published.

## What could change the significance assessment

More authored fixtures, generated cases, or seeds are not the missing result.
The most valuable feasible contribution would be an end-to-end analysis of
one unmodified public workflow whose confidentiality boundary is documented
or independently justified, with a reproducible source-to-graph mapping and
an independently checked nontrivial result under an explicit accounting
contract. The source-to-graph translation needs a soundness argument for the
admitted subset, and an independent reference execution should check the
translated requests, usage, and stop behavior. The source must retain its
workflow control and prompt semantics; any abstraction, oracle, or authored
mutation must be identified separately. This is a concrete route to stronger
OSP significance, not a promise that one case will earn an 8.

The single independent workflow reviewed here, IBM PDL’s pinned PDF RAG
example, does not meet that bar. Its upstream questions are fixed and public;
the implemented P08 reduction supplies passages to two answer calls and
removes embedding, retry, database retrieval, context assembly, and array
rendering. The source and license are real and pinned, but the reduction is
partial and adds no source-defined secret route or impact finding. See the
source audit in
[`trace_equivalence_primary_sources.md`](../research/trace_equivalence_primary_sources.md).

A faithful provider-tokenizer or invoice study could address practical
accounting validity, but would require a defensible serialization and data
contract and would still not establish broad security impact by itself. A
single provider call or another synthetic kernel is not enough. The current
artifact does not contain a small missing feature whose implementation would
justify an 8. Independent evidence of useful results on an unmodified
workflow, paired with source-fidelity evidence, is the material change that
could justify a substantial reassessment. Even that would not guarantee a
particular score or editorial outcome.

## Method reference for the OSP

The implementation constructs one rational transition matrix per visible
usage label. For each supplied scenario against scenario zero, it explores the
span of the signed initial row under these matrices and checks two output
columns: stopped mass and nonterminal mass. Closure plus zero outputs for a
basis proves equality for every finite word; a nonzero output yields a finite
word and exact probabilities. Resource or rational-precision caps return
`unknown` with no partial equality claim. This is a multi-output application
of established weighted-automaton linear algebra, not a new general
equivalence method. The result says nothing about infinite runs, termination,
provider distributions, errors, cumulative billing, or invoice privacy.
