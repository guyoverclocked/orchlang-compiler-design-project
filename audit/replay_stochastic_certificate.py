#!/usr/bin/env python3
"""Independently replay finite stochastic-bisimulation certificates.

This verifier uses the local v1 graph/kernel normalizer and reconstructs the
reachable finite semantic transition system itself. It checks the certificate
state/edge closure and independently validates the supplied partition as a
stable probabilistic bisimulation. A shared initial block certifies equality
of ordered success-only usage traces at every finite call horizon for the
bound inputs and finite kernel. A split is inconclusive, never a leakage
witness; neither result says anything about real providers, errors, total
billing, termination, or infinite executions.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

try:
    from .probabilistic_reference import (
        MAX_HORIZON,
        MAX_TOKEN,
        MAX_TEXT_BYTES,
        ReferenceError as OracleInputError,
        _Graph,
        _Kernel,
        _utf8,
    )
except ImportError:
    from probabilistic_reference import (  # type: ignore[no-redef]
        MAX_HORIZON,
        MAX_TOKEN,
        MAX_TEXT_BYTES,
        ReferenceError as OracleInputError,
        _Graph,
        _Kernel,
        _utf8,
    )


CERTIFICATE_FORMAT = "orchlang-stochastic-bisimulation-certificate"
ATTESTATION_FORMAT = "orchlang-stochastic-bisimulation-replay-attestation"
VERSION = 1
ORDINAL_SATURATION = MAX_HORIZON + 1
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 128 * 1024 * 1024
MAX_REPORT_ITEMS = 2_000_000
MAX_STATES = 1_000_000
MAX_TRANSITIONS = 1_000_000
MAX_WORK_BYTES = 1024 * 1024 * 1024
MAX_CONTROL_STEPS = 10_000_000
MAX_SCENARIOS = 64
MAX_RATIONAL_BITS = 8192
MAX_STATE_KEY_BYTES = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RATIONAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")

TOP_KEYS = {
    "format", "version", "status", "claim", "scope", "hashes", "inputs",
    "closed_system", "partition_certificate", "analysis_stats",
}
HASH_KEYS = {
    "graph_sha256", "kernel_sha256", "checker_sha256", "public_store_sha256",
    "secret_scenarios_sha256",
}
SCOPE_KEYS = {
    "oracle", "kernel_rule_precedence", "observer", "semantics",
    "ordinal_saturation", "history_window", "history_ordinal_saturation",
    "saturation_justification", "excluded", "interpretation",
}
SYSTEM_KEYS = {"state_count", "transition_count", "initial_state_ids", "states", "transitions"}
STATE_KEYS = {"id", "pc", "values", "ordinals", "history", "kind", "block"}
EDGE_KEYS = {"from", "label", "to", "probability"}
LABEL_KEYS = {"kind", "contract", "input_tokens", "output_tokens"}
PARTITION_KEYS = {
    "stable", "refinement_rounds", "block_count", "initial_scenario_blocks",
    "all_initial_scenarios_equivalent", "blocks",
}
BLOCK_KEYS = {"id", "kind", "states", "signature"}
SIGNATURE_KEYS = {"label", "target_block", "probability"}
STATS_KEYS = {
    "expanded_states", "call_outcome_transitions_before_merge", "byte_work_estimate",
    "max_states", "max_work_bytes", "max_state_key_bytes", "rational_precision_limit_bits",
}
CLAIM = "equal ordered success-only usage-trace laws at every finite call horizon"
RULE_PRECEDENCE = "first matching rule in supplied order, otherwise resolved-contract default"
OBSERVER_SCOPE = (
    "ordered call labels contain normalized resolved contract, integer input usage, and integer output usage; "
    "stop is a terminal state class"
)
SEMANTICS_SCOPE = (
    "successful model outcomes only; each response updates its result register and complete event history"
)
SATURATION_JUSTIFICATION = (
    "kernel ordinal and complete-history event ordinal literals are at most 32; all values >=33 match the same rules"
)
EXCLUDED_SCOPE = [
    "provider probability validity or provider behavior",
    "errors, retries, currency, cumulative cost or cumulative trace/work budgets",
    "termination probability or infinite-run trace law",
]
INTERPRETATION_SCOPE = (
    "same final block is sufficient for every finite-horizon trace-law equality; different blocks are inconclusive, "
    "not a trace-law counterexample"
)
UNVERIFIED_FIELDS = [
    "hashes.checker_sha256 (digest shape only; the producer executable was not replayed)",
    "analysis_stats.byte_work_estimate (producer meter; verifier uses a separate deterministic work budget)",
]


class ReplayError(ValueError):
    """Malformed or semantically inconsistent certificate."""


class ReplayLimit(RuntimeError):
    """Independent replay exceeded an explicit resource bound."""


@dataclass(frozen=True)
class _SemanticState:
    pc: tuple[str, int]
    values: tuple[tuple[str, str | bool], ...]
    ordinals: tuple[int, ...]
    history: tuple[dict[str, Any], ...]


def _canonical(value: Any, limit: int | None = None) -> str:
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    chunks: list[str] = []
    byte_count = 0
    try:
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            byte_count += len(encoded)
            if limit is not None and byte_count > limit:
                raise ReplayLimit("canonical JSON byte-work limit reached")
            chunks.append(chunk)
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as error:
        if _is_int_display_limit(error):
            raise ReplayLimit(f"exact integer formatting resource limit: {error}") from error
        if isinstance(error, RecursionError):
            raise ReplayLimit("canonical JSON nesting resource limit reached") from error
        raise ReplayError(f"value is not canonical JSON: {error}") from error
    return "".join(chunks)


def _canonical_digest(value: Any, label: str, limit: int) -> tuple[str, int]:
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256()
    size = 0
    try:
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            size += len(encoded)
            if size > limit:
                raise ReplayLimit(f"{label} canonical byte limit reached")
            digest.update(encoded)
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as error:
        if _is_int_display_limit(error):
            raise ReplayLimit(f"{label} exact integer formatting resource limit: {error}") from error
        if isinstance(error, RecursionError):
            raise ReplayLimit(f"{label} nesting resource limit reached") from error
        raise ReplayError(f"{label} is not canonical JSON: {error}") from error
    return digest.hexdigest(), size


def _is_int_display_limit(error: BaseException) -> bool:
    message = str(error).lower()
    return "integer string conversion" in message or "max_str_digits" in message


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayError(f"{label} must be an object")
    return value


def _keys(value: Any, required: set[str], label: str) -> dict[str, Any]:
    obj = _object(value, label)
    missing = required - obj.keys()
    unknown = obj.keys() - required
    if missing or unknown:
        raise ReplayError(
            f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return obj


def _natural(value: Any, label: str, minimum: int = 0, maximum: int = MAX_TOKEN) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReplayError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _fraction_bits(value: Fraction) -> int:
    return max(abs(value.numerator).bit_length(), value.denominator.bit_length())


def _bounded_fraction(value: Fraction, label: str) -> Fraction:
    if _fraction_bits(value) > MAX_RATIONAL_BITS:
        raise ReplayLimit(f"{label} exceeds the {MAX_RATIONAL_BITS}-bit exact-rational limit")
    return value


def _fraction(value: Any, label: str, *, positive: bool = False,
              at_most_one: bool = False) -> Fraction:
    if not isinstance(value, str) or len(value) > 5000 or not RATIONAL_RE.fullmatch(value):
        raise ReplayError(f"{label} must be a canonical exact rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        if _is_int_display_limit(error):
            raise ReplayLimit(f"{label} exact-rational parser limit reached") from error
        raise ReplayError(f"{label} is not an exact rational") from error
    if str(result) != value:
        raise ReplayError(f"{label} is not reduced canonical rational text")
    _bounded_fraction(result, label)
    if positive and result <= 0:
        raise ReplayError(f"{label} must be positive")
    if at_most_one and result > 1:
        raise ReplayError(f"{label} must be at most one")
    return result


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReplayError(f"non-finite JSON constant {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReplayError(f"non-finite JSON number {value}")
    return number


def _parse_json(raw: bytes, label: str, limit: int) -> Any:
    if len(raw) > limit:
        raise ReplayLimit(f"{label} byte read limit reached")
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant, parse_float=_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ReplayError):
            raise
        if isinstance(error, RecursionError) or _is_int_display_limit(error):
            raise ReplayLimit(f"{label} parser resource limit reached: {error}") from error
        raise ReplayError(f"invalid {label} JSON: {error}") from error


def _read_bounded(source: Any, label: str, limit: int) -> bytes:
    if isinstance(source, bytes):
        raw = source
    elif isinstance(source, bytearray):
        raw = bytes(source)
    elif isinstance(source, os.PathLike):
        try:
            with Path(source).open("rb") as stream:
                if os.fstat(stream.fileno()).st_size > limit:
                    raise ReplayLimit(f"{label} byte read limit reached")
                raw = stream.read(limit + 1)
        except OSError as error:
            raise ReplayError(f"cannot read {label}: {error}") from error
    else:
        raise ReplayError(f"{label} must be bytes or a filesystem path")
    if len(raw) > limit:
        raise ReplayLimit(f"{label} byte read limit reached")
    return raw


def _report_document(source: Any) -> tuple[bytes, Any]:
    if isinstance(source, Mapping):
        # The report is already materialized by the caller; validate its JSON
        # tree before the streaming serialization used to bind its digest.
        _check_tree(source, "report")
        raw = _canonical(source, MAX_REPORT_BYTES).encode("utf-8")
        return raw, _parse_json(raw, "report", MAX_REPORT_BYTES)
    raw = _read_bounded(source, "certificate", MAX_REPORT_BYTES)
    document = _parse_json(raw, "certificate", MAX_REPORT_BYTES)
    _check_tree(document, "certificate")
    return raw, document


def _check_tree(value: Any, label: str, *, max_items: int = MAX_REPORT_ITEMS) -> None:
    count = 0
    active: set[int] = set()

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        if depth > 256:
            raise ReplayLimit(f"{label} nesting resource limit reached")
        count += 1
        if count > max_items:
            raise ReplayLimit(f"{label} item resource limit reached")
        if item is None or type(item) in (bool, int, float):
            if type(item) is float and not math.isfinite(item):
                raise ReplayError(f"{label} contains a non-finite number")
            return
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ReplayError(f"{label} contains non-scalar Unicode") from error
            return
        if isinstance(item, (dict, list)):
            identity = id(item)
            if identity in active:
                raise ReplayError(f"{label} contains a reference cycle")
            active.add(identity)
            if isinstance(item, dict):
                if not all(isinstance(key, str) for key in item):
                    raise ReplayError(f"{label} has a non-string object key")
                for key, child in item.items():
                    try:
                        key.encode("utf-8")
                    except UnicodeEncodeError as error:
                        raise ReplayError(f"{label} has non-scalar object key") from error
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(identity)
            return
        raise ReplayError(f"{label} contains a non-JSON value")

    visit(value, 0)


class _Meter:
    def __init__(self, max_work_bytes: int, max_control_steps: int,
                 max_transitions: int):
        self.max_work_bytes = max_work_bytes
        self.max_control_steps = max_control_steps
        self.max_transitions = max_transitions
        self.work_bytes = 0
        self.control_steps = 0
        self.transitions = 0

    def canonical(self, value: Any, *, overhead: int = 64,
                  max_bytes: int | None = None) -> str:
        remaining = self.max_work_bytes - self.work_bytes - overhead
        if remaining < 0:
            raise ReplayLimit("independent cumulative byte-work limit reached")
        if max_bytes is not None:
            remaining = min(remaining, max_bytes)
        rendered = _canonical(value, remaining)
        amount = len(rendered.encode("utf-8")) + overhead
        self.work_bytes += amount
        if self.work_bytes > self.max_work_bytes:
            raise ReplayLimit("independent cumulative byte-work limit reached")
        return rendered

    def charge_control(self, steps: int) -> None:
        self.control_steps += steps
        if self.control_steps > self.max_control_steps:
            raise ReplayLimit("independent control-step limit reached")
        self.work_bytes += steps * 16
        if self.work_bytes > self.max_work_bytes:
            raise ReplayLimit("independent cumulative byte-work limit reached")

    def charge_transition(self) -> None:
        self.transitions += 1
        if self.transitions > self.max_transitions:
            raise ReplayLimit("independent call-transition expansion limit reached")


def _state_document(state: _SemanticState, identities: list[str]) -> dict[str, Any]:
    return {
        "pc": [state.pc[0], state.pc[1]],
        "values": {name: value for name, value in state.values},
        "ordinals": [
            {"contract": json.loads(identity), "count": count}
            for identity, count in zip(identities, state.ordinals)
        ],
        "history": list(state.history),
    }


def _advance_control(graph: _Graph, pc: tuple[str, int],
                     values: dict[str, Any]) -> tuple[tuple[str, int], str, int]:
    steps = 0
    while True:
        kind, event = graph.event(pc)
        if kind in ("call", "stop"):
            return pc, kind, steps
        steps += 1
        if kind == "goto":
            pc = (event["target"], 0)
            continue
        if kind not in ("public", "secret"):
            raise ReplayError(f"unsupported control kind {kind!r}")
        subject = event["guard"]["value"]
        if subject not in values:
            raise ReplayError(f"guard reads uninitialized value {subject!r}")
        guard = event["guard"]
        value = values[subject]
        if "op" not in guard:
            if type(value) is not bool:
                raise ReplayError("Boolean guard value is not Boolean")
            decision = value
        else:
            left, right, op = graph.estimate(value), guard["limit"], guard["op"]
            if op == "<":
                decision = left < right
            elif op == "<=":
                decision = left <= right
            elif op == ">":
                decision = left > right
            elif op == ">=":
                decision = left >= right
            elif op == "==":
                decision = left == right
            elif op == "!=":
                decision = left != right
            else:
                raise ReplayError(f"unsupported guard comparison {op!r}")
        pc = (event["then"] if decision else event["else"], 0)


def _normalize_store(graph: _Graph, public_store: Any,
                     secret_scenarios: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(public_store, dict):
        raise ReplayError("public_store must be an object")
    public_names = {name for name, declaration in graph.inputs.items()
                    if declaration["label"] == "public"}
    secret_names = set(graph.inputs) - public_names
    if set(public_store) != public_names:
        raise ReplayError("public_store must assign every public input and no secret input")
    if not isinstance(secret_scenarios, list) or not 2 <= len(secret_scenarios) <= MAX_SCENARIOS:
        raise ReplayError("secret_scenarios must contain 2..64 assignments")

    stores_seen: set[str] = set()
    stores: list[dict[str, Any]] = []
    for index, assignment in enumerate(secret_scenarios):
        if not isinstance(assignment, dict) or set(assignment) != secret_names:
            raise ReplayError(f"secret scenario {index} must assign every secret input exactly")
        full_store = {**public_store, **assignment}
        normalized = {}
        for name, declaration in graph.inputs.items():
            value = full_store[name]
            if declaration["type"] == "boolean":
                if type(value) is not bool:
                    raise ReplayError(f"Boolean input {name} has the wrong type")
                normalized[name] = value
            else:
                value = graph._text(value, f"input {name}")
                if graph.estimate(value) > declaration["max_tokens"]:
                    raise ReplayError(f"text input {name} exceeds its declared token bound")
                normalized[name] = value
        scenario_identity = _canonical({key: normalized[key] for key in sorted(secret_names)},
                                       MAX_SOURCE_BYTES)
        if scenario_identity in stores_seen:
            raise ReplayError("secret scenarios contain a duplicate assignment")
        stores_seen.add(scenario_identity)
        stores.append(normalized)
    return stores, len(public_names)


def _construct_closed_system(graph_document: Any, kernel_document: Any,
                             public_store: Any, secret_scenarios: Any, *,
                             max_states: int, max_transitions: int,
                             max_work_bytes: int, max_control_steps: int) -> dict[str, Any]:
    graph = _Graph(graph_document)
    kernel = _Kernel(kernel_document, graph)
    stores, _public_count = _normalize_store(graph, public_store, secret_scenarios)

    identities = sorted(graph.contracts)
    contract_positions = {identity: index for index, identity in enumerate(identities)}
    meter = _Meter(max_work_bytes, max_control_steps, max_transitions)
    states: dict[str, _SemanticState] = {}
    kinds: dict[str, str] = {}
    pending: deque[str] = deque()
    initial_keys: list[str] = []
    edge_rows: dict[str, list[tuple[str, str, Fraction]]] = {}
    outcomes_before_merge = 0

    def normalize(pc: tuple[str, int], values: dict[str, Any],
                  ordinals: list[int], history: tuple[dict[str, Any], ...]) -> _SemanticState:
        frozen_values = tuple(sorted(values.items()))
        normalized_pc, kind, steps = _advance_control(graph, pc, dict(frozen_values))
        meter.charge_control(steps)
        if kind not in ("call", "stop"):
            raise ReplayError("control normalization did not reach a call or stop")
        state = _SemanticState(normalized_pc, frozen_values, tuple(ordinals), history)
        return state

    def intern(state: _SemanticState) -> str:
        rendered = meter.canonical(
            _state_document(state, identities), max_bytes=MAX_STATE_KEY_BYTES
        )
        if rendered not in states:
            if len(states) >= max_states:
                raise ReplayLimit("independent reachable-state limit reached")
            pc_kind, _event = graph.event(state.pc)
            if pc_kind not in ("call", "stop"):
                raise ReplayError("interned semantic state has a non-normalized PC")
            states[rendered] = state
            kinds[rendered] = pc_kind
            pending.append(rendered)
        return rendered

    for store in stores:
        initial = normalize((graph.entry, 0), store, [0] * len(identities), ())
        initial_keys.append(intern(initial))

    while pending:
        source = pending.popleft()
        state = states[source]
        kind, event = graph.event(state.pc)
        if kind != kinds[source]:
            raise ReplayError("semantic state kind changed during closure")
        if kind == "stop":
            edge_rows[source] = []
            meter.canonical({"terminal_state": source})
            continue
        if kind != "call":
            raise ReplayError("semantic state PC is not normalized to call or stop")

        contract = graph.models[event["model"]]
        contract_identity = _canonical(contract)
        ordinal_index = contract_positions[contract_identity]
        ordinal = state.ordinals[ordinal_index]
        values = dict(state.values)
        for atom in event["arguments"]:
            if "value" in atom and atom["value"] not in values:
                raise ReplayError("request reads an uninitialized register")
        arguments = [
            atom["literal"] if "literal" in atom else values[atom["value"]]
            for atom in event["arguments"]
        ]
        if not all(isinstance(argument, str) for argument in arguments):
            raise ReplayError("request arguments must resolve to text")
        request_bytes = len(_utf8(event["template"], "request template", maximum=MAX_TEXT_BYTES))
        request_bytes += sum(len(_utf8(argument, "request argument", maximum=MAX_TEXT_BYTES))
                             for argument in arguments)
        if request_bytes > MAX_TEXT_BYTES:
            raise ReplayLimit("aggregate request byte limit reached")
        input_tokens = graph.estimate(event["template"]) + sum(graph.estimate(arg) for arg in arguments)
        outcomes = kernel.choose(contract_identity, event["template"], arguments,
                                 ordinal, state.history, event)
        merged: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
        for outcome in outcomes:
            meter.charge_transition()
            outcomes_before_merge += 1
            probability = _bounded_fraction(outcome.probability, "kernel transition probability")
            updated_values = dict(values)
            updated_values[event["result"]] = outcome.response
            updated_ordinals = list(state.ordinals)
            updated_ordinals[ordinal_index] = min(ORDINAL_SATURATION, ordinal + 1)
            complete_event = {
                "contract": contract,
                "ordinal": ordinal,
                "template": event["template"],
                "arguments": arguments,
                "response": outcome.response,
                "input_tokens": input_tokens,
                "output_tokens": outcome.output_tokens,
            }
            if kernel.window:
                next_history = (state.history + (complete_event,))[-kernel.window:]
            else:
                next_history = ()
            target_state = normalize(
                (state.pc[0], state.pc[1] + 1), updated_values,
                updated_ordinals, next_history,
            )
            target = intern(target_state)
            label = _canonical({
                "kind": "call",
                "contract": contract,
                "input_tokens": input_tokens,
                "output_tokens": outcome.output_tokens,
            })
            pair = (label, target)
            merged[pair] = _bounded_fraction(
                merged[pair] + probability, "merged transition probability"
            )
            meter.canonical({
                "source": source,
                "label": label,
                "target": target,
                "probability": str(probability),
            })
        total = Fraction(0)
        for probability in merged.values():
            total = _bounded_fraction(total + probability, "outgoing transition mass")
        if total != 1:
            raise ReplayError("independently reconstructed call transition mass is not one")
        edge_rows[source] = [
            (label, target, probability)
            for (label, target), probability in sorted(merged.items())
        ]

    if set(edge_rows) != set(states):
        raise ReplayError("independent semantic closure is incomplete")
    return {
        "graph": graph,
        "kernel": kernel,
        "identities": identities,
        "states": states,
        "kinds": kinds,
        "initial_keys": initial_keys,
        "edge_rows": edge_rows,
        "outcomes_before_merge": outcomes_before_merge,
        "meter": meter,
    }


def _validate_scope(scope: Any, history_window: int) -> None:
    scope = _keys(scope, SCOPE_KEYS, "scope")
    expected = {
        "oracle": "declared finite rational conditional kernel; exact request, saturated contract ordinal, and retained complete-event history determine its distribution",
        "kernel_rule_precedence": RULE_PRECEDENCE,
        "observer": OBSERVER_SCOPE,
        "semantics": SEMANTICS_SCOPE,
        "ordinal_saturation": ORDINAL_SATURATION,
        "history_window": history_window,
        "history_ordinal_saturation": ORDINAL_SATURATION,
        "saturation_justification": SATURATION_JUSTIFICATION,
        "excluded": EXCLUDED_SCOPE,
        "interpretation": INTERPRETATION_SCOPE,
    }
    if scope != expected:
        raise ReplayError("certificate scope declaration differs from the supported semantics")


def _validate_state_table(system: Any, raw: Any) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    closed = _keys(raw, SYSTEM_KEYS, "closed_system")
    expected_states = system["states"]
    if _natural(closed["state_count"], "closed_system.state_count", 1, MAX_STATES) != len(expected_states):
        raise ReplayError("closed_system state_count differs from independent closure")
    raw_states = closed["states"]
    if not isinstance(raw_states, list) or len(raw_states) != len(expected_states):
        raise ReplayError("closed_system state table is not the complete finite closure")

    id_by_key: dict[str, str] = {}
    raw_by_id: dict[str, dict[str, Any]] = {}
    key_by_id: dict[str, str] = {}
    for index, raw_state in enumerate(raw_states):
        state = _keys(raw_state, STATE_KEYS, f"closed_system state {index}")
        state_id = state["id"]
        block_id = state["block"]
        if not isinstance(state_id, str) or not state_id or len(state_id) > 64:
            raise ReplayError(f"state {index} has an invalid id")
        if state_id in raw_by_id:
            raise ReplayError(f"duplicate state id {state_id!r}")
        if not isinstance(block_id, str) or not block_id:
            raise ReplayError(f"state {state_id} has an invalid block reference")
        state_doc = {name: state[name] for name in ("pc", "values", "ordinals", "history")}
        key = system["meter"].canonical(
            state_doc, overhead=0, max_bytes=MAX_STATE_KEY_BYTES
        )
        if key not in expected_states:
            raise ReplayError(f"state {state_id} is absent from independently reconstructed closure")
        if key in id_by_key:
            raise ReplayError("closed_system repeats a semantic state")
        expected_kind = system["kinds"][key]
        if state["kind"] != ("stop" if expected_kind == "stop" else "call"):
            raise ReplayError(f"state {state_id} kind disagrees with its normalized PC")
        id_by_key[key] = state_id
        raw_by_id[state_id] = state
        key_by_id[state_id] = key
    if set(id_by_key) != set(expected_states):
        raise ReplayError("closed_system omits a reachable semantic state")

    initial_ids = closed["initial_state_ids"]
    expected_initial_ids = [id_by_key[key] for key in system["initial_keys"]]
    if not isinstance(initial_ids, list) or initial_ids != expected_initial_ids:
        raise ReplayError("closed_system initial roots differ from scenario-order semantic roots")
    return key_by_id, raw_by_id


def _validate_edges(system: Any, raw: Any, key_by_id: dict[str, str]) -> None:
    if not isinstance(raw, list):
        raise ReplayError("closed_system transitions must be an array")
    expected: Counter[tuple[str, str, str, Fraction]] = Counter()
    for source, rows in system["edge_rows"].items():
        for label, target, probability in rows:
            expected[(source, label, target, probability)] += 1

    actual: Counter[tuple[str, str, str, Fraction]] = Counter()
    outgoing: dict[str, Fraction] = defaultdict(Fraction)
    for index, raw_edge in enumerate(raw):
        edge = _keys(raw_edge, EDGE_KEYS, f"transition {index}")
        source_id, target_id = edge["from"], edge["to"]
        if source_id not in key_by_id or target_id not in key_by_id:
            raise ReplayError(f"transition {index} has an unknown source or target id")
        source, target = key_by_id[source_id], key_by_id[target_id]
        label = _keys(edge["label"], LABEL_KEYS, f"transition {index} label")
        if label["kind"] != "call":
            raise ReplayError(f"transition {index} label kind must be call")
        _object(label["contract"], f"transition {index} contract")
        _natural(label["input_tokens"], f"transition {index} input_tokens")
        _natural(label["output_tokens"], f"transition {index} output_tokens")
        label_key = system["meter"].canonical(label, overhead=0)
        probability = _fraction(edge["probability"], f"transition {index} probability",
                                positive=True, at_most_one=True)
        identity = (source, label_key, target, probability)
        actual[identity] += 1
        outgoing[source] = _bounded_fraction(
            outgoing[source] + probability, f"transition mass from {source_id}"
        )
    if actual != expected:
        raise ReplayError("closed_system transitions differ from independently reconstructed edges")
    for state_key, kind in system["kinds"].items():
        expected_mass = Fraction(0) if kind == "stop" else Fraction(1)
        if outgoing.get(state_key, Fraction(0)) != expected_mass:
            raise ReplayError("closed_system outgoing transition mass is invalid")


def _validate_partition(system: Any, partition_raw: Any,
                        key_by_id: dict[str, str], raw_by_id: dict[str, dict[str, Any]],
                        status: str) -> dict[str, Any]:
    partition = _keys(partition_raw, PARTITION_KEYS, "partition_certificate")
    if type(partition["stable"]) is not bool or not partition["stable"]:
        raise ReplayError("partition_certificate must claim a stable partition")
    raw_blocks = partition["blocks"]
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ReplayError("partition blocks must be a nonempty array")
    if _natural(partition["block_count"], "partition block_count", 1, MAX_STATES) != len(raw_blocks):
        raise ReplayError("partition block_count differs from the block table")
    _natural(partition["refinement_rounds"], "partition refinement_rounds", 1,
             len(system["states"]) + 1)

    block_by_id: dict[str, dict[str, Any]] = {}
    member_ids: set[str] = set()
    state_block: dict[str, str] = {}
    for index, raw_block in enumerate(raw_blocks):
        block = _keys(raw_block, BLOCK_KEYS, f"partition block {index}")
        block_id = block["id"]
        if not isinstance(block_id, str) or not block_id or len(block_id) > 64:
            raise ReplayError(f"partition block {index} has an invalid id")
        if block_id in block_by_id:
            raise ReplayError(f"duplicate partition block id {block_id!r}")
        if block["kind"] not in ("call", "stop"):
            raise ReplayError(f"partition block {block_id} has an invalid kind")
        members = block["states"]
        if not isinstance(members, list) or not members:
            raise ReplayError(f"partition block {block_id} must contain at least one state")
        local: set[str] = set()
        for state_id in members:
            if not isinstance(state_id, str) or state_id not in key_by_id:
                raise ReplayError(f"partition block {block_id} names an unknown state")
            if state_id in local or state_id in member_ids:
                raise ReplayError("partition membership repeats a state")
            local.add(state_id)
            member_ids.add(state_id)
            state_block[state_id] = block_id
            state_doc = raw_by_id[state_id]
            if state_doc["block"] != block_id or state_doc["kind"] != block["kind"]:
                raise ReplayError(f"partition block {block_id} disagrees with its state table")
        block_by_id[block_id] = block
    if member_ids != set(key_by_id):
        raise ReplayError("partition does not cover the complete state table")

    transitions_by_source: dict[str, list[tuple[str, str, Fraction]]] = defaultdict(list)
    state_id_by_key = {key: state_id for state_id, key in key_by_id.items()}
    for source, rows in system["edge_rows"].items():
        for label, target, probability in rows:
            transitions_by_source[source].append((label, target, probability))

    for block_id, block in block_by_id.items():
        declared: dict[tuple[str, str], Fraction] = {}
        raw_signature = block["signature"]
        if not isinstance(raw_signature, list):
            raise ReplayError(f"partition block {block_id} signature must be an array")
        for item_index, raw_item in enumerate(raw_signature):
            item = _keys(raw_item, SIGNATURE_KEYS,
                         f"partition block {block_id} signature item {item_index}")
            label = _keys(item["label"], LABEL_KEYS,
                          f"partition block {block_id} signature label {item_index}")
            target_block = item["target_block"]
            if target_block not in block_by_id:
                raise ReplayError(f"partition block {block_id} signature has an unknown target block")
            if label["kind"] != "call":
                raise ReplayError("partition signature labels must describe calls")
            _natural(label["input_tokens"], "partition signature input_tokens")
            _natural(label["output_tokens"], "partition signature output_tokens")
            _object(label["contract"], "partition signature contract")
            probability = _fraction(item["probability"], "partition signature probability",
                                    positive=True, at_most_one=True)
            pair = (_canonical(label), target_block)
            if pair in declared:
                raise ReplayError("partition signature repeats a label/target pair")
            declared[pair] = probability

        members = block["states"]
        for state_id in members:
            source = key_by_id[state_id]
            if system["kinds"][source] == "stop":
                actual: dict[tuple[str, str], Fraction] = {}
            else:
                actual = {}
                for label, target, probability in transitions_by_source[source]:
                    pair = (label, state_block[state_id_by_key[target]])
                    actual[pair] = _bounded_fraction(
                        actual.get(pair, Fraction(0)) + probability,
                        "partition signature aggregation",
                    )
            if actual != declared:
                raise ReplayError(f"partition block {block_id} is not stable")
            meter_value = {
                "block": block_id,
                "state": state_id,
                "signature": [
                    {"label": json.loads(label), "target_block": target, "probability": str(p)}
                    for (label, target), p in sorted(actual.items())
                ],
            }
            system["meter"].canonical(meter_value)

    initial_ids = system["initial_ids"]
    initial_blocks = [state_block[state_id] for state_id in initial_ids]
    if partition["initial_scenario_blocks"] != initial_blocks:
        raise ReplayError("partition initial scenario blocks differ from the root state membership")
    equivalent = len(set(initial_blocks)) == 1
    if type(partition["all_initial_scenarios_equivalent"]) is not bool:
        raise ReplayError("partition all_initial_scenarios_equivalent must be Boolean")
    if partition["all_initial_scenarios_equivalent"] != equivalent:
        raise ReplayError("partition equivalence flag differs from its initial blocks")
    expected_status = "proved_equal" if equivalent else "inconclusive"
    if status != expected_status:
        raise ReplayError("certificate status disagrees with the verified initial partition")
    return {
        "block_count": len(block_by_id),
        "initial_blocks": initial_blocks,
        "equal_laws_claim": equivalent,
        "block_by_id": block_by_id,
    }


def _validate_statistics(raw: Any, system: Any,
                         closed: dict[str, Any]) -> dict[str, int]:
    stats = _keys(raw, STATS_KEYS, "analysis_stats")
    declared_states = _natural(stats["max_states"], "analysis_stats.max_states", 1, MAX_STATES)
    declared_work = _natural(stats["max_work_bytes"], "analysis_stats.max_work_bytes", 1, MAX_WORK_BYTES)
    if len(system["states"]) > declared_states:
        raise ReplayError("closed state count exceeds the producer's declared state cap")
    if _natural(stats["expanded_states"], "analysis_stats.expanded_states", 1, MAX_STATES) != len(system["states"]):
        raise ReplayError("analysis_stats expanded_states differs from the closed system")
    if _natural(stats["call_outcome_transitions_before_merge"],
                "analysis_stats.call_outcome_transitions_before_merge", 0, MAX_TRANSITIONS) != system["outcomes_before_merge"]:
        raise ReplayError("analysis_stats transition expansion count differs from independent replay")
    work_estimate = _natural(stats["byte_work_estimate"], "analysis_stats.byte_work_estimate", 1, declared_work)
    if _natural(closed["state_count"], "closed_system.state_count", 1, MAX_STATES) != len(system["states"]):
        raise ReplayError("state count mismatch")
    if _natural(closed["transition_count"], "closed_system.transition_count", 0, MAX_TRANSITIONS) != sum(
        len(rows) for rows in system["edge_rows"].values()
    ):
        raise ReplayError("transition count differs from independent edge closure")
    if _natural(stats["rational_precision_limit_bits"],
                "analysis_stats.rational_precision_limit_bits", 1, 1_000_000) != MAX_RATIONAL_BITS:
        raise ReplayError("rational precision declaration differs from supported contract")
    if _natural(stats["max_state_key_bytes"], "analysis_stats.max_state_key_bytes",
                1, MAX_SOURCE_BYTES) != MAX_STATE_KEY_BYTES:
        raise ReplayError("state-key byte declaration differs from supported contract")
    return {"producer_max_states": declared_states,
            "producer_max_work_bytes": declared_work,
            "producer_byte_work_estimate": work_estimate}


def _attestation(status: str, *, diagnostic: str | None = None,
                  details: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "format": ATTESTATION_FORMAT,
        "version": 1,
        "status": status,
        "verification_method": "independent finite-state closure and bisimulation replay",
        "certificate_status": None,
        "equal_laws_claim": False,
        "claim_scope": (
            "No equality claim: independent replay did not verify a proved_equal certificate."
            if status != "verified" else
            "Equal ordered success-only usage-trace laws at every finite call horizon for the bound public store, "
            "secret assignments, and declared finite rational kernel; not a real-provider, total-billing, "
            "termination, infinite-horizon, or differential-privacy claim."
        ),
        "unverified_fields": UNVERIFIED_FIELDS,
        "diagnostic": diagnostic,
    }
    if details:
        result.update(details)
    return result


def replay_certificate(report_source: Any, graph_source: Any, kernel_source: Any, *,
                       expected_public_store: Any | None = None,
                       expected_secret_scenarios: Any | None = None,
                       max_states: int = 10_000,
                       max_transitions: int = 1_000_000,
                       max_work_bytes: int = 64 * 1024 * 1024,
                       max_control_steps: int = 1_000_000) -> dict[str, Any]:
    """Replay a complete stochastic bisimulation certificate independently.

    Graph/kernel hashes bind the exact supplied raw bytes. Public and secret
    assignments are included in the certificate and bound by canonical hashes;
    callers can also supply expected input values to bind an external study
    configuration explicitly. Resource exhaustion always returns UNKNOWN
    without a verified closure or equality claim.
    """
    try:
        max_states = _natural(max_states, "max_states", 1, MAX_STATES)
        max_transitions = _natural(max_transitions, "max_transitions", 1, MAX_TRANSITIONS)
        max_work_bytes = _natural(max_work_bytes, "max_work_bytes", 1, MAX_WORK_BYTES)
        max_control_steps = _natural(max_control_steps, "max_control_steps", 1, MAX_CONTROL_STEPS)
        report_raw, report = _report_document(report_source)
        graph_raw = _read_bounded(graph_source, "graph source", MAX_SOURCE_BYTES)
        kernel_raw = _read_bounded(kernel_source, "kernel source", MAX_SOURCE_BYTES)
        report = _object(report, "certificate")
        if report.get("format") != CERTIFICATE_FORMAT or type(report.get("version")) is not int or report["version"] != VERSION:
            raise ReplayError("unsupported stochastic bisimulation certificate format/version")
        hashes = _object(report.get("hashes"), "hashes")
        graph_digest = hashlib.sha256(graph_raw).hexdigest()
        kernel_digest = hashlib.sha256(kernel_raw).hexdigest()
        if hashes.get("graph_sha256") != graph_digest:
            raise ReplayError("certificate graph SHA-256 differs from supplied raw graph bytes")
        if hashes.get("kernel_sha256") != kernel_digest:
            raise ReplayError("certificate kernel SHA-256 differs from supplied raw kernel bytes")
        if report.get("status") == "unknown":
            if report.get("claim") is not None or report.get("closed_system") is not None or report.get("partition_certificate") is not None:
                raise ReplayError("UNKNOWN certificate must not carry a partial proof system")
            _valid_sha(hashes.get("checker_sha256"), "hashes.checker_sha256")
            return _attestation("unknown", diagnostic="producer certificate is UNKNOWN; no partial closure is replayed",
                                details={"graph_sha256": graph_digest,
                                         "kernel_sha256": kernel_digest,
                                         "report_sha256": hashlib.sha256(report_raw).hexdigest()})
        if report.get("status") not in ("proved_equal", "inconclusive"):
            raise ReplayError("certificate status must be proved_equal, inconclusive, or unknown")
        report = _keys(report, TOP_KEYS, "certificate")
        hashes = _keys(report["hashes"], HASH_KEYS, "hashes")
        _valid_sha(hashes["checker_sha256"], "hashes.checker_sha256")
        if hashes["graph_sha256"] != graph_digest or hashes["kernel_sha256"] != kernel_digest:
            raise ReplayError("raw graph/kernel hashes differ")
        graph_document = _parse_json(graph_raw, "graph source", MAX_SOURCE_BYTES)
        kernel_document = _parse_json(kernel_raw, "kernel source", MAX_SOURCE_BYTES)
        _check_tree(graph_document, "graph source")
        _check_tree(kernel_document, "kernel source")

        inputs = _keys(report["inputs"], {"public_store", "secret_scenarios"}, "inputs")
        public_store = _object(inputs["public_store"], "inputs.public_store")
        secret_scenarios = inputs["secret_scenarios"]
        public_digest, public_size = _canonical_digest(public_store, "public_store", MAX_SOURCE_BYTES)
        scenarios_digest, scenarios_size = _canonical_digest(
            secret_scenarios, "secret_scenarios", MAX_SOURCE_BYTES
        )
        if public_size + scenarios_size > MAX_SOURCE_BYTES:
            raise ReplayLimit("aggregate public-store and scenario byte cap reached")
        if hashes["public_store_sha256"] != public_digest:
            raise ReplayError("canonical public_store SHA-256 mismatch")
        if hashes["secret_scenarios_sha256"] != scenarios_digest:
            raise ReplayError("canonical secret_scenarios SHA-256 mismatch")
        if expected_public_store is not None:
            _object(expected_public_store, "expected public_store")
            _check_tree(expected_public_store, "expected public_store")
            expected_public_digest, _ = _canonical_digest(
                expected_public_store, "expected public_store", MAX_SOURCE_BYTES
            )
            if expected_public_digest != public_digest:
                raise ReplayError("certificate public_store differs from caller-supplied expected input")
        if expected_secret_scenarios is not None:
            if not isinstance(expected_secret_scenarios, list):
                raise ReplayError("expected secret scenarios must be an array")
            _check_tree(expected_secret_scenarios, "expected secret scenarios")
            expected_scenarios_digest, _ = _canonical_digest(
                expected_secret_scenarios, "expected secret scenarios", MAX_SOURCE_BYTES
            )
            if expected_scenarios_digest != scenarios_digest:
                raise ReplayError("certificate secret_scenarios differ from caller-supplied expected inputs")

        meter = _Meter(max_work_bytes, max_control_steps, max_transitions)
        # Charge the canonical scenario documents after their aggregate size
        # precheck and before constructing any semantic closure.
        meter.work_bytes += public_size + scenarios_size
        if meter.work_bytes > max_work_bytes:
            raise ReplayLimit("independent cumulative byte-work limit reached by input stores")

        system = _construct_closed_system(
            graph_document, kernel_document, public_store, secret_scenarios,
            max_states=max_states, max_transitions=max_transitions,
            max_work_bytes=max_work_bytes - meter.work_bytes,
            max_control_steps=max_control_steps,
        )
        # Include store hashing work in the reported independent budget.
        system["meter"].work_bytes += meter.work_bytes
        system["meter"].max_work_bytes = max_work_bytes
        system["initial_ids"] = []
        closed = _keys(report["closed_system"], SYSTEM_KEYS, "closed_system")
        key_by_id, raw_by_id = _validate_state_table(system, closed)
        system["initial_ids"] = closed["initial_state_ids"]
        _validate_edges(system, closed["transitions"], key_by_id)
        stats = _validate_statistics(report["analysis_stats"], system, closed)

        _validate_scope(report["scope"], system["kernel"].window)
        if report["claim"] != CLAIM:
            raise ReplayError("certificate claim text differs from the supported contract")
        partition = _validate_partition(
            system, report["partition_certificate"], key_by_id, raw_by_id, report["status"]
        )
        if system["meter"].work_bytes > max_work_bytes:
            raise ReplayLimit("independent cumulative byte-work limit reached during partition replay")

        return _attestation("verified", details={
            "certificate_status": report["status"],
            "equal_laws_claim": partition["equal_laws_claim"],
            "claim_scope": (
                "Equal ordered success-only usage-trace laws at every finite call horizon for the bound public store, "
                "secret assignments, and declared finite rational kernel; not a real-provider, total-billing, "
                "termination, infinite-horizon, or differential-privacy claim."
                if partition["equal_laws_claim"] else
                "A sound stable partition separates the scenario roots; the result is inconclusive and is not a "
                "leakage witness or a claim that trace laws differ."
            ),
            "report_sha256": hashlib.sha256(report_raw).hexdigest(),
            "graph_sha256": graph_digest,
            "kernel_sha256": kernel_digest,
            "public_store_sha256": public_digest,
            "secret_scenarios_sha256": scenarios_digest,
            "scenario_count": len(secret_scenarios),
            "state_count": len(system["states"]),
            "transition_count": sum(len(rows) for rows in system["edge_rows"].values()),
            "initial_scenario_state_ids": closed["initial_state_ids"],
            "initial_scenario_blocks": partition["initial_blocks"],
            "partition_block_count": partition["block_count"],
            "independent_outcomes_expanded": system["outcomes_before_merge"],
            "independent_control_steps": system["meter"].control_steps,
            "independent_work_bytes": system["meter"].work_bytes,
            **stats,
            "verifier_limits": {
                "max_states": max_states,
                "max_transitions": max_transitions,
                "max_work_bytes": max_work_bytes,
                "max_control_steps": max_control_steps,
                "max_state_key_bytes": MAX_STATE_KEY_BYTES,
                "rational_precision_limit_bits": MAX_RATIONAL_BITS,
            },
        })
    except ReplayLimit as error:
        return _attestation("unknown", diagnostic=str(error))
    except (MemoryError, OverflowError, RecursionError) as error:
        return _attestation("unknown", diagnostic=f"independent replay resource limit: {error}")
    except OracleInputError as error:
        if "resource" in str(error).lower() or "limit" in str(error).lower():
            return _attestation("unknown", diagnostic=f"independent parser resource limit: {error}")
        return _attestation("rejected", diagnostic=f"invalid graph/kernel: {error}")
    except (ReplayError, ValueError, TypeError, KeyError, OSError) as error:
        if _is_int_display_limit(error):
            return _attestation("unknown", diagnostic=f"exact integer resource limit: {error}")
        return _attestation("rejected", diagnostic=str(error))


def _valid_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ReplayError(f"{label} must be a lowercase SHA-256 digest")
    return value


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--public-json", help="optional expected public-store object")
    parser.add_argument("--scenarios-json", help="optional expected secret-assignment array")
    parser.add_argument("--max-states", type=int, default=10_000)
    parser.add_argument("--max-transitions", type=int, default=1_000_000)
    parser.add_argument("--max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-control-steps", type=int, default=1_000_000)
    args = parser.parse_args(argv)
    try:
        expected_public = None if args.public_json is None else _parse_json(
            args.public_json.encode("utf-8"), "expected public store", MAX_SOURCE_BYTES
        )
        expected_scenarios = None if args.scenarios_json is None else _parse_json(
            args.scenarios_json.encode("utf-8"), "expected secret scenarios", MAX_SOURCE_BYTES
        )
        result = replay_certificate(
            args.certificate, args.graph, args.kernel,
            expected_public_store=expected_public,
            expected_secret_scenarios=expected_scenarios,
            max_states=args.max_states,
            max_transitions=args.max_transitions,
            max_work_bytes=args.max_work_bytes,
            max_control_steps=args.max_control_steps,
        )
    except ReplayLimit as error:
        result = _attestation("unknown", diagnostic=str(error))
    except (ReplayError, ValueError, TypeError, OSError) as error:
        result = _attestation("rejected", diagnostic=str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return {"verified": 0, "unknown": 2, "rejected": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
