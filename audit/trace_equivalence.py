#!/usr/bin/env python3
"""Exact all-finite-horizon ordered usage-trace equivalence for rational models.

The checker specializes weighted-automaton row-span equivalence to the finite
success-only request-graph semantics in :mod:`stochastic_bisimulation`. For a
fixed public store and 2--64 explicit secret assignments, it reconstructs the
reachable finite semantic system. Its observable alphabet is a normalized
resolved model contract together with integer input and output usage.

For each supplied scenario i against scenario 0, the initial row is
``mu = e_i - e_0``. A labeled transition matrix is formed for every observable
call label. The two output columns indicate stopped and still-callable states.
The checker explores a basis for the exact rational span of ``mu A_w`` under
all label matrices. If every reachable basis row annihilates both output
columns, the two finite-word observations agree. If one does not, its word is
an exact finite counterexample. This is the standard weighted-automaton
linear-dependence method applied to this particular observer and semantics;
it is not a new general equivalence algorithm or a provider-level theorem.

The model uses a declared finite rational conditional kernel. Kernel matching
depends on the full modeled request, contract ordinal saturated at 33, and
retained complete-event history. Responses update result registers and history.
Only successful model outcomes are represented. Calls emit labels. At a
finite prefix, STOP and nonterminal mass are reported separately, so a
successful stop differs from a still-live call-cap prefix. No statement is
made about infinite executions, termination probability, retries, errors,
currency, provider behavior, or cumulative billing.

Exact-state closure and all linear algebra are bounded. UNKNOWN means no
partial closure, span, equality claim, or counterexample is returned. The
meters are deterministic work estimates, not RSS or wall-clock guarantees.

API:: ``analyze(graph_document, kernel_document, public_store,
secret_scenarios, ...)``.

CLI:: ``python3 audit/trace_equivalence.py GRAPH KERNEL --public-json '{}'
--scenarios-json '[{"secret":false},{"secret":true}]'``.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stochastic_bisimulation as _closure  # noqa: E402
from orchgraph import InvalidGraph, strict_json, utf8  # noqa: E402
from probabilistic_channels import ChannelError, ChannelLimit  # noqa: E402


FORMAT = "orchlang-exact-trace-equivalence"
VERSION = 2
CLAIM_EQUAL = (
    "exact all-finite-horizon success-only ordered usage-trace laws for every supplied "
    "secret scenario under the declared finite rational kernel"
)
CLAIM_UNEQUAL = "a finite ordered-usage observation distinguishes the supplied scenarios"
SCOPE = {
    "oracle": "declared finite rational conditional kernel; exact modeled request, saturated contract ordinal, and retained complete-event history determine outcomes",
    "observer": "ordered call labels are normalized resolved contract plus integer input and output usage; each finite word is observed with separate stopped and nonterminal mass",
    "semantics": "successful model outcomes only; responses update their result register and complete event history; stop states emit no further calls",
    "comparison": "one fixed public store and all explicitly supplied distinct secret assignments",
    "excluded": [
        "provider behavior/probability validity",
        "errors/retries",
        "currency/cumulative budgets",
        "termination probability/infinite-run laws",
    ],
}

DEFAULT_MAX_STATES = 10_000
MAX_STATES = 1_000_000
DEFAULT_MAX_WORK_BYTES = 64 * 1024 * 1024
MAX_WORK_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_MATRIX_ENTRIES = 10_000_000
MAX_MATRIX_ENTRIES = 100_000_000
DEFAULT_MAX_RATIONAL_BITS = 8192
MAX_RATIONAL_BITS = 8192
MAX_REPORT_BYTES = 64 * 1024 * 1024
# Count each dense rational-vector slot at 64 deterministic work bytes. This
# deliberately conservative meter limits Python object growth before vectors
# are allocated; it is still not a process-RSS guarantee.
VECTOR_SLOT_WORK_BYTES = 64
TOP_KEYS = {
    "format", "version", "status", "claim", "hashes", "inputs", "limits",
    "closed_system", "label_alphabet", "result", "scope", "diagnostics", "telemetry",
}
HASH_KEYS = {
    "graph_sha256", "kernel_sha256", "public_store_sha256",
    "secret_scenarios_sha256", "checker_sha256", "closure_producer_sha256",
}


class _Unknown(Exception):
    """A deterministic analysis cap was reached; no partial result is usable."""

    def __init__(self, message: str, *, reason: str = "OTHER_RESOURCE_LIMIT",
                 phase: str = "row_space", resource: str | None = None,
                 limit: int | None = None, observed: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.phase = phase
        self.resource = resource
        self.limit = limit
        self.observed = observed


class _Invalid(Exception):
    """Inputs or arguments are outside the supported exact semantics."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _canon(value: Any) -> bytes:
    return utf8(_closure.canonical(value))


def _rational_bits(value: Fraction) -> int:
    return max(abs(value.numerator).bit_length(), value.denominator.bit_length())


