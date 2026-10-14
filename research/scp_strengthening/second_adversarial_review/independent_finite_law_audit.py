"""Tiny exact-law adversary for robust_usage.py; no source workflows are run.

This enumerates all quarter-grid conditional rows in selected TV balls for a
two-step, three-symbol observer, constructs exact trace laws independently,
and checks every pair against the package's submitted robust bound. It is a
finite falsification probe, not a proof of the general recurrence.
"""

from __future__ import annotations

import itertools
import json
import sys
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research/scp_strengthening/robust_usage"))
import robust_usage as ru  # noqa: E402


STOP = ru.STOP
ALPHABET = ("a", "b", STOP)
HISTORIES = ((), ("a",), ("b",))
RADIUS = Fraction(1, 4)


def compositions(total: int, length: int = 3):
    if length == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for rest in compositions(total - first, length - 1):
            yield (first, *rest)


GRID = tuple(compositions(4))


def as_law(counts):
    return {symbol: Fraction(count, 4) for symbol, count in zip(ALPHABET, counts)}


def tv(left, right):
    return sum((abs(left.get(x, 0) - right.get(x, 0)) for x in ALPHABET), Fraction(0)) / 2


def center_json(counts):
    return {symbol: str(probability) for symbol, probability in as_law(counts).items()}


def make_contract(left_centers, right_centers):
    rows = []
    for history in HISTORIES:
        rows.append({
            "history": list(history),
            "left": {"center": center_json(left_centers[history]), "radius": "1/4"},
            "right": {"center": center_json(right_centers[history]), "radius": "1/4"},
        })
    return {
        "schema": ru.SCHEMA,
        "horizon": 2,
        "alphabet": list(ALPHABET),
        "require_stop_by_horizon": False,
        "rows": rows,
    }


def row_options(counts):
    center = as_law(counts)
    return tuple(as_law(candidate) for candidate in GRID if tv(as_law(candidate), center) <= RADIUS)


def all_policies(centers):
    options = [row_options(centers[history]) for history in HISTORIES]
    return tuple(
        dict(zip(HISTORIES, selected))
        for selected in itertools.product(*options)
    )


def trace_law(policy):
    """Independent direct trace enumeration; STOP is visibly padded."""
    law = {(): Fraction(1)}
    for _ in range(2):
        nxt = {}
        for history, mass in law.items():
            row = ({STOP: Fraction(1)} if STOP in history else policy[history])
            for symbol, probability in row.items():
                if probability:
                    trace = history + (symbol,)
                    nxt[trace] = nxt.get(trace, Fraction(0)) + mass * probability
        law = nxt
    return law


def trace_tv(left, right):
    support = set(left) | set(right)
    return sum((abs(left.get(trace, 0) - right.get(trace, 0)) for trace in support), Fraction(0)) / 2


CASES = (
    (
        {(): (2, 1, 1), ("a",): (3, 1, 0), ("b",): (1, 0, 3)},
        {(): (1, 2, 1), ("a",): (0, 3, 1), ("b",): (1, 1, 2)},
    ),
    (
        {(): (2, 1, 1), ("a",): (2, 1, 1), ("b",): (2, 1, 1)},
        {(): (2, 1, 1), ("a",): (2, 1, 1), ("b",): (2, 1, 1)},
    ),
    (
        {(): (4, 0, 0), ("a",): (2, 1, 1), ("b",): (0, 0, 4)},
        {(): (3, 1, 0), ("a",): (1, 2, 1), ("b",): (1, 1, 2)},
    ),
)


def run_exact_enumeration():
    results = []
    for index, (left_centers, right_centers) in enumerate(CASES, 1):
        raw = make_contract(left_centers, right_centers)
        certificate = ru.certify(raw)
        bound = Fraction(certificate["tv_upper_bound"])
        left_policies = all_policies(left_centers)
        right_policies = all_policies(right_centers)
        laws_left = [trace_law(policy) for policy in left_policies]
        laws_right = [trace_law(policy) for policy in right_policies]
        maximum = max(trace_tv(a, b) for a in laws_left for b in laws_right)
        assert maximum <= bound, (index, maximum, bound)
        with patch.object(ru, "certify", side_effect=AssertionError("producer called by replay")):
            accepted, report = ru.replay(raw, certificate)
        assert accepted, report
        results.append({
            "case": index,
            "left_kernels": len(left_policies),
            "right_kernels": len(right_policies),
            "kernel_pairs_checked": len(left_policies) * len(right_policies),
            "max_exact_trace_tv": str(maximum),
            "certified_upper_bound": str(bound),
            "replay_without_certify": accepted,
        })
    return results


