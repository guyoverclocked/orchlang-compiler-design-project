#!/usr/bin/env python3
"""Focused tests for independent exact trace-equivalence replay."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audit"))
from evaluate_probabilistic_channels import SCENARIOS, cases  # noqa: E402
from replay_trace_equivalence import replay_report  # noqa: E402
from trace_equivalence import analyze  # noqa: E402


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def find_case(name):
    for graph, kernel, public, _expected in cases():
        if graph["name"] == name:
            return graph, kernel, public
    raise AssertionError(f"missing authored channel case {name}")


class TraceEquivalenceReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph_path = ROOT / "examples/channels/trace_equal_not_bisimilar.graph.json"
        kernel_path = ROOT / "examples/channels/trace_equal_not_bisimilar.kernel.json"
        cls.equal_graph_raw = graph_path.read_bytes()
        cls.equal_kernel_raw = kernel_path.read_bytes()
        cls.equal_graph = json.loads(cls.equal_graph_raw.decode("utf-8"))
        cls.equal_kernel = json.loads(cls.equal_kernel_raw.decode("utf-8"))
        cls.public = {}
        cls.scenarios = [{"secret": False}, {"secret": True}]
        cls.equal_report = analyze(
            cls.equal_graph, cls.equal_kernel, cls.public, cls.scenarios,
            raw_graph=cls.equal_graph_raw, raw_kernel=cls.equal_kernel_raw,
        )

        cls.unequal_graph, cls.unequal_kernel, cls.unequal_public = find_case("noisy_usage_bit")
        cls.unequal_scenarios = [dict(row["values"]) for row in SCENARIOS]
        cls.unequal_graph_raw = canonical_bytes(cls.unequal_graph)
        cls.unequal_kernel_raw = canonical_bytes(cls.unequal_kernel)
        cls.unequal_report = analyze(
            cls.unequal_graph, cls.unequal_kernel, cls.unequal_public,
            cls.unequal_scenarios, raw_graph=cls.unequal_graph_raw,
            raw_kernel=cls.unequal_kernel_raw,
        )

    def test_equal_but_not_strongly_bisimilar_fixture_replays(self):
        self.assertEqual(self.equal_report["status"], "proved_equal")
        attestation = replay_report(
            self.equal_report, self.equal_graph_raw, self.equal_kernel_raw,
            expected_public_store=self.public,
            expected_secret_scenarios=self.scenarios,
        )
        self.assertEqual(attestation["status"], "verified")
        self.assertEqual(attestation["decision"], "proved_equal")
        self.assertTrue(attestation["all_finite_horizons_claim"])
        self.assertEqual(attestation["pair_count"], 1)

    def test_exact_unequal_witness_replays(self):
        self.assertEqual(self.unequal_report["status"], "unequal")
        attestation = replay_report(
            self.unequal_report, self.unequal_graph_raw, self.unequal_kernel_raw,
            expected_public_store=self.unequal_public,
            expected_secret_scenarios=self.unequal_scenarios,
        )
        self.assertEqual(attestation["status"], "verified")
        self.assertEqual(attestation["decision"], "unequal")
        self.assertFalse(attestation["all_finite_horizons_claim"])
        witness = attestation["verified_pairs"][0]
        self.assertNotEqual(witness["left_probability"], witness["right_probability"])

    def test_cap_unknown_has_no_partial_claim(self):
        unknown = analyze(
            self.equal_graph, self.equal_kernel, self.public, self.scenarios,
            max_states=1, raw_graph=self.equal_graph_raw,
            raw_kernel=self.equal_kernel_raw,
        )
        self.assertEqual(unknown["status"], "unknown")
        self.assertIsNone(unknown["closed_system"])
        self.assertIsNone(unknown["label_alphabet"])
        self.assertIsNone(unknown["result"])
        attestation = replay_report(unknown, self.equal_graph_raw, self.equal_kernel_raw)
        self.assertEqual(attestation["status"], "unknown")
        self.assertIsNone(attestation["decision"])
        self.assertFalse(attestation["all_finite_horizons_claim"])

    def test_verifier_matrix_cap_returns_unknown_without_partial_result(self):
        attestation = replay_report(
            self.equal_report, self.equal_graph_raw, self.equal_kernel_raw,
            max_matrix_entries=1,
        )
        self.assertEqual(attestation["status"], "unknown")
        self.assertIsNone(attestation["decision"])
        self.assertFalse(attestation["all_finite_horizons_claim"])

    def test_tampered_basis_row_is_rejected(self):
        report = copy.deepcopy(self.equal_report)
        row = report["result"]["pairs"][0]["basis"][0]["row"]
        row[0] = "1" if row[0] != "1" else "0"
        result = replay_report(report, self.equal_graph_raw, self.equal_kernel_raw)
        self.assertEqual(result["status"], "rejected")

    def test_tampered_span_claim_flag_is_rejected(self):
        report = copy.deepcopy(self.equal_report)
        report["result"]["pairs"][0]["closed_under_label_matrices"] = False
        result = replay_report(report, self.equal_graph_raw, self.equal_kernel_raw)
        self.assertEqual(result["status"], "rejected")

    def test_missing_closed_state_is_rejected(self):
        report = copy.deepcopy(self.equal_report)
        report["closed_system"]["states"].pop()
        report["closed_system"]["state_count"] -= 1
        result = replay_report(report, self.equal_graph_raw, self.equal_kernel_raw)
        self.assertEqual(result["status"], "rejected")

    def test_tampered_counterexample_probability_is_rejected(self):
        report = copy.deepcopy(self.unequal_report)
        witness = report["result"]["pairs"][0]["counterexample"]
        witness["left_probability"] = witness["right_probability"]
        result = replay_report(report, self.unequal_graph_raw, self.unequal_kernel_raw)
        self.assertEqual(result["status"], "rejected")

    def test_raw_graph_mismatch_is_rejected(self):
        changed = self.equal_graph_raw + b" "
        result = replay_report(self.equal_report, changed, self.equal_kernel_raw)
        self.assertEqual(result["status"], "rejected")

    def test_expected_secret_scenarios_are_bound(self):
        result = replay_report(
            self.equal_report, self.equal_graph_raw, self.equal_kernel_raw,
            expected_secret_scenarios=[{"secret": True}, {"secret": False}],
        )
        self.assertEqual(result["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
