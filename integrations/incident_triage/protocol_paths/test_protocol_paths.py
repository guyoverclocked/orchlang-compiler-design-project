"""Focused tests for selected pinned-source protocol paths and the verifier."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import unittest

from verify_protocol_paths import ProtocolPathsVerificationError, verify_report


HERE = Path(__file__).resolve().parent
REPORT_PATH = HERE / "results" / "protocol_paths.json"
UPSTREAM = Path(os.environ.get("INCIDENT_TRIAGE_UPSTREAM", "/tmp/incident-triage-offline-clone"))


@unittest.skipUnless(UPSTREAM.is_dir(), "set INCIDENT_TRIAGE_UPSTREAM to the clean pinned source checkout")
class ProtocolPathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        cls.attestation = verify_report(cls.report, UPSTREAM)
        cls.runs = {row["case_id"]: row for row in cls.report["runs"]}

    def test_independent_replay_accepts_all_six_path_pairs(self):
        self.assertEqual(self.attestation["status"], "verified")
        self.assertEqual((self.attestation["path_count"], self.attestation["pair_count"],
                          self.attestation["run_count"], self.attestation["call_count"]),
                         (6, 6, 12, 24))
        self.assertEqual(self.attestation["pair_relations"], ["equal"] * 6)

    def test_double_schema_failure_keeps_tracker_rows_when_state_costs_are_absent(self):
        run = self.runs["double_schema_failure_a"]
        self.assertFalse(run["state_costs_present"])
        self.assertEqual(run["state_cost_rows"], [])
        self.assertEqual(len(run["tracker_rows"]), 2)
        self.assertEqual([row["node"] for row in run["tracker_rows"]], ["classify", "classify"])
        self.assertEqual(run["terminal"]["kind"], "human_review")
        self.assertIn("schema validation", run["terminal"]["error"])

    def test_295_character_schema_valid_summary_flows_into_draft_request(self):
        run = self.runs["long_summary_a"]
        summary = run["terminal"]["classification"]["summary"]
        self.assertEqual(len(summary), 295)
        self.assertIn(f"summary: {summary}", run["calls"][-1]["user"])
        self.assertEqual(len(run["tracker_rows"]), 2)

    def test_invalid_draft_json_uses_source_fallback_action(self):
        run = self.runs["draft_json_fallback_a"]
        self.assertEqual(run["calls"][-1]["response"]["text"], "not-json")
        self.assertEqual(run["terminal"]["recommended_actions"],
                         ["Review incident manually; drafting agent returned invalid output"])
        self.assertEqual(run["terminal"]["report_status"], "pending_approval")

    def test_critical_site_bumps_low_priority_from_p4_to_p3(self):
        run = self.runs["critical_site_bump_a"]
        self.assertEqual(run["terminal"]["enrichment"]["site_criticality"], "critical")
        self.assertEqual(run["terminal"]["priority"]["level"], "P3")
        self.assertEqual(run["terminal"]["priority"]["response_sla_minutes"], 240)

    def test_leading_space_budget_probe_stops_before_action_request(self):
        run = self.runs["budget_guard_a"]
        self.assertEqual(run["calls"][0]["response"]["space_count"], 400_000)
        self.assertGreater(run["tracker_rows"][0]["cost_usd"], 0.05)
        self.assertEqual(len(run["calls"]), 1)
        self.assertEqual(run["terminal"]["kind"], "human_review")
        self.assertIn("cost budget exceeded", run["terminal"]["error"])
        self.assertFalse(any(call["node"] == "draft" for call in run["calls"]))

    def test_all_six_pairs_have_equal_selected_observations(self):
        for pair in self.report["pairs"]:
            self.assertEqual(pair["observed_relation"], "equal")
            left, right = self.runs[pair["left"]], self.runs[pair["right"]]
            self.assertNotEqual(left["input"]["text"], right["input"]["text"])
            self.assertEqual(left["source_redacted_text"], right["source_redacted_text"])
            for key in ("calls", "tracker_rows", "state_cost_rows", "node_events", "terminal"):
                self.assertEqual(left[key], right[key])

    def test_verifier_rejects_tampered_request_and_tracker_cost(self):
        altered = copy.deepcopy(self.report)
        altered["runs"][0]["calls"][0]["user"] += " altered"
        with self.assertRaises(ProtocolPathsVerificationError):
            verify_report(altered, UPSTREAM)
        altered = copy.deepcopy(self.report)
        altered["runs"][0]["calls"][0]["response"]["text"] = "tampered outcome"
        with self.assertRaises(ProtocolPathsVerificationError):
            verify_report(altered, UPSTREAM)
        altered = copy.deepcopy(self.report)
        altered["runs"][0]["tracker_rows"][0]["input_tokens"] += 1
        with self.assertRaises(ProtocolPathsVerificationError):
            verify_report(altered, UPSTREAM)

    def test_verifier_rejects_tampered_terminal_route_or_source_hash(self):
        altered = copy.deepcopy(self.report)
        altered["runs"][0]["terminal"]["kind"] = "human_review"
        with self.assertRaises(ProtocolPathsVerificationError):
            verify_report(altered, UPSTREAM)
        altered = copy.deepcopy(self.report)
        path = next(iter(altered["source"]["tracked_file_sha256_after"]))
        altered["source"]["tracked_file_sha256_after"][path] = "0" * 64
        with self.assertRaises(ProtocolPathsVerificationError):
            verify_report(altered, UPSTREAM)

    def test_verifier_is_standard_library_only_and_does_not_import_producer(self):
        source = Path(__file__).with_name("verify_protocol_paths.py").read_text(encoding="utf-8")
        for forbidden in ("import run_protocol_paths", "import triage", "import langgraph", "import pydantic"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
