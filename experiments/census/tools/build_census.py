# Builds census.csv and prints summary statistics.
# Repo prefixes: langgraph/ = /home/user/langchain-ai/langgraph (eb066bd3), docs/ = /home/user/langchain-ai/docs (5d83d5e6),
# promptflow/ = /home/user/microsoft/promptflow (33a68c9d)
import csv, sys, collections

OUT = sys.argv[1]
R = []
def row(id, source, paths, desc, sites, br, lp, fo, user, obs, ev, notes):
    R.append(dict(id=id, source=source, paths=paths, description=desc, llm_call_sites=sites,
                  branching=br, loop=lp, fanout=fo, decision_on_user_content=user,
                  observer_inference=obs, evidence_lines=ev, notes=notes))

LG = "langgraph/"; D = "docs/"; PF = "promptflow/"

# ------------------------------------------------------------------ LangGraph repo (Tier A)
row("lg-adaptive-rag", "langgraph",
    LG+"examples/rag/langgraph_adaptive_rag.ipynb; "+LG+"examples/rag/langgraph_adaptive_rag_local.ipynb",
    "Adaptive RAG: LLM router (vectorstore vs web search) -> retrieve -> per-doc relevance grader -> generate -> hallucination grader -> answer grader; rewrite+re-retrieve and regenerate cycles. _local variant = same topology with Ollama JSON-mode prompts.",
    6, "yes:llm", "yes:grader", "fixed-k", "yes",
    "query in/out of indexed domain (web route skips per-doc grader calls); how many retrieved docs judged relevant (generate input tokens); number of rewrite/regenerate cycles (retrieval failure / ungrounded answer)",
    "langgraph_adaptive_rag.ipynb:636-655 (route_question), 658-683 (decide_to_generate), 686-722 (grade_generation_v_documents_and_question), 752-779 (edges; 770 transform_query->retrieve; 775 'not supported'->generate; 777 'not useful'->transform_query); _local.ipynb:609-631, 634-659, 662-698, 728-747",
    "tier=A; cat=a+b; cycles unbounded in code (only recursion_limit; default 10007 at this commit per libs/langgraph/langgraph/_internal/_config.py:32); generator prompt pulled from LangChain Hub (rlm/rag-prompt)")
row("lg-adaptive-rag-cohere", "langgraph", LG+"examples/rag/langgraph_adaptive_rag_cohere.ipynb",
    "Cohere Command-R adaptive RAG: tool-calling router with 3 outcomes (vectorstore / web_search / llm_fallback if no tool call) -> per-doc grader -> web search if none relevant -> generate; regenerate if ungrounded, web search if not useful.",
    6, "yes:llm", "yes:grader", "fixed-k", "yes",
    "chit-chat vs domain vs web question (fallback path = 2 LLM calls total); relevance of retrieved docs; grounding failures (regeneration count)",
    "langgraph_adaptive_rag_cohere.ipynb:728-760 (route_question; 744-748 llm_fallback when no tool_calls), 763-786 (decide_to_generate), 789-825 (grade_generation), 861-889 (edges; 884 'not supported'->generate, 885 'not useful'->web_search)",
    "tier=A; cat=a+b; different topology from lg-adaptive-rag (llm_fallback node, no query rewriter)")
row("lg-crag", "langgraph", LG+"examples/rag/langgraph_crag.ipynb",
    "Corrective RAG: retrieve -> grade each doc -> if any doc irrelevant: rewrite query + Tavily web search -> generate.",
    3, "yes:llm", "no", "fixed-k", "yes",
    "whether >=1 retrieved doc judged irrelevant (extra rewrite call + web results in generate input)",
    "langgraph_crag.ipynb:393-423 (grade_documents; web_search='Yes' at 421), 473-499 (decide_to_generate), 533-543 (edges)",
    "tier=A; cat=a")
row("lg-crag-local", "langgraph", LG+"examples/rag/langgraph_crag_local.ipynb",
    "CRAG with local Llama3 (Ollama JSON mode): retrieve(k=4) -> per-doc yes/no JSON grade -> web search if any irrelevant (no rewrite) -> generate. Notebook also has a LangSmith eval harness (GPT-4o answer grader) outside the graph.",
    2, "yes:llm", "no", "fixed-k", "yes",
    "whether any retrieved doc judged irrelevant (web results appended -> larger generate input tokens, extra tool latency)",
    "langgraph_crag_local.ipynb:192 (as_retriever k=4), 414-446 (grade_documents; search='Yes' at 439), 474-488 (decide_to_generate), 503-512 (edges)",
    "tier=A; cat=a; topology differs from lg-crag (no transform_query)")
row("lg-self-rag", "langgraph",
    LG+"examples/rag/langgraph_self_rag.ipynb; "+LG+"examples/rag/langgraph_self_rag_local.ipynb; "+LG+"examples/rag/langgraph_self_rag_pinecone_movies.ipynb",
    "Self-RAG: retrieve -> grade docs -> rewrite+re-retrieve if none relevant -> generate -> hallucination grader -> answer grader -> regenerate / rewrite cycles. Local (Ollama) and Pinecone-movies variants share topology.",
    5, "yes:llm", "yes:grader", "fixed-k", "yes",
    "number of rewrite cycles (question poorly covered by corpus) and regenerations (grounding failures)",
    "langgraph_self_rag.ipynb:540-565 (decide_to_generate), 568-604 (grade_generation), 637-654 (edges; 645 transform_query->retrieve, 650 'not supported'->generate); _local.ipynb:631-646; _pinecone_movies.ipynb:639-654",
    "tier=A; cat=a+b; unbounded cycles")
