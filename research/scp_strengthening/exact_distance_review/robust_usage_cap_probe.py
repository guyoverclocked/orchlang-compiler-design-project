#!/usr/bin/env python3
"""Recheck the repaired robust_usage certificate tree-item cap.

The synthetic 1000-prefix contract previously produced a certificate under
the 16 MB byte cap that exceeded MAX_JSON_ITEMS and therefore failed replay.
The current producer must reject it before returning an artifact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "robust_usage"))
import robust_usage as subject  # noqa: E402


def tree_items(value: object) -> int:
    pending = [value]
    count = 0
    while pending:
        item = pending.pop()
        count += 1
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return count


def contract(prefix_rows: int = 1000) -> dict[str, object]:
    alphabet = ["A", "B", subject.STOP]
    center = {"A": "1/2", "B": "1/2", subject.STOP: "0"}
    rows = [
        {
            "history": ["A"] * depth,
            "left": {"center": center, "radius": "0"},
            "right": {"center": center, "radius": "0"},
        }
        for depth in range(prefix_rows)
    ]
    return {
        "schema": subject.SCHEMA,
        "horizon": prefix_rows + 2,
        "alphabet": alphabet,
        "require_stop_by_horizon": False,
        "rows": rows,
    }


def main() -> None:
    raw = contract()
    raw_bytes = len(json.dumps(raw, separators=(",", ":")).encode("utf-8"))
    print(f"raw_items={tree_items(raw)} raw_compact_bytes={raw_bytes}")
    try:
        subject.certify(raw)
    except subject.UnverifiableContract as exc:
        if "item limit" not in str(exc):
            raise
        print(f"producer_fails_closed={exc}")
    else:
        raise AssertionError("producer returned the previously oversized certificate")


if __name__ == "__main__":
    main()
