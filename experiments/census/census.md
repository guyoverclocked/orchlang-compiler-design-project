# Census of example LLM workflows: does control flow depend on content?

Companion to `census.csv` (72 rows). Port specs are in `ports/`. All facts below come from the local clones:

| Source | Clone path | Commit |
|---|---|---|
| LangGraph | `/home/user/langchain-ai/langgraph` | `eb066bd31a2bf01fc0cd58256df4800a3695c233` (langgraph lib 1.2.16) |
| LangChain/LangGraph docs | `/home/user/langchain-ai/docs` | `5d83d5e690af84ed654a8d4320bf9969af28e39f` |
| Prompt Flow | `/home/user/microsoft/promptflow` | `33a68c9d3cf349d7fdfad1f41969af27543c0406` |

Paths in the CSV are prefixed `langgraph/`, `docs/`, `promptflow/` relative to those roots. Notebook line numbers are raw `.ipynb` JSON line numbers, so `grep -n` and `sed -n` work on them directly.

## 1. Research question and observer model

Observer model: an observer sees per-call usage metadata and nothing else:
- number of LLM calls
- model id
- input/output token counts
- latency/timing
- loop iterations and tool calls

Prompt and response text stay hidden (TLS, or LangSmith-style hide-inputs/outputs).

For each example workflow we ask whether that metadata is a function of content. That happens when control flow branches, loops or fans out on LLM output, on user input, or on tool output derived from them.

## 2. Method

1. **Candidate discovery** (2026-10-23).
   - docs and langgraph: grep for `StateGraph`, `MessageGraph`, `add_conditional_edges`/`addConditionalEdges`, `Command(goto=...)`/`new Command({goto})`, `Send(`/`new Send(`, `@entrypoint`/`entrypoint(`, in `.md`, `.mdx`, `.ipynb` (code cells only), `.py`, `.ts`, `.js` files.
   - promptflow: every `flow.dag.yaml`/`*.flex.yaml` under `examples/`, plus flex flows without a YAML.
   - A second, broader grep (`Command(`, `Send(`) was run to catch Command-based routing.
2. **Feature extraction.**
   - Small scripts list, per file and per fenced code block / notebook cell, the graph constructs and any LLM call indicators (`init_chat_model`, `Chat*` classes, `with_structured_output`, `bind_tools`, `create_agent`, `*.invoke` on model objects).
   - For Prompt Flow they parse every DAG: node type (`llm`, `custom_llm`, `prompt`, `python`), `activate.when/is`, `aggregation`, `use_variants`.
   - Python nodes were then read by hand for LLM clients (`openai`, `promptflow.tools.aoai/openai`, LangChain chat models, `Prompty`) and for loops.
3. **Manual review.** Every candidate with an LLM call site was read. Each conditional edge, `Command(goto)`, `Send`, `activate`, `while`/`for` loop and early return was traced to its predicate, and the predicate's inputs were classified. Evidence (file:line) is recorded in `evidence_lines`.
4. **Activation semantics.** These were checked against the Prompt Flow executor: `promptflow/src/promptflow-core/promptflow/executor/_dag_manager.py:106-144`. A node is bypassed if its activate condition fails, if its `activate.when` node was bypassed, or if *all* of its node-reference dependencies are bypassed.
5. **Datasets.** Port datasets were verified with `GET https://huggingface.co/api/datasets/<id>` (HTTP 200). Schemas, sizes and label distributions came from `datasets-server.huggingface.co` (`/info`, `/statistics`, `/rows`).

The tools are in `../tools/`:
- `scan.py`, `mdxblocks.py`, `nbdump.py` (discovery)
- `build_census.py` (writes the CSV and prints the statistics below)
- `include.py` (copies verbatim source spans into the port specs)

## 3. Unit of analysis, inclusion and exclusion

**Unit.** A *distinct example workflow*: a concrete, runnable or nearly runnable graph/flow with at least one concrete LLM call site whose purpose is an application. Duplicates are merged into one row with all paths listed:
- Python and JS versions of the same example
- Graph API and Functional API versions of the same example
- `docs/src/snippets/code-samples/*.mdx`, which are generated copies of `docs/src/code-samples/*`
- model-provider variants with identical topology (e.g. `langgraph_self_rag.ipynb`, `_local`, `_pinecone_movies`)
- copied flows (`web-classification`, `flow-with-additional-includes`, `flow-with-symlinks`)

