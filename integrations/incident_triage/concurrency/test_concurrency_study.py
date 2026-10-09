from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify_concurrency_study import VerificationError, verify_report


HERE = Path(__file__).resolve().parent
UPSTREAM = Path(os.environ.get("INCIDENT_TRIAGE_UPSTREAM",
                              "/tmp/agent-incident-triage-research"))


class ConcurrencyStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory(prefix="incident-tracker-race-")
        cls.generated = Path(cls.tempdir.name) / "concurrency_study.json"
        subprocess.run(
            [sys.executable, str(HERE / "run_concurrency_study.py"),
             "--upstream", str(UPSTREAM), "--output", str(cls.generated)],
            check=True, stdout=subprocess.DEVNULL,
        )
        cls.report = json.loads(cls.generated.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tempdir.cleanup()

    def test_controlled_schedule_exposes_tracker_contamination(self) -> None:
        result = verify_report(self.report, UPSTREAM)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["shared_app"]["A_cost_rows"], 4)
        self.assertEqual(result["shared_app"]["B_cost_rows"], 2)
        self.assertEqual(result["shared_app"]["A_classifier_recorded_as"], "draft")
        self.assertEqual(result["shared_app"]["unique_call_tokens"], 456)
        self.assertEqual(result["shared_app"]["sum_of_returned_state_snapshot_tokens"], 687)
        self.assertEqual(result["shared_app"]["duplicated_B_tokens_in_A_snapshot"], 231)

    def test_generated_report_is_byte_stable(self) -> None:
        committed = (HERE / "results" / "concurrency_study.json").read_bytes()
        self.assertEqual(self.generated.read_bytes(), committed)

    def test_isolated_apps_keep_exact_rows_and_approve_by_thread_id(self) -> None:
        isolated = self.report["isolated_per_invocation_graphs"]
        for task in ("A", "B"):
            self.assertEqual(len(isolated["runs"][task]["calls"]), 2)
            self.assertEqual(len(isolated["runs"][task]["cost_rows"]), 2)
            self.assertEqual(isolated["approvals"][task]["status"], "approved")
            self.assertEqual(isolated["approvals"][task]["thread_id"], f"SYNTH-{task}")
            self.assertEqual(isolated["approvals"][task]["call_count_before"],
                             isolated["approvals"][task]["call_count_after"])

    def test_verifier_rejects_corrected_misattribution(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["shared_graph"]["runs"]["A"]["cost_rows"][2]["node"] = "classify"
        with self.assertRaises(VerificationError):
            verify_report(tampered, UPSTREAM)

    def test_verifier_rejects_missing_foreign_rows(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["shared_graph"]["runs"]["A"]["cost_rows"].pop(0)
        with self.assertRaises(VerificationError):
            verify_report(tampered, UPSTREAM)

    def test_verifier_rejects_a_different_schedule(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["shared_graph"]["events"][5]["kind"] = "wrapper_return"
        with self.assertRaises(VerificationError):
            verify_report(tampered, UPSTREAM)


if __name__ == "__main__":
    unittest.main()