def _channel_limit_reason(message: str) -> str:
    """Map closure/channel cap text to a stable, non-sensitive reason code."""
    lowered = message.lower()
    if "semantic-state byte" in lowered or "state-key byte" in lowered:
        return "STATE_KEY_BYTE_CAP"
    if "state" in lowered and ("state cap" in lowered or "resource cap" in lowered):
        return "STATE_CAP"
    if "control" in lowered and ("step" in lowered or "limit" in lowered):
        return "CONTROL_STEP_CAP"
    if "transition" in lowered:
        return "TRANSITION_CAP"
    if "request" in lowered and "byte" in lowered:
        return "REQUEST_BYTE_CAP"
    if "rational" in lowered or "precision cap" in lowered:
        return "RATIONAL_BIT_CAP"
    if "integer digit" in lowered:
        return "INTEGER_DIGIT_CAP"
    if "trace" in lowered and "byte" in lowered:
        return "TRACE_BYTE_CAP"
    if "value" in lowered and ("byte" in lowered or "limit" in lowered):
        return "VALUE_BYTE_CAP"
    if ("source" in lowered or "document" in lowered or "scenario" in lowered
            or "serialized" in lowered) and "byte" in lowered:
        return "SOURCE_BYTE_CAP"
    if "byte-work" in lowered or "work" in lowered:
        return "BYTE_WORK_CAP"
    return "OTHER_RESOURCE_LIMIT"


def _channel_limit_message(reason: str) -> str:
    """Return a bounded stable message without embedding input paths or values."""
    return {
        "STATE_CAP": "reachable semantic-state cap reached",
        "STATE_KEY_BYTE_CAP": "semantic-state key byte cap reached",
        "CONTROL_STEP_CAP": "deterministic control-step cap reached",
        "TRANSITION_CAP": "call-transition expansion cap reached",
        "REQUEST_BYTE_CAP": "request byte cap reached",
        "RATIONAL_BIT_CAP": "exact rational arithmetic precision cap reached",
        "INTEGER_DIGIT_CAP": "JSON integer digit cap reached",
        "TRACE_BYTE_CAP": "trace byte cap reached",
        "SOURCE_BYTE_CAP": "input or document byte cap reached",
        "VALUE_BYTE_CAP": "request or kernel value byte cap reached",
        "BYTE_WORK_CAP": "cumulative byte-work cap reached",
        "MEMORY_LIMIT": "process memory allocation limit reached",
        "OTHER_RESOURCE_LIMIT": "analysis stopped at an unsupported resource limit",
    }.get(reason, "analysis stopped at a configured resource limit")


class _Meter:
    """Deterministic pre-allocation meter for matrix and byte-work."""

    def __init__(self, max_entries: int, max_bytes: int, max_bits: int,
                 initial_bytes: int = 0):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.max_bits = max_bits
        self.entries_used = 0
        self.bytes_used = initial_bytes
        self.max_rational_bits_observed = 0
        self.phase = "row_space"
        if self.bytes_used > self.max_bytes:
            raise _Unknown(
                "closed-system work leaves no byte-work budget for row-space analysis",
                reason="BYTE_WORK_CAP", phase="row_space", resource="work_bytes",
                limit=self.max_bytes, observed=self.bytes_used,
            )

    def entries(self, count: int, label: str) -> None:
        if type(count) is not int or count < 0:
            raise _Invalid(f"invalid deterministic matrix charge for {label}")
        new_total = self.entries_used + count
        if new_total > self.max_entries:
            raise _Unknown(f"{label} matrix-entry cap reached", reason="MATRIX_ENTRY_CAP",
                           phase=self.phase, resource="matrix_entries",
                           limit=self.max_entries, observed=new_total)
        new_bytes = self.bytes_used + count * VECTOR_SLOT_WORK_BYTES
        if new_bytes > self.max_bytes:
            raise _Unknown(f"{label} byte-work cap reached", reason="BYTE_WORK_CAP",
                           phase=self.phase, resource="work_bytes",
                           limit=self.max_bytes, observed=new_bytes)
        self.entries_used = new_total
        self.bytes_used = new_bytes

    def bytes(self, count: int, label: str) -> None:
        if type(count) is not int or count < 0:
            raise _Invalid(f"invalid deterministic byte charge for {label}")
        new_total = self.bytes_used + count
        if new_total > self.max_bytes:
            raise _Unknown(f"{label} byte-work cap reached", reason="BYTE_WORK_CAP",
                           phase=self.phase, resource="work_bytes",
                           limit=self.max_bytes, observed=new_total)
        self.bytes_used = new_total

    def fraction(self, value: Fraction, label: str) -> Fraction:
        bits = _rational_bits(value)
        self.max_rational_bits_observed = max(self.max_rational_bits_observed, bits)
        if bits > self.max_bits:
            raise _Unknown(f"{label} exceeds the {self.max_bits}-bit exact-rational cap",
                           reason="RATIONAL_BIT_CAP", phase=self.phase,
                           resource="rational_bits", limit=self.max_bits, observed=bits)
        return value

    def _preflight(self, numerator_bits: int, denominator_bits: int, label: str) -> None:
        if max(numerator_bits, denominator_bits) > self.max_bits:
            observed = max(numerator_bits, denominator_bits)
            raise _Unknown(f"{label} may exceed the {self.max_bits}-bit exact-rational cap",
                           reason="RATIONAL_BIT_CAP", phase=self.phase,
                           resource="rational_bits", limit=self.max_bits, observed=observed)

    def add(self, left: Fraction, right: Fraction, label: str) -> Fraction:
        if not left:
            return self.fraction(right, label)
        if not right:
            return self.fraction(left, label)
        # Upper-bound the unreduced common-denominator result before creating it.
        nbits = max(left.numerator.bit_length() + right.denominator.bit_length(),
                    right.numerator.bit_length() + left.denominator.bit_length()) + 1
        dbits = left.denominator.bit_length() + right.denominator.bit_length()
        self._preflight(nbits, dbits, label)
        return self.fraction(left + right, label)

    def subtract(self, left: Fraction, right: Fraction, label: str) -> Fraction:
        if not right:
            return self.fraction(left, label)
        if not left:
            return self.fraction(-right, label)
        nbits = max(left.numerator.bit_length() + right.denominator.bit_length(),
                    right.numerator.bit_length() + left.denominator.bit_length()) + 1
        dbits = left.denominator.bit_length() + right.denominator.bit_length()
        self._preflight(nbits, dbits, label)
        return self.fraction(left - right, label)

    def multiply(self, left: Fraction, right: Fraction, label: str) -> Fraction:
        if not left or not right:
            return Fraction(0)
        self._preflight(left.numerator.bit_length() + right.numerator.bit_length(),
                        left.denominator.bit_length() + right.denominator.bit_length(), label)
        return self.fraction(left * right, label)

    def divide(self, left: Fraction, right: Fraction, label: str) -> Fraction:
        if not right:
            raise _Invalid("internal row normalization divided by zero")
        if not left:
            return Fraction(0)
        self._preflight(left.numerator.bit_length() + right.denominator.bit_length(),
                        left.denominator.bit_length() + right.numerator.bit_length(), label)
        return self.fraction(left / right, label)


