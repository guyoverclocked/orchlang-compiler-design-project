#!/usr/bin/env python3
"""Run the frozen structured scalability matrix in isolated worker processes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
STUDY_DIR = ROOT / "research/scp_strengthening/scalability"
OUT = ROOT / "output/scp_strengthening/scalability"
MANIFEST = OUT / "frozen_inputs.json"
PREREG = STUDY_DIR / "PREREGISTRATION.md"
CURRENT_ROOT = ROOT
PREOPT_REVISION = "5aa4ebc669a3fbae72d9a605be250624fd0bcbf5"
PREOPT_SAMPLE = {
    "secret_fanout_8",
    "mutable_registers_4",
    "productive_cycle_4",
    "observation_alphabet_8",
    "retained_history_3",
    "history_conditioned_unequal",
    "bisim_inconclusive_exact_equal",
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _load_case(case_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    case = next(row for row in frozen["cases"] if row["case_id"] == case_id)
    graph_path = ROOT / case["graph_path"]
    kernel_path = ROOT / case["kernel_path"]
    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    if _sha(graph_raw) != case["graph_sha256"] or _sha(kernel_raw) != case["kernel_sha256"]:
        raise RuntimeError(f"frozen input hash mismatch for {case_id}")
    if _sha(graph_raw + b"\0" + kernel_raw) != case["input_sha256"]:
        raise RuntimeError(f"paired input hash mismatch for {case_id}")
    return case, json.loads(graph_raw), json.loads(kernel_raw)


def _select_implementation(root: Path) -> None:
    audit = str((root / "audit").resolve())
    current = str((ROOT / "audit").resolve())
    sys.path[:] = [entry for entry in sys.path
                   if Path(entry or ".").resolve() != Path(current)]
    sys.path.insert(0, audit)


def _write_report(path: Path, report: dict[str, Any]) -> tuple[int, int]:
    compact = _json_bytes(report)
    pretty = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True,
                        allow_nan=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty)
    return len(compact), len(pretty)


def _exact_producer(case: dict[str, Any], graph: dict[str, Any], kernel: dict[str, Any],
                    graph_path: Path, kernel_path: Path, report_path: Path,
                    implementation_root: Path) -> dict[str, Any]:
    _select_implementation(implementation_root)
    from trace_equivalence import analyze

    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    start = time.perf_counter()
    report = analyze(graph, kernel, case["public_store"], case["secret_scenarios"],
                     max_states=case["max_states"], raw_graph=graph_raw,
                     raw_kernel=kernel_raw)
    seconds = time.perf_counter() - start
    compact_bytes, pretty_bytes = _write_report(report_path, report)
    closed = report.get("closed_system") or {}
    telemetry = report.get("telemetry") or {}
    result = report.get("result") or {}
    pairs = result.get("pairs") or []
    return {
        "status": report.get("status"),
        "analysis_seconds": seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "certificate_bytes_compact": compact_bytes,
        "report_file_bytes": pretty_bytes,
        "diagnostics": report.get("diagnostics"),
        "state_count": closed.get("state_count", telemetry.get("closed_state_count")),
        "transition_count": closed.get("transition_count", telemetry.get("transition_count")),
        "label_count": len(report.get("label_alphabet") or []) or telemetry.get("label_count"),
        "pair_statuses": [pair.get("status") for pair in pairs],
        "pair_ranks": [pair.get("rank") for pair in pairs],
        "finite_witness_lengths": [len(pair.get("counterexample", {}).get("word", []))
                                   for pair in pairs if pair.get("counterexample")],
        "bounded_work": {
            "matrix_entries_used": telemetry.get("matrix_entries_used"),
            "work_bytes_used_before_serialization": telemetry.get("work_bytes_used_before_serialization"),
            "max_rational_bits_observed": telemetry.get("max_rational_bits_observed"),
            "closed_state_count": telemetry.get("closed_state_count"),
            "transition_count": telemetry.get("transition_count"),
            "label_count": telemetry.get("label_count"),
            "diagnostic_reason": (report.get("diagnostics") or {}).get("reason"),
            "diagnostic_phase": (report.get("diagnostics") or {}).get("phase"),
        },
    }


def _exact_replay(case: dict[str, Any], report_path: Path, graph_path: Path,
                  kernel_path: Path, implementation_root: Path) -> dict[str, Any]:
    _select_implementation(implementation_root)
    from replay_trace_equivalence import replay_report

    start = time.perf_counter()
    result = replay_report(report_path, graph_path, kernel_path,
                           expected_public_store=case["public_store"],
                           expected_secret_scenarios=case["secret_scenarios"])
    seconds = time.perf_counter() - start
    return {
        "status": result.get("status"),
        "decision": result.get("decision"),
        "replay_seconds": seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "diagnostic": result.get("diagnostic"),
        "state_count": result.get("state_count"),
        "transition_count": result.get("transition_count"),
        "verified_pairs": result.get("verified_pairs"),
        "bounded_work": {
            "independent_matrix_entries": result.get("independent_matrix_entries"),
            "independent_work_bytes": result.get("independent_work_bytes"),
            "state_count": result.get("state_count"),
            "transition_count": result.get("transition_count"),
            "pair_count": result.get("pair_count"),
            "verifier_limits": result.get("verifier_limits"),
        },
    }


def _bisim_producer(case: dict[str, Any], graph: dict[str, Any], kernel: dict[str, Any],
                    graph_path: Path, kernel_path: Path, report_path: Path,
                    implementation_root: Path) -> dict[str, Any]:
    _select_implementation(implementation_root)
    import stochastic_bisimulation as bisim

    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    start = time.perf_counter()
    report = bisim.analyze(graph, kernel, case["public_store"],
                           case["secret_scenarios"], max_states=case["max_states"])
    seconds = time.perf_counter() - start
    # Match the producer CLI: API certificates default to canonicalized input
    # hashes, while replay binds the frozen source bytes exactly.
    report.setdefault("hashes", {})["graph_sha256"] = _sha(graph_raw)
    report.setdefault("hashes", {})["kernel_sha256"] = _sha(kernel_raw)
    compact_bytes, pretty_bytes = _write_report(report_path, report)
    closed = report.get("closed_system") or {}
    stats = report.get("analysis_stats") or {}
    return {
        "status": report.get("status"),
        "analysis_seconds": seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "certificate_bytes_compact": compact_bytes,
        "report_file_bytes": pretty_bytes,
        "reason": report.get("reason"),
        "state_count": closed.get("state_count"),
        "transition_count": closed.get("transition_count"),
        "partition_block_count": len((report.get("partition_certificate") or {}).get("blocks") or []),
        "bounded_work": {
            "state_count": closed.get("state_count"),
            "transition_count": closed.get("transition_count"),
            "expanded_states": stats.get("expanded_states"),
            "call_outcome_transitions_before_merge": stats.get("call_outcome_transitions_before_merge"),
            "byte_work_estimate": stats.get("byte_work_estimate"),
            "max_states": stats.get("max_states"),
            "max_work_bytes": stats.get("max_work_bytes"),
            "max_state_key_bytes": stats.get("max_state_key_bytes"),
            "rational_precision_limit_bits": stats.get("rational_precision_limit_bits"),
        },
    }


def _bisim_replay(case: dict[str, Any], report_path: Path, graph_path: Path,
                  kernel_path: Path, implementation_root: Path) -> dict[str, Any]:
    _select_implementation(implementation_root)
    from replay_stochastic_certificate import replay_certificate

    start = time.perf_counter()
    result = replay_certificate(report_path, graph_path, kernel_path,
                                expected_public_store=case["public_store"],
                                expected_secret_scenarios=case["secret_scenarios"])
    seconds = time.perf_counter() - start
    return {
        "status": result.get("status"),
        "decision": result.get("decision"),
        "replay_seconds": seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "diagnostic": result.get("diagnostic"),
        "state_count": result.get("state_count"),
        "transition_count": result.get("transition_count"),
        "certificate_status": result.get("certificate_status"),
        "equal_laws_claim": result.get("equal_laws_claim"),
        "partition_block_count": result.get("partition_block_count"),
        "bounded_work": {
            "state_count": result.get("state_count"),
            "transition_count": result.get("transition_count"),
            "independent_outcomes_expanded": result.get("independent_outcomes_expanded"),
            "independent_control_steps": result.get("independent_control_steps"),
            "independent_work_bytes": result.get("independent_work_bytes"),
            "partition_block_count": result.get("partition_block_count"),
            "verifier_limits": result.get("verifier_limits"),
        },
    }


def _worker(argv: list[str]) -> int:
    if len(argv) != 7:
        raise SystemExit("worker expects OP CASE_ID IMPLEMENTATION_ROOT GRAPH KERNEL REPORT")
    operation, case_id, implementation, graph_s, kernel_s, report_s, _spare = argv
    implementation_root = Path(implementation).resolve()
    graph_path, kernel_path, report_path = Path(graph_s), Path(kernel_s), Path(report_s)
    case, graph, kernel = _load_case(case_id)
    try:
        if operation == "exact_producer":
            row = _exact_producer(case, graph, kernel, graph_path, kernel_path,
                                  report_path, implementation_root)
        elif operation == "exact_replay":
            row = _exact_replay(case, report_path, graph_path, kernel_path,
                                implementation_root)
        elif operation == "bisim_producer":
            row = _bisim_producer(case, graph, kernel, graph_path, kernel_path,
                                  report_path, implementation_root)
        elif operation == "bisim_replay":
            row = _bisim_replay(case, report_path, graph_path, kernel_path,
                                implementation_root)
        else:
            raise SystemExit(f"unknown worker operation: {operation}")
        row["case_id"] = case_id
        row["operation"] = operation
        print(json.dumps(row, sort_keys=True, allow_nan=False))
        return 0
    except BaseException as error:
        print(json.dumps({"case_id": case_id, "operation": operation,
                          "status": "worker_error", "error_type": type(error).__name__,
                          "error": str(error)[:2000], "peak_rss_bytes": _peak_rss_bytes()},
                         sort_keys=True, allow_nan=False))
        return 0


def _extract_git_archive(destination: Path, revision: str) -> Path:
    archive = destination / "audit.tar"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar",
                    "--output", str(archive), revision, "audit"],
                   check=True, stdout=subprocess.DEVNULL)
    target = destination / "source"
    target.mkdir()
    with tarfile.open(archive, "r:") as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise RuntimeError(f"unsafe archive member {member.name}")
            if not path.parts or path.parts[0] != "audit":
                continue
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts:
                continue
            output = target / "audit" / Path(*relative.parts)
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError(f"missing archived file: {member.name}")
            with source, output.open("wb") as stream:
                shutil.copyfileobj(source, stream)
            output.chmod(member.mode & 0o777)
    archive.unlink()
    return target


def _worker_call(operation: str, case: dict[str, Any], implementation_root: Path,
                 report_path: Path, timeout: float) -> dict[str, Any]:
    graph_path = ROOT / case["graph_path"]
    kernel_path = ROOT / case["kernel_path"]
    command = [sys.executable, str(Path(__file__).resolve()), "--worker",
               operation, case["case_id"], str(implementation_root),
               str(graph_path), str(kernel_path), str(report_path), "reserved"]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"case_id": case["case_id"], "operation": operation,
                "status": "timeout", "elapsed_to_timeout_seconds": timeout,
                "peak_rss_bytes": None, "timeout_seconds": timeout}
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        return {"case_id": case["case_id"], "operation": operation,
                "status": "worker_error", "return_code": completed.returncode,
                "elapsed_seconds": elapsed, "stderr_tail": completed.stderr[-2000:]}
    try:
        row = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"case_id": case["case_id"], "operation": operation,
                "status": "worker_error", "elapsed_seconds": elapsed,
                "stderr_tail": completed.stderr[-2000:],
                "stdout_tail": completed.stdout[-2000:]}
    row["worker_elapsed_seconds_including_startup"] = elapsed
    return row


def _verify_freeze() -> tuple[dict[str, Any], str]:
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    digest = _sha(manifest_raw)
    if f"`{digest}`" not in PREREG.read_text(encoding="utf-8"):
        raise SystemExit("input manifest hash has not been registered in PREREGISTRATION.md")
    for case in manifest["cases"]:
        for key in ("graph_path", "kernel_path"):
            path = ROOT / case[key]
            expected = case[key.replace("_path", "_sha256")]
            if _sha(path.read_bytes()) != expected:
                raise SystemExit(f"frozen input changed before timing: {case['case_id']} {key}")
    return manifest, digest


def _source_hashes(root: Path) -> dict[str, str]:
    names = ["trace_equivalence.py", "replay_trace_equivalence.py",
             "stochastic_bisimulation.py", "replay_stochastic_certificate.py",
             "probabilistic_channels.py", "orchgraph.py"]
    return {name: _sha((root / "audit" / name).read_bytes()) for name in names}


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    fields = ("status", "decision", "diagnostics", "diagnostic", "reason",
              "analysis_seconds", "replay_seconds", "peak_rss_bytes",
              "certificate_bytes_compact", "report_file_bytes", "state_count",
              "transition_count", "label_count", "pair_statuses", "pair_ranks",
              "finite_witness_lengths", "partition_block_count", "bounded_work")
    return {key: row.get(key) for key in fields if key in row}


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = sorted({str(row.get("status")) for row in rows})
    status_counts = {status: sum(row.get("status") == status for row in rows)
                     for status in statuses}
    completed = [row for row in rows if row.get("status") in
                 ("proved_equal", "proved_unequal", "unequal", "inconclusive", "verified")]
    time_key = "analysis_seconds" if any("analysis_seconds" in row for row in rows) else "replay_seconds"
    complete_times = [row[time_key] for row in completed if isinstance(row.get(time_key), (float, int))]
    rss = [row["peak_rss_bytes"] for row in completed
           if isinstance(row.get("peak_rss_bytes"), int)]
    sizes = [row["certificate_bytes_compact"] for row in completed
             if isinstance(row.get("certificate_bytes_compact"), int)]
    return {
        "status_counts": status_counts,
        "completed_statuses_for_latency": sorted({row.get("status") for row in completed}),
        "latency_samples_used": len(complete_times),
        "latency_median_seconds": statistics.median(complete_times) if complete_times else None,
        "peak_rss_median_bytes": statistics.median(rss) if rss else None,
        "certificate_bytes_median": statistics.median(sizes) if sizes else None,
    }


def _run_operation_set(case: dict[str, Any], implementation_root: Path,
                       repetitions: int, warmups: int, timeout: float,
                       report_root: Path, preopt: bool = False,
                       include_bisim: bool = True) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="scp-scale-workers-") as temp_name:
        temp = Path(temp_name)
        for repetition in range(warmups + repetitions):
            warmup = repetition < warmups
            run_id = f"warmup-{repetition + 1}" if warmup else f"rep-{repetition - warmups + 1}"
            operations = ("exact_producer", "exact_replay")
            for operation in operations:
                if operation.endswith("producer"):
                    report_path = temp / f"{case['case_id']}-{run_id}-{operation}.json"
                else:
                    report_path = current_report_path
                    if not report_path.exists():
                        # A fresh producer report is required for every verifier worker.
                        report_path = temp / f"{case['case_id']}-{run_id}-exact_producer.json"
                current_report_path = report_path if operation == "exact_producer" else current_report_path
                row = _worker_call(operation, case, implementation_root,
                                   report_path, timeout)
                row.update({"run_id": run_id, "warmup": warmup,
                            "implementation": "5aa-preoptimization" if preopt else "current"})
                all_rows.append(row)
                if not warmup and repetition == warmups and operation.endswith("producer"):
                    destination = report_root / ("preoptimization" if preopt else "current") / f"{case['case_id']}.json"
                    if report_path.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(report_path, destination)
            if include_bisim:
                # Bisimulation runs are a separate analysis/replay pair and fresh workers.
                bisim_path = temp / f"{case['case_id']}-{run_id}-bisim.json"
                producer = _worker_call("bisim_producer", case, implementation_root,
                                        bisim_path, timeout)
                producer.update({"run_id": run_id, "warmup": warmup,
                                "implementation": "current"})
                all_rows.append(producer)
                replay = _worker_call("bisim_replay", case, implementation_root,
                                      bisim_path, timeout)
                replay.update({"run_id": run_id, "warmup": warmup,
                               "implementation": "current"})
                all_rows.append(replay)
                if not warmup and repetition == warmups and bisim_path.exists():
                    destination = report_root / "current_bisim" / f"{case['case_id']}.json"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(bisim_path, destination)
    return all_rows


def _summarize_by_case(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("warmup"):
            continue
        key = row["case_id"] + "/" + row.get("implementation", "current") + "/" + row["operation"]
        grouped.setdefault(key, []).append(row)
    return {key: _summarize(value) for key, value in sorted(grouped.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output", type=Path,
                        default=OUT / "structured_results.json")
    parser.add_argument("--preoptimization-sample", action="store_true",
                        help="run the frozen 5aa pre-optimization producer/replayer on selected structures")
    parser.add_argument("--worker", nargs=7, metavar=("OP", "CASE_ID", "IMPLEMENTATION_ROOT",
                        "GRAPH", "KERNEL", "REPORT", "RESERVED"))
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args.worker)
    if args.repetitions < 5 or args.warmups != 1:
        raise SystemExit("registration requires one warmup and at least five measured repetitions")
    if args.timeout_seconds <= 0 or args.timeout_seconds > 20:
        raise SystemExit("per-worker timeout must be in (0,20] seconds")

    manifest, manifest_sha = _verify_freeze()
    snapshot_diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--quiet", "dd97af2ac714f8c0dbf5ddb63ac29cbdb4a2d0dc",
         "HEAD", "--", "audit/trace_equivalence.py", "audit/replay_trace_equivalence.py",
         "audit/stochastic_bisimulation.py", "audit/replay_stochastic_certificate.py",
         "audit/probabilistic_channels.py", "audit/orchgraph.py"], check=False)
    relevant_source_diff = snapshot_diff.returncode != 0
    current_hashes = _source_hashes(CURRENT_ROOT)
    with tempfile.TemporaryDirectory(prefix="scp-scale-preopt-") as preopt_dir:
        preopt_root = _extract_git_archive(Path(preopt_dir), PREOPT_REVISION) if args.preoptimization_sample else None
        preopt_hashes = _source_hashes(preopt_root) if preopt_root else None
        manifest_cases = [case for case in manifest["cases"] if not case["family"].startswith("symmetric_equal_chain_primary")]
        report_root = OUT / "reports"
        all_rows: list[dict[str, Any]] = []
        for index, case in enumerate(manifest_cases, start=1):
            rows = _run_operation_set(case, CURRENT_ROOT, args.repetitions,
                                      args.warmups, args.timeout_seconds,
                                      report_root, preopt=False)
            all_rows.extend(rows)
            print(f"[{index}/{len(manifest_cases)}] current {case['case_id']} "
                  f"{sum(not row.get('warmup') for row in rows)} operation rows", flush=True)
            if preopt_root and case["case_id"] in PREOPT_SAMPLE:
                preopt_rows = _run_operation_set(case, preopt_root, args.repetitions,
                                                 args.warmups, args.timeout_seconds,
                                                 report_root, preopt=True,
                                                 include_bisim=False)
                # The pre-optimization snapshot lacks the current bisimulation pair;
                # retain only its exact producer/replayer rows for paired timing.
                all_rows.extend(row for row in preopt_rows
                                if row["operation"].startswith("exact_"))

        post_manifest, post_sha = _verify_freeze()
        if post_sha != manifest_sha or post_manifest["cases"] != manifest["cases"]:
            raise SystemExit("frozen input manifest changed during timing")
        result = {
            "format": "orchlang-structured-scalability-results",
            "version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"python": sys.version.split()[0],
                            "platform": platform.platform(),
                            "machine": platform.machine(),
                            "processor": platform.processor() or None,
                            "peak_rss_measurement": "OS high-water RSS per fresh worker; includes interpreter and imports"},
            "protocol": {"warmups_per_case_operation": args.warmups,
                         "measured_repetitions_per_case_operation": args.repetitions,
                         "timeout_seconds_per_worker": args.timeout_seconds,
                         "timer_scope": "analysis/replay call after module import; producer file parsing is timed only when done inside analyze API caller (graph/kernel JSON decode excluded)",
                         "manifest_sha256": manifest_sha,
                         "preregistration_sha256": _sha(PREREG.read_bytes()),
                         "study_worker_sha256": _sha(Path(__file__).read_bytes()),
                         "input_generator_sha256": manifest["generator_sha256"],
                         "primary_scaling_script_sha256": _sha((ROOT / "research/publication_upgrade/solver_scaling.py").read_bytes()),
                         "frozen_rc2_dd97_revision": "dd97af2ac714f8c0dbf5ddb63ac29cbdb4a2d0dc",
                         "dd97_to_current_audit_tree_has_source_diff": relevant_source_diff,
                         "dd97_current_exact_source_hashes_identical": {
                             name: current_hashes[name] for name in ("trace_equivalence.py", "replay_trace_equivalence.py")},
                         "current_source_sha256": current_hashes,
                         "preoptimization_revision": PREOPT_REVISION if preopt_hashes else None,
                         "preoptimization_source_sha256": preopt_hashes,
                         "unknown_policy": "preserved as its actual status and raw elapsed time; excluded from complete-result latency summaries; never recoded as zero",
                         "replay_policy": "fresh producer report for every replay operation, including UNKNOWN reports; unknown replay is retained as unknown"},
            "cases": manifest_cases,
            "rows": all_rows,
            "summaries": _summarize_by_case(all_rows),
        }
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                          sort_keys=True, allow_nan=False) + "\n",
                               encoding="utf-8")
        print(f"wrote {output_path}")
        print(f"result_sha256={_sha(output_path.read_bytes())}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        raise SystemExit(_worker(sys.argv[2:]))
    raise SystemExit(main())
