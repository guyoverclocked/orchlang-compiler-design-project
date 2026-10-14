from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import hashlib

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from integrations.langgraph.backend import (  # noqa: E402
    OracleOutcome,
    execute_verified,
    prepare_graph,
)
from completed_state_review import (  # noqa: E402
    RESULTS_PATH,
    audit_saved_study,
    evaluate_pair,
    run_review,
)


class CompletedStateReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report, cls.protocol, cls.result = audit_saved_study()

    def test_frozen_study_and_artifact_hashes_replay_cleanly(self) -> None:
        report = run_review()
        self.assertEqual(report["status"], "pass", report["issues"])
        self.assertEqual(report["totals"], {
            "completed_pairs": 96,
            "cutoff_pairs": 8,
            "call_events": 224,
            "all_checks_passed_pairs": 104,
        })
        self.assertTrue(report["protocol_integrity"]["results_mtime_after_freeze"])
        self.assertTrue(report["protocol_integrity"]["results_protocol_hash_matches"])

    def test_completed_projection_excludes_but_preserves_node_local_temp(self) -> None:
        summary = {item["name"]: item for item in self.report["case_summary"]}
        self.assertEqual(summary["multi_result_node"]["backend_only_registers"], ["lg_temp_0000"])
        row = next(
            item for item in self.result["runs"]
            if item["case"] == "multi_result_node" and item["max_calls"] == 4
        )
        events = row["source"]["trace"]
        mapping = row["source_state_mapping"]
        values = row["backend"]["final_values"]
        self.assertEqual([event["template"] for event in events], ["draft", "critique", "answer"])
        self.assertEqual(values["lg_temp_0000"], events[1]["response"])
        self.assertEqual(events[2]["arguments"], [events[1]["response"], events[0]["response"]])
        self.assertNotIn("intermediate", row["source"]["final_state"])
        self.assertEqual(values[mapping["draft"]], row["source"]["final_state"]["draft"])
        self.assertEqual(values[mapping["answer"]], row["source"]["final_state"]["answer"])

    def test_overwritten_source_field_is_projected_from_last_write(self) -> None:
        row = next(
            item for item in self.result["runs"]
            if item["case"] == "mutable_result_chain" and item["max_calls"] == 4
        )
        events = row["source"]["trace"]
        draft_register = row["source_state_mapping"]["draft"]
        self.assertEqual([event["template"] for event in events], ["draft", "revise", "answer"])
        self.assertNotEqual(events[0]["response"], events[1]["response"])
        self.assertEqual(row["source"]["final_state"]["draft"], events[1]["response"])
        self.assertEqual(row["backend"]["final_values"][draft_register], events[1]["response"])

    def test_completed_value_corruption_is_detected(self) -> None:
        damaged = deepcopy(self.result)
        row = next(
            item for item in damaged["runs"]
            if item["case"] == "multi_result_node" and item["max_calls"] == 4
        )
        answer_register = row["source_state_mapping"]["answer"]
        row["backend"]["final_values"][answer_register] = "INJECTED_CORRUPTION"
        evaluated = evaluate_pair(row)
        self.assertFalse(evaluated["checks"]["complete_state"])
        self.assertTrue(any(issue["code"] == "differential_check_failed"
                            and issue["detail"] == "complete_state"
                            for issue in evaluated["issues"]))

    def test_omitted_register_and_omitted_source_slot_are_detected(self) -> None:
        missing_register = deepcopy(self.result)
        row = next(
            item for item in missing_register["runs"]
            if item["case"] == "multi_result_node" and item["max_calls"] == 4
        )
        draft_register = row["source_state_mapping"]["draft"]
        del row["backend"]["final_values"][draft_register]
        evaluated = evaluate_pair(row)
        self.assertFalse(evaluated["checks"]["complete_state"])
        self.assertIn(draft_register, evaluated["missing_registers"])

        missing_mapping = deepcopy(self.result)
        row = next(
            item for item in missing_mapping["runs"]
            if item["case"] == "multi_result_node" and item["max_calls"] == 4
        )
        del row["source_state_mapping"]["answer"]
        evaluated = evaluate_pair(row)
        self.assertFalse(evaluated["checks"]["complete_state"])
        self.assertTrue(any(issue["code"] == "unmapped_source_field"
                            for issue in evaluated["issues"]))

    def test_cutoff_pair_cannot_publish_partial_registers(self) -> None:
        damaged = deepcopy(self.result)
        row = next(
            item for item in damaged["runs"]
            if item["case"] == "multi_result_node" and item["max_calls"] == 1
        )
        self.assertEqual(row["source"]["status"], "truncated")
        self.assertEqual(row["backend"]["status"], "truncated")
        self.assertIsNone(row["source"]["final_state"])
        self.assertIsNone(row["backend"]["final_values"])
        row["backend"]["final_values"] = {"lg_slot_0000": "PARTIAL_REGISTER"}
        evaluated = evaluate_pair(row)
        self.assertTrue(any(issue["code"] == "cutoff_published_state"
                            for issue in evaluated["issues"]))
        self.assertFalse(evaluated["checks"]["complete_state"])

    def test_all_six_operator_truth_tables_have_both_sides_in_supplement(self) -> None:
        supplement_path = ROOT / "research/scp_strengthening/completed_state_review/truth_table_results.json"
        self.assertTrue(supplement_path.exists(), "run the frozen supplementary truth-table experiment first")
        supplement = json.loads(supplement_path.read_bytes())
        self.assertEqual(supplement["status"], "pass", supplement["failures"])
        self.assertEqual(len(supplement["runs"]), 18)
        self.assertTrue(supplement["primary_study_unchanged"])
        primary = ROOT / "output/scp_strengthening/source_differential"
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(supplement["primary_protocol_sha256"], digest(primary / "protocol.json"))
        self.assertEqual(supplement["primary_results_sha256"], digest(primary / "results.json"))
        for row in supplement["runs"]:
            expected_response = "r" * (4 * row["draft_output_tokens"])
            for side in ("source", "backend"):
                for event in row[side]["trace"]:
                    self.assertEqual(event["response"], expected_response)
                    self.assertEqual(event["output_tokens"], row["draft_output_tokens"])
        for operation, summary in supplement["operator_summary"].items():
            self.assertEqual(summary["case_count"], 3)
            self.assertEqual(set(summary["branches"]), {"yes", "no"})
            self.assertEqual(summary["wrong_expected_route_count"], 0)
            self.assertEqual(summary["source_backend_trace_mismatches"], 0)
            self.assertEqual(summary["state_projection_mismatches"], 0)

    def test_error_after_eager_internal_write_never_returns_completed_values(self) -> None:
        graph_path = ROOT / "examples/graphs/accepted/finite_private_chain.json"
        certificate_path = ROOT / "bench/results/graph_certificates/finite_private_chain.json"
        verified = prepare_graph(graph_path.read_bytes(), certificate_path.read_bytes())
        calls = 0

        def fail_after_one(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return OracleOutcome("x", 1)
            raise RuntimeError("injected second-call failure")

        result = execute_verified(
            verified,
            {"query": "q", "route": True},
            17,
            fail_after_one,
            max_calls=4,
        ).to_dict()
        self.assertEqual(result["status"], "runtime_error")
        self.assertFalse(result["stopped"])
        self.assertEqual(result["call_count"], 1)
        self.assertIsNone(result["final_values"])
        self.assertNotIn("truncated_at_calls", result)


if __name__ == "__main__":
    unittest.main()