class _RowSpace:
    """Exact reduced row basis; normalized pivot rows are kept as Fractions."""

    def __init__(self, dimension: int, meter: _Meter):
        self.dimension = dimension
        self.meter = meter
        self.rows: dict[int, list[Fraction]] = {}

    def reduce(self, row: list[Fraction], label: str) -> list[Fraction]:
        if len(row) != self.dimension:
            raise _Invalid(f"{label} has wrong vector dimension")
        self.meter.entries(self.dimension, f"{label} temporary vector")
        result = list(row)
        for pivot in sorted(self.rows):
            factor = result[pivot]
            if not factor:
                continue
            basis = self.rows[pivot]
            # Charge before the O(dimension) exact coefficient updates.
            self.meter.entries(self.dimension, f"{label} elimination scan")
            for column in range(self.dimension):
                result[column] = self.meter.subtract(
                    result[column],
                    self.meter.multiply(factor, basis[column], f"{label} product"),
                    f"{label} reduced coefficient",
                )
        return result

    def add_independent(self, row: list[Fraction], label: str) -> tuple[bool, int | None]:
        residual = self.reduce(row, label)
        pivot = next((index for index, value in enumerate(residual) if value), None)
        if pivot is None:
            return False, None
        scale = residual[pivot]
        self.meter.entries(self.dimension, f"{label} normalized basis row")
        normalized = [self.meter.divide(value, scale, f"{label} normalization")
                      for value in residual]
        # Keep RREF-style pivot normalization. A new row is zero at every old
        # pivot; update old rows so they are zero at the newly inserted pivot.
        for old_pivot, old_row in list(self.rows.items()):
            factor = old_row[pivot]
            if factor:
                self.meter.entries(self.dimension, f"{label} pivot elimination")
                self.rows[old_pivot] = [
                    self.meter.subtract(
                        current,
                        self.meter.multiply(factor, value, f"{label} pivot product"),
                        f"{label} pivot coefficient",
                    )
                    for current, value in zip(old_row, normalized)
                ]
        self.rows[pivot] = normalized
        return True, pivot


def _dot(row: list[Fraction], indicator: list[Fraction], meter: _Meter,
         label: str) -> Fraction:
    total = Fraction(0)
    for left, right in zip(row, indicator):
        if left and right:
            total = meter.add(total, meter.multiply(left, right, f"{label} product"), label)
    return total


def _product(vector: list[Fraction], edges: list[tuple[int, int, Fraction]],
             dimension: int, meter: _Meter, label: str) -> list[Fraction]:
    if len(vector) != dimension:
        raise _Invalid("internal matrix/vector dimension mismatch")
    # Preflight dense allocation and sparse-edge scan before allocating.
    meter.entries(dimension, f"{label} output vector")
    meter.entries(len(edges), f"{label} sparse-matrix scan")
    result = [Fraction(0) for _ in range(dimension)]
    for source, target, probability in edges:
        if vector[source]:
            product = meter.multiply(vector[source], probability, f"{label} product")
            result[target] = meter.add(result[target], product, f"{label} accumulated coefficient")
    return result


