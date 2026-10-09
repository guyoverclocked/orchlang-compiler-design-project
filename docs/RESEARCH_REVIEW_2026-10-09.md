# OrchLang research review

**Date:** 9 October 2026  
**Purpose:** Update the prior research audit with current literature, narrow the
novelty claim, assess a source-derived workflow sample, and recommend credible
publication routes. This document is a research review, not an implementation
audit or a prediction of acceptance.

## Executive finding

OrchLang's most defensible research question is narrower than the earlier
project framing: **can a static analyzer prove equality of per-contract usage
traces across secret-controlled alternatives in a bounded LLM workflow under a
shared, request-sensitive abstract oracle?** The current rule is a sufficient,
compositional signature check. It applies established relational cost and
resource-aware information-flow ideas to external stochastic call effects; it
does not introduce a new general noninterference principle.

Do not claim that numeric potentials cannot apply to stochastic/LLM programs.
Probabilistic resource analysis has derived expected bounds for stochastic
programs, and peer-reviewed PPDL (ICML 2026) gives probabilistic semantics to
multi-call LLM flows. Its full paper also evaluates within total-token budgets
and logs token usage in a proof-repair example. The valid distinction is the
property: a token budget, expected resource bound, or output-distribution model
is not the same as **pathwise equality of two per-contract usage traces under
a specified coupling** or a quantitative leakage measure for that usage
observer. Do not frame workflow trace distributions or token budgets as absent
from prior work. The question is whether a relational usage-observer analysis
can compose soundly under a declared call contract—not whether all numeric or
probabilistic analysis is impossible.

The core general ideas are not new: resource-aware noninterference, relational
cost analysis, probabilistic resource bounds, prompt-programming languages,
agent IFC, and static checks over agent graphs all have prior art. The narrower
contribution is the invocation-level abstraction: resolved model contracts,
exact DSL template bytes and ordered argument values, aligned call positions,
and symbolic references to matched earlier results. Here “request” means that
abstract DSL descriptor, not a provider's complete serialized request. Alias
normalization and exact literal accounting are soundness repairs, not novelty
by themselves.

The practical issue matters when the threat model includes an observer of
per-run/per-contract token-usage records or related token-length observations.
Current deployment evidence is limited: the compiler has no live provider
adapter and no observed invoice/usage telemetry study. State these as
conditional observations and assumptions. Do not imply that every invoice
reveals a per-request trace or that usage signatures protect timing,
encrypted-traffic length, or prompt injection.

## What was reviewed and how

I read the existing project research and submission materials (`README.md`,
`docs/AGENT_BRIEF.md`, `docs/PAPER.md`, `docs/LANGUAGE_SPEC.md`,
`docs/SUBMISSION_PLAN.md`, `docs/RESEARCH_AUDIT_2026-09-17.md`,
`docs/REVIEW2_PROGRESS_REPORT.md`, `docs/REVIEW_DEMO.md`, and the submission
readmes), then inspected the shared checkout's relational analyzer, semantic
facts, interpreter, and certificate interfaces. The previous September audit is
treated as an input, not repeated as a clean independent reproduction.

This was a **targeted literature audit**, not a systematic review. OpenAlex was
used for discovery and to batch-resolve eight selected DOI/work records:
resource-aware constant-resource types, RelCost, monadic relational refinements,
bounded expectations, adaptive QIF, LMQL, APPL, and PPDL. OpenAlex is a metadata
cross-check, not the authority for a paper's theorem or publication status.
Claims were checked against the linked primary publisher, conference, or
author-version page; exact article and source boundaries are recorded in
[`research/literature_sources.csv`](../research/literature_sources.csv). For
2026–2025 work available only on arXiv in this audit, I label it a preprint and
do not treat author-reported results as independently replicated. PPDL's PMLR
page verifies publication at ICML 2026; its arXiv record alone was not used to
establish peer review. A follow-up targeted search found Dickerson's 18 May
2026 author-hosted research note on Petri-net bounds for monotone cumulative
resources in LLM-agent workflows, including a token-cost case and an author-
reported provider experiment. No peer-reviewed venue or DOI was located. This
is relevant prior art for unary LLM-workflow cost bounds, but it does not state
the relational usage-trace property studied here. For a separate cyclic-graph
method review, three OpenAlex searches failed with network/TLS errors; the
product-program references were therefore checked against primary conference
or publisher records linked in the literature inventory.