row("agentic-rag", "langgraph+docs",
    LG+"examples/rag/langgraph_agentic_rag.ipynb; "+D+"src/code-samples/langgraph/agentic-rag-tutorial.py; "+D+"src/code-samples/langgraph/agentic-rag-tutorial.ts; "+D+"src/oss/langgraph/agentic-rag.mdx (+ src/snippets/code-samples/agentic-rag-*.mdx generated copies)",
    "Agentic RAG: tool-calling LLM decides to call retriever or answer directly -> ToolNode retrieve -> LLM relevance grade -> generate answer, or rewrite question and loop back to the agent.",
    4, "yes:llm", "yes:grader", "no", "yes",
    "whether question needed retrieval (greeting answered in 1 call); whether retrieved context was relevant (generate vs rewrite path); number of rewrite cycles",
    "docs agentic-rag-tutorial.py:170-183 (grade_documents), 376-380 (route_on_tool_calls), 384-402 (edges; 402 rewrite_question->generate_query_or_respond); agentic-rag-tutorial.ts:203-218; langgraph_agentic_rag.ipynb:235-290 (grade_documents), 426-444 (edges)",
    "tier=A; cat=a+b; old notebook (gpt-4-turbo, inline prompts) and current docs tutorial (GRADE/REWRITE/GENERATE_PROMPT constants) share topology; deduped Py/TS")
row("lg-code-assistant", "langgraph", LG+"examples/code_assistant/langgraph_code_assistant_mistral.ipynb",
    "Code generation (Codestral): generate structured {prefix, imports, code} -> exec-based import/code check -> retry with error feedback until success or max_iterations.",
    1, "yes:tool", "yes:retry", "no", "yes",
    "whether generated code failed exec checks (1-3 generate calls, growing input tokens with error text)",
    "langgraph_code_assistant_mistral.ipynb:238 (max_iterations = 3), 350-368 (decide_to_finish; 363), 409-417 (conditional edge)",
    "tier=A; cat=a+b; bounded (3); sibling notebook langgraph_code_assistant.ipynb is a moved-stub")
row("lg-storm", "langgraph", LG+"libs/cli/examples/graphs/storm.py",
    "STORM Wikipedia-article writer: outline + related-topic survey -> LLM-generated editor personas -> parallel interview subgraphs (question/answer turns with web search) -> refine outline -> per-section writers -> final article.",
    9, "yes:llm", "yes:turns", "yes:llm-list", "yes",
    "number of editors and sections chosen by the LLM for the topic (topic breadth); interview lengths; number of search queries",
    "storm.py:356 (max_num_turns = 5), 359-369 (route_messages; 367 stop phrase), 376 (conditional edge), 330 (search_engine.abatch over LLM queries), 545 (interview_graph.abatch over editors), 591 (section_writer.abatch over outline.sections)",
    "tier=A; cat=a+b+c; lives under CLI test fixtures but is a full workflow (port of the STORM tutorial)")
row("lg-chat-simulation", "langgraph", LG+"examples/chatbot-simulation-evaluation/simulation_utils.py",
    "Chat simulator for evaluation: assistant <-> simulated-user loop until user says FINISHED or max_turns.",
    2, "yes:llm", "yes:turns", "no", "yes",
    "conversation length -> whether simulated user was satisfied early",
    "simulation_utils.py:80-121 (create_chat_simulator; 114-117 conditional edge), 195-203 (_should_continue; 198 max_turns, 200 FINISHED)",
    "tier=A; cat=a+b; bounded (max_turns=6 default); the notebooks using it are moved-stubs")

# ------------------------------------------------------------------ Docs repo (Tier A)
W = D+"src/oss/langgraph/workflows-agents.mdx"
row("wa-prompt-chaining", "docs", W+" (Python Graph+Functional; JS Graph+Functional)",
    "Prompt chaining with programmatic gate: generate joke -> gate ('?' or '!' in joke) -> if Fail: improve (wordplay) -> polish (twist).",
    3, "yes:llm", "no", "no", "partial",
    "whether the first generation contained '?' or '!' (1 vs 3 LLM calls)",
    "workflows-agents.mdx:204-210 (check_punchline), 236-238 (conditional edge); Functional 276-282 (INVERTED), JS 340-345, 370-372, 405-411",
    "tier=A; cat=a; Python Functional API gate returns 'Fail' when '?'/'!' present (lines 279-280) -- inverted relative to Python Graph API and both JS versions")
row("wa-parallelization", "docs", W+" (Python Graph+Functional; JS)",
    "Parallelization: joke, story, poem LLM calls in parallel -> string aggregator.",
    3, "no", "no", "static", "no",
    "nothing from control flow (3 calls always); only per-call output lengths",
    "workflows-agents.mdx:465-585 (519-524 edges), JS 587-707",
    "tier=A; cat=d")
row("wa-routing", "docs", W+" (Python Graph+Functional; JS)",
    "Routing: structured-output router (story/joke/poem) -> one of three LLM nodes (each just invokes the raw input).",
    4, "yes:llm", "no", "no", "yes",
    "requested genre: call count constant (2) but router output tokens and branch output length (story >> poem > joke) differ",
    "workflows-agents.mdx:723-726 (Route schema), 762-775 (llm_call_router), 779-786 (route_decision), 800-809 (edges); Functional 879-885; JS 986-1000",
    "tier=A; cat=a")
