from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from integrations.incident_triage.source_analysis import bridge, replay_projection


ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / "integrations/incident_triage/upstream_snapshot"
STUDY = ROOT / "integrations/incident_triage/results/source_study.json"


class SourceAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="incident-source-analysis-")
        cls.output = Path(cls.temp.name) / "artifacts"
        cls.report = bridge.build_analysis(UPSTREAM, STUDY, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _copy_artifacts(self, folder: Path) -> Path:
        for name in (
            "source_analysis.json",
            "classifier_request.graph.json",
            "classifier_request.certificate.json",
            "classifier_request.attestation.json",
        ):
            shutil.copyfile(self.output / name, folder / name)
        return folder / "source_analysis.json"

    def test_source_ast_covers_full_pre_dispatch_dependency_protocol(self):
        protocol = self.report["source_ast_contract"]["dependency_protocol"]
        self.assertEqual(protocol["format"], "orchlang-incident-triage-dependency-protocol")
        self.assertIn("category", protocol["classification"]["typed_result_dependencies"])
        self.assertIn("summary", protocol["classification"]["typed_result_dependencies"])
        self.assertEqual(protocol["classification"]["response_schema"]["summary"],
                         {"type": "str", "max_length": 300})
        self.assertEqual(protocol["classification"]["prompt_schema_note"]["prompt_summary_max_chars"], 280)
        self.assertTrue(protocol["classification"]["prompt_schema_note"]["mismatch"])
        self.assertEqual(protocol["validation_and_repair"]["repair"]["maximum_completions"], 2)
        self.assertEqual(protocol["usage_and_budget"]["record_formula"]["input_tokens"],
                         "max(1, len(system + user) // 4)")
        self.assertEqual(protocol["usage_and_budget"]["budget_usd"], 0.05)
        self.assertEqual(protocol["usage_and_budget"]["budget_predicate"],
                         "rounded_total_usd > MAX_COST_PER_INCIDENT_USD")
        self.assertEqual(protocol["draft_and_gate"]["maximum_model_completions_pre_dispatch"], 3)
        self.assertEqual(protocol["draft_and_gate"]["control"]["interrupt_before"], ["dispatch"])
        self.assertFalse(protocol["draft_and_gate"]["raw_incident_text_dependency"])

    def test_independent_replay_accepts_generated_report_and_graph_certificate(self):
        attestation = replay_projection.replay_projection(
            self.output / "source_analysis.json", UPSTREAM, STUDY,
        )
        self.assertEqual(attestation["status"], "verified")
        self.assertEqual(attestation["graph"]["graph_replay_status"], "verified")
        self.assertEqual(len(attestation["checks"]), 7)

    def test_saved_attestation_matches_fresh_independent_replay(self):
        saved = json.loads((self.output / "source_analysis.attestation.json").read_text())
        replayed = replay_projection.replay_projection(
            self.output / "source_analysis.json", UPSTREAM, STUDY,
        )
        self.assertEqual(saved, replayed)

    def test_finite_source_projection_has_22_cases_and_5_of_11_equal_pairs(self):
        projection = self.report["source_study_projection"]
        self.assertEqual(projection["source_case_count"], 22)
        self.assertEqual(projection["source_pair_count"], 11)
        self.assertEqual(projection["equal_projection_pairs"], 5)
        self.assertEqual(projection["different_projection_pairs"], 6)

    def test_authored_classifier_repair_and_draft_raw_bypasses_are_rejected(self):
        probes = self.report["authored_mutation_probes"]
        self.assertEqual({row["id"] for row in probes}, {
            "AUTHORED-CLASSIFY-RAW-BYPASS",
            "AUTHORED-REPAIR-RAW-BYPASS",
            "AUTHORED-DRAFT-RAW-BYPASS",
        })
        self.assertTrue(all(row["status"] == "rejected_by_source_ast_contract" for row in probes))
        self.assertTrue(all(row["upstream_modified"] is False for row in probes))

    def test_study_reports_source_calls_cover_retry_and_draft_lines(self):
        study = json.loads(STUDY.read_text())
        retried = study["cases"]
        retry_pair = [row for row in retried if row["case_id"] in {"retry_email_a", "retry_email_b"}]
        self.assertEqual(len(retry_pair), 2)
        self.assertTrue(all(len(row["calls"]) >= 2 for row in retry_pair))
        self.assertTrue(all(row["calls"][-1]["system"] == self.report["source_ast_contract"]["dependency_protocol"]["draft_and_gate"]["system"]
                            for row in study["cases"] if any(c["system"] == self.report["source_ast_contract"]["dependency_protocol"]["draft_and_gate"]["system"] for c in row["calls"])))

    def test_tampered_dependency_schema_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-tamper-") as temporary:
            folder = Path(temporary)
            report_path = self._copy_artifacts(folder)
            report = json.loads(report_path.read_text())
            report["source_ast_contract"]["dependency_protocol"]["classification"]["response_schema"]["summary"]["max_length"] = 999
            report_path.write_text(json.dumps(report))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(report_path, UPSTREAM, STUDY)

    def test_tampered_claim_or_scope_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-tamper-") as temporary:
            folder = Path(temporary)
            report_path = self._copy_artifacts(folder)
            report = json.loads(report_path.read_text())
            report["claim"] = "unconditional universal PII security"
            report_path.write_text(json.dumps(report))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(report_path, UPSTREAM, STUDY)

    def test_tampered_graph_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-tamper-") as temporary:
            folder = Path(temporary)
            report_path = self._copy_artifacts(folder)
            graph_path = folder / "classifier_request.graph.json"
            graph = json.loads(graph_path.read_text())
            graph["name"] = "tampered_graph"
            graph_path.write_text(json.dumps(graph))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(report_path, UPSTREAM, STUDY)

    def test_tampered_mutation_rejection_basis_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-tamper-") as temporary:
            folder = Path(temporary)
            report_path = self._copy_artifacts(folder)
            report = json.loads(report_path.read_text())
            report["authored_mutation_probes"][1]["rejection_basis"] = "source_hash_mismatch"
            report_path.write_text(json.dumps(report))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(report_path, UPSTREAM, STUDY)

    def test_tampered_graph_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-tamper-") as temporary:
            folder = Path(temporary)
            report_path = self._copy_artifacts(folder)
            certificate_path = folder / "classifier_request.certificate.json"
            certificate = json.loads(certificate_path.read_text())
            certificate["product_edges"] += 1
            certificate_path.write_text(json.dumps(certificate))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(report_path, UPSTREAM, STUDY)

    def test_mutated_snapshot_source_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="incident-source-") as temporary:
            folder = Path(temporary)
            shutil.copytree(UPSTREAM, folder / "snapshot")
            path = folder / "snapshot/src/triage/graph.py"
            path.write_bytes(path.read_bytes().replace(b"redact_pii(incident.text)", b"incident.text", 1))
            with self.assertRaises(replay_projection.ProjectionReplayError):
                replay_projection.replay_projection(self.output / "source_analysis.json", folder / "snapshot", STUDY)

    def test_checker_does_not_import_or_execute_bridge_or_upstream(self):
        source = Path(replay_projection.__file__).read_text()
        self.assertNotIn("import bridge", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("import triage", source)


if __name__ == "__main__":
    unittest.main()