The research catalog contains 17 pinned candidate source files from four public
workflow repositories (IBM PDL, APPL, LMQL, LangGraph). The executed corpus is
narrower: 15 partial, authored projections from three DSL frameworks (PDL,
APPL, LMQL), each with base, balanced-secret-arm, and extra-call unbalanced
variants. Thus the evidence is **not 17 executed ports**, 15 full application
ports, or an independent security benchmark. The catalog records source
revisions, paths and line spans, SHA-256, licenses, URLs, projection recipes,
and exclusions in [`research/workflow_patterns.csv`](../research/workflow_patterns.csv);
executed artifact hashes and partial semantics are in
[`bench/sourced/manifest.json`](../bench/sourced/manifest.json). The catalog's
P08 is the executed PDL RAG example. An earlier candidate, PDL's GSM8K
multi-plan example, is a historical excluded candidate outside this current
17-row catalog. No source project is being accused of containing an injected
secret or bad flow.

The manuscript's scope should stay aligned with this review: the property
is abstract usage-trace equality under Ω(c,k,Q), not independence of output
contents from secret-controlled paths and not a provider invoice theorem. The
content label tracks explicit data dependence and excludes program-counter
dependence; it does not by itself establish secret independence. Output and
tool policies use effective labels that include control dependence, while
secret-arm request matching is a separate relational obligation. The whole-workflow
usage-trace claim also excludes declassification.

## The result worth defending

The best candidate contribution is:

> A static sufficient check for equality of per-contract usage traces across
> secret-controlled alternatives in a bounded workflow language. It compares
> resolved model contracts and abstract request descriptors (template bytes
> plus ordered argument values), including references to earlier aligned
> results, under a shared oracle keyed by contract, call ordinal, and abstract
> request. The guarantee is conditional on this model and its cost assumptions.

The primary theorem compares executions with the same shared abstract oracle
and retry schedule; it does not claim that independently sampled runs have the
same response path. A conditional distributional corollary follows under a
secret-independent conditional kernel over complete outcomes at matched
request/history keys: an identity coupling yields equal usage-trace laws. This
is standard probabilistic coupling, is not encoded or checked by the
implementation, and does not establish any real provider kernel. It concerns
the abstract DSL request, not a complete provider invocation. It proves no
equality of workflow outputs, tool effects, timing, or other observations
beyond the declared usage trace. Its shared oracle is Ω(c,k,Q), where `c` is the resolved model
contract, `k` the per-contract call ordinal, and `Q` the exact template bytes
with ordered argument values. Equal keys have equal complete abstract outcomes
and usage; equal ordinals with different `Q` need not. This does not model
provider-added messages, tool schemas, request options, wire serialization,
real response text, or invoice adjustments. The separate input-bound premise
is per call: `I <= ceil(UTF8_bytes(template)/d) + sum(argument bounds)` in a
common target-tokenizer unit, with no uncounted system/tool/provider overhead
and no serialization or tokenizer-boundary interaction that exceeds the sum.
`d` alone is not a provider-accounting theorem. See
[`FORMAL_CONTRACT.md`](FORMAL_CONTRACT.md) for detailed assumptions and proof
sketches. The executable request-sensitive mock keys exact template/literal
bytes; it represents identifier values only with mock token-count/flag fields
and generates no response text. It is a projection of the abstract oracle,
not a provider adapter.

For the property itself, compare against the established alternatives instead
of implying a gap no one has explored:

- AARA and resource-aware noninterference already combine information flow and
  resource behavior. RelCost and monadic refinements already compare costs
  relationally.
- Bounded Expectations demonstrates numeric expected-resource analysis for
  probabilistic programs. PPDL models multi-call LLM/tool flow distributions,
  operates under token budgets in its evaluation, and records token usage in
  its proof-repair example. Its target is probabilistic output quality and
  inference scaling, not a static secret-conditioned usage-observer leakage
  property.
- Dickerson's author-hosted 2026 note directly describes static cumulative
  token-cost bounds for LLM-agent workflows using a Petri-net structure. Its
  peer-review status was not established here. Accordingly, OrchLang's unary
  token bound is supporting functionality, not a distinguishing novelty claim;
  the claimed delta remains relational request alignment under a specified
  shared oracle.
- QIF measures an attacker's uncertainty from side-channel observations.
  Pathwise equality is stricter/different; neither dominates every other
  security question.
- LMQL, APPL, and PDL establish prompt/workflow programming as prior work.
- CaMeL, FIDES, AgentFlow, and Agentproof cover neighboring agent information
  flows, tool policies, and workflow graph checks. AgentFlow includes a bounded
  static verifier; Agentproof explicitly checks static graphs. OrchLang should
  describe its different property rather than state that agent verification is
  runtime-only or absent.
