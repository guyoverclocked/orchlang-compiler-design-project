"""Regression tests for fixed-profile source and evidence custody checks."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from publication_provenance import ProvenanceError, read_manifest, verify
from publication_run_integrity import (
    CLAIM_PROFILE,
    EVIDENCE_PATHS,
    REQUIRED_SOURCE_PATHS,
    RUN_PATH,
    REQUIRED_STAGES,
    capture_run_outputs,
    frozen_source_inventory,
    sha256,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicationFixture:
    """A tiny Git repository carrying the complete fixed publication profile."""

    def __init__(self, root: Path):
        self.root = root
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        paths = set(REQUIRED_SOURCE_PATHS) | {
            "audit/reproduce_final.py",
            "audit/test_publication_provenance.py",
            "integrations/incident_triage/results/source_study.json",
            "examples/graphs/accepted/core.json",
            "examples/channels/core.graph.json",
            "demo/offline_evidence.json",
            "integrations/langgraph/source_frontend/examples/input.contracts.json",
            "pyproject.toml",
            "research/publication_upgrade/solver_inputs/scale.kernel.json",
            *("research/publication_upgrade/solver_inputs/scale_" + str(n) + ".graph.json"
              for n in (2, 8, 16, 32, 64, 128, 256)),
        }
        for name in sorted(paths):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("frozen source fixture: " + name + "\n", encoding="utf-8")
        (root / "output/publication_upgrade/corpus/selection_audit.json").write_text(
            json.dumps({"audit_status": "pass"}) + "\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run([
            "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "frozen test source",
        ], cwd=root, check=True)
        self.revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        self.source = frozen_source_inventory(root, self.revision)
        self._make_outputs()
        self.manifest = self._make_manifest()

    def _write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _make_outputs(self) -> None:
        root = self.root
        (root / "bench/results/core.json").parent.mkdir(parents=True, exist_ok=True)
        (root / "bench/results/core.json").write_text('{"fixture":true}\n', encoding="utf-8")
        (root / "audit/incident_triage/incident.txt").parent.mkdir(parents=True, exist_ok=True)
        (root / "audit/incident_triage/incident.txt").write_text("incident fixture\n", encoding="utf-8")
        artifact = root / "integrations/langgraph/source_frontend/artifacts/study.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text('{"study":"fixture"}\n', encoding="utf-8")
        release = root / "output/release/package.json"
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_text('{"package":"fixture"}\n', encoding="utf-8")
        proof_dir = root / "proofs/publication_upgrade"
        for name in ("AtomicUpdates.vo", "Assumptions.vo", "AtomicUpdates.glob", "Assumptions.glob"):
            (proof_dir / name).write_bytes(b"compiled test proof\n")

        (root / EVIDENCE_PATHS["proof"]).parent.mkdir(parents=True, exist_ok=True)
        (root / EVIDENCE_PATHS["proof"]).write_text(
            "Theorem one.\nClosed under the global context\n"
            "Theorem two.\nClosed under the global context\n",
            encoding="utf-8",
        )
        self._write_json(EVIDENCE_PATHS["corpus"], {
            "corpus_denominators": {
                "candidate_files": 59, "repositories": 12,
                "repositories_with_candidate_files": 9,
            },
            "admission_counts": {"admitted": 0, "error": 0, "not_attempted": 0, "unsupported": 59},
            "dynamic_differential": (
                "differential_not_run: no original files admitted; no external source was projected or rewritten"
            ),
            "attempts": [{"admission": "unsupported"} for _ in range(59)],
        })
        self._write_json(EVIDENCE_PATHS["selection"], {"audit_status": "pass"})
        tokenizer_cache = {
            name.removeprefix("output/publication_upgrade/tokenizer_cache/"): digest
            for name, digest in self.source.items()
            if name.startswith("output/publication_upgrade/tokenizer_cache/")
        }
        self._write_json(EVIDENCE_PATHS["tokenizer"], {
            "format": "orchlang-local-tokenizer-calibration", "version": 1,
            "status": "completed", "cache_files": tokenizer_cache,
            "source_study_sha256": self.source["integrations/incident_triage/results/source_study.json"],
        })
        self._write_json(EVIDENCE_PATHS["observer"], {
            "format": "orchlang-publication-observer-ablation", "version": 1,
            "status": "passed", "failures": [],
            "summary": {
                "fixture_count": 12,
                "fixtures_with_finite_observer_comparison": 3,
                "independent_replay_status_counts": {"verified": 12},
            },
        })

        graph_inputs = []
        for size in (2, 8, 16, 32, 64, 128, 256):
            name = f"research/publication_upgrade/solver_inputs/scale_{size}.graph.json"
            graph_inputs.append({"path": name, "sha256": self.source[name]})
        kernel_path = "research/publication_upgrade/solver_inputs/scale.kernel.json"
        solver_base = {
            "format": "orchlang-trace-equivalence-solver-scaling", "version": 1,
            "study": {"calls_per_arm": [2, 8, 16, 32, 64, 128, 256], "measured_repetitions_per_size": 5},
            "inputs": {"graphs": graph_inputs, "kernel_path": kernel_path, "kernel_sha256": self.source[kernel_path]},
            "samples": [{"calls_per_arm": size} for size in (2, 8, 16, 32, 64, 128, 256) for _ in range(5)],
        }
        self._write_json(EVIDENCE_PATHS["solver"], solver_base)
        self._write_json(EVIDENCE_PATHS["solver_baseline"], solver_base)
        svg = root / "research/publication_upgrade/solver_scaling.svg"
        pdf = root / "research/publication_upgrade/solver_scaling.pdf"
        svg.write_text("<svg/>\n", encoding="utf-8")
        pdf.write_bytes(b"%PDF-fixture\n")
        self._write_json("research/publication_upgrade/solver_scaling_plot_metadata.json", {
            "inputs": {
                "optimized_json_sha256": sha(root / EVIDENCE_PATHS["solver"]),
                "baseline_json_sha256": sha(root / EVIDENCE_PATHS["solver_baseline"]),
            },
            "outputs": {"svg_sha256": sha(svg), "pdf_sha256": sha(pdf)},
        })
        self._write_json("output/publication_upgrade/corpus/manifest.json", {
            "admission_results": EVIDENCE_PATHS["corpus"],
        })

        start = "2026-10-14T00:00:00+00:00"
        core_start, core_end = "2026-10-14T00:01:01+00:00", "2026-10-14T00:01:59+00:00"
        incident_start, incident_end = "2026-10-14T00:05:01+00:00", "2026-10-14T00:05:59+00:00"
        artifact_path = "integrations/langgraph/source_frontend/artifacts/study.json"
        self._write_json(EVIDENCE_PATHS["core"], {
            "format": "orchlang-final-reproduction", "version": 3, "status": "passed",
            "base_revision": self.revision, "quick": False,
            "sanitizer_requested": True, "packaging_requested": True,
            "optional_langgraph_requested": True, "inputs_unchanged_during_run": True,
            "started_utc": core_start, "completed_utc": core_end,
            "executable_input_sha256": {"audit/reproduce_final.py": self.source["audit/reproduce_final.py"]},
            "core_source_sha256": {"audit/reproduce_final.py": self.source["audit/reproduce_final.py"]},
            "graph_fixture_sha256": {"examples/graphs/accepted/core.json": self.source["examples/graphs/accepted/core.json"]},
            "channel_fixture_sha256": {"examples/channels/core.graph.json": self.source["examples/channels/core.graph.json"]},
            "integration_source_sha256": {
                "integrations/incident_triage/source_analysis/bridge.py": self.source[
                    "integrations/incident_triage/source_analysis/bridge.py"
                ]
            },
            "demo_snapshot_sha256": {"demo/offline_evidence.json": self.source["demo/offline_evidence.json"]},
            "package_source_sha256": {"pyproject.toml": self.source["pyproject.toml"]},
            "integration_artifact_sha256": {
                artifact_path: sha(root / artifact_path),
                "integrations/langgraph/source_frontend/examples/input.contracts.json":
                    self.source["integrations/langgraph/source_frontend/examples/input.contracts.json"],
            },
            "results_sha256": {"bench/results/core.json": sha(root / "bench/results/core.json")},
            "package_result_sha256": {"output/release/package.json": sha(root / "output/release/package.json")},
        })
        incident_inputs = {
            name: value for name, value in self.source.items()
            if name.startswith("integrations/incident_triage/")
            or (name.startswith("audit/") and name.endswith(".py"))
        }
        self._write_json(EVIDENCE_PATHS["incident"], {
            "format": "orchlang-incident-extension-reproduction", "version": 1,
            "status": "passed", "source_commit": "c08f710acfeefe233329df613fe8358eaac5f350",
            "source_bundle_sha256": self.source["integrations/incident_triage/upstream_c08f710.bundle"],
            "inputs_unchanged_during_run": True,
            "started_utc": incident_start, "completed_utc": incident_end,
            "input_sha256": incident_inputs,
            "result_sha256": {"audit/incident_triage/incident.txt": sha(root / "audit/incident_triage/incident.txt")},
        })

        logs = root / "output/publication_upgrade/reproduction"
        logs.mkdir(parents=True, exist_ok=True)
        self.stage_argv = self._stage_commands()
        self.stage_rows = []
        start_minutes = 1
        for index, (name, argv) in enumerate(zip(REQUIRED_STAGES, self.stage_argv)):
            began_minute = start_minutes + index * 2
            began = f"2026-10-14T00:{began_minute:02d}:00+00:00"
            ended = f"2026-10-14T00:{began_minute + 1:02d}:00+00:00"
            log_path = logs / (name + ".log")
            text = (
                "Closed under the global context\nClosed under the global context\n"
                if name == "proof-Assumptions" else "successful fixture stage: " + name + "\n"
            )
            log_path.write_text(text, encoding="utf-8")
            self.stage_rows.append({
                "name": name, "exit_code": 0, "started_utc": began, "completed_utc": ended,
                "log": log_path.relative_to(root).as_posix(), "log_sha256": sha(log_path), "argv": argv,
            })
        self.run_start = start
        self.run_finish = "2026-10-14T00:22:00+00:00"
        self._write_run()

    @staticmethod
    def _stage_commands() -> list[list[str]]:
        return [
            ["python3", "audit/reproduce_final.py", "--sanitize", "--package", "--integration-python", ".venv/bin/python"],
            ["python3", "research/publication_upgrade/observer_ablation.py", "--output", EVIDENCE_PATHS["observer"]],
            ["python3", "audit/reproduce_incident_triage.py", "--integration-python", "integrations/incident_triage/.venv/bin/python"],
            ["python3", "scripts/publication_upgrade_corpus.py", "--evaluate"],
            [".venv/bin/python", "research/publication_upgrade/tokenizer_calibration.py"],
            ["python3", "research/publication_upgrade/solver_scaling.py", "--repetitions", "5", "--sizes", "2,8,16,32,64,128,256", "--output", EVIDENCE_PATHS["solver"], "--input-dir", "research/publication_upgrade/solver_inputs"],
            ["python3", "research/publication_upgrade/run_solver_baseline.py", "--repetitions", "5", "--warmups", "1", "--sizes", "2,8,16,32,64,128,256", "--output", EVIDENCE_PATHS["solver_baseline"]],
            ["python3", "research/publication_upgrade/plot_solver_scaling.py", EVIDENCE_PATHS["solver"], "research/publication_upgrade/solver_scaling", "--baseline", EVIDENCE_PATHS["solver_baseline"]],
            ["coqc", "-Q", "/tmp/proofs/publication_upgrade", "PublicationUpgrade", "/tmp/proofs/publication_upgrade/AtomicUpdates.v"],
            ["coqc", "-Q", "/tmp/proofs/publication_upgrade", "PublicationUpgrade", "/tmp/proofs/publication_upgrade/Assumptions.v"],
        ]

    def _write_run(self) -> None:
        run = {
            "format": "orchlang-publication-upgrade-reproduction", "version": 2,
            "source_revision": self.revision, "source_files_sha256": self.source,
            "status": "passed", "started_utc": self.run_start, "completed_utc": self.run_finish,
            "stages": self.stage_rows, "outputs_sha256": capture_run_outputs(self.root),
        }
        path = self.root / RUN_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    def _make_manifest(self) -> dict:
        evidence = {}
        for key, name in EVIDENCE_PATHS.items():
            evidence[key] = {
                "path": name,
                "sha256": sha(self.root / name),
                "scope": "fixture evidence for " + key,
            }
        paper_path = self.root / "submission/paper.tex"
        paper_path.parent.mkdir(parents=True, exist_ok=True)
        paper_path.write_text(
            "% OrchLang-source-revision: " + self.revision + "\n"
            + "\\newcommand{\\SourceRevision}{" + self.revision + "}\n"
            + "\\begin{tabular}{lll}\n"
            + r"C2 & Permanent code link & \href{https://github.com/guyoverclocked/orchlang-compiler-design-project/tree/\SourceRevision}{\texttt{\SourceRevision}} \\"
            + "\n\\end{tabular}\n",
            encoding="utf-8",
        )
        evidence["manuscript"] = {
            "path": paper_path.relative_to(self.root).as_posix(),
            "sha256": sha(paper_path), "scope": "fixture paper",
        }
        pdf_path = self.root / "submission/paper.pdf"
        pdf_path.write_bytes(b"%PDF-fixture\n")
        evidence["manuscript_pdf"] = {
            "path": pdf_path.relative_to(self.root).as_posix(),
            "sha256": sha(pdf_path), "scope": "fixture compiled paper",
        }
        claims = []
        for claim_id, profile in CLAIM_PROFILE.items():
            claims.append({
                "id": claim_id, "statement": "Fixture claim for " + claim_id,
                "source_paths": sorted(profile["source_paths"]),
                "evidence_ids": sorted(profile["evidence_ids"]),
            })
        return {
            "format": "orchlang-publication-provenance", "version": 1,
            "source_revision": self.revision, "source_files": self.source,
            "evidence": evidence, "claims": claims,
            "limitations": ["fixture validates artifact custody only"],
        }


class PublicationProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = PublicationFixture(self.root)
        self.manifest = self.fixture.manifest
        self.paper = self.root / self.manifest["evidence"]["manuscript"]["path"]

    def refresh_manifest_file_digest(self, key: str) -> None:
        item = self.manifest["evidence"][key]
        item["sha256"] = sha(self.root / item["path"])

    def test_complete_frozen_profile_verifies(self):
        self.assertEqual(verify(self.manifest, self.root, self.paper)["status"], "verified")

    def test_later_study_missing_from_source_revision_rejects(self):
        later = self.root / "research/publication_upgrade/new_study.py"
        later.write_text("print('later')\n", encoding="utf-8")
        with self.assertRaisesRegex(ProvenanceError, "untracked publication source/data"):
            verify(self.manifest, self.root, self.paper)

    def test_working_source_drift_rejects(self):
        source = self.root / "audit/trace_equivalence.py"
        source.write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ProvenanceError, "source not frozen"):
            verify(self.manifest, self.root, self.paper)

    def test_post_run_evidence_drift_rejects(self):
        target = self.root / EVIDENCE_PATHS["corpus"]
        target.write_text('{"admission_counts":{"admitted":59}}\n', encoding="utf-8")
        with self.assertRaisesRegex(ProvenanceError, "changed evidence"):
            verify(self.manifest, self.root, self.paper)

    def test_missing_claim_evidence_reference_rejects(self):
        self.manifest["claims"][0]["evidence_ids"] = ["absent"]
        with self.assertRaisesRegex(ProvenanceError, "absent evidence_ids"):
            verify(self.manifest, self.root, self.paper)

    def test_incomplete_fixed_claim_profile_rejects(self):
        self.manifest["claims"].pop()
        with self.assertRaisesRegex(ProvenanceError, "claim profile is incomplete"):
            verify(self.manifest, self.root, self.paper)

    def test_old_or_incomplete_run_cannot_be_relabelled_as_passed(self):
        path = self.root / RUN_PATH
        run = json.loads(path.read_text())
        run["stages"].pop(2)
        run["outputs_sha256"] = capture_run_outputs(self.root)
        path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
        self.refresh_manifest_file_digest("run")
        with self.assertRaisesRegex(ProvenanceError, "stages are missing"):
            verify(self.manifest, self.root, self.paper)

    def test_old_incident_manifest_from_before_this_run_rejects(self):
        path = self.root / EVIDENCE_PATHS["incident"]
        incident = json.loads(path.read_text())
        incident["started_utc"] = "2026-10-13T23:00:00+00:00"
        path.write_text(json.dumps(incident) + "\n", encoding="utf-8")
        outputs = capture_run_outputs(self.root)
        run_path = self.root / RUN_PATH
        run = json.loads(run_path.read_text())
        run["outputs_sha256"] = outputs
        run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
        self.refresh_manifest_file_digest("run")
        self.refresh_manifest_file_digest("incident")
        with self.assertRaisesRegex(ProvenanceError, "not produced during this publication run"):
            verify(self.manifest, self.root, self.paper)

    def test_source_revision_macro_mismatch_rejects(self):
        text = self.paper.read_text(encoding="utf-8").replace(
            "\\newcommand{\\SourceRevision}{" + self.fixture.revision + "}",
            "\\newcommand{\\SourceRevision}{" + "a" * 40 + "}",
        )
        self.paper.write_text(text, encoding="utf-8")
        self.refresh_manifest_file_digest("manuscript")
        with self.assertRaisesRegex(ProvenanceError, "SourceRevision macro"):
            verify(self.manifest, self.root, self.paper)

    def test_c2_omission_rejects(self):
        text = self.paper.read_text(encoding="utf-8").replace(
            r"\SourceRevision}{\texttt{\SourceRevision}", "mutable URL"
        )
        self.paper.write_text(text, encoding="utf-8")
        self.refresh_manifest_file_digest("manuscript")
        with self.assertRaisesRegex(ProvenanceError, "C2 must link"):
            verify(self.manifest, self.root, self.paper)

    def test_mutable_c2_target_rejects(self):
        text = self.paper.read_text(encoding="utf-8").replace(
            r"https://github.com/guyoverclocked/orchlang-compiler-design-project/tree/\SourceRevision",
            "https://github.com/guyoverclocked/orchlang-compiler-design-project",
        )
        self.paper.write_text(text, encoding="utf-8")
        self.refresh_manifest_file_digest("manuscript")
        with self.assertRaisesRegex(ProvenanceError, "C2 must link"):
            verify(self.manifest, self.root, self.paper)

    def test_manuscript_comment_mismatch_rejects(self):
        text = self.paper.read_text(encoding="utf-8").replace(self.fixture.revision, "a" * 40, 1)
        self.paper.write_text(text, encoding="utf-8")
        self.refresh_manifest_file_digest("manuscript")
        with self.assertRaisesRegex(ProvenanceError, "same frozen source revision"):
            verify(self.manifest, self.root, self.paper)

    def test_escaping_path_and_boolean_version_reject(self):
        for key, value in (("source_files", {"../early.py": "a" * 64}), ("version", True)):
            with self.subTest(key=key):
                document = copy.deepcopy(self.manifest)
                document[key] = value
                with self.assertRaises(ProvenanceError):
                    verify(document, self.root, self.paper)

    def test_duplicate_json_fields_reject(self):
        path = self.root / "bad.json"
        path.write_text('{"version":1,"version":2}', encoding="utf-8")
        with self.assertRaisesRegex(ProvenanceError, "duplicate JSON"):
            read_manifest(path)


if __name__ == "__main__":
    unittest.main()
