# Final publication review: SCP Original Software Publication

**Review date:** 9 October 2026  
**Target:** *Science of Computer Programming* (SCP), Software Track, Original
Software Publication (OSP)  
**Purpose:** Independent artifact and publication assessment, not an editorial
decision or acceptance estimate.

## Decision

OrchLang is a credible, technically substantial OSP candidate with strong
scope fit. It integrates a bounded workflow compiler, relational request
checking, cyclic request graphs with independently replayed certificates,
exact finite usage-channel analysis, exact all-finite-horizon trace-law
checking, two narrow source adapters, a replay-gated LangGraph backend, an
offline wheel, and a local HTML demonstration.

My current subjective score for the SCP OSP **originality/novelty/significance
criterion is 6.2/10**. The equal-weight mean of my estimates for the track's
six published review dimensions is **7.4/10**. SCP publishes those dimensions
but no numerical scale or novelty cutoff; these are review aids, not journal
scores or acceptance probabilities. The requested novelty score of 8 is not
supported. The initial overall project novelty was assessed at 4.5/10 and the
applied-method score at 3.5/10; the same-scale current overall assessment is
5.8/10 and applied-method assessment 5.9/10.

The new row-span tool makes the artifact more precise: it proves one
authored, equal-law case left inconclusive by strong probabilistic
bisimulation, and independently checks both equality proofs and finite
separating witnesses. Its core method is established weighted-automata
equivalence. The result raises the software-method assessment modestly; it
does not establish an 8-level contribution because the evidence remains
controlled and authored, and practical use outside the project is unmeasured.

The software is **not submission-ready**. The current official-template
source has been rendered to a 9-page PDF and I visually checked all nine
pages. The body is single-column and the equations, tables, and references are
legible without clipping or overlap. After the reviewer capture, the stock footer wording was corrected to
“Manuscript prepared for” and the filled metadata heading to “Value”, preserving
the publisher template dimensions, font and layout. The direct 2013 Q-weighted
automata citation was also added; the revised source compiles successfully. The immutable public
candidate link, confirmed author metadata and declarations, and human review
and approval also remain pending. The PDF is a draft artifact, not a
submission bundle.

The completed full v3 reproduction passed 44 stages, including sanitizer and
optional LangGraph integration; it records 112 C++ tests, 203 Python audit
tests, 8 demo HTTP tests, and a separate 31-test LangGraph suite. I verified
the on-disk manifest SHA-256 as
`65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035`; it
records a full, non-quick run and all stages match their expected outcomes.
The trace-law study itself is recorded in
[`trace_equivalence.json`](../bench/results/trace_equivalence.json) and its
producer, replayer, and tests are linked in the evidence manifest.

## Contribution and prior art

The defensible contribution is a software specialization for bounded LLM
workflows. The C++ analysis compares resolved model contracts and exact
modeled request content across secret-controlled alternatives, and preserves
alignment for corresponding earlier results. Separate graph and stochastic
tools analyze productive cycles and finite rational outcome models. The new
trace-law checker compares the selected ordered usage observations under
that supplied model and emits proof or witness material that an independent
replayer checks. The source adapters and local framework backend make
restricted routes from example programs to executable graphs.

