"""Run one replay-accepted version-1 request graph on LangGraph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

try:
    from .backend import BackendError, execute_graph
    from replay_graph_certificate import ReplayError, strict_json
except ImportError:  # direct `python integrations/langgraph/cli.py ...` use
    root = Path(__file__).resolve().parents[2]
    for directory in (root, root / "audit"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from integrations.langgraph.backend import BackendError, execute_graph
    from replay_graph_certificate import ReplayError, strict_json


def _load_store(args: argparse.Namespace) -> dict[str, Any]:
    if args.store_json is not None:
        raw = args.store_json.encode("utf-8")
    else:
        raw = args.store_file.read_bytes()
    value = strict_json(raw, "runtime store")
    if not isinstance(value, dict):
        raise BackendError("runtime store JSON must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, help="version-1 request graph JSON")
    parser.add_argument("certificate", type=Path, help="accepted graph certificate JSON")
    stores = parser.add_mutually_exclusive_group(required=True)
    stores.add_argument("--store-json", help="runtime input object as JSON text")
    stores.add_argument("--store-file", type=Path, help="runtime input object JSON file")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--max-control-steps", type=int, default=1_000_000)
    parser.add_argument(
        "--recursion-limit", type=int,
        help="LangGraph super-step limit; defaults to the graph control cap plus a small cushion",
    )
    parser.add_argument("--output", type=Path, help="write full execution JSON to this path")
    args = parser.parse_args(argv)

    try:
        result = execute_graph(
            args.graph.read_bytes(),
            args.certificate.read_bytes(),
            _load_store(args),
            args.seed,
            max_calls=args.max_calls,
            max_control_steps=args.max_control_steps,
            recursion_limit=args.recursion_limit,
        )
        encoded = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8", newline="")
        else:
            sys.stdout.write(encoded)
        return 0 if result.status in ("stopped", "truncated") else 2
    except (BackendError, ReplayError, OSError, UnicodeError, ValueError, TypeError) as error:
        print(f"LangGraph execution rejected or failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