Variants are separate rows when the topology differs: `lg-crag` vs `lg-crag-local`, `lg-adaptive-rag` vs `lg-adaptive-rag-cohere`.

**Tiers** (first token of `notes`):
- **Tier A**: application/tutorial workflows. This includes the prebuilt-agent tutorials listed in `docs/src/oss/learn.mdx` and the multi-agent tutorials, even when they use `create_agent`/`create_deep_agent` instead of an explicit `StateGraph`.
- **Tier A(eval)**: Prompt Flow evaluation flows (LLM-as-judge).
- **Tier B**: API-demonstration graphs (memory, streaming, tracing, deployment, HITL mechanics) that contain an LLM call. They are deduplicated into 8 structural equivalence classes; each class is one row listing all member blocks.

**Excluded** (not rows):

| Reason | langgraph | docs | promptflow |
|---|---|---|---|
| Moved-stub notebooks (about 1 KB, only a "This file has been moved" link to an older commit; the content is not at this commit) | 25 of 35 `examples/**/*.ipynb` | – | – |
| Graph/flow with **no LLM call site** (API-mechanics toys, templates, benchmarks) | 5 `libs/langgraph/bench/*.py`; 5 CLI templates (`libs/cli/js-examples/src/agent/graph.ts`, `js-monorepo-example/.../graph.ts`, `python-monorepo-example/.../graph.py`, `uv-examples/{simple,monorepo}/.../graph.py`) | 59 non-snippet files (32 `code-samples/*` and 27 pages incl. `.mintlify/skills/langgraph/SKILL.md`, e.g. `use-time-travel.mdx`, `pregel.mdx`, `fault-tolerance.mdx`, `choosing-apis.mdx`, `errors/*.mdx`, HITL code samples) | 13 flows: `eval-basic`, `eval-accuracy-maths-to-code`, `eval-chat-math`, `eval-classification-accuracy`, `eval-entity-match-rate`, `azure-ai-language/analyze_conversations`, `analyze_documents` (Azure AI Language REST services, no LLM node), 5 `tools/use-cases/*` showcases without LLM, `tutorials/flow-deploy/.../echo_connection_flow` |
| Sketch with undefined/placeholder LLM functions (`...`, "Assumes ... defined elsewhere", `StateGraph(...)`) | – | `oss/langchain/multi-agent/router.mdx`, `oss/langchain/middleware/overview.mdx`, `oss/langgraph/frontend/overview.md`, `oss/langchain/middleware/built-in.mdx`, `choosing-apis.mdx` | – |
| Graph present but the LLM indicator is elsewhere on the page / not a workflow (migration notes, release notes, wrappers, constant node) | – | `code-samples/langchain/mcp-elicitation.ts`, `langsmith/server-mcp.mdx`, `oss/concepts/context.mdx`, `oss/javascript/langchain/mcp-v1.mdx`, `oss/javascript/migrate/langgraph-v1.mdx`, `oss/javascript/releases/{changelog,langgraph-v1}.mdx`, `oss/python/integrations/providers/nvidia.mdx`, `oss/python/migrate/langgraph-supervisor.mdx`, `oss/langgraph/graph-api.mdx` (conceptual toys), `oss/langgraph/test.mdx` | – |
| Matched only the broad grep (`Command(resume=...)`, `Send` in prose, HITL resume) | – | 64 files | – |
| Not a flow | `libs/prebuilt/README.md` (`create_react_agent` usage snippet), `libs/*/tests/**` | other `create_agent` API snippets across `oss/langchain/*` and `oss/deepagents/*` that are not tutorials (they would all be ReAct loops, i.e. category b) | 16 `examples/prompty/**/*.prompty` (single prompts), `examples/tutorials/tracing/*` (tracing of external frameworks) |

**Disposition of the 47 docs files that have both graph constructs and LLM indicators** (non-snippet):