def _state_system(system: dict[str, Any], meter: _Meter):
    state_keys = sorted(system["states"])
    state_ids = {key: f"S{index:06d}" for index, key in enumerate(state_keys)}
    state_index = {key: index for index, key in enumerate(state_keys)}
    transition_total = sum(len(system["edge_rows"][key]) for key in state_keys)
    # Reserve before building duplicate certificate and adjacency structures.
    meter.entries(transition_total, "sparse labeled adjacency")
    meter.entries(2 * len(state_keys), "stop/nonterminal output vectors")
    states_out: list[dict[str, Any]] = []
    transitions_out: list[dict[str, Any]] = []
    observable: dict[str, dict[str, Any]] = {}
    matrices: dict[str, list[tuple[int, int, Fraction]]] = defaultdict(list)

    for key in state_keys:
        state = system["states"][key]
        kind, _event = system["graph"].event(state.pc)
        states_out.append({
            "id": state_ids[key],
            **_closure._state_document(state, system["identities"]),
            "kind": "stop" if kind == "stop" else "call",
        })
        for label_text, target_key, probability in system["edge_rows"][key]:
            meter.fraction(probability, "closed-system transition probability")
            raw_label = json.loads(label_text)
            if raw_label.get("kind") != "call":
                raise _Invalid("closed system contains a non-call edge")
            label = {field: value for field, value in raw_label.items() if field != "kind"}
            label_text = _closure.canonical(label)
            observable[label_text] = label
            target_index = state_index[target_key]
            source_index = state_index[key]
            matrices[label_text].append((source_index, target_index, probability))
            transitions_out.append({
                "from": state_ids[key],
                # The closed semantic system retains its transition kind; the
                # separate usage alphabet below projects it away.
                "label": raw_label,
                "to": state_ids[target_key],
                "probability": str(probability),
            })

    alphabet_keys = sorted(observable)
    dimension = len(state_keys)
    stop = []
    for row in states_out:
        stop.append(Fraction(1 if row["kind"] == "stop" else 0))
    nonterminal = [Fraction(1) - value for value in stop]
    initial_ids = [state_ids[key] for key in system["initial_keys"]]
    closed = {
        "state_count": len(states_out),
        "transition_count": len(transitions_out),
        "initial_state_ids": initial_ids,
        "states": states_out,
        "transitions": transitions_out,
    }
    return state_keys, state_ids, state_index, closed, alphabet_keys, observable, matrices, stop, nonterminal