- USENIX work on remote token-length inference and LLM timing preprints establish
  that token length and latency can form side channels. They are not studies of
  an individual bill trace and are not the source of OrchLang's novelty claim.
- ProMCP profiles token and latency costs across MCP pipelines. New 2026 work
  also studies hidden provider operations and provider-side token inflation
  (Sun et al.; IMMACULATE; Hoque et al.; Chen et al.), while Persistent
  Billable State studies host-side re-ingestion costs. These are distinct
  threat models; they rule out broad “LLM token audit” and “agent cost control
  is unaddressed” claims. The individual sources and publication-status
  boundaries are in [`PRIOR_ART_MATRIX.md`](PRIOR_ART_MATRIX.md) and
  [`research/literature_sources.csv`](../research/literature_sources.csv).

No standalone canonical publication acronym “RANIF” was found by targeted exact
search/OpenAlex checking. Use the cited full work title—Ngo et al.,
*Verifying and Synthesizing Constant-Resource Implementations with Types*—and
call its property resource-aware noninterference. Do not cite “RANIF” as a
separate paper without a specific bibliographic record.

## Novelty and project assessment

These subjective 0–10 scores are **not acceptance probabilities**. A 5 means
a focused contribution substantially built from established ideas; 10 means a
major field-level advance. The first numeric column is this review's audit of
the earlier draft; the final column scores the October 9 artifact and evidence
now present. Using the same subjective overall-project rubric, the documented earlier
self-rating was 4.5/10 and this review's current assessment is 5.5/10. The
overall rating is not an average of the dimension scores.

| Dimension | Earlier draft | October 9 current | Why the score changed (or did not) |
|---|---:|---:|---|
| Fundamental theory | 2.5 | 3.0 | The shared-oracle contract and proof sketches sharpen a useful specialization; resource-aware NI, relational costs, and probabilistic resource analysis remain prior art. Proof sketches are not mechanized. |
| Applied analysis method | 3.5 | 5.5 | The implementation now resolves model aliases/contracts, compares exact abstract request descriptors, aligns call ordinals and matched earlier results, and accepts balanced secret arms including supported chains. This is the main methodological gain. |
| Compiler/software artifact | 4.0 | 6.0 | The compiler now has resolved-contract and request-aware relational checks, certificates/reports, an MIT license, citation metadata, pinned source manifests, and a cost-report auditor. A finite cyclic-graph checker has a separately implemented certificate replayer and an offline isolated-wheel smoke test; a bounded source bridge gates exact source/compiler snapshots. These are useful research tools, though the bridge is not verified, no provider adapter or independent full-source IFC/relational proof checker exists, and immutable public release is pending. |
| Evaluation evidence | 2.0 | 5.0 | The two mock grids, 111 C++ tests, 19 cost-auditor tests, and a separate generated-AST/full-text reference stress study now cross-check accepted cases and find finite witnesses for most authored mutations. The study is still synthetic, same-author, finite, and not provider validation or 15 independent applications. |
| Research framing | 2.5 | 5.5 | The claim is narrowed to request-sensitive shared-oracle usage-trace equality, with resource-aware and probabilistic prior art and security/workflow neighbors acknowledged. Deployment claims remain limited. |

The current evidence is reported separately for each oracle mode; do not add
the two grids and describe the result as independent trials. **In both ordinal
and request-sensitive modes separately**, the result files report 1,500 base
executions with 0 component-bound violations; 2,250 balanced paired comparisons
with 0 usage-observation mismatches; 2,250 extra-call unbalanced
comparisons with 2,250 mismatches; 30 source cost reports checked; and all 15
balanced variants accepted by the new compiler versus 8 by the baseline. The new compiler rejects
all 15 authored unbalanced variants. These are deterministic offline mock checks on a purposive corpus. The ordinal
and request-sensitive records are [`sourced.json`](../bench/results/sourced.json)
and [`sourced_request_sensitive.json`](../bench/results/sourced_request_sensitive.json).
The final reproduction manifest records optimized compiler SHA-256
`5bae3be94e9b7d747728965e2562d06a9844d47b28f871c6fe44dcb6f0a7aa43`, baseline
commit `a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9`, 111/111 optimized C++ tests,
sanitizer success, 19/19 source-cost-auditor tests, and 29 expected reproduction
stages; see [`audit/final/manifest.json`](../audit/final/manifest.json) and
[`audit/final/auditor-tests.log`](../audit/final/auditor-tests.log).
The separate Python source-cost auditor checks report consistency only; it is
not an independent IFC or relational proof checker. The C++ tests include
regressions for nonfinite prices, derived monetary overflow, and JSON control
bytes; these protect certificate/report behavior, not the relational theorem.

