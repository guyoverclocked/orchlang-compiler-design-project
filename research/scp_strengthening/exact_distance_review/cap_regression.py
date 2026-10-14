#!/usr/bin/env python3
"""Regression for generated-certificate JSON-item caps and direct replay.

The fixed synthetic contract stays below the DP-state and output-byte caps,
but yields a certificate with more than 200,000 JSON-tree items. The desired
behavior is either fail-closed generation or a certificate accepted by the
same bounded parser used by the CLI; the public direct verify() API must also
reject a certificate exceeding the active item cap.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "exact_uncertain_distance"))
import exact_uncertain_distance as subject  # noqa: E402

STOP = subject.STOP


def row(scenario: str, history: list[str], numerators: list[int], denominator: int) -> dict[str, object]:
    return {
        "scenario": scenario,
        "history": history,
        "generators": [
            {"A": f"{n}/{denominator}", STOP: f"{denominator - n}/{denominator}"}
            for n in numerators
        ],
    }


def terminal_row(scenario: str) -> dict[str, object]:
    return {"scenario": scenario, "history": ["A", "A"], "generators": [{"A": 0, STOP: 1}]}


def large_contract() -> dict[str, object]:
    return {
        "schema": subject.SCHEMA,
        "alphabet": ["A", STOP],
        "horizon": 3,
        "require_stop_by_horizon": True,
        "rows": [
            row("left", [], list(range(1, 33)), 33),
            row("right", [], list(range(1, 33)), 35),
            row("left", ["A"], [37, 41, 43, 47, 53], 107),
            row("right", ["A"], [37, 41, 43, 47, 53], 109),
            terminal_row("left"),
            terminal_row("right"),
        ],
    }


def main() -> None:
    raw = large_contract()
    default_items = subject.MAX_JSON_ITEMS

    # Keep the finite mathematical contract fixed while materializing an
    # oversized cert, so we can test the direct verifier's own input guard.
    subject.MAX_JSON_ITEMS = 1_000_000
    try:
        oversized = subject.certify(raw)
        encoded = subject._certificate_bytes(oversized)
    finally:
        subject.MAX_JSON_ITEMS = default_items

    print(f"oversized_certificate_states={len(oversized['states'])} bytes={len(encoded)}")
    try:
        subject.parse_json_bytes(encoded + b"\n", "oversized certificate")
    except subject.ContractError as exc:
        print(f"bounded_parser_rejects={exc}")
    else:
        print("bounded_parser_accepts=True")

    try:
        subject.verify(raw, oversized)
    except (subject.ContractError, subject.UnverifiableContract) as exc:
        print(f"direct_verify_rejects={exc}")
    else:
        raise AssertionError("direct verify() accepted a certificate over MAX_JSON_ITEMS")

    # Producer may safely refuse the high-item artifact, or emit one that the
    # normal CLI parser can round-trip. It must never emit an unreadable cert.
    try:
        bounded = subject.certify(raw)
    except subject.UnverifiableContract as exc:
        print(f"producer_fails_closed={exc}")
        return
    normal_bytes = subject._certificate_bytes(bounded)
    parsed = subject.parse_json_bytes(normal_bytes + b"\n", "producer certificate")
    assert subject.verify(raw, parsed)["verified"]
    print(f"producer_roundtrip=pass states={len(bounded['states'])} bytes={len(normal_bytes)}")


if __name__ == "__main__":
    main()
