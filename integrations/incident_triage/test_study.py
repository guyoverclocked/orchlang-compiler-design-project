"""Focused standard-library tests for the pinned source execution study."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import unittest

from run_study import StudyError, run_study
from verify_results import VerificationError, verify_report


UPSTREAM = os.environ.get("INCIDENT_TRIAGE_UPSTREAM")


@unittest.skipUnless(UPSTREAM, "set INCIDENT_TRIAGE_UPSTREAM to the pinned clean checkout")
class IncidentTriageSourceStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_study(Path(UPSTREAM))
        cls.cases = {row["case_id"]: row for row in cls.report["cases"]}

    def test_verified_report_and_source_binding(self):
        checked = verify_report(self.report)
        self.assertEqual(checked["status"], "verified")
        self.assertEqual(checked["case_count"], 22)
        self.assertEqual(checked["call_count"], 45)
        self.assertEqual(checked["source_node_invocations"], 87)
        self.assertEqual(self.report["source"]["license"], "MIT")
        self.assertTrue(self.report["source"]["verified_before_and_after_execution"])

    def test_redacted_pii_pairs_match_full_traces_and_costs(self):
        for kind in ("email", "phone", "national_insurance"):
            left = self.cases[f"pii_{kind}_a"]
            right = self.cases[f"pii_{kind}_b"]
            self.assertNotEqual(left["input"]["text"], right["input"]["text"])
            self.assertEqual(left["source_redacted_text"], right["source_redacted_text"])
            self.assertEqual(left["calls"], right["calls"])
            self.assertEqual(left["usage"], right["usage"])
            self.assertEqual(left["node_events"], right["node_events"])
            self.assertEqual(left["terminal"], right["terminal"])

    def test_source_retry_generates_equal_repair_requests(self):
        left = self.cases["retry_email_a"]
        right = self.cases["retry_email_b"]
        self.assertEqual(len(left["calls"]), 3)
        self.assertEqual(left["calls"], right["calls"])
        self.assertIn("failed validation", left["calls"][1]["user"].lower())
        self.assertEqual([row["node"] for row in left["usage"]],
                         ["classify", "classify", "draft"])

    def test_presence_count_and_type_are_not_mistaken_for_value_substitution(self):
        for left_id, right_id in (
            ("pii_presence_absent", "pii_presence_present"),
            ("pii_count_one", "pii_count_two"),
            ("pii_type_email", "pii_type_phone"),
        ):
            left, right = self.cases[left_id], self.cases[right_id]
            self.assertEqual({k: v for k, v in left["input"].items() if k != "text"},
                             {k: v for k, v in right["input"].items() if k != "text"})
            self.assertNotEqual(left["source_redacted_text"], right["source_redacted_text"])
            self.assertNotEqual(left["calls"][0]["user"], right["calls"][0]["user"])

    def test_upstream_default_factory_uses_same_deterministic_mock(self):
        injected = self.cases["public_text_a"]
        default = self.cases["upstream_default_mock"]
        self.assertEqual(default["execution_mode"], "upstream_default_mock")
        self.assertEqual(injected["input"], default["input"])
        self.assertEqual(injected["calls"], default["calls"])
        self.assertEqual(injected["usage"], default["usage"])
        self.assertEqual(injected["node_events"], default["node_events"])

    def test_public_content_and_unlisted_names_remain_observable(self):
        self.assertNotEqual(self.cases["public_text_a"]["calls"],
                            self.cases["public_text_b"]["calls"])
        self.assertNotEqual(self.cases["unlisted_name_a"]["calls"],
                            self.cases["unlisted_name_b"]["calls"])
        self.assertIn("Jane Example", self.cases["unlisted_name_a"]["calls"][0]["user"])
        self.assertIn("Alex Example", self.cases["unlisted_name_b"]["calls"][0]["user"])

    def test_unknown_site_route_skips_draft_and_dispatch(self):
        case = self.cases["unknown_site_route"]
        nodes = [row["name"] for row in case["node_events"] if row["kind"] == "node"]
        self.assertEqual(nodes, ["classify", "enrich", "human_review"])
        self.assertEqual([row["node"] for row in case["usage"]], ["classify"])
        self.assertEqual(case["terminal"]["kind"], "human_review")

    def test_source_mock_placeholder_effect_is_explicitly_local(self):
        self.assertEqual(self.cases["mock_marker_absent"]["terminal"]["classification"]["category"],
                         "operational")
        self.assertEqual(self.cases["mock_marker_present"]["terminal"]["classification"]["category"],
                         "cyber")
        self.assertIn("[EMAIL]", self.cases["mock_marker_present"]["calls"][0]["user"])

    def test_independent_verifier_rejects_tampered_cost(self):
        tampered = copy.deepcopy(self.report)
        tampered["cases"][0]["usage"][0]["input_tokens"] += 1
        with self.assertRaises(VerificationError):
            verify_report(tampered)

    def test_independent_verifier_rejects_tampered_source_prompt(self):
        tampered = copy.deepcopy(self.report)
        tampered["cases"][0]["calls"][0]["user"] += " altered"
        with self.assertRaises(VerificationError):
            verify_report(tampered)

    def test_independent_verifier_rejects_tampered_redaction(self):
        tampered = copy.deepcopy(self.report)
        tampered["cases"][0]["source_redacted_text"] += " forged"
        with self.assertRaises(VerificationError):
            verify_report(tampered)

    def test_unmodified_checkout_is_required(self):
        with self.assertRaises((StudyError, OSError)):
            run_study(Path("/definitely/not/an/upstream/checkout"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
