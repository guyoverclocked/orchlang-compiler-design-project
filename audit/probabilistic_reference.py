#!/usr/bin/env python3
"""Independent exhaustive evaluator for finite probabilistic billing channels.

This module deliberately has no dependency on the graph producer, certificate
replayer, or the probabilistic-channel analyzer.  It normalizes the v1 graph
and outcome-kernel documents locally, then enumerates complete bounded
executions without merging states.  The oracle is intended for small,
reviewable validation cases rather than large production models.

The probability kernel is offline and finite.  It is not a provider model and
does not establish empirical provider behavior.  See
``docs/PROBABILISTIC_CHANNELS.md`` for the surrounding research contract.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
from typing import Any


GRAPH_FORMAT = "orchlang-request-graph"
KERNEL_FORMAT = "orchlang-finite-outcome-kernel"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
PROBABILITY_RE = re.compile(r"^(?:[1-9][0-9]*|[1-9][0-9]*/[1-9][0-9]*)$")
MAX_TOKEN = 2**64 - 2
MAX_JSON_BYTES = 128 * 1024 * 1024
MAX_GRAPH_STATES = 100_000
MAX_GRAPH_ITEMS = 1_000_000
MAX_TEXT_BYTES = 1024 * 1024
MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_HORIZON = 32
MAX_PATHS = 1_000_000
MAX_WORK_STEPS = 10_000_000
MAX_WORK_BYTES = 1024 * 1024 * 1024
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}


class ReferenceError(ValueError):
    """Malformed graph, kernel, store, or unsupported execution."""


class ResourceExhausted(RuntimeError):
    """Enumeration could not complete within its explicit resource budget."""


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReferenceError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReferenceError(f"non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReferenceError(f"non-finite JSON number: {value}")
    return number


def _load_document(source: Any, label: str) -> Any:
    if isinstance(source, Mapping):
        # Do not round-trip a caller mapping through json: retain type checks
        # (especially bool-vs-int) and reject non-JSON objects explicitly.
        _validate_json_value(source, label)
        return source
    if isinstance(source, os.PathLike):
        try:
            path = Path(source)
            if path.stat().st_size > MAX_JSON_BYTES:
                raise ReferenceError(f"{label} exceeds the JSON byte resource limit")
            raw = path.read_bytes()
        except OSError as error:
            raise ReferenceError(f"cannot read {label}: {error}") from error
    elif isinstance(source, bytes):
        raw = source
    elif isinstance(source, str):
        if len(source) > MAX_JSON_BYTES:
            raise ReferenceError(f"{label} exceeds the JSON byte resource limit")
        try:
            raw = source.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ReferenceError(f"{label} text contains a non-scalar Unicode code point") from error
    else:
        raise ReferenceError(f"{label} must be a mapping, JSON text/bytes, or path")
    if len(raw) > MAX_JSON_BYTES:
        raise ReferenceError(f"{label} exceeds the JSON byte resource limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_without_duplicates,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ReferenceError):
            raise
        raise ReferenceError(f"invalid {label} JSON: {error}") from error


def _validate_json_value(value: Any, label: str, depth: int = 0,
                         budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [0, 0]  # item count, approximate serialized bytes
    if depth > 256:
        raise ReferenceError(f"{label} nesting exceeds the resource limit")
    budget[0] += 1
    budget[1] += 1
    if budget[0] > MAX_GRAPH_ITEMS or budget[1] > MAX_JSON_BYTES:
        raise ReferenceError(f"{label} exceeds the in-memory JSON resource limit")
    if value is None or type(value) in (bool, float):
        if type(value) is float and not math.isfinite(value):
            raise ReferenceError(f"{label} contains a non-finite number")
        return
    if type(value) is int:
        bits = value.bit_length()
        if bits > MAX_JSON_BYTES * 4:
            raise ReferenceError(f"{label} integer exceeds the JSON byte resource limit")
        budget[1] += max(1, int(bits * 0.302) + 1)
        if budget[1] > MAX_JSON_BYTES:
            raise ReferenceError(f"{label} exceeds the in-memory JSON resource limit")
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_BYTES:
            raise ReferenceError(f"{label} contains a string over the text byte resource limit")
        _utf8(value, label)
        budget[1] += len(value.encode("utf-8"))
        if budget[1] > MAX_JSON_BYTES:
            raise ReferenceError(f"{label} exceeds the in-memory JSON resource limit")
        return
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ReferenceError(f"{label} has a non-string object key")
        for key, child in value.items():
            if len(key) > MAX_TEXT_BYTES:
                raise ReferenceError(f"{label} contains an object key over the text byte resource limit")
            _utf8(key, label + " key")
            budget[1] += len(key.encode("utf-8"))
            _validate_json_value(child, label, depth + 1, budget)
        return
    if isinstance(value, list):
        for child in value:
            _validate_json_value(child, label, depth + 1, budget)
        return
    raise ReferenceError(f"{label} contains a non-JSON value")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReferenceError(f"{label} must be an object")
    return value


def _keys(value: Any, required: set[str], optional: set[str] = frozenset(),
          label: str = "object") -> dict[str, Any]:
    obj = _object(value, label)
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing or unknown:
        raise ReferenceError(f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return obj


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReferenceError(f"{label} must be an array")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ReferenceError(f"{label} is not a valid identifier: {value!r}")
    return value


def _natural(value: Any, label: str, minimum: int = 0,
             maximum: int = MAX_TOKEN) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReferenceError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _utf8(value: Any, label: str, *, maximum: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise ReferenceError(f"{label} must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ReferenceError(f"{label} contains a non-scalar Unicode code point") from error
    if maximum is not None and len(encoded) > maximum:
        raise ReferenceError(f"{label} exceeds the {maximum}-byte resource limit")
    return encoded


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _parse_probability(value: Any, label: str) -> Fraction:
    if not isinstance(value, str) or len(value) > 2001 or not PROBABILITY_RE.fullmatch(value):
        raise ReferenceError(f"{label} must be a positive exact integer or n/d string")
    if "/" in value:
        numerator_text, denominator_text = value.split("/")
    else:
        numerator_text, denominator_text = value, "1"
    # Bound integer parsing even for mapping inputs; probabilities are exact,
    # but unbounded integer strings are not a useful adversarial input here.
    if len(numerator_text) > 1000 or len(denominator_text) > 1000:
        raise ReferenceError(f"{label} exceeds the exact-rational resource limit")
    return Fraction(int(numerator_text), int(denominator_text))


class _Graph:
    """Small local implementation of the typed v1 request-graph contract."""

    def __init__(self, document: Any):
        root = _keys(document,
                     {"format", "version", "name", "inputs", "registers", "models", "states", "entry"},
                     {"chars_per_token"}, "graph")
        if root["format"] != GRAPH_FORMAT or type(root["version"]) is not int or root["version"] != 1:
            raise ReferenceError("unsupported request graph format/version")
        self.name = _identifier(root["name"], "graph name")
        self.divisor = _natural(root.get("chars_per_token", 4), "chars_per_token", 1)
        raw_inputs = _object(root["inputs"], "inputs")
        raw_registers = _object(root["registers"], "registers")
        raw_models = _object(root["models"], "models")
        raw_states = _object(root["states"], "states")
        if not raw_states:
            raise ReferenceError("graph must contain at least one state")
        if len(raw_states) > MAX_GRAPH_STATES:
            raise ReferenceError("graph state resource limit exceeded")
        if sum(map(len, (raw_inputs, raw_registers, raw_models, raw_states))) > MAX_GRAPH_ITEMS:
            raise ReferenceError("graph declaration resource limit exceeded")

        self.inputs: dict[str, dict[str, Any]] = {}
        self.registers: dict[str, dict[str, str]] = {}
        self.models: dict[str, dict[str, Any]] = {}
        self.states: dict[str, dict[str, Any]] = {}

        for alias, raw in raw_models.items():
            _identifier(alias, "model alias")
            model = _keys(raw, {"provider", "model", "max_tokens"}, {"unit_price"}, f"model {alias}")
            provider = self._text(model["provider"], f"model {alias} provider", nonempty=True)
            model_id = self._text(model["model"], f"model {alias} name", nonempty=True)
            cap = _natural(model["max_tokens"], f"model {alias} max_tokens", 1)
            price = model.get("unit_price", 0.0)
            if type(price) not in (int, float):
                raise ReferenceError(f"model {alias} unit_price must be numeric")
            try:
                finite = float(price)
            except (OverflowError, ValueError) as error:
                raise ReferenceError(f"model {alias} unit_price is not finite") from error
            if not math.isfinite(finite) or finite < 0:
                raise ReferenceError(f"model {alias} unit_price must be finite and nonnegative")
            self.models[alias] = {
                "provider": provider, "model": model_id, "max_tokens": cap,
                "has_unit_price": "unit_price" in model, "unit_price": finite or 0.0,
            }

        for variable, raw in raw_inputs.items():
            _identifier(variable, "input name")
            declaration = _keys(raw, {"type", "label"}, {"max_tokens"}, f"input {variable}")
            if declaration["type"] not in ("text", "boolean") or declaration["label"] not in ("public", "secret"):
                raise ReferenceError(f"input {variable} must be text/boolean and public/secret")
            if declaration["type"] == "text" and "max_tokens" not in declaration:
                raise ReferenceError(f"text input {variable} requires max_tokens")
            cap = _natural(declaration.get("max_tokens", 1), f"input {variable} max_tokens")
            self.inputs[variable] = {"type": declaration["type"], "label": declaration["label"],
                                     "max_tokens": cap}

        for variable, raw in raw_registers.items():
            _identifier(variable, "register name")
            declaration = _keys(raw, {"model"}, label=f"register {variable}")
            alias = _identifier(declaration["model"], f"register {variable} model")
            if variable in self.inputs:
                raise ReferenceError(f"input/register name collision: {variable}")
            if alias not in self.models:
                raise ReferenceError(f"register {variable} refers to an unknown model")
            self.registers[variable] = {"model": alias}

        total_calls = 0
        for state, raw in raw_states.items():
            _identifier(state, "state name")
            body = _keys(raw, {"calls", "next"}, label=f"state {state}")
            calls = []
            for index, raw_call in enumerate(_array(body["calls"], f"state {state} calls")):
                total_calls += 1
                if total_calls > MAX_GRAPH_ITEMS:
                    raise ReferenceError("graph call resource limit exceeded")
                call = _keys(raw_call, {"model", "template", "arguments", "result"},
                             label=f"call {state}[{index}]")
                alias = _identifier(call["model"], "call model")
                result = _identifier(call["result"], "call result")
                template = self._text(call["template"], "call template")
                if alias not in self.models:
                    raise ReferenceError(f"call in {state} uses an unknown model")
                if result not in self.registers:
                    raise ReferenceError(f"call in {state} uses an undeclared result register")
                contract = self.models[alias]
                result_contract = self.models[self.registers[result]["model"]]
                if self.unit(contract) != self.unit(result_contract):
                    raise ReferenceError("call result register changes provider/model token unit")
                if contract["max_tokens"] > result_contract["max_tokens"]:
                    raise ReferenceError("call result register cap is too small")
                arguments = []
                for raw_atom in _array(call["arguments"], "call arguments"):
                    atom = _object(raw_atom, "argument atom")
                    if set(atom) == {"literal"}:
                        arguments.append({"literal": self._text(atom["literal"], "literal argument")})
                    elif set(atom) == {"value"}:
                        variable = _identifier(atom["value"], "argument value")
                        if variable in self.inputs:
                            decl = self.inputs[variable]
                            if decl["type"] != "text" or decl["label"] != "public":
                                raise ReferenceError("only public text inputs may appear in requests")
                        elif variable in self.registers:
                            producer = self.models[self.registers[variable]["model"]]
                            if self.unit(producer) != self.unit(contract):
                                raise ReferenceError("generated request value crosses token units")
                        else:
                            raise ReferenceError(f"unknown request argument {variable}")
                        arguments.append({"value": variable})
                    else:
                        raise ReferenceError("argument atom must contain exactly literal or value")
                calls.append({"model": alias, "template": template,
                              "arguments": arguments, "result": result})
            decision = self.normalize_decision(body["next"], state)
            self.states[state] = {"calls": calls, "next": decision}

        self.entry = _identifier(root["entry"], "entry state")
        if self.entry not in self.states:
            raise ReferenceError("entry state is undeclared")
        for state, body in self.states.items():
            for target in self.targets(body["next"]):
                if target not in self.states:
                    raise ReferenceError(f"state {state} targets unknown state {target}")
        self.reachable = self._reachable()
        self._reject_silent_cycles()
        self.contracts: dict[str, dict[str, Any]] = {}
        for contract in self.models.values():
            self.contracts[_canonical(contract)] = contract

    @staticmethod
    def _text(value: Any, label: str, *, nonempty: bool = False) -> str:
        if not isinstance(value, str) or (nonempty and not value):
            raise ReferenceError(f"{label} must be a {'nonempty ' if nonempty else ''}string")
        _utf8(value, label, maximum=MAX_TEXT_BYTES)
        return value

    def _reachable(self) -> set[str]:
        found: set[str] = set()
        pending = [self.entry]
        while pending:
            state = pending.pop()
            if state not in found:
                found.add(state)
                pending.extend(self.targets(self.states[state]["next"]))
        return found

    def _reject_silent_cycles(self) -> None:
        empty = {state for state in self.reachable if not self.states[state]["calls"]}
        indegree = {state: 0 for state in empty}
        edges = {state: [target for target in self.targets(self.states[state]["next"])
                         if target in empty] for state in empty}
        for targets in edges.values():
            for target in targets:
                indegree[target] += 1
        pending = [state for state, count in indegree.items() if count == 0]
        removed = 0
        while pending:
            state = pending.pop()
            removed += 1
            for target in edges[state]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        if removed != len(empty):
            raise ReferenceError("reachable call-free control cycle is unsupported")

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

    def normalize_decision(self, raw: Any, state: str) -> dict[str, Any]:
        decision = _object(raw, f"state {state} decision")
        kind = decision.get("kind")
        if kind == "goto":
            _keys(decision, {"kind", "target"}, label="goto")
            return {"kind": kind, "target": _identifier(decision["target"], "goto target")}
        if kind == "stop":
            _keys(decision, {"kind"}, label="stop")
            return {"kind": kind}
        if kind not in ("public", "secret"):
            raise ReferenceError(f"unknown control kind {kind!r}")
        _keys(decision, {"kind", "guard", "then", "else"}, label="guard decision")
        guard = _object(decision["guard"], "guard")
        _keys(guard, {"value"}, {"op", "limit"}, "guard")
        subject = _identifier(guard["value"], "guard subject")
        if subject in self.inputs:
            boolean = self.inputs[subject]["type"] == "boolean"
            secret = self.inputs[subject]["label"] == "secret"
        elif subject in self.registers:
            boolean, secret = False, False
        else:
            raise ReferenceError(f"unknown guard subject {subject}")
        if boolean:
            _keys(guard, {"value"}, label="Boolean guard")
            normalized_guard = {"value": subject}
        else:
            _keys(guard, {"value", "op", "limit"}, label="text guard")
            op = self._text(guard["op"], "guard operator")
            if op not in COMPARISONS:
                raise ReferenceError(f"unsupported guard operator {op!r}")
            normalized_guard = {"value": subject, "op": op,
                                "limit": _natural(guard["limit"], "guard limit")}
        if (kind == "secret") != secret:
            raise ReferenceError("guard confidentiality disagrees with its subject")
        return {"kind": kind, "guard": normalized_guard,
                "then": _identifier(decision["then"], "then successor"),
                "else": _identifier(decision["else"], "else successor")}

    def event(self, pc: tuple[str, int]) -> tuple[str, dict[str, Any]]:
        state, index = pc
        calls = self.states[state]["calls"]
        if index < len(calls):
            return "call", calls[index]
        if index != len(calls):
            raise ReferenceError("program counter outside state's event sequence")
        decision = self.states[state]["next"]
        return decision["kind"], decision

    def estimate(self, text: str) -> int:
        return (len(_utf8(text, "accounted text")) + self.divisor - 1) // self.divisor


@dataclass(frozen=True)
class _Outcome:
    response: str
    output_tokens: int
    probability: Fraction


class _Kernel:
    def __init__(self, document: Any, graph: _Graph):
        root = _keys(document, {"format", "version", "defaults"}, {"rules", "history_window"}, "kernel")
        if root["format"] != KERNEL_FORMAT or type(root["version"]) is not int or root["version"] != 1:
            raise ReferenceError("unsupported outcome kernel format/version")
        self.window = _natural(root.get("history_window", 0), "history_window", 0, 4)
        raw_defaults = _object(root["defaults"], "kernel defaults")
        if not raw_defaults and graph.contracts:
            raise ReferenceError("kernel defaults must cover every resolved graph contract")
        self.defaults_by_alias: dict[str, tuple[_Outcome, ...]] = {}
        self.defaults_by_contract: dict[str, tuple[_Outcome, ...]] = {}
        for alias, raw_dist in raw_defaults.items():
            _identifier(alias, "kernel model alias")
            if alias not in graph.models:
                raise ReferenceError(f"kernel defaults refer to unknown model alias {alias}")
            dist = self._distribution(raw_dist, graph.models[alias], f"default {alias}", graph)
            contract_key = _canonical(graph.models[alias])
            previous = self.defaults_by_contract.get(contract_key)
            if previous is not None and self._distribution_key(previous) != self._distribution_key(dist):
                raise ReferenceError("same-contract model aliases have different default distributions")
            self.defaults_by_alias[alias] = dist
            self.defaults_by_contract[contract_key] = dist
        if set(self.defaults_by_contract) != set(graph.contracts):
            raise ReferenceError("kernel defaults must cover every resolved graph contract")

        self.rules: list[dict[str, Any]] = []
        raw_rules = _array(root.get("rules", []), "kernel rules")
        if len(raw_rules) > 10_000:
            raise ReferenceError("kernel rule resource limit exceeded")
        for index, raw_rule in enumerate(raw_rules):
            rule = _keys(raw_rule, {"model", "outcomes"},
                         {"template", "arguments", "ordinal", "history"}, f"kernel rule {index}")
            alias = _identifier(rule["model"], f"rule {index} model")
            if alias not in graph.models:
                raise ReferenceError(f"rule {index} refers to unknown model alias {alias}")
            normalized: dict[str, Any] = {"contract_key": _canonical(graph.models[alias])}
            if "template" in rule:
                normalized["template"] = graph._text(rule["template"], f"rule {index} template")
            if "arguments" in rule:
                args = [_utf8(x, f"rule {index} argument", maximum=MAX_TEXT_BYTES).decode("utf-8")
                        for x in _array(rule["arguments"], f"rule {index} arguments")]
                normalized["arguments"] = args
            if "ordinal" in rule:
                normalized["ordinal"] = _natural(rule["ordinal"], f"rule {index} ordinal", 0, MAX_HORIZON)
            if "history" in rule:
                raw_history = _array(rule["history"], f"rule {index} history")
                if len(raw_history) > self.window:
                    raise ReferenceError(f"rule {index} history exceeds the finite window")
                normalized["history"] = tuple(
                    self._event(item, graph, f"rule {index} history event {event_index}")
                    for event_index, item in enumerate(raw_history)
                )
            normalized["outcomes"] = self._distribution(
                rule["outcomes"], graph.models[alias], f"rule {index} outcomes", graph)
            self.rules.append(normalized)

    @staticmethod
    def _distribution_key(distribution: tuple[_Outcome, ...]) -> tuple[tuple[str, int, Fraction], ...]:
        return tuple(sorted((item.response, item.output_tokens, item.probability) for item in distribution))

    @staticmethod
    def _distribution(raw: Any, contract: dict[str, Any], label: str,
                      graph: _Graph) -> tuple[_Outcome, ...]:
        outcomes = _array(raw, label)
        if not outcomes or len(outcomes) > 256:
            raise ReferenceError(f"{label} must contain 1..256 outcomes")
        merged: dict[tuple[str, int], Fraction] = {}
        total = Fraction(0, 1)
        for index, raw_outcome in enumerate(outcomes):
            outcome = _keys(raw_outcome, {"response", "output_tokens", "probability"},
                            label=f"{label} outcome {index}")
            response = graph._text(outcome["response"], f"{label} response")
            output_tokens = _natural(outcome["output_tokens"], f"{label} output_tokens")
            if graph.estimate(response) > output_tokens:
                raise ReferenceError(f"{label} reported output usage undercounts response text")
            if output_tokens > contract["max_tokens"]:
                raise ReferenceError(f"{label} output usage exceeds model cap")
            probability = _parse_probability(outcome["probability"], f"{label} probability")
            key = (response, output_tokens)
            merged[key] = merged.get(key, Fraction(0, 1)) + probability
            total += probability
        if total != 1:
            raise ReferenceError(f"{label} probabilities must sum exactly to one (got {_fraction_text(total)})")
        return tuple(_Outcome(response, output_tokens, probability)
                     for (response, output_tokens), probability in sorted(merged.items()))

    @staticmethod
    def _event(raw: Any, graph: _Graph, label: str) -> dict[str, Any]:
        event = _keys(raw, {"contract", "ordinal", "template", "arguments", "response",
                            "input_tokens", "output_tokens"}, label=label)
        contract_raw = _object(event["contract"], f"{label} contract")
        _keys(contract_raw, {"provider", "model", "max_tokens", "has_unit_price", "unit_price"},
              label=f"{label} contract")
        provider = graph._text(contract_raw["provider"], f"{label} provider", nonempty=True)
        model_id = graph._text(contract_raw["model"], f"{label} model", nonempty=True)
        cap = _natural(contract_raw["max_tokens"], f"{label} max_tokens", 1)
        has_price = contract_raw["has_unit_price"]
        if type(has_price) is not bool:
            raise ReferenceError(f"{label} has_unit_price must be Boolean")
        price_raw = contract_raw["unit_price"]
        if type(price_raw) not in (int, float):
            raise ReferenceError(f"{label} unit_price must be numeric")
        try:
            price = float(price_raw)
        except (OverflowError, ValueError) as error:
            raise ReferenceError(f"{label} unit_price is not finite") from error
        if not math.isfinite(price) or price < 0:
            raise ReferenceError(f"{label} unit_price must be finite and nonnegative")
        contract = {"provider": provider, "model": model_id, "max_tokens": cap,
                    "has_unit_price": has_price, "unit_price": price or 0.0}
        contract_key = _canonical(contract)
        if contract_key not in graph.contracts:
            raise ReferenceError(f"{label} contract is not a resolved graph model contract")
        ordinal = _natural(event["ordinal"], f"{label} ordinal", 0, MAX_HORIZON)
        template = graph._text(event["template"], f"{label} template")
        arguments = [_utf8(x, f"{label} argument", maximum=MAX_TEXT_BYTES).decode("utf-8")
                     for x in _array(event["arguments"], f"{label} arguments")]
        response = graph._text(event["response"], f"{label} response")
        input_tokens = _natural(event["input_tokens"], f"{label} input_tokens")
        output_tokens = _natural(event["output_tokens"], f"{label} output_tokens")
        expected_input = graph.estimate(template) + sum(graph.estimate(arg) for arg in arguments)
        if input_tokens != expected_input:
            raise ReferenceError(f"{label} input usage is not exact additive UTF-8 accounting")
        if graph.estimate(response) > output_tokens or output_tokens > cap:
            raise ReferenceError(f"{label} output usage is inconsistent with response/cap")
        return {"contract": contract, "ordinal": ordinal, "template": template,
                "arguments": arguments, "response": response,
                "input_tokens": input_tokens, "output_tokens": output_tokens}

    def choose(self, contract_key: str, template: str, arguments: list[str], ordinal: int,
               history: tuple[dict[str, Any], ...], call: dict[str, Any]) -> tuple[_Outcome, ...]:
        for rule in self.rules:
            if rule["contract_key"] != contract_key:
                continue
            if "template" in rule and rule["template"] != template:
                continue
            if "arguments" in rule and rule["arguments"] != arguments:
                continue
            if "ordinal" in rule and rule["ordinal"] != ordinal:
                continue
            if "history" in rule and rule["history"] != history:
                # The field is the exact retained bounded history (oldest to
                # newest), not a pattern over an arbitrary suffix.
                continue
            return rule["outcomes"]
        try:
            return self.defaults_by_contract[contract_key]
        except KeyError as error:
            raise ReferenceError("request contract has no default outcome distribution") from error


def _observation_value(stopped: bool, billing: dict[str, list[int]],
                       contracts: dict[str, dict[str, Any]], usage_trace: list[dict[str, Any]],
                       observer: str) -> dict[str, Any]:
    if observer == "trace":
        return {"stopped": stopped, "usage_trace": usage_trace}
    entries = []
    for contract_key in sorted(contracts):
        call_count, input_tokens, output_tokens = billing.get(contract_key, [0, 0, 0])
        entries.append({"contract": contracts[contract_key], "call_count": call_count,
                        "input_tokens": input_tokens, "output_tokens": output_tokens})
    return {"stopped": stopped, "billing": entries}


def independent_histogram(graph_document: Any, kernel_document: Any, store: Mapping[str, Any],
                          horizon: int, max_paths: int = 100_000, *,
                          max_steps: int = 1_000_000,
                          max_work_bytes: int = 64 * 1024 * 1024,
                          observer: str = "aggregate") -> dict[str, Any]:
    """Enumerate all finite-kernel executions for one complete fixed store.

    ``store`` contains every graph input, including the explicit values assigned
    to secret inputs.  Secret values only control the graph's own secret
    guards; they are never exposed to kernel rule matching or observations.
    Rules inspect the resolved request contract, exact request, per-contract
    ordinal, and the exact retained bounded history of prior complete call events (oldest to
    newest).  Defaults provide the fallback distribution.

    A terminal execution is recorded only at `stop` or when the next call is
    reached after `horizon` calls.  Thus deterministic goto/guard/stop events
    following the horizon-th call are still observed.  This is an exhaustive
    path-tree DFS: paths are never merged, even when their configurations are
    equal.  If a resource limit is reached, status is ``unknown`` and no partial
    histogram or mass is returned.  ``max_work_bytes`` bounds cumulative
    canonical DFS-state/path serialization, request/response payload work, and
    terminal observation serialization.  Canonical JSON is counted as it is
    streamed, so exceeding the cap does not require materializing the rest of
    a large state or observation.
    """
    horizon = _natural(horizon, "call horizon", 1, MAX_HORIZON)
    max_paths = _natural(max_paths, "max_paths", 1, MAX_PATHS)
    max_steps = _natural(max_steps, "max_steps", 1, MAX_WORK_STEPS)
    max_work_bytes = _natural(max_work_bytes, "max_work_bytes", 1, MAX_WORK_BYTES)
    if observer not in ("aggregate", "trace"):
        raise ReferenceError("observer must be 'aggregate' or 'trace'")
    graph = _Graph(_load_document(graph_document, "graph"))
    kernel = _Kernel(_load_document(kernel_document, "kernel"), graph)
    if not isinstance(store, Mapping) or not all(isinstance(key, str) for key in store):
        raise ReferenceError("store must be a mapping with string input names")
    if set(store) != set(graph.inputs):
        raise ReferenceError("store must name every graph input exactly once")
    values: dict[str, Any] = dict(store)
    for name, declaration in graph.inputs.items():
        value = values[name]
        if declaration["type"] == "boolean":
            if type(value) is not bool:
                raise ReferenceError(f"Boolean input {name} has the wrong type")
        else:
            text = graph._text(value, f"input {name}")
            if graph.estimate(text) > declaration["max_tokens"]:
                raise ReferenceError(f"text input {name} exceeds its declared token bound")

    contracts = graph.contracts
    histogram: dict[str, Fraction] = {}
    complete_paths = expanded_outcomes = control_steps = work_bytes = 0
    unknown: str | None = None

    def charge_step() -> None:
        nonlocal control_steps
        control_steps += 1
        if control_steps > max_steps:
            raise ResourceExhausted("enumeration control/work-step limit reached")

    def charge_bytes(amount: int) -> None:
        nonlocal work_bytes
        work_bytes += amount
        if work_bytes > max_work_bytes:
            work_bytes = max_work_bytes + 1
            raise ResourceExhausted("enumeration aggregate byte-work limit reached")

    def canonical_work(value: Any, *, retain: bool) -> str | None:
        """Count exact UTF-8 bytes emitted by canonical JSON, stopping at cap."""
        nonlocal work_bytes
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False)
        chunks: list[str] | None = [] if retain else None
        for chunk in encoder.iterencode(value):
            size = len(chunk.encode("utf-8"))
            work_bytes += size
            if work_bytes > max_work_bytes:
                work_bytes = max_work_bytes + 1
                raise ResourceExhausted("enumeration canonical byte-work limit reached")
            if chunks is not None:
                chunks.append(chunk)
        return None if chunks is None else "".join(chunks)

    def charge_state(pc: tuple[str, int], branch_values: dict[str, Any],
                     ordinals: dict[str, int], billing: dict[str, list[int]],
                     history: tuple[dict[str, Any], ...], execution_path: tuple[dict[str, Any], ...],
                     calls_seen: int, trace_bytes: int, usage_trace: list[dict[str, Any]],
                     probability: Fraction) -> None:
        canonical_work({
            "pc": [pc[0], pc[1]],
            "values": branch_values,
            "ordinals": ordinals,
            "billing": billing,
            "history": history,
            "execution_path": execution_path,
            "calls_seen": calls_seen,
            "trace_bytes": trace_bytes,
            "usage_trace": usage_trace if observer == "trace" else [],
            "probability": _fraction_text(probability),
        }, retain=False)

    def complete(stopped: bool, probability: Fraction,
                 billing: dict[str, list[int]], usage_trace: list[dict[str, Any]]) -> None:
        nonlocal complete_paths
        complete_paths += 1
        if complete_paths > max_paths:
            raise ResourceExhausted("enumeration complete-path limit reached")
        observation = _observation_value(stopped, billing, contracts, usage_trace, observer)
        key = canonical_work(observation, retain=True)
        assert key is not None
        charge_bytes(len(_utf8(_fraction_text(probability), "path probability")))
        histogram[key] = histogram.get(key, Fraction(0, 1)) + probability

    def walk(pc: tuple[str, int], branch_values: dict[str, Any],
             ordinals: dict[str, int], billing: dict[str, list[int]],
             history: tuple[dict[str, Any], ...], calls_seen: int,
             trace_bytes: int, usage_trace: list[dict[str, Any]],
             execution_path: tuple[dict[str, Any], ...],
             probability: Fraction) -> None:
        nonlocal expanded_outcomes
        while True:
            charge_state(pc, branch_values, ordinals, billing, history, execution_path,
                         calls_seen, trace_bytes, usage_trace, probability)
            charge_step()
            kind, event = graph.event(pc)
            if kind == "stop":
                complete(True, probability, billing, usage_trace)
                return
            if kind == "goto":
                pc = (event["target"], 0)
                continue
            if kind in ("public", "secret"):
                subject = event["guard"]["value"]
                if subject not in branch_values:
                    raise ReferenceError(f"execution guard reads uninitialized value {subject}")
                value = branch_values[subject]
                guard = event["guard"]
                if "op" not in guard:
                    decision = value
                else:
                    left, right, op = graph.estimate(value), guard["limit"], guard["op"]
                    decision = {"<": left < right, "<=": left <= right,
                                ">": left > right, ">=": left >= right,
                                "==": left == right, "!=": left != right}[op]
                pc = (event["then" if decision else "else"], 0)
                continue
            if kind != "call":
                raise ReferenceError(f"unsupported event kind {kind!r}")
            if calls_seen >= horizon:
                complete(False, probability, billing, usage_trace)
                return

            contract = graph.models[event["model"]]
            contract_key = _canonical(contract)
            ordinal = ordinals.get(contract_key, 0)
            if any("value" in atom and atom["value"] not in branch_values
                   for atom in event["arguments"]):
                raise ReferenceError("execution request reads an uninitialized value")
            arguments = [atom["literal"] if "literal" in atom else branch_values[atom["value"]]
                         for atom in event["arguments"]]
            if not all(isinstance(argument, str) for argument in arguments):
                raise ReferenceError("request arguments must resolve to text")
            request_bytes = len(_utf8(event["template"], "request template", maximum=MAX_TEXT_BYTES))
            request_bytes += sum(len(_utf8(argument, "request argument", maximum=MAX_TEXT_BYTES))
                                 for argument in arguments)
            if request_bytes > MAX_TEXT_BYTES:
                raise ReferenceError("request exceeds the aggregate value byte limit")
            input_tokens = graph.estimate(event["template"]) + sum(graph.estimate(arg) for arg in arguments)
            distribution = kernel.choose(contract_key, event["template"], arguments, ordinal,
                                         history, event)

            # The recursion below is over outcome paths. The next state gets
            # isolated copies so branches cannot share register/billing data.
            for outcome in distribution:
                expanded_outcomes += 1
                next_trace_bytes = trace_bytes + request_bytes + len(_utf8(outcome.response, "response"))
                if next_trace_bytes > MAX_TRACE_BYTES:
                    raise ResourceExhausted("one execution path exceeds the trace-byte limit")
                charge_bytes(request_bytes + len(outcome.response.encode("utf-8")))
                call_event = {
                    "contract": contract, "ordinal": ordinal,
                    "template": event["template"], "arguments": arguments,
                    "response": outcome.response, "input_tokens": input_tokens,
                    "output_tokens": outcome.output_tokens,
                }
                next_values = dict(branch_values)
                next_values[event["result"]] = outcome.response
                next_ordinals = dict(ordinals)
                next_ordinals[contract_key] = ordinal + 1
                next_billing = {key: list(counts) for key, counts in billing.items()}
                usage = next_billing.setdefault(contract_key, [0, 0, 0])
                usage[0] += 1
                usage[1] += input_tokens
                usage[2] += outcome.output_tokens
                next_history = (history + (call_event,))[-kernel.window:] if kernel.window else ()
                next_usage_trace = usage_trace + [{
                    "contract": contract, "input_tokens": input_tokens,
                    "output_tokens": outcome.output_tokens,
                }]
                next_execution_path = execution_path + (call_event,)
                walk((pc[0], pc[1] + 1), next_values, next_ordinals, next_billing,
                     next_history, calls_seen + 1, next_trace_bytes, next_usage_trace,
                     next_execution_path,
                     probability * outcome.probability)
            return

    try:
        walk((graph.entry, 0), values, {}, {}, (), 0, 0, [], (), Fraction(1, 1))
    except ResourceExhausted as error:
        unknown = str(error)
    if unknown is not None:
        return {"status": "unknown", "histogram": None, "mass": None,
                "leaf_paths": complete_paths, "call_transitions": expanded_outcomes,
                "control_steps": control_steps, "work_bytes": work_bytes,
                "max_paths": max_paths, "max_steps": max_steps,
                "max_work_bytes": max_work_bytes, "observer": observer,
                "horizon": horizon, "diagnostic": unknown}
    mass = sum(histogram.values(), Fraction(0, 1))
    if mass != 1:
        # This is an internal invariant: with finite, positive, normalized
        # kernels and complete traversal, every path probability must sum to 1.
        raise AssertionError(f"exhaustive histogram mass is {_fraction_text(mass)}, not one")
    return {"status": "complete", "histogram": dict(sorted(histogram.items())),
            "mass": mass, "leaf_paths": complete_paths,
            "call_transitions": expanded_outcomes, "control_steps": control_steps,
            "work_bytes": work_bytes, "max_paths": max_paths,
            "max_steps": max_steps, "max_work_bytes": max_work_bytes,
            "observer": observer, "horizon": horizon,
            "diagnostic": None}


def main(argv: list[str] | None = None) -> int:
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("graph", type=Path)
    cli.add_argument("kernel", type=Path)
    cli.add_argument("store", type=Path, help="JSON object assigning every input, including secrets")
    cli.add_argument("--horizon", type=int, required=True)
    cli.add_argument("--max-paths", type=int, default=100_000)
    cli.add_argument("--max-steps", type=int, default=1_000_000)
    cli.add_argument("--max-work-bytes", type=int, default=64 * 1024 * 1024)
    args = cli.parse_args(argv)
    try:
        store = _load_document(args.store, "store")
        if not isinstance(store, Mapping):
            raise ReferenceError("store JSON must be an object")
        result = independent_histogram(args.graph, args.kernel, store, args.horizon,
                                       args.max_paths, max_steps=args.max_steps,
                                       max_work_bytes=args.max_work_bytes)
        report = dict(result)
        if result["histogram"] is not None:
            report["histogram"] = {key: _fraction_text(value)
                                   for key, value in result["histogram"].items()}
            report["mass"] = _fraction_text(result["mass"])
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "complete" else 2
    except (ReferenceError, ValueError, TypeError, OverflowError, OSError, RecursionError) as error:
        print(f"probabilistic reference failed closed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
