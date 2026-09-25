# Real-workflow corpus: protocol

This protocol, the candidate list, the split and every label in
`manifest.json` were fixed and committed **before any workflow was ported**.
The commit that adds this file contains no `.orch` port. Anything changed
afterwards is recorded in the "Deviations" section at the end, with the reason.

The corpus answers three questions:

1. **Expressiveness.** How much of a real workflow population can OrchLang
   express, and what can it not express? (The exclusion log is a result.)
2. **Agreement.** Do the analysis's verdicts on faithful ports match labels
   derived from the sources, before the analysis was run on them?
3. **Bounds on real prompts.** Does the certificate exist for real prompt
   templates and model caps, is the guaranteed input bound defined, and does
   the runtime ever exceed it?

## 1. Population

Three sources, each pinned to one commit. Every candidate below is in the
corpus; none was added or removed after porting started.

| Source | Commit | Candidates |
|---|---|---|
| `anthropics/anthropic-cookbook`, `patterns/agents/*.ipynb` | `813fbeec03cdedfda7808529438d1c7af71f26eb` | every workflow the notebooks define: `basic_workflows` defines three (chain, parallel, route), the other four notebooks one each — 7 |
| `langchain-ai/langgraph`, `docs/docs/tutorials/**/*.ipynb` | `23961cff61a42b52525f3b20b4094d8d2fba1744` | every tutorial notebook — 25. This is the revision that the archived `examples/` directory of the current default branch (`7daa3ab49d678a5da75edb08baa87db4a2be52c3`) links to. |
| `ethz-spylab/agentdojo`, `default_suites/v1` | `089ed468cf3ed0322acc66b0211f26d9d90dbf60` | the first five user tasks, by class number, of each suite: banking, slack, travel 0–4; workspace 0, 1, 2, 3, 5 (v1 defines no `UserTask4` in workspace) — 20 |

52 candidates. LangChain Hub prompts that a tutorial pulls by name are fetched
by commit hash through the Hub API; the hashes are in `manifest.json`.

## 2. Split

A candidate is **development** if the first hex digit of
`sha256(candidate id)` is 0–4, and **held-out** otherwise (about 31% / 69%).

Development ports were written first, and any change to the compiler they
prompted was made then. The compiler was then **frozen** at a commit recorded
in `manifest.json` (`frozen_compiler`). Held-out ports were written after the
freeze and checked once against the frozen compiler. A held-out result that
exposes a compiler defect is reported as found, whatever is done about it
later.

## 3. Labels

Labels are properties of the *source*, derived by the rules below, not
predictions of what OrchLang will say.

**Untrusted (U).** Content authored outside the workflow's trust boundary:
retrieved documents, web pages and search results, files, messages and
reviews written by third parties, customer-written tickets, and the output of
executing model-generated code. For AgentDojo the rule is mechanical and
AgentDojo's own: a tool response is untrusted exactly when it contains one of
the suite's injection vectors, as determined by running the task's ground truth
with canary injections (`agentdojo_canaries.py`, output in
`agentdojo_canaries.json`). Model responses are not labelled; their labels
follow from their inputs.

**Secret (S).** Data a source itself identifies as confidential. The two
tutorial collections identify none. AgentDojo's threat model is prompt
injection, i.e. integrity; its tasks are labelled by U alone. So **no
candidate has a secret**, and the relational (billing side-channel) analysis
has nothing to check on this corpus. This is recorded as a result, not
worked around.

**Effects.** Tool calls that change the world (send money, send a message,
reserve, create an event, execute code), and read requests whose arguments are
computed at run time: those arguments leave the workflow (a URL, a search
query), so the request is a sink like any other. A read whose arguments are
constants of the source is just an input.

**Expected diagnostics** on the unannotated port, by rule:

| Code | Expected exactly when, in the source, |
|---|---|
| `E233` | an effect's argument (including a run-time read request's) is computed from untrusted content, directly or through a model call |
| `E235` | an effect (including a run-time read request) runs or not depending on a decision computed from untrusted content |
| `E230`, `E231`, `E232`, `E234`, `E236` | secret content reaches a prompt, the output, a tool, guards an effect, or guards a branch whose arms send different requests (none, since no candidate has a secret) |
| `W237` | a branch whose guard is computed from untrusted content has arms whose worst-case token costs differ |

No other `E` or `W` code is expected. A port must be accepted if and only if
no `E` code is expected.

**Bounded in source.** Whether every loop in the source has a bound (a count,
a message-length cut-off, a framework recursion limit).

**Guaranteed input expected.** Whether every model the source calls has a
tokenizer with a verified contract in `src/tokenizer_contracts.cpp`. Anthropic
publishes no tokenizer for its current models, so any Claude call makes the
guaranteed input bound undefined.

