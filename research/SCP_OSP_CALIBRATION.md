# Calibration against published SCP Original Software Publications

**Prepared:** 9 October 2026  
**Purpose:** Compare the software contribution and evidence shown in three
published *Science of Computer Programming* Original Software Publications
(OSPs) with OrchLang's current evidence. This is a qualitative calibration,
not an editorial score, a threshold inference, or a prediction of acceptance.

## Sources and access

I read the complete primary PDFs for HBSniff and FTS4VMC. For *Analysis and
formal specification of OpenJDK's BitSet: Proof files*, the CWI repository
record and publisher-indexed abstract/section material were accessible, but
the OSP's complete PDF was not retrievable from the supplied CWI PDF URL or
publisher page. I therefore mark details about that 2025 OSP as **abstract and
repository-record level**. I also read the full companion iFM 2023 paper and
reviewed the associated artifact record; those materials inform the
underlying technical work but are not the same publication as the 2025 OSP.

The three papers are examples of the range of software contributions SCP has
published. They do not establish a common numerical bar, and publication does
not show that third-party adoption is a required condition. The comparison
below asks what each article makes concrete: a useful task, an executable
artifact, and evidence proportionate to its claims.

## What the three OSPs demonstrate

| OSP | Software originality and practical use | Evidence actually reported | Limits the paper acknowledges |
|---|---|---|---|
| **HBSniff** (Huang et al., SCP 217, 2022, 102778) | A static Java/Hibernate analyzer aimed at ORM-specific problems generic smell tools do not detect. It implements 14 smell detectors and four mapping metrics; it can analyze source without compiling the target project and produces readable, customizable XLS/JSON/CSV reports. The contribution is domain-specific detection and an operational tool, not a new general static-analysis theory. | Unit tests and documentation cover implemented detectors/metrics. Two authors independently checked detections in five open-source projects and one commercial project. A separate controlled database benchmark measures eight performance-related smells over a three-level entity relation and three data scales, with ten executions and medians. This supports practical relevance of most measured performance smells in that setup. | The four mapping metrics lacked a suitable real project for validation and were checked with examples, tests, and a sample project. One of eight tested performance smells had negligible measured impact. Three data-usage smells needing runtime information were not implemented. Static-analysis support for generated methods is library-specific, and the pagination detector is heuristic. The authors do not claim a complete Hibernate analyzer. |
| **FTS4VMC** (ter Beek et al., SCP 224, 2022, 102879) | A front end connecting Featured Transition System (FTS) inputs to existing analysis and the VMC model checker. It detects and visualizes three FTS ambiguities, supports selected ambiguity removal, checks liveness, translates eligible live FTSs to MTSs, and drives family-based property checking with counterexamples. It provides a GUI and command-line use of core components. The software contribution is integration and an end-to-end engineering workflow around established FTS/MTS methods. | The article explains each stage and provides a graphical workflow, sample models, source repository, manual, and a Code Ocean reproducibility capsule. Prior work had already supplied the ambiguity algorithm's correctness proof and benchmark evaluation, including larger models; the OSP makes that analysis usable in the VMC toolchain rather than claiming those earlier algorithmic results as a new benchmark. | Family-based verification is efficient only for the stated live-model/property fragment; otherwise other verification routes are needed. Graph rendering is capped at 300 transitions by default, and a CLI is suggested for larger models. The article's main contribution is a research toolchain front end, not a new model-checking formalism. |
| **OpenJDK BitSet proof files** (Tatman, Hiep, and de Gouw, SCP 241, 2025, 103232) | At the abstract/record level, the OSP packages software developed for a formal analysis of Java's widely used `BitSet`: implementation fixes, formal specifications, proof files, and new KeY proof rules for bitwise operators. This connects a research tool artifact to a concrete, standard-library analysis. | The official CWI record says the artifact contains proofs for a subset of methods and new proof rules, and links the work to the iFM 2023 paper. That complete companion paper reports an overflow bug in `get(int,int)`, issues in `valueOf(...)`, a JML specification and testing, and initial proof work on a difficult method. The OSP record and companion article make the artifact and the concrete analysis target inspectable. | **The 2025 OSP full text was not accessible in this review.** The CWI record says full mechanical verification was not yet possible because of limited KeY bitwise-operation support and bugs in BitSet. The companion paper describes initial/partial proof work, not a complete proof of the class. The standard-library setting makes potential impact salient, but does not itself demonstrate downstream adoption or accepted upstream fixes. |

### Primary references