| Row | Files |
|---|---|
| `agentic-rag` | `code-samples/langgraph/agentic-rag-tutorial.{py,ts}` |
| `langgraph-sql-agent` | `code-samples/langgraph/langgraph-sql-agent.{py,ts}` |
| `wa-*` (5 rows) and `calculator-react-agent` | `oss/langgraph/workflows-agents.mdx` |
| `calculator-react-agent` | `oss/langgraph/quickstart.mdx` |
| `email-support-agent` | `oss/langgraph/thinking-in-langgraph.mdx` |
| `router-knowledge-base` | `oss/langchain/multi-agent/router-knowledge-base.mdx` |
| `handoffs-sales-support` | `oss/langchain/multi-agent/handoffs.mdx` |
| `custom-workflow-wnba-rag` and `B-agent-as-node` | `oss/langchain/multi-agent/custom-workflow.mdx` |
| `chinook-support-agent` | `langsmith/evaluate-complex-agent.mdx` |
| `B-react-handwritten` | `langsmith/evaluate-graph.mdx`, `langsmith/trace-with-langgraph.mdx`, `langsmith/setup-javascript.mdx`, `oss/javascript/integrations/tools/composio.mdx`, `oss/langgraph/interrupts.mdx` |
| `B-single-llm-node` | `langsmith/generative-ui-react.mdx`, `langsmith/streaming.mdx`, `oss/python/integrations/chat/anthropic.mdx`, `oss/python/integrations/providers/{cockroachdb,langfuse,truefoundry}.mdx`, parts of `add-memory.mdx`, `streaming.mdx`, `use-functional-api.mdx`, `use-graph-api.mdx` |
| `B-runtime-config-selection` | `langsmith/configuration-cloud.mdx`, `langsmith/graph-rebuild.mdx`, part of `use-graph-api.mdx` |
| `B-two-step-chain` | `langsmith/human-in-the-loop-time-travel.mdx`, `code-samples/langchain/nostream-tag.{py,ts}`, part of `use-graph-api.mdx` |
| `B-static-parallel`, `B-agent-as-node` | parts of `streaming.mdx`; `B-agent-as-node` also takes `use-subgraphs.mdx` |
| `B-summarize-on-length` | part of `add-memory.mdx` |
| `B-input-list-parallel` | part of `use-functional-api.mdx` |
| excluded (sketch / not a workflow) | the remaining 15 files: 4 sketches (`router.mdx`, `middleware/overview.mdx`, `frontend/overview.md`, `middleware/built-in.mdx`) and 11 not-a-workflow files listed in the exclusion table above (32 of the 47 map to rows) |

Tier-A tutorial pages included without explicit graph constructs: `oss/langchain/{sql-agent,quickstart,voice-agent,deep-agent-from-scratch}.mdx`, `oss/langchain/multi-agent/{subagents-personal-assistant,skills-sql-assistant,handoffs-customer-support}.mdx`, `oss/deepagents/{rag,data-analysis,deep-research}.mdx`.

**LangGraph repo, included:**
- the 10 non-stub notebooks (9 under `examples/rag/` and `examples/code_assistant/langgraph_code_assistant_mistral.ipynb`)
- `examples/chatbot-simulation-evaluation/simulation_utils.py`
- `libs/cli/examples/graphs/storm.py`
- 5 CLI ReAct `agent.py` variants, which go into `B-react-handwritten`

**Prompt Flow:**
- 58 flow definitions (47 `flow.dag.yaml`, 10 `*.flex.yaml`, plus `flex-flows/chat-with-functions` with no YAML)
- 45 included: 34 application flows in 23 rows, and 11 eval flows in 10 rows
- 13 excluded (no LLM)

## 4. Coding scheme (CSV columns)