## 4. Porting rules

* **P1 Calls.** One source LLM call is one `call`. The template is the source's
  prompt text verbatim. A system and a user message are concatenated in order,
  separated by a blank line; conversation history is concatenated likewise.
  `verify_sources.py` checks that every literal fragment of every template of
  at least 20 characters occurs in the pinned source.
* **P2 Models.** `mock("<provider>/<model>")` with the model the source names.
  `max_tokens` is the source's setting, else the framework's default if it
  sets one, else the provider's maximum output for that model. Each value is
  recorded in `manifest.json` with where it comes from.
* **P3 Tokenizers.** OpenAI models get the tiktoken encoding the provider uses
  (`o200k_base` for the GPT-4o family, `cl100k_base` for GPT-3.5 and GPT-4);
  Mixtral gets the Mistral contract if its tokenizer is byte-identical to the
  measured `Mistral-7B-v0.1` one (checked, not assumed); Claude gets none.
* **P4 Envelope.** Chat formatting is covered by `overhead`: OpenAI documents
  3 tokens per message plus 3 for the reply, so `overhead` is
  3 × (most messages in any request to that model) + 3. For calls with a
  function or structured-output schema, the schema's JSON is added to the
  template as text. That the provider renders a schema in no more tokens than
  its JSON serialisation is an **assumption**, stated as such.
* **P5 Reads.** A read with constant arguments is an `input`. A read with
  run-time arguments is an `emit` of the request followed by an `input` for its
  result, modelled as arbitrary content within its byte bound; the dependency
  of the result on the arguments is not modelled, which both analyses can
  afford because they treat an input as arbitrary.
* **P6 Inputs.** User inputs are `input`; untrusted content is
  `input … untrusted`. Every input has a byte bound: from the source if it
  bounds it (a chunk size in tokens becomes `max_tokens N tokenizer T`),
  otherwise `max_bytes 8192`, an assumption a deployment would have to enforce.
  Constant data in the source (a list of stakeholders, a task prompt) is
  literal text.
* **P7 Control.** Iteration over a list of fixed length is unrolled. A branch
  on a model's yes/no decision is a `boolean` call and an `if`. A bounded
  loop is unrolled to its bound; a loop with no bound in the source gets a
  bound chosen by the port, recorded as `imposed_bound`.
