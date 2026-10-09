#!/usr/bin/env python3
"""Independently replay an OrchLang cyclic request-graph certificate.

This module has its own strict JSON reader, graph normalizer, transition
semantics, and reachable-product traversal. It deliberately does not import or
execute the graph producer. A successful replay checks the producer's finite
product closure against the supplied graph bytes; it is not a mechanized proof
of the metatheory or of a source-to-graph translation.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


GRAPH_FORMAT = "orchlang-request-graph"
CERT_FORMAT = "orchlang-cyclic-request-certificate"
ATTESTATION_FORMAT = "orchlang-cyclic-request-replay-attestation"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}
MAX_TOKEN = 2**64 - 2
MAX_REPORT_NODES = 1_000_000
MAX_GRAPH_STATES = 100_000
MAX_GRAPH_ITEMS = 1_000_000
MAX_JSON_BYTES = 128 * 1024 * 1024


class ReplayError(ValueError):
    """The graph or certificate does not satisfy the replay contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReplayError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReplayError(f"non-finite JSON number: {value}")
    return number


def strict_json(raw: bytes, what: str) -> Any:
    if len(raw) > MAX_JSON_BYTES:
        raise ReplayError(f"{what} exceeds {MAX_JSON_BYTES} bytes")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        if isinstance(error, ReplayError):
            raise
        raise ReplayError(f"invalid {what} JSON: {error}") from error


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayError(f"{label} must be a JSON object")
    return value


