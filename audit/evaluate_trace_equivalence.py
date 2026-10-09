#!/usr/bin/env python3
"""Reproduce exact finite trace-equivalence reports and independent replays.

This controlled evaluation uses the 11 authored finite-channel fixtures and
one authored equal-but-not-strongly-bisimilar example. It makes source-bound
reports, independently replays every complete decision, probes fresh UNKNOWN
caps, rejects one semantic tamper per fixture, and cross-checks proved equal
laws at finite DP horizons. No provider calls, fitting, sampling, or timing
claims are involved.

Run from the repository root with::

    python3 audit/evaluate_trace_equivalence.py
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "channels"
OUTPUT_DIR = ROOT / "bench" / "results" / "trace_equivalence"
SUMMARY_PATH = ROOT / "bench" / "results" / "trace_equivalence.json"
EQUAL_HORIZONS = (1, 2, 4, 8)
MAX_DP_HORIZON = 16

sys.path.insert(0, str(ROOT / "audit"))
from evaluate_probabilistic_channels import SCENARIOS, cases  # noqa: E402
from probabilistic_channels import canonical, producer_histogram  # noqa: E402
from replay_trace_equivalence import replay_report  # noqa: E402
from stochastic_bisimulation import analyze as analyze_bisimulation  # noqa: E402
from trace_equivalence import analyze as analyze_trace_equivalence  # noqa: E402


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":") if indent is None else None,
                      indent=indent, allow_nan=False)
    return (text + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> bytes:
    raw = _json_bytes(value, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _histogram_payload(histogram: dict[str, Fraction]) -> list[dict[str, Any]]:
    return [
        {"observation": json.loads(observation), "probability": str(probability)}
        for observation, probability in sorted(histogram.items())
    ]


def _histogram_digest(histogram: dict[str, Fraction]) -> str:
    return _sha(_json_bytes(_histogram_payload(histogram)))


def _scenario_assignments() -> list[dict[str, Any]]:
    return [dict(row["values"]) for row in SCENARIOS]


def _case_table() -> dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    return {graph["name"]: (graph, kernel, public)
            for graph, kernel, public, _expected in cases()}


def _fixture(name: str, graph_expected: dict[str, Any] | None = None,
             kernel_expected: dict[str, Any] | None = None):
    graph_path = FIXTURES / f"{name}.graph.json"
    kernel_path = FIXTURES / f"{name}.kernel.json"
    graph_raw, kernel_raw = graph_path.read_bytes(), kernel_path.read_bytes()
    graph = json.loads(graph_raw.decode("utf-8"))
    kernel = json.loads(kernel_raw.decode("utf-8"))
    if graph.get("name") != name:
        raise RuntimeError(f"fixture {name} contains a different graph name")
    if graph_expected is not None and graph != graph_expected:
        raise RuntimeError(f"fixture {name} graph differs from the controlled case definition")
    if kernel_expected is not None and kernel != kernel_expected:
        raise RuntimeError(f"fixture {name} kernel differs from the controlled case definition")
    return graph_path, kernel_path, graph_raw, kernel_raw, graph, kernel


def _run_trace_producer(graph: dict[str, Any], kernel: dict[str, Any],
                        public_store: dict[str, Any], scenarios: list[dict[str, Any]],
                        graph_raw: bytes, kernel_raw: bytes, *, max_states: int,
                        max_work_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    return analyze_trace_equivalence(
        graph, kernel, public_store, scenarios,
        max_states=max_states, max_work_bytes=max_work_bytes,
        raw_graph=graph_raw, raw_kernel=kernel_raw,
    )


def _replay_file(report_path: Path, graph_raw: bytes, kernel_raw: bytes,
                 public_store: dict[str, Any], scenarios: list[dict[str, Any]], *,
                 max_states: int = 10_000,
                 max_transitions: int = 1_000_000,
                 max_work_bytes: int = 64 * 1024 * 1024,
                 max_matrix_entries: int = 10_000_000,
                 max_control_steps: int = 1_000_000) -> dict[str, Any]:
    return replay_report(
        report_path, graph_raw, kernel_raw,
        expected_public_store=public_store,
        expected_secret_scenarios=scenarios,
        max_states=max_states,
        max_transitions=max_transitions,
        max_work_bytes=max_work_bytes,
        max_matrix_entries=max_matrix_entries,
        max_control_steps=max_control_steps,
    )


def _finite_dp(graph: dict[str, Any], kernel: dict[str, Any],
               public_store: dict[str, Any], scenarios: list[dict[str, Any]],
               horizon: int, observer: str, *, max_states: int,
               max_work_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = []
    for scenario_index, scenario in enumerate(scenarios):
        result = producer_histogram(
            graph, kernel, {**public_store, **scenario}, horizon,
            max_states=max_states, observer=observer,
            max_work_bytes=max_work_bytes,
        )
        if result.get("status") != "complete":
            raise RuntimeError(
                f"finite DP returned UNKNOWN at H={horizon}, observer={observer}, "
                f"scenario={scenario_index}: {result.get('reason')}"
            )
        if result.get("mass") != Fraction(1):
            raise RuntimeError("finite DP histogram has non-unit exact probability mass")
        results.append(result)
    evidence = {
        "horizon": horizon,
        "observer": observer,
        "scenario_histograms": [
            {
                "scenario_index": index,
                "mass": str(result["mass"]),
                "support_size": len(result["histogram"]),
                "histogram_sha256": _histogram_digest(result["histogram"]),
                "entries": _histogram_payload(result["histogram"]),
                "state_visits": result.get("state_visits"),
                "call_transitions": result.get("call_transitions"),
                "work_bytes_estimate": result.get("work_bytes_estimate"),
            }
            for index, result in enumerate(results)
        ],
    }
    return results, evidence


def _witness_mass(histogram: dict[str, Fraction], word: list[dict[str, Any]],
                  end_kind: str) -> Fraction:
    stopped = end_kind == "stop"
    total = Fraction(0)
    for observation_text, probability in histogram.items():
        observation = json.loads(observation_text)
        if (observation.get("stopped") is stopped
                and observation.get("usage_trace") == word):
            total += probability
    return total


def _bisimulation_status(name: str, graph: dict[str, Any], kernel: dict[str, Any],
                         public_store: dict[str, Any], scenarios: list[dict[str, Any]],
                         graph_raw: bytes, kernel_raw: bytes,
                         prior_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prior = prior_by_name.get(name)
    if prior is not None:
        if (prior["graph"].get("sha256") == _sha(graph_raw)
                and prior["kernel"].get("sha256") == _sha(kernel_raw)
                and prior.get("certificate", {}).get("checker_sha256")
                    == _sha((ROOT / "audit/stochastic_bisimulation.py").read_bytes())
                and prior.get("independent_attestation", {}).get("status") == "verified"):
            return {
                "status": prior["producer_status"],
                "source": "saved stochastic-bisimulation evaluation with matching raw fixture hashes",
                "attestation_status": prior["independent_attestation"].get("status"),
            }
        raise RuntimeError(f"saved bisimulation comparison for {name} has stale source hashes")
    report = analyze_bisimulation(
        graph, kernel, public_store, scenarios,
        max_states=10_000, max_work_bytes=64 * 1024 * 1024,
    )
    return {
        "status": report.get("status"),
        "source": "fresh authored comparison via stochastic_bisimulation.analyze",
        "attestation_status": "not independently replayed in this trace-equivalence study",
    }


def _tamper(report: dict[str, Any]) -> dict[str, Any]:
    altered = json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))
    pair = altered["result"]["pairs"][0]
    if pair["status"] == "equal":
        if pair["basis"]:
            row = pair["basis"][0]["row"]
            row[0] = "1" if row[0] != "1" else "0"
        else:
            pair["initial_difference_in_span"] = False
    else:
        pair["counterexample"]["left_probability"] = pair["counterexample"]["right_probability"]
    return altered


def evaluate(*, output_dir: Path = OUTPUT_DIR,
             summary_path: Path = SUMMARY_PATH,
             producer_max_states: int = 10_000,
             producer_max_work_bytes: int = 64 * 1024 * 1024,
             verifier_max_states: int = 10_000,
             verifier_max_transitions: int = 1_000_000,
             verifier_max_work_bytes: int = 64 * 1024 * 1024,
             verifier_max_matrix_entries: int = 10_000_000,
             verifier_max_control_steps: int = 1_000_000,
             dp_max_states: int = 100_000,
             dp_max_work_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    case_definitions = _case_table()
    scenarios = _scenario_assignments()
    prior_path = ROOT / "bench/results/stochastic_bisimulation.json"
    prior_doc = json.loads(prior_path.read_text(encoding="utf-8"))
    prior_by_name = {row["name"]: row for row in prior_doc["fixtures"]}

    if "trace_equal_not_bisimilar" in case_definitions:
        raise RuntimeError("new equal-not-bisimilar fixture collides with an existing case")
    case_definitions["trace_equal_not_bisimilar"] = (None, None, {})
    output_dir.mkdir(parents=True, exist_ok=True)

    source_paths = {
        "trace_equivalence_producer": ROOT / "audit/trace_equivalence.py",
        "independent_trace_replayer": ROOT / "audit/replay_trace_equivalence.py",
        "independent_closure_replayer": ROOT / "audit/replay_stochastic_certificate.py",
        "finite_channel_dp": ROOT / "audit/probabilistic_channels.py",
        "stochastic_bisimulation_comparison": ROOT / "audit/stochastic_bisimulation.py",
        "evaluation_driver": Path(__file__),
    }
    source_hashes = {name: _sha(path.read_bytes()) for name, path in source_paths.items()}
    summary: dict[str, Any] = {
        "format": "orchlang-exact-trace-equivalence-evaluation",
        "version": 1,
        "status": "running",
        "scope": (
            "12 controlled authored graph/kernel fixtures; finite rational successful-outcome models; "
            "exact ordered call-usage traces, no real providers or adoption study"
        ),
        "method": (
            "producer-generated exact weighted-automaton certificates are independently checked by "
            "reconstructing the finite semantic closure and verifying exact row-space certificates "
            "or exact finite distinguishing witnesses"
        ),
        "source_hashes": source_hashes,
        "runtime": {"python": platform.python_version()},
        "limits": {
            "producer": {"max_states": producer_max_states,
                         "max_work_bytes": producer_max_work_bytes,
                         "max_matrix_entries": 10_000_000,
                         "max_rational_bits": 8192},
            "independent_replay": {"max_states": verifier_max_states,
                                   "max_transitions": verifier_max_transitions,
                                   "max_work_bytes": verifier_max_work_bytes,
                                   "max_matrix_entries": verifier_max_matrix_entries,
                                   "max_control_steps": verifier_max_control_steps,
                                   "max_rational_bits": 8192},
            "finite_dp": {"max_states": dp_max_states,
                          "max_work_bytes": dp_max_work_bytes},
            "fresh_unknown_probe": {"max_states": 1},
        },
        "equal_cross_check_horizons": list(EQUAL_HORIZONS),
        "fixtures": [],
        "failures": [],
    }
    decision_counts: Counter[str] = Counter()
    bisimulation_counts: Counter[str] = Counter()
    proof_replay_count = 0
    witness_replay_count = 0
    equal_dp_checks = 0
    equal_dp_histograms = 0
    witness_dp_checks = 0
    witness_dp_distinguishing = 0
    cap_unknown_count = 0
    tamper_rejected_count = 0

    for name in sorted(case_definitions):
        graph_expected, kernel_expected, public_store = case_definitions[name]
        graph_path, kernel_path, graph_raw, kernel_raw, graph, kernel = _fixture(
            name, graph_expected, kernel_expected
        )
        scenario_values = scenarios
        if name == "trace_equal_not_bisimilar":
            scenario_values = [{"secret": False}, {"secret": True}]
        input_hashes = {
            "graph_raw_sha256": _sha(graph_raw),
            "kernel_raw_sha256": _sha(kernel_raw),
            "public_store_canonical_sha256": _sha(canonical(public_store).encode("utf-8")),
            "secret_scenarios_canonical_sha256": _sha(canonical(scenario_values).encode("utf-8")),
        }

        certificate = _run_trace_producer(
            graph, kernel, public_store, scenario_values, graph_raw, kernel_raw,
            max_states=producer_max_states,
            max_work_bytes=producer_max_work_bytes,
        )
        cert_path = output_dir / f"{name}.certificate.json"
        cert_raw = _write_json(cert_path, certificate)
        status = certificate["status"]
        if status not in ("proved_equal", "unequal"):
            summary["failures"].append(f"{name}: normal producer decision is {status}")
        for field, expected_digest in (
            ("graph_sha256", input_hashes["graph_raw_sha256"]),
            ("kernel_sha256", input_hashes["kernel_raw_sha256"]),
            ("public_store_sha256", input_hashes["public_store_canonical_sha256"]),
            ("secret_scenarios_sha256", input_hashes["secret_scenarios_canonical_sha256"]),
        ):
            if certificate.get("hashes", {}).get(field) != expected_digest:
                summary["failures"].append(f"{name}: producer {field} differs from evaluator binding")
        decision_counts[status] += 1

        attestation = _replay_file(
            cert_path, graph_raw, kernel_raw, public_store, scenario_values,
            max_states=verifier_max_states,
            max_transitions=verifier_max_transitions,
            max_work_bytes=verifier_max_work_bytes,
            max_matrix_entries=verifier_max_matrix_entries,
            max_control_steps=verifier_max_control_steps,
        )
        att_path = output_dir / f"{name}.attestation.json"
        att_raw = _write_json(att_path, attestation)
        if attestation["status"] != "verified" or attestation.get("decision") != status:
            summary["failures"].append(f"{name}: independent replay did not verify the producer decision")
        elif status == "proved_equal":
            proof_replay_count += 1
        elif status == "unequal":
            witness_replay_count += 1
        if attestation.get("status") == "verified" and (
                attestation.get("public_store_sha256") != input_hashes["public_store_canonical_sha256"]
                or attestation.get("secret_scenarios_sha256")
                    != input_hashes["secret_scenarios_canonical_sha256"]):
            summary["failures"].append(f"{name}: independent attestation store hashes differ from inputs")

        cap_report = _run_trace_producer(
            graph, kernel, public_store, scenario_values, graph_raw, kernel_raw,
            max_states=1, max_work_bytes=producer_max_work_bytes,
        )
        if cap_report.get("status") != "unknown":
            cap_report = _run_trace_producer(
                graph, kernel, public_store, scenario_values, graph_raw, kernel_raw,
                max_states=producer_max_states, max_work_bytes=1,
            )
        cap_path = output_dir / f"{name}.cap-unknown.certificate.json"
        _write_json(cap_path, cap_report)
        cap_attestation = _replay_file(
            cap_path, graph_raw, kernel_raw, public_store, scenario_values,
            max_states=verifier_max_states,
            max_transitions=verifier_max_transitions,
            max_work_bytes=verifier_max_work_bytes,
            max_matrix_entries=verifier_max_matrix_entries,
            max_control_steps=verifier_max_control_steps,
        )
        cap_att_path = output_dir / f"{name}.cap-unknown.attestation.json"
        cap_att_raw = _write_json(cap_att_path, cap_attestation)
        if (cap_report.get("status") == "unknown"
                and cap_report.get("closed_system") is None
                and cap_report.get("result") is None
                and cap_attestation.get("status") == "unknown"
                and cap_attestation.get("decision") is None
                and not cap_attestation.get("all_finite_horizons_claim")):
            cap_unknown_count += 1
        else:
            summary["failures"].append(f"{name}: capped report/replay did not fail closed as UNKNOWN")

        tampered = _tamper(certificate)
        tamper_path = output_dir / f"{name}.tampered.json"
        _write_json(tamper_path, tampered)
        tamper_attestation = replay_report(
            tamper_path, graph_raw, kernel_raw,
            expected_public_store=public_store,
            expected_secret_scenarios=scenario_values,
            max_states=verifier_max_states,
            max_transitions=verifier_max_transitions,
            max_work_bytes=verifier_max_work_bytes,
            max_matrix_entries=verifier_max_matrix_entries,
            max_control_steps=verifier_max_control_steps,
        )
        tamper_att_path = output_dir / f"{name}.tamper-attestation.json"
        tamper_att_raw = _write_json(tamper_att_path, tamper_attestation)
        if tamper_attestation.get("status") == "rejected":
            tamper_rejected_count += 1
        else:
            summary["failures"].append(f"{name}: semantically tampered report was not rejected")

        bisimulation = _bisimulation_status(
            name, graph, kernel, public_store, scenario_values,
            graph_raw, kernel_raw, prior_by_name,
        )
        bisimulation_counts[str(bisimulation["status"])] += 1

        finite_dp_ref = None
        if status == "proved_equal":
            checks = []
            distributions: dict[str, Any] = {}
            for horizon in EQUAL_HORIZONS:
                for observer in ("aggregate", "trace"):
                    dp_rows, evidence = _finite_dp(
                        graph, kernel, public_store, scenario_values,
                        horizon, observer, max_states=dp_max_states,
                        max_work_bytes=dp_max_work_bytes,
                    )
                    equal = all(row["histogram"] == dp_rows[0]["histogram"]
                                for row in dp_rows[1:])
                    if not equal:
                        summary["failures"].append(
                            f"{name}: proved_equal differs in finite DP at H={horizon}, {observer}"
                        )
                    checks.append({
                        "horizon": horizon,
                        "observer": observer,
                        "equal_exact_histograms": equal,
                        "scenario_count": len(dp_rows),
                        "scenario_histogram_sha256": [
                            _histogram_digest(row["histogram"]) for row in dp_rows
                        ],
                    })
                    distributions[f"H{horizon}.{observer}"] = evidence
                    equal_dp_histograms += len(dp_rows)
                    equal_dp_checks += 1
            dp_path = output_dir / f"{name}.finite-dp.json"
            dp_raw = _write_json(dp_path, {
                "format": "orchlang-trace-equivalence-finite-dp-cross-check",
                "version": 1,
                "fixture": name,
                "source_hashes": {"graph_sha256": _sha(graph_raw),
                                  "kernel_sha256": _sha(kernel_raw)},
                "checks": checks,
                "distributions": distributions,
                "scope": "finite-horizon DP corroboration at listed horizons; the exact certificate carries the all-finite-horizon claim",
            })
            finite_dp_ref = {"path": str(dp_path.relative_to(ROOT)), "sha256": _sha(dp_raw),
                             "check_count": len(checks)}
        elif status == "unequal" and certificate["result"]["pairs"]:
            pair = certificate["result"]["pairs"][0]
            witness = pair["counterexample"]
            horizon = max(1, len(witness["word"]))
            if horizon <= MAX_DP_HORIZON:
                dp_rows, evidence = _finite_dp(
                    graph, kernel, public_store, scenario_values,
                    horizon, "trace", max_states=dp_max_states,
                    max_work_bytes=dp_max_work_bytes,
                )
                left_index, right_index = pair["left_scenario"], pair["right_scenario"]
                distinguishes = dp_rows[left_index]["histogram"] != dp_rows[right_index]["histogram"]
                left_witness_mass = _witness_mass(
                    dp_rows[left_index]["histogram"], witness["word"], witness["end_kind"]
                )
                right_witness_mass = _witness_mass(
                    dp_rows[right_index]["histogram"], witness["word"], witness["end_kind"]
                )
                probability_match = (
                    left_witness_mass == Fraction(witness["left_probability"])
                    and right_witness_mass == Fraction(witness["right_probability"])
                )
                witness_dp_checks += 1
                witness_dp_distinguishing += int(distinguishes)
                if not distinguishes:
                    summary["failures"].append(
                        f"{name}: finite DP at witness horizon H={horizon} did not distinguish the pair"
                    )
                if not probability_match:
                    summary["failures"].append(
                        f"{name}: finite DP witness masses differ from the exact counterexample"
                    )
                dp_path = output_dir / f"{name}.witness-dp.json"
                dp_raw = _write_json(dp_path, {
                    "format": "orchlang-trace-equivalence-witness-dp-cross-check",
                    "version": 1,
                    "fixture": name,
                    "horizon": horizon,
                    "observer": "trace",
                    "pair": {"left_scenario": left_index, "right_scenario": right_index},
                    "finite_dp_histograms_differ": distinguishes,
                    "exact_witness_probabilities_match": probability_match,
                    "dp_witness_probabilities": {"left": str(left_witness_mass),
                                                 "right": str(right_witness_mass)},
                    "distributions": evidence,
                    "scope": "finite-DP cross-check of one exact finite witness; not the proof itself",
                })
                finite_dp_ref = {"path": str(dp_path.relative_to(ROOT)), "sha256": _sha(dp_raw),
                                 "witness_horizon": horizon,
                                 "histograms_differ": distinguishes}
            else:
                finite_dp_ref = {"skipped": True, "reason": "witness horizon exceeds the declared small-horizon DP cap",
                                 "witness_horizon": horizon}

        fixture_row = {
            "name": name,
            "graph": {"path": str(graph_path.relative_to(ROOT)), "sha256": _sha(graph_raw)},
            "kernel": {"path": str(kernel_path.relative_to(ROOT)), "sha256": _sha(kernel_raw)},
            "public_store": public_store,
            "secret_scenarios": scenario_values,
            "input_hashes": input_hashes,
            "producer_status": status,
            "claim": certificate.get("claim"),
            "trace_certificate": {
                "path": str(cert_path.relative_to(ROOT)), "sha256": _sha(cert_raw),
                "state_count": (certificate.get("closed_system") or {}).get("state_count"),
                "transition_count": (certificate.get("closed_system") or {}).get("transition_count"),
            },
            "independent_attestation": {
                "path": str(att_path.relative_to(ROOT)), "sha256": _sha(att_raw),
                "status": attestation.get("status"),
                "decision": attestation.get("decision"),
                "pair_count": attestation.get("pair_count"),
            },
            "bisimulation_comparison": bisimulation,
            "fresh_unknown_probe": {
                "producer_status": cap_report.get("status"),
                "producer_max_states": cap_report.get("limits", {}).get("max_states"),
                "certificate": {"path": str(cap_path.relative_to(ROOT)),
                                "sha256": _sha(cap_path.read_bytes())},
                "independent_attestation": {"path": str(cap_att_path.relative_to(ROOT)),
                                            "sha256": _sha(cap_att_raw),
                                            "status": cap_attestation.get("status"),
                                            "decision": cap_attestation.get("decision")},
            },
            "tamper_probe": {
                "path": str(tamper_path.relative_to(ROOT)),
                "sha256": _sha(tamper_path.read_bytes()),
                "independent_attestation": {"path": str(tamper_att_path.relative_to(ROOT)),
                                            "sha256": _sha(tamper_att_raw),
                                            "status": tamper_attestation.get("status")},
            },
            "finite_dp_cross_check": finite_dp_ref,
        }
        summary["fixtures"].append(fixture_row)

    special = next(row for row in summary["fixtures"] if row["name"] == "trace_equal_not_bisimilar")
    summary["summary"] = {
        "fixture_count": len(summary["fixtures"]),
        "producer_decision_counts": dict(sorted(decision_counts.items())),
        "independently_replayed_proofs": proof_replay_count,
        "independently_replayed_finite_witnesses": witness_replay_count,
        "proved_equal_finite_dp_checks": equal_dp_checks,
        "proved_equal_scenario_histograms_checked": equal_dp_histograms,
        "finite_witness_dp_checks": witness_dp_checks,
        "finite_witness_dp_distinguishing_checks": witness_dp_distinguishing,
        "fresh_producer_and_replay_unknown_probes": cap_unknown_count,
        "semantically_tampered_reports_rejected": tamper_rejected_count,
        "bisimulation_status_counts": dict(sorted(bisimulation_counts.items())),
        "equal_not_bisimilar_fixture": {
            "name": "trace_equal_not_bisimilar",
            "trace_equivalence_status": special["producer_status"],
            "independent_replay_status": special["independent_attestation"]["status"],
            "strong_bisimulation_status": special["bisimulation_comparison"]["status"],
            "finite_dp_cross_check": special["finite_dp_cross_check"],
        },
    }
    summary["status"] = "passed" if not summary["failures"] else "failed"
    summary_raw = _write_json(summary_path, summary)
    summary["summary_sha256"] = _sha(summary_raw)
    print(json.dumps({"status": summary["status"], "summary": summary["summary"],
                      "failures": summary["failures"], "summary_sha256": _sha(summary_raw)},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--producer-max-states", type=int, default=10_000)
    parser.add_argument("--producer-max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--verifier-max-states", type=int, default=10_000)
    parser.add_argument("--verifier-max-transitions", type=int, default=1_000_000)
    parser.add_argument("--verifier-max-work-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--verifier-max-matrix-entries", type=int, default=10_000_000)
    parser.add_argument("--verifier-max-control-steps", type=int, default=1_000_000)
    parser.add_argument("--dp-max-states", type=int, default=100_000)
    parser.add_argument("--dp-max-work-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args(argv)
    report = evaluate(
        output_dir=args.output_dir, summary_path=args.summary,
        producer_max_states=args.producer_max_states,
        producer_max_work_bytes=args.producer_max_work_bytes,
        verifier_max_states=args.verifier_max_states,
        verifier_max_transitions=args.verifier_max_transitions,
        verifier_max_work_bytes=args.verifier_max_work_bytes,
        verifier_max_matrix_entries=args.verifier_max_matrix_entries,
        verifier_max_control_steps=args.verifier_max_control_steps,
        dp_max_states=args.dp_max_states,
        dp_max_work_bytes=args.dp_max_work_bytes,
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