* **P8 Adaptations** the language forces, each recorded per port with whether
  the port's certified bound is still a bound for the source:
  * **A1** Response post-processing (XML or JSON extraction, parsing) is not
    expressible: the whole response is passed on. Cost-sound: an extract is
    no longer than the response.
  * **A2** A multi-way branch on a model's categorical answer becomes a cascade
    of yes/no decisions. Cost-sound only if every decision call is at least as
    expensive as the source's single selector call; recorded per port.
  * **A3** An early exit decided by a test on a response (`== "FINISHED"`,
    validation passes, evaluation is `PASS`) is dropped: the port always runs
    to the bound. Cost-sound (an upper bound on every path).
  * **A4** Model-driven filtering of a list (keep the relevant documents) is
    ported without the filter: the full list is passed. Cost-sound.
  * **A5** A call whose one structured response supplies both a decision and
    text is ported as a `boolean` call and a `text` call. Not cost-sound in
    general (adds a call); recorded.
  * **A6** *(added during development, see §7)* A workflow has exactly one
    output, bound outside every branch. A source that returns several values,
    or a value computed inside a branch, outputs a stand-in (named in the
    port's header). Outputs carry no cost and no effect, so bounds and the
    effect checks are unchanged.
* **P9 Plans, not agents.** An AgentDojo task is ported as its ground-truth
  plan executed as a fixed workflow: reads follow P5; one model call computes
  each run-time argument (of an effect or a read) from exactly the data the
  ground truth uses, placed where the plan needs it; one model call writes the
  final answer. Every such call's template is AgentDojo's default system
  message, the task's prompt, and the data, in that order, with no other text.
  The model is `gpt-4o-2024-05-13`, whose recorded runs the cross-check in §6
  uses. This is the plan-then-execute pattern, **not** AgentDojo's
  tool-calling agent, and its cost figures are not an agent's.
* **P10 No annotations.** `<id>.orch` contains no `endorse` or `declassify`.
  If it is rejected, `<id>.annotated.orch` adds the fewest reclassifications
  that let the source's intended behaviour through, each with a `because`;
  their number is reported.

## 5. Exclusion categories

Fixed in advance. A candidate is excluded when faithful porting would need:

* **X1** Model-chosen control: the model selects which tool, agent or node runs
  next, or how many (ReAct loops, supervisors, planners, dynamic fan-out).
* **X2** Reads whose *number*, or whose tool, the model chooses at run time
  (a list of search queries of model-chosen length). OrchLang inputs are
  declared up front, so a fixed sequence of reads can be ported (P5) and a
  model-sized one cannot.
* **X3** A cyclic state graph with more than one back edge.
* **X4** Iteration whose count depends on data (the size of a dataset).
* **X5** Interactive human input during the run, concurrency, or timing.
* **X6** Multimodal input.
* **X7** A duplicate: a variant of another candidate that differs only in model
  backend or evaluation harness.

## 6. Evaluation (E11 of `bench/evaluate.py`)

For every port:

1. `orchc check` on `<id>.orch`: the set of `E`/`W` codes must equal the
   expected set exactly, and the verdict must be accept iff no `E` is
   expected. Any mismatch fails the harness.
2. If `<id>.annotated.orch` exists it must be accepted.
3. `orchc certify` on the accepted file; record the output bound, the estimated
   and guaranteed input bounds, and whether the guaranteed bound is defined
   (it must be defined exactly when expected).
4. Run 200 seeds under the content-dependent provider with the
   content-sensitive tokenizer; every run must stay within the output bound and,
   where defined, the guaranteed input bound. How often the estimate is
   exceeded is reported.

For every ported AgentDojo task, a cross-check against AgentDojo's own recorded
attack runs (`runs/gpt-4o-2024-05-13/*/important_instructions/`): each run
where the injection succeeded (`security: true`) is classified as
**outside-plan** if it made a tool call the task's plan does not contain, or
more calls to a planned effect than the plan makes, and **within-plan**
otherwise. A within-plan success on a task the checker accepts fails the
harness: it would be an injection the port's structure does not stop and the
checker did not flag.

## 7. Deviations

Each deviation below was made during the development split, before the
compiler was frozen, unless marked otherwise.

* **D1 Literal braces.** A prompt template could not contain `{` or `}` other
  than as a placeholder (E222), so a real prompt carrying JSON or code could
  not be written verbatim. Found porting `lg-code-assistant`, whose tool schema
  is JSON. `{{` and `}}` now denote a literal brace, as in Python format strings
  and LangChain templates, in both the analysis and the runtime, with a
  regression test (`testDoubledBracesAreLiteral`) checking that the two agree
  on the bytes sent. This is lexical and does not change what the language can
  compute.
* **D2 Where warnings are compared.** `W237` comes from the cost analysis, which
  runs only once the flow check passes, so it can never appear on a rejected
  port. Warnings are therefore compared on the accepted variant (the port, or
  its annotated variant). In an annotated variant a guard the annotation
  endorses is trusted, so the `W237` rule is applied to that variant; the
  result is recorded per port as `expected_warnings_accepted_variant` where it
  differs from the source's label. Found on `lg-code-assistant`, whose
  untrusted guards all guard effects and so must all be endorsed.
* **D3 One output.** Adaptation A6 above.
* **D4 What counts as source text.** `verify_sources.py` checks prompt templates
  and literal call arguments. Model strings and endorsement justifications are
  the port's own text and are not checked.

The following were made **after the freeze**, with the held-out results in
view. None touches the compiler; each is a change to how the harness scores,
and each is reported here with what prompted it.

* **D5 Extra diagnostics are imprecision, not failure.** §6 said any mismatch
  between a port's diagnostics and its label fails the harness. On the
  held-out `ad-travel-1` and `lg-crag` the checker reports `E233` beyond the
  label: a value computed inside a branch guarded by untrusted data inherits
  the guard's integrity label, although the value itself is computed only from
  trusted data (the hotel's address; the user's question), and the label rule
  asks only whether the value is computed from untrusted content. The labelled
  `E235` is reported in both. A missed label would be a flow the checker failed
  to catch and still fails the harness; a diagnostic beyond the label is now
  listed and counted in E11 and in the paper, but does not fail it. This is the
  integrity counterpart of the data-versus-program-counter distinction that
  OP-1 drew for secrets, which the integrity half of the type system does not
  draw.
* **D6 Text the source computes.** `ac-route` sends
  `['billing', 'technical', 'account', 'product']`, which the source computes
  from its dictionary's keys, and `ac-evaluator-optimizer` sends
  `"Previous attempts:"` joined by newlines. `verify_sources.py` now also
  accepts a stretch that equals a whole string constant of the source (at least
  three characters), so text the source builds from its own constants is
  covered; invented prose is still rejected (checked by editing a port).
* **D7 Derived warning labels.** For the held-out `ad-travel-1` and `lg-crag`,
  `expected_warnings_accepted_variant` is `[]`, by D2: their annotated
  variants endorse every untrusted guard, since each guards an effect.

