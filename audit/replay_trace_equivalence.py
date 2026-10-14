#!/usr/bin/env python3
"""Independently replay exact finite-state trace-equivalence certificates.

This verifier reconstructs the bound graph/kernel transition system through
the independent stochastic-certificate reference implementation, then checks
the producer's weighted-automaton certificate using its own exact rational
linear algebra. It does not import the trace-equivalence producer or its
matrix/refinement code.
"""
from __future__ import annotations

from collections import defaultdict
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
    from . import replay_stochastic_certificate as _closure
except ImportError:
    import replay_stochastic_certificate as _closure  # type: ignore[no-redef]


REPORT_FORMAT = "orchlang-exact-trace-equivalence"
ATTESTATION_FORMAT = "orchlang-exact-trace-equivalence-replay-attestation"
SUPPORTED_VERSIONS = {1, 2}
MAX_MATRIX_ENTRIES = 100_000_000
MAX_WORK_BYTES = 1024 * 1024 * 1024
MAX_RATIONAL_BITS = 8192
MAX_STATES = 1_000_000
MAX_TRANSITIONS = 1_000_000
MAX_CONTROL_STEPS = 10_000_000
MAX_SCENARIOS = 64
MAX_SOURCE_BYTES = _closure.MAX_SOURCE_BYTES
MAX_REPORT_BYTES = _closure.MAX_REPORT_BYTES
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RATIONAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")

TOP_KEYS = {
    "format", "version", "status", "claim", "hashes", "inputs", "limits",
    "closed_system", "label_alphabet", "result", "scope",
}
TOP_KEYS_V2 = TOP_KEYS | {"diagnostics", "telemetry"}
HASH_KEYS = {
    "graph_sha256", "kernel_sha256", "public_store_sha256",
    "secret_scenarios_sha256", "checker_sha256", "closure_producer_sha256",
}
INPUT_KEYS = {"public_store", "secret_scenarios"}
LIMIT_KEYS = {"max_states", "max_work_bytes", "max_matrix_entries", "max_rational_bits"}
RESULT_KEYS = {"basis_state_order", "pairs"}
PAIR_BASE_KEYS = {
    "left_scenario", "right_scenario", "left_state_id", "right_state_id", "status",
}
PAIR_EQUAL_KEYS = PAIR_BASE_KEYS | {
    "basis", "rank", "initial_difference_in_span", "closed_under_label_matrices",
    "stop_outputs_zero", "nonterminal_outputs_zero", "max_word_length",
}
PAIR_UNEQUAL_KEYS = PAIR_BASE_KEYS | {"counterexample"}
COUNTEREXAMPLE_KEYS = {"word", "end_kind", "left_probability", "right_probability"}
LABEL_KEYS = {"contract", "input_tokens", "output_tokens"}
BASIS_KEYS = {"word", "row", "stop_dot", "nonterminal_dot"}
DIAGNOSTIC_KEYS = {"reason", "phase", "message", "resource"}
RESOURCE_KEYS = {"name", "limit", "observed"}
TELEMETRY_KEYS = {
    "closed_state_count", "transition_count", "label_count",
    "matrix_entries_used", "work_bytes_used_before_serialization",
    "max_rational_bits_observed",
}
UNKNOWN_REASONS = {
    "STATE_CAP", "BYTE_WORK_CAP", "MATRIX_ENTRY_CAP", "RATIONAL_BIT_CAP",
    "REPORT_BYTE_CAP", "SOURCE_BYTE_CAP", "CONTROL_STEP_CAP", "MEMORY_LIMIT",
    "STATE_KEY_BYTE_CAP", "TRANSITION_CAP", "REQUEST_BYTE_CAP",
    "INTEGER_DIGIT_CAP", "TRACE_BYTE_CAP", "VALUE_BYTE_CAP",
    "OTHER_RESOURCE_LIMIT",
}
UNKNOWN_PHASES = {
    "input_validation", "semantic_closure", "matrix_build", "row_space",
    "certificate_replay_preflight", "certificate_serialization", "report_serialization",
}
RESOURCE_NAMES = {
    "states", "work_bytes", "matrix_entries", "rational_bits", "report_bytes",
    "source_bytes", "control_steps", "memory_bytes",
}

CLAIM_EQUAL = (
    "exact all-finite-horizon success-only ordered usage-trace laws for every supplied "
    "secret scenario under the declared finite rational kernel"
)
CLAIM_UNEQUAL = "a finite ordered-usage observation distinguishes the supplied scenarios"
SCOPE = {
    "oracle": "declared finite rational conditional kernel; exact modeled request, "
              "saturated contract ordinal, and retained complete-event history determine outcomes",
    "observer": "ordered call labels are normalized resolved contract plus integer input and "
                "output usage; each finite word is observed with separate stopped and nonterminal mass",
    "semantics": "successful model outcomes only; responses update their result register and "
                 "complete event history; stop states emit no further calls",
    "comparison": "one fixed public store and all explicitly supplied distinct secret assignments",
    "excluded": ["provider behavior/probability validity", "errors/retries", "currency/cumulative budgets",
                 "termination probability/infinite-run laws"],
}


class TraceReplayError(ValueError):
    """Malformed or semantically inconsistent trace-equivalence report."""


