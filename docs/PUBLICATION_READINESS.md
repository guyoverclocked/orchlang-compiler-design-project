# SCP OSP contribution and publication-readiness review

**Review date:** 9 October 2026. This is an internal, evidence-based readiness
review. Its scores are not publisher ratings, editorial advice, or acceptance
probabilities. No editor was contacted and no paper or software was submitted.

## Decision

OrchLang has a credible **subject-matter fit** for the Science of Computer
Programming Software Track: it is a compiler and analysis tool for a workflow
language, and SCP explicitly lists programming-language design, implementation
and evaluation, development tools, and an Original Software Publication track
for existing, useful software in programming and software development. The
current publisher page does not set a numerical novelty score. The current OSP
author guide was subsequently opened and reviewed in the Codex in-app browser
on 9 October 2026; the earlier web-request 403 was a transport limitation,
not an inaccessible guide. The guide requires the OSP Word or LaTeX template
without formatting alterations, a single-column manuscript, a completed
metadata table at the end, and a public external software link. It suggests
3–6 pages for abstract plus running text, excluding title/authors/affiliations,
references, metadata, tables, and figures. It also requires an abstract of at
most 250 words, 1–7 keywords, and a separate editable highlights file with
3–5 highlights of at most 85 characters each. References should be numbered
in citation order; consistent style is flexible at first submission. Data
Option B encourages supporting data sharing or a data-availability statement.
MIT is expressly accepted. A public EAPLS call by SCP Software Track editor
Marieke Huisman
dated 27 August 2025 gives the clearest accessible track-level guidance: an
OSP consists primarily of a tool and a short description, typically around six
pages in regular SCP format; source code or a link and user documentation are
part of the submission. It lists six review dimensions: originality, novelty,
and significance; source quality; documentation; reproducibility;
accessibility; and manuscript clarity. “Typically” describes a norm, not a
verified mandatory page limit. The call also asks for an innovative
contribution and a recognized software license; the repository now has an MIT
license. [EAPLS SCP Software Track call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/),
[official SCP scope and OSP description](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423),
[current OSP guide](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors),
[official OSP LaTeX template](https://legacyfileshare.elsevier.com/promis_misc/scico-osp-template.tex),
[official OSP Word template](https://legacyfileshare.elsevier.com/promis_misc/scico-osp-template.docx).
The full component, file-category, metadata, policy, and preparation checklist
is in [`SCP_AUTHOR_REQUIREMENTS.md`](SCP_AUTHOR_REQUIREMENTS.md).

I also checked two published OSP examples indexed on the publisher's site.
The Contract Automata Library article says it follows the OSP guidelines and
describes its purpose, architecture, usage examples, build/test/code-analysis
process, availability, usability, reproducibility, and documentation. The
HBSniff OSP record includes a permanent link to the software version and
repository. These are useful precedents for the kind of evidence OrchLang
should prepare, but they are published artifacts, not the current author guide
or a verified mandatory checklist. [Contract Automata Library OSP](https://www.sciencedirect.com/science/article/abs/pii/S0167642322000740),
[HBSniff OSP](https://www.sciencedirect.com/science/article/abs/pii/S0167642322000119).

The previous provisional review assigned **5.5/10 on the project's novelty
scale**, **7.5/10 for SCP fit**, and **6.6/10 for OSP readiness**. These remain
historical baselines, not final scores: the exact probabilistic-channel
analysis, independent report replay, and all-horizon checker were added or
completed afterward, while the final demo and combined evidence review are
still in progress. This revision does not freeze replacement scores before
that artifact-quality assessment. The literature comparison still does not
support a novelty-based score of 8. The compiler, graph checker, independently
replayed graph certificates, bounded source bridges, mock evaluations, and
release materials make the artifact more reviewable. Its relational and
probabilistic-bisimulation methods are established, and independent
deployment evidence is absent. The graph method and its finite evidence are reviewed in
[`CYCLIC_METHOD_REVIEW.md`](CYCLIC_METHOD_REVIEW.md); source-to-graph
translation remains an unverified adapter.

Neither the publisher scope page, the OSP guide, nor the EAPLS track call
states a numerical novelty threshold or scoring scale. The project's internal
8/10 target must not be mistaken for an Elsevier criterion. The call's six
review dimensions are used below as an internal assessment structure, not as
scores reported by the journal.

## What the current evidence establishes

The research claim is now narrow: a sufficient relational check for equality
of modeled per-contract usage traces across secret-controlled alternatives,
under a shared oracle keyed by resolved model contract, per-contract call
ordinal, and complete modeled request. The request is the DSL template plus
ordered argument values; it is not the provider's serialized request. The
oracle is a conditional semantic contract, not an empirical fact about a
provider. The token bound also depends on a per-call full-request accounting
premise, not on a character-to-token divisor alone. The formal note states
these assumptions, excludes declassification from the unrestricted theorem,
and does not claim real invoice protection, independent-seed distributional
independence, prompt-injection elimination, or a full proof checker.

The implementation evidence is materially stronger than a demo:

- The archived core reproduction reports 111/111 C++ regressions, a successful
  address/undefined-behavior sanitizer run, and 19/19 source-cost-auditor
  tests. That manifest binds compiler SHA
  `5bae3be94e9b7d747728965e2562d06a9844d47b28f871c6fe44dcb6f0a7aa43`; later
  typed-literal and source-bridge changes require a refreshed combined
  reproduction before that count is presented as the final release snapshot.
- Each mock mode separately reports 1,500 base executions with zero declared
  cost-bound violations; 2,250 balanced pairs with zero usage-observation
  differences; 2,250 authored extra-call pairs with all 2,250 differences;
  30 checked source-cost reports; and 15 balanced variants accepted versus
  8 by the prior compiler. These are repeated deterministic grids, not
  independent studies.
- A separate Python full-text reference interpreter generated 264 bounded
  cases from six accepted shapes and five mutation classes. It ran 13,824
  accepted secret-assignment comparisons across 24,192 accepted executions,
  66,240 calls, and 66,240 per-call accounting checks; no request or usage
  mismatch was found. All 144 positives passed C++ `check`; all 120 mutations
  were rejected. The finite probes witnessed request/usage differences for
  117 negative cases; three retry mutations had no witness and remain unknown.
  One equal-value subgrid for distinct argument bindings was safe in the
  finite reference probes but rejected by the conservative static rule.
- The independent reference uses generated AST semantics, not C++ runtime
  facts or compiler certificates, but shares the generator AST with source
  rendering. It is differential semantic validation, not a mechanized proof,
  exhaustive language test, provider study, or independent source parser.
- The source corpus is 15 partial, authored projections from three workflow
  DSLs, supported by a 17-candidate/4-repository pinned catalog. It is not 15
  complete application ports, an independent benchmark, a prevalence sample,
  or evidence of upstream vulnerabilities.
- The project has an MIT license, third-party notices, a citation file,
  build/use instructions, reproducibility commands, and a versioned local
  release-candidate label. The immutable public release and final human author
  review remain pending.
- The cyclic checker has six accepted graph certificates independently
  replayed; its finite graph grid checked 1,400 accepted runs and 800 paired
  secret-store comparisons with no request, billing-vector, or full-trace
  mismatch. A separate 3,000-case generated property probe found no mismatch
  in 11,696 ordered comparisons, but calls the graph producer's own reference
  evaluator and is therefore not independent semantic validation. The graph
  checker and replayer also pass an offline isolated-wheel installation and
  smoke check; see
  [`packaging_validation.json`](../output/release/packaging_validation.json).
- A bounded source-to-graph bridge now gates the exact parsed source snapshot
  with `orchc`, then checks and replays the generated graph. Its 12 tests
  include finite source-AST/graph-probe comparisons, identifier outputs, and a
  regression for source-file replacement between parse and compiler gate. A
  separate corpus report attempts five existing accepted workflows and 15
  balanced source-derived OrchLang files, distinct from the upstream source
  catalog. Prompts and outputs were not rewritten: 17 exported and three retry
  examples were explicitly excluded. Across the 17 exports,
  the finite grid records 720 source/graph run pairs, 360 secret-trace
  comparisons, and 1,584 call events with no source/graph or secret-trace
  difference. Output values are recorded but excluded from the billing
  comparison. This is finite evidence for an authored adapter and deterministic
  mock, not a translation proof or independent application study; details are
  in [`source_graphs/evaluation.json`](../bench/results/source_graphs/evaluation.json).
- A separate bounded Python AST frontend extracts a documented subset of
  LangGraph `StateGraph` source into a hash-bound graph/provenance package. The
  exporter parses but does not execute the source, and runs the graph checker
  plus the independent graph-certificate replayer. Its offline study executes
  only three validated authored fixtures under Python 3.14.6 and LangGraph
  1.2.14. Across 36 source runs, all 30 source-to-graph trace pairs match; 66
  call events are recorded, and six probes of deliberately rejected graphs
  agree on per-run traces. Of 15 paired secret assignments, 12 traces match
  and the three different-template pairs differ as expected. The 20-test
  frontend suite passes. This evidence covers the admitted subset and fixtures,
  not arbitrary Python/LangGraph source or a provider. The adapter uses
  binary64-normalized nominal price for contract identity and records integer
  usage only; it does not compute currency. See
  [`source_frontend/README.md`](../integrations/langgraph/source_frontend/README.md)
  and [`langgraph_source_study.json`](../bench/results/langgraph_source_study.json).
- The finite probability-channel study has 11 authored graph/kernel fixtures
  and 130 horizon/observer analyses. An independent DFS report replayer
  verified all 130 with limits of 1,000,000 paths, 10,000,000 control steps,
  and 1 GiB serialized work; producer/reference/replay suites pass 46 tests.
  This models integer usage and stop/truncation under a finite success-only
  rational kernel. It does not fit provider distributions or include currency,
  errors, or infinite-run behavior. The scope and result are in
  [`PROBABILISTIC_CHANNELS_REVIEW.md`](PROBABILISTIC_CHANNELS_REVIEW.md).
- An all-horizon finite-state checker applies exact-rational probabilistic
  partition refinement to reachable request/history states. Seventeen tests
  cover productive cycles, ordinal/history saturation, hidden-response
  quotienting, stop behavior, and pre-serialization resource caps. It proves sufficient
  equality of every finite ordered usage-trace law under the declared kernel;
  different blocks are inconclusive. This is standard strong probabilistic
  bisimulation specialized to the usage observer, not a new bisimulation
  method. Its report does not yet have an independent replayer.

The independent stress report is [`RELATIONAL_STRESS.md`](RELATIONAL_STRESS.md)
and its machine-readable results are
[`relational_stress.json`](../bench/results/relational_stress.json). The
reproduction manifest and logs are in [`audit/final`](../audit/final/).

## Scores and rubric

The previous **overall novelty score of 5.5/10** is the subjective project
score used in the research review and upgrade assessment, where 5 means a
focused contribution substantially built from established ideas. The earlier
draft's documented overall score was 4.5/10. The applied-method score was
3.5/10 before the request/contract/alignment upgrade and 5.5/10 afterward.
These are historical ratings from before the exact probabilistic channel
study, all-horizon checker, and current-guide review were fully incorporated.
Do not treat the table below as a final score for the current candidate; a
fresh review follows the live demo and final combined evidence audit. The new
quantitative features improve utility and evidence, but their core QIF and
bisimulation methods are established. The current comparison does not support
a novelty score of 8.

| Previous internal assessment | Score | Evidence at the time; historical only |
|---|---:|---|
| Novelty-based publication merit (internal scale) | **5.5/10** | Relational resource security and two-run verification are established; LLM workflow cost bounds now have a direct author-hosted neighboring treatment; request-aware coupling is a plausible narrow application delta, but no priority search was systematic and no provider semantics are validated. |
| SCP OSP scope/track fit | **7.5/10** | A compiler and static-analysis tool directly fits SCP's programming-language and software-tool scope. This preceded the in-app guide review. A local release candidate and no outside-use evidence limited the assessment. |

The previous **6.6/10 OSP-readiness score** used equal weights across the six
review dimensions. It is historical, not a current judgment. The finite
probabilistic report replay is complete; final combined reproduction, the live
demo, human author review, and immutable public release remain pending. Scores
are internal judgments, not publisher ratings or acceptance odds. An 8/10
readiness assessment would require strong evidence across all six dimensions,
including a public release and credible external utility. The LangGraph
source/runtime study is complete for its listed fixtures; it improves
cross-runtime evidence but does not prove the AST translator or raise
theoretical novelty by itself.

| Previous EAPLS review dimension | Weight | Score | Weighted contribution | Basis at the time; historical only |
|---|---:|---:|---:|---|
| Originality, novelty, and significance | 16⅔% | 5.5 | 0.92 | The specialized relation is useful and well scoped; its core techniques are established, with no provider study or external adoption evidence. |
| Source quality, completeness, and readability | 16⅔% | 7.0 | 1.17 | Compiler regressions, sanitizer evidence, graph checker/replayer, source bridges, and a narrow AST frontend with fail-closed exclusions exist; neither frontend has an independent source-translation proof, and final combined reproduction/review remain. |
| User and developer documentation | 16⅔% | 7.0 | 1.17 | Language, formal contract, cyclic graphs, both source bridges, installation, and reproducibility are documented; final short OSP manuscript and author review are pending. |
| Reproducibility of empirical results | 16⅔% | 7.5 | 1.25 | Versioned scripts, data, hashes, core manifest, graph grids, LangGraph differential study, and isolated-wheel smoke report are present; no public immutable archive or external rerun is recorded. |
| Accessibility and ease of configuration/use | 16⅔% | 6.5 | 1.08 | The graph wheel and optional pinned LangGraph environment have isolated setup instructions; the C++ compiler is separate, validation is on one macOS environment, and a public release is pending. |
| Accompanying manuscript clarity | 16⅔% | 6.0 | 1.00 | The full draft has explicit scope and limitations; a short OSP article is being prepared, and human review remains. |
| **Historical equal-weight total** | **100%** |  | **6.6/10** | Arithmetic mean was 6.58/10 before rounding; not rescored after the later additions. |

The rubric measures this local candidate against the six dimensions stated in
the EAPLS call. It is not the journal's actual scoring form and cannot be read
as an estimate of its decision.

## Why the novelty score is not 8

The closest established line already combines information-flow security with
resource behavior: Ngo et al. formalize resource-aware noninterference and
prove it for a resource-annotated language. RelCost and related relational
refinement systems compare costs across executions. Product programs and
self-composition reduce 2-run properties such as noninterference to paired
verification. Probabilistic resource analysis and PPDL show that stochastic
programs and multi-call LLM workflows can be analyzed quantitatively. A
May 2026 author-hosted note by Dickerson additionally describes Petri-net
upper bounds for cumulative LLM-agent resources, including a token-cost case;
it is unrefereed in this review and its empirical claims remain author
reported. These works do not state the exact OrchLang property, but they make
the unary cost theorem, two-run product, or LLM context individually
insufficient novelty claims. The full comparison and sources are in
[`PRIOR_ART_MATRIX.md`](PRIOR_ART_MATRIX.md) and
[`research/literature_sources.csv`](../research/literature_sources.csv).

The surviving distinction is narrow and potentially useful: static matching
of resolved model contracts, exact abstract requests, aligned earlier call
results, and usage observations under a specified shared request-sensitive
oracle. The oracle assumption is also the main limitation. The runtime mock
and independent generated reference validate the declared abstraction; neither
demonstrates that provider APIs expose or preserve it. The current source
examples and authored extra-call changes are methodology tests, not real
applications or security incidents.

The reviewed cyclic-graph extension now improves supported workflow shape and
exercises coinductive closure over call-bearing cycles. Product-program and
bisimulation methods already exist; this finite application frontend is a
modest method/software contribution, not a route by itself from 5.5 to 8. The
graph certificate replayer is independently implemented, while the source
bridge is not verified and the property probe reuses the producer's reference
evaluator. See the separate design review for the proof conditions and
exclusions.

## Practical route to stronger SCP OSP value

The highest-value next work depends on whether the goal is novelty or an OSP
artifact:

1. **For method novelty:** the exact finite usage-channel analyzer and
   all-horizon equality checker now go beyond the original shared-coupling
   gate in what they report, but they apply established QIF metrics and
   probabilistic bisimulation. A stronger contribution needs a proved result
   or precision/usefulness advantage that does not reduce to these standard
   analyses on a finite request graph. Any proposed extension should be
   compared directly with PPDL, point-to-point leakage analysis, symbolic QIF,
   and probabilistic model checking before a novelty claim is raised.
2. **For deployment relevance:** add a carefully scoped provider adapter that
   captures the actual request envelope and returned usage record, then
   validate which observations are available to a realistic operator. Keep
   the shared-oracle theorem conditional; an adapter cannot turn independent
   stochastic provider samples into identical responses. Obtain outside
   workflows/users only with consent and report failures as well as successes.
3. **For OSP readiness:** obtain human author review; complete affiliation,
   contact, author-contribution, conflict, and AI-use declarations; prepare
   the paper, editable highlights, and metadata under the verified current
   guide; publish and archive a reviewed, immutable version with a stable
   citation; and provide an installation/use walkthrough that a new user can
   reproduce. The EAPLS call describes OSPs as
   citable archived software publications that can capture future software
   updates. An independent user or case study would provide the strongest
   missing usefulness evidence. These gates improve availability and software
   utility but do not change the novelty score by themselves.

The bounded LangGraph frontend and runtime study now provide a concrete
cross-runtime path from an admitted source subset to a replayed graph and a
trace comparison against actual LangGraph execution. This strengthens
accessibility and utility evidence. The extractor is not independently
verified, the study uses authored fixtures and a shared offline oracle, and
arbitrary LangGraph features remain excluded. A source-translation proof or a
qualitatively stronger analysis result would be needed for a larger method
contribution.

The EAPLS call frames the track around existing useful software and names
accessibility, documentation, reproducibility, code quality, contribution
significance, and manuscript clarity as review dimensions. The live guide and
templates have now been checked; the manuscript and highlights still need to
be prepared in the prescribed files, with the required metadata table filled.
The guide suggests 3–6 pages under its stated exclusions; it is not described
here as a hard page limit. No contact or submission is part of this review.

## Current journal recommendation

**SCP Software Track / OSP remains the best subject fit if the goal is to
disseminate OrchLang as reusable software.** The artifact has enough substance
to support continued preparation, but the publisher's usefulness threshold
cannot be inferred from a local checklist, and no external reuse is recorded.
Avoid a novelty-first title or claim that the graph product is new theory.
Frame the software's concrete function, supported fragment, output artifacts,
reproduction workflow, and limits; explain the request-sensitive relational
check as a focused feature.

**JSS New Ideas and Trends remains the alternative for the single research
idea.** It is not a substitute for a stronger novelty result: the current
paper would need a journal-specific single-contribution format and more
external validity. The current manuscript/release state is not ready to
submit to either journal without human author review, required submission
files, and a public immutable software version.
