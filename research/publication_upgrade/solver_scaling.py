#!/usr/bin/env python3
"""Repeatable producer/replayer scaling study for exact trace equivalence.

Default command (from the repository root)::

    python3 research/publication_upgrade/solver_scaling.py

The study writes its generated, hashed inputs under ``solver_inputs/`` and a
machine-readable result file next to this script. Use ``plot_solver_scaling.py``
as a separate step to create the SVG figure from that JSON.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _peak_rss_bytes() -> int:
    """Return this worker's OS high-water RSS in bytes (including interpreter)."""
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _graph(calls_per_arm: int) -> dict[str, Any]:
    states: dict[str, Any] = {
        "choose": {"calls": [], "next": {
            "kind": "secret", "guard": {"value": "route"},
            "then": "left0", "else": "right0",
        }},
    }
    for side in ("left", "right"):
        for index in range(calls_per_arm):
            states[f"{side}{index}"] = {
                "calls": [{"model": "m", "template": "ping", "arguments": [],
                           "result": "r"}],
                "next": ({"kind": "goto", "target": f"{side}{index + 1}"}
                         if index + 1 < calls_per_arm else {"kind": "stop"}),
            }
    return {
        "format": "orchlang-request-graph", "version": 1,
        "name": f"solver_equal_symmetric_chain_{calls_per_arm}",
        "chars_per_token": 4,
        "inputs": {"route": {"type": "boolean", "label": "secret"}},
        "models": {"m": {"provider": "mock", "model": "m", "max_tokens": 1}},
        "registers": {"r": {"model": "m"}},
        "entry": "choose", "states": states,
    }


def _kernel() -> dict[str, Any]:
    return {
        "format": "orchlang-finite-outcome-kernel", "version": 1,
        "history_window": 0,
        "defaults": {"m": [{"response": "ok", "output_tokens": 1,
                             "probability": "1"}]},
        "rules": [],
    }


def _prefix_work_stats(report: dict[str, Any]) -> dict[str, int] | None:
    result = report.get("result") or {}
    pairs = result.get("pairs") or []
    closed = report.get("closed_system") or {}
    if not pairs or any(pair.get("status") != "equal" for pair in pairs):
        return None
    edge_counts: dict[str, int] = {}
    for transition in closed.get("transitions", []):
        label = dict(transition["label"])
        label.pop("kind", None)
        key = _json_bytes(label).decode("utf-8")
        edge_counts[key] = edge_counts.get(key, 0) + 1
    dimension = int(closed["state_count"])
    naive_products = shared_products = 0
    naive_units = shared_units = 0
    for pair in pairs:
        prefix_root: dict[str, Any] = {}
        for item in pair.get("basis", []):
            word_keys = [_json_bytes(label).decode("utf-8") for label in item["word"]]
            naive_products += len(word_keys)
            node = prefix_root
            for key in word_keys:
                naive_units += dimension + edge_counts[key]
                child = node.get(key)
                if child is None:
                    child = {}
                    node[key] = child
                    shared_products += 1
                    shared_units += dimension + edge_counts[key]
                node = child
    return {
        "naive_basis_word_products": naive_products,
        "shared_prefix_products": shared_products,
        "avoided_repeated_products": naive_products - shared_products,
        "naive_product_matrix_entry_units": naive_units,
        "shared_product_matrix_entry_units": shared_units,
    }


def _run_worker(args: list[str], timeout_seconds: float,
                implementation_root: Path | None = None) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve())]
    if implementation_root is not None:
        command.extend(["--implementation-root", str(implementation_root.resolve())])
    command.extend(args)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT, capture_output=True, text=True, timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_seconds": timeout_seconds}
    if completed.returncode != 0:
        return {"status": "worker_error", "return_code": completed.returncode,
                "stderr_tail": completed.stderr[-2000:]}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "worker_error", "stderr_tail": completed.stderr[-2000:],
                "stdout_tail": completed.stdout[-2000:]}


def _select_implementation_root(root: Path | None) -> None:
    if root is None:
        return
    audit_path = str((root.resolve() / "audit"))
    if not (Path(audit_path) / "trace_equivalence.py").is_file():
        raise SystemExit(f"implementation root has no audit/trace_equivalence.py: {root}")
    sys.path[:] = [entry for entry in sys.path
                   if Path(entry or ".").resolve() != Path(AUDIT).resolve()]
    sys.path.insert(0, audit_path)


