# Next contribution decision: validate source-to-observer correspondence

**Prepared:** 9 October 2026  
**Purpose:** Choose one substantial next research/software contribution. This is
a proposal, not a claim about work already implemented or an estimate of SCP
acceptance.

## Decision

Build an independently replayable **source-to-observer translation check** for
a small, explicit subset of real LLM workflow source. Then evaluate it on the
pinned incident-triage application and one independently selected public
workflow. The check must establish that every admitted source execution has
the same ordered request, usage, and selected control trace as its exported
OrchGraph execution under the same declared outcome oracle.

This directly addresses the central gap in the current result. The incident
adapter reconstructs a useful source dependency protocol, but its graph
certificate covers only the classifier request. The separate Python frontend
exports a deliberately small subset and has finite differential tests; its
authored examples do not establish that an arbitrary framework source program
was translated faithfully. A translation check would connect the existing
graph-level relational and trace analyses to admitted source paths, with an
independent checker able to reject an omitted request, route, retry, or state
dependency.

The prior-art contribution would be an application and integration of
translation validation to an LLM-workflow usage observer, not a new
translation-validation or noninterference algorithm. The plan cannot promise
an 8/10 score. A later review should increase its estimate only if the
implementation demonstrates source coverage, a checked correspondence, and
analytical value beyond the source project's own tests and ordinary review.

## Alternatives considered

| Direction | Potential value | Why it is not the best next contribution |
|---|---|---|
| **Source-to-observer translation validation** | Makes graph-level properties apply to actual supported workflow source and can reveal request or billing behaviors that are hard to track across helper functions and branches. Can be evaluated across projects. | Highest implementation and semantics risk. Python is too dynamic for a broad promise, so the supported subset and helper contracts must be explicit and fail closed. This is the recommended direction. |
| **Concurrency/attribution checker** | Builds on the reproduced shared `CostTracker`/`current_node` contamination and the isolated-session manager. A checker for closure-scoped mutable state and invocation attribution could prevent a concrete operational error. | The current evidence is one source version and one race pattern. Race detection and isolation are established topics; without a multi-project study and clear detection advantage, this is mainly a useful, narrow engineering feature. Keep the existing finding as source-grounded evidence, but do not make it the main novelty claim. |
| **Tokenizer and usage-contract adapter** | Could replace the current declared byte-based estimate for selected local model/tokenizer/serializer versions and improve cross-model chain bounds. | Useful for cost estimates, but tokenization and request serialization are established engineering concerns. It does not solve whether a workflow translation preserves confidential data dependencies. Provider envelopes and reported usage remain difficult to validate without a complete provider contract. |
| **More probabilistic leakage metrics or kernels** | Could report quantitative leakage beyond equality for finite supplied models. | Probabilistic multi-call LLM flow models and quantitative information-flow methods already exist. Another TV, MI, or horizon analysis would add little unless tied to a new, validated source semantics or a result existing analyses cannot express. It would also remain conditional on a supplied kernel. |

The first direction has the strongest connection to the current project’s
specific contribution and the remaining limitation identified in
[`FINAL_PUBLICATION_REVIEW.md`](../docs/FINAL_PUBLICATION_REVIEW.md). It also
gives the other two directions a more credible substrate later: source calls
and concurrent invocations must be extracted faithfully before their costs
or attribution can be analyzed.

## Proposed architecture

### 1. Freeze a source subset and the observation first

Before adapting the second application, publish a short supported-language
contract. Admit only constructs whose behavior can be modeled exactly, such
as:

* statically declared workflow nodes and edges, including conditional routes
  and bounded retry/error transitions when they are part of the source;
* typed state reads and writes, lexical local values, and a declared set of
  pure helper functions whose source or semantics are checked;
* request construction with resolved model contract, exact template bytes,
  ordered argument values, and the source’s response/result update;
* source-observed input/output usage accounting, status, retry, and selected
  route/interrupt events.

The observer must be stated before checking a workflow. A suitable initial
observer is the ordered sequence of resolved model contract, complete modeled
request descriptor, source-estimated input/output usage, and selected
route/stop/interrupt events. If request contents are outside a particular
security claim, define a second projection that omits them; do not conflate
request confidentiality with usage-trace confidentiality. Do not equate a
local estimate with provider-reported tokens or invoice amounts.

Unknown imports, dynamic node registration, reflection, unmodeled state
reducers, arbitrary side effects, unbounded retry, hidden model wrappers, or
accounting code the adapter cannot explain must cause a rejection. For each
whitelisted helper, bind the exact source bytes or a reviewed semantic
contract into the report. A helper contract is an assumption unless its
implementation is itself in the translated subset.

### 2. Export a source-anchored transition model

Extend the existing AST front end to emit a transition system plus a mapping
from each state, call, guard, retry, and terminal action to source locations
and lexical bindings. Preserve result assignment and scope semantics. Each
call node should carry the complete normalized request identity and exact
ordered request atoms used by the declared oracle. Model aliases must resolve
to stable provider/model/cap/price contracts before the graph is checked.

