#!/usr/bin/env python3
"""Seeded property probes for the experimental request-graph checker.

This deliberately uses ``orchgraph.reference_run`` from the producer module.
It checks consistency between the producer's accepted product result and its
own seeded value-level semantics; it is not an independent interpreter or
proof. The separate ``replay_graph_certificate.py`` check is reported apart.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCER_PATH = Path(__file__).with_name("orchgraph.py")
DEFAULT_SEED = 8_675_309
DEFAULT_CASES = 3_000
DEFAULT_MAX_NODES = 10_000
DEFAULT_MAX_CALLS = 20
DEFAULT_ORACLE_SEED = 8_675_309


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_producer():
    spec = importlib.util.spec_from_file_location("orchgraph_under_probe", PRODUCER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load producer module: {PRODUCER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_graph(module: Any, rng: random.Random, index: int) -> dict[str, Any]:
    state_count = rng.randint(2, 5)
    names = [f"s{state}" for state in range(state_count)]
    states: dict[str, Any] = {}
    for state in names:
        calls = []
        for _ in range(rng.randint(0, 2)):
            arguments = []
            if rng.random() < 0.55:
                arguments = [{"literal": rng.choice(["a", "b", "c", ""])}]
            calls.append({
                "model": "m",
                "template": rng.choice(["A", "B", "C"]),
                "arguments": arguments,
                "result": rng.choice(["r", "q"]),
            })
        decision = rng.random()
        if decision < 0.34:
            next_state = {
                "kind": "secret", "guard": {"value": "h"},
                "then": rng.choice(names), "else": rng.choice(names),
            }
        elif decision < 0.64:
            next_state = {
                "kind": "public", "guard": {"value": "p"},
                "then": rng.choice(names), "else": rng.choice(names),
            }
        elif decision < 0.84:
            next_state = {"kind": "goto", "target": rng.choice(names)}
        else:
            next_state = {"kind": "stop"}
        states[state] = {"calls": calls, "next": next_state}

    return {
        "format": module.FORMAT,
        "version": 1,
        "name": f"g{index}",
        "inputs": {
            "h": {"type": "boolean", "label": "secret"},
            "p": {"type": "boolean", "label": "public"},
        },
        "registers": {"r": {"model": "m"}, "q": {"model": "m"}},
        "models": {"m": {"provider": "p", "model": "m", "max_tokens": 4}},
        "states": states,
        "entry": names[0],
    }


def event_projections(run: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    requests = []
    usage = []
    for event in run["trace"]:
        requests.append((
            event["contract"], event["ordinal"], event["template"],
            tuple(event["arguments"]),
        ))
        usage.append((event["input_tokens"], event["output_tokens"]))
    return requests, usage


def canonical_hash(graph: dict[str, Any]) -> str:
    raw = json.dumps(graph, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return sha256(raw)


def run(seed: int = DEFAULT_SEED, cases: int = DEFAULT_CASES,
        max_nodes: int = DEFAULT_MAX_NODES, max_calls: int = DEFAULT_MAX_CALLS) -> dict[str, Any]:
    if cases < 1 or max_nodes < 1 or max_calls < 1:
        raise ValueError("cases, max_nodes, and max_calls must be positive")
    module = load_producer()
    rng = random.Random(seed)
    counts = {
        "generated": cases,
        "constructor_rejected": 0,
        "checker_accepted": 0,
        "checker_rejected": 0,
        "checker_unknown": 0,
        "accepted_with_probe_exception": 0,
        "accepted_without_probe_exception": 0,
        "probe_runs": 0,
        "paired_store_comparisons": 0,
        "distinct_secret_store_comparisons": 0,
        "request_equal_comparisons": 0,
        "usage_equal_comparisons": 0,
        "stop_or_truncation_equal_comparisons": 0,
        "complete_observation_equal_comparisons": 0,
        "accepted_mismatches": 0,
        "both_runs_truncated_comparisons": 0,
        "one_run_truncated_comparisons": 0,
        "neither_run_truncated_comparisons": 0,
    }
    manifest: list[dict[str, Any]] = []

    for index in range(cases):
        graph_document = generate_graph(module, rng, index)
        row: dict[str, Any] = {
            "case": index,
            "graph_sha256": canonical_hash(graph_document),
        }
        try:
            graph = module.Graph(graph_document)
        except Exception as error:  # unsupported graphs are recorded fail-closed
            counts["constructor_rejected"] += 1
            row.update(
                status="constructor_rejected",
                reason=type(error).__name__,
                diagnostic=str(error)[:240],
            )
            manifest.append(row)
            continue

        try:
            report = module.check(graph, max_nodes=max_nodes)
        except Exception as error:
            counts["checker_rejected"] += 1
            row.update(
                status="checker_exception",
                reason=type(error).__name__,
                diagnostic=str(error)[:240],
            )
            manifest.append(row)
            continue

        status = report.get("status")
        row["status"] = status
        if status not in ("accepted", "rejected", "unknown"):
            counts["checker_rejected"] += 1
            row.update(status="checker_exception", reason="invalid status")
            manifest.append(row)
            continue
        counts[f"checker_{status}"] += 1
        if status != "accepted":
            if report.get("diagnostic"):
                row["diagnostic"] = report["diagnostic"][:240]
            manifest.append(row)
            continue

        # Two public values x two secret values. We compare every ordered pair
        # of stores that has the same public value, including equal-secret
        # pairs; distinct-secret comparisons are also reported separately.
        outputs: dict[tuple[bool, bool], dict[str, Any] | Exception] = {}
        for public_value, secret_value in itertools.product((False, True), repeat=2):
            counts["probe_runs"] += 1
            store = {"h": secret_value, "p": public_value}
            try:
                outputs[(public_value, secret_value)] = module.reference_run(
                    graph, store, seed=DEFAULT_ORACLE_SEED, max_calls=max_calls
                )
            except Exception as error:
                outputs[(public_value, secret_value)] = error

        run_error = any(isinstance(value, Exception) for value in outputs.values())
        if run_error:
            counts["accepted_with_probe_exception"] += 1
            reasons = sorted({type(value).__name__ for value in outputs.values()
                              if isinstance(value, Exception)})
            row.update(probe="exception", exception_types=reasons)
            # A runtime probe failure is retained as a fail-closed observation;
            # it is not counted as an accepted trace equality.
            manifest.append(row)
            continue

        counts["accepted_without_probe_exception"] += 1
        mismatches = 0
        row_requests_equal = 0
        row_usage_equal = 0
        row_stop_equal = 0
        row_complete_equal = 0
        row_pairs = 0
        row_distinct_secret_pairs = 0
        row_truncated_pairs = 0
        for public_value in (False, True):
            for left_secret, right_secret in itertools.product((False, True), repeat=2):
                left = outputs[(public_value, left_secret)]
                right = outputs[(public_value, right_secret)]
                assert isinstance(left, dict) and isinstance(right, dict)
                row_pairs += 1
                counts["paired_store_comparisons"] += 1
                if left_secret != right_secret:
                    row_distinct_secret_pairs += 1
                    counts["distinct_secret_store_comparisons"] += 1

                left_requests, left_usage = event_projections(left)
                right_requests, right_usage = event_projections(right)
                requests_equal = left_requests == right_requests
                usage_equal = left_usage == right_usage
                completion_equal = (
                    left.get("stopped") == right.get("stopped")
                    and left.get("truncated_at_calls") == right.get("truncated_at_calls")
                )
                observation_equal = (
                    requests_equal and usage_equal and completion_equal
                    and [event.get("response") for event in left["trace"]]
                    == [event.get("response") for event in right["trace"]]
                )
                row_requests_equal += int(requests_equal)
                row_usage_equal += int(usage_equal)
                row_stop_equal += int(completion_equal)
                row_complete_equal += int(observation_equal)
                counts["request_equal_comparisons"] += int(requests_equal)
                counts["usage_equal_comparisons"] += int(usage_equal)
                counts["stop_or_truncation_equal_comparisons"] += int(completion_equal)
                counts["complete_observation_equal_comparisons"] += int(observation_equal)
                if left.get("truncated_at_calls") is not None and right.get("truncated_at_calls") is not None:
                    row_truncated_pairs += 1
                    counts["both_runs_truncated_comparisons"] += 1
                elif left.get("truncated_at_calls") is not None or right.get("truncated_at_calls") is not None:
                    counts["one_run_truncated_comparisons"] += 1
                else:
                    counts["neither_run_truncated_comparisons"] += 1
                if not observation_equal:
                    mismatches += 1
                    counts["accepted_mismatches"] += 1

        row.update(
            probe="checked",
            paired_store_comparisons=row_pairs,
            distinct_secret_store_comparisons=row_distinct_secret_pairs,
            request_equal_comparisons=row_requests_equal,
            usage_equal_comparisons=row_usage_equal,
            stop_or_truncation_equal_comparisons=row_stop_equal,
            complete_observation_equal_comparisons=row_complete_equal,
            both_runs_truncated_comparisons=row_truncated_pairs,
            accepted_mismatches=mismatches,
        )
        manifest.append(row)

    return {
        "format": "orchlang-graph-adversarial-property-probe",
        "version": 1,
        "seed": seed,
        "generator": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256(Path(__file__).read_bytes()),
            "python_version": sys.version.split()[0],
            "prng": "random.Random (MT19937)",
        },
        "producer": {
            "path": str(PRODUCER_PATH.resolve().relative_to(ROOT)),
            "sha256": sha256(PRODUCER_PATH.read_bytes()),
            "source": "same audit/orchgraph.py module as check() and reference_run(); not independent semantics",
        },
        "oracle_probe": {
            "protocol_seed": DEFAULT_ORACLE_SEED,
            "max_nodes": max_nodes,
            "max_calls_per_run": max_calls,
            "input_domain": {
                "secret_boolean": [False, True],
                "shared_public_boolean": [False, True],
            },
            "pairing": "all ordered secret-store pairs for each equal shared-public value",
            "observation": "complete request descriptor, input/output usage, response bytes, and stop/truncation status",
            "limitations": [
                "property probe uses producer reference_run and is not an independent interpreter",
                "finite generated graph family and finite 20-call prefixes",
                "no provider, concurrency, exception, or source-to-graph claim",
                "separate certificate replayer is assessed independently",
            ],
        },
        "counts": counts,
        "case_hash_manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.seed, args.cases, args.max_nodes, args.max_calls)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="")
    print(encoded, end="")
    return 0 if report["counts"]["accepted_mismatches"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