def _worker_producer(graph_path: Path, kernel_path: Path, report_path: Path,
                     implementation_root: Path | None = None) -> int:
    _select_implementation_root(implementation_root)
    from trace_equivalence import analyze

    # Older producers suppress the reason and work counters in UNKNOWN
    # reports. Instrument their meter in this isolated measurement worker so
    # the before/after cap location and deterministic charge remain observable.
    legacy_cap_event: dict[str, Any] | None = None
    legacy_closure_stats: dict[str, int] | None = None
    legacy_meter: Any = None
    module = sys.modules[analyze.__module__]
    meter_type = getattr(module, "_Meter", None)
    if meter_type is not None and int(getattr(module, "VERSION", 1)) < 2:
        original_init = meter_type.__init__

        def remember_meter(meter: Any, *init_args: Any, **init_kwargs: Any) -> None:
            nonlocal legacy_meter
            original_init(meter, *init_args, **init_kwargs)
            legacy_meter = meter

        original_entries = meter_type.entries

        meter_type.__init__ = remember_meter

        def observe_entries(meter: Any, count: int, label: str) -> None:
            nonlocal legacy_cap_event
            before = {"entries_used": meter.entries_used,
                      "work_bytes_used": meter.bytes_used,
                      "max_entries": meter.max_entries,
                      "max_work_bytes": meter.max_bytes}
            try:
                original_entries(meter, count, label)
            except Exception as error:
                if type(error).__name__ == "_Unknown":
                    message = str(error)
                    resource = ("work_bytes" if "byte-work" in message
                                else "matrix_entries" if "matrix-entry" in message
                                else "unknown_meter_limit")
                    legacy_cap_event = {
                        **before, "resource": resource,
                        "operation": label, "attempted_entries": count,
                        "attempted_work_bytes": meter.bytes_used +
                        count * int(getattr(module, "VECTOR_SLOT_WORK_BYTES", 64)),
                        "attempted_matrix_entries": meter.entries_used + count,
                        "message": message,
                    }
                raise
        meter_type.entries = observe_entries

        closure_module = getattr(module, "_closure", None)
        original_builder = getattr(closure_module, "_build_closed_system", None)
        if original_builder is not None:
            def remember_closure(*builder_args: Any, **builder_kwargs: Any) -> Any:
                nonlocal legacy_closure_stats
                system = original_builder(*builder_args, **builder_kwargs)
                legacy_closure_stats = {
                    "state_count": len(system["states"]),
                    "transition_count": int(system["transition_count"]),
                    "closure_work_bytes": int(system["work"].used),
                }
                return system
            closure_module._build_closed_system = remember_closure

    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    graph, kernel = json.loads(graph_raw), json.loads(kernel_raw)
    start = time.perf_counter()
    report = analyze(graph, kernel, {}, [{"route": False}, {"route": True}],
                     raw_graph=graph_raw, raw_kernel=kernel_raw)
    elapsed = time.perf_counter() - start
    encoded = _json_bytes(report) + b"\n"
    report_path.write_bytes(encoded)
    closed = report.get("closed_system") or {}
    result = report.get("result") or {}
    pairs = result.get("pairs") or []
    telemetry = report.get("telemetry") or {}
    print(json.dumps({
        "status": report["status"],
        "diagnostics": report.get("diagnostics"),
        "analysis_seconds": elapsed,
        "peak_rss_bytes": _peak_rss_bytes(),
        "state_count": closed.get("state_count", telemetry.get("closed_state_count")),
        "transition_count": closed.get("transition_count", telemetry.get("transition_count")),
        "instrumented_closure": legacy_closure_stats,
        "instrumented_meter": ({
            "matrix_entries_used": legacy_meter.entries_used,
            "work_bytes_used": legacy_meter.bytes_used,
            "max_matrix_entries": legacy_meter.max_entries,
            "max_work_bytes": legacy_meter.max_bytes,
        } if legacy_meter is not None else None),
        "rank": pairs[0].get("rank") if pairs and pairs[0].get("status") == "equal" else None,
        "report_bytes": len(encoded),
        "telemetry": report.get("telemetry"),
        "prefix_work_stats": _prefix_work_stats(report),
        "legacy_cap_event": legacy_cap_event,
    }, sort_keys=True, allow_nan=False))
    return 0


