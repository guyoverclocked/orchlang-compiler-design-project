#!/usr/bin/env python3
"""Tests for exact finite ordered usage-trace-law equivalence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit"
sys.path.insert(0, str(AUDIT))

from probabilistic_channels import canonical, producer_histogram  # noqa: E402
from replay_trace_equivalence import replay_report  # noqa: E402
from stochastic_bisimulation import analyze as analyze_bisimulation  # noqa: E402
from trace_equivalence import analyze  # noqa: E402


def fixture(name: str):
    graph_raw = (ROOT / "examples" / "channels" / f"{name}.graph.json").read_bytes()
    kernel_raw = (ROOT / "examples" / "channels" / f"{name}.kernel.json").read_bytes()
    return (json.loads(graph_raw), json.loads(kernel_raw), graph_raw, kernel_raw)


def scenarios():
    return [{"secret": False}, {"secret": True}]


def stopped_vs_live_fixture():
    graph = {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "stopped_vs_live",
        "chars_per_token": 4,
        "inputs": {"secret": {"type": "boolean", "label": "secret"}},
        "models": {"m": {"provider": "offline", "model": "stop-test", "max_tokens": 2}},
        "registers": {"r": {"model": "m"}},
        "entry": "choose",
        "states": {
            "choose": {"calls": [], "next": {
                "kind": "secret", "guard": {"value": "secret"},
                "then": "stopped", "else": "call",
            }},
            "stopped": {"calls": [], "next": {"kind": "stop"}},
            "call": {"calls": [{"model": "m", "template": "Q",
                                   "arguments": [], "result": "r"}],
                     "next": {"kind": "stop"}},
        },
    }
    kernel = {
        "format": "orchlang-finite-outcome-kernel",
        "version": 1,
        "history_window": 0,
        "defaults": {"m": [{"response": "x", "output_tokens": 1,
                             "probability": "1"}]},
    }
    return graph, kernel


class TraceEquivalenceTests(unittest.TestCase):
    def test_equal_trace_law_even_when_strong_bisimulation_splits(self):
        graph, kernel, graph_raw, kernel_raw = fixture("trace_equal_not_bisimilar")
        report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                         raw_kernel=kernel_raw)
        self.assertEqual(report["status"], "proved_equal")
        self.assertEqual(report["claim"],
                         "exact all-finite-horizon success-only ordered usage-trace laws for every supplied secret scenario under the declared finite rational kernel")
        pair = report["result"]["pairs"][0]
        self.assertEqual(pair["status"], "equal")
        self.assertGreater(pair["rank"], 0)
        self.assertTrue(pair["closed_under_label_matrices"])
        self.assertTrue(pair["stop_outputs_zero"])
        self.assertTrue(pair["nonterminal_outputs_zero"])

        strong = analyze_bisimulation(graph, kernel, {}, scenarios())
        self.assertEqual(strong["status"], "inconclusive")

        # The independent finite-horizon DP confirms selected prefixes; the
        # new row-space proof covers every finite horizon under this kernel.
        for horizon in (1, 2, 3):
            rows = [producer_histogram(graph, kernel, {**scenario}, horizon,
                                       observer="trace")
                    for scenario in scenarios()]
            self.assertTrue(all(row["status"] == "complete" for row in rows))
            self.assertEqual(rows[0]["histogram"], rows[1]["histogram"])
            self.assertEqual(rows[0]["mass"], rows[1]["mass"])

        replay = replay_report(report, graph_raw, kernel_raw,
                               expected_public_store={},
                               expected_secret_scenarios=scenarios())
        self.assertEqual(replay["status"], "verified")
        self.assertEqual(replay["decision"], "proved_equal")
        self.assertTrue(replay["all_finite_horizons_claim"])

    def test_authored_finite_counterexample_is_exact_and_replayable(self):
        graph, kernel, graph_raw, kernel_raw = fixture("noisy_usage_bit")
        report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                         raw_kernel=kernel_raw)
        self.assertEqual(report["status"], "unequal")
        pair, = report["result"]["pairs"]
        self.assertEqual((pair["left_scenario"], pair["right_scenario"]), (1, 0))
        self.assertEqual(len(pair["counterexample"]["word"]), 1)
        self.assertEqual(pair["counterexample"]["word"][0]["input_tokens"], 1)
        self.assertEqual(pair["counterexample"]["word"][0]["output_tokens"], 1)
        self.assertEqual(pair["counterexample"]["end_kind"], "stop")
        self.assertEqual(pair["counterexample"]["left_probability"], "3/4")
        self.assertEqual(pair["counterexample"]["right_probability"], "1/4")
        replay = replay_report(report, graph_raw, kernel_raw)
        self.assertEqual(replay["status"], "verified")
        self.assertFalse(replay["all_finite_horizons_claim"])

        tampered = copy.deepcopy(report)
        tampered["result"]["pairs"][0]["counterexample"]["left_probability"] = "1/2"
        self.assertEqual(replay_report(tampered, graph_raw, kernel_raw)["status"],
                         "rejected")

    def test_ordered_usage_witness_detects_aggregate_order_leak(self):
        graph, kernel, graph_raw, kernel_raw = fixture("aggregate_hides_order")
        report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                         raw_kernel=kernel_raw)
        self.assertEqual(report["status"], "unequal")
        witness = report["result"]["pairs"][0]["counterexample"]
        self.assertEqual(len(witness["word"]), 1)
        self.assertEqual(witness["end_kind"], "nonterminal")
        self.assertNotEqual(witness["left_probability"], witness["right_probability"])
        replay = replay_report(report, graph_raw, kernel_raw)
        self.assertEqual(replay["status"], "verified")

        trace_rows = [producer_histogram(graph, kernel, scenario, 2,
                                         observer="trace") for scenario in scenarios()]
        aggregate_rows = [producer_histogram(graph, kernel, scenario, 2,
                                             observer="aggregate") for scenario in scenarios()]
        self.assertNotEqual(trace_rows[0]["histogram"], trace_rows[1]["histogram"])
        self.assertEqual(aggregate_rows[0]["histogram"], aggregate_rows[1]["histogram"])

    def test_epsilon_witness_distinguishes_stop_from_live_prefix(self):
        graph, kernel = stopped_vs_live_fixture()
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report["status"], "unequal")
        witness = report["result"]["pairs"][0]["counterexample"]
        self.assertEqual(witness["word"], [])
        self.assertEqual(witness["end_kind"], "stop")
        self.assertEqual((witness["left_probability"], witness["right_probability"]),
                         ("1", "0"))
        replay = replay_report(report, canonical(graph).encode(),
                               canonical(kernel).encode())
        self.assertEqual(replay["status"], "verified")

    def test_equal_certificate_tampering_is_rejected(self):
        graph, kernel, graph_raw, kernel_raw = fixture("trace_equal_not_bisimilar")
        report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                         raw_kernel=kernel_raw)
        tampered = copy.deepcopy(report)
        tampered["result"]["pairs"][0]["basis"].pop()
        replay = replay_report(tampered, graph_raw, kernel_raw)
        self.assertEqual(replay["status"], "rejected")

    def test_unknown_is_fail_closed_and_replays_as_unknown(self):
        graph, kernel, graph_raw, kernel_raw = fixture("trace_equal_not_bisimilar")
        for options in ({"max_states": 1}, {"max_work_bytes": 1},
                        {"max_matrix_entries": 1}, {"max_rational_bits": 1}):
            with self.subTest(options=options):
                report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                                 raw_kernel=kernel_raw, **options)
                self.assertEqual(report["status"], "unknown")
                self.assertIsNone(report["claim"])
                self.assertIsNone(report["closed_system"])
                self.assertIsNone(report["label_alphabet"])
                self.assertIsNone(report["result"])
                self.assertEqual(replay_report(report, graph_raw, kernel_raw)["status"],
                                 "unknown")

    def test_invalid_inputs_and_bad_source_binding_fail_closed(self):
        graph, kernel, graph_raw, kernel_raw = fixture("trace_equal_not_bisimilar")
        duplicate = analyze(graph, kernel, {}, [{"secret": False}, {"secret": False}])
        self.assertEqual(duplicate["status"], "invalid")
        self.assertIsNone(duplicate["closed_system"])
        self.assertEqual(replay_report(duplicate, graph_raw, kernel_raw)["status"],
                         "rejected")

        bad_raw = analyze(graph, kernel, {}, scenarios(), raw_graph="not bytes")
        self.assertEqual(bad_raw["status"], "invalid")
        self.assertIsNone(bad_raw["closed_system"])

        other_graph_raw = (ROOT / "examples/channels/noisy_usage_bit.graph.json").read_bytes()
        mismatched_source = analyze(graph, kernel, {}, scenarios(),
                                   raw_graph=other_graph_raw, raw_kernel=kernel_raw)
        self.assertEqual(mismatched_source["status"], "invalid")
        self.assertIsNone(mismatched_source["closed_system"])

    def test_different_modeled_requests_can_have_equal_usage_laws(self):
        graph, kernel, graph_raw, kernel_raw = fixture("different_requests_equal_usage")
        report = analyze(graph, kernel, {}, scenarios(), raw_graph=graph_raw,
                         raw_kernel=kernel_raw)
        self.assertEqual(report["status"], "proved_equal")
        self.assertEqual({label["input_tokens"] for label in report["label_alphabet"]}, {1})
        self.assertEqual({label["output_tokens"] for label in report["label_alphabet"]}, {1, 2})
        replay = replay_report(report, graph_raw, kernel_raw)
        self.assertEqual(replay["status"], "verified")

    def test_cli_exit_codes_and_report_file(self):
        graph_path = ROOT / "examples" / "channels" / "trace_equal_not_bisimilar.graph.json"
        kernel_path = ROOT / "examples" / "channels" / "trace_equal_not_bisimilar.kernel.json"
        command = [sys.executable, str(AUDIT / "trace_equivalence.py"),
                   str(graph_path), str(kernel_path), "--public-json", "{}",
                   "--scenarios-json", '[{"secret":false},{"secret":true}]']
        equal = subprocess.run(command, capture_output=True, check=False, text=True)
        self.assertEqual(equal.returncode, 0, equal.stderr)
        self.assertEqual(json.loads(equal.stdout)["status"], "proved_equal")
        limited = subprocess.run(command + ["--max-states", "1"], capture_output=True,
                                 check=False, text=True)
        self.assertEqual(limited.returncode, 3, limited.stderr)
        self.assertEqual(json.loads(limited.stdout)["status"], "unknown")
        invalid = subprocess.run(
            command[:-1] + ['[{"secret":false},{"secret":false}]'],
            capture_output=True, check=False, text=True,
        )
        self.assertEqual(invalid.returncode, 2, invalid.stderr)
        self.assertEqual(json.loads(invalid.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
