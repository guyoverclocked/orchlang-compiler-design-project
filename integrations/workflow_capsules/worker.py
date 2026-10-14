#!/usr/bin/env python3
"""Run one reviewed source slice inside the caller's Seatbelt sandbox.

The host-side run_capsule.py starts this file under a deny-network,
deny-write, deny-other-user-files profile. This worker intentionally does not
import the source module: it compiles only source segments pinned below.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Annotated, List, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, message_to_dict
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


SOURCE_RELATIVE = Path(
    "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/"
    "9de20be80dad6d410268ae75f75cf94c355dd364/"
    "案例与源码-3-LangGraph框架/01-helloworld/LangGraphLLM.py"
)
SOURCE_SHA256 = "b35741309de653d79e2cb403ebc5ddfa6b74383dd22f2e0d0142a1359225818b"
SOURCE_BYTES = 6982
SOURCE_COMMIT = "9de20be80dad6d410268ae75f75cf94c355dd364"
SOURCE_REPOSITORY = "didilili/ai-agents-from-zero"
SOURCE_URL = (
    "https://github.com/didilili/ai-agents-from-zero/blob/"
    "9de20be80dad6d410268ae75f75cf94c355dd364/"
    "%E6%A1%88%E4%BE%8B%E4%B8%8E%E6%BA%90%E7%A0%81-3-LangGraph%E6%A1%86%E6%9E%B6/"
    "01-helloworld/LangGraphLLM.py"
)
HORIZON_MODEL_CALLS = 1
GRAPH_RECURSION_LIMIT = 6


class CapsuleError(RuntimeError):
    """An unsupported source, interface, or frontier was encountered."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _plain(value: object) -> object:
    """Project only declared JSON/message values; never stringify unknowns."""
    if isinstance(value, BaseMessage):
        return {"$message": _plain(message_to_dict(value))}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CapsuleError("non-finite float is outside the projection")
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CapsuleError("non-string mapping key is outside the projection")
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(child) for child in value]
    raise CapsuleError(f"unsupported returned value type: {type(value).__qualname__}")


def _source_segment(source: str, node: ast.AST, label: str) -> str:
    segment = ast.get_source_segment(source, node)
    if segment is None:
        raise CapsuleError(f"missing exact source segment for {label}")
    return segment


def _call(node: ast.AST, dotted_name: str) -> ast.Call:
    if not isinstance(node, ast.Call) or ast.unparse(node.func) != dotted_name:
        raise CapsuleError(f"expected exactly a call to {dotted_name}")
    return node


def _assert_state_class(node: ast.ClassDef) -> None:
    if node.name != "DiliState" or node.decorator_list or node.keywords:
        raise CapsuleError("DiliState declaration left the reviewed subset")
    if len(node.bases) != 1 or not isinstance(node.bases[0], ast.Name) or node.bases[0].id != "TypedDict":
        raise CapsuleError("DiliState base changed")
    fields = [item for item in node.body if isinstance(item, ast.AnnAssign)]
    if len(fields) != 1 or len(node.body) != 1:
        raise CapsuleError("DiliState fields changed")
    field = fields[0]
    if not isinstance(field.target, ast.Name) or field.target.id != "messages" or field.value is not None:
        raise CapsuleError("DiliState.messages declaration changed")
    annotation = field.annotation
    if not isinstance(annotation, ast.Subscript) or not isinstance(annotation.value, ast.Name) or annotation.value.id != "Annotated":
        raise CapsuleError("DiliState.messages reducer annotation changed")
    args = annotation.slice
    if not isinstance(args, ast.Tuple) or len(args.elts) != 2:
        raise CapsuleError("DiliState.messages annotation is outside the reviewed subset")
    list_type, reducer = args.elts
    if not isinstance(list_type, ast.Name) or list_type.id != "List":
        raise CapsuleError("DiliState.messages list type changed")
    if not isinstance(reducer, ast.Name) or reducer.id != "add_messages":
        raise CapsuleError("DiliState.messages reducer changed")