row("wa-orchestrator-worker", "docs", W+" (Python Graph+Functional; JS)",
    "Orchestrator-worker: planner (structured Sections list) -> Send one worker LLM call per planned section -> synthesizer (string join).",
    2, "no", "no", "yes:llm-list", "yes",
    "number of planned sections (worker call count) and per-section lengths -> topic breadth/category",
    "workflows-agents.mdx:1122-1136 (Section/Sections schema), 1381-1385 (assign_workers via Send), 1398-1400 (conditional edge); Functional 1204-1211; JS 1482-1494",
    "tier=A; cat=c; unbounded K; Graph API worker system prompt differs from Functional API one")
row("wa-evaluator-optimizer", "docs", W+" (Python Graph+Functional; JS)",
    "Evaluator-optimizer: joke generator <-> structured evaluator (funny / not funny + feedback) loop until 'funny'.",
    2, "yes:llm", "yes:grader", "no", "yes",
    "number of generate/evaluate rounds until accepted",
    "workflows-agents.mdx:1531-1538 (Feedback schema), 1565-1571 (route_joke), 1584-1591 (edges); Functional 1641-1645 (while True); JS 1716-1730",
    "tier=A; cat=a+b; unbounded")
row("calculator-react-agent", "docs", W+" (Agents section); "+D+"src/oss/langgraph/quickstart.mdx (Graph+Functional, Python+JS)",
    "Tool-calling ReAct agent with add/multiply/divide tools; loop LLM <-> tool node until the LLM stops calling tools.",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of arithmetic tool calls (problem complexity), whether the input was arithmetic at all",
    "workflows-agents.mdx:1893-1905 (should_continue), 1916-1921 (edges), 1969 (Functional while True); quickstart.mdx:343-355, 396-401, 560-571, 584",
    "tier=A; cat=a+b; unbounded; quickstart state also counts llm_calls")
row("email-support-agent", "docs", D+"src/oss/langgraph/thinking-in-langgraph.mdx (Python+JS)",
    "Customer-email triage: LLM classifies intent+urgency (structured) -> Command routing to human_review / search_documentation / bug_tracking / draft_response; draft LLM; human review (interrupt) if high/critical/complex.",
    2, "yes:llm+human", "no", "no", "yes",
    "billing-or-critical emails skip the drafting call (1 vs 2 LLM calls); question/feature drafts include doc snippets, bug drafts a ticket id (draft input tokens); HITL pause reveals high/critical/complex",
    "thinking-in-langgraph.mdx:212-216 (EmailClassification), 542-575 (classify_intent; 562-569 routing), 739-786 (draft_response; 775-781 needs_review), 788-811 (human_review), 934-958 (wiring)",
    "tier=A; cat=a")
row("langgraph-sql-agent", "docs", D+"src/code-samples/langgraph/langgraph-sql-agent.py; "+D+"src/code-samples/langgraph/langgraph-sql-agent.ts; "+D+"src/oss/langgraph/sql-agent.mdx",
    "Custom SQL agent: list tables (fixed) -> forced get_schema tool call -> generate_query (tool-calling) -> check_query -> run_query -> back to generate_query until an answer; HITL variant interrupts before run_query.",
    3, "yes:llm", "yes:react", "no", "yes",
    "number of query attempts (SQL errors / question difficulty), which tables' schemas were fetched (input tokens)",
    "langgraph-sql-agent.py:160 (call_get_schema), 187 (generate_query), 219 (check_query), 236-241 (should_continue), 257-262 (edges); .ts:300-323",
    "tier=A; cat=a+b; unbounded")
row("router-knowledge-base", "docs", D+"src/oss/langchain/multi-agent/router-knowledge-base.mdx (Python+JS)",
    "Multi-source router: structured classifier emits (source, sub-query) list -> Send to github/notion/slack create_agent ReAct agents (stub tools) in parallel -> LLM synthesizer.",
    5, "yes:llm", "yes:react", "yes:llm-list", "yes",
    "which and how many knowledge sources were consulted (1-3; model mix gpt-5.4-mini vs gpt-5.5), per-agent tool-loop lengths -> query topic",
    "router-knowledge-base.mdx:947-975 (agents), 979-998 (classify_query), 1002-1006 (route_to_agents Send), 1069 (conditional edge); tutorial parts 469-501, 677",
    "tier=A; cat=a+b+c")
row("handoffs-sales-support", "docs", D+"src/oss/langchain/multi-agent/handoffs.mdx (Python 419-562, JS 566-722)",
    "Two create_agent agents (sales, support) with transfer tools returning Command(goto=..., graph=PARENT); route_after_agent until an agent answers without tool calls.",
    2, "yes:llm", "yes:react", "no", "yes",
    "sales vs support request (number of agent hops, which system prompt)",
    "handoffs.mdx:437-476 (transfer tools), 481-491 (agents), 508-529 (routers), 538-546 (edges)",
    "tier=A; cat=a+b; unbounded hops")
row("handoffs-customer-support", "docs", D+"src/oss/langchain/multi-agent/handoffs-customer-support.mdx",
    "Single create_agent whose prompt/tools switch by current_step (warranty_collector -> issue_classifier -> resolution_specialist) via tools returning Command(update=current_step); step middleware.",
    1, "yes:llm", "yes:react", "no", "yes",
    "warranty status and issue type (step-specific system prompts/tools change per-call input tokens; escalation tool use)",
    "handoffs-customer-support.mdx:193-231 (record_* tools set current_step), 488-512 (apply_step_config), 583-588 (create_agent)",
    "tier=A; cat=a+b; prebuilt create_agent loop")
