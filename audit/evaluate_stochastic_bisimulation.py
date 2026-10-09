#!/usr/bin/env python3
"""Reproduce finite stochastic-bisimulation certificates for channel fixtures.

The driver uses the 11 authored graph/kernel pairs in ``examples/channels``.
It makes source-byte-bound producer certificates, independently replays each
certificate, runs fresh state-cap UNKNOWN probes, and cross-checks every
``proved_equal`` case against exact finite-DP usage distributions at selected
call horizons. No provider calls, samples, fitting, or wall-clock fields are
used.

Run from the repository root with::

    python3 audit/evaluate_stochastic_bisimulation.py
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "channels"
DEFAULT_OUTPUT = ROOT / "bench" / "results" / "stochastic_bisimulation"
DEFAULT_SUMMARY = ROOT / "bench" / "results" / "stochastic_bisimulation.json"
HORIZONS = (1, 2, 4, 8, 16, 32)
OBSERVERS = ("aggregate", "trace")

sys.path.insert(0, str(ROOT / "audit"))
from evaluate_probabilistic_channels import SCENARIOS, cases  # noqa: E402
from orchgraph import Graph, check  # noqa: E402
from probabilistic_channels import canonical, producer_histogram  # noqa: E402


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _run_json(command: list[str], *, expected_codes: set[int], label: str) -> tuple[dict[str, Any], bytes]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    if completed.returncode not in expected_codes:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        stdout = completed.stdout.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{label} exited {completed.returncode}; stderr={stderr!r}; stdout={stdout[:2000]!r}"
        )
    try:
        document = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} did not emit JSON: {error}") from error
    if not isinstance(document, dict):
        raise RuntimeError(f"{label} result must be a JSON object")
    return document, completed.stdout


def _histogram_payload(histogram: dict[str, Fraction]) -> list[dict[str, Any]]:
    return [
        {"observation": json.loads(observation), "probability": str(probability)}
        for observation, probability in sorted(histogram.items())
    ]


def _histogram_sha256(histogram: dict[str, Fraction]) -> str:
    payload = _histogram_payload(histogram)
    return _sha(_json_bytes(payload))


def _scenario_assignments() -> list[dict[str, Any]]:
    # The finite-channel evaluator uses these same explicit secret values with
    # priors. Bisimulation compares the listed stores pairwise and needs only
    # the value assignments, so omit priors here.
    return [dict(row["values"]) for row in SCENARIOS]


def _case_table() -> dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]]:
    return {graph["name"]: (graph, kernel, public, expected)
            for graph, kernel, public, expected in cases()}


def _check_fixture_bytes(name: str, expected_graph: dict[str, Any],
                         expected_kernel: dict[str, Any]) -> tuple[Path, Path, bytes, bytes]:
    graph_path = FIXTURES / f"{name}.graph.json"
    kernel_path = FIXTURES / f"{name}.kernel.json"
    graph_raw = graph_path.read_bytes()
    kernel_raw = kernel_path.read_bytes()
    graph_document = json.loads(graph_raw.decode("utf-8"))
    kernel_document = json.loads(kernel_raw.decode("utf-8"))
    if graph_document != expected_graph or kernel_document != expected_kernel:
        raise RuntimeError(
            f"fixture {name} differs from the authored finite-channel case definition; "
            "review inputs before changing the evaluation"
        )
    return graph_path, kernel_path, graph_raw, kernel_raw


def _produce_certificate(graph_path: Path, kernel_path: Path,
                         public_store: dict[str, Any], scenarios: list[dict[str, Any]],
                         destination: Path, *, max_states: int,
                         max_work_bytes: int) -> tuple[dict[str, Any], bytes]:
    command = [
        sys.executable, str(ROOT / "audit" / "stochastic_bisimulation.py"),
        str(graph_path), str(kernel_path),
        "--public-json", canonical(public_store),
        "--scenarios-json", canonical(scenarios),
        "--max-states", str(max_states),
        "--max-work-bytes", str(max_work_bytes),
        "--report", str(destination),
    ]
    report, _stdout = _run_json(command, expected_codes={0, 2, 3},
                                label=f"producer {destination.name}")
    raw = destination.read_bytes()
    if json.loads(raw.decode("utf-8")) != report:
        raise RuntimeError(f"producer stdout/report file disagree for {destination.name}")
    return report, raw


def _replay_certificate(certificate_path: Path, graph_path: Path, kernel_path: Path,
                        public_store: dict[str, Any], scenarios: list[dict[str, Any]],
                        destination: Path, *, max_states: int,
                        max_transitions: int, max_work_bytes: int,
                        max_control_steps: int) -> tuple[dict[str, Any], bytes]:
    command = [
        sys.executable, str(ROOT / "audit" / "replay_stochastic_certificate.py"),
        str(certificate_path), str(graph_path), str(kernel_path),
        "--public-json", canonical(public_store),
        "--scenarios-json", canonical(scenarios),
        "--max-states", str(max_states),
        "--max-transitions", str(max_transitions),
        "--max-work-bytes", str(max_work_bytes),
        "--max-control-steps", str(max_control_steps),
    ]
    attestation, _stdout = _run_json(command, expected_codes={0, 1, 2},
                                     label=f"replayer {certificate_path.name}")
    return attestation, _write_json(destination, attestation)


def _cross_check_dp(graph: dict[str, Any], kernel: dict[str, Any],
                    public_store: dict[str, Any], scenarios: list[dict[str, Any]],
                    *, max_states: int, max_work_bytes: int) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    distributions: dict[str, Any] = {}
    transition_total = 0
    state_visit_total = 0
    for horizon in HORIZONS:
        for observer in OBSERVERS:
            rows = []
            for scenario_index, scenario in enumerate(scenarios):
                full_store = {**public_store, **scenario}
                result = producer_histogram(
                    graph, kernel, full_store, horizon,
                    max_states=max_states, observer=observer,
                    max_work_bytes=max_work_bytes,
                )
                if result["status"] != "complete":
                    raise RuntimeError(
                        f"finite DP returned UNKNOWN for proved_equal case at H={horizon}, "
                        f"observer={observer}, scenario={scenario_index}: {result.get('reason')}"
                    )
                if result["mass"] != Fraction(1):
                    raise RuntimeError("finite DP histogram has non-unit exact probability mass")
                rows.append(result)
            equal = all(row["histogram"] == rows[0]["histogram"] for row in rows[1:])
            if not equal:
                raise RuntimeError(
                    f"proved_equal case has unequal finite DP distributions at H={horizon}, "
                    f"observer={observer}"
                )
            checks.append({
                "horizon": horizon,
                "observer": observer,
                "equal_exact_histograms": True,
                "scenario_count": len(rows),
                "scenarios": [
                    {
                        "index": index,
                        "mass": str(result["mass"]),
                        "support_size": len(result["histogram"]),
                        "histogram_sha256": _histogram_sha256(result["histogram"]),
                        "state_visits": result["state_visits"],
                        "call_transitions": result["call_transitions"],
                        "work_bytes_estimate": result["work_bytes_estimate"],
                    }
                    for index, result in enumerate(rows)
                ],
            })
            transition_total += sum(row["call_transitions"] for row in rows)
            state_visit_total += sum(row["state_visits"] for row in rows)
            # Preserve the exact distributions as readable evidence. These
            # values contain only the chosen observer's billing/usage trace.
            distributions[f"H{horizon}.{observer}"] = {
                "horizon": horizon,
                "observer": observer,
                "scenario_histograms": [
                    {
                        "scenario": scenario,
                        "mass": str(row["mass"]),
                        "entries": _histogram_payload(row["histogram"]),
                    }
                    for scenario, row in zip(scenarios, rows)
                ],
            }
    return {
        "checks": checks,
        "distribution_evidence": distributions,
        "check_count": len(checks),
        "scenario_histograms_checked": len(checks) * len(scenarios),
        "dp_state_visits": state_visit_total,
        "dp_call_transitions": transition_total,
    }


def evaluate(*, output_dir: Path = DEFAULT_OUTPUT,
             summary_path: Path = DEFAULT_SUMMARY,
             producer_max_states: int = 10_000,
             producer_max_work_bytes: int = 64 * 1024 * 1024,
             verifier_max_states: int = 10_000,
             verifier_max_transitions: int = 1_000_000,
             verifier_max_work_bytes: int = 64 * 1024 * 1024,
             verifier_max_control_steps: int = 1_000_000,
             dp_max_states: int = 100_000,
             dp_max_work_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    cases_by_name = _case_table()
    scenarios = _scenario_assignments()
    output_dir.mkdir(parents=True, exist_ok=True)
    dp_dir = output_dir / "finite_dp"
    dp_dir.mkdir(parents=True, exist_ok=True)

    producer_path = ROOT / "audit" / "stochastic_bisimulation.py"
    replayer_path = ROOT / "audit" / "replay_stochastic_certificate.py"
    dp_path = ROOT / "audit" / "probabilistic_channels.py"
    evaluator_path = ROOT / "audit" / "evaluate_probabilistic_channels.py"
    producer_sha256 = _sha(producer_path.read_bytes())
    case_names = sorted(cases_by_name)
    counts = Counter()
    structural_counts = Counter()
    fixture_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    summary: dict[str, Any] = {
        "format": "orchlang-stochastic-bisimulation-evaluation",
        "version": 1,
        "status": "running",
        "scope": (
            "Authored finite request-graph fixtures and synthetic rational kernels; "
            "two explicit secret assignments per fixture; no priors or provider calls."
        ),
        "runtime": {"python_version": platform.python_version()},
        "method": {
            "producer": "audit/stochastic_bisimulation.py CLI; certificate binds exact graph/kernel file bytes",
            "independent_replay": "audit/replay_stochastic_certificate.py CLI with expected public store and secret assignments",
            "finite_dp_cross_check": "probabilistic_channels.producer_histogram exact dynamic program; aggregate and ordered trace observers",
            "secret_assignment_source": "audit/evaluate_probabilistic_channels.py SCENARIOS values, with priors omitted",
            "horizons": list(HORIZONS),
            "observers": list(OBSERVERS),
            "unknown_probe": "fresh producer run with max_states=1, followed by a fresh independent replay; no prior attestation reused",
        },
        "caps": {
            "producer": {"max_states": producer_max_states,
                         "max_work_bytes": producer_max_work_bytes,
                         "max_state_key_bytes": 16 * 1024 * 1024,
                         "rational_precision_limit_bits": 8192},
            "independent_replayer": {"max_states": verifier_max_states,
                                     "max_transitions": verifier_max_transitions,
                                     "max_work_bytes": verifier_max_work_bytes,
                                     "max_control_steps": verifier_max_control_steps,
                                     "max_state_key_bytes": 16 * 1024 * 1024,
                                     "rational_precision_limit_bits": 8192},
            "finite_dp": {"max_states_per_scenario_horizon_observer": dp_max_states,
                          "max_work_bytes_per_scenario_horizon_observer": dp_max_work_bytes},
            "unknown_probe": {"producer_max_states": 1,
                              "producer_max_work_bytes": producer_max_work_bytes,
                              "replayer_max_states": verifier_max_states,
                              "replayer_max_transitions": verifier_max_transitions,
                              "replayer_max_work_bytes": verifier_max_work_bytes,
                              "replayer_max_control_steps": verifier_max_control_steps},
        },
        "source_hashes": {
            "driver_sha256": _sha(Path(__file__).read_bytes()),
            "producer_sha256": producer_sha256,
            "replayer_sha256": _sha(replayer_path.read_bytes()),
            "finite_dp_sha256": _sha(dp_path.read_bytes()),
            "scenario_definition_sha256": _sha(evaluator_path.read_bytes()),
        },
        "scenario_assignments": scenarios,
        "fixtures": fixture_rows,
        "summary": {},
        "failures": failures,
    }

    for name in case_names:
        expected_graph, expected_kernel, public_store, expected_structural = cases_by_name[name]
        graph_path, kernel_path, graph_raw, kernel_raw = _check_fixture_bytes(
            name, expected_graph, expected_kernel
        )
        graph_document = json.loads(graph_raw.decode("utf-8"))
        kernel_document = json.loads(kernel_raw.decode("utf-8"))
        structural = check(Graph(graph_document))["status"]
        structural_counts[structural] += 1
        if structural != expected_structural:
            failures.append(f"{name}: structural status {structural} != authored {expected_structural}")

        inputs_path = output_dir / f"{name}.inputs.json"
        inputs_payload = {"public_store": public_store, "secret_scenarios": scenarios}
        inputs_raw = _write_json(inputs_path, inputs_payload)
        certificate_path = output_dir / f"{name}.certificate.json"
        report, report_raw = _produce_certificate(
            graph_path, kernel_path, public_store, scenarios, certificate_path,
            max_states=producer_max_states,
            max_work_bytes=producer_max_work_bytes,
        )
        status = report.get("status")
        if status not in ("proved_equal", "inconclusive", "unknown"):
            raise RuntimeError(f"{name}: unsupported producer status {status!r}")
        counts[status] += 1
        if report.get("hashes", {}).get("graph_sha256") != _sha(graph_raw):
            failures.append(f"{name}: certificate did not bind exact raw graph bytes")
        if report.get("hashes", {}).get("kernel_sha256") != _sha(kernel_raw):
            failures.append(f"{name}: certificate did not bind exact raw kernel bytes")
        if report.get("hashes", {}).get("checker_sha256") != producer_sha256:
            failures.append(f"{name}: certificate checker hash differs from the executed producer source")
        if status == "unknown":
            if any(report.get(field) is not None for field in
                   ("claim", "closed_system", "partition_certificate")):
                failures.append(f"{name}: UNKNOWN main certificate contains a partial proof")

        attestation_path = output_dir / f"{name}.attestation.json"
        attestation, attestation_raw = _replay_certificate(
            certificate_path, graph_path, kernel_path, public_store, scenarios,
            attestation_path, max_states=verifier_max_states,
            max_transitions=verifier_max_transitions,
            max_work_bytes=verifier_max_work_bytes,
            max_control_steps=verifier_max_control_steps,
        )
        expected_attestation = "verified" if status in ("proved_equal", "inconclusive") else "unknown"
        if attestation.get("status") != expected_attestation:
            failures.append(f"{name}: independent replay returned {attestation.get('status')} for {status}")
        if attestation.get("report_sha256") != _sha(report_raw):
            failures.append(f"{name}: attestation is not bound to the saved certificate bytes")
        if attestation.get("graph_sha256") != _sha(graph_raw):
            failures.append(f"{name}: attestation did not bind the raw graph bytes")
        if attestation.get("kernel_sha256") != _sha(kernel_raw):
            failures.append(f"{name}: attestation did not bind the raw kernel bytes")
        if attestation.get("public_store_sha256") != _sha(canonical(public_store).encode("utf-8")):
            failures.append(f"{name}: attestation did not bind the canonical public store")
        if attestation.get("secret_scenarios_sha256") != _sha(canonical(scenarios).encode("utf-8")):
            failures.append(f"{name}: attestation did not bind the canonical secret scenarios")
        if status == "proved_equal" and attestation.get("equal_laws_claim") is not True:
            failures.append(f"{name}: proved_equal certificate did not replay as equal")
        if status == "inconclusive" and attestation.get("equal_laws_claim") is not False:
            failures.append(f"{name}: inconclusive certificate carried an equality claim")

        unknown_certificate_path = output_dir / f"{name}.cap1-unknown.certificate.json"
        unknown_report, unknown_raw = _produce_certificate(
            graph_path, kernel_path, public_store, scenarios, unknown_certificate_path,
            max_states=1, max_work_bytes=producer_max_work_bytes,
        )
        if unknown_report.get("status") != "unknown":
            failures.append(f"{name}: state-cap probe returned {unknown_report.get('status')}")
        if any(unknown_report.get(field) is not None for field in
               ("claim", "closed_system", "partition_certificate")):
            failures.append(f"{name}: state-cap UNKNOWN contains a partial closure claim")
        unknown_attestation_path = output_dir / f"{name}.cap1-unknown.attestation.json"
        unknown_attestation, unknown_attestation_raw = _replay_certificate(
            unknown_certificate_path, graph_path, kernel_path, public_store, scenarios,
            unknown_attestation_path, max_states=verifier_max_states,
            max_transitions=verifier_max_transitions,
            max_work_bytes=verifier_max_work_bytes,
            max_control_steps=verifier_max_control_steps,
        )
        if unknown_attestation.get("status") != "unknown" or unknown_attestation.get("equal_laws_claim") is not False:
            failures.append(f"{name}: fresh replay did not preserve the state-cap UNKNOWN result")
        if unknown_attestation.get("report_sha256") != _sha(unknown_raw):
            failures.append(f"{name}: UNKNOWN attestation is not bound to its fresh capped report")

        dp_summary = None
        dp_evidence_path = None
        dp_evidence_raw = None
        if status == "proved_equal":
            dp_summary = _cross_check_dp(
                graph_document, kernel_document, public_store, scenarios,
                max_states=dp_max_states, max_work_bytes=dp_max_work_bytes,
            )
            dp_evidence_path = dp_dir / f"{name}.json"
            dp_evidence = {
                "format": "orchlang-stochastic-bisimulation-finite-dp-crosscheck",
                "version": 1,
                "case": name,
                "graph_sha256": _sha(graph_raw),
                "kernel_sha256": _sha(kernel_raw),
                "public_store": public_store,
                "secret_scenarios": scenarios,
                "horizons": list(HORIZONS),
                "observers": list(OBSERVERS),
                "caps": {"max_states": dp_max_states, "max_work_bytes": dp_max_work_bytes},
                **dp_summary,
            }
            dp_evidence_raw = _write_json(dp_evidence_path, dp_evidence)

        fixture_rows.append({
            "name": name,
            "structural_status": structural,
            "producer_status": status,
            "public_store": public_store,
            "secret_scenarios": scenarios,
            "graph": {
                "path": str(graph_path.relative_to(ROOT)),
                "sha256": _sha(graph_raw),
                "bytes": len(graph_raw),
            },
            "kernel": {
                "path": str(kernel_path.relative_to(ROOT)),
                "sha256": _sha(kernel_raw),
                "bytes": len(kernel_raw),
            },
            "inputs_artifact": {
                "path": str(inputs_path.relative_to(ROOT)),
                "sha256": _sha(inputs_raw),
            },
            "certificate": {
                "path": str(certificate_path.relative_to(ROOT)),
                "sha256": _sha(report_raw),
                "state_count": report.get("closed_system", {}).get("state_count")
                if isinstance(report.get("closed_system"), dict) else None,
                "transition_count": report.get("closed_system", {}).get("transition_count")
                if isinstance(report.get("closed_system"), dict) else None,
                "checker_sha256": report.get("hashes", {}).get("checker_sha256"),
            },
            "independent_attestation": {
                "path": str(attestation_path.relative_to(ROOT)),
                "sha256": _sha(attestation_raw),
                "status": attestation.get("status"),
                "certificate_status": attestation.get("certificate_status"),
                "equal_laws_claim": attestation.get("equal_laws_claim"),
                "state_count": attestation.get("state_count"),
                "transition_count": attestation.get("transition_count"),
                "independent_work_bytes": attestation.get("independent_work_bytes"),
            },
            "state_cap_unknown_probe": {
                "producer_max_states": 1,
                "certificate": {
                    "path": str(unknown_certificate_path.relative_to(ROOT)),
                    "sha256": _sha(unknown_raw),
                    "status": unknown_report.get("status"),
                    "reason": unknown_report.get("reason"),
                    "claim": unknown_report.get("claim"),
                    "closed_system": unknown_report.get("closed_system"),
                    "partition_certificate": unknown_report.get("partition_certificate"),
                },
                "fresh_independent_attestation": {
                    "path": str(unknown_attestation_path.relative_to(ROOT)),
                    "sha256": _sha(unknown_attestation_raw),
                    "status": unknown_attestation.get("status"),
                    "equal_laws_claim": unknown_attestation.get("equal_laws_claim"),
                    "diagnostic": unknown_attestation.get("diagnostic"),
                },
            },
            "finite_dp_cross_check": None if dp_summary is None else {
                "path": str(dp_evidence_path.relative_to(ROOT)),
                "sha256": _sha(dp_evidence_raw or b""),
                "horizons_checked": len(HORIZONS),
                "observers_checked": len(OBSERVERS),
                "scenario_histograms_checked": dp_summary["scenario_histograms_checked"],
                "exact_equal_law_checks": dp_summary["check_count"],
                "dp_state_visits": dp_summary["dp_state_visits"],
                "dp_call_transitions": dp_summary["dp_call_transitions"],
            },
        })

    summary["summary"] = {
        "fixture_count": len(fixture_rows),
        "producer_status_counts": {key: counts.get(key, 0)
                                    for key in ("proved_equal", "inconclusive", "unknown")},
        "structural_status_counts": dict(sorted(structural_counts.items())),
        "normal_certificates_independently_verified": sum(
            row["independent_attestation"]["status"] == "verified" for row in fixture_rows
        ),
        "fresh_state_cap_unknown_probes": sum(
            row["state_cap_unknown_probe"]["certificate"]["status"] == "unknown"
            and row["state_cap_unknown_probe"]["fresh_independent_attestation"]["status"] == "unknown"
            for row in fixture_rows
        ),
        "proved_equal_dp_comparisons": sum(
            row["finite_dp_cross_check"]["exact_equal_law_checks"]
            if row["finite_dp_cross_check"] else 0 for row in fixture_rows
        ),
        "dp_scenario_histograms_compared": sum(
            row["finite_dp_cross_check"]["scenario_histograms_checked"]
            if row["finite_dp_cross_check"] else 0 for row in fixture_rows
        ),
        "horizons": list(HORIZONS),
        "observers": list(OBSERVERS),
    }
    summary["status"] = "passed" if not failures else "failed"
    _write_json(summary_path, summary)
    if failures:
        raise RuntimeError("stochastic bisimulation evaluation failed: " + "; ".join(failures))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--producer-max-states", type=int, default=10_000)
    parser.add_argument("--producer-max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--verifier-max-states", type=int, default=10_000)
    parser.add_argument("--verifier-max-transitions", type=int, default=1_000_000)
    parser.add_argument("--verifier-max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--verifier-max-control-steps", type=int, default=1_000_000)
    parser.add_argument("--dp-max-states", type=int, default=100_000)
    parser.add_argument("--dp-max-work-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args(argv)
    result = evaluate(
        output_dir=args.output_dir, summary_path=args.summary,
        producer_max_states=args.producer_max_states,
        producer_max_work_bytes=args.producer_max_work_bytes,
        verifier_max_states=args.verifier_max_states,
        verifier_max_transitions=args.verifier_max_transitions,
        verifier_max_work_bytes=args.verifier_max_work_bytes,
        verifier_max_control_steps=args.verifier_max_control_steps,
        dp_max_states=args.dp_max_states,
        dp_max_work_bytes=args.dp_max_work_bytes,
    )
    print(json.dumps({"status": result["status"], **result["summary"]},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
