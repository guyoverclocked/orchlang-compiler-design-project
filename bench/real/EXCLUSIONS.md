# Exclusion log

Every candidate of the real-workflow corpus that was not ported, with the
category (defined in advance in `PROTOCOL.md` section 5) and the concrete
reason. Generated from `manifest.json`; 22 of 52 candidates.

| Category | Meaning | Count |
|---|---|---|
| X1 | Model-chosen control: the model selects which tool, agent or node runs next, or how many. | 9 |
| X2 | Reads whose number, or whose tool, the model chooses at run time. | 1 |
| X3 | A cyclic state graph with more than one back edge. | 2 |
| X4 | Iteration whose count depends on data. | 1 |
| X5 | Interactive human input during the run, concurrency, or timing. | 4 |
| X6 | Multimodal input. | 1 |
| X7 | A duplicate of another candidate (different model backend or evaluation harness). | 4 |

| Candidate | Split | Source | Category | Reason |
|---|---|---|---|---|
| `ac-orchestrator-workers` | held-out | `anthropics/anthropic-cookbook` orchestrator_workers.ipynb | X1 | the orchestrator model chooses how many worker calls run ("2-3 approaches", parsed from its answer) |
| `ac-async-multi-agent` | held-out | `anthropics/anthropic-cookbook` async_multi_agent_orchestration.ipynb | X5 | concurrent agents exchanging messages through a hub; the lead spawns helpers at run time (also X1) |
| `ac-latency-multi-agent` | dev | `anthropics/anthropic-cookbook` latency_multi_agent.ipynb | X5 | concurrent lead-and-helpers team driven by a shared clock (also X1) |
| `lg-langsmith-agent-simulation` | held-out | `langchain-ai/langgraph` langsmith-agent-simulation-evaluation.ipynb | X7 | the same simulated-conversation graph as lg-agent-simulation, run over a LangSmith dataset for red-teaming (also X4) |
| `lg-information-gather` | held-out | `langchain-ai/langgraph` information-gather-prompting.ipynb | X5 | interactive loop reading user input with input() until the model has gathered requirements |
| `lg-customer-support` | dev | `langchain-ai/langgraph` customer-support.ipynb | X1 | tool-calling assistant that chooses among many tools in a loop; later parts add human approval interrupts (X5) |
| `lg-lats` | held-out | `langchain-ai/langgraph` lats.ipynb | X1 | Monte-Carlo tree search: the model expands and scores a tree of candidates |
| `lg-llm-compiler` | dev | `langchain-ai/langgraph` LLMCompiler.ipynb | X1 | the planner model emits a task DAG that a scheduler executes, with re-planning |
| `lg-hierarchical-teams` | dev | `langchain-ai/langgraph` hierarchical_agent_teams.ipynb | X1 | supervisor models route among ReAct agents |
| `lg-multi-agent-collaboration` | held-out | `langchain-ai/langgraph` multi-agent-collaboration.ipynb | X1 | two ReAct agents with tools hand off until one says FINAL ANSWER |
| `lg-plan-and-execute` | held-out | `langchain-ai/langgraph` plan-and-execute.ipynb | X1 | a model-written plan of variable length is executed by a ReAct agent and re-planned |
| `lg-adaptive-rag` | held-out | `langchain-ai/langgraph` langgraph_adaptive_rag.ipynb | X3 | back edges transform_query -> retrieve and generate -> generate / transform_query |
| `lg-adaptive-rag-local` | held-out | `langchain-ai/langgraph` langgraph_adaptive_rag_local.ipynb | X7 | lg-adaptive-rag with a local Ollama model |
| `lg-crag-local` | held-out | `langchain-ai/langgraph` langgraph_crag_local.ipynb | X7 | lg-crag with a local model |
| `lg-self-rag` | held-out | `langchain-ai/langgraph` langgraph_self_rag.ipynb | X3 | back edges transform_query -> retrieve and generate -> generate / transform_query |
| `lg-self-rag-local` | dev | `langchain-ai/langgraph` langgraph_self_rag_local.ipynb | X7 | lg-self-rag with a local model |
| `lg-reflexion` | dev | `langchain-ai/langgraph` reflexion.ipynb | X2 | the model writes a list of 1-3 search queries, each run as a search whose results feed the revision |
| `lg-rewoo` | dev | `langchain-ai/langgraph` rewoo.ipynb | X1 | the planner model writes a plan of tool steps that the graph executes |
| `lg-tnt-llm` | held-out | `langchain-ai/langgraph` tnt-llm.ipynb | X4 | summarises a dataset of conversations and iterates over as many minibatches as the data has |
| `lg-tot` | held-out | `langchain-ai/langgraph` tot.ipynb | X1 | tree-of-thoughts beam search with dynamic fan-out (Send) |
| `lg-usaco` | held-out | `langchain-ai/langgraph` usaco.ipynb | X5 | the final graph interrupts for a human after evaluation; its solve/evaluate loop has no bound but the recursion limit |
| `lg-web-voyager` | held-out | `langchain-ai/langgraph` web_voyager.ipynb | X6 | browser agent on screenshots choosing among browser tools (also X1) |

## What the log says about the language

Thirteen of the twenty-two exclusions (X1 to X4), and two of the four X5
exclusions that are also X1, come from one limitation:
OrchLang fixes the shape of a workflow before it runs. Its only loop is
`retry n`, its only branch reads a declared value, and its inputs are
declared up front, which is what makes the worst-case bound and the
relational analysis decidable. Agents whose model decides what runs next
are outside that shape by design, and the corpus shows how much of current
practice they are: every multi-agent, planner and tree-search tutorial.

The ported workflows needed adaptations the language forces (listed per port
in `manifest.json`): unrolling self-correction loops whose later attempts see
earlier ones, because a `retry` body cannot (lg-code-assistant,
lg-extraction-retries, ac-evaluator-optimizer, lg-reflection,
lg-agent-simulation); dropping early exits decided by a test on a response
text (A3); cascading a categorical choice into yes/no calls (A2); passing
whole responses where the source extracts a field (A1); and returning a
stand-in where the source returns a value computed inside a branch (A6).
Where an adaptation changes cost, the port over-approximates; the one
exception is `ac-evaluator-optimizer`, whose source has no bound at all.
