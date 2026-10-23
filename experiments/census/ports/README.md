# Port candidates (8)

Selected from `../census.csv`. Selection criteria:

- **(i) Coverage.** Together the 8 cover the requested content-dependent patterns:
  - routing
  - gate/chaining
  - evaluator-optimizer loop
  - orchestrator-worker fan-out
  - corrective and adaptive/self-RAG grading with fallback
  - ReAct tool loop
  - a Prompt Flow `activate` conditional flow
- **(ii) Portability.** Each one is portable to a DSL with these primitives: LLM call (chat messages + `max_tokens`), string templates, equality/contains tests on LLM output, bounded "up to N until" loops, bounded "for up to K items of an LLM-produced list" fan-out, and pure deterministic tools (local retriever, calculator).

Each `<id>.md` contains:

- source paths and line numbers
- the verbatim prompts and code, expanded mechanically from the local clones with `tools/include.py`, so nothing is retyped
- the node graph and routing conditions
- loop and fan-out bounds
- the structured-output schemas and how to emulate them
- the secret attribute
- an honest list of deviations
- a dataset proposal checked against `https://huggingface.co/api/datasets/<id>` (all returned HTTP 200 on 2026-10-23)

Commits: langgraph `eb066bd31a2bf01fc0cd58256df4800a3695c233`; docs `5d83d5e690af84ed654a8d4320bf9969af28e39f`; promptflow `33a68c9d3cf349d7fdfad1f41969af27543c0406`.

## Summary table

| # | id (spec file) | Pattern | Source | LLM call sites | Content-dependent control | Original bound -> proposed | Secret attribute | Main metadata channel |
|---|---|---|---|---|---|---|---|---|
| 1 | [`email-support-agent`](email-support-agent.md) | Routing (Command goto) + review gate | docs `src/oss/langgraph/thinking-in-langgraph.mdx` | 2 (classifier, drafter) | intent/urgency route; billing or critical skips the draft | no loop | issue category (billing/bug/question...), urgency | #calls (1 vs 2), draft input tokens, HITL pause |
| 2 | [`wa-prompt-chaining`](wa-prompt-chaining.md) | Gate / prompt chaining | docs `src/oss/langgraph/workflows-agents.mdx` | 3 | `'?' or '!' in joke` gate | no loop | property of the hidden first output; topic category | #calls (1 vs 3) |
| 3 | [`wa-evaluator-optimizer`](wa-evaluator-optimizer.md) | Evaluator-optimizer loop | docs `workflows-agents.mdx` | 2 | loop until grade == "funny" | **unbounded** -> 5 rounds | topic category / how often hidden output was rejected | #rounds, growing input tokens |
| 4 | [`wa-orchestrator-worker`](wa-orchestrator-worker.md) | Orchestrator-worker, `Send` fan-out | docs `workflows-agents.mdx` | 2 (planner, worker) | one worker per LLM-planned section | **unbounded K** -> 8 | topic category / breadth | #worker calls, per-call output tokens |
| 5 | [`lg-crag-local`](lg-crag-local.md) | Corrective RAG (per-doc grading + web fallback) | langgraph `examples/rag/langgraph_crag_local.ipynb` | 2 (grader x4 docs, generator) | any doc graded "no" -> web search | fixed k=4 graders, no loop | question in/out of private corpus | **constant #calls**; generator input tokens, latency |
| 6 | [`lg-adaptive-rag`](lg-adaptive-rag.md) | Adaptive/self-RAG: router + doc/hallucination/answer graders + rewrite loops | langgraph `examples/rag/langgraph_adaptive_rag.ipynb` (+ `_local`) | 6 | router; relevance gate; 3 grader-driven cycles | **3 unbounded cycles** -> <=2 rewrites, <=2 regenerations | in-corpus topic; answerability | #calls, #rounds, model identity (gpt-4o-mini vs gpt-3.5) |
| 7 | [`calculator-react-agent`](calculator-react-agent.md) | ReAct tool loop | docs `workflows-agents.mdx` + `quickstart.mdx` | 1 (+3 tools) | loop while tool_calls | **unbounded** -> 10 LLM turns | arithmetic step count of a private problem | #calls, cumulative input tokens |
| 8 | [`pf-conditional-switch`](pf-conditional-switch.md) | Prompt Flow `activate` switch | promptflow `examples/flows/standard/conditional-flow-for-switch/` | 1 | substring class -> activated branch | none | shopping intent | **constant #calls (1)**; classifier output tokens |