### Supplemental validation update (9 October 2026)

After the score table was first finalized, a separate Python interpreter was
added to evaluate complete rendered request strings and compare usage traces
across secret assignments. It consumes the generated AST rather than compiler
facts or C++ runtime output; the compiler is used only for `orchc check`.
Across 264 generated cases, 144 accepted cases passed, and the reference ran
13,824 accepted secret-assignment comparisons (24,192 executions, 66,240 model
calls, and 66,240 per-call accounting checks) with zero request/usage
mismatches. All 120 authored mutations were rejected; 117 had a finite-grid
request/usage witness and three retry-bound mutations had no witness and remain
unknown. This improves evidence quality modestly, so the evaluation dimension
is updated from 4.5 to 5.0. It does not change the 5.5 overall or applied-method
scores: it validates the implemented conditional abstraction, not its novelty
or provider realism. Full methodology and caveats are in
[`RELATIONAL_STRESS.md`](RELATIONAL_STRESS.md) and
[`bench/results/relational_stress.json`](../bench/results/relational_stress.json).

The applied-method score rises from 3.5 to 5.5 because the design has a more
precise abstraction and demonstrably handles patterns the earlier baseline
rejected. The overall project score rises from the documented 4.5 to 5.5 for
the same concrete improvements plus reproducible evidence and a license. The
rating remains moderate: the mathematical principle is established, the
oracle is assumed, and field relevance has not been measured with providers.

### Cyclic graph and source bridge supplement (9 October 2026)

The finite graph checker extends the supported artifact to billable cycles.
Its 17 authored fixtures include 6 accepted cases with certificates replayed
by a separately implemented checker, 8 rejected cases with finite request,
usage, and full-trace witnesses, and 3 invalid cases. The graph grid reports
1,400 accepted reference executions, 800 paired secret-store comparisons,
and 28,580 accounting checks with no observed mismatch. A 3,000-case seeded
property probe reports 11,696 ordered equal-public comparisons with no
request/usage/response/stop mismatch; it imports the producer's own
`reference_run`, so it is not an independent semantic oracle. Productive
cycles establish finite usage-prefix equality only; call-free cycles are
rejected and no finite total-cost bound is claimed for unbounded call cycles.

The graph checker and certificate replayer also pass an offline isolated-wheel
installation, cyclic check, replay, and negative smoke cases in
[`packaging_validation.json`](../output/release/packaging_validation.json).
The bounded source bridge gates the exact source/compiler snapshots and has
twelve tests, including finite AST-to-graph comparisons, public text output
projection, and a source-replacement race regression. Its corpus evaluation
attempted 20 existing OrchLang files (five accepted examples and fifteen
balanced source-derived inputs, distinct from the upstream source catalog);
all passed the compiler gate, 17 exported,
and three retry examples were excluded by the graph subset. Across those
exports, 720 direct-source/graph run pairs, 360 secret-trace comparisons, and
1,584 call events showed no difference. This remains finite evidence for an
authored adapter and deterministic mock, not a translation proof or an
independent application study. These extensions improve software usability
and workflow-shape coverage; they do not change the 5.5 overall novelty or
applied-method scores because the theory remains an application of standard
relational products and external validity remains limited.
Per-file hashes, artifacts, probes, and exclusions are recorded in
[`source_graphs/evaluation.json`](../bench/results/source_graphs/evaluation.json)
and [`SOURCE_GRAPH_BRIDGE.md`](SOURCE_GRAPH_BRIDGE.md).

### LangGraph Python-source frontend supplement (9 October 2026)

A separate, deliberately small Python AST frontend now extracts a whitelisted
subset of authored LangGraph `StateGraph` programs into the request-graph
format. The exporter does not execute source: it binds the exact source and
contract bytes, the AST mapping, generated graph, compiler report, and
certificate-replay attestation in provenance files. The offline source study
then executes only its validated authored fixtures under Python 3.14.6 and
LangGraph 1.2.14, and compares full ordered traces from actual LangGraph
invocations with the replay-gated graph backend under the same declared
deterministic mock oracle.