The foundations are established. Resource-aware noninterference and
relational cost analysis already connect information flow and resource use
([Ngo et al., IEEE S&P 2017](https://doi.org/10.1109/SP.2017.53);
[Relational Cost Analysis, POPL 2017](https://doi.org/10.1145/3009837.3009858)).
Probabilistic resource bounds also predate OrchLang ([Bounded Expectations,
PLDI 2018](https://www.cs.cmu.edu/~janh/papers/NgoCH17.pdf)). Numeric
potentials can apply whenever a sound cost contract is available; the
OrchLang pathwise equality question is a different analysis target, not proof
that numeric methods do not apply.

PPDL models uncertain multi-call LLM flows and token budgets
([ICML 2026](https://proceedings.mlr.press/v306/mandel26a.html)).
Vulnerability, entropy, mutual information, and leakage metrics have
established foundations ([Smith 2009](https://doi.org/10.1007/978-3-642-00596-1_21);
[Chothia et al. 2013](https://doi.org/10.1109/CSF.2013.20);
[Schröer et al. 2024](https://doi.org/10.1007/978-3-031-75783-9_6)).
Probabilistic bisimulation is established ([Larsen and Skou
1991](https://doi.org/10.1016/0890-5401(91)90030-6)).

The new method also has direct predecessors. Tzeng gives a polynomial-time
equivalence algorithm for probabilistic automata ([SIAM J. Comput. 1992,
10.1137/0221017](https://doi.org/10.1137/0221017)). Kiefer et al. describe
linear-dependence exploration and finite distinguishing words, and discuss
anonymity and obliviousness as program-verification uses ([CAV 2011,
10.1007/978-3-642-22110-1_42](https://doi.org/10.1007/978-3-642-22110-1_42)).
APEX translates open probabilistic programs to automata and uses equivalence
to analyze properties including anonymity and termination ([CAV 2012,
10.1007/978-3-642-31424-7_51](https://doi.org/10.1007/978-3-642-31424-7_51)).
Rational weighted-automata equivalence is treated directly by Kiefer et al.
([LMCS 2013, 10.2168/LMCS-9(1:8)2013](https://doi.org/10.2168/LMCS-9(1:8)2013));
labelled Markov trace equivalence is also well studied ([Fijalkow, Kiefer,
and Shirmohammadi 2020](https://doi.org/10.23638/LMCS-16(2:10)2020)). These
references rule out claims that OrchLang invents general trace equivalence,
security equivalence, or a new span algorithm. The strongest claim is a
domain-specific software application with exact usage labels, separate
stopped/live observations, bounded LLM workflow semantics, and replayable
artifacts. This is a bounded literature review, not a systematic priority
search; do not claim “first” or “no existing tool.” A fuller checked source
note is in
[`trace_equivalence_primary_sources.md`](../research/trace_equivalence_primary_sources.md).

## Same-scale novelty review

Scores are subjective, use one 0–10 scale, and are not probabilities. The
historical initial values are retained; current values reflect the frozen
trace-law study and integrated artifact.

| Dimension | Initial | Current | Assessment |
|---|---:|---:|---|
| Fundamental theory | 2.5 | 3.0 | Useful formal models and proof sketches, but relational analysis, QIF, probabilistic equivalence, and span algorithms are known. No mechanized proof. |
| Applied analysis method | 3.5 | 5.9 | Request-sensitive relational checks plus exact finite channels and a complete finite trace-law decision for the selected observer. New use of the known method is scoped to LLM workflow requests and usage. |
| Research-software contribution | 4.0 | 6.5 | A coherent compiler, graph tools, replayers, source bridges, backend, package, and demo. Still a research prototype with no external adoption evidence. |
| Evidence | 2.0 | 7.0 | Reproducible, hash-bound verification is now broad. Fixtures are authored and the models are offline; no provider validation or independent application result. |
| Overall applied-project novelty | **4.5** | **5.8** | Material software completion and a demonstrated precision gain, tempered by established methods and unmeasured practical significance. |

The SCP OSP originality/significance criterion is **6.2/10**. This is a
small upward adjustment from the previous 6.0 review: a complete row-span
decision now replaces a sufficient-only bisimulation result on an actual
fixture, with an independent proof/witness checker. The result is expected
from established automata theory and its key precision example is authored;
it is not a major theory advance or an independent real-world need study.
The remaining distance to 8 reflects those limits, not missing numbers of
tests.

## OSP review dimensions and readiness

The EAPLS Software Track call identifies six review dimensions and describes
an OSP as primarily a tool with a short software description, typically about
six pages ([track call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/)).
The publisher assigns no numeric scale. The following internal estimates are
equal-weight only to make the tradeoffs explicit.

| Published review dimension | Internal score | Basis |
|---|---:|---|
| Originality, novelty, and significance | **6.2** | Clear LLM workflow specialization and a demonstrated exactness gain; generic methods are prior art and external utility is unknown. |
| Source quality, completeness, and readability | 8.0 | Modular tools, bounded interfaces, regression coverage, replay separation, and explicit unknown outcomes; frontends remain restricted. |
| User and developer documentation | 7.5 | Installation, language, assumptions, source limits, reproduction, and demo are documented. The official-template manuscript and editable highlights are present; metadata completion remains open. |
| Reproducibility | 8.0 | Reported 44-stage hash-bound run, sanitizer, offline replay and packaged checks; no held-out provider or application study. |
| Accessibility and configuration | 7.5 | Offline wheel, local demo, and no API key for core claims; C++ setup and optional LangGraph environment remain separate. No user study. |
| Accompanying manuscript clarity | 7.0 | The 9-page PDF is readable and the scope and assumptions are explicit. The submission footer and metadata-table header still contain placeholders, and the short paper is dense. |
| **Equal-weight candidate-quality proxy** | **7.4/10** | Mean of these six subjective estimates; not a journal rating or decision estimate. |

**Target fit: 8.5/10.** Programming-language tooling, compiler analysis,
security properties, and reproducible research software fit the Software
Track. Fit is not novelty. **Engineering evidence: 8.0/10.** The reproduced
artifact is unusually traceable for a local prototype, but the checks validate
declared semantics and kernels rather than real provider accounting.
**Narrative and presentation: 6.8/10.** The story can be clear if the paper
centers one contribution: offline software for checking and replaying
request-sensitive usage equivalence. Its multiple analyzers should be
presented as components of that software, not as several independent theory
claims.

**Submission readiness: 5.5/10.** The current official-template source has a
readable render and its layout has been checked. The manuscript is still a
draft, and its template footer and metadata heading need correction. Also
pending are:

- an immutable public candidate link and an exact source/PDF/highlights
  submission bundle;
- author confirmation of affiliation, address, correspondence, CRediT roles,
  funding, and competing-interest declarations;
- human review of the source, manuscript, and AI-use disclosure, with the
  author's accountability and approval recorded.

The current
[`SCP author requirements`](SCP_AUTHOR_REQUIREMENTS.md) and manuscript
[`compliance record`](../submission/research/manuscript/compliance.json)
capture the publisher requirements. No DOI or journal decision is asserted.

## Evidence audit

The current source study includes 15 partial patterns from pinned PDL, APPL,
and LMQL examples; a separate 17-file/four-repository catalog has only 15
implemented patterns across three frameworks. The reductions, labels, and
mutations are authored. The compiler accepts all 15 balanced reductions
versus 8/15 on the preceding compiler; this is not a claim of complete
framework ports or independent applications.

| Evidence family | Current observed result | Supported claim and limit |
|---|---|---|
| Bounded compiler/source study | 1,500 base runs per mock mode with no bound violations; 2,250 balanced comparisons per mode with no usage differences; 15/15 current balanced admissions versus 8/15 baseline; 15 extra-call mutations rejected | Authored partial projections and improved checker expressivity, not provider behavior or production prevalence. |
| Independent full-text stress | 13,824 accepted secret comparisons without request/usage mismatch; 117/120 negative mutations have witnesses, three remain unknown | Differential validation from a shared generated AST; not mechanized proof or an external benchmark. |
| Cyclic graph checker | Six accepted certificates replay; 1,400 accepted runs/800 secret pairs/28,580 accounting checks without request, usage, or stop differences; 3,000 property probes find no accepted mismatch | Finite-prefix behavior and certificate replay. The property probe shares producer value semantics; productive cycles imply no finite total budget or termination theorem. |
| Bounded source bridge and LangGraph | 17/20 OrchLang programs export; 720 source/graph comparisons agree; 888 actual backend runs and 4,528 call-event comparisons agree; 24 runs stop at the call cap | Finite behavior for the exact reduced programs and local oracle; three retry examples are excluded. |
| Python LangGraph source frontend | 20 tests; 36 actual source executions, 30 accepted source/backend pairs and six rejected-value probes | Restricted AST extraction and differential checks, not arbitrary Python translation or a translation theorem. |
| Exact finite channel study | 11 authored kernels, 130 analyses, 260 DP/independent-DFS histogram comparisons; 17 equal-mean cases have positive TV; 12 cap unknowns in that study | Exact quantities under supplied success-only rational kernels and selected inputs, not fitted provider probabilities or provider bills. |
| Sufficient all-horizon bisimulation | 11 models: five proved equal, six inconclusive; all 11 certificates independently replay | Sound sufficient result for all finite horizons; splits are inconclusive, not witnesses. |
| **Exact trace-law checker** | 12 authored fixtures: six equal proofs, six finite witnesses; 12/12 replay; 48 finite-DP checks/96 scenario histograms; six witness checks match exact probabilities; 12 cap unknowns and 12 tamper rejects | Complete equality decision for the selected finite success-only observer under each supplied kernel. One equal-law case is bisimulation-inconclusive. No provider or deployment claim. |
| Wheel and local demonstration | Seven-module, six-command wheel passed isolated offline checks; six fixed demo stories and eight HTTP tests | Accessible local package/demo, not a usability study. |

The structural compiler claim is conditional on a shared complete-outcome
oracle keyed by resolved model contract, per-contract ordinal, and complete
**modeled** request. That request is the DSL template and ordered values; it
does not include provider messages, options, tool schemas, or wire
serialization. The token bound also assumes complete per-call abstract input
accounting, such as `I ≤ ceil(UTF8_bytes(template)/d) + Σ(argument bound)` in a
common target-tokenizer unit. A character-density divisor does not prove this
premise. Prices are nominal binary64 identity metadata, not an exact invoice
theorem.

The rational tools instead take a user-supplied finite kernel. The trace-law
checker checks only successful outcomes and the selected ordered usage
observer for fixed public inputs and listed secret assignments. Its proof is
about all finite words in that finite model; it is not about infinite-run
behavior or termination. An independent trace replayer rebuilds the closed
system and checks exact rational equality bases or inequality witnesses. It
does not verify the C++ information-flow proof or validate the supplied
kernel against a service. The source integration test validates only the
documented subset. No provider calls, invoices, answer quality, deployment
prevalence, or outside adoption are measured.

The IBM PDL PDF RAG query was the single independent workflow examined for
this review. Its pinned source has two fixed public questions and real
embedding/retrieval/library behavior, but P08 replaces that behavior with two
answer calls over authored passages and adds any secret routing as an
experiment. It is pattern evidence only; it does not establish an upstream
security problem or add independent impact evidence. Exact source metadata
and exclusions are in
[`trace_equivalence_primary_sources.md`](../research/trace_equivalence_primary_sources.md).

## Recommendation and path to a stronger claim

Use the narrow claim: **OrchLang is offline research software for checking
and replaying request-sensitive usage-equivalence properties in bounded LLM
workflows.** Explain the distinction between a structural shared-oracle
check, exact metrics under one supplied kernel, and exact all-finite-horizon
equality for the selected observer. Identify their assumptions next to the
results. Do not claim a new general cost-channel theory, that numeric methods
cannot apply, provider-billing privacy, arbitrary framework translation,
termination, or an end-to-end agent-security guarantee.

Nothing in the present evidence justifies raising the novelty score to 8.
More authored kernels or variants would add little. A material next result
would use one unmodified, version-pinned public workflow whose confidentiality
boundary is documented independently of this project. Its source-to-graph
translation would need to preserve the admitted source constructs, with a
clear soundness argument and a separate reference execution. The case study
would then report a nontrivial request or usage result under a named offline
oracle and accounting contract, followed by an independent replay or review.
That result could show practical significance without making a provider
claim. The current P08 example does not meet these conditions: its reduction
is partial and the secret route was authored for the experiment. Such work
could warrant a substantial reassessment, but would not guarantee an 8 or an
editorial outcome.