1. Zijie Huang, Zhiqing Shao, Guisheng Fan, Huiqun Yu, Kang Yang, and Ziyi
   Zhou. “HBSniff: A Static Analysis Tool for Java Hibernate Object-Relational
   Mapping Code Smell Detection.” *Science of Computer Programming* 217
   (2022), 102778. [DOI](https://doi.org/10.1016/j.scico.2022.102778),
   [complete author PDF](https://hbsniff.github.io/paper.pdf).
2. Maurice H. ter Beek, Ferruccio Damiani, Michael Lienhardt, Franco
   Mazzanti, Luca Paolini, and Giordano Scarso. “FTS4VMC: A front-end tool for
   static analysis and family-based model checking of FTSs with VMC.” *Science
   of Computer Programming* 224 (2022), 102879. [DOI](https://doi.org/10.1016/j.scico.2022.102879),
   [complete institutional PDF](https://iris.unito.it/retrieve/handle/2318/1882860/1063847/FTS4VMC%20a%20front-end%20tool%20for%20static%20analysis%20and%20family-based%20model%20checking%20of%20FTSs%20with%20VMC%20-%20prePress.pdf),
   [reproducible capsule](https://doi.org/10.24433/CO.8774017.v1).
3. Andy S. Tatman, Hans-Dieter A. Hiep, and Stijn de Gouw. “Analysis and
   formal specification of OpenJDK's BitSet: Proof files.” *Science of
   Computer Programming* 241 (2025), 103232. [DOI](https://doi.org/10.1016/j.scico.2024.103232),
   [CWI publication and artifact record](https://ir.cwi.nl/pub/34582/).
   Companion paper: “Analysis and formal specification of OpenJDK's BitSet,”
   iFM 2023, [DOI](https://doi.org/10.1007/978-3-031-47705-8_8).

## Comparison with OrchLang

OrchLang's software contribution is a focused toolchain for checking and
replaying request- and usage-equivalence properties in a bounded LLM-workflow
model. Its novelty is chiefly the integration and specialization of
established relational, quantitative, and automata methods—not a new general
theory. The present artifact joins a C++ compiler, graph analysis,
finite-kernel and finite-trace tools, certificate replay, restricted source
front ends, an optional LangGraph execution backend, offline packaging, and a
local demo. Its claims explicitly exclude provider billing, unrestricted
Python translation, full-state confidentiality, and termination or whole-cycle
budget guarantees. See [`FINAL_PUBLICATION_REVIEW.md`](../docs/FINAL_PUBLICATION_REVIEW.md)
and the current [technical report](../docs/PAPER.md) for the detailed scope
and evidence inventory.

Relative to the three examples, OrchLang has a substantial artifact and
reproducibility story: independent checkers/replayers, bounded unknowns,
source hashes, controlled mutations, and multiple small studies. It also has
more than a purely authored DSL demonstration. The pinned incident-triage
study executes the unchanged public LangGraph source with its deterministic
mock and tests exact selected request/usage/control projections. A separate
controlled schedule exposes a shared mutable cost-tracker race in that pinned
revision and shows isolation with one graph per invocation. The source-specific
AST contract and classifier graph certificate provide a local compiler-linked
slice and reject authored raw-text bypass mutations. These results add
source-grounded evidence, but their scope is still specific to one pinned
mock-first workflow and its declared inputs, observer, runtime, and oracle;
the source-protocol and concurrency artifacts are not yet frozen into a common
release reproduction.

The difference from the comparison papers is evidence shape, not an assumed
requirement that OrchLang must have production adoption:

* HBSniff couples a readily understood practitioner task to detections and
  empirical checks on several actual projects. OrchLang's direct utility is
  less established: its current source case demonstrates bounded properties
  and an isolation lesson, but no user study, external use, provider-backed
  evaluation, or measured decision benefit. The system's own mock-based
  accounting is not real tokenization or invoice evidence.
* FTS4VMC's main value is an explicit user path from input model through
  visualization, transformations, and calls to a verification tool. OrchLang
  has a compiler/CLI, replay artifacts, installation route, backend, and demo,
  but its most ambitious workflow-source correspondence is intentionally
  narrower. The first classifier request has a replayable graph certificate;
  the rest of the source argument depends on a version-pinned AST contract and
  stated oracle/runtime assumptions. It is not a proof of arbitrary source
  translation or full-graph noninterference.
* The BitSet artifact ties formal methods to a standard-library target and
  concrete bugs, while being candid about partial mechanization. OrchLang has
  stronger breadth in software integration and replayable empirical studies;
  it does not yet show a comparably concrete improvement to an adopted LLM
  workflow or validate real-provider usage. That gap is about practical
  significance, not the absence of a novel general theorem.

The current incident-triage case provides a credible, source-derived
demonstration of a narrow redaction boundary, not a general PII guarantee.
Its raw incident remains in graph state/checkpoints. The concurrency case
shows one deterministic interleaving with incorrect shared tracker attribution;
it is not a frequency estimate or general concurrency verification. The
source-specific bridge should be reported separately from direct-source
execution and should retain its explicit classifier-slice boundary. These
qualifications are important to a fair software comparison, not reasons to
discount the underlying reproducibility work.

## Calibration conclusions

The three OSPs show several credible forms of original software contribution:
specialized detection with project-level evidence; operational integration of
previously established methods into a usable analysis pipeline; and a
reproducible artifact supporting a substantive formal-analysis case study.
Their originality is not identical and their evidence is not interchangeable.
None of these examples licenses an editorial score cutoff or makes independent
adoption a prerequisite.

For OrchLang, the closest defensible claim is that it is a replayable research
software pipeline specializing established analysis techniques to a narrow,
important class of LLM workflow usage questions, with a source-specific
case-study bridge and explicit limits. The present evidence supports a
technical software contribution and relevance; stronger practical-significance
claims should wait for the source-protocol and concurrency evidence to be
frozen, reproduced, and incorporated consistently into the public artifact.
This calibration does not change any existing novelty, venue, or readiness
score.