def _assert_model_node(node: ast.FunctionDef) -> None:
    if node.name != "model_node" or node.decorator_list or node.type_params:
        raise CapsuleError("model_node declaration left the reviewed subset")
    if node.args.posonlyargs or node.args.kwonlyargs or node.args.vararg or node.args.kwarg:
        raise CapsuleError("model_node signature changed")
    if len(node.args.args) != 1 or node.args.args[0].arg != "state":
        raise CapsuleError("model_node signature changed")
    if not isinstance(node.args.args[0].annotation, ast.Name) or node.args.args[0].annotation.id != "DiliState":
        raise CapsuleError("model_node state annotation changed")
    if len(node.body) != 2:
        raise CapsuleError("model_node body changed")
    assignment, returned = node.body
    if not isinstance(assignment, ast.Assign) or len(assignment.targets) != 1:
        raise CapsuleError("model_node reply assignment changed")
    if not isinstance(assignment.targets[0], ast.Name) or assignment.targets[0].id != "reply":
        raise CapsuleError("model_node reply target changed")
    invoke = _call(assignment.value, "llm.invoke")
    if invoke.keywords or len(invoke.args) != 1:
        raise CapsuleError("model_node invoke arguments changed")
    messages = invoke.args[0]
    if not isinstance(messages, ast.Subscript) or not isinstance(messages.value, ast.Name) or messages.value.id != "state":
        raise CapsuleError("model_node request source changed")
    if not isinstance(messages.slice, ast.Constant) or messages.slice.value != "messages":
        raise CapsuleError("model_node request field changed")
    if not isinstance(returned, ast.Return) or not isinstance(returned.value, ast.Dict):
        raise CapsuleError("model_node return changed")
    if len(returned.value.keys) != 1 or len(returned.value.values) != 1:
        raise CapsuleError("model_node return mapping changed")
    key = returned.value.keys[0]
    value = returned.value.values[0]
    if not isinstance(key, ast.Constant) or key.value != "messages":
        raise CapsuleError("model_node return field changed")
    if not isinstance(value, ast.List) or len(value.elts) != 1:
        raise CapsuleError("model_node return shape changed")
    if not isinstance(value.elts[0], ast.Name) or value.elts[0].id != "reply":
        raise CapsuleError("model_node return value changed")


def _graph_setup_segments(tree: ast.Module, source: str) -> list[tuple[str, ast.AST]]:
    """Pick and validate only the five source statements that wire this graph."""
    selected: dict[str, ast.AST] = {}
    for statement in tree.body:
        label: str | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id == "graph":
                call = _call(statement.value, "StateGraph")
                if call.keywords or len(call.args) != 1 or not isinstance(call.args[0], ast.Name) or call.args[0].id != "DiliState":
                    raise CapsuleError("graph state schema changed")
                label = "graph_init"
            elif isinstance(target, ast.Name) and target.id == "app":
                call = _call(statement.value, "graph.compile")
                if call.args or call.keywords:
                    raise CapsuleError("graph compile call changed")
                label = "graph_compile"
        elif isinstance(statement, ast.Expr):
            value = statement.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name) and value.func.value.id == "graph":
                if value.func.attr == "add_node":
                    if value.keywords or len(value.args) != 2 or not isinstance(value.args[0], ast.Constant) or value.args[0].value != "model" or not isinstance(value.args[1], ast.Name) or value.args[1].id != "model_node":
                        raise CapsuleError("graph node registration changed")
                    label = "graph_add_node"
                elif value.func.attr == "add_edge":
                    if value.keywords or len(value.args) != 2:
                        raise CapsuleError("graph edge registration changed")
                    left, right = value.args
                    if isinstance(left, ast.Name) and left.id == "START" and isinstance(right, ast.Constant) and right.value == "model":
                        label = "graph_start_edge"
                    elif isinstance(left, ast.Constant) and left.value == "model" and isinstance(right, ast.Name) and right.id == "END":
                        label = "graph_end_edge"
                    else:
                        raise CapsuleError("graph contains an undeclared edge")
        if label is not None:
            if label in selected:
                raise CapsuleError(f"duplicate graph statement: {label}")
            selected[label] = statement

    expected = ["graph_init", "graph_add_node", "graph_start_edge", "graph_end_edge", "graph_compile"]
    if set(selected) != set(expected):
        missing = sorted(set(expected) - set(selected))
        extra = sorted(set(selected) - set(expected))
        raise CapsuleError(f"graph frontier is incomplete; missing={missing}, extra={extra}")
    ordered = sorted(selected.items(), key=lambda pair: pair[1].lineno)
    if [label for label, _ in ordered] != expected:
        raise CapsuleError("graph setup statements are not in the reviewed order")
    return [(label, node) for label, node in ordered]


