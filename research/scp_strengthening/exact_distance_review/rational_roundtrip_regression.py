#!/usr/bin/env python3
"""Regression for certificate rationals wider than input-rational tokens.

This public synthetic contract has valid 47-digit input denominators and a
93-digit exact prefix-mass denominator after two transitions. Arithmetic stays
well below the module's 4096-bit intermediate bound. The producer and replay
must agree on the accepted certificate-rational budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "exact_uncertain_distance"))
import exact_uncertain_distance as subject  # noqa: E402


def one_a(scenario: str, history: list[str], denominator: int) -> dict[str, object]:
    return {
        "scenario": scenario,
        "history": history,
        "generators": [
            {
                "A": f"1/{denominator}",
                subject.STOP: f"{denominator - 1}/{denominator}",
            }
        ],
    }


def stop_at_aa(scenario: str) -> dict[str, object]:
    return {
        "scenario": scenario,
        "history": ["A", "A"],
        "generators": [{"A": "0", subject.STOP: "1"}],
    }


def contract() -> dict[str, object]:
    d1 = 10**46 + 33
    d2 = 10**46 + 79
    assert len(str(d1)) == len(str(d2)) == 47
    return {
        "schema": subject.SCHEMA,
        "alphabet": ["A", subject.STOP],
        "horizon": 3,
        "require_stop_by_horizon": True,
        "rows": [
            one_a("left", [], d1),
            one_a("right", [], d1),
            one_a("left", ["A"], d2),
            one_a("right", ["A"], d2),
            stop_at_aa("left"),
            stop_at_aa("right"),
        ],
    }


def main() -> None:
    raw = contract()
    subject.parse_contract(raw)
    certificate = subject.certify(raw)
    deepest = next(state for state in certificate["states"] if state["history"] == ["A", "A"])
    denominator_digits = len(deepest["left_mass"].split("/")[1])
    print(f"states={len(certificate['states'])} deepest_mass_denominator_digits={denominator_digits}")
    result = subject.verify(raw, certificate)
    print(f"verify={result['verified']} tv={result['worst_case_tv']}")


if __name__ == "__main__":
    main()