- `llm_call_sites`: static count of distinct LLM invocation sites in the workflow, counting graders and routers. A prebuilt agent counts once per agent model. Embedding calls and non-LLM ML services (Azure Language, CLU, LLMLingua's compressor) are not counted.
- `branching`:
  - `yes:llm`: a route predicate on LLM output, including deterministic tests on generated text (`'?' in joke`) and the agent's own tool-call decision;
  - `yes:tool`: a predicate on tool output (code exec);
  - `yes:llm+human`: an LLM route plus a human interrupt;
  - `cfg`: config/flag driven, including field-presence checks (not content semantics);
  - `len`: message/token length threshold;
  - `rand`: random placeholder;
  - `no`.
- `loop`:
  - `yes:react`: iterate while the LLM emits tool calls or handoffs;
  - `yes:grader`: iterate until an LLM grader accepts (evaluator-optimizer, self-RAG);
  - `yes:retry`: retry on validation failure;
  - `yes:turns`: dialogue turns until a stop phrase / max turns;
  - `no`.
- `fanout`:
  - `yes:llm-list`: `Send`/map over an LLM-produced list;
  - `yes:llm-tool-calls`: LLM-decided sub-agent delegations (deep agents);
  - `yes:input-list`: map over an input-derived list;
  - `fixed-k`: one grader call per retrieved document with a fixed k (count not content-dependent);
  - `static`: fixed parallel branches;
  - `no`.
- **Category.** (a) = `branching` starts with `yes`; (b) = `loop` starts with `yes`; (c) = `fanout` starts with `yes`; (d) = none of these. `cfg`, `len`, `rand`, `fixed-k` and `static` do not count as content-dependent.
- `decision_on_user_content`:
  - `yes`: the decision is a function of the semantics of user-provided input, directly or through an LLM judgement of it;
  - `partial`: only through structural properties (item count, field presence, length) or through a stylistic property of the LLM's own output;
  - `no`.

## 5. Summary statistics

Produced by `tools/build_census.py`. Percentages are of rows in the stated subset.

| Subset | Rows | Any content-dependent (a/b/c) | (a) branching | (b) loop | (c) fan-out | (d) none |
|---|---|---|---|---|---|---|
| All rows (A + A(eval) + B classes) | 72 | 42 (58%) | 36 (50%) | 27 (38%) | 9 (12%) | 30 (42%) |
| Tier A incl. PF eval flows | 64 | 39 (61%) | 34 (53%) | 25 (39%) | 8 (12%) | 25 (39%) |
| **Tier A application workflows (excl. eval)** | **54** | **37 (69%)** | 34 (63%) | 25 (46%) | 6 (11%) | 17 (31%) |
| Tier A, LangGraph/LangChain (both repos) | 31 | 30 (97%) | 28 (90%) | 24 (77%) | 5 (16%) | 1 (3%) |
| of which explicit-graph workflows (excl. 10 prebuilt-agent tutorials) | 21 | 20 (95%) | 18 (86%) | 14 (67%) | 3 (14%) | 1 (5%) |
| Tier A, Prompt Flow apps (excl. eval) | 23 | 7 (30%) | 6 (26%) | 1 (4%) | 1 (4%) | 16 (70%) |
| Tier A(eval), Prompt Flow | 10 | 2 (20%) (input-list fan-out) | 0 | 0 | 2 | 8 |
| Tier B API-demo classes | 8 | 3 (38%) | 2 | 2 | 1 | 5 |

Category combinations among the 54 Tier-A application rows: a+b 20, a 10, a+b+c 4, c 2, b 1, d 17.

Further observations on the 37 content-dependent Tier-A application rows:

- **Who drives the decision.** In 35 the decision depends on the semantics of user-supplied input (`yes`); in 2 only partially (`wa-prompt-chaining`, `pf-gen-docstring`).
- **Unbounded loops.** 22 of 25 looping workflows (88%) have no explicit iteration bound. They stop only on a content condition, or else on LangGraph's `recursion_limit`. The explicitly bounded ones are:
  - `lg-code-assistant`: `max_iterations = 3`
  - `lg-storm`: `max_num_turns = 5`
  - `lg-chat-simulation`: `max_turns = 6`

  The default `recursion_limit` is `DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))` at `langgraph/libs/langgraph/langgraph/_internal/_config.py:32`. The docs state "Starting in version 1.0.6, the default recursion limit is set to 1000 steps" (`docs/src/oss/langgraph/graph-api.mdx:1502`) for Python and 25 for JS (line 1512).
- **Fan-out bounds.** All content-dependent fan-outs are unbounded in code: `Send` over LLM lists, deep-agent delegation, per-chunk or per-statement maps.
- **Constant call count.** In 5 of 37 (14%), content changes metadata *without* changing the LLM call count:
  - `lg-crag-local`: web search is a tool, so 4 graders + 1 generator always run;
  - `wa-routing`: always 2 calls;
  - `pf-conditional-switch`: always 1 call;
  - `pf-promptflow-copilot`: always 3 calls; the final call's input switches between retrieved context and a refusal prompt;
  - `pf-chat-with-functions`.

  In these the leak is via token counts, latency or tool round trips only. In the other 32 the number and sequence of LLM calls varies with content.
- **Per-role model mixing.** At least 7 Tier-A workflows use different models for different roles, so the `model` field alone reveals which role ran:
  - adaptive/self/CRAG RAG notebooks: `gpt-4o-mini` graders vs `gpt-3.5-turbo` generators;
  - old agentic RAG: `gpt-4-turbo` agent, `gpt-4o` grader, `gpt-4-0125-preview` rewriter;
  - STORM: `gpt-4o-mini` vs `gpt-4o`;
  - router-knowledge-base: `gpt-5.4-mini` router vs `gpt-5.5` agents;
  - promptflow-copilot: `gpt-4` vs `gpt-35-turbo` relevance check.
- **Source contrast.**
  - The LangGraph/LangChain examples are almost all content-dependent (97%). This is by design: the corpus teaches routers, graders and agents.
  - Prompt Flow's DAG examples are mostly straight-line (70% (d)). Its content-dependent examples are:
    - `activate`-based: `conditional-flow-for-switch`, `promptflow-copilot`, `question-simulation`. `conditional-flow-for-if-else` uses `random.choice` as a placeholder, so it is (d) as implemented.
    - inside python nodes: `autonomous-agent`'s `while True` loop, `generate-test-data`'s early-return validation gates, `gen-docstring`'s per-chunk map.

## 6. Notable details found during review (relevant to porting)

- **Inverted gate.** `docs/src/oss/langgraph/workflows-agents.mdx`: the Python Functional API prompt-chaining gate is inverted (`"?" in joke or "!" in joke` returns `"Fail"`, lines 279-280). The Graph API (lines 208-209) and both JS versions (lines 342-343, 408-409) return `"Pass"`.
- **Generator prompt not in the clone.** The adaptive, CRAG and self-RAG notebooks pull the generator prompt from LangChain Hub (`hub.pull("rlm/rag-prompt")`). The only local copy of its text is the printed output in `langgraph/examples/rag/langgraph_agentic_rag.ipynb` (raw lines 211-217).
- **`format_docs` unused.** Those notebooks define `format_docs` but pass the raw `List[Document]` into `{context}` (e.g. `langgraph_adaptive_rag.ipynb:556`). Prompts therefore contain `Document(...)` reprs, which inflates input tokens.
- **Prompt Flow bypass propagation.** A node with no `activate` is bypassed only when *all* its node-reference dependencies are bypassed. This is why `promptflow-copilot`'s `select_prompt` still runs and selects the refusal prompt, and why `question-simulation`'s `call_llm_chat` is skipped.
- **Unbounded evaluator.** `wa-evaluator-optimizer` has no iteration cap. Its `route_joke` returns `None` for any grade other than the two literals.
- **Synthetic agent tools.** Several "agent" examples use stub tools that return constants (weather `search`, router-KB's GitHub/Notion/Slack tools, email-agent documentation search). Their tool outputs are content-independent, but the decision to call them is content-dependent.

## 7. Threats to validity

- **Static coding.** `llm_call_sites` counts code sites, not calls. Whether a branch is reachable, and how often loops iterate, depend on the models.
- **Tiering.** Tiering and deduplication are judgement calls. The CSV keeps all paths so the reader can re-tier. Prebuilt-agent tutorials inflate the LangGraph/LangChain content-dependent share; the explicit-graph-only subset (20/21) is reported separately for that reason.
- **Scope.**
  - The docs `create_agent`/`create_deep_agent` API snippets outside tutorials were not enumerated. Each would be a ReAct loop (b).
  - The 25 moved-stub LangGraph notebooks (reflection, reflexion, LATS, plan-and-execute, ReWOO, customer-support, multi-agent collaboration, SQL agent, ...) are absent at this commit. They would almost certainly add more (a)/(b) rows.
- **Prompt Flow eval flows.** Their activation depends on configuration and field presence, which we code as `cfg` (not content). A stricter reading, under which the presence of a ground-truth field is private, would move 3 rows to (a).