def _compile_segment(namespace: dict[str, object], source: str, node: ast.AST, label: str) -> str:
    segment = _source_segment(source, node, label)
    # No AST rewrite or pretty-print: compile the exact source substring.
    exec(compile(segment, f"{SOURCE_RELATIVE}:{node.lineno}", "exec"), namespace)
    return segment


INPUT_SUPPORT = [
    {"input_id": "question_a", "content": "What is two plus two?", "weight": "1/2"},
    {"input_id": "question_b", "content": "Why does the graph keep messages?", "weight": "1/2"},
]

RESPONSE_SUPPORT = [
    {
        "response_id": "finish_stop",
        "weight": "1/3",
        "kind": "returned",
        "content": "The answer is recorded.",
        "id": "fixture-stop-001",
        "status": "success",
        "response_metadata": {"finish_reason": "stop", "model_name": "finite-oracle-v1"},
        "usage_metadata": {"input_tokens": 7, "output_tokens": 4, "total_tokens": 11},
    },
    {
        "response_id": "finish_length",
        "weight": "1/3",
        "kind": "returned",
        "content": "The answer is recorded.",
        "id": "fixture-length-001",
        "status": "success",
        "response_metadata": {"finish_reason": "length", "model_name": "finite-oracle-v1"},
        "usage_metadata": {"input_tokens": 7, "output_tokens": 8, "total_tokens": 15},
    },
    {
        "response_id": "provider_exception",
        "weight": "1/3",
        "kind": "exception",
        "exception_type": "RuntimeError",
        "exception_message": "finite provider fixture failure",
    },
]


class FiniteResponseOracle:
    """Deterministic `.invoke(messages)` mock with one declared response slot."""

    def __init__(self, response: dict[str, object], events: list[dict[str, object]]):
        self.response = response
        self.events = events
        self.call_count = 0

    def invoke(self, messages: object, *args: object, **kwargs: object) -> AIMessage:
        self.call_count += 1
        if args or kwargs:
            self.events.append({"kind": "frontier_failure", "reason": "invoke used unsupported args/kwargs"})
            raise CapsuleError("mock boundary received unsupported invoke arguments")
        if self.call_count != 1:
            self.events.append({"kind": "frontier_failure", "reason": "model-call horizon exceeded"})
            raise CapsuleError("model-call horizon exceeded the declared one-call support")
        if not isinstance(messages, list) or not messages or not all(isinstance(message, BaseMessage) for message in messages):
            self.events.append({"kind": "frontier_failure", "reason": "request is outside message-list support"})
            raise CapsuleError("model request is outside the declared list[BaseMessage] support")
        envelope = {
            "method": "invoke",
            "args": [_plain(messages)],
            "kwargs": {},
        }
        self.events.append({"kind": "model_request", "envelope": envelope})
        if self.response["kind"] == "exception":
            self.events.append(
                {
                    "kind": "model_response",
                    "status": "raised",
                    "response_id": self.response["response_id"],
                    "exception_type": self.response["exception_type"],
                    "exception_message": self.response["exception_message"],
                }
            )
            raise RuntimeError(str(self.response["exception_message"]))
        reply = AIMessage(
            content=str(self.response["content"]),
            id=str(self.response["id"]),
            status=str(self.response["status"]),
            response_metadata=dict(self.response["response_metadata"]),
            usage_metadata=dict(self.response["usage_metadata"]),
        )
        reply_projection = _plain(reply)
        self.events.append(
            {
                "kind": "model_response",
                "status": "returned",
                "response_id": self.response["response_id"],
                "message": reply_projection,
                "finish_reason": self.response["response_metadata"]["finish_reason"],
                "usage": self.response["usage_metadata"],
            }
        )
        return reply


def _fraction(text: str) -> Fraction:
    value = Fraction(text)
    if value <= 0:
        raise CapsuleError("all declared support weights must be positive")
    return value