row("custom-workflow-wnba-rag", "docs", D+"src/oss/langchain/multi-agent/custom-workflow.mdx (Python 138-225, JS 232-328)",
    "Straight graph: structured query rewrite -> retrieve k=5 -> create_agent (may call get_latest_news tool) answers.",
    2, "no", "yes:react", "no", "yes",
    "whether the agent needed the news tool (question about latest news vs KB facts)",
    "custom-workflow.mdx:178-182 (agent), 188-200 (rewrite_query), 204-209 (call_agent), 211-221 (edges)",
    "tier=A; cat=b (loop inside prebuilt agent only)")
row("subagents-personal-assistant", "docs", D+"src/oss/langchain/multi-agent/subagents-personal-assistant.mdx (Python+JS)",
    "Supervisor create_agent with schedule_event/manage_email tools, each wrapping a sub-agent (calendar_agent, email_agent) with its own tools; HITL variant.",
    3, "yes:llm", "yes:react", "no", "yes",
    "whether the request involved calendar, email or both (nested sub-agent calls and their tool loops)",
    "subagents-personal-assistant.mdx:244 (calendar_agent), 375 (email_agent), 479-510 (wrapper tools), 580-583 (supervisor)",
    "tier=A; cat=a+b; parallel tool calls possible but not modelled as fan-out")
row("skills-sql-assistant", "docs", D+"src/oss/langchain/multi-agent/skills-sql-assistant.mdx",
    "create_agent with load_skill tool (progressive disclosure of per-domain SQL schema/business-logic skills); constrained-state variant.",
    1, "yes:llm", "yes:react", "no", "yes",
    "which skill was loaded (tool output size -> next call input tokens) ~ business domain of the question",
    "skills-sql-assistant.mdx:485-486 (load_skill), 641 (create_agent), 850-851 (Command-returning load_skill), 1056",
    "tier=A; cat=a+b")
row("langchain-sql-agent", "docs", D+"src/code-samples/langchain/sql-agent.py; "+D+"src/code-samples/langchain/sql-agent.ts; "+D+"src/oss/langchain/sql-agent.mdx",
    "create_agent SQL agent over Chinook with list/schema/query tools; HITL middleware variant.",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of tool rounds (query difficulty, SQL errors)",
    "sql-agent.py:182, 215, 426 (create_agent)",
    "tier=A; cat=a+b")
row("langchain-quickstart-weather", "docs", D+"src/oss/langchain/quickstart.mdx",
    "Quickstart create_agent with get_weather tool (one tab per provider) and an extended real-world agent.",
    1, "yes:llm", "yes:react", "no", "yes",
    "whether a tool call happened (weather question vs other)",
    "quickstart.mdx:269-276 (and per-provider repeats 287-330)",
    "tier=A; cat=a+b")
row("voice-agent", "docs", D+"src/oss/langchain/voice-agent.mdx",
    "Speech-to-text -> create_agent with tools -> text-to-speech pipeline.",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of agent/tool rounds per utterance",
    "voice-agent.mdx:363 (create_agent), 443 (JS)",
    "tier=A; cat=a+b")
row("deep-agent-from-scratch", "docs", D+"src/code-samples/langchain/deep-agent-from-scratch.py; .ts; "+D+"src/oss/langchain/deep-agent-from-scratch.mdx",
    "Builds a deep agent from create_agent + middleware (sandbox, summarization, skills, visualization subagent).",
    2, "yes:llm", "yes:react", "yes:llm-tool-calls", "yes",
    "number of tool rounds and subagent delegations",
    "deep-agent-from-scratch.py:6, 115, 163, 194, 225 (create_agent variants)",
    "tier=A; cat=a+b+c")
row("deepagents-deep-research", "docs", D+"src/code-samples/deepagents/deep-research.py (+ .ts, deep-research-agent-gemini.py); "+D+"src/oss/deepagents/deep-research.mdx",
    "Deep research agent: orchestrator deep agent with Tavily search + research sub-agent delegation and todo list.",
    2, "yes:llm", "yes:react", "yes:llm-tool-calls", "yes",
    "number of research sub-tasks delegated, search rounds -> breadth of the research question",
    "deep-research.py:255-261 (create_deep_agent with subagents)",
    "tier=A; cat=a+b+c; prebuilt deepagents")
row("deepagents-data-analysis", "docs", D+"src/code-samples/deepagents/data-analysis.py; "+D+"src/oss/deepagents/data-analysis.mdx",
    "Deep agent with sandbox backend analysing CSV data and posting a Slack report.",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of code-execution rounds (analysis difficulty)",
    "data-analysis.py:86 (create_deep_agent)",
    "tier=A; cat=a+b")
row("deepagents-rag", "docs", D+"src/code-samples/deepagents/rag-deep.py (+ rag-deep-full.py, rag-deep-baseline.py, .ts); "+D+"src/oss/deepagents/rag.mdx",
    "RAG agent built as a deep agent with a docs search tool (plus non-agent baseline).",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of search rounds (question difficulty/coverage)",
    "rag-deep.py:197 (create_deep_agent)",
    "tier=A; cat=a+b")