def _worker_replay(report_path: Path, graph_path: Path, kernel_path: Path,
                   implementation_root: Path | None = None) -> int:
    _select_implementation_root(implementation_root)
    from replay_trace_equivalence import replay_report

    start = time.perf_counter()
    report = replay_report(report_path, graph_path, kernel_path)
    elapsed = time.perf_counter() - start
    print(json.dumps({
        "status": report["status"], "decision": report.get("decision"),
        "diagnostic": report.get("diagnostic"),
        "replay_seconds": elapsed,
        "peak_rss_bytes": _peak_rss_bytes(),
        "state_count": report.get("state_count"),
        "transition_count": report.get("transition_count"),
        "independent_matrix_entries": report.get("independent_matrix_entries"),
        "independent_work_bytes": report.get("independent_work_bytes"),
        "verified_pairs": report.get("pair_count"),
    }, sort_keys=True, allow_nan=False))
    return 0


def _median(values: list[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _summarize(size: int, samples: list[dict[str, Any]]) -> dict[str, Any]:
    producers = [sample["producer"] for sample in samples]
    replays = [sample["replay"] for sample in samples]
    verified_replays = [row for row in replays if row.get("status") == "verified"]
    return {
        "calls_per_arm": size,
        "repetitions": len(samples),
        "producer_status_counts": {
            status: sum(row.get("status") == status for row in producers)
            for status in sorted({row.get("status") for row in producers})
        },
        "replay_status_counts": {
            status: sum(row.get("status") == status for row in replays)
            for status in sorted({row.get("status") for row in replays})
        },
        "state_count": next((row.get("state_count") for row in producers
                              if row.get("state_count") is not None), None),
        "transition_count": next((row.get("transition_count") for row in producers
                                   if row.get("transition_count") is not None), None),
        "median_rank": _median([row.get("rank") for row in producers]),
        "producer_seconds_median": _median([row.get("analysis_seconds") for row in producers]),
        "producer_seconds_min": min((row["analysis_seconds"] for row in producers
                                      if "analysis_seconds" in row), default=None),
        "producer_seconds_max": max((row["analysis_seconds"] for row in producers
                                      if "analysis_seconds" in row), default=None),
        "replay_seconds_median": _median([row.get("replay_seconds") for row in verified_replays]),
        "replay_seconds_min": min((row["replay_seconds"] for row in verified_replays
                                   if "replay_seconds" in row), default=None),
        "replay_seconds_max": max((row["replay_seconds"] for row in verified_replays
                                   if "replay_seconds" in row), default=None),
        "producer_peak_rss_bytes_median": _median([row.get("peak_rss_bytes") for row in producers]),
        "replay_peak_rss_bytes_median": _median(
            [row.get("peak_rss_bytes") for row in verified_replays]
        ),
        "report_bytes_median": _median([row.get("report_bytes") for row in producers]),
        "independent_work_bytes_median": _median(
            [row.get("independent_work_bytes") for row in replays]
        ),
        "naive_basis_word_products_median": _median([
            (row.get("prefix_work_stats") or {}).get("naive_basis_word_products")
            for row in producers
        ]),
        "shared_prefix_products_median": _median([
            (row.get("prefix_work_stats") or {}).get("shared_prefix_products")
            for row in producers
        ]),
        "naive_product_matrix_entry_units_median": _median([
            (row.get("prefix_work_stats") or {}).get("naive_product_matrix_entry_units")
            for row in producers
        ]),
        "shared_product_matrix_entry_units_median": _median([
            (row.get("prefix_work_stats") or {}).get("shared_product_matrix_entry_units")
            for row in producers
        ]),
    }


def _study(args: argparse.Namespace) -> int:
    sizes = [int(item) for item in args.sizes.split(",") if item]
    if not sizes or any(size < 2 or size > 512 for size in sizes):
        raise SystemExit("--sizes must be comma-separated integers in [2,512]")
    if args.repetitions < 5:
        raise SystemExit("publication study requires at least five measured repetitions")
    if not 0 <= args.warmups <= 10:
        raise SystemExit("--warmups must be in [0,10]")

    output_path = args.output.resolve()
    input_dir = args.input_dir.resolve()
    implementation_root = args.implementation_root.resolve() if args.implementation_root else ROOT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    kernel_path = input_dir / "scale.kernel.json"
    kernel_raw = _json_bytes(_kernel()) + b"\n"
    kernel_path.write_bytes(kernel_raw)

    all_samples = []
    summaries = []
    for size in sizes:
        graph_path = input_dir / f"scale_{size}.graph.json"
        graph_raw = _json_bytes(_graph(size)) + b"\n"
        graph_path.write_bytes(graph_raw)
        samples: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="orchlang-scale-") as temp_name:
            temp = Path(temp_name)
            for repetition in range(args.warmups + args.repetitions):
                report_path = temp / f"scale_{size}_{repetition}.report.json"
                producer = _run_worker([
                    "--worker-producer", str(graph_path), str(kernel_path),
                    str(report_path),
                ], args.timeout_seconds, implementation_root)
                replay = ({"status": "not_run"} if producer.get("status") in
                          ("timeout", "worker_error") or not report_path.exists()
                          else _run_worker([
                              "--worker-replay", str(report_path), str(graph_path),
                              str(kernel_path),
                          ], args.timeout_seconds, implementation_root))
                if repetition >= args.warmups:
                    sample = {"repetition": repetition - args.warmups,
                              "producer": producer, "replay": replay}
                    samples.append(sample)
                    all_samples.append({"calls_per_arm": size, **sample})
        summaries.append(_summarize(size, samples))

    source_hashes = {}
    for filename in ("trace_equivalence.py", "replay_trace_equivalence.py",
                     "stochastic_bisimulation.py", "orchgraph.py",
                     "probabilistic_channels.py"):
        candidate = implementation_root / "audit" / filename
        if candidate.is_file():
            source_hashes[filename] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    worker_source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    document = {
        "format": "orchlang-trace-equivalence-solver-scaling",
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "peak_rss_measurement": "worker process OS high-water RSS including Python runtime; bytes",
        },
        "implementation": {
            "name": args.implementation_name,
            "source_sha256": source_hashes,
            "study_worker_sha256": worker_source_hash,
        },
        "study": {
            "family": "symmetric deterministic call chains with identical ordered usage labels",
            "semantics": "two secret routes select mirrored arms; every finite usage word agrees under a point-mass success kernel",
            "calls_per_arm": sizes,
            "warmups_per_size": args.warmups,
            "measured_repetitions_per_size": args.repetitions,
            "timeout_seconds_per_worker": args.timeout_seconds,
            "caps": {"max_states": 10000, "max_work_bytes": 67108864,
                     "max_matrix_entries": 10000000, "max_rational_bits": 8192},
            "limitations": [
                "one synthetic symmetric family; it does not characterize real workflow distributions",
                "wall time and process RSS are environment-specific; exact analysis counters are deterministic work estimates",
                "producer and replayer runs include Python interpreter startup only in peak RSS, not in reported analysis/replay seconds",
            ],
        },
        "inputs": {
            "kernel_path": str(kernel_path.relative_to(ROOT)),
            "kernel_sha256": hashlib.sha256(kernel_raw).hexdigest(),
            "graphs": [{"calls_per_arm": size,
                        "path": str((input_dir / f"scale_{size}.graph.json").relative_to(ROOT)),
                        "sha256": hashlib.sha256(
                            (input_dir / f"scale_{size}.graph.json").read_bytes()
                        ).hexdigest(),
                        "bytes": (input_dir / f"scale_{size}.graph.json").stat().st_size}
                       for size in sizes],
        },
        "summaries": summaries,
        "samples": all_samples,
    }
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2,
                                      sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="2,8,16,32,64,128,256")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "research/publication_upgrade/solver_scaling.json")
    parser.add_argument("--input-dir", type=Path,
                        default=ROOT / "research/publication_upgrade/solver_inputs")
    parser.add_argument("--implementation-root", type=Path,
                        help="repository/archive root whose audit modules the worker imports")
    parser.add_argument("--implementation-name", default="optimized working tree")
    parser.add_argument("--worker-producer", nargs=3, metavar=("GRAPH", "KERNEL", "REPORT"))
    parser.add_argument("--worker-replay", nargs=3, metavar=("REPORT", "GRAPH", "KERNEL"))
    args = parser.parse_args(argv)
    if args.worker_producer:
        return _worker_producer(*(Path(value) for value in args.worker_producer),
                                implementation_root=args.implementation_root)
    if args.worker_replay:
        return _worker_replay(*(Path(value) for value in args.worker_replay),
                              implementation_root=args.implementation_root)
    return _study(args)


if __name__ == "__main__":
    raise SystemExit(main())
