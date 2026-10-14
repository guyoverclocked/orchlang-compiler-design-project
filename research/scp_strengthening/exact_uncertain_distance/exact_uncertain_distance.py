#!/usr/bin/env python3
"""Exact finite-horizon trace TV for rectangular rational row polytopes.

The input explicitly gives finite generator lists for each scenario/history
row.  A row may be any point in the convex hull of its list.  Missing live
rows denote the full simplex over the declared alphabet.  This module checks
only the finite mathematical contract; it does not validate an external
system's conditional distributions against that contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


SCHEMA = "orchlang.exact-uncertain-distance/v1"
CERTIFICATE_SCHEMA = "orchlang.exact-uncertain-distance-certificate/v1"
STOP = "__STOP__"

MAX_INPUT_BYTES = 4_000_000
# Leave room for the CLI's trailing newline so every emitted certificate can
# be read back through the same bounded JSON parser.
MAX_OUTPUT_BYTES = MAX_INPUT_BYTES - 1
MAX_JSON_ITEMS = 200_000
MAX_JSON_DEPTH = 64
MAX_HORIZON = 10
MAX_ALPHABET = 8
MAX_SYMBOL_BYTES = 128
MAX_ROWS = 20_000
MAX_GENERATORS_PER_ROW = 32
MAX_TOTAL_GENERATORS = 100_000
MAX_RATIONAL_DIGITS = 48
MAX_INPUT_INTEGER_BITS = 192
MAX_ARITHMETIC_BITS = 4096
# Products of admissible input probabilities can exceed the per-row digit
# limit. Certificates may use the full bounded intermediate arithmetic domain.
MAX_CERTIFICATE_RATIONAL_DIGITS = (MAX_ARITHMETIC_BITS * 30103 + 99999) // 100000
MAX_DP_STATES = 30_000
MAX_STOP_STATES = 30_000
MAX_EVALUATIONS = 2_000_000

_RATIONAL = re.compile(r"(?:0|[1-9][0-9]*)(?:/(?:[1-9][0-9]*))?\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SCENARIOS = ("left", "right")


class ContractError(ValueError):
    """Malformed or semantically inconsistent exact-distance input."""


class UnverifiableContract(ValueError):
    """A valid request exceeded a deterministic resource bound."""


@dataclass(frozen=True)
class Contract:
    alphabet: tuple[str, ...]
    horizon: int
    require_stop_by_horizon: bool
    rows: dict[tuple[str, tuple[str, ...]], tuple[tuple[Fraction, ...], ...]]
    digest: str


@dataclass(frozen=True)
class State:
    history: tuple[str, ...]
    left_mass: Fraction
    right_mass: Fraction


@dataclass(frozen=True)
class StateResult:
    overlap: Fraction
    selected_pair: tuple[int, int] | None


class _Budget:
    def __init__(self, limit: int | None = None) -> None:
        self.limit = MAX_EVALUATIONS if limit is None else limit
        self.used = 0

    def spend(self, amount: int = 1) -> None:
        self.used += amount
        if self.used > self.limit:
            raise UnverifiableContract(
                f"exact row-pair work exceeds the {self.limit}-evaluation limit"
            )


def _check_fraction(value: Fraction, where: str) -> Fraction:
    if value.numerator.bit_length() > MAX_ARITHMETIC_BITS:
        raise UnverifiableContract(f"{where} numerator exceeds the arithmetic bit limit")
    if value.denominator.bit_length() > MAX_ARITHMETIC_BITS:
        raise UnverifiableContract(f"{where} denominator exceeds the arithmetic bit limit")
    return value


def _add(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _check_fraction(left + right, where)


def _mul(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _check_fraction(left * right, where)


def _fraction(value: Any, where: str, *, certificate: bool = False) -> Fraction:
    if type(value) is int:
        if certificate:
            raise ContractError(f"{where} must be a rational string in the certificate")
        if value < 0:
            raise ContractError(f"{where} must be nonnegative")
        if value.bit_length() > MAX_INPUT_INTEGER_BITS:
            raise ContractError(f"{where} exceeds the input integer bit limit")
        return Fraction(value)
    digits = MAX_CERTIFICATE_RATIONAL_DIGITS if certificate else MAX_RATIONAL_DIGITS
    if type(value) is not str or not value or len(value) > 2 * digits + 1:
        raise ContractError(f"{where} must be a bounded nonnegative rational")
    if not _RATIONAL.fullmatch(value):
        raise ContractError(f"{where} must use integer or numerator/denominator syntax")
    parts = value.split("/")
    if any(len(part) > digits for part in parts):
        raise ContractError(f"{where} exceeds the {digits}-digit rational limit")
    numerator = int(parts[0])
    denominator = int(parts[1]) if len(parts) == 2 else 1
    result = Fraction(numerator, denominator)
    return _check_fraction(result, where) if certificate else result


def _rational_text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _validate_json_tree(value: Any, where: str) -> None:
    """Bound direct-API input and reject floats, exotic objects and surrogates."""
    pending: list[tuple[Any, bool, int]] = [(value, False, 1)]
    active: set[int] = set()
    count = 0
    estimated = 0
    while pending:
        item, exiting, depth = pending.pop()
        if exiting:
            active.remove(id(item))
            continue
        if depth > MAX_JSON_DEPTH:
            raise ContractError(f"{where} exceeds the {MAX_JSON_DEPTH}-level nesting limit")
        count += 1
        if count > MAX_JSON_ITEMS:
            raise ContractError(f"{where} exceeds the {MAX_JSON_ITEMS}-item limit")
        if item is None:
            estimated += 4
        elif type(item) is bool:
            estimated += 5
        elif type(item) is int:
            if item.bit_length() > MAX_INPUT_INTEGER_BITS:
                raise ContractError(f"{where} contains an oversized integer")
            estimated += max(1, (item.bit_length() * 30103) // 100000 + 1) + 1
        elif type(item) is str:
            try:
                encoded = item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ContractError(f"{where} contains non-scalar Unicode") from exc
            estimated += len(encoded) + 2
        elif type(item) is list:
            if id(item) in active:
                raise ContractError(f"{where} contains a cyclic object graph")
            active.add(id(item))
            estimated += 2
            pending.append((item, True, depth))
            pending.extend((child, False, depth + 1) for child in reversed(item))
        elif type(item) is dict:
            if id(item) in active:
                raise ContractError(f"{where} contains a cyclic object graph")
            active.add(id(item))
            estimated += 2
            children = []
            for key, child in item.items():
                if type(key) is not str:
                    raise ContractError(f"{where} contains a non-string object key")
                try:
                    estimated += len(key.encode("utf-8", errors="strict")) + 3
                except UnicodeEncodeError as exc:
                    raise ContractError(f"{where} contains a non-scalar object key") from exc
                children.append(child)
            pending.append((item, True, depth))
            pending.extend((child, False, depth + 1) for child in reversed(children))
        else:
            raise ContractError(f"{where} contains unsupported value type {type(item).__name__}")
        if estimated > MAX_INPUT_BYTES:
            raise ContractError(f"{where} exceeds the {MAX_INPUT_BYTES}-byte data limit")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _parse_json_int(text: str) -> int:
    if len(text.lstrip("-")) > MAX_RATIONAL_DIGITS:
        raise ContractError("JSON integer exceeds the input digit limit")
    return int(text)


def _reject_json_float(_text: str) -> Any:
    raise ContractError("JSON floating-point and exponent values are not accepted")


def _reject_json_constant(text: str) -> Any:
    raise ContractError(f"non-JSON numeric constant {text!r} is not accepted")


def parse_json_bytes(data: bytes, where: str = "JSON input") -> Any:
    if type(data) is not bytes:
        raise ContractError(f"{where} must be bytes")
    if len(data) > MAX_INPUT_BYTES:
        raise ContractError(f"{where} exceeds the {MAX_INPUT_BYTES}-byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{where} is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_json_int,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ContractError(f"cannot parse {where}: {exc}") from exc
    _validate_json_tree(value, where)
    return value


def _canonical_json(raw: Any) -> bytes:
    _validate_json_tree(raw, "contract")
    try:
        text = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        data = text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ContractError(f"cannot canonicalize contract: {exc}") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise ContractError(f"canonical contract exceeds {MAX_INPUT_BYTES} bytes")
    return data


def _expect_exact_fields(value: Any, fields: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{where} must be an object")
    if set(value) != fields:
        raise ContractError(f"{where} fields must be exactly {sorted(fields)}")
    return value


def _parse_distribution(raw: Any, alphabet: tuple[str, ...], where: str) -> tuple[Fraction, ...]:
    if type(raw) is not dict or set(raw) != set(alphabet):
        raise ContractError(f"{where} must assign every alphabet symbol exactly once")
    result = tuple(_fraction(raw[symbol], f"{where}[{symbol!r}]") for symbol in alphabet)
    total = Fraction(0)
    for probability in result:
        total = _add(total, probability, f"{where} probability sum")
    if total != 1:
        raise ContractError(f"{where} probabilities must sum exactly to 1")
    return result


def parse_contract(raw: Any) -> Contract:
    canonical = _canonical_json(raw)
    value = _expect_exact_fields(
        raw,
        {"schema", "alphabet", "horizon", "require_stop_by_horizon", "rows"},
        "contract",
    )
    if type(value["schema"]) is not str or value["schema"] != SCHEMA:
        raise ContractError("unsupported exact-distance schema")
    horizon = value["horizon"]
    if type(horizon) is not int or not 1 <= horizon <= MAX_HORIZON:
        raise ContractError(f"horizon must be an integer from 1 through {MAX_HORIZON}")
    require_stop = value["require_stop_by_horizon"]
    if type(require_stop) is not bool:
        raise ContractError("require_stop_by_horizon must be a JSON Boolean")
    alphabet_raw = value["alphabet"]
    if type(alphabet_raw) is not list or not alphabet_raw or len(alphabet_raw) > MAX_ALPHABET:
        raise ContractError(f"alphabet must contain 1 through {MAX_ALPHABET} symbols")
    if any(type(symbol) is not str or not symbol for symbol in alphabet_raw):
        raise ContractError("every alphabet symbol must be a nonempty string")
    for symbol in alphabet_raw:
        try:
            size = len(symbol.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise ContractError("alphabet contains non-scalar Unicode") from exc
        if size > MAX_SYMBOL_BYTES:
            raise ContractError(f"alphabet symbols may contain at most {MAX_SYMBOL_BYTES} UTF-8 bytes")
    if len(set(alphabet_raw)) != len(alphabet_raw):
        raise ContractError("alphabet symbols must be unique")
    alphabet = tuple(alphabet_raw)
    if STOP not in alphabet:
        raise ContractError(f"alphabet must include reserved terminal symbol {STOP!r}")

    rows_raw = value["rows"]
    if type(rows_raw) is not list or len(rows_raw) > MAX_ROWS:
        raise ContractError(f"rows must be an array of at most {MAX_ROWS} entries")
    rows: dict[tuple[str, tuple[str, ...]], tuple[tuple[Fraction, ...], ...]] = {}
    total_generators = 0
    for index, row_raw in enumerate(rows_raw):
        row = _expect_exact_fields(row_raw, {"scenario", "history", "generators"}, f"rows[{index}]")
        scenario = row["scenario"]
        if type(scenario) is not str or scenario not in _SCENARIOS:
            raise ContractError(f"rows[{index}].scenario must be 'left' or 'right'")
        history_raw = row["history"]
        if type(history_raw) is not list:
            raise ContractError(f"rows[{index}].history must be an array")
        if len(history_raw) >= horizon:
            raise ContractError(f"rows[{index}].history must be shorter than the horizon")
        if any(type(symbol) is not str or symbol not in alphabet for symbol in history_raw):
            raise ContractError(f"rows[{index}].history contains a symbol outside the alphabet")
        if STOP in history_raw:
            raise ContractError(f"rows[{index}].history cannot continue after {STOP!r}")
        history = tuple(history_raw)
        key = (scenario, history)
        if key in rows:
            raise ContractError(f"duplicate row for {scenario} at history {history!r}")
        generators_raw = row["generators"]
        if type(generators_raw) is not list or not generators_raw:
            raise ContractError(f"rows[{index}].generators must be a nonempty array")
        if len(generators_raw) > MAX_GENERATORS_PER_ROW:
            raise ContractError(
                f"rows[{index}] exceeds the {MAX_GENERATORS_PER_ROW}-generator limit"
            )
        generators = tuple(
            _parse_distribution(gen, alphabet, f"rows[{index}].generators[{gen_index}]")
            for gen_index, gen in enumerate(generators_raw)
        )
        if len(set(generators)) != len(generators):
            raise ContractError(f"rows[{index}].generators contains a duplicate distribution")
        total_generators += len(generators)
        if total_generators > MAX_TOTAL_GENERATORS:
            raise ContractError(f"contract exceeds the {MAX_TOTAL_GENERATORS}-generator limit")
        rows[key] = generators

    contract = Contract(alphabet, horizon, require_stop, rows, hashlib.sha256(canonical).hexdigest())
    if require_stop:
        _check_stop_by_horizon(contract)
    return contract


def _full_simplex(alphabet: tuple[str, ...]) -> tuple[tuple[Fraction, ...], ...]:
    rows = []
    for selected in range(len(alphabet)):
        row = [Fraction(0) for _ in alphabet]
        row[selected] = Fraction(1)
        rows.append(tuple(row))
    return tuple(rows)


def _row(contract: Contract, scenario: str, history: tuple[str, ...]) -> tuple[tuple[Fraction, ...], ...]:
    return contract.rows.get((scenario, history), _full_simplex(contract.alphabet))


def _check_stop_by_horizon(contract: Contract) -> None:
    stop_index = contract.alphabet.index(STOP)
    visited = 0

    def visit(scenario: str, history: tuple[str, ...]) -> None:
        nonlocal visited
        if history and history[-1] == STOP:
            return
        if len(history) >= contract.horizon:
            raise ContractError(
                f"require_stop_by_horizon is false: {scenario} permits a non-STOP trace of length {contract.horizon}"
            )
        visited += 1
        if visited > MAX_STOP_STATES:
            raise UnverifiableContract(f"stop-completeness traversal exceeds {MAX_STOP_STATES} nodes")
        possible = set()
        for generator in _row(contract, scenario, history):
            possible.update(index for index, probability in enumerate(generator) if probability > 0)
        if not possible:
            raise ContractError("a probability row has empty support")
        for symbol_index in sorted(possible):
            if symbol_index == stop_index:
                continue
            visit(scenario, history + (contract.alphabet[symbol_index],))

    visit("left", ())
    visit("right", ())


def _state_sort_key(key: tuple[tuple[str, ...], Fraction, Fraction]) -> tuple[Any, ...]:
    history, left_mass, right_mass = key
    return (
        len(history),
        history,
        left_mass.numerator,
        left_mass.denominator,
        right_mass.numerator,
        right_mass.denominator,
    )


def _state_record(state: State, result: StateResult) -> dict[str, Any]:
    selected = None if result.selected_pair is None else list(result.selected_pair)
    return {
        "history": list(state.history),
        "left_mass": _rational_text(state.left_mass),
        "right_mass": _rational_text(state.right_mass),
        "overlap": _rational_text(result.overlap),
        "selected_pair": selected,
    }


def _certificate_bytes(certificate: dict[str, Any]) -> bytes:
    try:
        _validate_json_tree(certificate, "certificate")
    except ContractError as exc:
        raise UnverifiableContract(str(exc)) from exc
    try:
        text = json.dumps(certificate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        data = text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise UnverifiableContract(f"cannot serialize certificate: {exc}") from exc
    if len(data) > MAX_OUTPUT_BYTES:
        raise UnverifiableContract(f"certificate exceeds the {MAX_OUTPUT_BYTES}-byte output limit")
    return data


def certify(raw: Any) -> dict[str, Any]:
    contract = parse_contract(raw)
    stop_index = contract.alphabet.index(STOP)
    budget = _Budget()
    memo: dict[tuple[tuple[str, ...], Fraction, Fraction], StateResult] = {}
    reserved_states = 0

    def solve(history: tuple[str, ...], left_mass: Fraction, right_mass: Fraction) -> Fraction:
        nonlocal reserved_states
        if left_mass == 0 or right_mass == 0:
            return Fraction(0)
        key = (history, left_mass, right_mass)
        known = memo.get(key)
        if known is not None:
            return known.overlap
        # Reserve before descending: unfinished ancestors occupy states too.
        if reserved_states >= MAX_DP_STATES:
            raise UnverifiableContract(f"overlap DP exceeds the {MAX_DP_STATES}-state limit")
        reserved_states += 1
        if len(history) == contract.horizon:
            result = StateResult(min(left_mass, right_mass), None)
            memo[key] = result
            return result.overlap

        left_generators = _row(contract, "left", history)
        right_generators = _row(contract, "right", history)
        best_value: Fraction | None = None
        best_pair: tuple[int, int] | None = None
        for left_index, left_row in enumerate(left_generators):
            for right_index, right_row in enumerate(right_generators):
                budget.spend(len(contract.alphabet))
                total = Fraction(0)
                for symbol_index, symbol in enumerate(contract.alphabet):
                    left_child = _mul(left_mass, left_row[symbol_index], "left child mass")
                    right_child = _mul(right_mass, right_row[symbol_index], "right child mass")
                    if left_child == 0 or right_child == 0:
                        continue
                    if symbol_index == stop_index:
                        child_overlap = min(left_child, right_child)
                    else:
                        child_overlap = solve(history + (symbol,), left_child, right_child)
                    total = _add(total, child_overlap, "local overlap sum")
                if best_value is None or total < best_value:
                    best_value = total
                    best_pair = (left_index, right_index)
        if best_value is None or best_pair is None:
            raise ContractError("a live row has no generator pair")
        memo[key] = StateResult(best_value, best_pair)
        return best_value

    overlap = solve((), Fraction(1), Fraction(1))
    worst_tv = _check_fraction(Fraction(1) - overlap, "worst-case TV")
    certificate = {
        "schema": CERTIFICATE_SCHEMA,
        "contract_sha256": contract.digest,
        "overlap": _rational_text(overlap),
        "worst_case_tv": _rational_text(worst_tv),
        "states": [
            _state_record(State(history, left_mass, right_mass), result)
            for (history, left_mass, right_mass), result in sorted(memo.items(), key=lambda item: _state_sort_key(item[0]))
        ],
    }
    _certificate_bytes(certificate)
    return certificate


def _parse_certificate(raw: Any, contract: Contract) -> tuple[Fraction, Fraction, dict[tuple[tuple[str, ...], Fraction, Fraction], StateResult]]:
    # The object API obeys the same tree/serialized-size caps as the CLI. This
    # also ensures producers never emit a table the bounded reader cannot load.
    _certificate_bytes(raw)
    value = _expect_exact_fields(
        raw,
        {"schema", "contract_sha256", "overlap", "worst_case_tv", "states"},
        "certificate",
    )
    if type(value["schema"]) is not str or value["schema"] != CERTIFICATE_SCHEMA:
        raise ContractError("unsupported certificate schema")
    digest = value["contract_sha256"]
    if type(digest) is not str or not _DIGEST.fullmatch(digest):
        raise ContractError("certificate contract_sha256 must be a lowercase SHA-256 hex string")
    if digest != contract.digest:
        raise ContractError("certificate is bound to a different canonical contract")
    overlap = _fraction(value["overlap"], "certificate.overlap", certificate=True)
    worst_tv = _fraction(value["worst_case_tv"], "certificate.worst_case_tv", certificate=True)
    if overlap > 1 or worst_tv > 1:
        raise ContractError("certificate overlap and TV values must be at most one")
    states_raw = value["states"]
    if type(states_raw) is not list or len(states_raw) > MAX_DP_STATES:
        raise ContractError(f"certificate states must be an array of at most {MAX_DP_STATES} entries")
    states: dict[tuple[tuple[str, ...], Fraction, Fraction], StateResult] = {}
    for index, state_raw in enumerate(states_raw):
        state = _expect_exact_fields(
            state_raw,
            {"history", "left_mass", "right_mass", "overlap", "selected_pair"},
            f"certificate.states[{index}]",
        )
        history_raw = state["history"]
        if type(history_raw) is not list or len(history_raw) > contract.horizon:
            raise ContractError(f"certificate.states[{index}].history has invalid shape")
        if any(type(symbol) is not str or symbol not in contract.alphabet for symbol in history_raw):
            raise ContractError(f"certificate.states[{index}].history uses an unknown symbol")
        if STOP in history_raw:
            raise ContractError("certificate must not contain post-STOP states")
        history = tuple(history_raw)
        left_mass = _fraction(state["left_mass"], f"certificate.states[{index}].left_mass", certificate=True)
        right_mass = _fraction(state["right_mass"], f"certificate.states[{index}].right_mass", certificate=True)
        if left_mass == 0 or right_mass == 0:
            raise ContractError("certificate states must have positive prefix masses")
        state_overlap = _fraction(state["overlap"], f"certificate.states[{index}].overlap", certificate=True)
        if state_overlap > min(left_mass, right_mass):
            raise ContractError("state overlap exceeds its prefix mass")
        selected_raw = state["selected_pair"]
        selected: tuple[int, int] | None
        if selected_raw is None:
            selected = None
        else:
            if type(selected_raw) is not list or len(selected_raw) != 2 or any(type(i) is not int or i < 0 for i in selected_raw):
                raise ContractError("selected_pair must be null or two nonnegative integer indexes")
            selected = (selected_raw[0], selected_raw[1])
        key = (history, left_mass, right_mass)
        if key in states:
            raise ContractError("certificate repeats a DP state")
        states[key] = StateResult(state_overlap, selected)
    return overlap, worst_tv, states


def verify(raw_contract: Any, raw_certificate: Any) -> dict[str, Any]:
    """Independently replay all table states, row-pair minima and the root value."""
    contract = parse_contract(raw_contract)
    declared_overlap, declared_tv, states = _parse_certificate(raw_certificate, contract)
    root = ((), Fraction(1), Fraction(1))
    if root not in states:
        raise ContractError("certificate is missing the root DP state")

    # Derive the exact state closure expected from *all* generator pairs.
    # This rejects omitted subproblems as well as arbitrary extra claims.
    pending = [root]
    expected: set[tuple[tuple[str, ...], Fraction, Fraction]] = set()
    stop_index = contract.alphabet.index(STOP)
    closure_budget = _Budget()
    while pending:
        key = pending.pop()
        if key in expected:
            continue
        if len(expected) >= MAX_DP_STATES:
            raise UnverifiableContract(f"certificate closure exceeds the {MAX_DP_STATES}-state limit")
        expected.add(key)
        history, left_mass, right_mass = key
        if len(history) == contract.horizon:
            continue
        left_generators = _row(contract, "left", history)
        right_generators = _row(contract, "right", history)
        for left_row in left_generators:
            for right_row in right_generators:
                closure_budget.spend(len(contract.alphabet))
                for symbol_index, symbol in enumerate(contract.alphabet):
                    left_child = _mul(left_mass, left_row[symbol_index], "left child mass")
                    right_child = _mul(right_mass, right_row[symbol_index], "right child mass")
                    if left_child > 0 and right_child > 0 and symbol_index != stop_index:
                        pending.append((history + (symbol,), left_child, right_child))
    if set(states) != expected:
        missing = len(expected - set(states))
        extra = len(set(states) - expected)
        raise ContractError(f"certificate DP state closure differs (missing={missing}, extra={extra})")

    # Recompute local Bellman values bottom-up from the state table.
    computed: dict[tuple[tuple[str, ...], Fraction, Fraction], Fraction] = {}
    replay_budget = _Budget()
    for key in sorted(expected, key=lambda item: _state_sort_key(item), reverse=True):
        history, left_mass, right_mass = key
        record = states[key]
        if len(history) == contract.horizon:
            expected_value = min(left_mass, right_mass)
            expected_pair = None
        else:
            left_generators = _row(contract, "left", history)
            right_generators = _row(contract, "right", history)
            best_value: Fraction | None = None
            best_pair: tuple[int, int] | None = None
            for left_index, left_row in enumerate(left_generators):
                for right_index, right_row in enumerate(right_generators):
                    replay_budget.spend(len(contract.alphabet))
                    total = Fraction(0)
                    for symbol_index, symbol in enumerate(contract.alphabet):
                        left_child = _mul(left_mass, left_row[symbol_index], "left child mass")
                        right_child = _mul(right_mass, right_row[symbol_index], "right child mass")
                        if left_child == 0 or right_child == 0:
                            continue
                        if symbol_index == stop_index:
                            child_value = min(left_child, right_child)
                        else:
                            child_key = (history + (symbol,), left_child, right_child)
                            try:
                                child_value = computed[child_key]
                            except KeyError as exc:
                                raise ContractError("certificate omits a required child state") from exc
                        total = _add(total, child_value, "local overlap sum")
                    if best_value is None or total < best_value:
                        best_value = total
                        best_pair = (left_index, right_index)
            if best_value is None or best_pair is None:
                raise ContractError("a live row has no generator pair")
            expected_value = best_value
            expected_pair = best_pair
        if record.overlap != expected_value or record.selected_pair != expected_pair:
            raise ContractError(f"certificate has an incorrect Bellman value at history {history!r}")
        computed[key] = expected_value

    root_overlap = computed[root]
    if declared_overlap != root_overlap:
        raise ContractError("certificate root overlap does not match the verified DP table")
    expected_tv = _check_fraction(Fraction(1) - root_overlap, "verified worst-case TV")
    if declared_tv != expected_tv:
        raise ContractError("certificate worst_case_tv is not one minus the root overlap")
    return {
        "verified": True,
        "overlap": _rational_text(root_overlap),
        "worst_case_tv": _rational_text(expected_tv),
        "states": len(expected),
    }


def _read_json_file(path: str) -> Any:
    file_path = Path(path)
    try:
        with file_path.open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise ContractError(f"{path} exceeds the {MAX_INPUT_BYTES}-byte input limit")
    return parse_json_bytes(data, path)


def _write_atomic(path: str, data: bytes) -> None:
    if len(data) > MAX_OUTPUT_BYTES:
        raise UnverifiableContract(f"output exceeds the {MAX_OUTPUT_BYTES}-byte limit")
    if path == "-":
        sys.stdout.buffer.write(data + b"\n")
        return
    destination = Path(path)
    parent = destination.parent
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    except OSError as exc:
        raise UnverifiableContract(f"cannot atomically write {destination}: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    certify_parser = subparsers.add_parser("certify", help="produce an exact overlap/TV certificate")
    certify_parser.add_argument("contract")
    certify_parser.add_argument("--out", required=True, help="certificate destination or '-' for stdout")
    verify_parser = subparsers.add_parser("verify", help="replay a certificate against its contract")
    verify_parser.add_argument("contract")
    verify_parser.add_argument("certificate")
    args = parser.parse_args(argv)
    try:
        raw_contract = _read_json_file(args.contract)
        if args.command == "certify":
            certificate = certify(raw_contract)
            _write_atomic(args.out, _certificate_bytes(certificate))
            return 0
        raw_certificate = _read_json_file(args.certificate)
        result = verify(raw_contract, raw_certificate)
        _write_atomic("-", json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return 0
    except (ContractError, UnverifiableContract) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