row("chinook-support-agent", "docs", D+"src/langsmith/evaluate-complex-agent.mdx",
    "Chinook music-store support: intent classifier -> refund subgraph (structured info extraction -> refund / lookup / END) or QA create_agent with lookup tools -> compile follow-up.",
    3, "yes:llm", "yes:react", "no", "yes",
    "refund vs question intent (different subgraphs/models); whether the user supplied invoice ids vs name+phone",
    "evaluate-complex-agent.mdx:1004-1022 (gather_info routing), 1262 (qa_graph), 1268-1300 (router schema+intent_classifier), 1316 (subgraph node)",
    "tier=A; cat=a+b; plus an LLM grader used only for evaluation")

# ------------------------------------------------------------------ Docs/LangGraph Tier B equivalence classes (API demos)
row("B-single-llm-node", "docs",
    D+"src/oss/langgraph/add-memory.mdx (blocks 103-2365); "+D+"src/oss/langgraph/streaming.mdx:336-612,2065-2104; "+D+"src/langsmith/streaming.mdx:642-670; "+D+"src/oss/langgraph/use-graph-api.mdx:3347-3360; "+D+"src/oss/langgraph/use-functional-api.mdx:122-187,1538-1630; "+D+"src/oss/python/integrations/providers/cockroachdb.mdx:162-245; "+D+"src/oss/python/integrations/providers/langfuse.mdx:119-153; "+D+"src/oss/python/integrations/providers/truefoundry.mdx:64-90; "+D+"src/oss/python/integrations/chat/anthropic.mdx:1391-1438; "+D+"src/langsmith/generative-ui-react.mdx:79-174",
    "API-demo graphs with one chat-model node (START -> call_model -> END), used to illustrate memory, streaming, async, tracing, deployment.",
    1, "no", "no", "no", "no", "nothing beyond per-call sizes", "see paths (line ranges)",
    "tier=B; cat=d; counted once as an equivalence class")
row("B-runtime-config-selection", "docs+langgraph",
    D+"src/oss/langgraph/use-graph-api.mdx:1261-1477; "+D+"src/langsmith/configuration-cloud.mdx:17-46; "+D+"src/langsmith/graph-rebuild.mdx:73-143",
    "Single-node graphs whose model (or tool set / graph) is selected from runtime context or per-user config.",
    1, "cfg", "no", "no", "no", "model identity reveals deployment/user configuration, not content", "use-graph-api.mdx:1273-1281; configuration-cloud.mdx:23-27; graph-rebuild.mdx:73-99",
    "tier=B; cat=d (config-dependent only)")
row("B-react-handwritten", "docs+langgraph",
    D+"src/oss/langgraph/interrupts.mdx:711-916; "+D+"src/langsmith/evaluate-graph.mdx:20-96,286-442; "+D+"src/langsmith/trace-with-langgraph.mdx:79-202; "+D+"src/langsmith/setup-javascript.mdx:94-165; "+D+"src/oss/javascript/integrations/tools/composio.mdx:129-201; "+LG+"libs/cli/examples/graphs/agent.py; "+LG+"libs/cli/examples/graphs_reqs_a/graphs_submod/agent.py; "+LG+"libs/cli/examples/graphs_reqs_b/graphs_submod/agent.py; "+LG+"libs/cli/examples/graph_prerelease_reqs/agent.py; "+LG+"libs/cli/examples/graph_prerelease_reqs_fail/agent.py",
    "Hand-written agent<->tools loop (should_continue on tool_calls) used to demo HITL approval, tracing, evaluation, deployment (weather 'search' stub, send_email, Tavily).",
    1, "yes:llm", "yes:react", "no", "yes", "whether/how many tool calls (e.g. SF vs other city stub; email sent or not)",
    "interrupts.mdx:770-777 (should_continue); evaluate-graph.mdx:48-57; libs/cli/examples/graphs/agent.py:30-38, 69",
    "tier=B; cat=a+b; CLI agent also selects model from runtime context (agent.py:43-46)")
row("B-agent-as-node", "docs",
    D+"src/oss/langgraph/streaming.mdx:1287-1338; "+D+"src/oss/langchain/multi-agent/custom-workflow.mdx:54-104; "+D+"src/oss/langgraph/use-subgraphs.mdx:1016-1055,1175-1209",
    "Prebuilt create_agent embedded as a single StateGraph node.",
    1, "yes:llm", "yes:react", "no", "yes", "tool-loop length inside the agent", "streaming.mdx:1293; custom-workflow.mdx:58-62; use-subgraphs.mdx:1019-1025",
    "tier=B; cat=a+b")
row("B-two-step-chain", "docs",
    D+"src/langsmith/human-in-the-loop-time-travel.mdx:19-57; "+D+"src/code-samples/langchain/nostream-tag.py; "+D+"src/code-samples/langchain/nostream-tag.ts; "+D+"src/oss/langgraph/use-graph-api.mdx:1543-1629",
    "Straight two-node chains (topic->joke, answer->internal notes, model->DB query with retry policy).",
    2, "no", "no", "no", "no", "nothing from control flow", "human-in-the-loop-time-travel.mdx:34-45; nostream-tag.py:23-43; use-graph-api.mdx:1554-1574",
    "tier=B; cat=d; RetryPolicy retries are on exceptions, not content")
row("B-static-parallel", "docs", D+"src/oss/langgraph/streaming.mdx:679-786",
    "Two independent LLM nodes (joke, poem) fanned out statically from START.",
    2, "no", "no", "static", "no", "nothing from control flow", "streaming.mdx:693-716",
    "tier=B; cat=d")
