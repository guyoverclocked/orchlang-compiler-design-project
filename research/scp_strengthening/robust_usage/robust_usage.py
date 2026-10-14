#!/usr/bin/env python3
"""Exact-rational checker for finite, history-indexed robust usage contracts.

The checker certifies a finite-horizon TV upper bound from row contracts. It
does not establish that an external/provider kernel satisfies those contracts.
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


SCHEMA = "orchlang.robust-usage/v1"
CERTIFICATE_SCHEMA = "orchlang.robust-usage-certificate/v1"
STOP = "__STOP__"

# These are implementation limits, not mathematical assumptions. They make
# every accepted invocation finite and prevent a small textual input from
# requesting an enormous exact-integer or horizon computation.
MAX_INPUT_BYTES = 16_000_000
MAX_OUTPUT_BYTES = 16_000_000
MAX_JSON_ITEMS = 1_000_000
MAX_JSON_DEPTH = 64
MAX_HORIZON = 10_000
MAX_ALPHABET = 128
MAX_SYMBOL_BYTES = 256
MAX_ROWS = 50_000
MAX_NODES = 50_000
MAX_RATIONAL_DIGITS = 128
MAX_INTEGER_DIGITS = 160
MAX_NUMERIC_BITS = 512
MAX_ARITHMETIC_BITS = 8_192
MAX_REPLAY_ERRORS = 64

_RATIONAL_RE = re.compile(r"(?:[0-9]+)(?:/[0-9]+)?\Z")


class ContractError(ValueError):
    """The input is malformed or violates the declared trace encoding."""


class UnverifiableContract(ValueError):
    """The requested complete-trace property is not established by the rows."""


@dataclass(frozen=True)
class Row:
    center: dict[str, Fraction]
    radius: Fraction


@dataclass(frozen=True)
class Contract:
    horizon: int
    alphabet: tuple[str, ...]
    rows: dict[tuple[str, ...], tuple[Row | None, Row | None]]
    require_stop_by_horizon: bool
    digest: str


@dataclass(frozen=True)
class _Local:
    history: tuple[str, ...]
    center_tv: Fraction | None
    left_radius: Fraction | None
    right_radius: Fraction | None
    bound: Fraction
    shared: tuple[str, ...]
    missing: bool


def _validate_json_tree(value: Any, where: str = "JSON input") -> None:
    """Validate a bounded JSON-shaped tree, including scalar Unicode.

    The iterative walk avoids adding another recursion failure mode for direct
    API callers. JSON text is separately size-limited before decoding.
    """
    pending: list[tuple[Any, bool, int]] = [(value, False, 1)]
    active_containers: set[int] = set()
    item_count = 0
    estimated_size = 0

    def account(amount: int) -> None:
        nonlocal estimated_size
        estimated_size += amount
        if estimated_size > MAX_INPUT_BYTES:
            raise ContractError(f"{where} exceeds the {MAX_INPUT_BYTES}-byte data limit")

    while pending:
        item, exiting, depth = pending.pop()
        if exiting:
            active_containers.remove(id(item))
            continue
        if depth > MAX_JSON_DEPTH:
            raise ContractError(f"{where} exceeds the {MAX_JSON_DEPTH}-level nesting limit")
        item_count += 1
        if item_count > MAX_JSON_ITEMS:
            raise ContractError(f"{where} exceeds the {MAX_JSON_ITEMS}-item limit")

        if item is None:
            account(4)
        elif type(item) is bool:
            account(5 if item else 4)
        elif type(item) is int:
            if item.bit_length() > MAX_NUMERIC_BITS:
                raise ContractError(f"{where} contains an integer exceeding the numeric bit limit")
            digits = max(1, (item.bit_length() * 30103) // 100000 + 1)
            account(digits + 1)
        elif type(item) is str:
            try:
                encoded = item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ContractError(f"{where} contains a non-scalar Unicode string") from exc
            # json.dumps may expand each control byte to a six-character escape.
            control_count = sum(1 for char in item if ord(char) < 0x20)
            account(len(encoded) + 2 + 5 * control_count)
        elif type(item) is list:
            identity = id(item)
            if identity in active_containers:
                raise ContractError(f"{where} contains a cyclic object graph")
            active_containers.add(identity)
            account(2)
            pending.append((item, True, depth))
            pending.extend((child, False, depth + 1) for child in reversed(item))
        elif type(item) is dict:
            identity = id(item)
            if identity in active_containers:
                raise ContractError(f"{where} contains a cyclic object graph")
            active_containers.add(identity)
            account(2)
            children = []
            for key, child in item.items():
                if type(key) is not str:
                    raise ContractError(f"{where} contains a non-string object key")
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise ContractError(f"{where} contains a non-scalar Unicode object key") from exc
                control_count = sum(1 for char in key if ord(char) < 0x20)
                account(len(encoded_key) + 3 + 5 * control_count)
                children.append(child)
            pending.append((item, True, depth))
            pending.extend((child, False, depth + 1) for child in reversed(children))
        else:
            raise ContractError(f"{where} contains a non-JSON value of type {type(item).__name__}")


def _canonical_json(value: Any, where: str) -> bytes:
    _validate_json_tree(value, where)
    try:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        encoded = rendered.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ContractError(f"cannot canonicalize {where}: {exc}") from exc
    if len(encoded) > MAX_INPUT_BYTES:
        raise ContractError(f"{where} exceeds the {MAX_INPUT_BYTES}-byte canonical data limit")
    return encoded


def _fraction(value: Any, where: str) -> Fraction:
    if type(value) is int:
        if value.bit_length() > MAX_NUMERIC_BITS:
            raise ContractError(f"{where} exceeds the numeric bit limit")
        if value < 0:
            raise ContractError(f"{where} must be nonnegative")
        return Fraction(value)
    if type(value) is not str or len(value) > 2 * MAX_RATIONAL_DIGITS + 1:
        raise ContractError(f"{where} must be a bounded nonnegative integer or numerator/denominator string")
    if not _RATIONAL_RE.fullmatch(value):
        raise ContractError(f"{where} must use integer or numerator/denominator syntax")
    parts = value.split("/")
    if any(len(part) > MAX_RATIONAL_DIGITS for part in parts):
        raise ContractError(f"{where} exceeds the {MAX_RATIONAL_DIGITS}-digit rational limit")
    numerator = int(parts[0])
    denominator = int(parts[1]) if len(parts) == 2 else 1
    if denominator == 0:
        raise ContractError(f"{where} has a zero denominator")
    return Fraction(numerator, denominator)


def _check_arithmetic_size(value: Fraction, where: str) -> Fraction:
    if value.numerator.bit_length() > MAX_ARITHMETIC_BITS or value.denominator.bit_length() > MAX_ARITHMETIC_BITS:
        raise UnverifiableContract(
            f"{where} exceeds the {MAX_ARITHMETIC_BITS}-bit exact-arithmetic limit"
        )
    return value


def _add(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _check_arithmetic_size(left + right, where)


def _sub(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _check_arithmetic_size(left - right, where)


def _mul(left: Fraction, right: Fraction, where: str) -> Fraction:
    return _check_arithmetic_size(left * right, where)


def _parse_row(raw: Any, alphabet: tuple[str, ...], where: str) -> Row:
    if type(raw) is not dict:
        raise ContractError(f"{where} must be an object")
    if set(raw) != {"center", "radius"}:
        raise ContractError(f"{where} must contain exactly center and radius")
    center_raw = raw["center"]
    if type(center_raw) is not dict or set(center_raw) != set(alphabet):
        raise ContractError(f"{where}.center must specify every alphabet symbol exactly once")
    center = {
        symbol: _fraction(center_raw[symbol], f"{where}.center[{symbol!r}]")
        for symbol in alphabet
    }
    if any(probability < 0 for probability in center.values()):
        raise ContractError(f"{where}.center has a negative probability")
    center_total = Fraction(0)
    for probability in center.values():
        center_total = _add(center_total, probability, f"{where}.center sum")
    if center_total != 1:
        raise ContractError(f"{where}.center probabilities must sum exactly to 1")
    radius = _fraction(raw["radius"], f"{where}.radius")
    if radius > 1:
        raise ContractError(f"{where}.radius must be between 0 and 1")
    return Row(center, radius)


def parse_contract(raw: Any) -> Contract:
    canonical = _canonical_json(raw, "contract")
    if type(raw) is not dict:
        raise ContractError("contract must be a JSON object")
    required = {"schema", "horizon", "alphabet", "require_stop_by_horizon", "rows"}
    if set(raw) != required:
        raise ContractError(f"contract fields must be exactly {sorted(required)}")
    if type(raw["schema"]) is not str or raw["schema"] != SCHEMA:
        raise ContractError("unsupported schema value")
    horizon = raw["horizon"]
    if type(horizon) is not int or horizon < 1 or horizon > MAX_HORIZON:
        raise ContractError(f"horizon must be an integer from 1 through {MAX_HORIZON}")
    alphabet_raw = raw["alphabet"]
    if type(alphabet_raw) is not list or not alphabet_raw:
        raise ContractError("alphabet must be a nonempty array")
    if len(alphabet_raw) > MAX_ALPHABET:
        raise ContractError(f"alphabet exceeds the {MAX_ALPHABET}-symbol limit")
    if any(type(symbol) is not str or not symbol for symbol in alphabet_raw):
        raise ContractError("every alphabet symbol must be a nonempty string")
    if any(len(symbol.encode("utf-8")) > MAX_SYMBOL_BYTES for symbol in alphabet_raw):
        raise ContractError(f"alphabet symbols may contain at most {MAX_SYMBOL_BYTES} UTF-8 bytes")
    if len(set(alphabet_raw)) != len(alphabet_raw):
        raise ContractError("alphabet symbols must be unique")
    alphabet = tuple(alphabet_raw)
    if STOP not in alphabet:
        raise ContractError(f"alphabet must include reserved symbol {STOP!r}")
    require_stop = raw["require_stop_by_horizon"]
    if type(require_stop) is not bool:
        raise ContractError("require_stop_by_horizon must be a boolean")
    rows_raw = raw["rows"]
    if type(rows_raw) is not list:
        raise ContractError("rows must be an array")
    if len(rows_raw) > MAX_ROWS:
        raise ContractError(f"rows exceeds the {MAX_ROWS}-row limit")

    parsed_rows: dict[tuple[str, ...], tuple[Row | None, Row | None]] = {}
    for index, entry in enumerate(rows_raw):
        where = f"rows[{index}]"
        if type(entry) is not dict or set(entry) != {"history", "left", "right"}:
            raise ContractError(f"{where} must contain exactly history, left, and right")
        history_raw = entry["history"]
        if type(history_raw) is not list or len(history_raw) >= horizon:
            raise ContractError(f"{where}.history must be an array shorter than the horizon")
        if any(type(symbol) is not str or symbol not in alphabet for symbol in history_raw):
            raise ContractError(f"{where}.history contains a symbol outside the alphabet")
        history = tuple(history_raw)
        if history in parsed_rows:
            raise ContractError(f"duplicate history row at depth {len(history)}")
        saw_stop = False
        for symbol in history:
            if symbol == STOP:
                saw_stop = True
            elif saw_stop:
                raise ContractError(f"{where}.history has a non-STOP symbol after STOP")
        left = _parse_row(entry["left"], alphabet, f"{where}.left") if entry["left"] is not None else None
        right = _parse_row(entry["right"], alphabet, f"{where}.right") if entry["right"] is not None else None
        for scenario, row_value in (("left", left), ("right", right)):
            if row_value is None:
                continue
            if saw_stop and (row_value.radius != 0 or row_value.center[STOP] != 1):
                raise ContractError(f"{where}.{scenario} must deterministically STOP after STOP")
        parsed_rows[history] = (left, right)

    digest = hashlib.sha256(canonical).hexdigest()
    return Contract(horizon, alphabet, parsed_rows, require_stop, digest)


def _row(contract: Contract, history: tuple[str, ...], side: int) -> Row | None:
    if STOP in history:
        return Row({symbol: Fraction(int(symbol == STOP)) for symbol in contract.alphabet}, Fraction(0))
    pair = contract.rows.get(history)
    return None if pair is None else pair[side]


def _possible_support(row_value: Row, alphabet: tuple[str, ...]) -> tuple[str, ...]:
    # A TV ball of radius rho around q permits positive mass at y iff q(y)+rho>0.
    return tuple(symbol for symbol in alphabet if row_value.center[symbol] + row_value.radius > 0)


def _tv(left: Row, right: Row, alphabet: tuple[str, ...]) -> Fraction:
    l1 = Fraction(0)
    for symbol in alphabet:
        difference = abs(_sub(left.center[symbol], right.center[symbol], "row TV difference"))
        l1 = _add(l1, difference, "row TV sum")
    return _check_arithmetic_size(l1 / 2, "row TV")


def _local_obligation(contract: Contract, history: tuple[str, ...]) -> _Local:
    if STOP in history:
        return _Local(history, Fraction(0), Fraction(0), Fraction(0), Fraction(0), (STOP,), False)
    left = _row(contract, history, 0)
    right = _row(contract, history, 1)
    if left is None or right is None:
        shared = ()
        if left is not None and right is not None:
            shared = tuple(
                symbol for symbol in contract.alphabet
                if symbol in _possible_support(left, contract.alphabet)
                and symbol in _possible_support(right, contract.alphabet)
            )
        return _Local(
            history,
            None,
            None if left is None else left.radius,
            None if right is None else right.radius,
            Fraction(1),
            shared,
            True,
        )
    left_support = set(_possible_support(left, contract.alphabet))
    right_support = set(_possible_support(right, contract.alphabet))
    shared = tuple(
        symbol for symbol in contract.alphabet if symbol in left_support and symbol in right_support
    )
    center_tv = _tv(left, right, contract.alphabet)
    radius_sum = _add(left.radius, right.radius, "local radius sum")
    total_bound = _add(center_tv, radius_sum, "local TV bound")
    return _Local(
        history,
        center_tv,
        left.radius,
        right.radius,
        min(Fraction(1), total_bound),
        shared,
        False,
    )


def _checked_max_nodes(max_nodes: int) -> int:
    if type(max_nodes) is not int or max_nodes < 1 or max_nodes > MAX_NODES:
        raise ContractError(f"max_nodes must be an integer from 1 through {MAX_NODES}")
    return max_nodes


def _check_stop_guarantee(contract: Contract, max_nodes: int) -> int:
    """Iteratively prove all positive-support active traces reach STOP by H."""
    visited = 0
    stack: list[tuple[tuple[str, ...], int]] = [((), 1), ((), 0)]
    while stack:
        history, side = stack.pop()
        if STOP in history:
            continue
        if len(history) >= contract.horizon:
            scenario = "left" if side == 0 else "right"
            raise UnverifiableContract(
                f"scenario {scenario} has a possible trace with no STOP by horizon {contract.horizon}"
            )
        if visited >= max_nodes:
            raise UnverifiableContract(f"stop-coverage check exceeded max_nodes={max_nodes}")
        visited += 1
        row_value = _row(contract, history, side)
        if row_value is None:
            scenario = "left" if side == 0 else "right"
            raise UnverifiableContract(
                f"scenario {scenario} has no row at reachable active history of depth {len(history)}"
            )
        children = [
            (history + (symbol,), side)
            for symbol in _possible_support(row_value, contract.alphabet)
            if symbol != STOP
        ]
        if visited + len(stack) + len(children) > max_nodes:
            raise UnverifiableContract(f"stop-coverage check exceeded max_nodes={max_nodes}")
        stack.extend(reversed(children))
    return visited


def certify(raw: Any, max_nodes: int = MAX_NODES) -> dict[str, Any]:
    """Produce a bounded exact-rational sufficient TV certificate."""
    max_nodes = _checked_max_nodes(max_nodes)
    contract = parse_contract(raw)
    stop_nodes = _check_stop_guarantee(contract, max_nodes) if contract.require_stop_by_horizon else 0

    # Explicit postorder DFS avoids dependence on Python's recursion limit.
    local_nodes: dict[tuple[str, ...], _Local] = {}
    results: dict[tuple[str, ...], Fraction] = {}
    worst_next: dict[tuple[str, ...], str | None] = {}
    entries: list[dict[str, Any]] = []
    estimated_row_bytes = 0
    local_by_depth: dict[int, list[Fraction]] = {}
    stack: list[tuple[str, ...]] = [()]

    def append_entry(entry: dict[str, Any]) -> None:
        nonlocal estimated_row_bytes
        try:
            rendered = json.dumps(entry, indent=2, sort_keys=True, ensure_ascii=False)
            line_count = rendered.count("\n") + 1
            row_bytes = len(rendered.encode("utf-8")) + 4 * line_count + 3
        except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
            raise UnverifiableContract(f"certificate row cannot be rendered: {exc}") from exc
        estimated_row_bytes += row_bytes
        if estimated_row_bytes > MAX_OUTPUT_BYTES:
            raise UnverifiableContract(f"certificate rows exceed the {MAX_OUTPUT_BYTES}-byte output budget")
        entries.append(entry)

    while stack:
        history = stack[-1]
        if history in results:
            stack.pop()
            continue

        local = local_nodes.get(history)
        if local is None:
            if len(local_nodes) >= max_nodes:
                raise UnverifiableContract(f"certificate construction exceeded max_nodes={max_nodes}")
            local = _local_obligation(contract, history)
            local_nodes[history] = local
            local_by_depth.setdefault(len(history), []).append(local.bound)
            if local.bound == 1:
                results[history] = Fraction(0)
                worst_next[history] = None
                append_entry(_certificate_row(local, Fraction(1), Fraction(0), None))
                stack.pop()
                continue
            if not local.shared:
                raise ContractError("local TV bound is below 1 but the robust rows have no shared possible symbol")

        unresolved = None
        for symbol in local.shared:
            child = history + (symbol,)
            if len(child) < contract.horizon and child not in results:
                unresolved = child
                break
        if unresolved is not None:
            stack.append(unresolved)
            continue

        child_options: list[tuple[str, Fraction]] = []
        for symbol in local.shared:
            child = history + (symbol,)
            if len(child) == contract.horizon:
                child_value = Fraction(1)
            else:
                child_value = results[child]
            child_options.append((symbol, child_value))
        best_symbol, continuation = min(
            child_options,
            key=lambda item: (item[1], contract.alphabet.index(item[0])),
        )
        survival = _mul(_sub(Fraction(1), local.bound, "survival factor"), continuation, "survival recurrence")
        results[history] = survival
        worst_next[history] = best_symbol
        append_entry(_certificate_row(local, continuation, survival, best_symbol))
        stack.pop()

    root_survival = results[()]
    worst_suffix: list[str] | None
    if worst_next.get(()) is None:
        worst_suffix = None
    else:
        worst_suffix = []
        history: tuple[str, ...] = ()
        while len(history) < contract.horizon:
            symbol = worst_next.get(history)
            if symbol is None:
                break
            worst_suffix.append(symbol)
            history = history + (symbol,)
    per_level: list[dict[str, str | int]] = []
    level_survival = Fraction(1)
    for depth in sorted(local_by_depth):
        worst_local = max(local_by_depth[depth])
        level_survival = _mul(
            level_survival,
            _sub(Fraction(1), worst_local, "per-level survival factor"),
            "per-level product",
        )
        per_level.append({"depth": depth, "max_local_tv_bound": str(worst_local)})

    entries.sort(key=lambda item: (len(item["history"]), tuple(item["history"])))
    scope = "complete_trace_through_horizon" if contract.require_stop_by_horizon else "horizon_prefix_only"
    certificate = {
        "schema": CERTIFICATE_SCHEMA,
        "contract_sha256": contract.digest,
        "horizon": contract.horizon,
        "scope": scope,
        "tv_upper_bound": str(_sub(Fraction(1), root_survival, "root TV bound")),
        "survival_lower_bound": str(root_survival),
        "worst_shared_prefix": worst_suffix,
        "termination_proved_by_contract": contract.require_stop_by_horizon,
        "stop_coverage_nodes": stop_nodes,
        "shared_prefix_nodes": len(local_nodes),
        "per_level_maxima": per_level,
        "per_level_product_upper_bound": str(_sub(Fraction(1), level_survival, "per-level TV bound")),
        "rows": entries,
    }
    try:
        _validate_json_tree(certificate, "certificate")
        rendered_certificate = json.dumps(
            certificate, indent=2, sort_keys=True, ensure_ascii=False
        ).encode("utf-8", errors="strict") + b"\n"
    except ContractError as exc:
        raise UnverifiableContract(str(exc)) from exc
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise UnverifiableContract(f"certificate cannot be rendered: {exc}") from exc
    if len(rendered_certificate) > MAX_OUTPUT_BYTES:
        raise UnverifiableContract(f"certificate exceeds the {MAX_OUTPUT_BYTES}-byte output budget")
    return certificate


def _certificate_row(
    local: _Local,
    continuation: Fraction,
    survival: Fraction,
    worst_next_symbol: str | None,
) -> dict[str, Any]:
    return {
        "history": list(local.history),
        "center_tv": None if local.center_tv is None else str(local.center_tv),
        "left_radius": None if local.left_radius is None else str(local.left_radius),
        "right_radius": None if local.right_radius is None else str(local.right_radius),
        "local_tv_bound": str(local.bound),
        "shared_possible_symbols": list(local.shared),
        "continuation_survival": str(continuation),
        "survival_lower_bound": str(survival),
        "missing_row": local.missing,
        "worst_next_symbol": worst_next_symbol,
    }


_CERTIFICATE_FIELDS = {
    "schema",
    "contract_sha256",
    "horizon",
    "scope",
    "tv_upper_bound",
    "survival_lower_bound",
    "worst_shared_prefix",
    "termination_proved_by_contract",
    "stop_coverage_nodes",
    "shared_prefix_nodes",
    "per_level_maxima",
    "per_level_product_upper_bound",
    "rows",
}


def _record_error(errors: list[str], message: str) -> None:
    if len(errors) < MAX_REPLAY_ERRORS:
        errors.append(message)


def _same_json_value(actual: Any, expected: Any) -> bool:
    """JSON equality that does not conflate bool/int or other Python types."""
    if type(actual) is not type(expected):
        return False
    if type(actual) is dict:
        return actual.keys() == expected.keys() and all(
            _same_json_value(actual[key], expected[key]) for key in expected
        )
    if type(actual) is list:
        return len(actual) == len(expected) and all(
            _same_json_value(a, b) for a, b in zip(actual, expected)
        )
    return actual == expected


def _verify_stop_obligation(contract: Contract, max_nodes: int) -> tuple[int | None, str | None]:
    """Checker-side traversal for the all-paths STOP claim; no producer call."""
    expanded = 0
    stack: list[tuple[tuple[str, ...], int]] = [((), 0), ((), 1)]
    while stack:
        history, side = stack.pop()
        if STOP in history:
            continue
        if len(history) == contract.horizon:
            return None, f"scenario {'left' if side == 0 else 'right'} has an active trace at the horizon"
        if expanded == max_nodes:
            return None, f"stop proof exceeds max_nodes={max_nodes}"
        row_value = _row(contract, history, side)
        if row_value is None:
            return None, f"stop proof has a missing reachable row at depth {len(history)}"
        expanded += 1
        support = _possible_support(row_value, contract.alphabet)
        next_active = [(history + (symbol,), side) for symbol in support if symbol != STOP]
        if expanded + len(stack) + len(next_active) > max_nodes:
            return None, f"stop proof exceeds max_nodes={max_nodes}"
        stack.extend(next_active)
    return expanded, None


def _expected_obligations(contract: Contract, max_nodes: int) -> dict[tuple[str, ...], _Local]:
    """Derive precisely the shared-prefix closure required by local obligations."""
    obligations: dict[tuple[str, ...], _Local] = {}
    stack: list[tuple[str, ...]] = [()]
    while stack:
        history = stack.pop()
        if len(history) >= contract.horizon or history in obligations:
            continue
        if len(obligations) == max_nodes:
            raise UnverifiableContract(f"certificate obligation check exceeded max_nodes={max_nodes}")
        local = _local_obligation(contract, history)
        obligations[history] = local
        # Continuation rows are required exactly when a positive match remains.
        # local==1 requires no future coupling obligation, even if shared symbols exist.
        if local.bound < 1:
            if not local.shared:
                raise ContractError("local TV bound is below 1 but there is no shared possible symbol")
            for symbol in reversed(local.shared):
                child = history + (symbol,)
                if len(child) < contract.horizon:
                    stack.append(child)
    return obligations


def _verify_row_obligations(
    contract: Contract,
    obligations: dict[tuple[str, ...], _Local],
    certificate_rows: Any,
    errors: list[str],
) -> tuple[dict[tuple[str, ...], Fraction], dict[tuple[str, ...], str | None]]:
    if type(certificate_rows) is not list:
        _record_error(errors, "certificate.rows must be an array")
        return {}, {}
    if len(certificate_rows) > MAX_NODES:
        _record_error(errors, f"certificate.rows exceeds the {MAX_NODES}-row limit")
        return {}, {}

    actual_by_history: dict[tuple[str, ...], dict[str, Any]] = {}
    actual_order: list[tuple[str, ...]] = []
    for index, row_value in enumerate(certificate_rows):
        if type(row_value) is not dict:
            _record_error(errors, f"certificate.rows[{index}] must be an object")
            continue
        history_raw = row_value.get("history")
        if type(history_raw) is not list or any(type(symbol) is not str for symbol in history_raw):
            _record_error(errors, f"certificate.rows[{index}].history must be an array of strings")
            continue
        if len(history_raw) > contract.horizon or any(symbol not in contract.alphabet for symbol in history_raw):
            _record_error(errors, f"certificate.rows[{index}].history is outside the contract trace space")
            continue
        history = tuple(history_raw)
        actual_order.append(history)
        if history in actual_by_history:
            _record_error(errors, f"duplicate certificate row at depth {len(history)}")
        else:
            actual_by_history[history] = row_value

    expected_order = sorted(obligations, key=lambda history: (len(history), history))
    if actual_order != expected_order:
        _record_error(errors, "certificate rows do not provide the exact ordered necessary continuation coverage")
    if set(actual_by_history) != set(obligations):
        _record_error(errors, "certificate row histories do not match the required shared-prefix closure")

    survivals: dict[tuple[str, ...], Fraction] = {}
    worst_next: dict[tuple[str, ...], str | None] = {}
    # The checker discharges local equations from leaves toward the root.
    for history in sorted(obligations, key=lambda item: (len(item), item), reverse=True):
        local = obligations[history]
        expected_next: str | None = None
        if local.bound == 1:
            continuation = Fraction(1)
            survival = Fraction(0)
            expected_next = None
        else:
            choices: list[tuple[str, Fraction]] = []
            for symbol in local.shared:
                child = history + (symbol,)
                if len(child) == contract.horizon:
                    child_survival = Fraction(1)
                elif child in survivals:
                    child_survival = survivals[child]
                else:
                    # A missing child is an obligation-coverage failure. Continue
                    # with the least favorable value so no assurance is inferred.
                    _record_error(errors, f"required continuation row missing below depth {len(history)}")
                    child_survival = Fraction(0)
                choices.append((symbol, child_survival))
            best_symbol, continuation = min(
                choices,
                key=lambda item: (item[1], contract.alphabet.index(item[0])),
            )
            expected_next = best_symbol
            survival = _mul(_sub(Fraction(1), local.bound, "verified survival factor"), continuation, "verified survival recurrence")

        survivals[history] = survival
        worst_next[history] = expected_next
        expected_row = _certificate_row(local, continuation, survival, expected_next)
        actual_row = actual_by_history.get(history)
        if actual_row is None:
            continue
        if set(actual_row) != set(expected_row):
            _record_error(errors, f"certificate row at depth {len(history)} has unexpected or missing fields")
            continue
        for field, expected_value in expected_row.items():
            if not _same_json_value(actual_row[field], expected_value):
                _record_error(errors, f"certificate row field {field!r} is invalid at depth {len(history)}")
                if len(errors) >= MAX_REPLAY_ERRORS:
                    return survivals, worst_next
    return survivals, worst_next


def replay(raw: Any, certificate: Any, max_nodes: int = MAX_NODES) -> tuple[bool, dict[str, Any]]:
    """Check a submitted certificate by local arithmetic and coverage obligations.

    This uses a separate traversal and verifier control flow from ``certify``;
    it shares parsing and exact row-arithmetic primitives and is not a formally
    verified or structurally independent proof checker.
    """
    max_nodes = _checked_max_nodes(max_nodes)
    contract = parse_contract(raw)
    errors: list[str] = []
    try:
        _validate_json_tree(certificate, "certificate")
    except ContractError as exc:
        return False, {"errors": [str(exc)]}
    if type(certificate) is not dict:
        return False, {"errors": ["certificate must be an object"]}
    if set(certificate) != _CERTIFICATE_FIELDS:
        _record_error(errors, "certificate fields are missing or unexpected")

    try:
        obligations = _expected_obligations(contract, max_nodes)
    except UnverifiableContract as exc:
        return False, {"errors": [str(exc)]}

    survivals, worst_next = _verify_row_obligations(
        contract, obligations, certificate.get("rows"), errors
    )
    root_survival = survivals.get(())
    if root_survival is None:
        _record_error(errors, "root local obligation was not discharged")
        root_survival = Fraction(0)

    worst_path: list[str] | None
    if worst_next.get(()) is None:
        worst_path = None
    else:
        worst_path = []
        history: tuple[str, ...] = ()
        while len(history) < contract.horizon:
            symbol = worst_next.get(history)
            if symbol is None:
                break
            worst_path.append(symbol)
            history = history + (symbol,)

    stop_nodes = 0
    if contract.require_stop_by_horizon:
        checked_stop_nodes, stop_error = _verify_stop_obligation(contract, max_nodes)
        if stop_error is not None:
            _record_error(errors, stop_error)
        else:
            stop_nodes = checked_stop_nodes or 0

    level_bounds: dict[int, list[Fraction]] = {}
    for history, local in obligations.items():
        level_bounds.setdefault(len(history), []).append(local.bound)
    level_survival = Fraction(1)
    per_level: list[dict[str, str | int]] = []
    for depth in sorted(level_bounds):
        maximum = max(level_bounds[depth])
        level_survival = _mul(
            level_survival,
            _sub(Fraction(1), maximum, "verified per-level survival factor"),
            "verified per-level product",
        )
        per_level.append({"depth": depth, "max_local_tv_bound": str(maximum)})

    expected_top = {
        "schema": CERTIFICATE_SCHEMA,
        "contract_sha256": contract.digest,
        "horizon": contract.horizon,
        "scope": "complete_trace_through_horizon" if contract.require_stop_by_horizon else "horizon_prefix_only",
        "tv_upper_bound": str(_sub(Fraction(1), root_survival, "verified root TV bound")),
        "survival_lower_bound": str(root_survival),
        "worst_shared_prefix": worst_path,
        "termination_proved_by_contract": contract.require_stop_by_horizon,
        "stop_coverage_nodes": stop_nodes,
        "shared_prefix_nodes": len(obligations),
        "per_level_maxima": per_level,
        "per_level_product_upper_bound": str(_sub(Fraction(1), level_survival, "verified per-level TV bound")),
    }
    for field, expected_value in expected_top.items():
        if field not in certificate:
            continue
        if not _same_json_value(certificate[field], expected_value):
            _record_error(errors, f"certificate field {field!r} is invalid")
            if len(errors) >= MAX_REPLAY_ERRORS:
                break

    if errors:
        return False, {"errors": errors[:MAX_REPLAY_ERRORS]}
    checks = ["exact local row arithmetic", "necessary continuation coverage", "root bound"]
    if contract.require_stop_by_horizon:
        checks.append("stop proof")
    else:
        checks.append("bounded prefix only; termination not checked")
    return True, {"checks": checks}


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key: {key[:80]!r}")
        result[key] = value
    return result


def _parse_json_integer(text: str) -> int:
    digits = text[1:] if text.startswith("-") else text
    if len(digits) > MAX_INTEGER_DIGITS:
        raise ContractError(f"JSON integer exceeds the {MAX_INTEGER_DIGITS}-digit limit")
    value = int(text)
    if value.bit_length() > MAX_NUMERIC_BITS:
        raise ContractError("JSON integer exceeds the numeric bit limit")
    return value


def _reject_json_number(text: str) -> Any:
    raise ContractError(f"JSON floating-point/non-finite number is unsupported: {text[:40]!r}")


def _loads_json_bytes(payload: bytes, where: str = "JSON input") -> Any:
    if len(payload) > MAX_INPUT_BYTES:
        raise ContractError(f"{where} exceeds the {MAX_INPUT_BYTES}-byte file limit")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{where} is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_int=_parse_json_integer,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ContractError(f"invalid or excessively nested JSON in {where}: {exc}") from exc
    _validate_json_tree(value, where)
    return value


def _load_json(path: str) -> Any:
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    return _loads_json_bytes(payload, path)


def _write_json(payload: Any, output: str | None) -> None:
    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        encoded = rendered.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ContractError(f"cannot render JSON output: {exc}") from exc
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ContractError(f"JSON output exceeds the {MAX_OUTPUT_BYTES}-byte limit")
    if output is None or output == "-":
        sys.stdout.write(rendered)
        return

    target = Path(output)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary_name = stream.name
            stream.write(encoded)
        os.replace(temporary_name, target)
    except OSError as exc:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise ContractError(f"cannot write {output}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    certify_parser = subparsers.add_parser("certify", help="compute a rational TV certificate")
    certify_parser.add_argument("contract")
    certify_parser.add_argument("--out", default="-", help="certificate JSON path, or - for stdout")
    certify_parser.add_argument("--max-nodes", type=int, default=MAX_NODES)
    replay_parser = subparsers.add_parser("replay", help="check certificate local obligations")
    replay_parser.add_argument("contract")
    replay_parser.add_argument("certificate")
    replay_parser.add_argument("--max-nodes", type=int, default=MAX_NODES)
    args = parser.parse_args(argv)
    try:
        raw = _load_json(args.contract)
        if args.command == "certify":
            _write_json(certify(raw, max_nodes=args.max_nodes), args.out)
            return 0
        certificate = _load_json(args.certificate)
        matches, report = replay(raw, certificate, max_nodes=args.max_nodes)
        result = {"replay": "ok", **report} if matches else {"replay": "mismatch", **report}
        _write_json(result, None)
        return 0 if matches else 1
    except (ContractError, UnverifiableContract) as exc:
        sys.stderr.write(f"unknown/rejected: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
