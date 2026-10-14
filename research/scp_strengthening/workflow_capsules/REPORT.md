# Bounded source-slice workflow capsules

## Feasibility and claim

Docker could not provide isolation here: the Docker CLI was installed, but no daemon was running. The macOS host has `/usr/bin/sandbox-exec`, and a Seatbelt profile successfully ran both capsules against the pinned LangGraph 1.2.14 runtime with network and writes denied. The runner performs a separate preflight first; source execution is skipped unless network, writes, fork, and an unlisted user file are all confirmed denied.

This adds a bounded execution capsule alongside SCP's AST path. It compiles and executes a small, source-hash-pinned set of exact original statements and callables in one explicit `ModuleType` namespace, then runs the source's actual compiled LangGraph path against a deterministic finite oracle. It does **not** admit a whole file, translate arbitrary Python, establish arbitrary-input correctness, or claim provider/API conformance. The guarantee is conditional on the enumerated finite input and response supports, the pinned runtime, the mocks, the call horizons, and the declared observation projection.

The capsule records each complete declared schedule twice and stores both observations. It retains graph input/config/stream-mode envelopes, model and retriever request envelopes, returned message/document projections, node updates, ordered LangGraph state snapshots, graph completion or error, and source logger calls. A separate standard-library verifier reads the JSON artifacts and pinned source bytes, but never executes workflow source. It checks fixed source, worker, mock, finite-support, declaration, and law hashes; source-span selection; every schedule weight; complete per-capsule replay field sets; request/response/status/horizon consistency; and exact rational laws before writing a certificate. Its strict JSON reader rejects duplicate keys, malformed UTF-8, surrogates, noncanonical or non-finite numbers, and inputs exceeding fixed byte, depth, item, string, integer, rational, or arithmetic limits. The certificate is a replay of the hash-bound recorded finite model; it does not independently establish that the original source run occurred as represented. A failed CLI verification removes that capsule's previous certificate, and successful certificate writes are atomic.

## Cases and results

Both sources are MIT-licensed snapshots in the existing development corpus. They are independent repositories selected for a compact, sequential LangGraph path: one synchronous model node and one three-node async knowledge-base path. The second case exercises real async graph and RunnableSequence behavior, including the nested `create_system_message` function inside `wrap_model`; its captured prompt is checked against both the document and no-document state. No held-out files were read.

