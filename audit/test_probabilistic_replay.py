#!/usr/bin/env python3
"""Focused tests for independent finite-channel report replay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_probabilistic_report as verifier
from replay_probabilistic_report import replay_report


REPO = Path(__file__).resolve().parent.parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_inputs():
    graph = {
        "format": "orchlang-request-graph", "version": 1, "name": "replay_demo",
        "chars_per_token": 1,
        "inputs": {
            "query": {"type": "text", "label": "public", "max_tokens": 4},
            "route": {"type": "boolean", "label": "secret"},
        },
        "registers": {"answer": {"model": "m"}},
        "models": {"m": {"provider": "offline", "model": "small", "max_tokens": 4}},
        "states": {
            "entry": {"calls": [], "next": {
                "kind": "secret", "guard": {"value": "route"},
                "then": "left", "else": "right",
            }},
            "left": {"calls": [{"model": "m", "template": "t",
                                  "arguments": [{"value": "query"}, {"literal": "x"}],
                                  "result": "answer"}], "next": {"kind": "stop"}},
            "right": {"calls": [{"model": "m", "template": "t",
                                   "arguments": [{"value": "query"}, {"literal": "y"}],
                                   "result": "answer"}], "next": {"kind": "stop"}},
        },
        "entry": "entry",
    }
    kernel = {
        "format": "orchlang-finite-outcome-kernel", "version": 1,
        "history_window": 0,
        "defaults": {"m": [
            {"response": "a", "output_tokens": 1, "probability": "1/2"},
            {"response": "bb", "output_tokens": 2, "probability": "1/2"},
        ]},
        "rules": [
            {"model": "m", "arguments": ["q", "x"], "outcomes": [
                {"response": "a", "output_tokens": 1, "probability": "1/3"},
                {"response": "bb", "output_tokens": 2, "probability": "2/3"},
            ]},
            {"model": "m", "arguments": ["q", "y"], "outcomes": [
                {"response": "a", "output_tokens": 1, "probability": "2/3"},
                {"response": "bb", "output_tokens": 2, "probability": "1/3"},
            ]},
        ],
    }
    public_store = {"query": "q"}
    secret_scenarios = [
        {"values": {"route": True}, "prior": "1/2"},
        {"values": {"route": False}, "prior": "1/2"},
    ]
    return graph, kernel, public_store, secret_scenarios


class ProbabilisticReportReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="orchlang-channel-replay-")
        cls.directory = Path(cls.temp.name)
        graph, kernel, public, scenarios = make_inputs()
        cls.graph_raw = (json.dumps(graph, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        cls.kernel_raw = (json.dumps(kernel, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        cls.graph_path = cls.directory / "graph.json"
        cls.kernel_path = cls.directory / "kernel.json"
        write_json(cls.graph_path, graph)
        write_json(cls.kernel_path, kernel)
        command = [
            sys.executable, str(REPO / "audit" / "probabilistic_channels.py"),
            str(cls.graph_path), str(cls.kernel_path),
            "--public-json", canonical(public),
            "--scenarios-json", canonical(scenarios),
            "--horizon", "1", "--max-states", "10000",
            "--max-work-bytes", str(64 * 1024 * 1024),
            "--observer", "aggregate",
        ]
        completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise AssertionError(f"candidate producer failed: {completed.stderr}\n{completed.stdout}")
        cls.report_raw = completed.stdout.encode("utf-8")
        cls.report = json.loads(completed.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def replay(self, report=None, *, graph_raw=None, kernel_raw=None, **kwargs):
        return replay_report(self.report if report is None else report,
                             self.graph_raw if graph_raw is None else graph_raw,
                             self.kernel_raw if kernel_raw is None else kernel_raw,
                             **kwargs)

    def test_producer_report_replays_and_attestation_limits_claim(self):
        attestation = replay_report(self.report_raw, self.graph_raw, self.kernel_raw)
        self.assertEqual(attestation["status"], "verified")
        self.assertEqual(attestation["verification_method"], "independent finite DFS re-execution")
        self.assertIn("not a general proof", attestation["claim_scope"])
        self.assertEqual(attestation["scenario_rows_verified"], 2)
        self.assertEqual(attestation["observer"], "aggregate")
        self.assertEqual(attestation["horizon"], 1)
        self.assertIn("rows[*].state_visits", " ".join(attestation["unverified_fields"]))

    def test_standalone_cli_replays_a_bound_report(self):
        report_path = self.directory / "candidate-report.json"
        report_path.write_bytes(self.report_raw)
        completed = subprocess.run(
            [sys.executable, str(REPO / "audit" / "replay_probabilistic_report.py"),
             str(report_path), str(self.graph_path), str(self.kernel_path)],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        attestation = json.loads(completed.stdout)
        self.assertEqual(attestation["status"], "verified")
        self.assertEqual(attestation["verification_method"], "independent finite DFS re-execution")

    def test_report_hashes_bind_raw_sources_and_canonical_scenario_inputs(self):
        changed_graph = self.graph_raw + b" "
        changed_kernel = self.kernel_raw + b" "
        with self.subTest(source="graph"):
            self.assertEqual(self.replay(graph_raw=changed_graph)["status"], "rejected")
        with self.subTest(source="kernel"):
            self.assertEqual(self.replay(kernel_raw=changed_kernel)["status"], "rejected")
        for field in ("public_store_sha256", "secret_scenarios_sha256"):
            changed = copy.deepcopy(self.report)
            changed[field] = "0" * 64
            with self.subTest(field=field):
                self.assertEqual(self.replay(changed)["status"], "rejected")

    def test_scope_declaration_is_checked_against_supported_report_contracts(self):
        changed = copy.deepcopy(self.report)
        changed["scope"] = "unbounded provider billing and user adoption proven"
        self.assertEqual(self.replay(changed)["status"], "rejected")

    def test_histogram_mass_observation_and_row_budget_tampering_are_rejected(self):
        mutations = []
        changed = copy.deepcopy(self.report)
        changed["rows"][0]["histogram"][0]["probability"] = "1"
        mutations.append(("probability", changed))

        changed = copy.deepcopy(self.report)
        changed["rows"][0]["histogram"][0]["observation"]["billing"][0]["input_tokens"] += 1
        mutations.append(("observation", changed))

        changed = copy.deepcopy(self.report)
        changed["rows"][0]["mass"] = "2"
        mutations.append(("mass", changed))

        changed = copy.deepcopy(self.report)
        changed["rows"][0]["observer"] = "trace"
        mutations.append(("observer", changed))

        changed = copy.deepcopy(self.report)
        changed["rows"][0]["horizon"] += 1
        mutations.append(("horizon", changed))

        changed = copy.deepcopy(self.report)
        changed["rows"][0]["max_work_bytes"] -= 1
        mutations.append(("row budget", changed))

        for label, report in mutations:
            with self.subTest(tampering=label):
                self.assertEqual(self.replay(report)["status"], "rejected")

    def test_singleton_duplicate_and_incomplete_secret_scenarios_are_rejected(self):
        singleton = copy.deepcopy(self.report)
        singleton["secret_scenarios"] = singleton["secret_scenarios"][:1]
        singleton["rows"] = singleton["rows"][:1]
        singleton["priors"] = singleton["priors"][:1]
        singleton["secret_scenarios_sha256"] = digest(singleton["secret_scenarios"])
        self.assertEqual(self.replay(singleton)["status"], "rejected")

        duplicate = copy.deepcopy(self.report)
        duplicate["secret_scenarios"][1]["values"] = copy.deepcopy(
            duplicate["secret_scenarios"][0]["values"])
        duplicate["secret_scenarios_sha256"] = digest(duplicate["secret_scenarios"])
        self.assertEqual(self.replay(duplicate)["status"], "rejected")

        missing = copy.deepcopy(self.report)
        missing["secret_scenarios"][1]["values"] = {}
        missing["secret_scenarios_sha256"] = digest(missing["secret_scenarios"])
        self.assertEqual(self.replay(missing)["status"], "rejected")

    def test_priors_require_exact_positive_unit_mass(self):
        changed = copy.deepcopy(self.report)
        changed["secret_scenarios"][0]["prior"] = "1/3"
        changed["secret_scenarios"][1]["prior"] = "1/3"
        changed["priors"] = ["1/3", "1/3"]
        changed["secret_scenarios_sha256"] = digest(changed["secret_scenarios"])
        self.assertEqual(self.replay(changed)["status"], "rejected")

        float_prior = copy.deepcopy(self.report)
        float_prior["secret_scenarios"][0]["prior"] = 0.5
        float_prior["secret_scenarios_sha256"] = digest(float_prior["secret_scenarios"])
        self.assertEqual(self.replay(float_prior)["status"], "rejected")

    def test_exact_leakage_metric_tampering_is_rejected(self):
        changed_tv = copy.deepcopy(self.report)
        changed_tv["metrics"]["pairwise"][0]["total_variation"] = "0"
        self.assertEqual(self.replay(changed_tv)["status"], "rejected")

        changed_vulnerability = copy.deepcopy(self.report)
        changed_vulnerability["metrics"]["bayes_vulnerability"] = "1/2"
        self.assertEqual(self.replay(changed_vulnerability)["status"], "rejected")

        changed_expression = copy.deepcopy(self.report)
        changed_expression["metrics"]["mutual_information_exact_expression"]["terms"][0]["coefficient"] = "1/7"
        self.assertEqual(self.replay(changed_expression)["status"], "rejected")

    def test_approximate_log_fields_are_not_treated_as_verified_facts(self):
        changed = copy.deepcopy(self.report)
        changed["metrics"]["pairwise"][0]["maximum_log_likelihood_ratio_nats_approx"] = -123.0
        changed["metrics"]["min_entropy_leakage_bits_approx"] = 987.0
        changed["metrics"]["mutual_information_bits_approx"] = 456.0
        attestation = self.replay(changed)
        self.assertEqual(attestation["status"], "verified")
        self.assertTrue(any("approx" in field for field in attestation["unverified_fields"]))

    def test_scenario_row_and_prior_order_do_not_change_exact_mi_verification(self):
        changed = copy.deepcopy(self.report)
        changed["secret_scenarios"].reverse()
        changed["rows"].reverse()
        changed["priors"].reverse()
        changed["secret_scenarios_sha256"] = digest(changed["secret_scenarios"])
        attestation = self.replay(changed)
        self.assertEqual(attestation["status"], "verified")
        self.assertIn("exact mutual-information symbolic terms (multiset comparison)",
                      attestation["verified_exact_metrics"])

    def test_dfs_resource_exhaustion_returns_unknown_not_verified(self):
        attestation = self.replay(max_reference_paths=1)
        self.assertEqual(attestation["status"], "unknown")
        self.assertIn("path limit", attestation["diagnostic"])

        byte_limited = self.replay(max_reference_work_bytes=1)
        self.assertEqual(byte_limited["status"], "unknown")
        self.assertNotIn("verified_exact_metrics", byte_limited)

    def test_verifier_read_and_exact_integer_limits_return_unknown(self):
        with patch.object(verifier, "MAX_SOURCE_BYTES", len(self.graph_raw) - 1):
            oversized_source = self.replay()
        self.assertEqual(oversized_source["status"], "unknown")
        self.assertIn("read limit", oversized_source["diagnostic"])

        resource_error = ValueError(
            "Exceeds the limit (4300 digits) for integer string conversion"
        )
        with patch.object(verifier, "independent_histogram", side_effect=resource_error):
            oversized_exact_arithmetic = self.replay()
        self.assertEqual(oversized_exact_arithmetic["status"], "unknown")
        self.assertIn("exact-integer resource limit", oversized_exact_arithmetic["diagnostic"])

        denominator = 10 ** 999
        kernel = {"defaults": {"m": [
            {"probability": f"1/{denominator}"},
            {"probability": f"{denominator - 1}/{denominator}"},
        ]}, "rules": []}
        with self.assertRaises(verifier.ReportReplayLimit):
            verifier._check_path_probability_growth(kernel, 3)

    def test_report_with_unknown_producer_row_stays_unknown(self):
        changed = copy.deepcopy(self.report)
        changed["rows"][0] = {"status": "unknown"}
        self.assertEqual(self.replay(changed)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
