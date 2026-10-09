# Independent publication review: SCP Software Track OSP

**Review date:** 9 October 2026  
**Target:** *Science of Computer Programming*, Software Track, Original
Software Publication (OSP)  
**Status:** Evidence review completed for the current working tree. The
technical content is credible for critical human review; the current OSP PDF
still needs layout/length QA, and the submission bundle is not synchronized
to the current evidence or public immutable release. Scores below are
subjective contribution assessments, not editorial ratings or acceptance
probabilities.

## Assessment

OrchLang is an integrated research-software artifact for checking and
replaying selected request, usage, and probabilistic properties of bounded
LLM workflows. The contribution combines a compiler, graph and rational-kernel
analyses, independent certificate/report replayers, bounded source adapters,
an optional actual LangGraph execution path, an installable offline wheel,
and a local demonstration. Its strongest applied result is now a source-bound
study of one unchanged MIT LangGraph incident-triage program: it records a
controlled shared-meter race, checks a narrow source dependency protocol,
executes selected source paths, and tests a bounded per-incident mitigation.

The general theory is established. Relational cost analysis,
resource-aware noninterference, quantitative information flow, probabilistic
resource analysis, automata trace equivalence, weighted span methods, and
probabilistic bisimulation are prior art. OrchLang's contribution is a
bounded, replay-oriented specialization and usable software integration for
request-sensitive LLM workflow observations, together with the source-specific
case study. The paper should not claim a new general theorem or new general
equivalence algorithm.

### Scores

| Dimension | Initial | Current | Assessment |
|---|---:|---:|---|
| Fundamental theory novelty | 2.5 | 3.0 | Formal contracts and proof boundaries are clear; the underlying theories are established and the source mapping is not mechanized. |
| Applied analysis-method novelty | 3.5 | 6.2 | The compiler and replay tools make a useful workflow-specific combination, but the real-source protocol remains version-bound and the full control flow is not translated into one general source graph. |
| Research-software contribution | 4.0 | 7.3 | The compiler/checkers, exact replay artifacts, bounded source/runtime integration, and source-specific concurrency utility form a substantial, inspectable package. |
| Evidence | 2.0 | 8.2 | Reproducible core, source, path, concurrency, and manager studies have independent checks; the real-source evidence is still one pinned application with authored offline outcomes. |
| Overall applied-project novelty | **4.5** | **6.5** | A meaningful improvement through coherent software and source-grounded findings; transferability and measured broader impact remain limited. |
| SCP OSP originality, novelty, significance | **6.2** | **7.1** | A credible software-track contribution; the six independently replayed source paths close an evidence gap, but not yet an 8-level demonstration of transfer or broad analytical leverage. |

These ratings use the same internal comparison scale as the earlier reviews:
5 denotes a focused software contribution assembled from established methods;
around 7 denotes a substantial, reproducible specialization with a concrete
use case and meaningful scope limits. The requested 8 is not supported by the
current evidence. The OSP call publishes review dimensions, not a numeric
threshold; these are not predictions of acceptance.

The OSP dimensions, scored as an internal quality proxy, are: originality,
novelty and significance **7.1**; source quality/completeness/readability
**8.2**; documentation **7.9**; reproducibility **8.3**; accessibility and
configuration **7.8**; manuscript clarity **7.5**. Their equal-weight mean is
**7.8/10**. This is not an SCP score. The software fits SCP OSP well
(**8.5/10 scope fit**) because it is executable software for programming
language analysis and workflow verification; fit does not establish
originality. The published six review dimensions and current formatting
requirements are summarized in [SCP_AUTHOR_REQUIREMENTS.md](SCP_AUTHOR_REQUIREMENTS.md).
Calibration against the complete published HBSniff and FTS4VMC texts, the
OpenJDK BitSet OSP record/abstract and its full companion paper is documented in
[SCP_OSP_CALIBRATION.md](../research/SCP_OSP_CALIBRATION.md). These examples
show different credible software-artifact contributions; they establish
neither a numerical threshold nor a categorical adoption requirement.

## Evidence reviewed

### Full project and source-extension reproductions

The current full reproduction is `audit/final/manifest.json`, SHA-256
`3e019b4cc368ee7026afa9c7f83b76abb226c69e3da7826efe7cc6d0a8b43b7d`.
It passed all 44 stages with `quick=false`, sanitizer, packaging, and the
optional LangGraph integration enabled. It records unchanged inputs and
binds the current compiler and source inventories; its base revision is
`af707fe5a13c888860ea99b94d599ae3ef9c1027`, while the manifest itself says
the working-tree release-candidate edits are identified by file inventories,
not by that base revision alone. The main Python suite reports 203 passing
tests.