The frontend suite passes 20 tests. Its finite study reports 36 source runs,
30/30 source-to-graph run pairs with equal traces, 66 call events, and 6/6
source/value probes equal for graphs that the relational checker rejected.
Across 15 paired secret assignments, 12 traces matched and three deliberately
different-template pairs differed as expected. The machine-readable result
records the exact exporter, backend, checker, replayer, and study hashes in
[`langgraph_source_study.json`](../bench/results/langgraph_source_study.json).
These results support the documented AST subset and improve cross-runtime
usability evidence. They do not prove translation for arbitrary Python or
LangGraph programs, and the source and graph paths share the same offline
oracle; the study is not an independent provider experiment. This frontend
study is separate from the 17/20 export result for existing OrchLang source
files above and from the 15 source-pattern projections in the benchmark.
Nominal price fields normalize to finite binary64 values for model identity;
the probabilistic usage observer records integer call/token usage and does not
compute currency.

### Exact probabilistic usage-channel supplement (9 October 2026)

The finite-channel analyzer adds a model-dependent quantitative view beside
the universal shared-oracle relation. It analyzes a declared finite,
request/history-indexed rational kernel and measures the selected integer-usage
observer. The study has 11 authored graph/kernel fixtures and 130
horizon/observer analyses. A separately implemented no-state-merging DFS
replayer verified all 130 reports with explicit limits of 1,000,000 paths,
10,000,000 control steps, and 1 GiB serialized work. Across 260
DP-versus-DFS histogram/mass comparisons there were no mismatches; 11 cap
probes returned `UNKNOWN` without partial histograms. The combined
producer/reference/replay suites pass 46 tests. Results include different
requests with identical usage laws under the supplied kernel, equal expected
usage hiding distributional differences, and ordered traces distinguishing a
permutation hidden by aggregate usage.

This does not estimate or validate a provider distribution. Input usage uses
additive UTF-8 byte-ceiling accounting in an abstract unit, not provider prompt
serialization or money. It models successful outcomes only, finite
conditional kernels, and finite-horizon TV, vulnerability, likelihood-ratio,
and mutual-information expressions. The independent verifier recomputes exact
rows and metrics but does not verify producer execution counters or approximate
logarithms. Details and hashes are in
[`PROBABILISTIC_CHANNELS_REVIEW.md`](PROBABILISTIC_CHANNELS_REVIEW.md).

An all-horizon checker separately closes the finite semantic state space for
the same class of declared kernels and computes exact-rational strong
probabilistic bisimulation over visible `(resolved contract, input usage,
output usage)` labels and terminal stop states. Its state retains concrete
registers and the bounded complete-event history; contract and history-event
ordinals saturate at 33 because kernel literals stop at 32. Equal initial
partition blocks prove equality of ordered usage-trace laws at every finite
horizon, including stop positions. Different blocks are inconclusive; no
total-cost, termination, or infinite-run claim follows. Seventeen tests pass,
including pre-serialization state-size and UTF-8 size-preflight regressions.
This uses standard probabilistic bisimulation, specialized to this finite
request/usage state, not a new general theory. Larsen–Skou probabilistic
bisimulation and Kamaleson, Parker, and Rowe partition-refinement minimization
for finite-horizon probabilistic systems are direct prior art. The all-horizon
report has no independent certificate replayer yet. A 16 MiB per-state
canonical-key cap is checked before serialization. The cumulative serialized-
work estimate still is not a process-RSS bound.

These additions increase expressiveness and evidence for a software
specialization, but do not change the fixed overall novelty score of 5.5/10 or
the applied-method score of 5.5/10. General probabilistic QIF metrics, finite
channel analysis, and strong probabilistic bisimulation are established
methods. The remaining contribution is the integrated request/history-aware
usage semantics and executable analysis, not new TV, MI, coupling, or
bisimulation theory.

### SCP OSP guide verification (9 October 2026)

The current OSP guide was opened in the in-app browser after ordinary web
fetch returned 403. It specifies an unaltered publisher template, a
single-column paper, suggested text length of 3–6 pages with listed exclusions,
a completed metadata table, public code link, abstract/keyword limits, and a
separate editable highlights file. The publisher's Word and LaTeX templates
were retrieved for paper preparation. The detailed checklist is in
[`SCP_AUTHOR_REQUIREMENTS.md`](SCP_AUTHOR_REQUIREMENTS.md); do not repeat the
earlier 403 as an unresolved requirements gap.

## Importance versus deployment relevance

