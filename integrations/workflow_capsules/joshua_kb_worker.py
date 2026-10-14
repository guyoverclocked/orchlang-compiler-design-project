#!/usr/bin/env python3
"""Bounded async capsule for a source-pinned JoshuaC215 KB workflow slice.

The caller must launch this worker inside run_capsule.py's macOS Seatbelt
profile. It compiles exact source segments only; it never imports the source
module or the unavailable AWS/community provider integrations.
"""
from __future__ import annotations

import ast
import asyncio
from collections import defaultdict
from fractions import Fraction
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, cast

from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, message_to_dict
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableConfig, RunnableLambda, RunnableSerializable
from langchain_core.runnables.base import RunnableSequence
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from pydantic import PrivateAttr


SOURCE_RELATIVE = Path(
    "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/"
    "88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py"
)
SOURCE_SHA256 = "6a96b47a58e855444fa410bef6e077220f578f188476a605aabeb88d88bf0ccc"
SOURCE_BYTES = 6641
SOURCE_COMMIT = "88ebfa1fadd1a207aa92115635abf7ed20d66a88"
SOURCE_REPOSITORY = "JoshuaC215/agent-service-toolkit"
SOURCE_URL = (
    "https://github.com/JoshuaC215/agent-service-toolkit/blob/"
    "88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py"
)
GRAPH_RECURSION_LIMIT = 12
MODEL_HORIZON = 1
RETRIEVER_HORIZON = 1


class CapsuleError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _worker_definition_hash() -> str:
    actual = _sha(Path(__file__).read_bytes())
    expected = os.environ.get("CAPSULE_WORKER_SHA256")
    if expected is None or expected != actual:
        raise CapsuleError("worker bytes differ from the host-runner manifest")
    return actual


def _assert_module_bindings(namespace: dict[str, object], names: list[str]) -> dict[str, object]:
    """Reject extracted callables that depend on a discarded closure."""
    observations: dict[str, object] = {}
    for name in names:
        value = namespace.get(name)
        if not callable(value) or getattr(value, "__globals__", None) is not namespace:
            raise CapsuleError(f"{name} did not retain the reviewed module-global namespace")
        code = getattr(value, "__code__", None)
        if code is None or code.co_freevars or getattr(value, "__closure__", None):
            raise CapsuleError(f"{name} depends on an unsupported lexical closure")
        observations[name] = {
            "module_name": getattr(value, "__module__", None),
            "globals_identity_matches_namespace": getattr(value, "__globals__", None) is namespace,
            "free_variables": list(code.co_freevars),
        }
    return observations


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _plain(value: object) -> object:
    if isinstance(value, BaseMessage):
        return {"$message": _plain(message_to_dict(value))}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CapsuleError("non-finite float is outside declared projection")
        return value
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CapsuleError("non-string mapping key is outside declared projection")
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(child) for child in value]
    raise CapsuleError(f"unsupported returned value type {type(value).__qualname__}")


def _segment(source: str, node: ast.AST, label: str) -> str:
    text = ast.get_source_segment(source, node)
    if text is None:
        raise CapsuleError(f"missing exact source segment for {label}")
    return text