def exact_keys(value: Any, required: set[str], optional: set[str] | None = None,
               label: str = "object") -> dict[str, Any]:
    obj = require_object(value, label)
    optional = optional or set()
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing or unknown:
        raise ReplayError(
            f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return obj


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ReplayError(f"{label} is not a valid identifier: {value!r}")
    return value


def natural(value: Any, label: str, minimum: int = 0,
            maximum: int = MAX_TOKEN) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReplayError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def string(value: Any, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        requirement = "nonempty string" if nonempty else "string"
        raise ReplayError(f"{label} must be a {requirement}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ReplayError(f"{label} contains a non-scalar Unicode code point") from error
    return value


def array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReplayError(f"{label} must be an array")
    return value


class NormalizedGraph:
    """Small independent normalizer for the version-1 graph contract."""

    def __init__(self, document: Any):
        root = exact_keys(
            document,
            {"format", "version", "name", "inputs", "registers", "models", "states", "entry"},
            {"chars_per_token"},
            "graph",
        )
        if root["format"] != GRAPH_FORMAT or type(root["version"]) is not int or root["version"] != 1:
            raise ReplayError("unknown graph format or version")
        self.name = identifier(root["name"], "graph name")
        self.divisor = natural(root.get("chars_per_token", 4), "chars_per_token", 1)
        raw_inputs = require_object(root["inputs"], "inputs")
        raw_registers = require_object(root["registers"], "registers")
        raw_models = require_object(root["models"], "models")
        raw_states = require_object(root["states"], "states")
        if not raw_states:
            raise ReplayError("graph must contain at least one state")
        if len(raw_states) > MAX_GRAPH_STATES:
            raise ReplayError("graph state limit exceeded")
        if sum(map(len, (raw_inputs, raw_registers, raw_models, raw_states))) > MAX_GRAPH_ITEMS:
            raise ReplayError("graph declaration limit exceeded")

        self.inputs: dict[str, dict[str, Any]] = {}
        self.registers: dict[str, dict[str, Any]] = {}
        self.models: dict[str, dict[str, Any]] = {}
        self.states: dict[str, dict[str, Any]] = {}

        for alias, source in raw_models.items():
            identifier(alias, "model alias")
            model = exact_keys(source, {"provider", "model", "max_tokens"}, {"unit_price"},
                               f"model {alias}")
            provider = string(model["provider"], f"model {alias} provider", nonempty=True)
            model_id = string(model["model"], f"model {alias} identifier", nonempty=True)
            cap = natural(model["max_tokens"], f"model {alias} max_tokens", 1)
            has_price = "unit_price" in model
            price = model.get("unit_price", 0)
            if type(price) not in (int, float):
                raise ReplayError(f"model {alias} unit_price must be numeric")
            try:
                finite_price = float(price)
            except (OverflowError, ValueError) as error:
                raise ReplayError(f"model {alias} unit_price is not finite") from error
            if not math.isfinite(finite_price) or finite_price < 0:
                raise ReplayError(f"model {alias} unit_price must be finite and nonnegative")
            self.models[alias] = {
                "provider": provider,
                "model": model_id,
                "max_tokens": cap,
                "has_unit_price": has_price,
                "unit_price": finite_price,
            }

        for variable, source in raw_inputs.items():
            identifier(variable, "input name")
            declaration = exact_keys(source, {"type", "label"}, {"max_tokens"},
                                     f"input {variable}")
            input_type = declaration["type"]
            label = declaration["label"]
            if input_type not in ("text", "boolean") or label not in ("public", "secret"):
                raise ReplayError(f"input {variable} needs text/boolean type and public/secret label")
            if input_type == "text" and "max_tokens" not in declaration:
                raise ReplayError(f"text input {variable} requires max_tokens")
            cap = natural(declaration.get("max_tokens", 1),
                          f"input {variable} max_tokens")
            self.inputs[variable] = {"type": input_type, "label": label, "max_tokens": cap}

        for variable, source in raw_registers.items():
            identifier(variable, "register name")
            declaration = exact_keys(source, {"model"}, label=f"register {variable}")
            if variable in self.inputs:
                raise ReplayError(f"input/register name collision: {variable}")
            alias = identifier(declaration["model"], f"register {variable} model")
            if alias not in self.models:
                raise ReplayError(f"register {variable} refers to an unknown model")
            self.registers[variable] = {"model": alias}

        self.total_calls = 0
        for state_name, source in raw_states.items():
            identifier(state_name, "state name")
            body = exact_keys(source, {"calls", "next"}, label=f"state {state_name}")
            calls: list[dict[str, Any]] = []
            for call_index, raw_call in enumerate(array(body["calls"], f"state {state_name} calls")):
                self.total_calls += 1
                if self.total_calls > MAX_GRAPH_ITEMS:
                    raise ReplayError("graph call limit exceeded")
                call = exact_keys(raw_call, {"model", "template", "arguments", "result"},
                                  label=f"call {state_name}[{call_index}]")
                alias = identifier(call["model"], "call model")
                result = identifier(call["result"], "call result")
                template = string(call["template"], "call template")
                if alias not in self.models:
                    raise ReplayError(f"call in {state_name} uses an unknown model")
                if result not in self.registers:
                    raise ReplayError(f"call in {state_name} has an undeclared result register")
                call_contract = self.models[alias]
                result_contract = self.models[self.registers[result]["model"]]
                if self.unit(call_contract) != self.unit(result_contract):
                    raise ReplayError("call result register changes provider/model token unit")
                if call_contract["max_tokens"] > result_contract["max_tokens"]:
                    raise ReplayError("call result register cap is too small")
                arguments: list[dict[str, str]] = []
                for arg_index, raw_argument in enumerate(array(call["arguments"], "call arguments")):
                    argument = require_object(raw_argument, f"argument {arg_index}")
                    if set(argument) == {"literal"}:
                        arguments.append({"literal": string(argument["literal"], "literal argument")})
                    elif set(argument) == {"value"}:
                        variable = identifier(argument["value"], "argument value")
                        if variable in self.inputs:
                            declaration = self.inputs[variable]
                            if declaration["type"] != "text" or declaration["label"] != "public":
                                raise ReplayError("only public text inputs may appear in requests")
                        elif variable in self.registers:
                            producer = self.models[self.registers[variable]["model"]]
                            if self.unit(producer) != self.unit(call_contract):
                                raise ReplayError("generated request values cross model token units")
                        else:
                            raise ReplayError(f"unknown request argument {variable}")
                        arguments.append({"value": variable})
                    else:
                        raise ReplayError("an argument must contain exactly literal or value")
                calls.append({"model": alias, "template": template,
                              "arguments": arguments, "result": result})

            decision = require_object(body["next"], f"state {state_name} next")
            kind = decision.get("kind")
            if kind == "goto":
                exact_keys(decision, {"kind", "target"}, label="goto decision")
                normalized = {"kind": kind, "target": identifier(decision["target"], "goto target")}
            elif kind == "stop":
                exact_keys(decision, {"kind"}, label="stop decision")
                normalized = {"kind": kind}
            elif kind in ("public", "secret"):
                exact_keys(decision, {"kind", "guard", "then", "else"}, label="guard decision")
                guard = require_object(decision["guard"], "guard")
                exact_keys(guard, {"value"}, {"op", "limit"}, "guard")
                subject = identifier(guard["value"], "guard subject")
                if subject in self.inputs:
                    subject_decl = self.inputs[subject]
                    boolean_subject = subject_decl["type"] == "boolean"
                    secret_subject = subject_decl["label"] == "secret"
                elif subject in self.registers:
                    boolean_subject = False
                    secret_subject = False
                else:
                    raise ReplayError(f"unknown guard subject {subject}")
                if boolean_subject:
                    exact_keys(guard, {"value"}, label="Boolean guard")
                    normalized_guard = {"value": subject}
                else:
                    exact_keys(guard, {"value", "op", "limit"}, label="text guard")
                    op = string(guard["op"], "guard operator")
                    if op not in COMPARISONS:
                        raise ReplayError(f"unsupported guard operator {op!r}")
                    limit = natural(guard["limit"], "guard limit")
                    normalized_guard = {"value": subject, "op": op, "limit": limit}
                if (kind == "secret") != secret_subject:
                    raise ReplayError("guard decision confidentiality disagrees with its subject")
                normalized = {
                    "kind": kind,
                    "guard": normalized_guard,
                    "then": identifier(decision["then"], "then successor"),
                    "else": identifier(decision["else"], "else successor"),
                }
            else:
                raise ReplayError(f"unknown decision kind {kind!r}")
            self.states[state_name] = {"calls": calls, "next": normalized}

        self.entry = identifier(root["entry"], "entry state")
        if self.entry not in self.states:
            raise ReplayError("entry state is undeclared")
        for state_name, body in self.states.items():
            for target in self.targets(body["next"]):
                if target not in self.states:
                    raise ReplayError(f"state {state_name} has unknown successor {target}")

        self.reachable = self._reachable_states()
        self._reject_call_free_cycles()

    @staticmethod
    def unit(contract: dict[str, Any]) -> tuple[str, str]:
        return contract["provider"], contract["model"]

    @staticmethod
    def targets(decision: dict[str, Any]) -> list[str]:
        if decision["kind"] == "goto":
            return [decision["target"]]
        if decision["kind"] in ("public", "secret"):
            return [decision["then"], decision["else"]]
        return []

    def _reachable_states(self) -> set[str]:
        reached: set[str] = set()
        pending = [self.entry]
        while pending:
            state = pending.pop()
            if state in reached:
                continue
            reached.add(state)
            pending.extend(self.targets(self.states[state]["next"]))
        return reached

    def _reject_call_free_cycles(self) -> None:
        empty = {state for state in self.reachable if not self.states[state]["calls"]}
        indegree = {state: 0 for state in empty}
        successors = {
            state: [target for target in self.targets(self.states[state]["next"]) if target in empty]
            for state in empty
        }
        for targets in successors.values():
            for target in targets:
                indegree[target] += 1
        pending = deque(state for state, degree in indegree.items() if degree == 0)
        removed = 0
        while pending:
            state = pending.popleft()
            removed += 1
            for target in successors[state]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        if removed != len(empty):
            raise ReplayError("reachable call-free control cycle is unsupported")

    def event(self, pc: tuple[str, int]) -> tuple[str, dict[str, Any]]:
        state, index = pc
        calls = self.states[state]["calls"]
        if index < len(calls):
            return "call", calls[index]
        if index != len(calls):
            raise ReplayError("program counter is outside its state's event sequence")
        decision = self.states[state]["next"]
        return decision["kind"], decision

    def estimate(self, text: str) -> int:
        byte_count = len(text.encode("utf-8"))
        return (byte_count + self.divisor - 1) // self.divisor

    def argument_bound(self, atom: dict[str, str]) -> int:
        if "literal" in atom:
            return self.estimate(atom["literal"])
        variable = atom["value"]
        if variable in self.inputs:
            return self.inputs[variable]["max_tokens"]
        model = self.registers[variable]["model"]
        return self.models[model]["max_tokens"]

    def expected_state_bounds(self) -> dict[str, dict[str, int]]:
        result = {}
        for state in sorted(self.reachable):
            total_input = 0
            total_output = 0
            for call in self.states[state]["calls"]:
                total_output += self.models[call["model"]]["max_tokens"]
                total_input += self.estimate(call["template"]) + sum(
                    self.argument_bound(argument) for argument in call["arguments"]
                )
            result[state] = {
                "output_tokens": total_output,
                "input_tokens": total_input,
                "total_tokens": total_input + total_output,
            }
        return result


def _related_atom(left: dict[str, str], right: dict[str, str], relation: frozenset[tuple[str, str]]) -> bool:
    if "literal" in left or "literal" in right:
        return "literal" in left and "literal" in right and left["literal"] == right["literal"]
    return (left["value"], right["value"]) in relation


def _successors(graph: NormalizedGraph, left: tuple[str, int], right: tuple[str, int],
                relation: frozenset[tuple[str, str]]) -> tuple[str, list[tuple[tuple[str, int], tuple[str, int], frozenset[tuple[str, str]]]]]:
    """Reconstruct one deterministic local product rule and all obligations."""
    left_kind, left_event = graph.event(left)
    right_kind, right_event = graph.event(right)
    same_relation = relation

    # This priority is part of the version-1 producer contract: silent control
    # moves first, then universal secret branching, then synchronized public
    # decisions and calls.
    if left_kind == "goto":
        return "left-goto", [((left_event["target"], 0), right, same_relation)]
    if right_kind == "goto":
        return "right-goto", [(left, (right_event["target"], 0), same_relation)]
    if left_kind == "secret":
        return "left-secret", [((left_event[arm], 0), right, same_relation)
                               for arm in ("then", "else")]
    if right_kind == "secret":
        return "right-secret", [(left, (right_event[arm], 0), same_relation)
                                for arm in ("then", "else")]
    if left_kind != right_kind:
        raise ReplayError(f"accepted certificate has unmatched events: {left_kind} vs {right_kind}")
    if left_kind == "stop":
        return "stop", []
    if left_kind == "public":
        left_guard = left_event["guard"]
        right_guard = right_event["guard"]
        left_predicate = {key: value for key, value in left_guard.items() if key != "value"}
        right_predicate = {key: value for key, value in right_guard.items() if key != "value"}
        if ((left_guard["value"], right_guard["value"]) not in relation
                or left_predicate != right_predicate):
            raise ReplayError("accepted certificate contains unproved public guards")
        return "public-choice", [
            ((left_event[arm], 0), (right_event[arm], 0), same_relation)
            for arm in ("then", "else")
        ]
    if left_kind == "call":
        if graph.models[left_event["model"]] != graph.models[right_event["model"]]:
            raise ReplayError("accepted certificate matches calls with different contracts")
        if left_event["template"] != right_event["template"]:
            raise ReplayError("accepted certificate matches calls with different templates")
        left_arguments = left_event["arguments"]
        right_arguments = right_event["arguments"]
        if (len(left_arguments) != len(right_arguments)
                or not all(_related_atom(a, b, relation)
                           for a, b in zip(left_arguments, right_arguments))):
            raise ReplayError("accepted certificate matches calls with unequal ordered arguments")
        left_result, right_result = left_event["result"], right_event["result"]
        after = frozenset(
            (a, b) for a, b in relation if a != left_result and b != right_result
        ) | {(left_result, right_result)}
        return "matched-call", [
            ((left[0], left[1] + 1), (right[0], right[1] + 1), after)
        ]
    raise ReplayError(f"unexpected product event {left_kind!r}")


def _valid_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ReplayError(f"{label} must be a lowercase SHA-256 digest")
    return value


EXPECTED_SEMANTICS = {
    "oracle": "shared Omega(resolved-contract,per-contract-ordinal,template,ordered-text-values)",
    "inputs": "all public external values agree; secret inputs may differ",
    "claim": "equal complete request/usage traces and stop positions under the shared oracle",
    "cycles": "every finite trace prefix; no termination or finite total-cost claim",
    "input_accounting": "complete additive request contract in compatible token units",
    "unsupported": [
        "declassification", "tools", "request serialization", "independent provider sampling",
        "call-free cycles",
    ],
}


def _validate_certificate_shape(document: Any, graph: NormalizedGraph,
                                source_digest: str) -> dict[str, Any]:
    cert = exact_keys(
        document,
        {
            "format", "version", "graph_name", "status", "root", "nodes", "max_nodes",
            "semantics", "state_entry_bounds", "reachable_source_states", "product_nodes",
            "product_edges", "source_sha256", "checker_sha256",
        },
        label="certificate",
    )
    if cert["format"] != CERT_FORMAT or type(cert["version"]) is not int or cert["version"] != 1:
        raise ReplayError("unknown certificate format or version")
    if cert["status"] != "accepted":
        raise ReplayError("only accepted certificates may be replayed")
    if cert["graph_name"] != graph.name:
        raise ReplayError("certificate graph_name does not match source graph")
    if natural(cert["root"], "certificate root", maximum=MAX_REPORT_NODES) != 0:
        raise ReplayError("certificate root must be node zero")
    max_nodes = natural(cert["max_nodes"], "certificate max_nodes", 1, MAX_REPORT_NODES)
    nodes = array(cert["nodes"], "certificate nodes")
    if not nodes or len(nodes) > max_nodes:
        raise ReplayError("certificate node array is empty or exceeds its declared cap")
    if cert["source_sha256"] != source_digest:
        raise ReplayError("certificate source SHA-256 does not match graph bytes")
    _valid_sha(cert["source_sha256"], "certificate source_sha256")
    _valid_sha(cert["checker_sha256"], "certificate checker_sha256")

    semantics = exact_keys(cert["semantics"], set(EXPECTED_SEMANTICS), label="certificate semantics")
    if semantics != EXPECTED_SEMANTICS:
        raise ReplayError("certificate semantics do not match the replay contract")

    declared_states = array(cert["reachable_source_states"], "reachable_source_states")
    for state in declared_states:
        identifier(state, "reachable source state")
    if declared_states != sorted(graph.reachable):
        raise ReplayError("certificate reachable-source-state set is incomplete or incorrect")

    actual_bounds = require_object(cert["state_entry_bounds"], "state_entry_bounds")
    expected_bounds = graph.expected_state_bounds()
    if set(actual_bounds) != set(expected_bounds):
        raise ReplayError("certificate state-entry bounds name the wrong states")
    for state, bound in actual_bounds.items():
        exact_keys(bound, {"output_tokens", "input_tokens", "total_tokens"},
                   label=f"state-entry bounds for {state}")
        for component in ("output_tokens", "input_tokens", "total_tokens"):
            if type(bound[component]) is not int or bound[component] < 0:
                raise ReplayError(f"state {state} {component} must be a nonnegative integer")
        if bound != expected_bounds[state]:
            raise ReplayError(f"certificate state-entry bounds differ for {state}")

    natural(cert["product_nodes"], "product_nodes", maximum=MAX_REPORT_NODES)
    natural(cert["product_edges"], "product_edges", maximum=MAX_REPORT_NODES * 4)
    return cert


def _validate_node_encoding(value: Any, expected_id: int) -> dict[str, Any]:
    node = exact_keys(value, {"id", "left", "right", "equal_values", "rule", "successors"},
                      label=f"certificate node {expected_id}")
    if natural(node["id"], f"node {expected_id} id", maximum=MAX_REPORT_NODES) != expected_id:
        raise ReplayError("certificate nodes must have canonical consecutive IDs")
    for side in ("left", "right"):
        pc = array(node[side], f"node {expected_id} {side} program counter")
        if len(pc) != 2:
            raise ReplayError(f"node {expected_id} {side} program counter must have two fields")
        identifier(pc[0], f"node {expected_id} {side} state")
        natural(pc[1], f"node {expected_id} {side} event index")
    relation = array(node["equal_values"], f"node {expected_id} equal_values")
    for pair_index, pair in enumerate(relation):
        pair = array(pair, f"node {expected_id} relation pair {pair_index}")
        if len(pair) != 2:
            raise ReplayError("each relation pair must contain a left and right name")
        identifier(pair[0], "left relation name")
        identifier(pair[1], "right relation name")
    if relation != sorted(relation) or len({tuple(pair) for pair in relation}) != len(relation):
        raise ReplayError("node relation pairs must be sorted and unique")
    string(node["rule"], f"node {expected_id} rule", nonempty=True)
    successors = array(node["successors"], f"node {expected_id} successors")
    for successor in successors:
        natural(successor, f"node {expected_id} successor", maximum=MAX_REPORT_NODES)
    return node


def _serialize_product_state(left: tuple[str, int], right: tuple[str, int],
                             relation: frozenset[tuple[str, str]]) -> dict[str, Any]:
    return {
        "left": [left[0], left[1]],
        "right": [right[0], right[1]],
        "equal_values": [list(pair) for pair in sorted(relation)],
    }


def replay(graph_bytes: bytes, certificate_bytes: bytes) -> dict[str, Any]:
    source_digest = sha256(graph_bytes)
    graph = NormalizedGraph(strict_json(graph_bytes, "source graph"))
    certificate_doc = strict_json(certificate_bytes, "certificate")
    cert = _validate_certificate_shape(certificate_doc, graph, source_digest)
    nodes = cert["nodes"]
    for index, raw_node in enumerate(nodes):
        _validate_node_encoding(raw_node, index)

    public_identity = frozenset(
        (variable, variable)
        for variable, declaration in graph.inputs.items()
        if declaration["label"] == "public"
    )
    root_state = ((graph.entry, 0), (graph.entry, 0), public_identity)
    state_ids = {root_state: 0}
    pending = deque([root_state])
    expected_edges = 0
    visited = 0

    while pending:
        product = pending.popleft()
        left, right, relation = product
        node_id = state_ids[product]
        if node_id >= len(nodes):
            raise ReplayError("certificate omits a reachable product node")
        actual = nodes[node_id]
        rule, successor_states = _successors(graph, left, right, relation)
        successor_ids = []
        for successor in successor_states:
            if successor not in state_ids:
                if len(state_ids) >= cert["max_nodes"]:
                    raise ReplayError("certificate claims acceptance beyond its node resource cap")
                state_ids[successor] = len(state_ids)
                pending.append(successor)
            successor_ids.append(state_ids[successor])
        expected = {
            "id": node_id,
            **_serialize_product_state(left, right, relation),
            "rule": rule,
            "successors": successor_ids,
        }
        if actual != expected:
            raise ReplayError(f"certificate node {node_id} does not match its reconstructed obligation")
        visited += 1
        expected_edges += len(successor_ids)

    if visited != len(nodes):
        raise ReplayError("certificate contains unreachable or extra product nodes")
    if natural(cert["product_nodes"], "product_nodes") != visited:
        raise ReplayError("certificate product_nodes count is incorrect")
    if natural(cert["product_edges"], "product_edges") != expected_edges:
        raise ReplayError("certificate product_edges count is incorrect")

    replayer_digest = sha256(Path(__file__).read_bytes())
    cert_digest = sha256(certificate_bytes)
    return {
        "format": ATTESTATION_FORMAT,
        "version": 1,
        "status": "verified",
        "graph_name": graph.name,
        "source_sha256": source_digest,
        "certificate_sha256": cert_digest,
        "replayer_sha256": replayer_digest,
        "producer_checker_sha256": cert["checker_sha256"],
        "producer_checker_hash_verified": False,
        "resource_limits": {
            "json_bytes_each": MAX_JSON_BYTES,
            "graph_states": MAX_GRAPH_STATES,
            "graph_declarations_or_calls": MAX_GRAPH_ITEMS,
            "product_nodes": MAX_REPORT_NODES,
            "certificate_declared_product_nodes": cert["max_nodes"],
        },
        "product_nodes_replayed": visited,
        "product_edges_replayed": expected_edges,
        "checks": {
            "strict_graph_and_certificate_schema": True,
            "source_hash_binding": True,
            "graph_schema_and_types": True,
            "reachable_source_states_and_cost_summaries": True,
            "root_public_identity_relation": True,
            "all_product_relations_and_local_rules": True,
            "complete_universal_successor_closure": True,
            "no_unreachable_or_extra_product_nodes": True,
            "call_free_cycle_exclusion": True,
        },
        "scope": {
            "claim": "the reported finite product graph is the complete closure of the replayed version-1 graph under the declared local rules",
            "not_claimed": [
                "mechanized proof of the relational metatheory",
                "source-language or framework-to-graph translation fidelity",
                "real provider request serialization or billing behavior",
                "termination or finite total-cost bounds for billable cycles",
                "validation of the producer checker implementation from its reported hash",
            ],
        },
    }


def _read_limited(path: Path, label: str) -> bytes:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ReplayError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    data = path.read_bytes()
    if len(data) > MAX_JSON_BYTES:
        raise ReplayError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, help="exact JSON graph whose hash is bound by the certificate")
    parser.add_argument("certificate", type=Path, help="accepted cyclic-request certificate JSON")
    parser.add_argument("--attestation", type=Path, help="also write the replay attestation to this path")
    args = parser.parse_args(argv)
    try:
        graph_bytes = _read_limited(args.graph, "source graph")
        certificate_bytes = _read_limited(args.certificate, "certificate")
        report = replay(graph_bytes, certificate_bytes)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.attestation:
            args.attestation.parent.mkdir(parents=True, exist_ok=True)
            args.attestation.write_text(encoded, encoding="utf-8", newline="")
        print(encoded, end="")
        return 0
    except (ReplayError, OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        print(f"certificate replay failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