row("B-summarize-on-length", "docs", D+"src/oss/langgraph/add-memory.mdx:2478-2527 (Python, langmem SummarizationNode); 2549-2663 (JS, messages.length > 6)",
    "Chat graph that summarizes history when it exceeds a token/message threshold.",
    2, "len", "no", "no", "partial", "whether history exceeded the threshold (conversation length)", "add-memory.mdx:2498-2504 (max_tokens_before_summary=256), 2598-2605 (JS shouldContinue)",
    "tier=B; cat=d* (length-dependent, not semantic)")
row("B-input-list-parallel", "docs", D+"src/oss/langgraph/use-functional-api.mdx:227-296",
    "Functional API: one LLM task per user-supplied topic, run in parallel, joined.",
    1, "no", "no", "yes:input-list", "partial", "number of topics supplied by the user", "use-functional-api.mdx:248-253",
    "tier=B; cat=c")

# ------------------------------------------------------------------ Prompt Flow (Tier A)
F = PF+"examples/flows/"
row("pf-conditional-switch", "promptflow", F+"standard/conditional-flow-for-switch/",
    "Mall-app query intent: LLM classifies into order_search/product_info/product_recommendation -> class_check (substring match) -> one activated python branch (stub strings) -> generate_response.",
    1, "yes:llm", "no", "no", "yes",
    "query intent: call count constant (1) but classifier output tokens and final response length differ per class",
    "flow.dag.yaml:11-21 (classify_with_llm, max_tokens 128), 36-38, 46-48, 56-58 (activate when/is); class_check.py:6-8",
    "tier=A; cat=a; branches are deterministic python stubs")
row("pf-conditional-if-else", "promptflow", F+"standard/conditional-flow-for-if-else/",
    "Content-safety gate placeholder: content_safety_check (random.choice) activates llm_result (placeholder python) or default_result.",
    0, "rand", "no", "no", "no",
    "as implemented nothing (random); intended design leaks whether input was flagged unsafe",
    "flow.dag.yaml:25-37 (activate); content_safety_check.py:8 (random.choice); llm_result.py:6 ('You can use an LLM node to replace this tool')",
    "tier=A; cat=d as implemented (would be a if the placeholders were replaced as the comments suggest)")
row("pf-promptflow-copilot", "promptflow", F+"chat/promptflow-copilot/",
    "Docs copilot: rewrite question with history (LLM) -> relevance score 0-10 (LLM, max_tokens=1) -> if score=='0' bypass index lookup and feed a refusal prompt, else retrieve top-4 and answer with context (LLM).",
    3, "yes:llm", "no", "no", "yes",
    "whether the question is on-topic for promptflow (final call input tokens: retrieved context vs short refusal prompt; fixed refusal output)",
    "flow.dag.yaml:43-45 (activate is false), 94 (max_tokens: 1), 102-109, 117-126; check_relevance_score.py:6; select_prompt.py:6-9",
    "tier=A; cat=a")
row("pf-question-simulation", "promptflow", F+"standard/question-simulation/",
    "Simulated-user question generation: LLM judges whether conversation should stop -> if continue, render human prompt and call LLM to produce next questions.",
    2, "yes:llm", "no", "no", "yes",
    "whether the conversation was judged complete (1 vs 2 LLM calls)",
    "flow.dag.yaml:16-32, 48-50 (activate), 52-65; if_continue.py:6; flow_output.py:6",
    "tier=A; cat=a; call_llm_chat bypassed when its only node dependency is bypassed (promptflow-core _dag_manager.py:133-144)")
row("pf-autonomous-agent", "promptflow", F+"standard/autonomous-agent/",
    "AutoGPT-style agent inside one python node: function-calling LLM loop with wiki search + python REPL until it calls 'finish'.",
    1, "yes:llm", "yes:react", "no", "yes",
    "number of agent steps / tools used for the goal",
    "autogpt_class.py:103 (while True), 106 (function_call check), 121-124 (finish), 125-140 (tool execution)",
    "tier=A; cat=a+b; unbounded")
row("pf-generate-test-data", "promptflow", PF+"examples/tutorials/generate-test-data/example_flow/",
    "Test-data generation chain with validation gates: score text chunk -> generate question -> validate question -> generate answer -> validate answer; each step short-circuits when the previous gate fails.",
    5, "yes:llm", "no", "no", "yes",
    "whether the input text chunk / generated question / answer passed each LLM validation (1-5 LLM calls)",
    "validate_text_chunk.py:45; generate_question.py:35; validate_question.py:37, 53; generate_suggested_answer.py:35; validate_suggested_answer.py:36, 50",
    "tier=A; cat=a (gated chain implemented as early returns, not activate)")
row("pf-chat-with-pdf", "promptflow", F+"chat/chat-with-pdf/",
    "Chat with PDF: download+index -> rewrite question (LLM) -> FAISS top-5 -> QnA (LLM); token-limit truncation loops are deterministic.",
    2, "no", "no", "no", "no", "nothing from control flow", "flow.dag.yaml:31-79; chat_with_pdf/rewrite_question.py:15-23, find_context.py:21-30 (truncation loops, no LLM)",
    "tier=A; cat=d")
row("pf-chat-with-wikipedia", "promptflow", F+"chat/chat-with-wikipedia/",
    "Extract query (LLM) -> Wikipedia search/scrape -> augmented chat (LLM).",
    2, "no", "no", "no", "no", "nothing from control flow (retrieval size varies)", "flow.dag.yaml nodes extract_query_from_question .. augmented_chat",
    "tier=A; cat=d")
