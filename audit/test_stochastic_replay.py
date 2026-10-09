#!/usr/bin/env python3
"""Focused tests for independent all-horizon bisimulation replay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_stochastic_certificate import replay_certificate
from stochastic_bisimulation import analyze


ROOT = Path(__file__).resolve().parent.parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def make_graph(*, different_usage=False, cyclic=False):
    right_template = "BBBB" if different_usage else "B"
    left_next = {"kind": "goto", "target": "left"} if cyclic else {"kind": "stop"}
    right_next = {"kind": "goto", "target": "right"} if cyclic else {"kind": "stop"}
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "stochastic_replay_case",
        "chars_per_token": 1,
        "inputs": {
            "query": {"type": "text", "label": "public", "max_tokens": 4},
            "secret": {"type": "boolean", "label": "secret"},
        },
        "models": {"m": {"provider": "offline", "model": "small", "max_tokens": 4}},
        "registers": {"answer": {"model": "m"}},
        "entry": "entry",
        "states": {
            "entry": {"calls": [], "next": {
                "kind": "secret", "guard": {"value": "secret"},
                "then": "left", "else": "right",
            }},
            "left": {"calls": [{
                "model": "m", "template": "A", "arguments": [{"value": "query"}],
                "result": "answer",
            }], "next": left_next},
            "right": {"calls": [{
                "model": "m", "template": right_template, "arguments": [{"value": "query"}],
                "result": "answer",
            }], "next": right_next},
        },
    }


def make_kernel():
    return {
        "format": "orchlang-finite-outcome-kernel",
        "version": 1,
        "defaults": {"m": [
            {"response": "x", "output_tokens": 1, "probability": "1/3"},
            {"response": "yy", "output_tokens": 2, "probability": "2/3"},
        ]},
        "rules": [],
    }


def make_history_case():
    graph = make_graph()
    graph["states"] = {
        "entry": {"calls": [], "next": {
            "kind": "secret", "guard": {"value": "secret"},
            "then": "left", "else": "right",
        }},
        "left": {"calls": [{
            "model": "m", "template": "A", "arguments": [{"value": "query"}],
            "result": "answer",
        }], "next": {"kind": "goto", "target": "follow"}},
        "right": {"calls": [{
            "model": "m", "template": "B", "arguments": [{"value": "query"}],
            "result": "answer",
        }], "next": {"kind": "goto", "target": "follow"}},
        "follow": {"calls": [{
            "model": "m", "template": "F", "arguments": [{"value": "answer"}],
            "result": "answer",
        }], "next": {"kind": "stop"}},
    }
    contract = {
        "provider": "offline", "model": "small", "max_tokens": 4,
        "has_unit_price": False, "unit_price": 0.0,
    }

    def event(template, argument, response):
        return {
            "contract": contract, "ordinal": 0, "template": template,
            "arguments": [argument], "response": response,
            "input_tokens": 2, "output_tokens": 1,
        }

    kernel = {
        "format": "orchlang-finite-outcome-kernel", "version": 1,
        "history_window": 1,
        "defaults": {"m": [
            {"response": "z", "output_tokens": 1, "probability": "1"},
        ]},
        "rules": [
            {"model": "m", "template": "A", "outcomes": [
                {"response": "x", "output_tokens": 1, "probability": "1"},
            ]},
            {"model": "m", "template": "B", "outcomes": [
                {"response": "y", "output_tokens": 1, "probability": "1"},
            ]},
            {"model": "m", "template": "F", "arguments": ["x"],
             "history": [event("A", "q", "x")], "outcomes": [
                {"response": "u", "output_tokens": 1, "probability": "1"},
            ]},
            {"model": "m", "template": "F", "arguments": ["y"],
             "history": [event("B", "q", "y")], "outcomes": [
                {"response": "v", "output_tokens": 1, "probability": "1"},
            ]},
        ],
    }
    return graph, kernel


class StochasticCertificateReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="orchlang-stochastic-replay-")
        cls.directory = Path(cls.temp.name)
        cls.graph = make_graph()
        cls.kernel = make_kernel()
        cls.public = {"query": "q"}
        cls.scenarios = [{"secret": False}, {"secret": True}]
        cls.graph_raw = canonical(cls.graph).encode("utf-8")
        cls.kernel_raw = canonical(cls.kernel).encode("utf-8")
        cls.graph_path = cls.directory / "graph.json"
        cls.kernel_path = cls.directory / "kernel.json"
        cls.graph_path.write_bytes(cls.graph_raw)
        cls.kernel_path.write_bytes(cls.kernel_raw)
        report = analyze(cls.graph, cls.kernel, cls.public, cls.scenarios)
        # analyze() hashes canonical documents; the same canonical bytes are
        # supplied to the independent raw-byte verifier.
        report["hashes"]["graph_sha256"] = digest(cls.graph_raw)
        report["hashes"]["kernel_sha256"] = digest(cls.kernel_raw)
        cls.report = report

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def replay(self, report=None, **kwargs):
        return replay_certificate(
            self.report if report is None else report,
            self.graph_raw, self.kernel_raw, **kwargs,
        )

    def test_equal_certificate_replays_full_closure_and_partition(self):
        result = self.replay(expected_public_store=self.public,
                             expected_secret_scenarios=self.scenarios)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["certificate_status"], "proved_equal")
        self.assertTrue(result["equal_laws_claim"])
        self.assertEqual(result["scenario_count"], 2)
        self.assertGreater(result["state_count"], 2)
        self.assertGreater(result["transition_count"], 0)
        self.assertIn("at every finite call horizon", result["claim_scope"])
        self.assertIn("not a real-provider", result["claim_scope"])

    def test_inconclusive_partition_is_verified_without_a_leakage_claim(self):
        graph = make_graph(different_usage=True)
        graph_raw = canonical(graph).encode("utf-8")
        report = analyze(graph, self.kernel, self.public, self.scenarios)
        report["hashes"]["graph_sha256"] = digest(graph_raw)
        result = replay_certificate(report, graph_raw, self.kernel_raw)
        self.assertEqual(report["status"], "inconclusive")
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["certificate_status"], "inconclusive")
        self.assertFalse(result["equal_laws_claim"])
        self.assertIn("not a leakage witness", result["claim_scope"])

    def test_productive_cycle_closes_and_replays(self):
        graph = make_graph(cyclic=True)
        graph_raw = canonical(graph).encode("utf-8")
        report = analyze(graph, self.kernel, self.public, self.scenarios)
        report["hashes"]["graph_sha256"] = digest(graph_raw)
        result = replay_certificate(report, graph_raw, self.kernel_raw,
                                    max_states=1000, max_work_bytes=32 * 1024 * 1024)
        self.assertEqual(report["status"], "proved_equal")
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["equal_laws_claim"])
        # The complete state includes saturated per-contract ordinals and
        # retained complete-event history; both contribute to finite closure.
        self.assertEqual(result["state_count"], 134)

    def test_history_dependent_kernel_closes_and_replays(self):
        graph, kernel = make_history_case()
        graph_raw = canonical(graph).encode("utf-8")
        kernel_raw = canonical(kernel).encode("utf-8")
        report = analyze(graph, kernel, self.public, self.scenarios)
        report["hashes"]["graph_sha256"] = digest(graph_raw)
        report["hashes"]["kernel_sha256"] = digest(kernel_raw)
        self.assertEqual(report["status"], "proved_equal")
        result = replay_certificate(report, graph_raw, kernel_raw)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["equal_laws_claim"])
        self.assertEqual(
            {event["template"] for state in report["closed_system"]["states"]
             for event in state["history"]},
            {"A", "B", "F"},
        )

    def test_public_and_secret_text_guard_paths_replay(self):
        graph = make_graph()
        graph["inputs"]["secret"] = {
            "type": "text", "label": "secret", "max_tokens": 4,
        }
        graph["states"] = {
            "entry": {"calls": [], "next": {
                "kind": "public", "guard": {"value": "query", "op": ">=", "limit": 2},
                "then": "check_secret", "else": "stop_public",
            }},
            "check_secret": {"calls": [], "next": {
                "kind": "secret", "guard": {"value": "secret", "op": ">", "limit": 1},
                "then": "long_secret", "else": "short_secret",
            }},
            "long_secret": {"calls": [{
                "model": "m", "template": "A", "arguments": [{"value": "query"}],
                "result": "answer",
            }], "next": {"kind": "stop"}},
            "short_secret": {"calls": [{
                "model": "m", "template": "B", "arguments": [{"value": "query"}],
                "result": "answer",
            }], "next": {"kind": "stop"}},
            "stop_public": {"calls": [], "next": {"kind": "stop"}},
        }
        public = {"query": "qq"}
        scenarios = [{"secret": "x"}, {"secret": "yy"}]
        graph_raw = canonical(graph).encode("utf-8")
        kernel_raw = canonical(make_kernel()).encode("utf-8")
        report = analyze(graph, make_kernel(), public, scenarios)
        report["hashes"]["graph_sha256"] = digest(graph_raw)
        report["hashes"]["kernel_sha256"] = digest(kernel_raw)
        self.assertEqual(report["status"], "proved_equal")
        result = replay_certificate(report, graph_raw, kernel_raw)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["equal_laws_claim"])

    def test_ordinal_and_history_saturation_cycle_replays(self):
        graph = make_graph(cyclic=True)
        kernel = {
            "format": "orchlang-finite-outcome-kernel", "version": 1,
            "history_window": 1,
            "defaults": {"m": [
                {"response": "x", "output_tokens": 1, "probability": "1/2"},
                {"response": "yy", "output_tokens": 2, "probability": "1/2"},
            ]},
            "rules": [{"model": "m", "ordinal": 32, "outcomes": [
                {"response": "z", "output_tokens": 2, "probability": "1"},
            ]}],
        }
        graph_raw = canonical(graph).encode("utf-8")
        kernel_raw = canonical(kernel).encode("utf-8")
        report = analyze(graph, kernel, self.public, self.scenarios)
        report["hashes"]["graph_sha256"] = digest(graph_raw)
        report["hashes"]["kernel_sha256"] = digest(kernel_raw)
        self.assertEqual(report["status"], "proved_equal")
        result = replay_certificate(report, graph_raw, kernel_raw,
                                    max_states=1000, max_work_bytes=32 * 1024 * 1024)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["equal_laws_claim"])
        self.assertGreater(result["state_count"], 100)

    def test_partition_id_and_row_order_are_representation_independent(self):
        changed = copy.deepcopy(self.report)
        states = changed["closed_system"]["states"]
        state_ids = {state["id"]: f"node-{index}" for index, state in enumerate(reversed(states))}
        block_rows = changed["partition_certificate"]["blocks"]
        block_ids = {block["id"]: f"part-{index}" for index, block in enumerate(reversed(block_rows))}
        for state in states:
            state["id"] = state_ids[state["id"]]
            state["block"] = block_ids[state["block"]]
        for edge in changed["closed_system"]["transitions"]:
            edge["from"] = state_ids[edge["from"]]
            edge["to"] = state_ids[edge["to"]]
        changed["closed_system"]["initial_state_ids"] = [
            state_ids[state_id] for state_id in changed["closed_system"]["initial_state_ids"]
        ]
        changed["closed_system"]["states"].reverse()
        changed["closed_system"]["transitions"].reverse()
        partition = changed["partition_certificate"]
        partition["initial_scenario_blocks"] = [
            block_ids[block_id] for block_id in partition["initial_scenario_blocks"]
        ]
        for block in partition["blocks"]:
            block["id"] = block_ids[block["id"]]
            block["states"] = [state_ids[state_id] for state_id in block["states"]]
            for item in block["signature"]:
                item["target_block"] = block_ids[item["target_block"]]
        partition["blocks"].reverse()
        self.assertEqual(self.replay(changed)["status"], "verified")

    def test_missing_edge_changed_usage_probability_and_partition_are_rejected(self):
        mutations = []
        changed = copy.deepcopy(self.report)
        changed["closed_system"]["transitions"].pop()
        changed["closed_system"]["transition_count"] -= 1
        mutations.append(("missing successor", changed))

        changed = copy.deepcopy(self.report)
        changed["closed_system"]["transitions"][0]["label"]["input_tokens"] += 1
        mutations.append(("changed usage", changed))

        changed = copy.deepcopy(self.report)
        changed["closed_system"]["transitions"][0]["probability"] = "1/2"
        mutations.append(("changed probability", changed))

        changed = copy.deepcopy(self.report)
        changed["partition_certificate"]["blocks"][0]["signature"] = []
        mutations.append(("unstable partition", changed))

        for label, report in mutations:
            with self.subTest(tampering=label):
                self.assertEqual(self.replay(report)["status"], "rejected")

    def test_wrong_hashes_and_missing_roots_are_rejected(self):
        for field in ("graph_sha256", "kernel_sha256", "public_store_sha256",
                      "secret_scenarios_sha256"):
            changed = copy.deepcopy(self.report)
            changed["hashes"][field] = "0" * 64
            with self.subTest(field=field):
                self.assertEqual(self.replay(changed)["status"], "rejected")

        changed = copy.deepcopy(self.report)
        changed["closed_system"]["initial_state_ids"].pop()
        self.assertEqual(self.replay(changed)["status"], "rejected")

        wrong_expected = self.replay(expected_public_store={"query": "other"})
        self.assertEqual(wrong_expected["status"], "rejected")

    def test_source_bytes_are_exactly_bound(self):
        changed_graph = self.graph_raw + b" "
        changed_kernel = self.kernel_raw + b" "
        self.assertEqual(replay_certificate(self.report, changed_graph, self.kernel_raw)["status"],
                         "rejected")
        self.assertEqual(replay_certificate(self.report, self.graph_raw, changed_kernel)["status"],
                         "rejected")

    def test_verifier_resource_exhaustion_and_producer_unknown_fail_closed(self):
        too_small = self.replay(max_states=1)
        self.assertEqual(too_small["status"], "unknown")
        self.assertFalse(too_small["equal_laws_claim"])

        byte_limited = self.replay(max_work_bytes=5_000)
        self.assertEqual(byte_limited["status"], "unknown")
        self.assertFalse(byte_limited["equal_laws_claim"])
        self.assertNotIn("state_count", byte_limited)

        unknown_report = analyze(self.graph, self.kernel, self.public, self.scenarios, max_states=1)
        unknown_report["hashes"]["graph_sha256"] = digest(self.graph_raw)
        unknown_report["hashes"]["kernel_sha256"] = digest(self.kernel_raw)
        result = self.replay(unknown_report)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["certificate_status"])
        self.assertFalse(result["equal_laws_claim"])

    def test_standalone_cli_accepts_a_bound_certificate(self):
        report_path = self.directory / "certificate.json"
        report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(ROOT / "audit" / "replay_stochastic_certificate.py"),
             str(report_path), str(self.graph_path), str(self.kernel_path),
             "--public-json", canonical(self.public),
             "--scenarios-json", canonical(self.scenarios)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        attestation = json.loads(completed.stdout)
        self.assertEqual(attestation["status"], "verified")
        self.assertTrue(attestation["equal_laws_claim"])

        malformed = subprocess.run(
            [sys.executable, str(ROOT / "audit" / "replay_stochastic_certificate.py"),
             str(report_path), str(self.graph_path), str(self.kernel_path),
             "--scenarios-json", "{malformed"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(malformed.returncode, 1)
        self.assertEqual(json.loads(malformed.stdout)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