def _word_json(word: tuple[int, ...] | list[int], alphabet_keys: list[str],
               observable: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [observable[alphabet_keys[index]] for index in word]


def _unit_row(index: int, dimension: int, meter: _Meter, label: str) -> list[Fraction]:
    meter.entries(dimension, label)
    row = [Fraction(0) for _ in range(dimension)]
    row[index] = Fraction(1)
    return row


def _counterexample(word: tuple[int, ...], left_scenario: int,
                    right_scenario: int, initial_ids: list[str],
                    matrices: dict[str, list[tuple[int, int, Fraction]]],
                    alphabet_keys: list[str], observable: dict[str, dict[str, Any]],
                    stop: list[Fraction], nonterminal: list[Fraction], meter: _Meter):
    dimension = len(stop)
    left_row = _unit_row(int(initial_ids[left_scenario][1:]),
                         dimension, meter, "counterexample left initial vector")
    right_row = _unit_row(int(initial_ids[right_scenario][1:]),
                          dimension, meter, "counterexample right initial vector")
    # The canonical S-id's numeric suffix is its state-vector index.
    output_kind = None
    left_probability = right_probability = Fraction(0)
    for label_index in word:
        matrix = matrices[alphabet_keys[label_index]]
        left_row = _product(left_row, matrix, dimension, meter, "counterexample left word")
        right_row = _product(right_row, matrix, dimension, meter, "counterexample right word")
    stop_difference = meter.subtract(
        _dot(left_row, stop, meter, "counterexample left stop"),
        _dot(right_row, stop, meter, "counterexample right stop"),
        "counterexample stop difference",
    )
    if stop_difference:
        output_kind = "stop"
        output = stop
    else:
        output_kind = "nonterminal"
        output = nonterminal
    left_probability = _dot(left_row, output, meter, "counterexample left output")
    right_probability = _dot(right_row, output, meter, "counterexample right output")
    if left_probability == right_probability:
        raise _Invalid("internal counterexample did not distinguish exact probabilities")
    return {
        "word": _word_json(word, alphabet_keys, observable),
        "end_kind": output_kind,
        "left_probability": str(left_probability),
        "right_probability": str(right_probability),
    }


def _rational_text_size(value: Fraction) -> int:
    # Exact decimal lengths are bounded by max_rational_bits (<=8192), so these
    # temporary strings remain small even for a worst-case accepted coefficient.
    numerator = len(str(abs(value.numerator))) + (1 if value.numerator < 0 else 0)
    denominator = len(str(value.denominator))
    return numerator + (1 + denominator if value.denominator != 1 else 0)


def _analysis_result(system, meter: _Meter, state_keys, state_ids, state_index,
                     closed, alphabet_keys, observable, matrices, stop, nonterminal):
    dimension = len(state_keys)
    initial_indices = [int(state_id[1:]) for state_id in closed["initial_state_ids"]]
    pair_results = []
    total_serialized_basis_bytes = 0
    label_sizes = {key: len(_canon(observable[key])) for key in alphabet_keys}
    meter.bytes(sum(label_sizes.values()), "observable label alphabet")

    for scenario_index in range(1, len(initial_indices)):
        initial = _unit_row(initial_indices[scenario_index], dimension, meter,
                            "pair initial difference vector")
        initial[initial_indices[0]] = meter.subtract(
            initial[initial_indices[0]], Fraction(1), "pair initial difference coefficient"
        )
        row_space = _RowSpace(dimension, meter)
        queue: deque[tuple[tuple[int, ...], list[Fraction]]] = deque()
        stored_basis: list[tuple[tuple[int, ...], list[Fraction]]] = []

        def check_output(word: tuple[int, ...], row: list[Fraction]):
            stop_mass = _dot(row, stop, meter, "stop output")
            live_mass = _dot(row, nonterminal, meter, "nonterminal output")
            if stop_mass or live_mass:
                witness = _counterexample(
                    word, scenario_index, 0, closed["initial_state_ids"],
                    matrices, alphabet_keys, observable,
                    stop, nonterminal, meter,
                )
                return witness
            return None

        witness = check_output((), initial)
        if witness is None:
            independent, _pivot = row_space.add_independent(initial, "initial difference")
            if independent:
                meter.entries(dimension, "stored generator row")
                stored_basis.append(((), initial))
                queue.append(((), initial))

        while queue and witness is None:
            word, row = queue.popleft()
            for label_index, label_key in enumerate(alphabet_keys):
                next_word = word + (label_index,)
                candidate = _product(row, matrices[label_key], dimension, meter,
                                     "labeled row-space product")
                witness = check_output(next_word, candidate)
                if witness is not None:
                    break
                independent, _pivot = row_space.add_independent(candidate,
                                                                 "reachable generator row")
                if independent:
                    meter.entries(dimension, "stored generator row")
                    stored_basis.append((next_word, candidate))
                    queue.append((next_word, candidate))

        if witness is not None:
            unequal_pair = {
                "left_scenario": scenario_index,
                "right_scenario": 0,
                "left_state_id": closed["initial_state_ids"][scenario_index],
                "right_state_id": closed["initial_state_ids"][0],
                "status": "unequal",
                "counterexample": witness,
            }
            # The report decision is existential: one replayable witness is
            # sufficient, and preceding equal pairs are not claimed as a
            # complete analysis of every remaining scenario.
            return "unequal", [unequal_pair]

        # Preflight dense certificate rows before constructing JSON lists/strings.
        pair_rank_entries = len(stored_basis) * dimension
        meter.entries(pair_rank_entries, "serialized basis rows")
        pair_basis = []
        max_word_length = 0
        estimated_basis_bytes = 0
        for word, row in stored_basis:
            max_word_length = max(max_word_length, len(word))
            stop_dot = _dot(row, stop, meter, "serialized basis stop output")
            live_dot = _dot(row, nonterminal, meter, "serialized basis live output")
            if stop_dot or live_dot:
                raise _Invalid("internal equal basis contains nonzero output")
            # Estimate the final exact rational encoding before materializing it.
            estimated_basis_bytes += sum(_rational_text_size(value) + 3 for value in row)
            estimated_basis_bytes += 1024 + sum(label_sizes[alphabet_keys[label_index]] + 3
                                                for label_index in word)
            if total_serialized_basis_bytes + estimated_basis_bytes > MAX_REPORT_BYTES:
                raise _Unknown(
                    "serialized basis report byte cap reached",
                    reason="REPORT_BYTE_CAP", phase="certificate_serialization",
                    resource="report_bytes", limit=MAX_REPORT_BYTES,
                    observed=total_serialized_basis_bytes + estimated_basis_bytes,
                )
            pair_basis.append({
                "word": _word_json(word, alphabet_keys, observable),
                "row": [str(value) for value in row],
                "stop_dot": str(stop_dot),
                "nonterminal_dot": str(live_dot),
            })
        total_serialized_basis_bytes += estimated_basis_bytes
        pair_results.append({
            "left_scenario": scenario_index,
            "right_scenario": 0,
            "left_state_id": closed["initial_state_ids"][scenario_index],
            "right_state_id": closed["initial_state_ids"][0],
            "status": "equal",
            "basis": pair_basis,
            "rank": len(stored_basis),
            "initial_difference_in_span": True,
            "closed_under_label_matrices": True,
            "stop_outputs_zero": True,
            "nonterminal_outputs_zero": True,
            "max_word_length": max_word_length,
        })
    return "proved_equal", pair_results


def _safe_limits(max_states, max_work_bytes, max_matrix_entries, max_rational_bits):
    def safe(value, default, maximum):
        if type(value) is int and 1 <= value <= maximum:
            return value
        return default
    return {
        "max_states": safe(max_states, DEFAULT_MAX_STATES, MAX_STATES),
        "max_work_bytes": safe(max_work_bytes, DEFAULT_MAX_WORK_BYTES, MAX_WORK_BYTES),
        "max_matrix_entries": safe(max_matrix_entries, DEFAULT_MAX_MATRIX_ENTRIES,
                                    MAX_MATRIX_ENTRIES),
        "max_rational_bits": safe(max_rational_bits, DEFAULT_MAX_RATIONAL_BITS,
                                  MAX_RATIONAL_BITS),
    }


def _safe_json_copy(value: Any, fallback: Any) -> Any:
    try:
        _closure._canonical_size(value, _closure.MAX_SOURCE_BYTES)
        raw = _canon(value)
        return json.loads(raw)
    except (TypeError, ValueError, OverflowError, RecursionError, InvalidGraph):
        return fallback


def _base_report(status: str, *, graph_raw: bytes | None, kernel_raw: bytes | None,
                 public_store: Any, secret_scenarios: Any,
                 limits: dict[str, int], claim: str | None = None,
                 closed_system: Any = None, label_alphabet: Any = None,
                 result: Any = None, diagnostics: Any = None,
                 telemetry: Any = None) -> dict[str, Any]:
    public_copy = _safe_json_copy(public_store, {})
    scenarios_copy = _safe_json_copy(secret_scenarios, [])
    graph_digest = (_sha(graph_raw) if isinstance(graph_raw, bytes)
                    and len(graph_raw) <= _closure.MAX_SOURCE_BYTES else _sha(b""))
    kernel_digest = (_sha(kernel_raw) if isinstance(kernel_raw, bytes)
                     and len(kernel_raw) <= _closure.MAX_SOURCE_BYTES else _sha(b""))
    hashes = {
        "graph_sha256": graph_digest,
        "kernel_sha256": kernel_digest,
        "public_store_sha256": _sha(_canon(public_copy)),
        "secret_scenarios_sha256": _sha(_canon(scenarios_copy)),
        "checker_sha256": _file_sha(Path(__file__)),
        "closure_producer_sha256": _file_sha(Path(_closure.__file__)),
    }
    return {
        "format": FORMAT,
        "version": VERSION,
        "status": status,
        "claim": claim,
        "hashes": hashes,
        "inputs": {"public_store": public_copy, "secret_scenarios": scenarios_copy},
        "limits": limits,
        "closed_system": closed_system,
        "label_alphabet": label_alphabet,
        "result": result,
        "scope": SCOPE,
        "diagnostics": diagnostics,
        "telemetry": telemetry,
    }


def _preflight_independent_replay(result: dict[str, Any], alphabet_keys: list[str],
                                 matrices: dict[str, list[tuple[int, int, Fraction]]],
                                 dimension: int, meter: _Meter) -> None:
    """Reserve enough work for the independent certificate checker as well.

    This makes default producer reports replayable under their own declared
    matrix/work caps. The separate checker still reconstructs and meters its
    work independently; this is a conservative producer-side preflight.
    """
    edge_counts = {key: len(matrices[key]) for key in alphabet_keys}
    for pair in result["pairs"]:
        # Independent root-vector construction; the producer also performs it.
        meter.entries(dimension, "independent replay initial vector")
        if pair["status"] == "equal":
            # Certificate words are often nested (for example, successive
            # prefixes of a chain). Replay their shared trie once. Charging
            # every complete word independently makes the verifier's work
            # cubic in this common case even though only O(rank) distinct
            # prefix products are needed.
            prefix_trie: dict[str, Any] = {}
            for basis_item in pair["basis"]:
                word_keys = [_closure.canonical(label) for label in basis_item["word"]]
                node = prefix_trie
                for key in word_keys:
                    child = node.get(key)
                    if child is None:
                        # Reserve retained prefix-vector space as well as the
                        # temporary product vector charged below.
                        meter.entries(dimension,
                                      "independent replay basis-prefix cache row")
                        meter.entries(dimension + edge_counts[key],
                                      "independent replay basis-prefix product")
                        child = {}
                        node[key] = child
                    node = child
                # Verify independence and retain a normalized row.
                meter.entries(2 * dimension, "independent replay row-basis insertion")
                # Verify closure and membership for every label matrix.
                for key in alphabet_keys:
                    meter.entries(dimension + edge_counts[key],
                                  "independent replay closure product")
                    meter.entries(dimension, "independent replay closure membership")
            meter.entries(dimension, "independent replay initial-span membership")
        else:
            # The witness checker creates independent unit rows for both roots.
            meter.entries(2 * dimension, "independent replay witness roots")
            word_keys = [_closure.canonical(label)
                         for label in pair["counterexample"]["word"]]
            for key in word_keys:
                meter.entries(2 * (dimension + edge_counts[key]),
                              "independent replay witness-word products")


def analyze(graph_document: Any, kernel_document: Any, public_store: Any,
            secret_scenarios: Any, *, max_states: int = DEFAULT_MAX_STATES,
            max_work_bytes: int = DEFAULT_MAX_WORK_BYTES,
            max_matrix_entries: int = DEFAULT_MAX_MATRIX_ENTRIES,
            max_rational_bits: int = DEFAULT_MAX_RATIONAL_BITS,
            raw_graph: bytes | None = None,
            raw_kernel: bytes | None = None) -> dict[str, Any]:
    """Prove exact all-finite-horizon trace equality or return a finite witness.

    A resource cap yields UNKNOWN and no partial transition system or result.
    Invalid inputs yield INVALID. ``raw_graph`` and ``raw_kernel`` bind reports
    to exact source bytes; API callers that omit them bind canonical JSON bytes.
    """
    limits = _safe_limits(max_states, max_work_bytes, max_matrix_entries,
                          max_rational_bits)
    phase = "input_validation"
    meter: _Meter | None = None
    closed_telemetry: dict[str, Any] | None = None
    label_count_telemetry: int | None = None
    try:
        if limits["max_states"] != max_states or type(max_states) is not int:
            raise _Invalid("max_states must be an integer in [1, 1000000]")
        if limits["max_work_bytes"] != max_work_bytes or type(max_work_bytes) is not int:
            raise _Invalid("max_work_bytes must be an integer in [1, 1073741824]")
        if limits["max_matrix_entries"] != max_matrix_entries or type(max_matrix_entries) is not int:
            raise _Invalid("max_matrix_entries is outside supported integer bounds")
        if limits["max_rational_bits"] != max_rational_bits or type(max_rational_bits) is not int:
            raise _Invalid("max_rational_bits is outside supported integer bounds")
        graph_document = _closure._bounded_json(graph_document)
        kernel_document = _closure._bounded_json(kernel_document)
        public_store = _closure._bounded_json(public_store)
        secret_scenarios = _closure._bounded_json(secret_scenarios)
        if raw_graph is None:
            raw_graph = _canon(graph_document)
        elif not isinstance(raw_graph, bytes):
            raise _Invalid("raw_graph must be bytes")
        if raw_kernel is None:
            raw_kernel = _canon(kernel_document)
        elif not isinstance(raw_kernel, bytes):
            raise _Invalid("raw_kernel must be bytes")
        for raw, document, label in ((raw_graph, graph_document, "graph"),
                                     (raw_kernel, kernel_document, "kernel")):
            if len(raw) > _closure.MAX_SOURCE_BYTES:
                raise ChannelLimit(f"{label} raw source byte cap reached")
            try:
                parsed_raw = strict_json(raw)
            except (ValueError, TypeError, RecursionError, UnicodeError) as error:
                raise _Invalid(f"{label} raw source is invalid JSON: {error}") from error
            if _closure.canonical(parsed_raw) != _closure.canonical(document):
                raise _Invalid(f"{label} raw source bytes do not encode the supplied document")

        phase = "semantic_closure"
        system = _closure._build_closed_system(
            graph_document, kernel_document, public_store, secret_scenarios,
            limits["max_states"], limits["max_work_bytes"],
        )
        closed_telemetry = {
            "state_count": len(system["states"]),
            "transition_count": system["transition_count"],
        }
        # The underlying closure is the semantic source of truth. Charge its
        # deterministic work before any exact row-space allocation.
        source_store_bytes = len(_canon(system["public_store"])) + len(
            _canon(system["secret_scenarios"])
        )
        meter = _Meter(limits["max_matrix_entries"], limits["max_work_bytes"],
                       limits["max_rational_bits"],
                       system["work"].used + source_store_bytes)
        phase = "matrix_build"
        meter.phase = phase
        (state_keys, state_ids, state_index, closed, alphabet_keys, observable,
         matrices, stop, nonterminal) = _state_system(system, meter)
        closed_telemetry = closed
        label_count_telemetry = len(alphabet_keys)
        phase = "row_space"
        meter.phase = phase
        status, pairs = _analysis_result(
            system, meter, state_keys, state_ids, state_index, closed,
            alphabet_keys, observable, matrices, stop, nonterminal,
        )
        alphabet = [observable[key] for key in alphabet_keys]
        result = {"basis_state_order": [row["id"] for row in closed["states"]],
                  "pairs": pairs}
        phase = "certificate_replay_preflight"
        meter.phase = phase
        _preflight_independent_replay(result, alphabet_keys, matrices,
                                      len(state_keys), meter)
        report = _base_report(
            status, graph_raw=raw_graph, kernel_raw=raw_kernel,
            public_store=system["public_store"],
            secret_scenarios=system["secret_scenarios"], limits=limits,
            claim=CLAIM_EQUAL if status == "proved_equal" else CLAIM_UNEQUAL,
            closed_system=closed, label_alphabet=alphabet, result=result,
            telemetry={
                "closed_state_count": closed["state_count"],
                "transition_count": closed["transition_count"],
                "label_count": len(alphabet_keys),
                "matrix_entries_used": meter.entries_used,
                "work_bytes_used_before_serialization": meter.bytes_used,
                "max_rational_bits_observed": meter.max_rational_bits_observed,
            },
        )
        phase = "report_serialization"
        meter.phase = phase
        report_bytes = utf8(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False))
        if len(report_bytes) > MAX_REPORT_BYTES:
            raise _Unknown("complete report byte cap reached",
                           reason="REPORT_BYTE_CAP", phase=phase,
                           resource="report_bytes", limit=MAX_REPORT_BYTES,
                           observed=len(report_bytes))
        meter.bytes(len(report_bytes), "complete certificate report")
        return report
    except (_Unknown, ChannelLimit, MemoryError) as error:
        if isinstance(error, _Unknown):
            diagnostic = {
                "reason": error.reason,
                "phase": error.phase,
                "message": str(error)[:512],
                "resource": (None if error.resource is None else {
                    "name": error.resource, "limit": error.limit,
                    "observed": error.observed,
                }),
            }
        else:
            if isinstance(error, MemoryError):
                reason = "MEMORY_LIMIT"
            else:
                reason = _channel_limit_reason(str(error))
            diagnostic = {"reason": reason, "phase": phase,
                          "message": _channel_limit_message(reason),
                          "resource": None}
        telemetry = {
            "closed_state_count": (None if closed_telemetry is None
                                   else closed_telemetry["state_count"]),
            "transition_count": (None if closed_telemetry is None
                                 else closed_telemetry["transition_count"]),
            "label_count": label_count_telemetry,
            "matrix_entries_used": None if meter is None else meter.entries_used,
            "work_bytes_used_before_serialization": (
                None if meter is None else meter.bytes_used
            ),
            "max_rational_bits_observed": (
                None if meter is None else meter.max_rational_bits_observed
            ),
        }
        return _base_report(
            "unknown", graph_raw=raw_graph, kernel_raw=raw_kernel,
            public_store=public_store, secret_scenarios=secret_scenarios,
            limits=limits, diagnostics=diagnostic, telemetry=telemetry,
        )
    except (_Invalid, ChannelError, InvalidGraph, ValueError, TypeError,
            KeyError, OverflowError, ZeroDivisionError, RecursionError) as error:
        return _base_report(
            "invalid", graph_raw=raw_graph, kernel_raw=raw_kernel,
            public_store=public_store, secret_scenarios=secret_scenarios,
            limits=limits, result={"diagnostic": str(error)},
        )