row("pf-web-classification", "promptflow", F+"standard/web-classification/; "+F+"standard/flow-with-additional-includes/; "+F+"standard/flow-with-symlinks/",
    "Fetch URL -> summarize (LLM, variants) -> few-shot classify (LLM) -> dict.",
    2, "no", "no", "no", "no", "nothing from control flow", "flow.dag.yaml (all three identical node lists)",
    "tier=A; cat=d; group_size=3 (three copies deduped)")
row("pf-gen-docstring", "promptflow", F+"standard/gen-docstring/",
    "Split code into function/class chunks -> one LLM docstring call per chunk (asyncio.gather) -> merge.",
    1, "no", "no", "yes:input-list", "partial",
    "number and size of functions/classes in the submitted code",
    "generate_docstring_tool.py:45-57 (token-limit splitting), 61-67 (one async_query per chunk)",
    "tier=A; cat=c (list derived deterministically from user code, not from an LLM)")
row("pf-maths-to-code", "promptflow", F+"standard/maths-to-code/",
    "Math word problem -> code generation (LLM) -> AST-based refine (no LLM) -> exec.",
    1, "no", "no", "no", "no", "nothing from control flow", "flow.dag.yaml:16-49; code_refine.py:33-47",
    "tier=A; cat=d")
row("pf-chat-with-functions", "promptflow", F+"chat/use_functions_with_chat_models/; "+PF+"examples/flex-flows/chat-with-functions/",
    "One function-calling LLM call -> run the requested weather function (if any) once.",
    1, "yes:llm", "no", "no", "yes",
    "whether a function was called (output tokens of the single call)",
    "use_functions_with_chat_models/run_function.py:30-40; flex-flows/chat-with-functions/flow.py:41-56",
    "tier=A; cat=a (branch affects only a python tool, no extra LLM call); DAG and flex versions deduped")
for _id,_p,_d,_ev in [
    ("pf-customer-intent-extraction", F+"standard/customer-intent-extraction/", "Customer info + history prompt -> one AzureChatOpenAI call (via LangChain) extracting intent.", "intent.py:27-36 (AzureChatOpenAI call); extract_intent_tool.py:10-17"),
    ("pf-named-entity-recognition", F+"standard/named-entity-recognition/", "NER via one LLM call -> python cleansing.", "flow.dag.yaml:16 (type: llm)"),
    ("pf-describe-image", F+"standard/describe-image/", "Flip image -> one vision LLM question.", "flow.dag.yaml:25 (type: custom_llm)"),
    ("pf-chat-with-image", F+"chat/chat-with-image/", "Chat with image input: one vision LLM call.", "flow.dag.yaml:21 (type: custom_llm)"),
    ("pf-chat-math-variant", F+"chat/chat-math-variant/", "Math chat with 3 prompt variants of one LLM node -> extract result.", "flow.dag.yaml:20 (use_variants), 34/49/64 (variant llm nodes)"),
    ("pf-simple-summarization", F+"integrations/continuous-monitoring-with-pipeline/flows/standard/simple-summarization/", "One summarization LLM node with 2 variants (monitoring pipeline sample).", "flow.dag.yaml:13 (use_variants), 20/34"),
    ("pf-llmlingua-gsm8k", F+"integrations/llmlingua-prompt-compression/gsm8k_example/", "LLMLingua prompt compression -> one LLM call -> answer check.", "flow.dag.yaml:52 (type: llm)"),
    ("pf-multi-intent-clu", F+"integrations/azure-ai-language/multi_intent_conversational_language_understanding/", "LLM rewrites multi-intent utterance -> Azure CLU service.", "flow.dag.yaml:16 (type: llm)"),
    ("pf-custom-llm-tool-showcase", PF+"examples/tools/use-cases/custom_llm_tool_showcase/", "One custom_llm tool node.", "flow.dag.yaml:15 (type: custom_llm)"),
]:
    row(_id, "promptflow", _p, _d, 1, "no", "no", "no", "no", "nothing from control flow", _ev, "tier=A; cat=d")
row("pf-chat-basic", "promptflow", F+"chat/chat-basic/; "+PF+"examples/flex-flows/chat-basic/; chat-minimal/; chat-stream/; chat-async-stream/",
    "Basic chat (one prompty/LLM call); flex versions truncate history by token count before the call.",
    1, "no", "no", "no", "no", "nothing from control flow", "flex-flows/chat-basic/flow.py:39-52",
    "tier=A; cat=d; group_size=5 (DAG + 4 flex variants deduped)")
row("pf-basic-hello", "promptflow", F+"standard/basic/; basic-with-connection/; basic-with-builtin-llm/; "+PF+"examples/flex-flows/basic/; "+F+"integrations/unify-ai/",
    "Hello-world 'write a simple program' prompt -> one LLM call.",
    1, "no", "no", "no", "no", "nothing", "flex-flows/basic/programmer.py:27-33",
    "tier=A; cat=d; group_size=5 (deduped)")
