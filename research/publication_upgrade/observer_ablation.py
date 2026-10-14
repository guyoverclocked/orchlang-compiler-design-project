#!/usr/bin/env python3
"""Compare request equality, stochastic bisimulation, and exact usage traces.

Runs the same twelve authored fixtures used by the exact trace-equivalence
study. The request-equality checker and stochastic bisimulation are evaluated
fresh from their source implementations. Exact trace decisions are produced
and independently replayed. Three hand-selected cases also compare exact
finite-horizon aggregate-usage and ordered-trace observers.

Reproduce from the repository root with:

    python3 research/publication_upgrade/observer_ablation.py \
      --output output/publication_upgrade/observer_ablation.json

This is a controlled observer comparison, not a new equivalence algorithm or
an empirical claim about provider behavior.
"""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "examples" / "channels"
DEFAULT_OUTPUT = ROOT / "output" / "publication_upgrade" / "observer_ablation.json"

sys.path.insert(0, str(ROOT / "audit"))
from evaluate_probabilistic_channels import (  # noqa: E402
    SCENARIOS as CHANNEL_SCENARIOS,
    expected_totals,
)
from evaluate_trace_equivalence import (  # noqa: E402
    _case_table as exact_trace_case_table,
)
from orchgraph import Graph, check as check_request_equivalence  # noqa: E402
from probabilistic_channels import analyze as analyze_finite_channel  # noqa: E402
from replay_trace_equivalence import replay_report  # noqa: E402
from stochastic_bisimulation import analyze as analyze_bisimulation  # noqa: E402
from trace_equivalence import analyze as analyze_trace_equivalence  # noqa: E402