def parser_probes():
    cases = {
        "duplicate escaped key": b'{"field":1,"\\u0066ield":2}',
        "exponent number": b'{"field":1e400}',
        "deep nesting": b"[" * 1500 + b"0" + b"]" * 1500,
        "invalid UTF-8": b'{"field":"\xff"}',
        "lone escaped surrogate": b'{"field":"\\ud800"}',
    }
    outcomes = {}
    for name, payload in cases.items():
        try:
            ru._loads_json_bytes(payload, name)
        except ru.ContractError as exc:
            outcomes[name] = f"rejected: {str(exc).split(':')[0]}"
        else:
            raise AssertionError(f"parser accepted adversarial case: {name}")
    cyclic = []
    cyclic.append(cyclic)
    try:
        ru._validate_json_tree(cyclic, "cyclic direct object")
    except ru.ContractError as exc:
        outcomes["cyclic direct object"] = f"rejected: {str(exc).split(':')[0]}"
    else:
        raise AssertionError("tree validator accepted a cyclic direct object")
    return outcomes


def deterministic_row(symbol):
    return {"center": {name: str(Fraction(int(name == symbol))) for name in ALPHABET}, "radius": "0"}


def replay_boundary_probes():
    prefix_only = {
        "schema": ru.SCHEMA,
        "horizon": 1,
        "alphabet": list(ALPHABET),
        "require_stop_by_horizon": False,
        "rows": [{"history": [], "left": deterministic_row("a"), "right": deterministic_row("a")}],
    }
    prefix_certificate = ru.certify(prefix_only)
    accepted, report = ru.replay(prefix_only, prefix_certificate)
    assert accepted

    # Fault injection documents a trust boundary: replay uses _local_obligation
    # and certificate-row arithmetic shared with certify. This deliberately
    # corrupts that helper; it does not demonstrate a current-code defect.
    divergent = {
        "schema": ru.SCHEMA,
        "horizon": 1,
        "alphabet": list(ALPHABET),
        "require_stop_by_horizon": False,
        "rows": [{"history": [], "left": deterministic_row("a"), "right": deterministic_row("b")}],
    }
    actual_tv = tv(as_law((4, 0, 0)), as_law((0, 4, 0)))
    assert actual_tv == 1

    def injected_bad_local(_contract, history):
        return ru._Local(history, Fraction(0), Fraction(0), Fraction(0), Fraction(0), ("a",), False)

    with patch.object(ru, "_local_obligation", side_effect=injected_bad_local):
        forged = ru.certify(divergent)
        fault_accepted, _ = ru.replay(divergent, forged)
    assert fault_accepted and forged["tv_upper_bound"] == "0"
    return {
        "prefix_only_replay": {
            "scope": prefix_certificate["scope"],
            "termination_proved_by_contract": prefix_certificate["termination_proved_by_contract"],
            "checks_label_contains_stop_proof": "stop proof" in report["checks"],
        },
        "shared_helper_fault_injection": {
            "deliberately_corrupted_helper": "_local_obligation",
            "current_code_claim": False,
            "forged_bound": forged["tv_upper_bound"],
            "independently_enumerated_true_tv": str(actual_tv),
            "replay_accepts_under_injected_shared_fault": fault_accepted,
        },
    }


if __name__ == "__main__":
    print(json.dumps({
        "finite_grid": "all quarter-grid distributions over {a,b,__STOP__}",
        "per_row_tv_radius": "1/4",
        "horizon": 2,
        "exact_law_results": run_exact_enumeration(),
        "strict_parser_probes": parser_probes(),
        "replay_boundary_probes": replay_boundary_probes(),
    }, indent=2, sort_keys=True))