| Original workflow | Source identity | Finite schedules | Complete trace classes | Message-content classes | Final-answer classes | Graph status law |
|---|---|---:|---:|---:|---:|---|
| Dili one-node LangGraph | [`LangGraphLLM.py`](https://github.com/didilili/ai-agents-from-zero/blob/9de20be80dad6d410268ae75f75cf94c355dd364/%E6%A1%88%E4%BE%8B%E4%B8%8E%E6%BA%90%E7%A0%81-3-LangGraph%E6%A1%86%E6%9E%B6/01-helloworld/LangGraphLLM.py), commit `9de20be80dad6d410268ae75f75cf94c355dd364`, SHA256 `b35741309de653d79e2cb403ebc5ddfa6b74383dd22f2e0d0142a1359225818b` | 2 inputs × 3 responses = 6, each `1/6` | 6 | 4 | 2 | complete `2/3`; provider error `1/3` |
| JoshuaC215 knowledge-base agent | [`knowledge_base_agent.py`](https://github.com/JoshuaC215/agent-service-toolkit/blob/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py), commit `88ebfa1fadd1a207aa92115635abf7ed20d66a88`, SHA256 `6a96b47a58e855444fa410bef6e077220f578f188476a605aabeb88d88bf0ccc` | 2 inputs × 2 retrieval outcomes × 3 responses = 12, each `1/12` | 12 | 4 | 2 | complete `2/3`; provider error `1/3` |

The finite response support includes same-text returned `AIMessage` values with distinct IDs, `finish_reason` (`stop` or `length`), and usage metadata, plus a declared `RuntimeError`. The exact law makes each return, stop reason, and raised status visible. The Joshua support additionally includes one returned `Document` and one retrieval exception; that original catch-all branch logs the error, keeps an empty retrieval state, selects the no-documents prompt, and continues to the model. The model-error schedule visibly stops before a terminal graph state.

The exact full-state equivalence is canonical JSON equality over each capsule's `trace_projection`. LangChain messages use the runtime's `message_to_dict` representation, retaining their message type and available `id`, `status`, `additional_kwargs`, `response_metadata`, and `usage_metadata`. Joshua retrieval responses retain a declared `Document` projection (`type`, `id`, `page_content`, and `metadata`); graph states retain the complete JSON-projectable values and message history returned by LangGraph. Request envelopes retain ordered messages, method, stop value, and kwargs. Equality excludes Python object identity, timestamps, opaque callback/run IDs, OS scheduling, and real provider wire behavior. Unsupported values fail projection instead of being stringified.

## Lossy-observer controls

The message-content projection deliberately keeps only ordered message content strings. On Joshua's fixed finite schedules, it merges worlds whose retrieval response status is `returned` versus `raised`; those traces have different retriever responses, logger events, state, and model prompt envelopes. The final-answer-only projection also merges distinct user histories. The exported certificates list the exact world IDs, rational weights, content hashes, complete trace hashes, and status/history values in those groups.

The Dili case separately shows that content-only equality merges `stop` and `length` responses with the same answer text even though full `AIMessage` IDs, finish reasons, and usage metadata differ. Its final-answer-only projection further erases which of the two inputs was run. These are explicit negative controls: a reduced observer can conceal finite, observed differences. They do not imply that every helper adapter or every source program has those behaviors.

## Execution boundary and limits

The workers compile exact `ast.get_source_segment` substrings without rewriting or pretty-printing them. Each selected callable executes with `__globals__` identical to its synthetic module namespace; free-variable closures on selected top-level callables are rejected. Joshua's original nested prompt closure is created by the unchanged compiled `wrap_model` body and its behavior is observed through the exact model request: the correct human history and either retrieved document or no-document prompt must be present. The verifier independently re-hashes the full original file and each declared source span, and binds the ordered span manifest, mock contract, and worker bytes.

External premises are explicit and hash-bound. Dili's `llm` global is replaced by a finite `.invoke(messages)` oracle. Joshua's `AmazonKnowledgeBasesRetriever`, `get_model`, settings fixture, and logger are local doubles; its async `BaseChatModel` test double uses actual LangChain Core's `.ainvoke` path. Both cases use the actual pinned LangGraph runtime; Joshua also uses actual LangChain Core RunnableSequence, messages, and Document classes. `langchain_aws` and the full `langchain` package are unavailable, so no AWS adapter, provider, API key, or paid call is involved. The child receives only fixed Python flags, a nonsecret fixture `AWS_KB_ID`, and the worker hash; it receives no `HOME`, `.env`, provider credentials, or application API configuration.

The Seatbelt profile denies network access, writes, process inspection/fork, Mach lookup, unlisted user files, temporary paths, and volumes; only the pinned source and runtime paths are opened under `/Users`. The preflight passed all four active probes for both runs. One host limitation remains: `/opt` reads could not be denied without preventing the Homebrew Python launcher from starting, so that tree remains readable. This is a constrained execution of inspected, immutable development snapshots, not a general sandbox for arbitrary source. Both graph paths have explicit one-call horizons and fixed recursion limits; additional calls, unexpected stream modes/nodes, changed API arguments, unsupported projections, unmodeled errors, or nondeterministic repeated traces reject the capsule.

The prior `StreamLLMTokens.py` incident remains helper-only evidence and is not counted as a workflow case here. Its `str` annotation did not match its `AIMessage` runtime result, and its factory/main/streaming harness was outside that helper projection. These two independently developed LangGraph cases are new capsule evidence, not a repair or re-evaluation of that incident.

## Relation to prior work

Finite exploration and behavioral comparison are established ideas. Bounded model checking checks modeled executions to a declared bound; DART combines interface extraction, test-driver generation, and dynamic input generation; McKeeman's differential testing compares multiple implementations over generated cases. This capsule is related to those bounded/dynamic testing traditions, but it does not claim a new model-checking or differential-testing algorithm. It uses a manually declared finite schedule, executes exact original source slices with explicit mocks, and independently replays a rational observer law from the exported trace model. The practical contribution here is a source-slice execution lane with explicit trust, stop/error, projection, and isolation boundaries alongside SCP's current helper/AST path.

- E. Clarke, A. Biere, R. Raimi, and Y. Zhu, [“Bounded Model Checking Using Satisfiability Solving” (2001)](https://fmv.jku.at/papers/ClarkeBiereRaimiZhu-FMSD-19-1-2001.pdf).
- P. Godefroid, N. Klarlund, and K. Sen, [“DART: Directed Automated Random Testing,” PLDI 2005](https://osl.cs.illinois.edu/publications/conf/pldi/GodefroidKS05.html).
- W. M. McKeeman, [“Differential Testing for Software,” Digital Technical Journal 10(1), 1998](https://vmssoftware.com/docs/dtj-v10-01-1998.pdf).

## Reproduction and artifacts

From the repository root, run the source capsules first, then independently verify the two JSON artifacts:

```sh
python3 -B integrations/workflow_capsules/run_capsule.py all
python3 -B integrations/workflow_capsules/verify_finite_trace.py \
  research/scp_strengthening/workflow_capsules/didilili-langgraphllm-one-node-finite-oracle-v1.json \
  research/scp_strengthening/workflow_capsules/joshuac215-kb-agent-sequential-async-finite-oracle-v1.json
```

The verifier writes one `*-certificate.json` beside each artifact. The captured full traces and schedules are in [the Dili trace artifact](didilili-langgraphllm-one-node-finite-oracle-v1.json) and [the Joshua trace artifact](joshuac215-kb-agent-sequential-async-finite-oracle-v1.json); independent results are in [the Dili certificate](didilili-langgraphllm-one-node-finite-oracle-v1-certificate.json) and [the Joshua certificate](joshuac215-kb-agent-sequential-async-finite-oracle-v1-certificate.json). Both certificates currently report `PASS_CONDITIONAL_FINITE_TRACE_CERTIFICATE`.

The bounded parser, runner protocol, source boundary, and verifier tamper controls can be checked without executing workflow source:

```sh
python3 -B -m unittest discover -s integrations/workflow_capsules -p 'test_finite_trace_hardening.py' -v
```