def _hash_projection(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _worker_definition_hash() -> str:
    actual = _sha256(Path(__file__).read_bytes())
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


def _run_world(
    source: str,
    state_node: ast.ClassDef,
    function_node: ast.FunctionDef,
    graph_segments: list[tuple[str, ast.AST]],
    input_case: dict[str, str],
    response_case: dict[str, object],
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    oracle = FiniteResponseOracle(response_case, events)
    source_module = ModuleType(
        f"_capsule_didilili_{input_case['input_id']}_{response_case['response_id']}"
    )
    sys.modules[source_module.__name__] = source_module
    namespace: dict[str, object] = source_module.__dict__
    namespace.update({
        "__builtins__": __builtins__,
        "Annotated": Annotated,
        "List": List,
        "TypedDict": TypedDict,
        "add_messages": add_messages,
        "StateGraph": StateGraph,
        "START": START,
        "END": END,
        "llm": oracle,
    })
    snippets: list[dict[str, object]] = []
    for label, node in [("DiliState", state_node), ("model_node", function_node)]:
        segment = _compile_segment(namespace, source, node, label)
        snippets.append(
            {
                "label": label,
                "source_lines": [node.lineno, node.end_lineno],
                "segment_sha256": _sha256(segment.encode("utf-8")),
            }
        )
    for label, node in graph_segments:
        segment = _compile_segment(namespace, source, node, label)
        snippets.append(
            {
                "label": label,
                "source_lines": [node.lineno, node.end_lineno],
                "segment_sha256": _sha256(segment.encode("utf-8")),
            }
        )

    binding_observation: dict[str, object] = {
        "state_class_module_matches_namespace": getattr(namespace.get("DiliState"), "__module__", None) == source_module.__name__,
        "callables": _assert_module_bindings(namespace, ["model_node"]),
    }
    if not binding_observation["state_class_module_matches_namespace"]:
        raise CapsuleError("DiliState class was not compiled into its source-slice module")

    app = namespace.get("app")
    stream_method = getattr(app, "stream", None)
    if not callable(stream_method):
        raise CapsuleError("original source graph did not produce a stream-capable app")
    initial = {
        "messages": [
            HumanMessage(
                content=input_case["content"],
                id=f"input-{input_case['input_id']}",
            )
        ]
    }
    graph_config = {"recursion_limit": GRAPH_RECURSION_LIMIT}
    stream_modes = ["updates", "values"]
    events.append({
        "kind": "graph_start",
        "input": _plain(initial),
        "config": graph_config,
        "stream_mode": stream_modes,
    })
    terminal_values: object | None = None
    callable_returns: list[dict[str, object]] = []
    graph_completed = False
    graph_error: dict[str, str] | None = None
    value_count = 0
    update_count = 0
    try:
        for item in stream_method(
            initial,
            graph_config,
            stream_mode=stream_modes,
        ):
            if not isinstance(item, tuple) or len(item) != 2:
                raise CapsuleError("LangGraph stream returned an unsupported event shape")
            mode, chunk = item
            if mode == "values":
                value_count += 1
                terminal_values = _plain(chunk)
                events.append({"kind": "graph_state", "ordinal": value_count, "state": terminal_values})
            elif mode == "updates":
                if not isinstance(chunk, dict):
                    raise CapsuleError("LangGraph update chunk is not a mapping")
                for node_name, update in chunk.items():
                    update_count += 1
                    if node_name != "model":
                        events.append({"kind": "frontier_failure", "reason": f"unexpected node {node_name!r}"})
                        raise CapsuleError(f"unmodeled graph node reached: {node_name!r}")
                    projected_update = _plain(update)
                    callable_returns.append({"node": node_name, "update": projected_update})
                    events.append({"kind": "node_update", "node": node_name, "update": projected_update})
            else:
                events.append({"kind": "frontier_failure", "reason": f"unsupported stream mode {mode!r}"})
                raise CapsuleError(f"unsupported LangGraph stream mode: {mode!r}")
        graph_completed = True
        events.append({"kind": "graph_complete", "terminal": _plain(terminal_values)})
    except Exception as error:  # Preserve each failure as a result instead of dropping it.
        graph_error = {
            "type": f"{type(error).__module__}.{type(error).__qualname__}",
            "message": str(error)[:2000],
        }
        events.append({"kind": "graph_exception", **graph_error})

    failures: list[str] = []
    if oracle.call_count != HORIZON_MODEL_CALLS:
        failures.append(f"expected {HORIZON_MODEL_CALLS} model call, observed {oracle.call_count}")
    expected_model_error = response_case["kind"] == "exception"
    if expected_model_error:
        if graph_completed:
            failures.append("model exception branch unexpectedly completed the graph")
        if graph_error is None or graph_error.get("type") != "builtins.RuntimeError" or graph_error.get("message") != response_case["exception_message"]:
            failures.append("graph error did not match the declared deterministic provider exception")
        if update_count != 0:
            failures.append(f"model exception branch emitted {update_count} node updates")
        if value_count != 1:
            failures.append(f"model exception branch observed {value_count} value states, expected initial state only")
        if not any(event.get("kind") == "model_response" and event.get("status") == "raised" for event in events):
            failures.append("provider exception status was not recorded")
    else:
        if not graph_completed:
            failures.append("graph did not terminate within the declared run")
        if graph_error is not None:
            failures.append("graph raised an exception")
        if value_count != 2:
            failures.append(f"expected initial and terminal state events, observed {value_count}")
        if update_count != 1:
            failures.append(f"expected one model node update, observed {update_count}")
        if not isinstance(terminal_values, dict) or "messages" not in terminal_values:
            failures.append("terminal state is outside the declared message-state projection")

    last_observed_state = _plain(terminal_values)
    terminal_state = last_observed_state if graph_completed else None
    content_state = terminal_state if graph_completed else last_observed_state
    terminal_messages = content_state.get("messages") if isinstance(content_state, dict) else None
    if graph_completed:
        if not isinstance(terminal_messages, list) or len(terminal_messages) != 2:
            failures.append("terminal state did not retain one input and one response message")
        elif terminal_messages[0].get("$message", {}).get("data", {}).get("id") != f"input-{input_case['input_id']}":
            failures.append("input message history was not preserved")
    elif not isinstance(terminal_messages, list) or len(terminal_messages) != 1:
        failures.append("error branch did not preserve the last observed input-only state")

    content_projection: object = None
    if isinstance(terminal_messages, list):
        content_projection = [
            message.get("$message", {}).get("data", {}).get("content")
            for message in terminal_messages
            if isinstance(message, dict)
        ]
    final_answer_only = (
        terminal_messages[-1].get("$message", {}).get("data", {}).get("content")
        if graph_completed and isinstance(terminal_messages, list)
        else None
    )
    assistant_message_only = terminal_messages[-1] if graph_completed and isinstance(terminal_messages, list) else None

    trace_projection = {
        "request_and_response_events": [
            event for event in events if event.get("kind") in {"model_request", "model_response"}
        ],
        "ordered_execution_events": events,
        "callable_returns": callable_returns,
        "last_observed_state": last_observed_state,
        "terminal_state": terminal_state,
        "graph_status": "complete" if graph_completed else "provider_error",
        "graph_completed": graph_completed,
    }
    probability = _fraction(input_case["weight"]) * _fraction(str(response_case["weight"]))
    return {
        "world_id": f"{input_case['input_id']}__{response_case['response_id']}",
        "input_id": input_case["input_id"],
        "response_id": response_case["response_id"],
        "probability": f"{probability.numerator}/{probability.denominator}",
        "outcome": ("modeled_error" if expected_model_error else "complete") if not failures else "frontier_failure",
        "run_status": "provider_error" if expected_model_error and not failures else "complete" if not failures else "frontier_failure",
        "failure_reasons": failures,
        "exception": graph_error,
        "horizon_observed": {
            "model_calls": oracle.call_count,
            "graph_value_events": value_count,
            "node_updates": update_count,
            "graph_recursion_limit": GRAPH_RECURSION_LIMIT,
        },
        "extracted_source_segments": snippets,
        "source_slice_binding_observation": binding_observation,
        "trace_projection": trace_projection,
        "content_only_projection": content_projection,
        "final_answer_only_projection": final_answer_only,
        "assistant_message_only_projection": assistant_message_only,
        "trace_sha256": _hash_projection(trace_projection),
        "content_only_sha256": _hash_projection(content_projection),
        "final_answer_only_sha256": _hash_projection(final_answer_only),
        "assistant_message_only_sha256": _hash_projection(assistant_message_only),
    }


def _law(worlds: list[dict[str, object]], key_name: str) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for world in worlds:
        key = str(world[key_name])
        probability = _fraction(str(world["probability"]))
        if key not in groups:
            groups[key] = {"weight": Fraction(0), "world_ids": [], "representative": world}
        groups[key]["weight"] += probability  # type: ignore[operator]
        groups[key]["world_ids"].append(world["world_id"])  # type: ignore[union-attr]
    result = []
    for key, group in sorted(groups.items()):
        weight = group["weight"]
        assert isinstance(weight, Fraction)
        projection_field = {
            "trace_sha256": "trace_projection",
            "content_only_sha256": "content_only_projection",
            "final_answer_only_sha256": "final_answer_only_projection",
            "assistant_message_only_sha256": "assistant_message_only_projection",
        }.get(key_name)
        if projection_field is None:
            raise CapsuleError(f"unsupported law key {key_name}")
        result.append(
            {
                "projection_sha256": key,
                "weight": f"{weight.numerator}/{weight.denominator}",
                "world_ids": group["world_ids"],
                "representative": group["representative"][projection_field],
            }
        )
    return result


def _status_law(worlds: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        groups[str(world["run_status"])] += _fraction(str(world["probability"]))
    return [
        {"status": status, "weight": f"{weight.numerator}/{weight.denominator}"}
        for status, weight in sorted(groups.items())
    ]


def _event_law(worlds: list[dict[str, object]], event_kind: str, value_key: str) -> list[dict[str, object]]:
    groups: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        events = world["trace_projection"]["ordered_execution_events"]
        matches = [event for event in events if event.get("kind") == event_kind]
        value = matches[0].get(value_key) if len(matches) == 1 else f"event_count_{len(matches)}"
        groups[str(value if value is not None else "raised")] += _fraction(str(world["probability"]))
    return [
        {"value": value, "weight": f"{weight.numerator}/{weight.denominator}"}
        for value, weight in sorted(groups.items())
    ]


def _replay_world(primary: dict[str, object], replay: dict[str, object]) -> dict[str, object]:
    compared = [
        "world_id", "input_id", "response_id", "probability", "extracted_source_segments",
        "outcome", "run_status", "failure_reasons", "exception", "horizon_observed",
        "trace_projection", "content_only_projection", "final_answer_only_projection",
        "assistant_message_only_projection", "trace_sha256", "content_only_sha256",
        "final_answer_only_sha256", "assistant_message_only_sha256", "source_slice_binding_observation",
    ]
    identical = all(_canonical_bytes(primary[key]) == _canonical_bytes(replay[key]) for key in compared)
    replay_observation = {key: replay[key] for key in compared}
    return {
        "identical": identical,
        "second_observation": replay_observation,
        "compared_fields": compared,
    }


def run() -> dict[str, object]:
    worker_sha256 = _worker_definition_hash()
    expected_environment = {
        "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
        "AWS_KB_ID", "CAPSULE_WORKER_SHA256",
    }
    extra_environment = set(os.environ) - expected_environment
    if extra_environment not in (set(), {"LC_CTYPE"}) or set(os.environ) < expected_environment:
        raise CapsuleError("child environment was not reduced to the declared fixture variables")
    if "LC_CTYPE" in extra_environment and os.environ["LC_CTYPE"] != "C.UTF-8":
        raise CapsuleError("unexpected interpreter-synthesized locale value")
    root = Path(__file__).resolve().parents[2]
    source_path = root / SOURCE_RELATIVE
    raw = source_path.read_bytes()
    if len(raw) != SOURCE_BYTES or _sha256(raw) != SOURCE_SHA256:
        raise CapsuleError("development snapshot bytes do not match the pinned source manifest")
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(SOURCE_RELATIVE))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DiliState"]
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "model_node"]
    if len(classes) != 1 or len(functions) != 1:
        raise CapsuleError("expected one DiliState class and one model_node function")
    state_node = classes[0]
    function_node = functions[0]
    _assert_state_class(state_node)
    _assert_model_node(function_node)
    graph_segments = _graph_setup_segments(tree, source)

    worlds = []
    for input_case in INPUT_SUPPORT:
        for response_case in RESPONSE_SUPPORT:
            world = _run_world(source, state_node, function_node, graph_segments, input_case, response_case)
            replay = _run_world(source, state_node, function_node, graph_segments, input_case, response_case)
            world["independent_replay"] = _replay_world(world, replay)
            if not world["independent_replay"]["identical"]:
                world["outcome"] = "frontier_failure"
                world["run_status"] = "nondeterministic"
                world["failure_reasons"].append("exact schedule replay changed its complete observation")
            worlds.append(world)
    total = sum((_fraction(str(world["probability"])) for world in worlds), Fraction(0))
    if total != 1:
        raise CapsuleError(f"finite world weights sum to {total}, expected 1")
    full_law = _law(worlds, "trace_sha256")
    content_law = _law(worlds, "content_only_sha256")
    full_keys_by_content: dict[str, list[str]] = defaultdict(list)
    for world in worlds:
        full_keys_by_content[str(world["content_only_sha256"])].append(str(world["trace_sha256"]))
    collisions = [
        {
            "content_projection_sha256": content_key,
            "full_trace_sha256s": sorted(set(full_keys)),
            "world_ids": sorted(
                str(world["world_id"])
                for world in worlds
                if world["content_only_sha256"] == content_key
            ),
            "same_content_distinct_full_observations": len(set(full_keys)) > 1,
        }
        for content_key, full_keys in sorted(full_keys_by_content.items())
    ]
    accounted_for = all(
        world["outcome"] in {"complete", "modeled_error"}
        and world["independent_replay"]["identical"]
        for world in worlds
    )

    source_segments = []
    for label, node in [("DiliState", state_node), ("model_node", function_node), *graph_segments]:
        segment = _source_segment(source, node, label)
        source_segments.append(
            {"label": label, "lines": [node.lineno, node.end_lineno], "sha256": _sha256(segment.encode("utf-8"))}
        )
    selection_hash = _sha256(_canonical_bytes(source_segments))
    mock_contract = {
        "global_bindings": {
            "llm": "FiniteResponseOracle instance; model_node.__globals__ is the same ModuleType namespace",
            "StateGraph/START/END": "actual langgraph.graph 1.2.14 runtime objects",
            "add_messages": "actual langgraph.graph.message.add_messages from LangGraph 1.2.14",
            "typing_names": "actual Python 3.14 typing.Annotated/List/TypedDict",
        },
        "model_boundary": {
            "api": ".invoke(messages) with exactly one list[BaseMessage] call",
            "schedule_support": [
                {"response_id": item["response_id"], "kind": item["kind"], "weight": item["weight"]}
                for item in RESPONSE_SUPPORT
            ],
            "returned_type": "actual langchain_core.messages.AIMessage, including type, id, status, response_metadata, and usage_metadata in the projection",
            "exception": "declared builtins.RuntimeError with exact fixture message",
        },
        "excluded_effects": ["provider network and wire protocol", "dotenv and application configuration", "host logging", "unbounded calls", "concurrency"],
    }
    mock_contract_hash = _sha256(_canonical_bytes(mock_contract))

    return {
        "capsule_id": "didilili-langgraphllm-one-node-finite-oracle-v1",
        "result": "PASS_CONDITIONAL_FINITE_DOMAIN" if accounted_for else "REJECTED_FRONTIER_OR_RUNTIME_FAILURE",
        "claim": {
            "scope": "Exact replay of the byte-pinned DiliState/model_node source segments and byte-pinned one-node graph-wiring statements, run by actual LangGraph 1.2.14 over the declared finite inputs and deterministic response support.",
            "finite_domain_guarantee": "Every declared input x response-support pair was enumerated; the rational trace law is exact for that finite product support and the declared trace projection.",
            "exclusions": [
                "No claim about arbitrary Python programs, AST-to-OrchLang translation, other source spans, whole-file admission, arbitrary inputs, unbounded call sequences, or real provider HTTP/API behavior.",
                "The source module was not imported. load_dotenv, init_chat_model, provider initialization, top-level example invocation, printing, and graph visualization were excluded.",
                "The llm global was replaced with an explicit finite .invoke(messages) oracle. This tests the source-to-mock boundary, not a provider adapter or wire protocol.",
                "The finite support weights are declared fixture weights, not measured model probabilities.",
                "Projection equality compares canonical message dictionaries, request envelopes, node updates, ordered stream states, and terminal state; it omits Python identity, wall-clock timing, and opaque LangGraph run/config IDs.",
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
            "langgraph": "1.2.14",
            "langchain_core": "1.6.9",
            "langchain_full_package": "not installed; no full-langchain import was needed",
            "model_provider": "deterministic in-process mock; no API key or network",
        },
        "finite_support": {
            "input_states": INPUT_SUPPORT,
            "model_responses": RESPONSE_SUPPORT,
            "input_domain_size": len(INPUT_SUPPORT),
            "response_support_size": len(RESPONSE_SUPPORT),
            "elementary_world_count": len(worlds),
            "model_call_horizon": HORIZON_MODEL_CALLS,
            "graph_recursion_limit": GRAPH_RECURSION_LIMIT,
            "world_weight_rule": "P(input) * P(response); all arithmetic uses exact Fraction values",
        },
        "worlds": worlds,
        "exact_laws": {
            "complete_trace_equivalence": "exact canonical JSON equality over trace_projection",
            "content_only_equivalence": "exact canonical JSON equality over ordered content strings in terminal messages, or the last observed input-only state for a modeled provider error",
            "complete_trace_law": full_law,
            "content_only_law": content_law,
            "final_answer_only_law": _law(worlds, "final_answer_only_sha256"),
            "assistant_message_only_law": _law(worlds, "assistant_message_only_sha256"),
            "run_status_law": _status_law(worlds),
            "model_response_status_law": _event_law(worlds, "model_response", "status"),
            "finish_reason_or_error_law": _event_law(worlds, "model_response", "finish_reason"),
            "same_content_distinct_observation_collisions": collisions,
            "weights_sum_to_one": total == 1,
            "all_declared_worlds_accounted_for": accounted_for,
            "all_independent_replays_identical": all(world["independent_replay"]["identical"] for world in worlds),
            "modeled_provider_error_world_count": sum(world["run_status"] == "provider_error" for world in worlds),
        },
        "practical_counterexample": {
            "property": "The source returns same-text AIMessage variants with different ID, finish reason, and usage metadata; an explicit provider-error schedule yields a visible raised status and no terminal graph state.",
            "same_text": RESPONSE_SUPPORT[0]["content"] == RESPONSE_SUPPORT[1]["content"],
            "response_finish_reasons": [
                "raised" if item["kind"] == "exception" else item["response_metadata"]["finish_reason"]
                for item in RESPONSE_SUPPORT
            ],
            "response_usage": [item.get("usage_metadata") for item in RESPONSE_SUPPORT],
            "model_statuses": ["returned" if item["kind"] == "returned" else "raised" for item in RESPONSE_SUPPORT],
            "complete_trace_class_count": len(full_law),
            "message_content_history_class_count": len(content_law),
            "final_answer_only_class_count": len(_law(worlds, "final_answer_only_sha256")),
            "assistant_message_only_class_count": len(_law(worlds, "assistant_message_only_sha256")),
            "content_history_merges_distinct_full_observations": any(
                item["same_content_distinct_full_observations"] for item in collisions
            ),
            "content_projection": "ordered message content strings; omits AIMessage type, id, status, response_metadata, usage_metadata, request envelopes, and graph/provider statuses",
            "interpretation": "Content-only projections merge source runs that differ in returned message metadata or raised status; final-answer-only projection also drops input history. This does not show that every helper adapter does so.",
        },
        "execution_boundary": {
            "original_source_module_imported": False,
            "execution_unit": "scoped exact source slices compiled into one explicit ModuleType namespace; callable globals are identity-checked and free-variable closures are rejected",
            "source_callable_executed": "model_node(state)",
            "source_state_schema_executed": "DiliState",
            "source_graph_statements_executed": [label for label, _ in graph_segments],
            "sandbox": "Host runner launches this worker with macOS Seatbelt: network, writes, process inspection/fork, Mach lookup, /Users except explicit source/runtime/driver paths, /private/var, temporary paths, and volumes denied.",
            "environment": "Caller environment is replaced by a small fixed environment before sandbox launch; no HOME, provider credentials, .env file, or API configuration is passed.",
        },
    }


def main() -> int:
    try:
        result = run()
    except Exception as error:
        result = {
            "capsule_id": "didilili-langgraphllm-one-node-finite-oracle-v1",
            "result": "REJECTED_FRONTIER_OR_RUNTIME_FAILURE",
            "fatal_error": {
                "type": f"{type(error).__module__}.{type(error).__qualname__}",
                "message": str(error)[:2000],
            },
        }
    print("CAPSULE_JSON:" + json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("result") == "PASS_CONDITIONAL_FINITE_DOMAIN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
