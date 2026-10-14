#!/usr/bin/env python3
"""Reproduce adversarial edge cases in the reviewed robust-usage prototype.

Run from any directory with Python 3:

    python3 reproduce_checker_edges.py

This script imports, but does not modify, ../robust_usage/robust_usage.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "robust_usage"))
import robust_usage as ru  # noqa: E402


def center(**entries: str) -> dict[str, str]:
    return {"__STOP__": "0", "a": "0", **entries}


def paired(history: list[str], left: dict[str, str], right: dict[str, str]) -> dict:
    return {
        "history": history,
        "left": {"center": left, "radius": "0"},
        "right": {"center": right, "radius": "0"},
    }


def make_contract(horizon: int, rows: list[dict], alphabet=None) -> dict:
    return {
        "schema": ru.SCHEMA,
        "horizon": horizon,
        "alphabet": alphabet or ["__STOP__", "a"],
        "require_stop_by_horizon": False,
        "rows": rows,
    }


def main() -> None:
    duplicate_path = HERE / "duplicate_keys_contract.json"
    duplicate_raw = ru._load_json(str(duplicate_path))
    duplicate_parsed = ru.parse_contract(duplicate_raw)
    normalized = make_contract(1, [], alphabet=["__STOP__"])
    print("duplicate-key JSON:", duplicate_parsed.horizon, duplicate_raw["schema"])
    print("duplicate-key digest equals clean normalized contract:",
          duplicate_parsed.digest == ru.parse_contract(normalized).digest)

    # JSON distinguishes booleans from integers, but replay relies on Python's
    # equality where True == 1. A changed certificate field therefore passes.
    stop = {"__STOP__": "1", "a": "0"}
    one = make_contract(1, [paired([], stop, stop)])
    certificate = ru.certify(one)
    certificate["horizon"] = True
    accepted, _ = ru.replay(one, certificate)
    print("replay accepts horizon=true in place of integer 1:", accepted)

    # max_nodes=1 bounds recursive trie visits here, but not the horizon loop
    # used to construct per-level summaries after the root is already unknown.
    huge_horizon = make_contract(2_000_000, [])
    started = time.perf_counter()
    result = ru.certify(huge_horizon, max_nodes=1)
    elapsed = time.perf_counter() - started
    print("missing-root certificate with max_nodes=1:", result["tv_upper_bound"],
          f"elapsed={elapsed:.3f}s for horizon=2,000,000")

    # A single positive-support chain exceeds Python's recursion limit even
    # though the declared visit budget is generous and finite.
    horizon = 1_100
    only_a = center(a="1")
    chain_rows = [paired(["a"] * depth, only_a, only_a)
                  for depth in range(horizon)]
    chain = make_contract(horizon, chain_rows)
    try:
        ru.certify(chain, max_nodes=10_000)
    except RecursionError as error:
        print("long valid horizon raises uncaught RecursionError:", type(error).__name__)
    else:
        print("long valid horizon completed")

    # A lone escaped UTF-16 surrogate is accepted by json.load but cannot be
    # encoded by parse_contract's canonical JSON digest path.
    unicode_raw = json.loads(
        '{"schema":"orchlang.robust-usage/v1","horizon":1,'
        '"alphabet":["__STOP__","\\ud800"],'
        '"require_stop_by_horizon":false,"rows":[]}'
    )
    try:
        ru.parse_contract(unicode_raw)
    except UnicodeEncodeError as error:
        print("escaped lone surrogate raises uncaught UnicodeEncodeError:", type(error).__name__)
    else:
        print("lone surrogate accepted")


if __name__ == "__main__":
    main()