class TraceReplayLimit(RuntimeError):
    """The independent exact replay exceeded a declared verifier budget."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _obj(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TraceReplayError(f"{label} must be an object")
    return value


def _keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    result = _obj(value, label)
    missing, unknown = expected - result.keys(), result.keys() - expected
    if missing or unknown:
        raise TraceReplayError(
            f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return result


def _nat(value: Any, label: str, minimum: int = 0, maximum: int = MAX_STATES) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TraceReplayError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _validate_v2_metadata(report: dict[str, Any]) -> None:
    """Validate additive v2 diagnostics and advisory producer counters."""
    status = report.get("status")
    diagnostics = report.get("diagnostics")
    telemetry = report.get("telemetry")
    if status == "unknown":
        item = _keys(diagnostics, DIAGNOSTIC_KEYS, "diagnostics")
        if item["reason"] not in UNKNOWN_REASONS:
            raise TraceReplayError("diagnostics.reason is not a supported UNKNOWN reason")
        if item["phase"] not in UNKNOWN_PHASES:
            raise TraceReplayError("diagnostics.phase is not a supported analysis phase")
        if not isinstance(item["message"], str) or not 1 <= len(item["message"]) <= 4096:
            raise TraceReplayError("diagnostics.message must be a bounded nonempty string")
        resource = item["resource"]
        if resource is not None:
            resource = _keys(resource, RESOURCE_KEYS, "diagnostics.resource")
            if resource["name"] not in RESOURCE_NAMES:
                raise TraceReplayError("diagnostics.resource.name is unsupported")
            for field in ("limit", "observed"):
                value = resource[field]
                if value is not None and (type(value) is not int or not 0 <= value < 2**63):
                    raise TraceReplayError(f"diagnostics.resource.{field} must be a bounded nonnegative integer or null")
    elif diagnostics is not None:
        raise TraceReplayError("non-UNKNOWN v2 reports must have null diagnostics")

    if telemetry is None:
        raise TraceReplayError("v2 reports must include resource telemetry")
    item = _keys(telemetry, TELEMETRY_KEYS, "telemetry")
    nullable_bounds = {
        "closed_state_count": MAX_STATES,
        "transition_count": MAX_TRANSITIONS,
        "label_count": MAX_TRANSITIONS,
        "matrix_entries_used": MAX_MATRIX_ENTRIES,
        "work_bytes_used_before_serialization": MAX_WORK_BYTES,
        "max_rational_bits_observed": MAX_RATIONAL_BITS,
    }
    for field, maximum in nullable_bounds.items():
        value = item[field]
        if value is None:
            if status != "unknown":
                raise TraceReplayError(f"successful telemetry.{field} must be an integer")
        elif (type(value) is not int or not 0 <= value <= maximum
              or (field == "closed_state_count" and value == 0)):
            raise TraceReplayError(f"telemetry.{field} is outside its supported range")


def _check_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise TraceReplayError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any, limit: int | None = None) -> str:
    try:
        return _closure._canonical(value, limit)
    except _closure.ReplayLimit as error:
        raise TraceReplayLimit(str(error)) from error
    except _closure.ReplayError as error:
        raise TraceReplayError(str(error)) from error


def _bounded_fraction(value: Fraction, bits: int, label: str) -> Fraction:
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > bits:
        raise TraceReplayLimit(f"{label} exceeds the {bits}-bit exact-rational cap")
    return value


def _fraction(value: Any, label: str, bits: int) -> Fraction:
    if not isinstance(value, str) or len(value) > 6000 or not RATIONAL_RE.fullmatch(value):
        raise TraceReplayError(f"{label} must be a canonical exact rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        if _closure._is_int_display_limit(error):
            raise TraceReplayLimit(f"{label} integer parsing reached its resource limit") from error
        raise TraceReplayError(f"{label} is not an exact rational") from error
    if str(result) != value:
        raise TraceReplayError(f"{label} is not reduced canonical rational text")
    return _bounded_fraction(result, bits, label)


class _Meter:
    """Deterministic local meter for vector/matrix and canonical-byte work."""

    def __init__(self, max_matrix_entries: int, max_work_bytes: int, rational_bits: int,
                 initial_work_bytes: int = 0):
        self.max_matrix_entries = max_matrix_entries
        self.max_work_bytes = max_work_bytes
        self.rational_bits = rational_bits
        self.matrix_entries = 0
        self.work_bytes = initial_work_bytes
        if type(initial_work_bytes) is not int or initial_work_bytes < 0:
            raise TraceReplayError("invalid initial independent byte-work charge")
        if self.work_bytes > self.max_work_bytes:
            raise TraceReplayLimit("independent cumulative byte-work cap reached")

    def entries(self, count: int, label: str) -> None:
        if type(count) is not int or count < 0:
            raise TraceReplayError(f"invalid matrix-entry charge for {label}")
        new_entries = self.matrix_entries + count
        if new_entries > self.max_matrix_entries:
            raise TraceReplayLimit(f"independent {label} matrix-entry cap reached")
        new_work_bytes = self.work_bytes + count * 16
        if new_work_bytes > self.max_work_bytes:
            raise TraceReplayLimit(f"independent {label} byte-work cap reached")
        self.matrix_entries = new_entries
        self.work_bytes = new_work_bytes

    def bytes(self, count: int, label: str) -> None:
        self.work_bytes += count
        if self.work_bytes > self.max_work_bytes:
            raise TraceReplayLimit(f"independent {label} byte-work cap reached")

    def fraction(self, value: Fraction, label: str) -> Fraction:
        return _bounded_fraction(value, self.rational_bits, label)


class _RowSpace:
    """Exact RREF-style row-space membership and independence checker."""

    def __init__(self, dimension: int, meter: _Meter):
        self.dimension = dimension
        self.meter = meter
        self.rows: dict[int, list[Fraction]] = {}

    @staticmethod
    def _zero(row: list[Fraction]) -> bool:
        return all(value == 0 for value in row)

    def reduce(self, row: list[Fraction], label: str) -> list[Fraction]:
        if len(row) != self.dimension:
            raise TraceReplayError(f"{label} has the wrong vector dimension")
        self.meter.entries(self.dimension, f"{label} temporary-vector")
        result = list(row)
        for pivot in sorted(self.rows):
            factor = result[pivot]
            if factor:
                basis = self.rows[pivot]
                for column in range(self.dimension):
                    result[column] = self.meter.fraction(
                        result[column] - factor * basis[column],
                        f"{label} row-reduction coefficient",
                    )
        return result

    def add_independent(self, row: list[Fraction], label: str) -> int:
        result = self.reduce(row, label)
        pivot = next((i for i, value in enumerate(result) if value), None)
        if pivot is None:
            raise TraceReplayError(f"{label} rows are not linearly independent")
        scale = result[pivot]
        result = [self.meter.fraction(value / scale, f"{label} normalized coefficient")
                  for value in result]
        for existing_pivot, existing in list(self.rows.items()):
            factor = existing[pivot]
            if factor:
                self.rows[existing_pivot] = [
                    self.meter.fraction(
                        current - factor * value,
                        f"{label} echelon coefficient",
                    )
                    for current, value in zip(existing, result)
                ]
        self.meter.entries(self.dimension, f"{label} stored-echelon")
        self.rows[pivot] = result
        return pivot

    def contains(self, row: list[Fraction], label: str) -> bool:
        return self._zero(self.reduce(row, label))


def _matrix_product(vector: list[Fraction], edges: list[tuple[int, int, Fraction]],
                    dimension: int, meter: _Meter, label: str) -> list[Fraction]:
    if len(vector) != dimension:
        raise TraceReplayError("matrix product vector dimension mismatch")
    meter.entries(dimension, f"{label} product-vector")
    meter.entries(len(edges), f"{label} sparse-matrix-scan")
    result = [Fraction(0) for _ in range(dimension)]
    for source, target, probability in edges:
        if vector[source]:
            result[target] = meter.fraction(
                result[target] + vector[source] * probability,
                f"{label} product coefficient",
            )
    return result


def _dot(row: list[Fraction], indicator: list[Fraction], meter: _Meter,
         label: str) -> Fraction:
    total = Fraction(0)
    for left, right in zip(row, indicator):
        total = meter.fraction(total + left * right, f"{label} dot product")
    return total


def _label(value: Any, label: str, *, bits: int, byte_limit: int) -> tuple[str, dict[str, Any]]:
    item = _keys(value, LABEL_KEYS, label)
    if not isinstance(item["contract"], dict):
        raise TraceReplayError(f"{label}.contract must be an object")
    _nat(item["input_tokens"], f"{label}.input_tokens", 0, _closure.MAX_TOKEN)
    _nat(item["output_tokens"], f"{label}.output_tokens", 0, _closure.MAX_TOKEN)
    rendered = _canonical(item, byte_limit)
    return rendered, item


def _attestation(status: str, *, diagnostic: str | None = None,
                  details: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "format": ATTESTATION_FORMAT,
        "version": 1,
        "status": status,
        "decision": None,
        "verification_method": "independent bounded finite semantic-closure reconstruction and verifier-owned exact rational weighted-automaton span or witness checks",
        "claim_scope": "this attests only the supplied source-bound finite rational model, fixed stores, and declared success-only ordered-usage observer; it is not a general algorithm theorem proof or a real-provider claim",
        "all_finite_horizons_claim": False,
        "unverified_fields": [
            "hashes.checker_sha256 and hashes.closure_producer_sha256 (digest syntax checked only; executable identity is not established)",
            "producer-side resource consumption; the verifier measures its own deterministic budget",
        ],
        "diagnostic": diagnostic,
    }
    if details:
        result.update(details)
    return result


def _load_sources(report_source: Any, graph_source: Any, kernel_source: Any):
    report_raw, report = _closure._report_document(report_source)
    graph_raw = _closure._read_bounded(graph_source, "graph source", MAX_SOURCE_BYTES)
    kernel_raw = _closure._read_bounded(kernel_source, "kernel source", MAX_SOURCE_BYTES)
    return report_raw, report, graph_raw, kernel_raw


def _verify_hashes(report: dict[str, Any], graph_raw: bytes, kernel_raw: bytes,
                   *, require_inputs: bool) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    hashes = _obj(report.get("hashes"), "hashes")
    graph_hash, kernel_hash = _sha(graph_raw), _sha(kernel_raw)
    if hashes.get("graph_sha256") != graph_hash:
        raise TraceReplayError("report graph hash differs from supplied raw graph bytes")
    if hashes.get("kernel_sha256") != kernel_hash:
        raise TraceReplayError("report kernel hash differs from supplied raw kernel bytes")
    _check_sha(hashes.get("checker_sha256"), "hashes.checker_sha256")
    _check_sha(hashes.get("closure_producer_sha256"), "hashes.closure_producer_sha256")
    if not require_inputs:
        return hashes, {}, graph_hash, kernel_hash
    hashes = _keys(hashes, HASH_KEYS, "hashes")
    inputs = _keys(report.get("inputs"), INPUT_KEYS, "inputs")
    public = _obj(inputs["public_store"], "inputs.public_store")
    scenarios = inputs["secret_scenarios"]
    if not isinstance(scenarios, list) or not 2 <= len(scenarios) <= MAX_SCENARIOS:
        raise TraceReplayError("secret_scenarios must contain 2..64 assignments")
    public_hash, public_size = _closure._canonical_digest(
        public, "public_store", MAX_SOURCE_BYTES
    )
    scenario_hash, scenario_size = _closure._canonical_digest(
        scenarios, "secret_scenarios", MAX_SOURCE_BYTES
    )
    if public_size + scenario_size > MAX_SOURCE_BYTES:
        raise TraceReplayLimit("aggregate public-store and scenario byte cap reached")
    if hashes["public_store_sha256"] != public_hash:
        raise TraceReplayError("canonical public_store SHA-256 mismatch")
    if hashes["secret_scenarios_sha256"] != scenario_hash:
        raise TraceReplayError("canonical secret_scenarios SHA-256 mismatch")
    return hashes, inputs, graph_hash, kernel_hash


def _parse_limits(raw: Any, *, max_states: int, max_transitions: int,
                  max_work_bytes: int, max_matrix_entries: int,
                  max_control_steps: int, max_rational_bits: int) -> dict[str, int]:
    limits = _keys(raw, LIMIT_KEYS, "limits")
    declared = {
        "max_states": _nat(limits["max_states"], "limits.max_states", 1, MAX_STATES),
        "max_work_bytes": _nat(limits["max_work_bytes"], "limits.max_work_bytes", 1, MAX_WORK_BYTES),
        "max_matrix_entries": _nat(limits["max_matrix_entries"], "limits.max_matrix_entries", 1, MAX_MATRIX_ENTRIES),
        "max_rational_bits": _nat(limits["max_rational_bits"], "limits.max_rational_bits", 1, MAX_RATIONAL_BITS),
    }
    return {
        "max_states": min(max_states, declared["max_states"]),
        "max_transitions": max_transitions,
        "max_work_bytes": min(max_work_bytes, declared["max_work_bytes"]),
        "max_matrix_entries": min(max_matrix_entries, declared["max_matrix_entries"]),
        "max_control_steps": max_control_steps,
        "max_rational_bits": min(max_rational_bits, declared["max_rational_bits"]),
    }


def _semantic_system(report: dict[str, Any], graph_raw: bytes, kernel_raw: bytes,
                     inputs: dict[str, Any], limits: dict[str, int]):
    graph_document = _closure._parse_json(graph_raw, "graph source", MAX_SOURCE_BYTES)
    kernel_document = _closure._parse_json(kernel_raw, "kernel source", MAX_SOURCE_BYTES)
    _closure._check_tree(graph_document, "graph source")
    _closure._check_tree(kernel_document, "kernel source")
    system = _closure._construct_closed_system(
        graph_document, kernel_document, inputs["public_store"], inputs["secret_scenarios"],
        max_states=limits["max_states"],
        max_transitions=limits["max_transitions"],
        max_work_bytes=limits["max_work_bytes"],
        max_control_steps=limits["max_control_steps"],
    )
    closed = _closure._keys(report["closed_system"], _closure.SYSTEM_KEYS, "closed_system")
    # The producer schema fixes vector coordinates to the supplied state-array
    # order; require its canonical S-id ordering so that row meaning is stable.
    raw_states = closed["states"]
    if not isinstance(raw_states, list):
        raise TraceReplayError("closed_system.states must be an array")
    claimed_state_count = closed["state_count"]
    if type(claimed_state_count) is not int or claimed_state_count < 1:
        raise TraceReplayError("closed_system.state_count must be a positive integer")
    if claimed_state_count > limits["max_states"] or len(raw_states) > limits["max_states"]:
        raise TraceReplayLimit("closed_system state-table cap reached")
    if len(raw_states) != claimed_state_count:
        raise TraceReplayError("closed_system state_count differs from its state table")
    if not isinstance(closed["transitions"], list):
        raise TraceReplayError("closed_system.transitions must be an array")
    if len(closed["transitions"]) > limits["max_transitions"]:
        raise TraceReplayLimit("closed_system transition-table cap reached")
    state_ids = [row.get("id") if isinstance(row, dict) else None for row in raw_states]
    if any(not isinstance(state_id, str) or not re.fullmatch(r"S[0-9]{6}", state_id)
           for state_id in state_ids):
        raise TraceReplayError("closed_system.states contains a noncanonical S-id")
    if state_ids != sorted(state_ids):
        raise TraceReplayError("closed_system.states must be in ascending S-id order")
    if len(state_ids) != len(set(state_ids)):
        raise TraceReplayError("closed_system state ids must be unique")
    # The stochastic certificate helper predates this report schema and requires
    # a bisimulation block reference. Add one only to a private validation copy;
    # the trace-equivalence format deliberately contains no partition field.
    validation_closed = dict(closed)
    validation_closed["states"] = []
    for state in raw_states:
        row = _keys(state, {"id", "pc", "values", "ordinals", "history", "kind"},
                    "closed_system state")
        validation_closed["states"].append({**row, "block": "trace-state"})
    key_by_id, _validated_raw_by_id = _closure._validate_state_table(system, validation_closed)
    raw_by_id = {row["id"]: row for row in raw_states}
    canonical_ids = {
        key: f"S{index:06d}" for index, key in enumerate(sorted(system["states"]))
    }
    if any(canonical_ids.get(key) != state_id for state_id, key in key_by_id.items()):
        raise TraceReplayError("closed_system state IDs differ from canonical semantic-key order")
    system["initial_ids"] = closed["initial_state_ids"]
    _closure._validate_edges(system, closed["transitions"], key_by_id)
    edge_count = sum(len(rows) for rows in system["edge_rows"].values())
    if _nat(closed["transition_count"], "closed_system.transition_count", 0,
            MAX_TRANSITIONS) != edge_count:
        raise TraceReplayError("closed_system transition_count differs from independent closure")
    ordered_keys = [key_by_id[state_id] for state_id in state_ids]
    if len(ordered_keys) != len(system["states"]):
        raise TraceReplayError("closed_system state order does not cover independent closure")
    return system, closed, key_by_id, raw_by_id, ordered_keys


def _build_matrices(system: dict[str, Any], ordered_keys: list[str],
                    report_alphabet: Any, meter: _Meter):
    dimension = len(ordered_keys)
    entry_count = sum(len(rows) for rows in system["edge_rows"].values())
    # Charge sparse adjacency before allocating its per-edge tuples/lists.
    # If either declared budget cannot hold the reconstruction, fail closed
    # while only the independently closed edge rows are retained.
    meter.entries(entry_count, "sparse labeled adjacency")
    index_by_key = {key: index for index, key in enumerate(ordered_keys)}
    raw_matrices: dict[str, list[tuple[int, int, Fraction]]] = defaultdict(list)
    labels: dict[str, dict[str, Any]] = {}
    for source, rows in system["edge_rows"].items():
        source_index = index_by_key[source]
        for label_text, target, probability in rows:
            label_json = json.loads(label_text)
            if label_json.get("kind") != "call":
                raise TraceReplayError("independent closure contains a non-call transition label")
            label_json = {key: value for key, value in label_json.items() if key != "kind"}
            label_key, label = _label(
                label_json, "closed_system transition label",
                bits=meter.rational_bits, byte_limit=MAX_SOURCE_BYTES,
            )
            labels[label_key] = label
            raw_matrices[label_key].append((source_index, index_by_key[target], probability))
    alphabet = [_label(item, f"label_alphabet[{i}]", bits=meter.rational_bits,
                        byte_limit=MAX_SOURCE_BYTES)
                for i, item in enumerate(report_alphabet if isinstance(report_alphabet, list) else [])]
    if not isinstance(report_alphabet, list):
        raise TraceReplayError("label_alphabet must be an array")
    alphabet_keys = [key for key, _ in alphabet]
    actual_keys = sorted(labels)
    if alphabet_keys != actual_keys or len(alphabet_keys) != len(set(alphabet_keys)):
        raise TraceReplayError("label_alphabet differs from the independently reconstructed actions")
    matrices = {key: raw_matrices[key] for key in actual_keys}
    meter.entries(2 * dimension, "stop/nonterminal output vectors")
    stop = [Fraction(1 if system["kinds"][key] == "stop" else 0)
            for key in ordered_keys]
    nonterminal = [Fraction(1) - value for value in stop]
    return index_by_key, labels, matrices, stop, nonterminal


def _initial_vector(pair: dict[str, Any], scenario_count: int,
                    closed: dict[str, Any], index_by_key: dict[str, int],
                    key_by_id: dict[str, str], dimension: int, meter: _Meter,
                    *, label: str) -> tuple[int, int, list[Fraction]]:
    left = _nat(pair.get("left_scenario"), f"{label}.left_scenario", 0, scenario_count - 1)
    right = _nat(pair.get("right_scenario"), f"{label}.right_scenario", 0, scenario_count - 1)
    if left == right:
        raise TraceReplayError(f"{label} must compare distinct scenarios")
    roots = closed["initial_state_ids"]
    left_id, right_id = roots[left], roots[right]
    if pair.get("left_state_id") != left_id or pair.get("right_state_id") != right_id:
        raise TraceReplayError(f"{label} initial state ids differ from scenario roots")
    meter.entries(dimension, f"{label} initial vector")
    row = [Fraction(0) for _ in range(dimension)]
    row[index_by_key[key_by_id[left_id]]] += 1
    row[index_by_key[key_by_id[right_id]]] -= 1
    return left, right, row


def _word(value: Any, alphabet_keys: set[str], *, label: str,
          max_length: int, meter: _Meter) -> list[str]:
    if not isinstance(value, list) or len(value) > max_length:
        raise TraceReplayError(f"{label} must be an array of at most {max_length} labels")
    result: list[str] = []
    for index, item in enumerate(value):
        key, _ = _label(item, f"{label}[{index}]", bits=meter.rational_bits,
                         byte_limit=MAX_SOURCE_BYTES)
        if key not in alphabet_keys:
            raise TraceReplayError(f"{label}[{index}] is not in the reconstructed alphabet")
        result.append(key)
    return result


def _word_row(initial: list[Fraction], word: list[str], matrices: dict[str, list[tuple[int, int, Fraction]]],
              dimension: int, meter: _Meter, label: str) -> list[Fraction]:
    meter.entries(dimension, f"{label} initial-vector copy")
    row = list(initial)
    for index, action in enumerate(word):
        row = _matrix_product(row, matrices[action], dimension, meter,
                              f"{label} word action {index}")
    return row


def _basis_pair(pair: dict[str, Any], *, pair_label: str, initial: list[Fraction],
                dimension: int, alphabet_keys: set[str], matrices: dict[str, list[tuple[int, int, Fraction]]],
                stop: list[Fraction], nonterminal: list[Fraction], meter: _Meter,
                max_basis_rows: int) -> dict[str, Any]:
    pair = _keys(pair, PAIR_EQUAL_KEYS, pair_label)
    if pair["status"] != "equal":
        raise TraceReplayError(f"{pair_label}.status must be equal")
    raw_basis = pair["basis"]
    if not isinstance(raw_basis, list) or len(raw_basis) > max_basis_rows:
        raise TraceReplayError(f"{pair_label}.basis must be a bounded array")
    # Reserve the retained parsed Fraction rows as a batch before constructing
    # any one row. `parsed_rows` retains each resulting list throughout exact
    # closure verification. Row-space reduction/storage below meters their own
    # distinct working copies; do not charge these reserved input rows again.
    meter.entries(len(raw_basis) * dimension,
                  f"{pair_label} parsed basis-row storage")
    rows_by_word: set[tuple[str, ...]] = set()
    row_space = _RowSpace(dimension, meter)
    parsed_rows: list[tuple[list[str], list[Fraction]]] = []
    # Words share prefixes frequently: a chain certificate contains successive
    # prefixes of one path. Retain each exact prefix product once and reuse it
    # when reconstructing later basis rows. This changes verification cost,
    # not the certificate equation μA_word or the checked row values.
    prefix_root: dict[str, Any] = {"row": initial, "children": {}}
    for index, raw_item in enumerate(raw_basis):
        item = _keys(raw_item, BASIS_KEYS, f"{pair_label}.basis[{index}]")
        word = _word(item["word"], alphabet_keys, label=f"{pair_label}.basis[{index}].word",
                     max_length=dimension, meter=meter)
        word_id = tuple(word)
        if word_id in rows_by_word:
            raise TraceReplayError(f"{pair_label}.basis repeats a word")
        rows_by_word.add(word_id)
        node = prefix_root
        for action_index, action in enumerate(word):
            child = node["children"].get(action)
            if child is None:
                meter.entries(dimension, f"{pair_label} prefix-cache row")
                row = _matrix_product(
                    node["row"], matrices[action], dimension, meter,
                    f"{pair_label}.basis[{index}] prefix action {action_index}",
                )
                child = {"row": row, "children": {}}
                node["children"][action] = child
            node = child
        expected = node["row"]
        raw_row = item["row"]
        if not isinstance(raw_row, list) or len(raw_row) != dimension:
            raise TraceReplayError(f"{pair_label}.basis[{index}].row must have {dimension} entries")
        actual = [_fraction(value, f"{pair_label}.basis[{index}].row[{j}]", meter.rational_bits)
                  for j, value in enumerate(raw_row)]
        if actual != expected:
            raise TraceReplayError(f"{pair_label}.basis[{index}] row differs from μA_word")
        stop_dot = _fraction(item["stop_dot"],
                             f"{pair_label}.basis[{index}].stop_dot", meter.rational_bits)
        nonterminal_dot = _fraction(item["nonterminal_dot"],
                                     f"{pair_label}.basis[{index}].nonterminal_dot",
                                     meter.rational_bits)
        if stop_dot != _dot(actual, stop, meter, f"{pair_label}.basis[{index}] stop output"):
            raise TraceReplayError(f"{pair_label}.basis[{index}].stop_dot differs from exact output")
        if nonterminal_dot != _dot(actual, nonterminal, meter,
                                   f"{pair_label}.basis[{index}] nonterminal output"):
            raise TraceReplayError(f"{pair_label}.basis[{index}].nonterminal_dot differs from exact output")
        row_space.add_independent(actual, f"{pair_label}.basis[{index}]")
        parsed_rows.append((word, actual))
    rank = _nat(pair["rank"], f"{pair_label}.rank", 0, dimension)
    if rank != len(parsed_rows) or rank != len(row_space.rows):
        raise TraceReplayError(f"{pair_label}.rank differs from exact basis rank")
    if not row_space.contains(initial, f"{pair_label}.initial-membership"):
        raise TraceReplayError(f"{pair_label}.basis does not span the initial difference row")

    for basis_index, (_word_value, row) in enumerate(parsed_rows):
        for action in sorted(matrices):
            image = _matrix_product(row, matrices[action], dimension, meter,
                                    f"{pair_label}.basis[{basis_index}] closure")
            if not row_space.contains(image, f"{pair_label}.basis[{basis_index}] closure-membership"):
                raise TraceReplayError(f"{pair_label}.basis span is not closed under every action matrix")
        stop_mass = _dot(row, stop, meter, f"{pair_label} stop output")
        call_mass = _dot(row, nonterminal, meter, f"{pair_label} nonterminal output")
        if stop_mass != 0 or call_mass != 0:
            raise TraceReplayError(f"{pair_label}.basis has a nonzero terminal/nonterminal output")
    if (pair["initial_difference_in_span"] is not True
            or pair["closed_under_label_matrices"] is not True
            or pair["stop_outputs_zero"] is not True
            or pair["nonterminal_outputs_zero"] is not True):
        raise TraceReplayError(f"{pair_label} exact span/output flags must all be true")
    max_word_length = max((len(word) for word, _row in parsed_rows), default=0)
    if _nat(pair["max_word_length"], f"{pair_label}.max_word_length", 0, MAX_STATES) != max_word_length:
        raise TraceReplayError(f"{pair_label}.max_word_length differs from its basis")
    return {"rank": rank, "basis_size": len(parsed_rows),
            "max_word_length": max_word_length,
            "checked_action_closures": len(parsed_rows) * len(matrices)}


def _counterexample_pair(pair: dict[str, Any], *, pair_label: str,
                         scenario_count: int, closed: dict[str, Any],
                         index_by_key: dict[str, int], key_by_id: dict[str, str],
                         dimension: int, alphabet_keys: set[str],
                         matrices: dict[str, list[tuple[int, int, Fraction]]],
                         stop: list[Fraction], nonterminal: list[Fraction],
                         meter: _Meter, max_word_length: int) -> dict[str, Any]:
    pair = _keys(pair, PAIR_UNEQUAL_KEYS, pair_label)
    if pair["status"] != "unequal":
        raise TraceReplayError(f"{pair_label}.status must be unequal")
    left, right, _difference = _initial_vector(
        pair, scenario_count, closed, index_by_key, key_by_id, dimension,
        meter, label=pair_label,
    )
    counterexample = _keys(pair["counterexample"], COUNTEREXAMPLE_KEYS,
                           f"{pair_label}.counterexample")
    word = _word(counterexample["word"], alphabet_keys,
                 label=f"{pair_label}.counterexample.word",
                 max_length=max_word_length, meter=meter)
    end_kind = counterexample["end_kind"]
    if end_kind == "stop":
        output = stop
    elif end_kind == "nonterminal":
        output = nonterminal
    else:
        raise TraceReplayError(f"{pair_label}.counterexample.end_kind must be stop or nonterminal")
    initial_ids = closed["initial_state_ids"]
    left_id, right_id = initial_ids[left], initial_ids[right]
    meter.entries(2 * dimension, f"{pair_label} witness initial vectors")
    left_vector = [Fraction(0) for _ in range(dimension)]
    right_vector = [Fraction(0) for _ in range(dimension)]
    left_vector[index_by_key[key_by_id[left_id]]] = Fraction(1)
    right_vector[index_by_key[key_by_id[right_id]]] = Fraction(1)
    left_row = _word_row(left_vector, word, matrices, dimension, meter,
                         f"{pair_label} witness left")
    right_row = _word_row(right_vector, word, matrices, dimension, meter,
                          f"{pair_label} witness right")
    left_probability = _dot(left_row, output, meter, f"{pair_label} left witness output")
    right_probability = _dot(right_row, output, meter, f"{pair_label} right witness output")
    claimed_left = _fraction(counterexample["left_probability"],
                             f"{pair_label}.counterexample.left_probability", meter.rational_bits)
    claimed_right = _fraction(counterexample["right_probability"],
                              f"{pair_label}.counterexample.right_probability", meter.rational_bits)
    if (claimed_left, claimed_right) != (left_probability, right_probability):
        raise TraceReplayError(f"{pair_label} exact witness probabilities differ from independent replay")
    if left_probability == right_probability:
        raise TraceReplayError(f"{pair_label} purported counterexample has equal probabilities")
    return {"word_length": len(word), "end_kind": end_kind,
            "left_probability": str(left_probability),
            "right_probability": str(right_probability)}


def replay_report(report_source: Any, graph_source: Any, kernel_source: Any, *,
                  expected_public_store: Any | None = None,
                  expected_secret_scenarios: Any | None = None,
                  max_states: int = 10_000,
                  max_transitions: int = 1_000_000,
                  max_work_bytes: int = 64 * 1024 * 1024,
                  max_matrix_entries: int = 10_000_000,
                  max_control_steps: int = 1_000_000,
                  max_rational_bits: int = MAX_RATIONAL_BITS) -> dict[str, Any]:
    """Independently replay an exact weighted finite-trace certificate."""
    try:
        max_states = _nat(max_states, "max_states", 1, MAX_STATES)
        max_transitions = _nat(max_transitions, "max_transitions", 1, MAX_TRANSITIONS)
        max_work_bytes = _nat(max_work_bytes, "max_work_bytes", 1, MAX_WORK_BYTES)
        max_matrix_entries = _nat(max_matrix_entries, "max_matrix_entries", 1, MAX_MATRIX_ENTRIES)
        max_control_steps = _nat(max_control_steps, "max_control_steps", 1, MAX_CONTROL_STEPS)
        max_rational_bits = _nat(max_rational_bits, "max_rational_bits", 1, MAX_RATIONAL_BITS)
        report_raw, raw_report, graph_raw, kernel_raw = _load_sources(
            report_source, graph_source, kernel_source
        )
        report = _obj(raw_report, "report")
        if (report.get("format") != REPORT_FORMAT
                or type(report.get("version")) is not int
                or report["version"] not in SUPPORTED_VERSIONS):
            raise TraceReplayError("unsupported trace-equivalence report format/version")
        if report.get("status") == "invalid":
            raise TraceReplayError("producer report status is invalid")
        version = report["version"]
        report = _keys(report, TOP_KEYS if version == 1 else TOP_KEYS_V2, "report")
        if version == 2:
            _validate_v2_metadata(report)
        _closure._check_tree(report, "trace-equivalence report")
        hashes, inputs, graph_hash, kernel_hash = _verify_hashes(
            report, graph_raw, kernel_raw, require_inputs=True
        )
        if report.get("status") == "unknown":
            if (report.get("claim") is not None or report.get("closed_system") is not None
                    or report.get("result") is not None or report.get("label_alphabet") is not None):
                raise TraceReplayError("UNKNOWN report must not carry a partial closure, alphabet, or trace claim")
            _parse_limits(
                report["limits"], max_states=max_states,
                max_transitions=max_transitions, max_work_bytes=max_work_bytes,
                max_matrix_entries=max_matrix_entries,
                max_control_steps=max_control_steps,
                max_rational_bits=max_rational_bits,
            )
            if report.get("scope") != SCOPE:
                raise TraceReplayError("UNKNOWN scope declaration differs from the supported semantics")
            return _attestation("unknown", diagnostic="producer report is UNKNOWN; no partial result is replayed",
                                details={"graph_sha256": graph_hash,
                                         "kernel_sha256": kernel_hash,
                                         "report_sha256": _sha(report_raw),
                                         **({"producer_diagnostics": report["diagnostics"],
                                             "producer_telemetry": report["telemetry"]}
                                            if version == 2 else {})})
        if report.get("status") not in ("proved_equal", "unequal"):
            raise TraceReplayError("report status must be proved_equal, unequal, or unknown")
        expected_claim = CLAIM_EQUAL if report["status"] == "proved_equal" else CLAIM_UNEQUAL
        if report.get("claim") != expected_claim:
            raise TraceReplayError("report claim does not match its exact decision semantics")
        if report.get("scope") != SCOPE:
            raise TraceReplayError("scope declaration differs from the supported semantics")
        if expected_public_store is not None:
            _obj(expected_public_store, "expected public_store")
            _closure._check_tree(expected_public_store, "expected public_store")
            expected, _ = _closure._canonical_digest(expected_public_store, "expected public_store", MAX_SOURCE_BYTES)
            if expected != hashes["public_store_sha256"]:
                raise TraceReplayError("report public store differs from caller-supplied expected input")
        if expected_secret_scenarios is not None:
            if not isinstance(expected_secret_scenarios, list):
                raise TraceReplayError("expected secret scenarios must be an array")
            _closure._check_tree(expected_secret_scenarios, "expected secret scenarios")
            expected, _ = _closure._canonical_digest(expected_secret_scenarios, "expected scenarios", MAX_SOURCE_BYTES)
            if expected != hashes["secret_scenarios_sha256"]:
                raise TraceReplayError("report secret scenarios differ from caller-supplied expected inputs")

        limits = _parse_limits(
            report["limits"], max_states=max_states,
            max_transitions=max_transitions, max_work_bytes=max_work_bytes,
            max_matrix_entries=max_matrix_entries,
            max_control_steps=max_control_steps,
            max_rational_bits=max_rational_bits,
        )
        if len(inputs["secret_scenarios"]) < 2:
            raise TraceReplayError("trace equivalence requires at least two secret scenarios")
        public_hash, public_size = _closure._canonical_digest(inputs["public_store"], "public_store", MAX_SOURCE_BYTES)
        scenarios_hash, scenarios_size = _closure._canonical_digest(inputs["secret_scenarios"], "secret_scenarios", MAX_SOURCE_BYTES)
        base_work_bytes = len(report_raw) + len(graph_raw) + len(kernel_raw) + public_size + scenarios_size
        if base_work_bytes >= limits["max_work_bytes"]:
            raise TraceReplayLimit("independent source/input byte-work cap reached")
        closure_limits = dict(limits)
        closure_limits["max_work_bytes"] = limits["max_work_bytes"] - base_work_bytes
        system, closed, key_by_id, _raw_by_id, ordered_keys = _semantic_system(
            report, graph_raw, kernel_raw, inputs, closure_limits
        )
        meter = _Meter(
            limits["max_matrix_entries"], limits["max_work_bytes"],
            limits["max_rational_bits"],
            initial_work_bytes=base_work_bytes + system["meter"].work_bytes,
        )
        dimension = len(ordered_keys)
        if dimension * len(inputs["secret_scenarios"]) > limits["max_matrix_entries"]:
            raise TraceReplayLimit("scenario root matrix cap reached")
        index_by_key, labels, matrices, stop, nonterminal = _build_matrices(
            system, ordered_keys, report["label_alphabet"], meter
        )
        if set(report["result"]) != RESULT_KEYS:
            raise TraceReplayError("result fields differ from the supported schema")
        expected_state_order = [row["id"] for row in closed["states"]]
        if report["result"]["basis_state_order"] != expected_state_order:
            raise TraceReplayError("result.basis_state_order differs from closed_system state order")
        pairs = report["result"]["pairs"]
        if not isinstance(pairs, list):
            raise TraceReplayError("result.pairs must be an array")
        expected_pairs = len(inputs["secret_scenarios"]) - 1
        if report["status"] == "proved_equal" and len(pairs) != expected_pairs:
            raise TraceReplayError("proved_equal report must contain a pair for each nonzero scenario index")
        if report["status"] == "unequal" and len(pairs) != 1:
            raise TraceReplayError("unequal report must contain exactly one finite witness pair")
        if not pairs:
            raise TraceReplayError("result.pairs must be nonempty")
        verified_pairs = []
        seen_pair_ids: set[tuple[int, int]] = set()
        for index, raw_pair in enumerate(pairs):
            pair_label = f"result.pairs[{index}]"
            pair_object = _obj(raw_pair, pair_label)
            status = pair_object.get("status")
            left, right = pair_object.get("left_scenario"), pair_object.get("right_scenario")
            pair_id = (_nat(left, f"{pair_label}.left_scenario", 0, expected_pairs),
                       _nat(right, f"{pair_label}.right_scenario", 0, expected_pairs))
            if pair_id[0] == pair_id[1] or pair_id in seen_pair_ids:
                raise TraceReplayError(f"{pair_label} repeats or compares the same scenario")
            seen_pair_ids.add(pair_id)
            left_index, right_index, initial = _initial_vector(
                pair_object, len(inputs["secret_scenarios"]), closed,
                index_by_key, key_by_id, dimension, meter, label=pair_label,
            )
            if report["status"] == "proved_equal" and status == "equal":
                result = _basis_pair(
                    pair_object, pair_label=pair_label, initial=initial,
                    dimension=dimension, alphabet_keys=set(labels), matrices=matrices,
                    stop=stop, nonterminal=nonterminal, meter=meter,
                    max_basis_rows=min(dimension, limits["max_matrix_entries"] // max(1, dimension)),
                )
                result.update({"left_scenario": left_index, "right_scenario": right_index,
                               "status": "equal"})
                verified_pairs.append(result)
            elif report["status"] == "unequal" and status == "unequal":
                if right_index != 0 or left_index == 0:
                    raise TraceReplayError("unequal pairs must compare a nonzero scenario on the left with scenario 0")
                result = _counterexample_pair(
                    pair_object, pair_label=pair_label,
                    scenario_count=len(inputs["secret_scenarios"]), closed=closed,
                    index_by_key=index_by_key, key_by_id=key_by_id,
                    dimension=dimension, alphabet_keys=set(labels), matrices=matrices,
                    stop=stop, nonterminal=nonterminal, meter=meter,
                    max_word_length=min(MAX_STATES, limits["max_states"]),
                )
                result.update({"left_scenario": left_index, "right_scenario": right_index,
                               "status": "unequal"})
                verified_pairs.append(result)
            else:
                raise TraceReplayError(f"{pair_label}.status must be equal or unequal")
        any_unequal = any(row["status"] == "unequal" for row in verified_pairs)
        if report["status"] == "proved_equal":
            expected_order = [(index, 0) for index in range(1, expected_pairs + 1)]
            actual_order = [(row["left_scenario"], row["right_scenario"]) for row in verified_pairs]
            if actual_order != expected_order or any_unequal:
                raise TraceReplayError("proved_equal pair list is incomplete, unordered, or unequal")
        elif not any_unequal:
            raise TraceReplayError("unequal report contains no independently verified witness")
        if report["status"] == "unequal" and len(verified_pairs) != len(pairs):
            raise TraceReplayError("unequal report contains an unverified pair")
        if meter.work_bytes > limits["max_work_bytes"]:
            raise TraceReplayLimit("independent cumulative byte-work cap reached")
        return _attestation("verified", details={
            "decision": report["status"],
            "all_finite_horizons_claim": report["status"] == "proved_equal",
            "report_sha256": _sha(report_raw),
            "graph_sha256": graph_hash,
            "kernel_sha256": kernel_hash,
            "public_store_sha256": public_hash,
            "secret_scenarios_sha256": scenarios_hash,
            "scenario_count": len(inputs["secret_scenarios"]),
            "state_count": dimension,
            "transition_count": sum(len(rows) for rows in system["edge_rows"].values()),
            "pair_count": len(verified_pairs),
            "verified_pairs": verified_pairs,
            "independent_matrix_entries": meter.matrix_entries,
            "independent_work_bytes": meter.work_bytes,
            "verifier_limits": limits,
        })
    except TraceReplayLimit as error:
        return _attestation("unknown", diagnostic=str(error))
    except (MemoryError, OverflowError, RecursionError) as error:
        return _attestation("unknown", diagnostic=f"independent replay resource limit: {error}")
    except _closure.ReplayLimit as error:
        return _attestation("unknown", diagnostic=str(error))
    except _closure.OracleInputError as error:
        if "resource" in str(error).lower() or "limit" in str(error).lower():
            return _attestation("unknown", diagnostic=f"independent parser resource limit: {error}")
        return _attestation("rejected", diagnostic=f"invalid graph/kernel: {error}")
    except (_closure.ReplayError, TraceReplayError, ValueError, TypeError,
            KeyError, OSError) as error:
        if _closure._is_int_display_limit(error):
            return _attestation("unknown", diagnostic=f"integer formatting resource limit: {error}")
        return _attestation("rejected", diagnostic=str(error))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--public-json")
    parser.add_argument("--scenarios-json")
    parser.add_argument("--max-states", type=int, default=10_000)
    parser.add_argument("--max-transitions", type=int, default=1_000_000)
    parser.add_argument("--max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-matrix-entries", type=int, default=10_000_000)
    parser.add_argument("--max-control-steps", type=int, default=1_000_000)
    parser.add_argument("--max-rational-bits", type=int, default=MAX_RATIONAL_BITS)
    args = parser.parse_args(argv)
    try:
        expected_public = None if args.public_json is None else _closure._parse_json(
            args.public_json.encode("utf-8"), "expected public store", MAX_SOURCE_BYTES
        )
        expected_scenarios = None if args.scenarios_json is None else _closure._parse_json(
            args.scenarios_json.encode("utf-8"), "expected secret scenarios", MAX_SOURCE_BYTES
        )
        result = replay_report(
            args.report, args.graph, args.kernel,
            expected_public_store=expected_public,
            expected_secret_scenarios=expected_scenarios,
            max_states=args.max_states,
            max_transitions=args.max_transitions,
            max_work_bytes=args.max_work_bytes,
            max_matrix_entries=args.max_matrix_entries,
            max_control_steps=args.max_control_steps,
            max_rational_bits=args.max_rational_bits,
        )
    except _closure.ReplayLimit as error:
        result = _attestation("unknown", diagnostic=str(error))
    except (_closure.ReplayError, ValueError, TypeError, OSError) as error:
        result = _attestation("rejected", diagnostic=str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return {"verified": 0, "unknown": 2, "rejected": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
