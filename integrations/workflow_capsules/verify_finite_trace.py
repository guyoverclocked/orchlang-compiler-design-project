#!/usr/bin/env python3
"""Independently replay bounded workflow trace certificates from JSON artifacts.

This verifier never imports or executes a source workflow. It recomputes exact
rational laws from the recorded finite schedules, checks both captured run
observations, re-hashes the pinned source slices and capsule worker, and emits a
small reviewable certificate alongside each input artifact.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any

from strict_json import StrictJSONError, loads as strict_loads, read_bytes as strict_read_bytes, validate_tree

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "research/scp_strengthening/workflow_capsules"
CERTIFICATE_DIR = ARTIFACT_DIR
MAX_WORLDS = 128
MAX_SUPPORT_ITEMS = 128
MAX_WEIGHT_DIGITS = 256
MAX_WEIGHT_BITS = 512
MAX_ARITHMETIC_BITS = 8192
_WEIGHT_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:/(?:[1-9][0-9]*))?\Z")
WORKERS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": ROOT / "integrations/workflow_capsules/worker.py",
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": ROOT / "integrations/workflow_capsules/joshua_kb_worker.py",
}
EXPECTED_WORKER_SHA256 = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": "97343b8fc5998deb2ca7c195d62414c4876187412532e990241d77a979a9c0b5",
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": "0cc31d2d6f258fa134d6b3bfc14930f0ef74fd756ef1d514340fbb07c1e25ac8",
}
EXPECTED_SEGMENTS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": [
        "DiliState", "model_node", "graph_init", "graph_add_node",
        "graph_start_edge", "graph_end_edge", "graph_compile",
    ],
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": [
        "AgentState", "get_kb_retriever", "wrap_model", "retrieve_documents",
        "prepare_augmented_prompt", "acall_model", "graph_init", "node_retrieve",
        "node_prepare", "node_model", "entry", "edge_retrieve_prepare",
        "edge_prepare_model", "edge_model_end", "graph_compile",
    ],
}
EXPECTED_SEGMENT_LINES = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "DiliState": [28, 33], "model_node": [46, 48], "graph_init": [52, 52],
        "graph_add_node": [53, 53], "graph_start_edge": [54, 54],
        "graph_end_edge": [55, 55], "graph_compile": [58, 58],
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "AgentState": [19, 24], "get_kb_retriever": [28, 44], "wrap_model": [47, 82],
        "retrieve_documents": [85, 121], "prepare_augmented_prompt": [124, 144],
        "acall_model": [147, 154], "graph_init": [158, 158], "node_retrieve": [161, 161],
        "node_prepare": [162, 162], "node_model": [163, 163], "entry": [166, 166],
        "edge_retrieve_prepare": [169, 169], "edge_prepare_model": [170, 170],
        "edge_model_end": [171, 171], "graph_compile": [174, 174],
    },
}
EXPECTED_SOURCE = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "repository": "didilili/ai-agents-from-zero",
        "commit": "9de20be80dad6d410268ae75f75cf94c355dd364",
        "path": "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364/案例与源码-3-LangGraph框架/01-helloworld/LangGraphLLM.py",
        "sha256": "b35741309de653d79e2cb403ebc5ddfa6b74383dd22f2e0d0142a1359225818b",
        "bytes": 6982,
        "license": "MIT",
        "url": "https://github.com/didilili/ai-agents-from-zero/blob/9de20be80dad6d410268ae75f75cf94c355dd364/%E6%A1%88%E4%BE%8B%E4%B8%8E%E6%BA%90%E7%A0%81-3-LangGraph%E6%A1%86%E6%9E%B6/01-helloworld/LangGraphLLM.py",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "repository": "JoshuaC215/agent-service-toolkit",
        "commit": "88ebfa1fadd1a207aa92115635abf7ed20d66a88",
        "path": "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py",
        "sha256": "6a96b47a58e855444fa410bef6e077220f578f188476a605aabeb88d88bf0ccc",
        "bytes": 6641,
        "license": "MIT",
        "url": "https://github.com/JoshuaC215/agent-service-toolkit/blob/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py",
    },
}
EXPECTED_MOCK_HASH = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": "a74b5f648f6c8627e3369cbf8679220ff0f55230dfe88d67a51ab44819b91b7c",
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": "2bfe8ef8388aa7f4ad124602c2aa2b1ef175cfd3e0d89f2e2aca720025d1bcbb",
}
EXPECTED_SUPPORT_HASH = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": "737b0e417db1464c46f255dd3dc545631c8c85716bc7605d316e72098209ea8f",
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": "54ff231f4aa847e7cf605a15d6af79b1b39ad7ef5692a08db4aea18a7bc0106c",
}
EXPECTED_RUNTIME = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "python": "3.14.6", "langgraph": "1.2.14", "langchain_core": "1.6.9",
        "langchain_full_package": "not installed; no full-langchain import was needed",
        "model_provider": "deterministic in-process mock; no API key or network",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "python": "3.14.6", "langgraph": "1.2.14", "langchain_core": "1.6.9",
        "langchain_aws": "not installed; production retriever replaced by explicit mock",
        "model_provider": "deterministic local BaseChatModel async oracle; no API key or network",
    },
}
EXPECTED_EVIDENCE_HASHES = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "claim": "66618da96d46ec6d6bc3e61d07e544d794f4e39105e655554f93274de12eccc0",
        "execution_boundary": "fdb36ebde10de4f439451517d393c2c821f034821196dfe74e179f74524497f2",
        "practical_counterexample": "579accad8415f2da1d9c2eac63b8c77fa8ac647a8437e05dee761a378b09072e",
        "exact_laws": "81766ad21d46a12edccf9d3253890c74d0becf3a81253f14364b58588cdceff4",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "claim": "9344dcc98516eb660f96b9546b6cc20a0d2ede203e8a5fe523f6a490e82cb73f",
        "execution_boundary": "11ef7ae2bfc90e1eb84b3678dfdeea42acd2c70d025d2b29b52eab69ef97319c",
        "practical_property": "3f2aa83613a7dfac27d024dce6173198fa484ad9a128607fa6f5c7b4b55429e4",
        "exact_laws": "d3a4e644352d51dc730ac504ca5aca458bd4f8c79c2fc67fb448e71f9a00ec03",
    },
}

REPLAY_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": (
        "world_id", "input_id", "response_id", "probability", "extracted_source_segments",
        "outcome", "run_status", "failure_reasons", "exception", "horizon_observed",
        "trace_projection", "content_only_projection", "final_answer_only_projection",
        "assistant_message_only_projection", "trace_sha256", "content_only_sha256",
        "final_answer_only_sha256", "assistant_message_only_sha256", "source_slice_binding_observation",
    ),
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": (
        "world_id", "probability", "extracted_source_segments", "outcome", "run_status",
        "failure_reasons", "exception", "horizon_observed", "trace_projection",
        "content_only_projection", "final_answer_only_projection", "assistant_message_only_projection",
        "trace_sha256", "content_only_sha256", "final_answer_only_sha256",
        "assistant_message_only_sha256", "source_slice_binding_observation",
    ),
}

ARTIFACT_CAPSULES = {
    "didilili-langgraphllm-one-node-finite-oracle-v1.json": "didilili-langgraphllm-one-node-finite-oracle-v1",
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1.json": "joshuac215-kb-agent-sequential-async-finite-oracle-v1",
}

WRAPPER_FIELDS = {
    "elapsed_seconds", "exit_code", "parse_error", "preflight", "result", "stderr_tail",
    "stdout_unparsed", "timed_out", "worker", "worker_sha256",
}
SOURCE_FIELDS = {"bytes", "commit", "license", "path", "repository", "segments", "selection_sha256", "sha256", "url"}
SEGMENT_FIELDS = {"label", "lines", "sha256"}
DEFINITION_FIELDS = {"mock_contract", "mock_contract_sha256", "source_segment_selection_sha256", "worker_sha256"}
REPLAY_OBJECT_FIELDS = {"compared_fields", "identical", "second_observation"}
RESULT_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "capsule_definition", "capsule_id", "claim", "exact_laws", "execution_boundary",
        "finite_support", "practical_counterexample", "result", "runtime", "source", "worlds",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "capsule_definition", "capsule_id", "claim", "exact_laws", "execution_boundary",
        "finite_support", "practical_property", "result", "runtime", "source", "worlds",
    },
}
CLAIM_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {"scope", "finite_domain_guarantee", "exclusions"},
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {"scope", "finite_domain_guarantee", "excluded"},
}
EXECUTION_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "original_source_module_imported", "execution_unit", "source_callable_executed",
        "source_state_schema_executed", "source_graph_statements_executed", "sandbox", "environment",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "source_module_imported", "execution_unit", "executed_original_source", "actual_runtime", "sandbox", "environment",
    },
}
PRACTICAL_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "property", "same_text", "response_finish_reasons", "response_usage", "model_statuses",
        "complete_trace_class_count", "message_content_history_class_count", "final_answer_only_class_count",
        "assistant_message_only_class_count", "content_history_merges_distinct_full_observations",
        "content_projection", "interpretation",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "property", "exception_world_count", "same_answer_text_across_retrieval_outcomes",
        "full_trace_class_count", "content_only_class_count", "final_answer_only_class_count",
        "content_history_merges_distinct_full_observations", "interpretation",
    },
}
FINITE_SUPPORT_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "elementary_world_count", "graph_recursion_limit", "input_domain_size", "input_states",
        "model_call_horizon", "model_responses", "response_support_size", "world_weight_rule",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "elementary_world_count", "graph_recursion_limit", "input_domain_size", "inputs",
        "model_horizon", "model_responses", "model_support_size", "retrieval_horizon",
        "retrieval_outcomes", "retrieval_support_size", "weight_rule",
    },
}
EXACT_LAW_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "complete_trace_equivalence", "content_only_equivalence", "complete_trace_law",
        "content_only_law", "final_answer_only_law", "assistant_message_only_law",
        "run_status_law", "model_response_status_law", "finish_reason_or_error_law",
        "same_content_distinct_observation_collisions", "weights_sum_to_one",
        "all_declared_worlds_accounted_for", "all_independent_replays_identical",
        "modeled_provider_error_world_count",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "complete_trace_equivalence", "content_only_equivalence", "complete_trace_law",
        "content_only_law", "final_answer_only_law", "assistant_message_only_law",
        "run_status_law", "retrieval_response_status_law", "model_response_status_law",
        "finish_reason_or_error_law", "same_content_distinct_full_observations_collisions",
        "weights_sum_to_one", "all_declared_worlds_accounted_for",
        "all_independent_replays_identical", "modeled_model_error_world_count",
    },
}
TRACE_FIELDS = {
    "didilili-langgraphllm-one-node-finite-oracle-v1": {
        "callable_returns", "graph_completed", "graph_status", "last_observed_state",
        "ordered_execution_events", "request_and_response_events", "terminal_state",
    },
    "joshuac215-kb-agent-sequential-async-finite-oracle-v1": {
        "completed", "error", "graph_status", "last_observed_state", "node_updates",
        "ordered_events", "terminal_state",
    },
}
EVENT_FIELDS = {
    "graph_start": ({"config", "input", "kind", "stream_mode"},),
    "graph_state": ({"kind", "ordinal", "state"},),
    "model_request": ({"envelope", "kind"},),
    "model_response": (
        {"finish_reason", "kind", "message", "response_id", "status", "usage"},
        {"exception_message", "exception_type", "kind", "response_id", "status"},
    ),
    "node_update": ({"kind", "node", "update"},),
    "graph_complete": ({"kind", "terminal"},),
    "graph_exception": ({"kind", "message", "type"},),
    "retriever_construct": ({"kind", "request"},),
    "retrieval_request": ({"envelope", "kind"},),
    "retrieval_response": (
        {"documents", "kind", "outcome_id", "status"},
        {"exception_message", "exception_type", "kind", "outcome_id", "status"},
    ),
    "source_log": ({"kind", "level", "message"},),
    "model_factory": ({"kind", "request"},),
}


class VerificationError(RuntimeError):
    pass


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    validate_tree(value, where="canonical capsule value")
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha_value(value: Any) -> str:
    return sha_bytes(canonical(value))


def fraction(value: str) -> Fraction:
    require(type(value) is str, "rational weights must be strings")
    require(len(value) <= 2 * MAX_WEIGHT_DIGITS + 1, "rational weight exceeds textual limit")
    require(_WEIGHT_RE.fullmatch(value) is not None, f"noncanonical rational weight {value!r}")
    parts = value.split("/")
    require(all(len(part) <= MAX_WEIGHT_DIGITS for part in parts), "rational weight exceeds digit limit")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise VerificationError(f"invalid rational weight {value!r}") from exc
    require(str(result) == value, f"rational weight is not reduced/canonical: {value!r}")
    require(
        result.numerator.bit_length() <= MAX_WEIGHT_BITS
        and result.denominator.bit_length() <= MAX_WEIGHT_BITS,
        "rational weight exceeds bit limit",
    )
    if result <= 0:
        raise VerificationError(f"nonpositive support weight {value!r}")
    return result


def _bounded_fraction(value: Fraction, where: str) -> Fraction:
    require(
        value.numerator.bit_length() <= MAX_ARITHMETIC_BITS
        and value.denominator.bit_length() <= MAX_ARITHMETIC_BITS,
        f"{where} exceeds exact arithmetic bit limit",
    )
    return value


def add_weights(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _bounded_fraction(left + right, where)


def multiply_weights(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _bounded_fraction(left * right, where)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_object(value: Any, fields: set[str], where: str) -> dict[str, Any]:
    require(type(value) is dict, f"{where} must be an object")
    require(set(value) == fields, f"{where} fields differ from the fixed capsule schema")
    return value


def require_exact_int(value: Any, where: str, expected: int | None = None) -> int:
    require(type(value) is int, f"{where} must be an integer (booleans are not integers here)")
    if expected is not None:
        require(value == expected, f"{where} must equal {expected}")
    return value


def _read_regular_beneath(root: Path, relative: Path) -> bytes:
    require(not relative.is_absolute() and ".." not in relative.parts, "source path escapes repository")
    root_real = root.resolve(strict=True)
    current = root_real
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise VerificationError(f"cannot inspect pinned source path: {exc}") from exc
        require(not stat.S_ISLNK(info.st_mode), "pinned source path contains a symlink")
        final = index == len(relative.parts) - 1
        require(stat.S_ISREG(info.st_mode) if final else stat.S_ISDIR(info.st_mode), "pinned source path has an unexpected file type")
    resolved = current.resolve(strict=True)
    require(resolved.is_relative_to(root_real), "resolved source path escapes repository")
    try:
        with current.open("rb") as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
    except OSError as exc:
        raise VerificationError(f"cannot read pinned source: {exc}") from exc
    require(len(raw) <= 32 * 1024 * 1024, "pinned source exceeds byte limit")
    return raw


def _check_result_schema(result: Any, capsule_id: str, worker_sha: str) -> dict[str, Any]:
    result = require_object(result, RESULT_FIELDS[capsule_id], "capsule result")
    require(result["capsule_id"] == capsule_id, "capsule ID changed")
    require(result["result"] == "PASS_CONDITIONAL_FINITE_DOMAIN", "capsule did not report a conditional finite-domain pass")
    for field in ("claim", "exact_laws", "execution_boundary", "finite_support", "practical_counterexample" if capsule_id.startswith("didilili") else "practical_property", "runtime", "source", "capsule_definition"):
        require(type(result[field]) is dict, f"result.{field} must be an object")
    require_object(result["claim"], CLAIM_FIELDS[capsule_id], "claim")
    require_object(result["execution_boundary"], EXECUTION_FIELDS[capsule_id], "execution_boundary")
    practical_key = "practical_counterexample" if capsule_id.startswith("didilili") else "practical_property"
    require_object(result[practical_key], PRACTICAL_FIELDS[capsule_id], practical_key)
    runtime = require_object(result["runtime"], set(EXPECTED_RUNTIME[capsule_id]), "runtime")
    require(runtime == EXPECTED_RUNTIME[capsule_id], "runtime dependency declaration changed")
    for name, expected_hash in EXPECTED_EVIDENCE_HASHES[capsule_id].items():
        require(sha_value(result[name]) == expected_hash, f"hash-bound {name} declaration changed")
    definition = require_object(result["capsule_definition"], DEFINITION_FIELDS, "capsule_definition")
    require(definition["worker_sha256"] == worker_sha, "capsule definition worker hash mismatch")
    require(definition["mock_contract_sha256"] == EXPECTED_MOCK_HASH[capsule_id], "mock contract hash differs from the frozen capsule premise")
    require(definition["mock_contract_sha256"] == sha_value(definition["mock_contract"]), "mock contract hash mismatch")

    finite = require_object(result["finite_support"], FINITE_SUPPORT_FIELDS[capsule_id], "finite_support")
    require(sha_value(finite) == EXPECTED_SUPPORT_HASH[capsule_id], "finite schedule support differs from the frozen domain")
    if capsule_id.startswith("didilili"):
        dimensions = {
            "input_domain_size": ("input_states", 2),
            "response_support_size": ("model_responses", 3),
            "elementary_world_count": ("worlds", 6),
        }
        require_exact_int(finite["model_call_horizon"], "model_call_horizon", 1)
        require_exact_int(finite["graph_recursion_limit"], "graph_recursion_limit", 6)
    else:
        dimensions = {
            "input_domain_size": ("inputs", 2),
            "retrieval_support_size": ("retrieval_outcomes", 2),
            "model_support_size": ("model_responses", 3),
            "elementary_world_count": ("worlds", 12),
        }
        require_exact_int(finite["retrieval_horizon"], "retrieval_horizon", 1)
        require_exact_int(finite["model_horizon"], "model_horizon", 1)
        require_exact_int(finite["graph_recursion_limit"], "graph_recursion_limit", 12)
    for count_field, (support_field, expected) in dimensions.items():
        require_exact_int(finite[count_field], count_field, expected)
        if support_field != "worlds":
            require(type(finite[support_field]) is list, f"finite_support.{support_field} must be an array")
            require(len(finite[support_field]) == expected, f"finite_support.{support_field} size mismatch")
    require(type(result["worlds"]) is list and len(result["worlds"]) <= MAX_WORLDS, "world list is invalid or over limit")
    require_exact_int(finite["elementary_world_count"], "elementary_world_count", len(result["worlds"]))
    require_object(result["exact_laws"], EXACT_LAW_FIELDS[capsule_id], "exact_laws")
    return result


def _check_wrapper(wrapper: Any, expected_capsule_id: str) -> tuple[dict[str, Any], str, dict[str, bool]]:
    wrapper = require_object(wrapper, WRAPPER_FIELDS, "execution wrapper")
    require_exact_int(wrapper["exit_code"], "wrapper.exit_code", 0)
    require(type(wrapper["timed_out"]) is bool and wrapper["timed_out"] is False, "wrapper timeout flag must be boolean false")
    require(wrapper["parse_error"] is None, "child output has a parse error")
    require(wrapper["stdout_unparsed"] is None, "child output contains unparsed stdout")
    require(type(wrapper["stderr_tail"]) is str, "wrapper.stderr_tail must be text")
    require(type(wrapper["elapsed_seconds"]) is float and wrapper["elapsed_seconds"] >= 0, "wrapper elapsed time must be a nonnegative finite decimal")
    worker = wrapper["worker"]
    require(type(worker) is str and worker == Path(WORKERS[expected_capsule_id]).name, "wrapper worker name mismatch")
    worker_sha = wrapper["worker_sha256"]
    require(type(worker_sha) is str and re.fullmatch(r"[0-9a-f]{64}", worker_sha) is not None, "wrapper worker hash is malformed")
    preflight = require_object(wrapper["preflight"], {"checks"}, "preflight")
    expected_checks = {"fork_denied", "network_denied", "unlisted_user_file_denied", "writes_denied"}
    checks = require_object(preflight["checks"], expected_checks, "preflight.checks")
    for name, value in checks.items():
        require(type(value) is bool and value is True, f"preflight {name} did not prove a denial")
    result = _check_result_schema(wrapper["result"], expected_capsule_id, worker_sha)
    return result, worker_sha, checks


def _check_trace_schema(trace: Any, capsule_id: str, world_id: str) -> None:
    trace = require_object(trace, TRACE_FIELDS[capsule_id], f"{world_id}.trace_projection")
    require(type(trace["graph_status"]) is str and trace["graph_status"] in {"complete", "provider_error"}, f"unknown graph status in {world_id}")
    completed = trace["graph_status"] == "complete"
    flag = trace["graph_completed"] if capsule_id.startswith("didilili") else trace["completed"]
    require(type(flag) is bool and flag is completed, f"completion flag type/value mismatch in {world_id}")
    require(type(trace["last_observed_state"]) is dict, f"last state is not an object in {world_id}")
    require(trace["terminal_state"] is None or type(trace["terminal_state"]) is dict, f"terminal state has unsupported type in {world_id}")
    if capsule_id.startswith("joshuac"):
        error = trace["error"]
        require(error is None or type(error) is dict, f"trace error has unsupported type in {world_id}")
        if error is not None:
            require_object(error, {"message", "type"}, f"{world_id}.trace.error")
            require(type(error["message"]) is str and type(error["type"]) is str, f"trace error fields are invalid in {world_id}")
        require((not completed) == (error is not None), f"trace error/status pair conflicts in {world_id}")
    event_key = "ordered_execution_events" if capsule_id.startswith("didilili") else "ordered_events"
    events = trace[event_key]
    require(type(events) is list and len(events) <= 256, f"ordered events are invalid or over limit in {world_id}")
    counts: dict[str, int] = defaultdict(int)
    sequence: list[str] = []
    for event in events:
        require(type(event) is dict and type(event.get("kind")) is str, f"malformed event in {world_id}")
        kind = event["kind"]
        require(kind in EVENT_FIELDS, f"unsupported event kind {kind!r} in {world_id}")
        require(set(event) in EVENT_FIELDS[kind], f"event fields differ from fixed {kind} schema in {world_id}")
        counts[kind] += 1
        sequence.append(kind)
        if kind == "graph_state":
            require_exact_int(event["ordinal"], f"{world_id}.graph_state.ordinal")
            require(type(event["state"]) is dict, f"graph state event is not an object in {world_id}")
            _check_state_schema(event["state"], capsule_id, f"{world_id}.graph_state[{event['ordinal']}]")
        if kind == "model_response":
            require(type(event["status"]) is str and event["status"] in {"returned", "raised"}, f"model status is invalid in {world_id}")
        if kind == "retrieval_response":
            require(type(event["status"]) is str and event["status"] in {"returned", "raised"}, f"retrieval status is invalid in {world_id}")
        if kind in {"graph_exception", "model_response", "retrieval_response"}:
            fields_to_check = ("exception_message", "exception_type") + (("message",) if kind == "graph_exception" else ())
            for field in fields_to_check:
                if field in event:
                    require(type(event[field]) is str, f"{world_id}.{kind}.{field} must be text")
    require(counts["graph_start"] == 1, f"graph start count mismatch in {world_id}")
    require(counts["model_request"] == 1 and counts["model_response"] == 1, f"model call horizon mismatch in {world_id}")
    if capsule_id.startswith("didilili"):
        require(counts["graph_state"] == (2 if completed else 1), f"Dili graph-state horizon mismatch in {world_id}")
        require(counts["node_update"] == (1 if completed else 0), f"Dili update horizon mismatch in {world_id}")
        require(counts["graph_complete"] == (1 if completed else 0), f"Dili terminal event mismatch in {world_id}")
        require(counts["graph_exception"] == (0 if completed else 1), f"Dili exception event mismatch in {world_id}")
        expected_sequence = (
            ["graph_start", "graph_state", "model_request", "model_response", "node_update", "graph_state", "graph_complete"]
            if completed else
            ["graph_start", "graph_state", "model_request", "model_response", "graph_exception"]
        )
    else:
        require(counts["retriever_construct"] == 1 and counts["retrieval_request"] == 1 and counts["retrieval_response"] == 1, f"retriever call horizon mismatch in {world_id}")
        require(counts["model_factory"] == 1, f"model factory count mismatch in {world_id}")
        require(counts["graph_state"] == (4 if completed else 3), f"Joshua graph-state horizon mismatch in {world_id}")
        require(counts["node_update"] == (3 if completed else 2), f"Joshua update horizon mismatch in {world_id}")
        require(counts["graph_complete"] == (1 if completed else 0), f"Joshua terminal event mismatch in {world_id}")
        require(counts["graph_exception"] == (0 if completed else 1), f"Joshua exception event mismatch in {world_id}")
        prefix = [
            "graph_start", "graph_state", "retriever_construct", "retrieval_request", "retrieval_response",
            "source_log", "node_update", "graph_state", "node_update", "graph_state", "model_factory",
            "model_request", "model_response",
        ]
        expected_sequence = prefix + (["node_update", "graph_state", "graph_complete"] if completed else ["graph_exception"])
    require(sequence == expected_sequence, f"event order or stopping horizon differs from the fixed capsule path in {world_id}")


def _check_state_schema(state: Any, capsule_id: str, where: str) -> None:
    require(type(state) is dict, f"{where} must be an object")
    allowed = (
        {"messages"}
        if capsule_id.startswith("didilili")
        else {"messages", "retrieved_documents"}
    )
    if not capsule_id.startswith("didilili"):
        allowed_variants = [{"messages"}, allowed, allowed | {"kb_documents"}]
        require(set(state) in [set(variant) for variant in allowed_variants], f"{where} fields differ from the source state schema")
        if "retrieved_documents" in state:
            require(type(state["retrieved_documents"]) is list, f"{where}.retrieved_documents must be an array")
            for index, document in enumerate(state["retrieved_documents"]):
                document = require_object(document, {"content", "id", "relevance_score", "source", "title"}, f"{where}.retrieved_documents[{index}]")
                require(all(type(document[field]) is str for field in ("content", "id", "source", "title")), f"{where}.retrieved_documents[{index}] text fields are malformed")
                require(type(document["relevance_score"]) in {int, float}, f"{where}.retrieved_documents[{index}] score is malformed")
        if "kb_documents" in state:
            require(type(state["kb_documents"]) is str, f"{where}.kb_documents must be text")
    else:
        require(set(state) == {"messages"}, f"{where} fields differ from the Dili source state schema")
    messages = state["messages"]
    require(type(messages) is list, f"{where}.messages must be an array")
    for index, message in enumerate(messages):
        message = require_object(message, {"$message"}, f"{where}.messages[{index}]")
        body = require_object(message["$message"], {"data", "type"}, f"{where}.messages[{index}].$message")
        data = body["data"]
        require(type(data) is dict, f"{where}.messages[{index}] data must be an object")
        kind = body["type"]
        require(type(kind) is str and kind in {"human", "system", "ai"}, f"{where}.messages[{index}] has an unsupported message type")
        expected = (
            {"additional_kwargs", "content", "id", "name", "response_metadata", "type"}
            if kind in {"human", "system"}
            else (
                {"additional_kwargs", "content", "id", "invalid_tool_calls", "name", "response_metadata", "status", "tool_calls", "type", "usage_metadata"}
                if capsule_id.startswith("didilili")
                else {"additional_kwargs", "content", "id", "invalid_tool_calls", "name", "response_metadata", "tool_calls", "type", "usage_metadata"}
            )
        )
        require(set(data) == expected, f"{where}.messages[{index}] data fields differ from fixed message projection")
        require(data["type"] == kind and type(data["content"]) is str, f"{where}.messages[{index}] type/content mismatch")
        require(data["additional_kwargs"] == {} and type(data["response_metadata"]) is dict, f"{where}.messages[{index}] metadata is malformed")
        if kind == "ai":
            require(type(data["invalid_tool_calls"]) is list and type(data["tool_calls"]) is list, f"{where}.messages[{index}] tool-call fields are malformed")
            require(type(data["usage_metadata"]) is dict, f"{where}.messages[{index}] usage metadata is malformed")
            if capsule_id.startswith("didilili"):
                require(data["status"] == "success", f"{where}.messages[{index}] AI status is unsupported")


def _check_world_schema(world: Any, capsule_id: str) -> dict[str, Any]:
    fields = set(REPLAY_FIELDS[capsule_id]) | {"independent_replay"}
    world = require_object(world, fields, "world observation")
    replay = require_object(world["independent_replay"], REPLAY_OBJECT_FIELDS, "independent_replay")
    compared = replay["compared_fields"]
    require(type(compared) is list and all(type(item) is str for item in compared), "compared_fields must be a string array")
    require(len(compared) == len(set(compared)), "compared_fields contains duplicates")
    require(tuple(compared) == REPLAY_FIELDS[capsule_id], "compared_fields does not equal the fixed complete per-capsule set")
    second = require_object(replay["second_observation"], set(REPLAY_FIELDS[capsule_id]), "second_observation")
    require(set(world) - {"independent_replay"} == set(second), "primary/replay field sets differ")
    require(type(replay["identical"]) is bool and replay["identical"] is True, "repeat execution was not marked exactly true")
    for field in REPLAY_FIELDS[capsule_id]:
        require(canonical(world[field]) == canonical(second[field]), f"independent replay differs in required field {field}")
    require(type(world["world_id"]) is str and world["world_id"], "world_id must be nonempty text")
    require(type(world["probability"]) is str, "world probability must be a rational string")
    require(type(world["run_status"]) is str and world["run_status"] in {"complete", "provider_error"}, "world status is unsupported")
    require(type(world["outcome"]) is str and world["outcome"] in {"complete", "modeled_error"}, "world outcome is unsupported")
    require((world["run_status"] == "complete") == (world["outcome"] == "complete"), "world outcome/status pair conflicts")
    require(type(world["failure_reasons"]) is list and all(type(x) is str for x in world["failure_reasons"]), "failure_reasons must be an array of strings")
    require(world["failure_reasons"] == [], "finite capsule world records a failure reason")
    exception = world["exception"]
    require(exception is None or type(exception) is dict, "world exception must be null or an object")
    if exception is not None:
        require_object(exception, {"message", "type"}, f"{world['world_id']}.exception")
        require(type(exception["message"]) is str and type(exception["type"]) is str, "exception fields must be text")
    require((world["run_status"] == "provider_error") == (exception is not None), "world exception/status pair conflicts")
    horizon = world["horizon_observed"]
    require(type(horizon) is dict, "horizon_observed must be an object")
    if capsule_id.startswith("didilili"):
        require_object(horizon, {"graph_recursion_limit", "graph_value_events", "model_calls", "node_updates"}, "horizon_observed")
        expected_horizon = {
            "graph_recursion_limit": 6,
            "graph_value_events": 2 if world["run_status"] == "complete" else 1,
            "model_calls": 1,
            "node_updates": 1 if world["run_status"] == "complete" else 0,
        }
    else:
        require_object(horizon, {"graph_recursion_limit", "graph_value_events", "model_calls", "node_update_path", "retriever_calls", "retriever_constructors"}, "horizon_observed")
        expected_horizon = {
            "graph_recursion_limit": 12,
            "graph_value_events": 4 if world["run_status"] == "complete" else 3,
            "model_calls": 1,
            "node_update_path": ["retrieve_documents", "prepare_augmented_prompt", "model"] if world["run_status"] == "complete" else ["retrieve_documents", "prepare_augmented_prompt"],
            "retriever_calls": 1,
            "retriever_constructors": 1,
        }
    for name, value in horizon.items():
        if name == "node_update_path":
            require(type(value) is list and all(type(item) is str for item in value), "node_update_path must be a string array")
        else:
            require_exact_int(value, f"horizon_observed.{name}")
    require(horizon == expected_horizon, "observed finite horizon differs from the fixed capsule schedule")
    _check_trace_schema(world["trace_projection"], capsule_id, world["world_id"])
    return world


def _check_source(result: dict[str, Any], capsule_id: str) -> list[dict[str, Any]]:
    source = require_object(result["source"], SOURCE_FIELDS, "source manifest")
    expected_source = EXPECTED_SOURCE[capsule_id]
    for field, expected in expected_source.items():
        require(type(source[field]) is type(expected), f"source.{field} has the wrong JSON type")
        require(source[field] == expected, f"source.{field} differs from the fixed pinned-source identity")
    require_exact_int(source["bytes"], "source.bytes", expected_source["bytes"])
    relative = Path(source["path"])
    require(relative.as_posix().startswith("output/publication_upgrade/corpus/sources/"), "source is outside the allowed development corpus")
    raw = _read_regular_beneath(ROOT, relative)
    require(len(raw) == source["bytes"], "pinned source byte length mismatch")
    require(sha_bytes(raw) == source["sha256"], "pinned whole-source SHA256 mismatch")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VerificationError("pinned source is not valid UTF-8") from exc
    tree = ast.parse(text, filename=str(relative))
    entries = source["segments"]
    require(type(entries) is list and len(entries) == len(EXPECTED_SEGMENTS[capsule_id]), "source segment list has wrong size")
    for entry in entries:
        require_object(entry, SEGMENT_FIELDS, "source segment")
    labels = [entry["label"] for entry in entries]
    require(all(type(label) is str for label in labels), "source segment labels must be text")
    require(labels == EXPECTED_SEGMENTS[capsule_id], "source-slice selection has a missing, extra, or reordered span")
    recomputed = []
    top_level_statements = [node for node in tree.body if isinstance(node, ast.stmt)]
    for entry in entries:
        require_object(entry, SEGMENT_FIELDS, "source segment")
        lines = entry["lines"]
        require(type(lines) is list and len(lines) == 2, "malformed segment line span")
        require_exact_int(lines[0], f"segment {entry['label']} start line")
        require_exact_int(lines[1], f"segment {entry['label']} end line")
        require(lines == EXPECTED_SEGMENT_LINES[capsule_id][entry["label"]], f"source segment lines changed for {entry['label']}")
        candidates = [node for node in top_level_statements if node.lineno == lines[0] and node.end_lineno == lines[1]]
        require(len(candidates) == 1, f"segment {entry['label']} does not identify one top-level source statement")
        segment = ast.get_source_segment(text, candidates[0])
        require(segment is not None, f"cannot extract exact source text for {entry['label']}")
        segment_sha = sha_bytes(segment.encode("utf-8"))
        require(segment_sha == entry["sha256"], f"source segment hash mismatch for {entry['label']}")
        recomputed.append({"label": entry["label"], "lines": lines, "sha256": segment_sha})
    selection_hash = sha_value(recomputed)
    require(source.get("selection_sha256") == selection_hash, "source selection manifest hash mismatch")
    definition = require_object(result["capsule_definition"], DEFINITION_FIELDS, "capsule_definition")
    require(definition.get("source_segment_selection_sha256") == selection_hash, "capsule definition does not bind source selection")
    require(definition.get("mock_contract_sha256") == sha_value(definition["mock_contract"]), "mock contract hash mismatch")
    require(definition["mock_contract_sha256"] == EXPECTED_MOCK_HASH[capsule_id], "mock contract differs from the frozen capsule premise")
    return recomputed


def _projection_from_trace(capsule_id: str, trace: dict[str, Any]) -> tuple[Any, Any, Any]:
    state = trace["last_observed_state"]
    messages = state.get("messages") if isinstance(state, dict) else None
    require(isinstance(messages, list), "last observed state has no declared messages list")
    content = [
        message.get("$message", {}).get("data", {}).get("content")
        for message in messages if isinstance(message, dict)
    ]
    completed = trace.get("graph_status") == "complete"
    if capsule_id == "didilili-langgraphllm-one-node-finite-oracle-v1":
        require(trace.get("graph_completed") is completed, "Dili completion flag conflicts with graph status")
    else:
        require(trace.get("completed") is completed, "Joshua completion flag conflicts with graph status")
    terminal_messages = trace.get("terminal_state")
    if completed:
        require(isinstance(terminal_messages, dict), "completed run lacks terminal state")
        terminal_messages = terminal_messages.get("messages")
        require(isinstance(terminal_messages, list) and terminal_messages, "completed run lacks terminal messages")
        final_answer = terminal_messages[-1].get("$message", {}).get("data", {}).get("content")
        assistant = terminal_messages[-1]
    else:
        require(trace.get("terminal_state") is None, "error run must have no terminal state")
        final_answer = None
        assistant = None
    return content, final_answer, assistant


def _law(worlds: list[dict[str, Any]], hash_key: str, projection_key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for world in worlds:
        projection_hash = world[hash_key]
        projection = world[projection_key]
        require(sha_value(projection) == projection_hash, f"projection hash mismatch in {world['world_id']}:{projection_key}")
        if projection_hash not in groups:
            groups[projection_hash] = {"weight": Fraction(0), "world_ids": [], "representative": projection}
        groups[projection_hash]["weight"] = add_weights(
            groups[projection_hash]["weight"], fraction(world["probability"]), "observer-law accumulation"
        )
        groups[projection_hash]["world_ids"].append(world["world_id"])
    law = []
    for projection_hash, group in sorted(groups.items()):
        weight = group["weight"]
        law.append({
            "projection_sha256": projection_hash,
            "weight": f"{weight.numerator}/{weight.denominator}",
            "world_ids": group["world_ids"],
            "representative": group["representative"],
        })
    return law


def _status_law(worlds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        status = world["run_status"]
        require(type(status) is str, "run status must be a string")
        groups[status] = add_weights(groups[status], fraction(world["probability"]), "status-law accumulation")
    return [
        {"status": status, "weight": f"{weight.numerator}/{weight.denominator}"}
        for status, weight in sorted(groups.items())
    ]


def _event_law(worlds: list[dict[str, Any]], event_kind: str, field: str, event_key: str) -> list[dict[str, Any]]:
    groups: dict[str, Fraction] = defaultdict(Fraction)
    for world in worlds:
        events = world["trace_projection"][event_key]
        matches = [event for event in events if event.get("kind") == event_kind]
        require(len(matches) == 1, f"{world['world_id']} has {len(matches)} {event_kind} observations")
        value = matches[0].get(field)
        require(value is None or type(value) is str, f"{world['world_id']} has a non-text {event_kind}.{field}")
        label = value if value is not None else "raised"
        groups[label] = add_weights(
            groups[label],
            fraction(world["probability"]),
            "event-law accumulation",
        )
    return [
        {"value": value, "weight": f"{weight.numerator}/{weight.denominator}"}
        for value, weight in sorted(groups.items())
    ]


def _support(result: dict[str, Any], capsule_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None]:
    finite = result["finite_support"]
    if capsule_id == "didilili-langgraphllm-one-node-finite-oracle-v1":
        return finite["input_states"], finite["model_responses"], None
    return finite["inputs"], finite["retrieval_outcomes"], finite["model_responses"]


def _event_once(events: list[dict[str, Any]], kind: str, world_id: str) -> dict[str, Any]:
    found = [event for event in events if event["kind"] == kind]
    require(len(found) == 1, f"{world_id} has an unsupported {kind} count")
    return found[0]


def _message_projection(data: dict[str, Any], message_type: str) -> dict[str, Any]:
    return {"$message": {"type": message_type, "data": data}}


def _expected_ai_message(response: dict[str, Any], capsule_id: str) -> dict[str, Any]:
    finish = response["response_metadata"]["finish_reason"]
    model = response["response_metadata"]["model_name"]
    data: dict[str, Any] = {
        "additional_kwargs": {},
        "content": response["content"],
        "id": response["id"],
        "invalid_tool_calls": [],
        "name": None,
        "response_metadata": {"finish_reason": finish, "model_name": model},
        "tool_calls": [],
        "type": "ai",
        "usage_metadata": response["usage_metadata"],
    }
    if capsule_id.startswith("didilili"):
        data["status"] = "success"
    return _message_projection(data, "ai")


def _check_model_schedule(
    world: dict[str, Any], capsule_id: str, response_case: dict[str, Any], model_event: dict[str, Any]
) -> None:
    require(model_event["response_id"] == response_case["response_id"], f"model response ID differs from declared schedule in {world['world_id']}")
    if response_case["kind"] == "exception":
        require(model_event["status"] == "raised", f"declared model exception was not raised in {world['world_id']}")
        require(model_event["exception_type"] == response_case["exception_type"], f"model exception type differs from schedule in {world['world_id']}")
        require(model_event["exception_message"] == response_case["exception_message"], f"model exception message differs from schedule in {world['world_id']}")
        require(world["exception"] == {"message": response_case["exception_message"], "type": f"builtins.{response_case['exception_type']}"}, f"world exception differs from model schedule in {world['world_id']}")
        require(world["run_status"] == "provider_error" and world["outcome"] == "modeled_error", f"model error stop status differs in {world['world_id']}")
        require(model_event["status"] == "raised", f"model error status was elided in {world['world_id']}")
    else:
        require(response_case["kind"] == "returned", f"unsupported declared model response kind in {world['world_id']}")
        require(model_event["status"] == "returned", f"declared model return was not returned in {world['world_id']}")
        expected_message = _expected_ai_message(response_case, capsule_id)
        require(canonical(model_event["message"]) == canonical(expected_message), f"model message or metadata differs from declared response in {world['world_id']}")
        require(model_event["finish_reason"] == response_case["response_metadata"]["finish_reason"], f"model finish reason differs from schedule in {world['world_id']}")
        usage = {key: response_case["usage_metadata"][key] for key in ("input_tokens", "output_tokens", "total_tokens")}
        require(model_event["usage"] == usage, f"model usage differs from declared response in {world['world_id']}")
        require(world["exception"] is None and world["run_status"] == "complete" and world["outcome"] == "complete", f"returned model response has an error stop in {world['world_id']}")


def _check_retrieval_schedule(
    world: dict[str, Any], retrieval_case: dict[str, Any], request_event: dict[str, Any], response_event: dict[str, Any], query: str
) -> None:
    require(request_event["envelope"] == {"args": [query], "kwargs": {}, "method": "ainvoke"}, f"retrieval request envelope differs from input in {world['world_id']}")
    require(response_event["outcome_id"] == retrieval_case["outcome_id"], f"retrieval response ID differs from declared schedule in {world['world_id']}")
    if retrieval_case["kind"] == "exception":
        require(response_event["status"] == "raised", f"declared retrieval exception was not raised in {world['world_id']}")
        require(response_event["exception_type"] == retrieval_case["exception_type"], f"retrieval exception type differs from schedule in {world['world_id']}")
        require(response_event["exception_message"] == retrieval_case["exception_message"], f"retrieval exception message differs from schedule in {world['world_id']}")
        require("documents" not in response_event, f"raised retrieval unexpectedly returned documents in {world['world_id']}")
    else:
        document = retrieval_case["document"]
        expected = [{
            "$type": "langchain_core.documents.base.Document",
            "id": None,
            "metadata": {
                "id": document["id"], "score": document["score"],
                "source": document["source"], "title": document["title"],
            },
            "page_content": document["content"],
        }]
        require(retrieval_case["kind"] == "success", f"unsupported declared retrieval kind in {world['world_id']}")
        require(response_event["status"] == "returned" and canonical(response_event["documents"]) == canonical(expected), f"retrieved documents differ from declared schedule in {world['world_id']}")


def _check_worlds(result: dict[str, Any], capsule_id: str) -> dict[str, Any]:
    worlds = [_check_world_schema(world, capsule_id) for world in result["worlds"]]
    first, second, third = _support(result, capsule_id)
    supports = [first, second] if third is None else [first, second, third]
    for support in supports:
        require(all(type(item) is dict for item in support), "schedule support entries must be objects")
        ids = [item.get("input_id", item.get("response_id", item.get("outcome_id"))) for item in support]
        require(all(type(item_id) is str and item_id for item_id in ids), "schedule identifiers must be nonempty strings")
        require(len(ids) == len(set(ids)), "support dimension has duplicate schedule IDs")
        total = Fraction(0)
        for item in support:
            total = add_weights(total, fraction(item["weight"]), "support weight accumulation")
        require(total == 1, "support weights do not sum to one")
    expected_ids: list[str] = []
    expected_weights: dict[str, Fraction] = {}
    if third is None:
        for input_case in first:
            for response_case in second:
                world_id = f"{input_case['input_id']}__{response_case['response_id']}"
                expected_ids.append(world_id)
                expected_weights[world_id] = multiply_weights(fraction(input_case["weight"]), fraction(response_case["weight"]), "schedule weight product")
    else:
        for input_case in first:
            for retrieval_case in second:
                for model_case in third:
                    world_id = f"{input_case['input_id']}__{retrieval_case['outcome_id']}__{model_case['response_id']}"
                    expected_ids.append(world_id)
                    product = multiply_weights(fraction(input_case["weight"]), fraction(retrieval_case["weight"]), "schedule weight product")
                    expected_weights[world_id] = multiply_weights(product, fraction(model_case["weight"]), "schedule weight product")
    observed_ids = [world["world_id"] for world in worlds]
    require(observed_ids == expected_ids, "world enumeration is incomplete, duplicated, or out of declared order")
    require_exact_int(result["finite_support"]["elementary_world_count"], "elementary_world_count", len(expected_ids))
    require(len(worlds) == len(expected_ids), "observed world count mismatch")

    source_segments = result["source"]["segments"]
    source_snippets = [
        {"label": segment["label"], "source_lines": segment["lines"], "segment_sha256": segment["sha256"]}
        for segment in source_segments
    ]
    retrieval_by_id = {item["outcome_id"]: item for item in second} if third is not None else {}
    input_by_id = {item["input_id"]: item for item in first}
    for world in worlds:
        world_id = world["world_id"]
        expected_weight = expected_weights[world_id]
        require(fraction(world["probability"]) == expected_weight, f"schedule weight mismatch for {world_id}")
        require(world["outcome"] in {"complete", "modeled_error"}, f"unaccounted outcome at {world_id}")
        require(world["failure_reasons"] == [], f"failure reasons present at {world_id}")
        require(world["extracted_source_segments"] == source_snippets, f"selected slices changed at {world_id}")
        observation = {key: world[key] for key in REPLAY_FIELDS[capsule_id]}
        replay = world["independent_replay"]["second_observation"]
        require(set(observation) == set(replay), f"replay field set mismatch at {world_id}")
        require(all(canonical(observation[key]) == canonical(replay[key]) for key in observation), f"replay observation differs at {world_id}")
        require(world["independent_replay"]["identical"] is True, f"replay marked nondeterministic at {world_id}")
        require(sha_value(replay["trace_projection"]) == replay["trace_sha256"], f"second trace hash mismatch at {world_id}")
        require(sha_value(replay["content_only_projection"]) == replay["content_only_sha256"], f"second content hash mismatch at {world_id}")
        trace = world["trace_projection"]
        require(sha_value(trace) == world["trace_sha256"], f"complete trace hash mismatch at {world_id}")
        event_list = trace["ordered_execution_events"] if third is None else trace["ordered_events"]
        state_events = [event for event in event_list if event["kind"] == "graph_state"]
        require([event["ordinal"] for event in state_events] == list(range(1, len(state_events) + 1)), f"graph-state ordinals are incomplete in {world_id}")
        require(canonical(state_events[-1]["state"]) == canonical(trace["last_observed_state"]), f"last observed state differs from final stream state in {world_id}")
        updates = [{"node": event["node"], "update": event["update"]} for event in event_list if event["kind"] == "node_update"]
        if third is None:
            require(canonical(trace["callable_returns"]) == canonical(updates), f"callable return trace differs from node updates in {world_id}")
            requests = [event for event in event_list if event["kind"] in {"model_request", "model_response"}]
            require(canonical(trace["request_and_response_events"]) == canonical(requests), f"Dili request/response projection is incomplete in {world_id}")
        else:
            require(canonical(trace["node_updates"]) == canonical(updates), f"Joshua node update projection differs from ordered events in {world_id}")
        if world["run_status"] == "complete":
            require(canonical(trace["terminal_state"]) == canonical(trace["last_observed_state"]), f"terminal state differs from final stream state in {world_id}")
        graph_starts = [event for event in event_list if event.get("kind") == "graph_start"]
        require(len(graph_starts) == 1, f"graph invocation envelope missing at {world_id}")
        graph_start = graph_starts[0]
        expected_config = (
            {"recursion_limit": result["finite_support"]["graph_recursion_limit"]}
            if third is None
            else {"configurable": {"model": "finite-kb-model-v1"}, "recursion_limit": result["finite_support"]["graph_recursion_limit"]}
        )
        require(graph_start.get("config") == expected_config, f"graph config envelope mismatch at {world_id}")
        require(graph_start.get("stream_mode") == ["updates", "values"], f"graph stream-mode envelope mismatch at {world_id}")
        initial_states = [event.get("state") for event in event_list if event.get("kind") == "graph_state" and event.get("ordinal") == 1]
        require(len(initial_states) == 1 and canonical(graph_start.get("input")) == canonical(initial_states[0]), f"graph input state mismatch at {world_id}")
        input_id = world["input_id"] if third is None else world_id.split("__", 2)[0]
        input_case = input_by_id[input_id]
        initial_messages = initial_states[0].get("messages")
        require(type(initial_messages) is list and len(initial_messages) == 1, f"initial message history differs from fixed one-message input in {world_id}")
        human_data = {
            "additional_kwargs": {},
            "content": input_case["content"] if third is None else input_case["query"],
            "id": f"input-{input_id}" if third is None else f"{input_id}-human",
            "name": None,
            "response_metadata": {},
            "type": "human",
        }
        expected_human = _message_projection(human_data, "human")
        require(canonical(initial_messages[0]) == canonical(expected_human), f"initial input message differs from declared input schedule in {world_id}")
        model_request_event = _event_once(event_list, "model_request", world_id)
        if third is None:
            expected_model_envelope = {"args": [[expected_human]], "kwargs": {}, "method": "invoke"}
            require(canonical(model_request_event["envelope"]) == canonical(expected_model_envelope), f"Dili model request envelope differs from declared input in {world_id}")
        content, final_answer, assistant = _projection_from_trace(capsule_id, trace)
        require(content == world["content_only_projection"], f"message-content projection mismatch at {world_id}")
        require(final_answer == world["final_answer_only_projection"], f"final-answer projection mismatch at {world_id}")
        require(assistant == world["assistant_message_only_projection"], f"assistant-message projection mismatch at {world_id}")
        require(sha_value(content) == world["content_only_sha256"], f"message-content hash mismatch at {world_id}")
        require(sha_value(final_answer) == world["final_answer_only_sha256"], f"final-answer hash mismatch at {world_id}")
        require(sha_value(assistant) == world["assistant_message_only_sha256"], f"assistant-message hash mismatch at {world_id}")
        require(world["run_status"] == trace["graph_status"], f"run status does not match trace status at {world_id}")
        response_id = world["response_id"] if third is None else world_id.split("__", 2)[2]
        model_case = next((case for case in (second if third is None else third) if case["response_id"] == response_id), None)
        require(model_case is not None, f"model schedule support is missing {response_id!r} at {world_id}")
        model_event = _event_once(event_list, "model_response", world_id)
        _check_model_schedule(world, capsule_id, model_case, model_event)
        final_messages = trace["last_observed_state"]["messages"]
        if world["run_status"] == "complete":
            require(final_messages and canonical(final_messages[-1]) == canonical(model_event["message"]), f"terminal AI message differs from scheduled response in {world_id}")
        else:
            require(not any(message["$message"]["type"] == "ai" for message in final_messages), f"provider error state contains an unreturned AI message in {world_id}")
        if world["run_status"] == "provider_error":
            require(trace["terminal_state"] is None, f"provider error unexpectedly has terminal state at {world_id}")
            exception_event = _event_once(event_list, "graph_exception", world_id)
            require(world["exception"] == {"message": exception_event["message"], "type": exception_event["type"]}, f"graph exception differs from world status in {world_id}")
            if third is not None:
                require(trace["error"] == world["exception"], f"Joshua trace error differs from world status in {world_id}")
        elif third is not None:
            require(trace["error"] is None, f"completed Joshua graph retains an error in {world_id}")
        if third is None:
            binding = world["source_slice_binding_observation"]
            binding = require_object(binding, {"callables", "state_class_module_matches_namespace"}, f"{world_id}.source_slice_binding_observation")
            require(binding["state_class_module_matches_namespace"] is True, f"Dili state class binding mismatch at {world_id}")
            callables = require_object(binding["callables"], {"model_node"}, f"{world_id}.source callables")
            model_binding = require_object(callables["model_node"], {"free_variables", "globals_identity_matches_namespace", "module_name"}, f"{world_id}.model_node binding")
            require(model_binding["globals_identity_matches_namespace"] is True and model_binding["free_variables"] == [], f"Dili callable binding mismatch at {world_id}")
            require(model_binding["module_name"] == f"_capsule_didilili_{world_id.replace('__', '_')}", f"Dili source module name changed at {world_id}")
        else:
            event_key = "ordered_events"
            input_id, retrieval_id, _model_id = world_id.split("__", 2)
            retrieval_case = retrieval_by_id[retrieval_id]
            retrieval_request = _event_once(event_list, "retrieval_request", world_id)
            retrieval_response = _event_once(event_list, "retrieval_response", world_id)
            _check_retrieval_schedule(world, retrieval_case, retrieval_request, retrieval_response, input_case["query"])
            retriever_construct = _event_once(event_list, "retriever_construct", world_id)
            require(retriever_construct["request"] == {
                "knowledge_base_id": "finite-kb-fixture",
                "retrieval_config": {"vectorSearchConfiguration": {"numberOfResults": 3}},
            }, f"retriever construction request changed in {world_id}")
            model_factory = _event_once(event_list, "model_factory", world_id)
            require(model_factory["request"] == {"model_id": "finite-kb-model-v1"}, f"model factory request changed in {world_id}")
            source_log = _event_once(event_list, "source_log", world_id)
            if retrieval_case["kind"] == "success":
                expected_log = {"kind": "source_log", "level": "info", "message": f"Retrieved 1 documents for query: {input_case['query']}..."}
            else:
                expected_log = {"kind": "source_log", "level": "error", "message": f"Error retrieving documents: {retrieval_case['exception_message']}"}
            require(canonical(source_log) == canonical(expected_log), f"retriever logger observation changed in {world_id}")
            retrieved_state = trace["last_observed_state"].get("retrieved_documents")
            if retrieval_case["kind"] == "success":
                document = retrieval_case["document"]
                expected_state_documents = [{
                    "content": document["content"], "id": document["id"],
                    "relevance_score": document["score"], "source": document["source"],
                    "title": document["title"],
                }]
            else:
                expected_state_documents = []
            require(canonical(retrieved_state) == canonical(expected_state_documents), f"terminal retrieval state differs from declared retrieval schedule in {world_id}")
            model_requests = [event for event in trace[event_key] if event.get("kind") == "model_request"]
            require(len(model_requests) == 1, f"model request missing from closure observation at {world_id}")
            require(set(model_requests[0]["envelope"]) == {"kwargs", "messages", "method", "stop"}, f"model request envelope fields are incomplete at {world_id}")
            require(model_requests[0]["envelope"]["kwargs"] == {} and model_requests[0]["envelope"]["method"] == "BaseChatModel._agenerate" and model_requests[0]["envelope"]["stop"] is None, f"model request boundary changed at {world_id}")
            messages = model_requests[0]["envelope"].get("messages")
            require(isinstance(messages, list) and len(messages) == 2, f"unsupported source wrapper request at {world_id}")
            system_msg = require_object(messages[0], {"$message"}, f"{world_id}.model_request.system")
            system_body = require_object(system_msg["$message"], {"data", "type"}, f"{world_id}.model_request.system.$message")
            system = require_object(system_body["data"], {"additional_kwargs", "content", "id", "name", "response_metadata", "type"}, f"{world_id}.model_request.system.data")
            human_msg = require_object(messages[1], {"$message"}, f"{world_id}.model_request.human")
            human_body = require_object(human_msg["$message"], {"data", "type"}, f"{world_id}.model_request.human.$message")
            human = require_object(human_body["data"], {"additional_kwargs", "content", "id", "name", "response_metadata", "type"}, f"{world_id}.model_request.human.data")
            require(system_body["type"] == "system" and system["type"] == "system", f"system message type changed in {world_id}")
            require(type(system["content"]) is str, f"system prompt is not text in {world_id}")
            require(system["id"] is None and system["name"] is None and system["additional_kwargs"] == {} and system["response_metadata"] == {}, f"system message metadata changed in {world_id}")
            require(human_body["type"] == "human", f"human message type changed in {world_id}")
            require(canonical(messages[1]) == canonical(expected_human), f"model request human history differs from declared input in {world_id}")
            system_text = system.get("content", "") if isinstance(system, dict) else ""
            found = retrieval_case["kind"] == "success"
            closure = {
                "model_request_count": 1,
                "system_message_observed": isinstance(system, dict) and system.get("type") == "system",
                "human_message_history_preserved": (
                    isinstance(human, dict)
                    and human.get("type") == "human"
                    and human.get("content") == input_case["query"]
                    and human.get("id") == f"{input_id}-human"
                ),
                "retrieved_document_closure_observed": (
                    found
                    and isinstance(system_text, str)
                    and "fixture://release-notes" in system_text
                    and "Release notes" in system_text
                    and str(retrieval_case["document"]["content"]) in system_text
                ),
                "no_documents_closure_observed": (
                    not found
                    and isinstance(system_text, str)
                    and "No relevant documents were found" in system_text
                    and "fixture://release-notes" not in system_text
                ),
            }
            binding = world["source_slice_binding_observation"]
            binding = require_object(binding, {"nested_prompt_closure", "state_class_module_matches_namespace", "top_level_callables"}, f"{world_id}.source_slice_binding_observation")
            require(binding["state_class_module_matches_namespace"] is True, f"source state namespace mismatch at {world_id}")
            require(binding["nested_prompt_closure"] == closure, f"source lexical-binding witness mismatch at {world_id}")
            callable_names = {"acall_model", "get_kb_retriever", "prepare_augmented_prompt", "retrieve_documents", "wrap_model"}
            callable_bindings = require_object(binding["top_level_callables"], callable_names, f"{world_id}.top_level_callables")
            for name, item in callable_bindings.items():
                item = require_object(item, {"free_variables", "globals_identity_matches_namespace", "module_name"}, f"{world_id}.{name} binding")
                require(item["globals_identity_matches_namespace"] is True and item["free_variables"] == [], f"source globals or closure binding mismatch at {world_id}:{name}")
                require(item["module_name"] == f"_capsule_joshua_{world_id.replace('__', '_')}", f"Joshua source module name changed at {world_id}:{name}")
            require(closure["system_message_observed"] and closure["human_message_history_preserved"], f"source message closure failed at {world_id}")
            require(closure["retrieved_document_closure_observed"] if found else closure["no_documents_closure_observed"], f"source retrieval closure failed at {world_id}")
    total = Fraction(0)
    for world in worlds:
        total = add_weights(total, fraction(world["probability"]), "finite model total weight")
    require(total == 1, "schedule weights do not sum to one")
    return {"worlds": worlds, "expected_weight_by_world": expected_weights, "total_weight": total}


def _laws(result: dict[str, Any], capsule_id: str, worlds: list[dict[str, Any]]) -> dict[str, Any]:
    laws = result["exact_laws"]
    event_key = "ordered_execution_events" if capsule_id == "didilili-langgraphllm-one-node-finite-oracle-v1" else "ordered_events"
    recomputed = {
        "complete_trace_law": _law(worlds, "trace_sha256", "trace_projection"),
        "content_only_law": _law(worlds, "content_only_sha256", "content_only_projection"),
        "final_answer_only_law": _law(worlds, "final_answer_only_sha256", "final_answer_only_projection"),
        "assistant_message_only_law": _law(worlds, "assistant_message_only_sha256", "assistant_message_only_projection"),
        "run_status_law": _status_law(worlds),
    }
    if capsule_id == "didilili-langgraphllm-one-node-finite-oracle-v1":
        recomputed["model_response_status_law"] = _event_law(worlds, "model_response", "status", event_key)
        recomputed["finish_reason_or_error_law"] = _event_law(worlds, "model_response", "finish_reason", event_key)
    else:
        recomputed["retrieval_response_status_law"] = _event_law(worlds, "retrieval_response", "status", event_key)
        recomputed["model_response_status_law"] = _event_law(worlds, "model_response", "status", event_key)
        recomputed["finish_reason_or_error_law"] = _event_law(worlds, "model_response", "finish_reason", event_key)
    for name, observed in recomputed.items():
        require(canonical(laws[name]) == canonical(observed), f"advertised exact law does not replay: {name}")
    require(laws["weights_sum_to_one"] is True, "artifact does not assert normalized finite weights")
    require(laws["all_declared_worlds_accounted_for"] is True, "artifact does not assert all schedules were accounted for")
    require(laws["all_independent_replays_identical"] is True, "artifact does not assert repeatability")
    require(result["result"] == "PASS_CONDITIONAL_FINITE_DOMAIN", "capsule did not pass its conditional finite-domain checks")

    error_count = sum(world["run_status"] == "provider_error" for world in worlds)
    error_field = "modeled_provider_error_world_count" if capsule_id.startswith("didilili") else "modeled_model_error_world_count"
    require_exact_int(laws[error_field], error_field, error_count)

    coarse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for world in worlds:
        coarse[world["content_only_sha256"]].append(world)
    collision_witnesses = []
    collision_claims = []
    for key, group in sorted(coarse.items()):
        group_weight = Fraction(0)
        for world in group:
            group_weight = add_weights(group_weight, fraction(world["probability"]), "coarsening witness weight")
        events = [event for world in group for event in world["trace_projection"][event_key]]
        full_hashes = sorted({world["trace_sha256"] for world in group})
        collision = len(full_hashes) > 1
        collision_witnesses.append({
            "content_projection_sha256": key,
            "weight": f"{group_weight.numerator}/{group_weight.denominator}",
            "world_ids": [world["world_id"] for world in group],
            "complete_trace_sha256s": full_hashes,
            "model_statuses": sorted({str(event.get("status")) for event in events if event.get("kind") == "model_response"}),
            "model_finish_reasons_or_error": sorted({str(event.get("finish_reason", "raised")) for event in events if event.get("kind") == "model_response"}),
            "retrieval_statuses": sorted({str(event.get("status")) for event in events if event.get("kind") == "retrieval_response"}),
            "coarse_projection_merges_full_traces": collision,
        })
        if capsule_id.startswith("didilili"):
            collision_claims.append({
                "content_projection_sha256": key,
                "full_trace_sha256s": full_hashes,
                "same_content_distinct_full_observations": collision,
                "world_ids": sorted(world["world_id"] for world in group),
            })
        else:
            collision_claims.append({
                "content_projection_sha256": key,
                "full_trace_sha256s": full_hashes,
                "retrieval_response_statuses": sorted({
                    str(event.get("status")) for event in events if event.get("kind") == "retrieval_response"
                }),
                "same_content_distinct_full_observations": collision,
                "world_ids": sorted(world["world_id"] for world in group),
            })
    collision_field = "same_content_distinct_observation_collisions" if capsule_id.startswith("didilili") else "same_content_distinct_full_observations_collisions"
    require(canonical(laws[collision_field]) == canonical(collision_claims), f"coarse collision claims do not replay: {collision_field}")
    final_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for world in worlds:
        final_groups[world["final_answer_only_sha256"]].append(world)
    history_witnesses = []
    for key, group in sorted(final_groups.items()):
        group_weight = Fraction(0)
        for world in group:
            group_weight = add_weights(group_weight, fraction(world["probability"]), "history witness weight")
        histories = sorted({world["content_only_sha256"] for world in group})
        user_inputs = sorted({
            str(world["content_only_projection"][0])
            for world in group
            if isinstance(world["content_only_projection"], list) and world["content_only_projection"]
        })
        history_witnesses.append({
            "final_answer_projection_sha256": key,
            "weight": f"{group_weight.numerator}/{group_weight.denominator}",
            "world_ids": [world["world_id"] for world in group],
            "distinct_message_history_sha256s": histories,
            "distinct_first_message_contents": user_inputs,
            "final_answer_projection_erases_distinct_histories": len(histories) > 1,
        })
    status_witnesses = [
        item for item in collision_witnesses
        if len(item["retrieval_statuses"]) > 1
        or len(item["model_statuses"]) > 1
        or len(item["model_finish_reasons_or_error"]) > 1
    ]
    return {
        "laws": recomputed,
        "coarsening_witnesses": collision_witnesses,
        "status_elision_witnesses": status_witnesses,
        "history_elision_witnesses": history_witnesses,
    }


def verify(path: Path) -> dict[str, Any]:
    raw = strict_read_bytes(path, where="finite capsule artifact")
    wrapper_value = strict_loads(raw, where="finite capsule artifact")
    require(type(wrapper_value) is dict, "execution wrapper must be an object")
    worker_name = wrapper_value.get("worker")
    worker_to_capsule = {candidate.name: capsule_id for capsule_id, candidate in WORKERS.items()}
    require(type(worker_name) is str and worker_name in worker_to_capsule, "artifact names an unknown capsule worker")
    capsule_id = worker_to_capsule[worker_name]
    result, worker_sha, checks = _check_wrapper(wrapper_value, capsule_id)
    worker_path = WORKERS[capsule_id]
    worker_raw = _read_regular_beneath(ROOT, worker_path.relative_to(ROOT))
    require(sha_bytes(worker_raw) == EXPECTED_WORKER_SHA256[capsule_id], "current capsule worker differs from the frozen worker version")
    require(worker_sha == EXPECTED_WORKER_SHA256[capsule_id], "artifact worker hash differs from the frozen worker version")
    require(result["capsule_definition"]["worker_sha256"] == worker_sha, "result capsule definition does not bind current worker")
    _check_source(result, capsule_id)
    checked = _check_worlds(result, capsule_id)
    laws = _laws(result, capsule_id, checked["worlds"])
    artifact_sha = sha_bytes(raw)
    verifier_sha = sha_bytes(Path(__file__).read_bytes())
    total = checked["total_weight"]
    world_certificates = [
        {
            "world_id": world["world_id"],
            "probability": world["probability"],
            "outcome": world["outcome"],
            "run_status": world["run_status"],
            "trace_sha256": world["trace_sha256"],
            "content_only_sha256": world["content_only_sha256"],
            "independent_replay_identical": world["independent_replay"]["identical"],
        }
        for world in checked["worlds"]
    ]
    certificate = {
        "certificate_id": "independent-bounded-workflow-trace-law-v1",
        "verification": "PASS_CONDITIONAL_FINITE_TRACE_CERTIFICATE",
        "scope": "Replay of the hash-bound exported finite trace model and rational observer laws; no workflow source was executed by this verifier. This does not independently establish that the recorded execution occurred as represented.",
        "capsule_id": capsule_id,
        "artifact": str(path.resolve()),
        "artifact_sha256": artifact_sha,
        "worker_sha256": worker_sha,
        "verifier_sha256": verifier_sha,
        "source": {
            "repository": result["source"]["repository"],
            "commit": result["source"]["commit"],
            "path": result["source"]["path"],
            "sha256": result["source"]["sha256"],
            "selection_sha256": result["source"]["selection_sha256"],
            "selected_segments": result["source"]["segments"],
        },
        "finite_model": {
            "support": result["finite_support"],
            "world_count": len(checked["worlds"]),
            "world_weights_sum": f"{total.numerator}/{total.denominator}",
            "worlds": world_certificates,
        },
        "observer_laws": laws["laws"],
        "coarsening_witnesses": laws["coarsening_witnesses"],
        "lossy_projection_controls": {
            "message_content_projection_omits_statuses_and_metadata": laws["status_elision_witnesses"],
            "final_answer_projection_omits_history": laws["history_elision_witnesses"],
        },
        "isolation_evidence": checks,
        "mock_contract_sha256": result["capsule_definition"]["mock_contract_sha256"],
    }
    return certificate


def _cli_certificate_path(artifact: Path) -> Path | None:
    candidate = Path(os.path.abspath(os.fspath(artifact)))
    for filename, capsule_id in ARTIFACT_CAPSULES.items():
        if candidate == ARTIFACT_DIR / filename:
            return CERTIFICATE_DIR / f"{capsule_id}-certificate.json"
    return None


def _write_certificate(path: Path, certificate: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.parent.is_symlink(), "certificate directory must not be a symlink")
    require(path.parent.resolve(strict=True) == path.parent.absolute(), "certificate directory resolves outside its fixed location")
    validate_tree(certificate, where="certificate")
    payload = json.dumps(certificate, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    encoded = payload.encode("utf-8", errors="strict")
    require(len(encoded) <= 32 * 1024 * 1024, "certificate exceeds byte limit")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _discard_certificate(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    failures = []
    for path in args.artifacts:
        output = _cli_certificate_path(path)
        if output is not None:
            _discard_certificate(output)
        try:
            require(output is not None, "CLI accepts only the two fixed finite-capsule artifact paths")
            certificate = verify(path)
            require(output.name == f"{certificate['capsule_id']}-certificate.json", "certificate filename does not match the verified capsule")
            _write_certificate(output, certificate)
            print(json.dumps({"verification": certificate["verification"], "capsule_id": certificate["capsule_id"], "certificate": str(output), "world_count": certificate["finite_model"]["world_count"]}, ensure_ascii=False))
        except BaseException as exc:
            if output is not None:
                _discard_certificate(output)
            if not isinstance(exc, Exception):
                raise
            failures.append({"artifact": str(path), "error": f"{type(exc).__name__}: {exc}"})
            print(json.dumps(failures[-1], ensure_ascii=False), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