## Datasets (all verified via the HF API, HTTP 200)

| # | HF dataset id | License | Size (rows) | Input field | Ground-truth label for the secret |
|---|---|---|---|---|---|
| 1 | `Tobi-Bueck/customer-support-tickets` (alt: `bitext/Bitext-customer-support-llm-chatbot-training-dataset`) | cc-by-nc-4.0, synthetic (alt: cdla-sharing-1.0) | 61,765 (28,261 `language=en`) (alt: 26,872) | `subject` + `body` (alt: `instruction`) | `queue` (`Billing and Payments`), `priority` (`critical`/`high`/...), `type` (alt: `category`, `intent`) |
| 2 | `fancyzhx/dbpedia_14` | cc-by-sa-3.0 | 560,000 / 70,000 | `title` -> topic | `label` (14 entity classes) |
| 3 | `fancyzhx/dbpedia_14` | cc-by-sa-3.0 | 560,000 / 70,000 | `title` -> topic | `label` |
| 4 | `fancyzhx/dbpedia_14` (alt: `keivalya/MedQuad-MedicalQnADataset`, no license on card) | cc-by-sa-3.0 | 560,000 / 70,000 (alt: 16,407) | `title` (alt: `Question` focus) | `label` (alt: `qtype`) |
| 5 | `rajpurkar/squad` (alt: `hotpotqa/hotpot_qa` distractor) | cc-by-sa-4.0 | 87,599 / 10,570; 48 validation titles | `question`; corpus = `context` paragraphs of indexed titles | `in_corpus` = title in indexed half; gold paragraph for per-doc relevance |
| 6 | `rajpurkar/squad_v2` | cc-by-sa-4.0 | 130,319 / 11,873; 35 validation titles; 5,945 unanswerable | `question`; corpus = indexed titles' `context` | `in_corpus`, `answerable` (`answers.text` non-empty) |
| 7 | `openai/gsm8k` (config `main`) | mit | 7,473 / 1,319 | `question` | number of `<<...>>` calculator steps in `answer` (test: median 3, p95 6, max 8); final answer after `####` |
| 8 | `bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset` (alt: `clinc/clinc_oos`) | cdla-sharing-1.0 (alt: cc-by-3.0) | 44,884 (alt: 15,250/3,100/5,500 `plus`) | `instruction` -> `query` | `intent` mapped: order_* -> order_search; product_information/availability* -> product_info; **no recommendation intent exists**, so use `unknown`/hand-written supplement |

## Cross-cutting deviations (apply to all ports)

- **Structured output and native tool calling become constrained text plus contains/equals tests.** The original sends JSON schemas/tool definitions in the request and gets tool-call JSON back, so absolute token counts differ from the original. Relative branch differences are what is preserved.
- **`max_tokens` is added everywhere.** Most originals rely on provider defaults; exception: Prompt Flow switch, `max_tokens: 128`.
- **Live external tools become deterministic local tools.** Web loaders, embeddings, vector stores and Tavily are replaced; the retrieval ranking and the sizes of what is retrieved therefore differ.
- **Unbounded cycles get explicit bounds.** LangGraph's default `recursion_limit` is 10007 super-steps in langgraph 1.2.16 (`libs/langgraph/langgraph/_internal/_config.py:32`), while `docs/src/oss/langgraph/graph-api.mdx:1502` states 1000. Report bound-saturation rates.
- **Models are replaced by the study's model(s).** Where the original mixes models (adaptive RAG; router-KB in the census), model identity is itself a metadata channel. Keep that split if it is in scope.

## Runners-up (not ported, but in the census)

- `pf-promptflow-copilot`: relevance gate (max_tokens=1 score) that bypasses retrieval. A strong leak, but it needs on-topic/off-topic promptflow questions, for which no HF dataset was found.
- `agentic-rag` (docs + langgraph): tool-call decision + grade -> rewrite loop.
- `router-knowledge-base`: `Send` fan-out to ReAct sub-agents using different models.
- `chinook-support-agent`: router -> refund subgraph vs. QA agent.
- `wa-routing`: constant call count; only output length leaks.
- `pf-generate-test-data`: gated 5-call chain.
- `pf-question-simulation`: stop/continue gate.