TRACE_SCENARIOS = [dict(row["values"]) for row in CHANNEL_SCENARIOS]
FIXTURE_NAMES = {
    "aggregate_hides_order",
    "biased_productive_cycle",
    "canonical_alias_chain",
    "changed_public_context",
    "different_requests_equal_usage",
    "equivalent_dependent_chain",
    "fixed_public_context",
    "history_conditioned_usage",
    "merge_stress_productive_cycle",
    "noisy_usage_bit",
    "same_mean_distinct_laws",
    "trace_equal_not_bisimilar",
}
SELECTED_FINITE_OBSERVER_CASES = {
    "different_requests_equal_usage": 1,
    "same_mean_distinct_laws": 1,
    "aggregate_hides_order": 2,
}
LIMITS = {
    "request_equivalence": {"max_product_nodes": 50_000},
    "strong_stochastic_bisimulation": {
        "max_states": 10_000,
        "max_work_bytes": 64 * 1024 * 1024,
    },
    "exact_trace": {
        "max_states": 10_000,
        "max_work_bytes": 64 * 1024 * 1024,
        "max_matrix_entries": 10_000_000,
        "max_rational_bits": 8192,
    },
    "independent_replay": {
        "max_states": 10_000,
        "max_transitions": 1_000_000,
        "max_work_bytes": 64 * 1024 * 1024,
        "max_matrix_entries": 10_000_000,
        "max_control_steps": 1_000_000,
    },
    "finite_observer_cross_check": {
        "max_states": 100_000,
        "max_work_bytes": 64 * 1024 * 1024,
    },
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _case_table() -> dict[str, tuple[dict[str, Any] | None,
                                     dict[str, Any] | None,
                                     dict[str, Any]]]:
    # Reuse the exact-trace study's authored source definitions and add its
    # special equal-but-not-bisimilar fixture, which has no channel-case row.
    table = exact_trace_case_table()
    if "trace_equal_not_bisimilar" in table:
        raise RuntimeError("special exact-trace fixture unexpectedly collides with the study cases")
    table["trace_equal_not_bisimilar"] = (None, None, {})
    if set(table) != FIXTURE_NAMES:
        raise RuntimeError("authored fixture name set differs from the pinned 12-case study")
    return table


def _load_fixture(name: str, expected_graph: dict[str, Any] | None,
                  expected_kernel: dict[str, Any] | None,
                  public_store: dict[str, Any]):
    graph_path = FIXTURE_DIR / f"{name}.graph.json"
    kernel_path = FIXTURE_DIR / f"{name}.kernel.json"
    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    graph = json.loads(graph_raw.decode("utf-8"))
    kernel = json.loads(kernel_raw.decode("utf-8"))
    if graph.get("name") != name:
        raise RuntimeError(f"{name}: graph document name does not match its fixture file")
    if expected_graph is not None and graph != expected_graph:
        raise RuntimeError(f"{name}: graph differs from the authored exact-trace study definition")
    if expected_kernel is not None and kernel != expected_kernel:
        raise RuntimeError(f"{name}: kernel differs from the authored exact-trace study definition")
    return graph_path, kernel_path, graph_raw, kernel_raw, graph, kernel


def _histogram_digest(histogram: dict[str, Any]) -> str:
    payload = [
        {"observation": json.loads(observation), "probability": str(probability)}
        for observation, probability in sorted(histogram.items())
    ]
    return _sha(_json_bytes(payload))


def _finite_observer_comparison(name: str, graph: dict[str, Any],
                                kernel: dict[str, Any], public_store: dict[str, Any],
                                horizon: int) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for observer in ("aggregate", "trace"):
        report = analyze_finite_channel(
            graph, kernel, public_store, CHANNEL_SCENARIOS, horizon,
            max_states=LIMITS["finite_observer_cross_check"]["max_states"],
            observer=observer,
            max_work_bytes=LIMITS["finite_observer_cross_check"]["max_work_bytes"],
        )
        if report.get("status") != "complete" or report.get("metrics") is None:
            raise RuntimeError(
                f"{name}: finite {observer} observer cross-check did not complete"
            )
        histograms = [row["histogram"] for row in report["rows"]]
        if any(row.get("mass") != 1 for row in report["rows"]):
            raise RuntimeError(f"{name}: finite {observer} histogram mass is not exactly one")
        variation = report["metrics"]["pairwise"][0]["total_variation"]
        observations[observer] = {
            "status": report["status"],
            "horizon": horizon,
            "total_variation_between_secret_laws": str(variation),
            "mean_usage_vectors_equal": (
                expected_totals(histograms[0]) == expected_totals(histograms[1])
            ),
            "scenario_histograms": [
                {
                    "scenario_index": index,
                    "mass": str(row["mass"]),
                    "support_size": len(row["histogram"]),
                    "histogram_sha256": _histogram_digest(row["histogram"]),
                    "entries": [
                        {"observation": json.loads(key), "probability": str(probability)}
                        for key, probability in sorted(row["histogram"].items())
                    ],
                }
                for index, row in enumerate(report["rows"])
            ],
        }
    return {"horizon": horizon, "observers": observations}


def _exact_witness_summary(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for pair in (report.get("result") or {}).get("pairs", []):
        if pair.get("status") != "unequal":
            continue
        witness = pair.get("counterexample", {})
        rows.append({
            "left_scenario": pair.get("left_scenario"),
            "right_scenario": pair.get("right_scenario"),
            "word": witness.get("word"),
            "end_kind": witness.get("end_kind"),
            "left_probability": witness.get("left_probability"),
            "right_probability": witness.get("right_probability"),
        })
    return rows


def _run_case(name: str, expected_graph: dict[str, Any] | None,
              expected_kernel: dict[str, Any] | None,
              public_store: dict[str, Any]) -> dict[str, Any]:
    (graph_path, kernel_path, graph_raw, kernel_raw,
     graph, kernel) = _load_fixture(name, expected_graph, expected_kernel, public_store)
    input_hashes = {
        "graph_raw_sha256": _sha(graph_raw),
        "kernel_raw_sha256": _sha(kernel_raw),
        "public_store_canonical_sha256": _sha(_json_bytes(public_store).rstrip(b"\n")),
        "secret_scenarios_canonical_sha256": _sha(_json_bytes(TRACE_SCENARIOS).rstrip(b"\n")),
        "channel_scenarios_canonical_sha256": _sha(_json_bytes(CHANNEL_SCENARIOS).rstrip(b"\n")),
    }

    request_report = check_request_equivalence(
        Graph(graph), max_nodes=LIMITS["request_equivalence"]["max_product_nodes"]
    )
    bisimulation = analyze_bisimulation(
        graph, kernel, public_store, TRACE_SCENARIOS,
        max_states=LIMITS["strong_stochastic_bisimulation"]["max_states"],
        max_work_bytes=LIMITS["strong_stochastic_bisimulation"]["max_work_bytes"],
    )
    trace_report = analyze_trace_equivalence(
        graph, kernel, public_store, TRACE_SCENARIOS,
        max_states=LIMITS["exact_trace"]["max_states"],
        max_work_bytes=LIMITS["exact_trace"]["max_work_bytes"],
        max_matrix_entries=LIMITS["exact_trace"]["max_matrix_entries"],
        max_rational_bits=LIMITS["exact_trace"]["max_rational_bits"],
        raw_graph=graph_raw,
        raw_kernel=kernel_raw,
    )
    attestation = replay_report(
        trace_report, graph_raw, kernel_raw,
        expected_public_store=public_store,
        expected_secret_scenarios=TRACE_SCENARIOS,
        max_states=LIMITS["independent_replay"]["max_states"],
        max_transitions=LIMITS["independent_replay"]["max_transitions"],
        max_work_bytes=LIMITS["independent_replay"]["max_work_bytes"],
        max_matrix_entries=LIMITS["independent_replay"]["max_matrix_entries"],
        max_control_steps=LIMITS["independent_replay"]["max_control_steps"],
    )

    finite_observer = None
    if name in SELECTED_FINITE_OBSERVER_CASES:
        finite_observer = _finite_observer_comparison(
            name, graph, kernel, public_store, SELECTED_FINITE_OBSERVER_CASES[name]
        )

    return {
        "name": name,
        "fixtures": {
            "graph": {"path": graph_path.relative_to(ROOT).as_posix(),
                      "raw_sha256": input_hashes["graph_raw_sha256"]},
            "kernel": {"path": kernel_path.relative_to(ROOT).as_posix(),
                       "raw_sha256": input_hashes["kernel_raw_sha256"]},
        },
        "input_hashes": input_hashes,
        "request_equality_graph_checker": {
            "status": request_report.get("status"),
            "diagnostic": request_report.get("diagnostic"),
            "product_nodes": request_report.get("product_nodes"),
            "product_edges": request_report.get("product_edges"),
            "claim": request_report.get("semantics", {}).get("claim"),
            "interpretation": (
                "rejection means this sufficient universal request-equality condition was not proved; "
                "it is not evidence of a usage leak under the supplied finite kernel"
            ),
        },
        "strong_stochastic_bisimulation": {
            "status": bisimulation.get("status"),
            "claim": bisimulation.get("claim"),
            "initial_scenario_blocks": (bisimulation.get("partition_certificate") or {}).get(
                "initial_scenario_blocks"),
            "expanded_states": (bisimulation.get("analysis_stats") or {}).get("expanded_states"),
            "interpretation": (
                "proved_equal is sufficient; inconclusive means a bisimulation partition split, "
                "not an exact trace-law counterexample"
            ),
        },
        "exact_ordered_usage_trace": {
            "status": trace_report.get("status"),
            "claim": trace_report.get("claim"),
            "scope": trace_report.get("scope"),
            "certificate_sha256": _sha(_json_bytes(trace_report)),
            "independent_replay": {
                "status": attestation.get("status"),
                "decision": attestation.get("decision"),
                "pair_count": attestation.get("pair_count"),
                "attestation_sha256": _sha(_json_bytes(attestation)),
            },
            "finite_distinguishing_witnesses": _exact_witness_summary(trace_report),
        },
        "finite_horizon_observer_comparison": finite_observer,
    }


def run(output: Path) -> dict[str, Any]:
    case_table = _case_table()
    graph_files = {path.name.removesuffix(".graph.json")
                   for path in FIXTURE_DIR.glob("*.graph.json")}
    kernel_files = {path.name.removesuffix(".kernel.json")
                    for path in FIXTURE_DIR.glob("*.kernel.json")}
    if graph_files != FIXTURE_NAMES or kernel_files != FIXTURE_NAMES:
        raise RuntimeError("fixture directory no longer contains the exact pinned 12 graph/kernel pairs")

    source_paths = {
        "request_equality_checker": ROOT / "audit" / "orchgraph.py",
        "strong_stochastic_bisimulation": ROOT / "audit" / "stochastic_bisimulation.py",
        "exact_trace_producer": ROOT / "audit" / "trace_equivalence.py",
        "independent_trace_replayer": ROOT / "audit" / "replay_trace_equivalence.py",
        "independent_closure_replayer": ROOT / "audit" / "replay_stochastic_certificate.py",
        "finite_channel_analyzer": ROOT / "audit" / "probabilistic_channels.py",
        "authored_fixture_definitions": ROOT / "audit" / "evaluate_probabilistic_channels.py",
        "exact_trace_fixture_study": ROOT / "audit" / "evaluate_trace_equivalence.py",
        "observer_ablation_driver": Path(__file__).resolve(),
    }
    source_hashes = {label: _sha(path.read_bytes()) for label, path in source_paths.items()}
    report: dict[str, Any] = {
        "format": "orchlang-publication-observer-ablation",
        "version": 1,
        "status": "running",
        "scope": (
            "the same 12 authored graph/kernel fixtures as the exact-trace study; one fixed public store; "
            "two explicit secret assignments; exact decisions concern the declared finite rational "
            "successful-outcome kernel and ordered usage words with separate stop and nonterminal mass"
        ),
        "method": (
            "freshly run the sufficient request-equality graph checker, strong stochastic-bisimulation "
            "checker, exact trace-law producer, and independent exact-trace replay on every frozen pair; "
            "compare aggregate and ordered-trace finite-horizon observers for three discriminating cases"
        ),
        "algorithm_claim": "observer and checker comparison only; no new equivalence algorithm is claimed",
        "reproduction_cli": [
            "python3", "research/publication_upgrade/observer_ablation.py",
            "--output", "output/publication_upgrade/observer_ablation.json",
        ],
        "actual_argv": [str(Path(sys.argv[0]).as_posix()), *sys.argv[1:]],
        "output_path": output.relative_to(ROOT).as_posix() if output.is_relative_to(ROOT) else str(output),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "limits": LIMITS,
        "tool_sha256": source_hashes,
        "fixtures": [],
        "summary": {},
        "failures": [],
    }

    request_counts: Counter[str] = Counter()
    bisimulation_counts: Counter[str] = Counter()
    trace_counts: Counter[str] = Counter()
    replay_counts: Counter[str] = Counter()
    for name in sorted(case_table):
        expected_graph, expected_kernel, public_store = case_table[name]
        try:
            row = _run_case(name, expected_graph, expected_kernel, public_store)
        except Exception as error:
            report["failures"].append({
                "fixture": name,
                "error_type": type(error).__name__,
                "message": str(error),
            })
            continue
        report["fixtures"].append(row)
        request_counts[str(row["request_equality_graph_checker"]["status"])] += 1
        bisimulation_counts[str(row["strong_stochastic_bisimulation"]["status"])] += 1
        trace_counts[str(row["exact_ordered_usage_trace"]["status"])] += 1
        replay_counts[str(row["exact_ordered_usage_trace"]["independent_replay"]["status"])] += 1
        if row["request_equality_graph_checker"]["status"] not in ("accepted", "rejected"):
            report["failures"].append(f"{name}: request checker status is not a completed decision")
        if row["strong_stochastic_bisimulation"]["status"] not in (
                "proved_equal", "inconclusive"):
            report["failures"].append(f"{name}: stochastic bisimulation did not complete")
        if row["exact_ordered_usage_trace"]["status"] not in ("proved_equal", "unequal"):
            report["failures"].append(f"{name}: exact trace analysis did not decide")
        expected_trace = row["exact_ordered_usage_trace"]["status"]
        replay = row["exact_ordered_usage_trace"]["independent_replay"]
        if replay["status"] != "verified" or replay["decision"] != expected_trace:
            report["failures"].append(f"{name}: independent replay did not verify the exact decision")

    report["summary"] = {
        "fixture_count": len(report["fixtures"]),
        "request_equality_status_counts": dict(sorted(request_counts.items())),
        "strong_stochastic_bisimulation_status_counts": dict(sorted(bisimulation_counts.items())),
        "exact_trace_status_counts": dict(sorted(trace_counts.items())),
        "independent_replay_status_counts": dict(sorted(replay_counts.items())),
        "fixtures_with_finite_observer_comparison": sum(
            row["finite_horizon_observer_comparison"] is not None
            for row in report["fixtures"]
        ),
    }

    by_name = {row["name"]: row for row in report["fixtures"]}
    expected_exact = {
        "different_requests_equal_usage": "proved_equal",
        "same_mean_distinct_laws": "unequal",
        "aggregate_hides_order": "unequal",
        "trace_equal_not_bisimilar": "proved_equal",
    }
    for name, expected in expected_exact.items():
        row = by_name.get(name)
        if row is None or row["exact_ordered_usage_trace"]["status"] != expected:
            report["failures"].append(f"{name}: expected exact trace status {expected}")
    different_requests = by_name.get("different_requests_equal_usage")
    if (different_requests is None
            or different_requests["request_equality_graph_checker"]["status"] != "rejected"):
        report["failures"].append(
            "different_requests_equal_usage: request-equivalence rejection was not reproduced"
        )
    if (different_requests is None
            or different_requests["exact_ordered_usage_trace"]["independent_replay"]["status"] != "verified"):
        report["failures"].append(
            "different_requests_equal_usage: exact equality was not independently replayed"
        )
    for name, expected_tv in (
        ("different_requests_equal_usage", {"aggregate": "0", "trace": "0"}),
        ("same_mean_distinct_laws", {"aggregate": "1", "trace": "1"}),
        ("aggregate_hides_order", {"aggregate": "0", "trace": "1"}),
    ):
        row = by_name.get(name)
        comparison = None if row is None else row["finite_horizon_observer_comparison"]
        if comparison is None:
            report["failures"].append(f"{name}: finite observer comparison is missing")
            continue
        actual = {
            observer: comparison["observers"][observer]["total_variation_between_secret_laws"]
            for observer in ("aggregate", "trace")
        }
        if actual != expected_tv:
            report["failures"].append(
                f"{name}: finite observer variation {actual} differs from {expected_tv}"
            )
    same_mean = by_name.get("same_mean_distinct_laws")
    if same_mean is None or not all(
        same_mean["finite_horizon_observer_comparison"]["observers"][observer][
            "mean_usage_vectors_equal"
        ] for observer in ("aggregate", "trace")
    ):
        report["failures"].append("same_mean_distinct_laws: finite-horizon usage means differ")
    order_case = by_name.get("aggregate_hides_order")
    if order_case is None or not all(
        order_case["finite_horizon_observer_comparison"]["observers"][observer][
            "mean_usage_vectors_equal"
        ] for observer in ("aggregate", "trace")
    ):
        report["failures"].append("aggregate_hides_order: aggregate usage totals differ")

    report["status"] = "passed" if not report["failures"] else "failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_json_bytes(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="write the observer-ablation JSON (default: output/publication_upgrade/observer_ablation.json)")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        report = run(output)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "message": str(error)}, indent=2))
        return 1
    print(json.dumps({"status": report["status"], "summary": report["summary"],
                      "failures": report["failures"]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