**Importance:** moderate for workflows in which secret-dependent control or
content can affect model choice, request size, call count/order, or retries and
an unauthorized observer can see per-run/per-contract usage. This is an
established resource-side-channel problem. Token-length and timing attacks
support the relevance of related observables, but do not establish that a
provider invoice exposes an individual workflow trace.

**Deployment relevance today:** limited. The artifact has an offline mock, no
provider adapter, no real serialized-request accounting, and no usage-receipt
study. The theorem's input bound assumes per-call full abstract request
accounting `I <= ceil(UTF8_bytes(template)/d) + sum(argument bounds)` in a
common target-tokenizer unit; provider-added overhead and tokenizer boundary
effects are outside that premise. Thus this work is currently a static-method
prototype, not evidence that an actual invoice is protected. Billing, latency,
network packet lengths, and hardware cache behavior are distinct observations.

## Main reviewer objections and responses

1. **“This is existing resource-aware IFC in new syntax.”** Agree with the
   lineage; identify the delta as relational matching of abstract invocation
   effects under a declared external oracle, not a new NI principle.
2. **“The oracle makes the theorem vacuous.”** State Ω(c,k,Q), the shared
   coupling and retry schedule, and prove the signature matches each abstract
   key. The current guarantee is conditional and does not claim all
   equal-ordinal real provider calls have equal outcomes. Discuss expected and
   distributional properties as different questions.
3. **“The abstract request is incomplete.”** Agree: it is template bytes plus
   ordered argument values, not the provider's full wire request. Keep the
   theorem at that abstraction and spell out its limitations. Resolved model
   contracts, rather than alias spelling, are compared.
4. **“Stochastic cost can be analyzed numerically.”** Concede it. Numeric worst
   cases, expected values, and cost contracts apply in other settings. Explain
   that this work targets a particular pathwise relational property under an
   explicit shared coupling.
5. **“No one has statically checked agent workflows.”** Do not make that claim.
   Compare AgentFlow and Agentproof; state their policy/graph properties differ
   from the usage observation here.
6. **“The examples prove little about practice.”** Say they are partial public
   source projections with explicit bounds/exclusions. Keep authored mutations
   separate and never frame them as upstream vulnerabilities or real incidents.
7. **“A bill may not reveal a per-call trace.”** Define the observer. The current
   work proves equality of an abstract usage trace, not a claim about what an
   ordinary invoice exposes.

## Repository and artifact concerns

The checkout now contains a root MIT `LICENSE` and `CITATION.cff`; the parent
task reports that repository-owner/author authority was checked. The final
author review and immutable public release are still pending, so the artifact
is not yet available as a public release. Keep upstream attribution and
licenses attached to the source catalog; the OrchLang license does not relicense
third-party source examples. The 15 evaluated projections are authored bounded
abstractions and the manifest lists their source-specific changes and
exclusions.

## Remaining research and release work

1. Convert the written induction sketches into a complete, independently
   reviewed formal argument; the current proof is not mechanized and the cost
   auditor does not check the relational theorem.
2. Keep the request/cost abstraction explicit in every paper, certificate, and
   interface. A provider adapter would need to identify the full request,
   tokenizer, usage receipt, retries, and tariff before making any deployment
   claim.
3. Treat the 17-row catalog and the executed 15-pattern/three-framework
   corpus separately. The current 15 variants are partial projections; the
   unbalanced fixture adds one request in one arm. Preserve the adaptation and
   exclusion log and do not describe the corpus as independent applications.
4. The current baseline comparison and cost-report audit are useful but do not
   replace an independent full-source relational proof checker,
   independently selected corpus, or provider-backed evaluation. The graph
   certificate replayer checks JSON-graph certificate closure; it is not a
   full OrchLang relational proof checker.
5. Complete final author review and make an immutable public release before
   claiming public reuse/reproducibility. The MIT license and citation metadata
   are now present; publication/release actions remain pending.

## Publisher and article-type assessment

See [`JOURNAL_SHORTLIST.md`](JOURNAL_SHORTLIST.md) for the dated fit, article
type, policy, and fee review. SCP OSP remains the strongest software
publication fit; JSS NITP is a plausible research-paper route if the paper
stays narrow and accurately presents synthetic/model-based evidence. SCP OSP
still needs a public immutable code version, final human author review, the
required template-based short manuscript/metadata/highlights, and the pending
final demo and combined reproduction review. STTT would require a stronger
proof and evaluation package. This is a readiness assessment, not a prediction
of acceptance; no editor contact or submission has been made.