for _id,_p,_d,_n,_ev,_note in [
    ("pf-eval-groundedness", F+"evaluation/eval-groundedness/", "LLM-judge groundedness score -> parse -> aggregate.", 1, "flow.dag.yaml:248 (type: llm)", ""),
    ("pf-eval-perceived-intelligence", F+"evaluation/eval-perceived-intelligence/", "LLM-judge perceived-intelligence score -> parse -> aggregate.", 1, "flow.dag.yaml:247 (type: llm)", ""),
    ("pf-eval-summarization", F+"evaluation/eval-summarization/", "G-Eval: 4 fixed dimensions, each one python LLM call with n=20 samples.", 4, "geval.py:114-139 (client.chat.completions.create, n=20)", ""),
    ("pf-eval-code-quality", PF+"examples/flex-flows/eval-code-quality/; "+F+"integrations/unify-ai/eval_code_flow/", "Prompty LLM judge for code correctness/readability.", 1, "flex-flows/eval-code-quality/code_quality.py:36-40", "; 2 flows deduped (OpenAI vs Unify backend)"),
    ("pf-eval-criteria-langchain", PF+"examples/flex-flows/eval-criteria-with-langchain/", "LangChain criteria (conciseness) evaluator.", 1, "eval_conciseness.py:24-40 (LLM + load_evaluator)", ""),
]:
    row(_id, "promptflow", _p, _d, _n, "no", "no", "no", "no", "nothing from control flow", _ev, "tier=A(eval); cat=d"+_note)
for _id,_p,_n,_ev in [
    ("pf-eval-qna-non-rag", F+"evaluation/eval-qna-non-rag/", 5, "validate_input.py:16-26; flow.dag.yaml activate at 67,106,131,155,167,191,222,235,247"),
    ("pf-eval-qna-rag-metrics", F+"evaluation/eval-qna-rag-metrics/", 3, "flow.dag.yaml activate at 438,462,487"),
    ("pf-eval-single-turn-metrics", F+"evaluation/eval-single-turn-metrics/", 8, "flow.dag.yaml activate at 87,108,130,151,173,184,206,227,238,251,264,277,299,311"),
]:
    row(_id, "promptflow", _p, "Metric-suite evaluation: select_metrics (config string) + validate_input (required fields non-empty) activate per-metric LLM judges.", _n, "cfg", "no", "no", "partial",
        "which metrics were requested and which input fields were non-empty (number of judge calls)", _ev, "tier=A(eval); cat=d (activation depends on config / field presence, not semantics)")
row("pf-eval-multi-turn-metrics", "promptflow", F+"evaluation/eval-multi-turn-metrics/",
    "Multi-turn metric suite: config/presence activation of 3 LLM judges + grounding python node calling the LLM once per chat turn.",
    4, "cfg", "no", "yes:input-list", "partial",
    "requested metrics; number of turns in the evaluated chat history", "flow.dag.yaml activate at 110,130,150,160,174; grounding.py:15-40 (one LLM call per turn)",
    "tier=A(eval); cat=c")
row("pf-eval-checklist", "promptflow", PF+"examples/flex-flows/eval-checklist/",
    "Check an answer against a dict of statements: one LLM judge call per statement.",
    1, "no", "no", "yes:input-list", "partial",
    "number of checklist statements", "check_list.py:41-45",
    "tier=A(eval); cat=c")

with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id","source","paths","description","llm_call_sites","branching","loop","fanout","decision_on_user_content","observer_inference","evidence_lines","notes"])
    w.writeheader()
    for r in R: w.writerow(r)

# ---------------- stats
def feats(r):
    a = r["branching"].startswith("yes")
    b = r["loop"].startswith("yes")
    c = r["fanout"].startswith("yes")
    return a, b, c
def tier(r):
    n = r["notes"]
    return "B" if n.startswith("tier=B") else ("A-eval" if n.startswith("tier=A(eval)") else "A")
def summarize(rows, label):
    n = len(rows)
    A = sum(feats(r)[0] for r in rows); B = sum(feats(r)[1] for r in rows); C = sum(feats(r)[2] for r in rows)
    anyc = sum(any(feats(r)) for r in rows)
    usr = sum(r["decision_on_user_content"] == "yes" for r in rows if any(feats(r)))
    usrp = sum(r["decision_on_user_content"] == "partial" for r in rows if any(feats(r)))
    print(f"{label}: n={n} any-content-dependent={anyc} ({100*anyc/n:.0f}%) | a(branch)={A} ({100*A/n:.0f}%) b(loop)={B} ({100*B/n:.0f}%) c(fanout)={C} ({100*C/n:.0f}%) d(none)={n-anyc} ({100*(n-anyc)/n:.0f}%) | of content-dependent, decision on user content yes={usr} partial={usrp}")
    combo = collections.Counter("+".join(x for x, f in zip("abc", feats(r)) if f) or "d" for r in rows)
    print("   combos:", dict(combo))
src = lambda s: [r for r in R if s in r["source"]]
TA = [r for r in R if tier(r) == "A"]; TAe = [r for r in R if tier(r) == "A-eval"]; TB = [r for r in R if tier(r) == "B"]
summarize(R, "ALL rows")
summarize(TA + TAe, "Tier A (incl. eval flows)")
summarize(TA, "Tier A application workflows (excl. PF eval flows)")
summarize(TB, "Tier B API-demo classes")
for s in ["langgraph", "docs", "promptflow"]:
    summarize([r for r in TA + TAe if s in r["source"]], f"Tier A source contains '{s}'")
summarize([r for r in TA if "promptflow" not in r["source"]], "Tier A LangGraph/LangChain (both repos)")
summarize([r for r in TA if r["source"] == "promptflow"], "Tier A Prompt Flow apps (excl eval)")
print("rows:", len(R), "tierA:", len(TA), "tierA-eval:", len(TAe), "tierB:", len(TB))