The source-specific extension has its own passed 16-stage manifest,
`audit/incident_triage/manifest.json`, SHA-256
`b5a71d7ecd7497c4cce006407164a976cb75f58b8b43a335c44e182ebe7a02a0`.
It covers source bundle verification and offline checkout, execution and
independent replay of the direct-source study, source protocol, controlled
concurrency study and witness, session manager, and scripted source paths.
The manifest records unchanged inputs and byte-identical reproductions. It
pins upstream revision
[`c08f710acfeefe233329df613fe8358eaac5f350`](https://github.com/codewithkachi/agent-incident-triage/tree/c08f710acfeefe233329df613fe8358eaac5f350).
The 44-stage project manifest inventories incident-triage executable sources,
manager, tests and dependency lock. The separate extension manifest also binds
the recorded JSON reports, attestations, full upstream snapshot and local bundle.

The full project evidence includes the bounded compiler and graph studies,
finite probability reports, all-finite-horizon equality/witness tools,
partial projections of public framework examples, a Python LangGraph
front end and optional runtime backend, and a functioning offline HTML demo.
The comparisons are authored or bounded source projections, not a held-out
benchmark or independent application population. They must be described by
their stated scope and not added up as independent real-world deployments.

### Pinned incident-triage source result

The unchanged MIT source was run through its actual LangGraph graph under an
offline deterministic mock. The direct-source corpus contains 22 executions,
45 calls, and 87 node events, with an independent verifier. The exact-source
dependency protocol binds request construction, redaction, helper/schema
logic, repair, selected control and accounting dependencies, and a pre-
dispatch gate to pinned source. It independently reconstructs its declared
AST contract and rejects authored raw-text bypass mutations. The key
qualification is that the OrchGraph certificate covers only the first
classifier request pair. The rest is a strict, version-pinned source
dependency argument, not a general Python/LangGraph translation or
mechanized semantics proof.

The new path study adds six authored response schedules, each executed twice
with inputs that redact to the same value: repair success, double schema
failure to human review, a 295-character summary passed to drafting, malformed
draft fallback, critical-site priority increase, and a synthetic budget
stop. It records 12 runs and 24 source calls; all six pairs have equal
selected observations. The independent standard-library replayer reports
nine checks, and the focused path suite has 10 tests. Its 400,000-leading-
space fixture exercises the source's `len(text)//4` estimate and nominal
`gpt-4o-mini` price guard only. It uses a fixed offline response, spends no
money, and does not establish provider tokenization or billing behavior.

The controlled concurrency schedule exposes one concrete source behavior:
four unique source calls account for 456 estimated units, while adding
returned snapshots gives 687 because B's 231 units are present in A's
snapshot; A's classifier row is also labelled as draft. The per-incident
control restores ownership and retains each app for approval. This is a
source-specific controlled witness, not a claim of an upstream vulnerability
or arbitrary-schedule concurrency safety.

The bounded offline `IsolatedSessionManager` is tested with 13 lifecycle
tests plus six concurrency/witness tests. Peer review found and prompted fixes
for an import-name substitution, cancellation cleanup, non-finite TTL,
expiry/capacity behavior, and unbounded evidence reads; the final extension
reproduction includes current code and tests. This review records those
reproduced results, but does not claim the manager is a production service,
cross-process session store, or full checkpoint privacy mechanism. A Python
process is trusted, expiry may need periodic sweeping while idle, and the
study does not establish arbitrary-schedule linearizability.

### Limits that remain part of the result

The core theorem is conditional on the modeled oracle, requests, accounting,
resolved model contract, and binary64 nominal-price contract. The finite
probability tools assume supplied rational kernels; the all-finite-horizon
result is for its selected success-only usage observer. No result certifies
real-provider response laws, tokenizer usage, invoices, prompt-injection
resistance, universal PII detection, raw checkpoint privacy, unrestricted
Python translation, termination, or finite total cost for productive cycles.
Independent artifact replay checks the specified facts; it is not a complete
independent interpreter or a full proof of source/compiler correctness.

## Publication readiness

**Technical review:** credible now for a human author/reviewer to inspect the
method, artifact, and scoped evidence. The source finding is concrete, the
reproduction is hash-bound, limitations are explicit, and the reviewers can
replay important claims without provider access.

**Submission bundle:** not yet ready to submit. The manuscript compliance
record still points to the older public commit
[`af707fe`](https://github.com/guyoverclocked/orchlang-compiler-design-project/tree/af707fe5a13c888860ea99b94d599ae3ef9c1027)
and the earlier reproduction-manifest digest
`65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035`, rather
than the current manifest above and source-extension evidence. The current
source changes have not yet been made an immutable public candidate. The
author's names/order, affiliation and contact, CRediT roles, funding/conflict
declarations, AI-use review, and final submission approval are also still
marked for human confirmation. These are concrete synchronization and author
review steps, not gaps in the current experiment. The rebuilt OSP manuscript
is currently reported at 10 pages and still needs final visual QA and
condensation against the guide's suggested 3–6 pages of abstract plus running
text (excluding front matter, references, metadata, tables, and figures).

I rate **submission readiness 6.5/10**: the technical content and local
evidence are reviewable, but the final PDF still needs format QA, the cited
public artifact and manuscript metadata are not tied to the same frozen
release, and author facts remain open. After immutable release,
compliance/source cross-check, PDF QA, and human approval, readiness can be
reconsidered without changing the novelty score.

## What still separates this from an 8

The remaining substantive gap is **transfer plus comparative analytical
value**, not missing path fixtures. The new paths close the earlier coverage
gap. The current source profile is still one hand-pinned application; its
source protocol is bespoke, the checked graph certificate is classifier-only,
and the concurrency issue is one controlled schedule. The other source
examples in the package are explicitly partial projections or authored
workloads, not a second independently selected real application with a
source-to-observer result.

A useful next study would apply a predeclared subset of the source protocol to
one independent public LLM workflow, bind its revision, state all exclusions,
and independently replay a source-derived finding that ordinary tests or
straight source review did not establish as clearly. It should report both
successful mapping and fail-closed coverage, and compare the finding with the
workflow's own tests/review. If no new analytical leverage appears, report
that honestly. Such a result could support a stronger software-significance
case; it would not mechanically earn an 8, require external adoption, or
alter the established-theory boundary. See
[NOVELTY_NEXT_STEP.md](NOVELTY_NEXT_STEP.md) for the bounded proposal.

The defensible narrative is: **offline research software for replayable,
request-sensitive usage analysis of bounded LLM workflows, with a
source-grounded LangGraph case study that demonstrates a specific
concurrency-attribution failure and a tested isolation mitigation.** Keep the
compiler theorem, supplied-kernel probability results, source-specific
protocol, and controlled runtime finding as separate evidence layers.