def _read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(_closure.MAX_SOURCE_BYTES + 1)
    if len(raw) > _closure.MAX_SOURCE_BYTES:
        raise ChannelLimit("source document byte cap reached: " + str(path))
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--public-json", required=True,
                        help="JSON object assigning exactly the public inputs")
    parser.add_argument("--scenarios-json", required=True,
                        help="JSON array of 2..64 distinct secret assignments")
    parser.add_argument("--max-states", type=int, default=DEFAULT_MAX_STATES)
    parser.add_argument("--max-work-bytes", type=int, default=DEFAULT_MAX_WORK_BYTES)
    parser.add_argument("--max-matrix-entries", type=int, default=DEFAULT_MAX_MATRIX_ENTRIES)
    parser.add_argument("--max-rational-bits", type=int, default=DEFAULT_MAX_RATIONAL_BITS)
    parser.add_argument("--report", type=Path,
                        help="also write the complete JSON report to this path")
    args = parser.parse_args(argv)
    raw_graph = raw_kernel = None
    public_store: Any = {}
    scenarios: Any = []
    limits = _safe_limits(args.max_states, args.max_work_bytes,
                          args.max_matrix_entries, args.max_rational_bits)
    try:
        raw_graph = _read_bounded(args.graph)
        raw_kernel = _read_bounded(args.kernel)
        if len(utf8(args.public_json)) + len(utf8(args.scenarios_json)) > _closure.MAX_SOURCE_BYTES:
            raise ChannelLimit("public/scenario JSON byte cap reached")
        graph_document = strict_json(raw_graph)
        kernel_document = strict_json(raw_kernel)
        public_store = strict_json(args.public_json)
        scenarios = strict_json(args.scenarios_json)
        report = analyze(
            graph_document, kernel_document, public_store, scenarios,
            max_states=args.max_states,
            max_work_bytes=args.max_work_bytes,
            max_matrix_entries=args.max_matrix_entries,
            max_rational_bits=args.max_rational_bits,
            raw_graph=raw_graph,
            raw_kernel=raw_kernel,
        )
    except (ChannelLimit, OSError, ValueError, TypeError, InvalidGraph,
            OverflowError, RecursionError) as error:
        status = "unknown" if isinstance(error, ChannelLimit) else "invalid"
        unknown_reason = (_channel_limit_reason(str(error))
                          if status == "unknown" else None)
        report = _base_report(status, graph_raw=raw_graph, kernel_raw=raw_kernel,
                              public_store=public_store, secret_scenarios=scenarios,
                              limits=limits,
                              result=(None if status == "unknown" else {"diagnostic": str(error)}),
            diagnostics=({
                                  "reason": unknown_reason,
                                  "phase": "input_validation",
                                  "message": _channel_limit_message(unknown_reason),
                                  "resource": None,
                              } if status == "unknown" else None),
                              telemetry=({
                                  "closed_state_count": None,
                                  "transition_count": None,
                                  "label_count": None,
                                  "matrix_entries_used": None,
                                  "work_bytes_used_before_serialization": None,
                                  "max_rational_bits_observed": None,
                              } if status == "unknown" else None))

    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return {"proved_equal": 0, "unequal": 1, "invalid": 2, "unknown": 3}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
