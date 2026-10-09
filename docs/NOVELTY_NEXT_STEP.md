# Novelty assessment and next substantive study

**Review date:** 9 October 2026  
**Target:** *Science of Computer Programming*, Software Track, Original
Software Publication (OSP)  
**Status:** The current reproduction and incident-triage path study pass.
This document identifies the remaining contribution-level gap; it does not
describe unfinished source-path coverage.

## Current judgment

OrchLang's general methods are established: relational/resource
noninterference, quantitative information flow, finite probabilistic
analysis, probabilistic bisimulation, and weighted-automata trace equivalence
all have substantial prior art. The project contributes an inspectable
software specialization for bounded, request-sensitive LLM workflow
observations, with replayable artifacts and a source-grounded case study.
The formal and literature boundaries are summarized in
[FORMAL_CONTRACT.md](FORMAL_CONTRACT.md),
[trace_equivalence_primary_sources.md](../research/trace_equivalence_primary_sources.md),
and [SOURCE_PROTOCOL_PRIOR_ART.md](../research/SOURCE_PROTOCOL_PRIOR_ART.md).

My current subjective scores are: **SCP OSP originality/novelty/significance
7.1/10** (6.2 initial; 6.4 after the first direct-source study; 6.9 after the
source protocol and concurrency result; 7.1 after source-path coverage and
the refreshed reproductions); **overall applied-project novelty
6.5/10** (historical 4.5); **applied-method novelty 6.2/10** (historical
3.5); **research-software contribution 7.3/10**. These are not journal
ratings or acceptance probabilities. The OSP call has no published numeric
threshold. The evidence supports a meaningful software contribution, but not
the requested score of 8.

The just-completed 16-stage incident extension reproduction
([manifest](../audit/incident_triage/manifest.json), SHA-256
`b5a71d7ecd7497c4cce006407164a976cb75f58b8b43a335c44e182ebe7a02a0`)
and full 44-stage project reproduction
([manifest](../audit/final/manifest.json), SHA-256
`3e019b4cc368ee7026afa9c7f83b76abb226c69e3da7826efe7cc6d0a8b43b7d`)
close the prior path-coverage and local reproducibility gap. The extension
contains six authored source schedules, 12 runs and 24 calls, all six paired
selected observations equal, nine independent replay checks, and 10 focused
tests. The manager and controlled concurrency suite has 19 tests. These
results strengthen completeness and confidence, not general-method novelty.

## What the current real-source result demonstrates

On unchanged MIT source revision
[`c08f710acfeefe233329df613fe8358eaac5f350`](https://github.com/codewithkachi/agent-incident-triage/tree/c08f710acfeefe233329df613fe8358eaac5f350),
the project has a direct offline execution study, an independently checked
source-specific AST dependency protocol, a classifier-request relational
certificate, selected path tests, and a controlled concurrent execution.
That schedule exposes concrete misattribution and duplicate rows in the
source's closure-scoped meter; the bounded offline session manager exercises
one per-incident isolation mitigation. This is stronger than purely authored
compiler examples: it connects code, selected requests and usage records to
actual execution of a public workflow.

The claim remains deliberately narrow. The source protocol is pinned to one
application revision. The graph certificate covers the first classifier
request pair, while the rest of the source dependency path is checked by a
bespoke AST contract and selected executions. The path schedules and mock
outcomes are authored, the race is one controlled interleaving, and the
manager is not a production service. This does not establish provider billing,
universal PII handling, checkpoint privacy, arbitrary-schedule safety, or
general Python translation. The 15 partial projections across public
framework examples and the LangGraph runtime studies are useful engineering
coverage, but they are not 15 independent real applications.

## Remaining contribution gap

The remaining gap is **transferable source-to-observer evidence with a
comparative claim of analytical value**. One source-bound case shows a
concrete workflow-specific behavior, but the project has not yet shown that a
predeclared adapter/checking method can be reused on an independently selected
application and reveal a property that its own tests or ordinary source
review do not establish as clearly. This is why the software contribution
scores well but remains below 8.

### Recommended next study

Select one maintained, permissively licensed, public LLM workflow using
criteria fixed before inspection: real model-call sites, a meaningful result
or cost/data-flow dependency, and enough static structure to define a bounded
subset. Do not pick a project to fit a known desired counterexample. Then:

1. Pin the immutable source revision, license, files, environment, and
   source hashes. Record candidate selection criteria and all source files
   excluded from analysis.
2. Freeze a predeclared source subset and observation before writing the
   adapter. Admit only statically explained calls, templates/arguments,
   result updates, guards, retries, and accounting. Reject unknown helpers,
   dynamic registration, unsupported state reducers, concurrency, or other
   behavior outside the subset.
3. Export a source-to-observer correspondence with source locations and
   lexical bindings. Have an independently written replayer reconstruct
   mappings and reject missing/extra calls, changed request atoms, wrong
   result bindings, altered retry edges, and mismatched guards/routes.
4. Differentially execute admitted source paths with a declared offline
   oracle. Compare complete modeled requests, source usage rows, selected
   routes, and stop/interrupt observations. Report mapped and rejected
   coverage, not just passing examples.
5. State one pre-registered analysis question and compare its result with
   upstream tests and ordinary source review. A substantive result could be
   a replayable counterexample or a useful proof about request/usage
   dependence that these baselines did not directly provide. Do not claim
   provider behavior from a mock or infer real-world prevalence from authored
   schedules.

This is a feasible software-method extension, but it is not guaranteed to
raise the score. A faithful mapping with no incremental finding would support
transferability, not an 8 by itself. A second useful, source-grounded result
plus the independently checked correspondence would justify reconsidering
significance. External adoption is not a categorical requirement for an OSP;
it is also not a substitute for analytical leverage.

### Work that is not a substitute

More generated graphs, probability kernels, finite horizons, test counts, or
authored response schedules would increase implementation confidence but do
not resolve the transfer gap. A new general quantitative metric or compiler
syntax feature is also low priority unless it enables the source-level study
above. Do not claim a new general algorithm by renaming bisimulation, weighted
span equivalence, translation validation, or source slicing.

## Publication boundary

The technical content and evidence are credible for critical human review.
The rebuilt 10-page OSP PDF still needs final layout QA and condensation
against the guide's suggested 3–6 pages of abstract plus running text. The
manuscript and compliance metadata also need to point at one immutable
candidate that contains the just-passed manifests and artifacts; the existing
public link and compliance record identify the older `af707fe` base. Final
author facts, AI-use review, and submission approval remain human actions.
These are release/readiness items separate from this novelty assessment. Full
details and the current OSP readiness judgment are in
[FINAL_PUBLICATION_REVIEW.md](FINAL_PUBLICATION_REVIEW.md).