def _node_signature(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _select_graph(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    expected: list[tuple[str, str]] = [
        ("graph_init", "agent = StateGraph(AgentState)"),
        ("node_retrieve", "agent.add_node('retrieve_documents', retrieve_documents)"),
        ("node_prepare", "agent.add_node('prepare_augmented_prompt', prepare_augmented_prompt)"),
        ("node_model", "agent.add_node('model', acall_model)"),
        ("entry", "agent.set_entry_point('retrieve_documents')"),
        ("edge_retrieve_prepare", "agent.add_edge('retrieve_documents', 'prepare_augmented_prompt')"),
        ("edge_prepare_model", "agent.add_edge('prepare_augmented_prompt', 'model')"),
        ("edge_model_end", "agent.add_edge('model', END)"),
        ("graph_compile", "kb_agent = agent.compile()"),
    ]
    wanted = {label: ast.parse(line).body[0] for label, line in expected}
    found: dict[str, ast.AST] = {}
    for statement in tree.body:
        for label, pattern in wanted.items():
            if _node_signature(statement) == _node_signature(pattern):
                if label in found:
                    raise CapsuleError(f"duplicate graph statement {label}")
                found[label] = statement
    missing = sorted(set(wanted) - set(found))
    if missing:
        raise CapsuleError(f"graph path is incomplete; missing {missing}")
    ordered = [(label, found[label]) for label, _ in expected]
    if [n.lineno for _, n in ordered] != sorted(n.lineno for _, n in ordered):
        raise CapsuleError("graph wiring order changed")
    return ordered


def _function(tree: ast.Module, name: str, is_async: bool = False) -> ast.AST:
    found = [
        n for n in tree.body
        if getattr(n, "name", None) == name
        and isinstance(n, ast.AsyncFunctionDef if is_async else ast.FunctionDef)
    ]
    if len(found) != 1:
        raise CapsuleError(f"expected one {'async ' if is_async else ''}function {name}")
    return found[0]


def _compile(namespace: dict[str, object], source: str, node: ast.AST, label: str) -> dict[str, object]:
    segment = _segment(source, node, label)
    exec(compile(segment, f"{SOURCE_RELATIVE}:{node.lineno}", "exec"), namespace)
    return {"label": label, "source_lines": [node.lineno, node.end_lineno], "segment_sha256": _sha(segment.encode())}


INPUTS = [
    {"input_id": "query_alpha", "query": "Which release introduced the cache?", "weight": "1/2"},
    {"input_id": "query_beta", "query": "How is cache invalidation handled?", "weight": "1/2"},
]

RETRIEVAL_SUPPORT = [
    {
        "outcome_id": "document_found",
        "weight": "1/2",
        "kind": "success",
        "document": {
            "id": "fixture-doc-alpha",
            "source": "fixture://release-notes",
            "title": "Release notes",
            "content": "The cache was introduced in release 2.4.",
            "score": 0.875,
        },
    },
    {
        "outcome_id": "retrieval_exception",
        "weight": "1/2",
        "kind": "exception",
        "exception_type": "RuntimeError",
        "exception_message": "finite retrieval fixture unavailable",
    },
]

MODEL_SUPPORT = [
    {
        "response_id": "model_stop",
        "weight": "1/3",
        "kind": "returned",
        "content": "The answer is available in this fixture.",
        "id": "fixture-answer-stop",
        "response_metadata": {"finish_reason": "stop", "model_name": "finite-kb-model-v1"},
        "usage_metadata": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27},
    },
    {
        "response_id": "model_length",
        "weight": "1/3",
        "kind": "returned",
        "content": "The answer is available in this fixture.",
        "id": "fixture-answer-length",
        "response_metadata": {"finish_reason": "length", "model_name": "finite-kb-model-v1"},
        "usage_metadata": {"input_tokens": 20, "output_tokens": 12, "total_tokens": 32},
    },
    {
        "response_id": "model_exception",
        "weight": "1/3",
        "kind": "exception",
        "exception_type": "RuntimeError",
        "exception_message": "finite model fixture unavailable",
    },
]


class MemoryLogger:
    def __init__(self, events: list[dict[str, object]]):
        self.events = events

    def info(self, message: object, *args: object, **kwargs: object) -> None:
        if args or kwargs:
            raise CapsuleError("logger.info used unsupported args/kwargs")
        self.events.append({"kind": "source_log", "level": "info", "message": str(message)})

    def error(self, message: object, *args: object, **kwargs: object) -> None:
        if args or kwargs:
            raise CapsuleError("logger.error used unsupported args/kwargs")
        self.events.append({"kind": "source_log", "level": "error", "message": str(message)})


class FiniteRetriever:
    """Explicit mock of AmazonKnowledgeBasesRetriever.ainvoke(query)."""

    def __init__(self, outcome: dict[str, object], events: list[dict[str, object]]):
        self.outcome = outcome
        self.events = events
        self.call_count = 0

    async def ainvoke(self, query: object, *args: object, **kwargs: object) -> list[Document]:
        self.call_count += 1
        if self.call_count != 1 or args or kwargs or not isinstance(query, str):
            self.events.append({"kind": "frontier_failure", "boundary": "retriever", "query": _plain(query)})
            raise CapsuleError("retriever request exceeded declared query/kwargs/horizon support")
        envelope = {"method": "ainvoke", "args": [query], "kwargs": {}}
        self.events.append({"kind": "retrieval_request", "envelope": envelope})
        if self.outcome["kind"] == "exception":
            record = {
                "kind": "retrieval_response",
                "status": "raised",
                "outcome_id": self.outcome["outcome_id"],
                "exception_type": self.outcome["exception_type"],
                "exception_message": self.outcome["exception_message"],
            }
            self.events.append(record)
            raise RuntimeError(str(self.outcome["exception_message"]))
        doc = self.outcome["document"]
        if not isinstance(doc, dict):
            raise CapsuleError("declared document response is malformed")
        document = Document(
            page_content=str(doc["content"]),
            metadata={
                "id": str(doc["id"]),
                "source": str(doc["source"]),
                "title": str(doc["title"]),
                "score": float(doc["score"]),
            },
        )
        self.events.append(
            {
                "kind": "retrieval_response",
                "status": "returned",
                "outcome_id": self.outcome["outcome_id"],
                "documents": [
                    {
                        "$type": f"{type(document).__module__}.{type(document).__qualname__}",
                        "id": document.id,
                        "page_content": document.page_content,
                        "metadata": _plain(document.metadata),
                    }
                ],
            }
        )
        return [document]


class FiniteRetrieverFactory:
    def __init__(self, outcome: dict[str, object], events: list[dict[str, object]]):
        self.outcome = outcome
        self.events = events
        self.calls: list[dict[str, object]] = []
        self.instances: list[FiniteRetriever] = []

    def __call__(self, *args: object, **kwargs: object) -> FiniteRetriever:
        if args or set(kwargs) != {"knowledge_base_id", "retrieval_config"}:
            raise CapsuleError("AmazonKnowledgeBasesRetriever constructor boundary changed")
        if kwargs["knowledge_base_id"] != "finite-kb-fixture":
            raise CapsuleError("unexpected knowledge-base ID")
        expected_config = {"vectorSearchConfiguration": {"numberOfResults": 3}}
        if kwargs["retrieval_config"] != expected_config:
            raise CapsuleError("source retriever request config changed")
        record = {
            "knowledge_base_id": kwargs["knowledge_base_id"],
            "retrieval_config": _plain(kwargs["retrieval_config"]),
        }
        self.calls.append(record)
        self.events.append({"kind": "retriever_construct", "request": record})
        instance = FiniteRetriever(self.outcome, self.events)
        self.instances.append(instance)
        return instance


class FiniteChatModel(BaseChatModel):
    """A sequential async provider-boundary oracle, never a real provider."""

    response: dict[str, object]
    call_count: int = 0
    _event_journal: list[dict[str, object]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "workflow-capsule-finite-oracle"

    @property
    def _identifying_params(self) -> dict[str, object]:
        return {"model": "finite-kb-model-v1"}

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object) -> ChatResult:
        raise CapsuleError("sync generation is outside the declared async-only capsule")

    async def _agenerate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object) -> ChatResult:
        self.call_count += 1
        if self.call_count != 1:
            self._event_journal.append({"kind": "frontier_failure", "boundary": "model", "reason": "call horizon exceeded"})
            raise CapsuleError("model call horizon exceeded")
        if kwargs:
            self._event_journal.append({"kind": "frontier_failure", "boundary": "model", "reason": "unsupported kwargs", "kwargs": _plain(kwargs)})
            raise CapsuleError("model request used unsupported kwargs")
        if not isinstance(messages, list) or not all(isinstance(message, BaseMessage) for message in messages):
            raise CapsuleError("model request is outside list[BaseMessage] support")
        envelope = {
            "method": "BaseChatModel._agenerate",
            "messages": _plain(messages),
            "stop": _plain(stop),
            "kwargs": {},
        }
        self._event_journal.append({"kind": "model_request", "envelope": envelope})
        if self.response["kind"] == "exception":
            self._event_journal.append(
                {
                    "kind": "model_response",
                    "status": "raised",
                    "response_id": self.response["response_id"],
                    "exception_type": self.response["exception_type"],
                    "exception_message": self.response["exception_message"],
                }
            )
            raise RuntimeError(str(self.response["exception_message"]))
        response = AIMessage(
            content=str(self.response["content"]),
            id=str(self.response["id"]),
            response_metadata=dict(self.response["response_metadata"]),
            usage_metadata=dict(self.response["usage_metadata"]),
        )
        projected = _plain(response)
        self._event_journal.append(
            {
                "kind": "model_response",
                "status": "returned",
                "response_id": self.response["response_id"],
                "message": projected,
                "finish_reason": self.response["response_metadata"]["finish_reason"],
                "usage": self.response["usage_metadata"],
            }
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=response,
                    generation_info={"finish_reason": self.response["response_metadata"]["finish_reason"]},
                )
            ],
            llm_output={"model_name": "finite-kb-model-v1"},
        )