The translation obligation should be a local simulation relation between
source configurations and graph configurations. For every admitted source
step, the mapped graph must match the same visible event or take an explicitly
silent setup step; for every graph step, the source model must permit the
corresponding step. This two-way condition rules out both omitted source
behavior and spurious graph behavior. At a model call, the correspondence
must preserve the complete modeled request, call ordinal and retry context,
and the response-to-state update under the same oracle. At a branch, it must
preserve the guard value and both possible successors. The checker can be
syntax-directed for the restricted language; it need not model all of
Python.

An independent replayer should parse the exact pinned source and check the
mapping and correspondence obligations itself. It must reject extra graph
nodes, missing source call sites, duplicate or unreachable source mappings,
incorrect lexical bindings, altered templates/argument order, and edges that
do not correspond to a source transition. The graph relational checker then
proves its existing property on the graph that passed this source check. Keep
the source-to-graph claim separate from the graph checker’s theorem.

This division is important: a matching set of finite executions can expose
mistakes, but it is not itself a translation proof. Runtime differential
tests are useful validation of the admitted semantics and extractor; the
independent source/graph relation is the basis for the covered-subset claim.

### 3. Evaluate transfer and analytical value

Select the second public workflow by criteria fixed before analysis: a
maintained source repository, a clear license, real model calls, nontrivial
control or result flow, and a confidentiality or cost boundary stated in its
own code/docs. Record its immutable revision and every translated file.
Do not hand-edit its source or choose it because a desired counterexample is
already known.

Use the existing incident-triage source as one case and the independent
workflow as the transfer case. For both, report:

1. Source call sites, paths, branches, retries, helpers, state fields, and
   observer events found; how many map into the supported subset; and every
   exclusion with a source location and reason.
2. Whether independent replay accepts the generated mapping and whether
   mutations to a call, argument order, result binding, retry edge, model
   contract, or route are rejected.
3. Source/runtime differential traces under deterministic offline mocks,
   including full modeled requests, source-estimated usage rows, response
   updates, and route/interrupt outcomes. Keep the source and graph
   interpreters separate; bind both to source, exporter, oracle, and runtime
   hashes.
4. Paired public/secret experiments that follow the stated source boundary,
   plus at least one meaningful public change. Explain whether request,
   ordered-usage, route, and stop projections agree, and attach replayable
   witnesses for differences.
5. Incremental value: identify a concrete source-derived fact or
   counterexample that the project’s existing tests and direct source review
   do not establish as clearly. Have a second reviewer reproduce the mapping
   and finding from the pinned source. If no such result appears, report that
   honestly; do not infer novelty from case count or test count.

The measurement is not “how many lines compiled.” A useful result is a
checked source path with an explicit trust boundary, plus a finding or
property whose source-level dependencies and observable consequences are
reproducible. Report rejected coverage alongside admitted coverage so a
small easy subset cannot look like broad support.

## Prior-art boundary

This design should not be described as the first workflow extractor,
framework-independent agent graph, source security analyzer, or translation
validator:

* [AgentProof (2026 preprint)](https://arxiv.org/abs/2603.20356) extracts
  workflow graphs from LangGraph, CrewAI, AutoGen, and Google ADK and checks
  structural and temporal policies. Its existence means framework graph
  extraction and policy checking alone are not the contribution.
* The peer-reviewed [Open Agent Specification](https://doi.org/10.1145/3786335.3813130)
  provides a framework-agnostic representation and adapters for workflow
  comparison. Interoperability alone is established adjacent work.
* [Agent Audit (2026 preprint)](https://arxiv.org/abs/2603.22853) analyzes
  Python agent code and deployment artifacts for dataflow, credentials,
  configuration, and privilege risks. A generic “static analyzer for agent
  source” claim would be too broad.
* [Alive2 (PLDI 2021)](https://doi.org/10.1145/3453483.3454030) is a mature
  example of bounded translation validation. Use that established framing;
  the possible contribution here is the source-level correspondence for a
  request and usage observer, not a new validation algorithm.
* [PPDL (ICML 2026)](https://proceedings.mlr.press/v306/mandel26a.html) models
  probabilistic multi-call LLM/tool flows. A general probabilistic workflow
  model or resource budget is not a sufficient novelty claim.

The narrow residual question is whether an independently replayable,
source-to-observer correspondence for admitted LLM workflow code can make
request-sensitive usage analyses reliable and useful on real source without
pretending to verify arbitrary Python or provider behavior.

## Stop/go criteria and claims to withhold

Proceed only if the current source-specific adapter can be converted into a
reviewable subset with an independently checked correspondence, and a second
independently selected workflow has enough actual source behavior in that
subset to make the comparison meaningful. If the second workflow requires
hand-coded per-case conclusions, silently ignored Python, or a substantial
trusted helper layer, stop and publish the existing narrower result instead
of broadening the claim.

Do not promise an 8/10 score in advance. Reassess only after the new bridge,
independent replayer, two source studies, differential evidence, and a
source-grounded incremental result all exist in one frozen reproduction. If
the study yields faithful translation but no additional analytical finding,
the right conclusion may still be a useful software contribution with
moderate originality.