def _fraction(value: str) -> Fraction:
    result = Fraction(value)
    if result <= 0:
        raise CapsuleError("finite-support weights must be positive")
    return result


def _hash(value: object) -> str:
    return _sha(_canonical(value))


async def _run_world(
    source: str,
    selected: list[tuple[str, ast.AST]],
    input_case: dict[str, str],
    retrieval_case: dict[str, object],
    model_case: dict[str, object],
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    retriever_factory = FiniteRetrieverFactory(retrieval_case, events)
    model = FiniteChatModel(response=model_case)
    model._event_journal = events
    if model._event_journal is not events:
        raise CapsuleError("model event journal did not retain shared identity")
    logger = MemoryLogger(events)

    # os.environ is real but sanitized by the parent; this single nonsecret
    # fixture variable is the only application environment value supplied.
    expected_environment = {
        "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
        "AWS_KB_ID", "CAPSULE_WORKER_SHA256",
    }
    actual_environment = set(os.environ)
    synthesized_locale = actual_environment - expected_environment
    if synthesized_locale not in (set(), {"LC_CTYPE"}) or actual_environment < expected_environment:
        raise CapsuleError("child environment was not reduced to the declared fixture variables")
    if "LC_CTYPE" in synthesized_locale and os.environ["LC_CTYPE"] != "C.UTF-8":
        raise CapsuleError("unexpected interpreter-synthesized locale value")

    source_module = ModuleType(
        f"_capsule_joshua_{input_case['input_id']}_{retrieval_case['outcome_id']}_{model_case['response_id']}"
    )
    sys.modules[source_module.__name__] = source_module
    def resolve_model(model_id: object) -> FiniteChatModel:
        events.append({"kind": "model_factory", "request": {"model_id": _plain(model_id)}})
        if model_id != "finite-kb-model-v1":
            raise CapsuleError(f"unknown model id {model_id!r}")
        return model

    namespace: dict[str, object] = source_module.__dict__
    namespace.update({
        "__builtins__": __builtins__,
        "Any": Any,
        "cast": cast,
        "MessagesState": MessagesState,
        "RemainingSteps": RemainingSteps,
        "END": END,
        "StateGraph": StateGraph,
        "RunnableConfig": RunnableConfig,
        "RunnableLambda": RunnableLambda,
        "RunnableSerializable": RunnableSerializable,
        "RunnableSequence": RunnableSequence,
        "BaseChatModel": BaseChatModel,
        "AIMessage": AIMessage,
        "HumanMessage": HumanMessage,
        "SystemMessage": SystemMessage,
        "os": os,
        "AmazonKnowledgeBasesRetriever": retriever_factory,
        "logger": logger,
        "get_model": resolve_model,
        "settings": type("SettingsFixture", (), {"DEFAULT_MODEL": "finite-kb-model-v1"})(),
    })

    source_nodes: list[tuple[str, ast.AST]] = []
    tree = ast.parse(source, filename=str(SOURCE_RELATIVE))
    state_candidates = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AgentState"]
    if len(state_candidates) != 1:
        raise CapsuleError("expected one AgentState declaration")
    source_nodes.append(("AgentState", state_candidates[0]))
    for name, is_async in [
        ("get_kb_retriever", False),
        ("wrap_model", False),
        ("retrieve_documents", True),
        ("prepare_augmented_prompt", True),
        ("acall_model", True),
    ]:
        source_nodes.append((name, _function(tree, name, is_async)))
    source_nodes.extend(selected)
    snippets = [_compile(namespace, source, node, label) for label, node in source_nodes]
    callable_bindings = _assert_module_bindings(
        namespace,
        ["get_kb_retriever", "wrap_model", "retrieve_documents", "prepare_augmented_prompt", "acall_model"],
    )
    if getattr(namespace.get("AgentState"), "__module__", None) != source_module.__name__:
        raise CapsuleError("AgentState class was not compiled into its source-slice module")
    binding_observation: dict[str, object] = {
        "state_class_module_matches_namespace": True,
        "top_level_callables": callable_bindings,
    }

    graph = namespace.get("kb_agent")
    astream = getattr(graph, "astream", None)
    if not callable(astream):
        raise CapsuleError("source graph did not compile to actual LangGraph async stream")
    initial = {
        "messages": [
            HumanMessage(content=input_case["query"], id=f"{input_case['input_id']}-human")
        ]
    }
    graph_config = {
        "configurable": {"model": "finite-kb-model-v1"},
        "recursion_limit": GRAPH_RECURSION_LIMIT,
    }
    stream_modes = ["updates", "values"]
    events.append({
        "kind": "graph_start",
        "input": _plain(initial),
        "config": graph_config,
        "stream_mode": stream_modes,
    })
    terminal: object = None
    node_updates: list[dict[str, object]] = []
    values: list[object] = []
    completed = False
    error: dict[str, str] | None = None
    try:
        async for item in astream(
            initial,
            graph_config,
            stream_mode=stream_modes,
        ):
            if not isinstance(item, tuple) or len(item) != 2:
                raise CapsuleError("unsupported LangGraph async event shape")
            mode, chunk = item
            if mode == "values":
                projected = _plain(chunk)
                values.append(projected)
                terminal = projected
                events.append({"kind": "graph_state", "ordinal": len(values), "state": projected})
            elif mode == "updates":
                if not isinstance(chunk, dict):
                    raise CapsuleError("LangGraph async update is not a mapping")
                for node_name, update in chunk.items():
                    projected = _plain(update)
                    node_updates.append({"node": node_name, "update": projected})
                    events.append({"kind": "node_update", "node": node_name, "update": projected})
            else:
                events.append({"kind": "frontier_failure", "reason": f"unexpected stream mode {mode!r}"})
                raise CapsuleError(f"unexpected LangGraph stream mode {mode!r}")
        completed = True
        events.append({"kind": "graph_complete", "terminal": terminal})
    except Exception as exc:
        error = {"type": f"{type(exc).__module__}.{type(exc).__qualname__}", "message": str(exc)[:2000]}
        events.append({"kind": "graph_exception", **error})

    failures: list[str] = []
    expected_model_error = model_case["kind"] == "exception"
    if expected_model_error:
        if completed:
            failures.append("declared model exception unexpectedly completed the graph")
        if error is None or error.get("type") != "builtins.RuntimeError" or error.get("message") != model_case["exception_message"]:
            failures.append("graph error did not match declared deterministic model exception")
        if not any(event.get("kind") == "model_response" and event.get("status") == "raised" for event in events):
            failures.append("provider exception status was not recorded")
    else:
        if not completed:
            failures.append("async graph did not complete")
        if error is not None:
            failures.append("async graph raised")
    model_requests = [event for event in events if event.get("kind") == "model_request"]
    closure_observation: dict[str, object] = {
        "model_request_count": len(model_requests),
        "system_message_observed": False,
        "human_message_history_preserved": False,
        "retrieved_document_closure_observed": False,
        "no_documents_closure_observed": False,
    }
    if len(model_requests) == 1:
        envelope = model_requests[0].get("envelope")
        request_messages = envelope.get("messages") if isinstance(envelope, dict) else None
        if isinstance(request_messages, list) and len(request_messages) == 2:
            system_data = request_messages[0].get("$message", {}).get("data", {})
            human_data = request_messages[1].get("$message", {}).get("data", {})
            system_text = system_data.get("content", "") if isinstance(system_data, dict) else ""
            closure_observation["system_message_observed"] = isinstance(system_data, dict) and system_data.get("type") == "system"
            closure_observation["human_message_history_preserved"] = (
                isinstance(human_data, dict)
                and human_data.get("type") == "human"
                and human_data.get("content") == input_case["query"]
                and human_data.get("id") == f"{input_case['input_id']}-human"
            )
            if retrieval_case["kind"] == "success":
                document = retrieval_case["document"]
                closure_observation["retrieved_document_closure_observed"] = (
                    isinstance(system_text, str)
                    and "fixture://release-notes" in system_text
                    and "Release notes" in system_text
                    and str(document["content"]) in system_text
                )
            else:
                closure_observation["no_documents_closure_observed"] = (
                    isinstance(system_text, str)
                    and "No relevant documents were found" in system_text
                    and "fixture://release-notes" not in system_text
                )
        else:
            failures.append("source wrapper closure produced an unsupported model request shape")
    else:
        failures.append(f"expected one model request for lexical-binding observation, saw {len(model_requests)}")
    if not closure_observation["system_message_observed"] or not closure_observation["human_message_history_preserved"]:
        failures.append("source wrapper closure did not preserve system/query message bindings")
    if retrieval_case["kind"] == "success" and not closure_observation["retrieved_document_closure_observed"]:
        failures.append("source wrapper closure omitted the retrieved document state")
    if retrieval_case["kind"] == "exception" and not closure_observation["no_documents_closure_observed"]:
        failures.append("source wrapper closure did not take the declared no-documents branch")
    expected_nodes = ["retrieve_documents", "prepare_augmented_prompt"]
    if not expected_model_error:
        expected_nodes.append("model")
    observed_nodes = [str(item["node"]) for item in node_updates]
    if observed_nodes != expected_nodes:
        failures.append(f"observed node path {observed_nodes!r}, expected {expected_nodes!r}")
    expected_value_count = 3 if expected_model_error else 4
    if len(values) != expected_value_count:
        failures.append(f"observed {len(values)} value snapshots, expected {expected_value_count}")
    last_observed_state = terminal
    terminal_state = terminal if completed else None
    if not isinstance(last_observed_state, dict):
        failures.append("last graph state is outside JSON mapping projection")
    elif completed:
        messages = last_observed_state.get("messages")
        if not isinstance(messages, list) or len(messages) != 2:
            failures.append("terminal state did not retain human and model messages")
        elif messages[0].get("$message", {}).get("data", {}).get("id") != f"{input_case['input_id']}-human":
            failures.append("human message history was not preserved")
    else:
        messages = last_observed_state.get("messages")
        if not isinstance(messages, list) or len(messages) != 1:
            failures.append("modeled model error did not preserve input-only last state")
    if isinstance(last_observed_state, dict):
        messages = last_observed_state.get("messages")
        if isinstance(messages, list) and messages and messages[0].get("$message", {}).get("data", {}).get("id") != f"{input_case['input_id']}-human":
            failures.append("human message identity changed in observed state")
    retriever_calls = sum(instance.call_count for instance in retriever_factory.instances)
    if len(retriever_factory.calls) != 1 or retriever_calls != RETRIEVER_HORIZON:
        failures.append(f"retriever horizon mismatch: constructors={len(retriever_factory.calls)}, calls={retriever_calls}")
    if model.call_count != MODEL_HORIZON:
        failures.append(f"model horizon mismatch: calls={model.call_count}")
    if retrieval_case["kind"] == "exception":
        if not any(event.get("kind") == "source_log" and event.get("level") == "error" for event in events):
            failures.append("source did not observe the declared retriever exception branch")
        if isinstance(last_observed_state, dict) and (last_observed_state.get("retrieved_documents") != [] or "kb_documents" in last_observed_state):
            failures.append("retriever exception did not take the declared empty/no-doc state")
    else:
        docs = last_observed_state.get("retrieved_documents") if isinstance(last_observed_state, dict) else None
        if not isinstance(docs, list) or len(docs) != 1:
            failures.append("successful retrieval did not yield one summarized document")
        if not isinstance(last_observed_state, dict) or "kb_documents" not in last_observed_state:
            failures.append("successful retrieval did not produce the augmented prompt field")

    # The content quotient deliberately keeps only user-visible message text.
    terminal_messages = last_observed_state.get("messages") if isinstance(last_observed_state, dict) else None
    content_only = [
        message.get("$message", {}).get("data", {}).get("content")
        for message in terminal_messages
        if isinstance(message, dict)
    ] if isinstance(terminal_messages, list) else None
    final_answer_only = terminal_messages[-1].get("$message", {}).get("data", {}).get("content") if completed and isinstance(terminal_messages, list) else None
    assistant_message_only = terminal_messages[-1] if completed and isinstance(terminal_messages, list) else None
    trace = {
        "ordered_events": events,
        "node_updates": node_updates,
        "last_observed_state": last_observed_state,
        "terminal_state": terminal_state,
        "graph_status": "complete" if completed else "provider_error",
        "completed": completed,
        "error": error,
    }
    weight = _fraction(input_case["weight"]) * _fraction(str(retrieval_case["weight"])) * _fraction(str(model_case["weight"]))
    return {
        "world_id": f"{input_case['input_id']}__{retrieval_case['outcome_id']}__{model_case['response_id']}",
        "probability": f"{weight.numerator}/{weight.denominator}",
        "outcome": ("modeled_error" if expected_model_error else "complete") if not failures else "frontier_failure",
        "run_status": "provider_error" if expected_model_error and not failures else "complete" if not failures else "frontier_failure",
        "failure_reasons": failures,
        "exception": error,
        "horizon_observed": {
            "retriever_constructors": len(retriever_factory.calls),
            "retriever_calls": retriever_calls,
            "model_calls": model.call_count,
            "graph_value_events": len(values),
            "node_update_path": observed_nodes,
            "graph_recursion_limit": GRAPH_RECURSION_LIMIT,
        },
        "extracted_source_segments": snippets,
        "trace_projection": trace,
        "content_only_projection": content_only,
        "final_answer_only_projection": final_answer_only,
        "assistant_message_only_projection": assistant_message_only,
        "source_slice_binding_observation": {
            **binding_observation,
            "nested_prompt_closure": closure_observation,
        },
        "trace_sha256": _hash(trace),
        "content_only_sha256": _hash(content_only),
        "final_answer_only_sha256": _hash(final_answer_only),
        "assistant_message_only_sha256": _hash(assistant_message_only),
    }


def _law(worlds: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for world in worlds:
        projection_hash = str(world[key])
        if projection_hash not in grouped:
            grouped[projection_hash] = {"weight": Fraction(0), "world_ids": [], "representative": world}
        grouped[projection_hash]["weight"] += _fraction(str(world["probability"]))  # type: ignore[operator]
        grouped[projection_hash]["world_ids"].append(world["world_id"])  # type: ignore[union-attr]
    answer = []
    for projection_hash, group in sorted(grouped.items()):
        probability = group["weight"]
        assert isinstance(probability, Fraction)
        representative = group["representative"]
        assert isinstance(representative, dict)
        projection_field = {
            "trace_sha256": "trace_projection",
            "content_only_sha256": "content_only_projection",
            "final_answer_only_sha256": "final_answer_only_projection",
            "assistant_message_only_sha256": "assistant_message_only_projection",
        }.get(key)
        if projection_field is None:
            raise CapsuleError(f"unsupported law projection key {key}")
        answer.append({
            "projection_sha256": projection_hash,
            "weight": f"{probability.numerator}/{probability.denominator}",
            "world_ids": group["world_ids"],
            "representative": representative[projection_field],
        })
    return answer


def _status_law(worlds: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        grouped[str(world["run_status"])] += _fraction(str(world["probability"]))
    return [
        {"status": status, "weight": f"{weight.numerator}/{weight.denominator}"}
        for status, weight in sorted(grouped.items())
    ]


def _event_law(worlds: list[dict[str, object]], event_kind: str, value_key: str) -> list[dict[str, object]]:
    grouped: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        events = world["trace_projection"]["ordered_events"]
        matches = [event for event in events if event.get("kind") == event_kind]
        value = matches[0].get(value_key) if len(matches) == 1 else f"event_count_{len(matches)}"
        grouped[str(value if value is not None else "raised")] += _fraction(str(world["probability"]))
    return [
        {"value": value, "weight": f"{weight.numerator}/{weight.denominator}"}
        for value, weight in sorted(grouped.items())
    ]


def _replay_world(primary: dict[str, object], replay: dict[str, object]) -> dict[str, object]:
    compared = [
        "world_id", "probability", "extracted_source_segments",
        "outcome", "run_status", "failure_reasons", "exception", "horizon_observed",
        "trace_projection", "content_only_projection", "final_answer_only_projection",
        "assistant_message_only_projection", "trace_sha256", "content_only_sha256",
        "final_answer_only_sha256", "assistant_message_only_sha256", "source_slice_binding_observation",
    ]
    identical = all(_canonical(primary[key]) == _canonical(replay[key]) for key in compared)
    replay_observation = {key: replay[key] for key in compared}
    return {
        "identical": identical,
        "second_observation": replay_observation,
        "compared_fields": compared,
    }


def _collisions(worlds: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for world in worlds:
        grouped[str(world["content_only_sha256"])].append(world)
    return [
        {
            "content_projection_sha256": key,
            "world_ids": sorted(str(world["world_id"]) for world in group),
            "full_trace_sha256s": sorted({str(world["trace_sha256"]) for world in group}),
            "retrieval_response_statuses": sorted({
                str(event.get("status"))
                for world in group
                for event in world["trace_projection"]["ordered_events"]
                if event.get("kind") == "retrieval_response"
            }),
            "same_content_distinct_full_observations": len({str(world["trace_sha256"]) for world in group}) > 1,
        }
        for key, group in sorted(grouped.items())
    ]


async def run() -> dict[str, object]:
    worker_sha256 = _worker_definition_hash()
    root = Path(__file__).resolve().parents[2]
    source_path = root / SOURCE_RELATIVE
    raw = source_path.read_bytes()
    if len(raw) != SOURCE_BYTES or _sha(raw) != SOURCE_SHA256:
        raise CapsuleError("knowledge_base_agent.py bytes differ from pinned manifest")
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(SOURCE_RELATIVE))
    selected = _select_graph(tree)
    worlds = []
    for input_case in INPUTS:
        for retrieval_case in RETRIEVAL_SUPPORT:
            for model_case in MODEL_SUPPORT:
                world = await _run_world(source, selected, input_case, retrieval_case, model_case)
                replay = await _run_world(source, selected, input_case, retrieval_case, model_case)
                world["independent_replay"] = _replay_world(world, replay)
                if not world["independent_replay"]["identical"]:
                    world["outcome"] = "frontier_failure"
                    world["run_status"] = "nondeterministic"
                    world["failure_reasons"].append("exact schedule replay changed its complete observation")
                worlds.append(world)
    total = sum((_fraction(str(world["probability"])) for world in worlds), Fraction(0))
    if total != 1:
        raise CapsuleError(f"finite world weights sum to {total}; expected 1")
    trace_law = _law(worlds, "trace_sha256")
    content_law = _law(worlds, "content_only_sha256")
    source_segments = []
    state = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AgentState")
    source_nodes: list[tuple[str, ast.AST]] = [("AgentState", state)]
    for name, is_async in [
        ("get_kb_retriever", False),
        ("wrap_model", False),
        ("retrieve_documents", True),
        ("prepare_augmented_prompt", True),
        ("acall_model", True),
    ]:
        source_nodes.append((name, _function(tree, name, is_async)))
    source_nodes.extend(selected)
    for label, node in source_nodes:
        text = _segment(source, node, label)
        source_segments.append({"label": label, "lines": [node.lineno, node.end_lineno], "sha256": _sha(text.encode())})
    selection_hash = _sha(_canonical(source_segments))
    mock_contract = {
        "global_bindings": {
            "AmazonKnowledgeBasesRetriever": "FiniteRetrieverFactory; constructor validates exact knowledge_base_id and retrieval_config",
            "get_model": "explicit resolver; records model_id and returns one local BaseChatModel oracle",
            "logger": "MemoryLogger; records info/error calls without host logging or I/O",
            "settings.DEFAULT_MODEL": "finite-kb-model-v1 fixture object",
            "LangGraph/LangChain symbols": "actual pinned runtime classes and graph/runnable/message APIs",
        },
        "retriever_boundary": {
            "constructor": "keyword-only knowledge_base_id and retrieval_config, one constructor per run",
            "ainvoke": "exactly one positional string query; returns one actual Document or raises declared builtins.RuntimeError",
            "schedule_support": [
                {"outcome_id": item["outcome_id"], "kind": item["kind"], "weight": item["weight"]}
                for item in RETRIEVAL_SUPPORT
            ],
        },
        "model_boundary": {
            "api": "actual LangChain Core BaseChatModel.ainvoke path into deterministic _agenerate; exactly one request",
            "request": "full ordered BaseMessage dictionaries plus stop and kwargs",
            "response": "actual AIMessage dictionary including type/id/status/additional kwargs/response metadata/usage metadata; or declared RuntimeError",
            "schedule_support": [
                {"response_id": item["response_id"], "kind": item["kind"], "weight": item["weight"]}
                for item in MODEL_SUPPORT
            ],
        },
        "excluded_effects": ["AWS SDK/provider behavior", "network", "external logging", "unbounded calls", "parallel graph scheduling", "application settings and configuration"],
    }
    mock_contract_hash = _sha(_canonical(mock_contract))
    all_accounted_for = all(
        world["outcome"] in {"complete", "modeled_error"}
        and world["independent_replay"]["identical"]
        for world in worlds
    )
    trace_law = _law(worlds, "trace_sha256")
    content_law = _law(worlds, "content_only_sha256")
    final_answer_law = _law(worlds, "final_answer_only_sha256")
    return {
        "capsule_id": "joshuac215-kb-agent-sequential-async-finite-oracle-v1",
        "result": "PASS_CONDITIONAL_FINITE_DOMAIN" if all_accounted_for else "REJECTED_FRONTIER_OR_RUNTIME_FAILURE",
        "claim": {
            "scope": "Scoped source-slice execution: exact source segments for the AgentState schema, retriever/model/prompt async callables, and the one sequential three-node graph path, run with actual LangGraph 1.2.14 and LangChain Core 1.6.9 over the declared finite support.",
            "finite_domain_guarantee": "Every declared input x retrieval outcome x model response was executed; exact rational trace weights are conditional on this finite product support and declared projection.",
            "excluded": [
                "This is not whole-file admission, arbitrary Python/AST translation correctness, arbitrary inputs, unbounded horizon, or an AWS/OpenAI provider conformance claim.",
                "The module was never imported. Production imports, AWS retriever, application core/settings, external logger setup, and service infrastructure were excluded.",
                "AmazonKnowledgeBasesRetriever, get_model, settings, and logger are explicit external premises. Their pure mock APIs are hash-bound in mock_contract; the source-to-mock Python boundary is exercised, not a network protocol or cloud API.",
                "The only environment key is a nonsecret fixture AWS_KB_ID. Runtime credentials and .env files are absent.",
                "Projection equality retains canonical BaseMessage dictionaries (including message type and metadata), Document boundary values, retriever/model requests and responses, source log calls, ordered LangGraph updates/value states, and full terminal state. It omits Python object identity, timestamps, opaque callback/run IDs, and OS scheduling.",
                "The catch-all retrieval exception branch is exercised only for the single declared RuntimeError message; this does not validate arbitrary exception behavior.",
            ],
        },
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "path": str(SOURCE_RELATIVE),
            "sha256": SOURCE_SHA256,
            "bytes": SOURCE_BYTES,
            "license": "MIT",
            "url": SOURCE_URL,
            "segments": source_segments,
            "selection_sha256": selection_hash,
        },
        "capsule_definition": {
            "worker_sha256": worker_sha256,
            "source_segment_selection_sha256": selection_hash,
            "mock_contract_sha256": mock_contract_hash,
            "mock_contract": mock_contract,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "langgraph": importlib.metadata.version("langgraph"),
            "langchain_core": importlib.metadata.version("langchain-core"),
            "langchain_aws": "not installed; production retriever replaced by explicit mock",
            "model_provider": "deterministic local BaseChatModel async oracle; no API key or network",
        },
        "finite_support": {
            "inputs": INPUTS,
            "retrieval_outcomes": RETRIEVAL_SUPPORT,
            "model_responses": MODEL_SUPPORT,
            "input_domain_size": len(INPUTS),
            "retrieval_support_size": len(RETRIEVAL_SUPPORT),
            "model_support_size": len(MODEL_SUPPORT),
            "elementary_world_count": len(worlds),
            "retrieval_horizon": RETRIEVER_HORIZON,
            "model_horizon": MODEL_HORIZON,
            "graph_recursion_limit": GRAPH_RECURSION_LIMIT,
            "weight_rule": "P(input) * P(retrieval outcome) * P(model response), exact Fraction arithmetic",
        },
        "worlds": worlds,
        "exact_laws": {
            "complete_trace_equivalence": "exact canonical JSON equality over trace_projection",
            "content_only_equivalence": "exact equality over ordered terminal message content strings; omits request/history outside messages, message type/IDs/metadata, documents, and statuses",
            "complete_trace_law": trace_law,
            "content_only_law": content_law,
            "final_answer_only_law": final_answer_law,
            "assistant_message_only_law": _law(worlds, "assistant_message_only_sha256"),
            "run_status_law": _status_law(worlds),
            "retrieval_response_status_law": _event_law(worlds, "retrieval_response", "status"),
            "model_response_status_law": _event_law(worlds, "model_response", "status"),
            "finish_reason_or_error_law": _event_law(worlds, "model_response", "finish_reason"),
            "same_content_distinct_full_observations_collisions": _collisions(worlds),
            "weights_sum_to_one": total == 1,
            "all_declared_worlds_accounted_for": all_accounted_for,
            "all_independent_replays_identical": all(world["independent_replay"]["identical"] for world in worlds),
            "modeled_model_error_world_count": sum(world["run_status"] == "provider_error" for world in worlds),
        },
        "practical_property": {
            "property": "The original catch-all retrieval exception path logs the declared retrieval error, returns empty retrieval state, skips prompt augmentation, and still invokes the model with the no-documents system prompt.",
            "exception_world_count": sum(world["world_id"].find("retrieval_exception") >= 0 for world in worlds),
            "same_answer_text_across_retrieval_outcomes": len({str(response["content"]) for response in MODEL_SUPPORT if response["kind"] == "returned"}) == 1,
            "full_trace_class_count": len(trace_law),
            "content_only_class_count": len(content_law),
            "final_answer_only_class_count": len(final_answer_law),
            "content_history_merges_distinct_full_observations": any(
                item["same_content_distinct_full_observations"]
                for item in _collisions(worlds)
            ),
            "interpretation": "For the declared fixture domain, terminal user-visible answer text hides whether retrieval returned evidence or the original source caught a retrieval exception; the complete request/history/state trace distinguishes those executions.",
        },
        "execution_boundary": {
            "source_module_imported": False,
            "execution_unit": "scoped exact source slices compiled into one explicit ModuleType namespace; callable globals are identity-checked and free-variable closures are rejected",
            "executed_original_source": [label for label, _ in source_nodes],
            "actual_runtime": "LangGraph compiled graph .astream(..., stream_mode=['updates','values']) with sequential async nodes; the finite provider/retriever adapters are in-process mocks.",
            "sandbox": "macOS Seatbelt profile denies network, writes, process inspection/fork, Mach lookups, unlisted user files, temporary storage, and volumes; only pinned runtime, worker, and exact source file are readable.",
            "environment": "Minimal scrubbed child env plus one nonsecret fixture AWS_KB_ID; no HOME, provider credentials, or API config.",
        },
    }


def main() -> int:
    try:
        result = asyncio.run(run())
    except Exception as exc:
        result = {
            "capsule_id": "joshuac215-kb-agent-sequential-async-finite-oracle-v1",
            "result": "REJECTED_FRONTIER_OR_RUNTIME_FAILURE",
            "fatal_error": {"type": f"{type(exc).__module__}.{type(exc).__qualname__}", "message": str(exc)[:2000]},
        }
    print("CAPSULE_JSON:" + json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("result") == "PASS_CONDITIONAL_FINITE_DOMAIN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
