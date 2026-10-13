#!/usr/bin/env python3
"""Offline integrity checks for the frozen external-source corpus evaluator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_upgrade_corpus as corpus  # noqa: E402


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(corpus.canonical(value))


def _stub_frontend_modules(*, include_differential=False):
    packages = {}
    for name in ("integrations", "integrations.langgraph",
                 "integrations.langgraph.source_frontend"):
        module = ModuleType(name)
        module.__path__ = []
        packages[name] = module
    extract = ModuleType("integrations.langgraph.source_frontend.extract")

    class FrontendError(Exception):
        pass

    extract.FrontendError = FrontendError
    extract.extract_source = lambda *_args: (_ for _ in ()).throw(
        AssertionError("the tampered source must be rejected before extraction")
    )
    packages[extract.__name__] = extract
    if include_differential:
        extract.extract_source = lambda *_args: ({"nodes": [{"id": "entry"}]},
                                                  {"compiled_variable": "app"})
        extract.parse_contracts = lambda _raw: {
            "inputs": {"question": {"type": "text"}},
        }
        export = ModuleType("integrations.langgraph.source_frontend.export")
        export.export_bytes = lambda *_args: ({"nodes": []}, {"certificate": True},
                                               {}, None)
        study = ModuleType("integrations.langgraph.source_frontend.study")
        # This mirrors the current helper's partial return: it compares source
        # and graph internally but preserves only one trace and no states/logs.
        study._paired_run = lambda *_args: {
            "trace_equal": True, "trace_sha256": "a" * 64,
            "status": "stopped", "trace": [],
        }
        packages[export.__name__] = export
        packages[study.__name__] = study
    return packages


class PublicationCorpusTests(unittest.TestCase):
    def _configure_temp_root(self, root: Path, out: Path, protocol: Path):
        frontend = root / "integrations/langgraph/source_frontend"
        frontend.mkdir(parents=True, exist_ok=True)
        (frontend / "extract.py").write_text("# frozen test frontend\n", encoding="utf-8")
        protocol.parent.mkdir(parents=True, exist_ok=True)
        protocol.write_text("frozen protocol fixture\n", encoding="utf-8")
        return patch.multiple(corpus, ROOT=root, OUT=out, PROTOCOL=protocol)

    def test_tampered_frozen_source_sha_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output/corpus"
            protocol = root / "research/corpus/protocol.md"
            context = self._configure_temp_root(root, out, protocol)
            source_rel = "output/corpus/sources/acme/demo/commit/file.py"
            source_path = root / source_rel
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"original snapshot bytes\n")
            protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
            _write_json(out / "repository_manifest.json", {
                "protocol_sha256": protocol_hash,
                "selected_repositories": [{"full_name": "acme/demo", "commit": "commit"}],
                "frontend_fingerprint": {"sha256": "frozen-fingerprint", "files": []},
            })
            enumeration = {
                "protocol_sha256": protocol_hash,
                "candidates": [{
                    "repository": "acme/demo", "commit": "commit",
                    "path": "file.py", "source_snapshot": source_rel,
                    "sha256": "0" * 64,
                }],
            }
            old_path = list(sys.path)
            try:
                with context, patch.dict(sys.modules, _stub_frontend_modules()):
                    with self.assertRaisesRegex(RuntimeError, "source SHA-256 mismatch"):
                        corpus.evaluate(enumeration)
            finally:
                sys.path[:] = old_path

    def test_frozen_frontend_fingerprint_uses_original_manifest_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output/corpus"
            protocol = root / "research/corpus/protocol.md"
            context = self._configure_temp_root(root, out, protocol)
            protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
            frozen = {"sha256": "frozen-fingerprint", "files": [{
                "path": "extract.py", "sha256": "frozen-extract-sha",
            }]}
            _write_json(out / "repository_manifest.json", {
                "protocol_sha256": protocol_hash,
                "selected_repositories": [{"full_name": "acme/demo", "commit": "commit"}],
                # This is the actual key in the frozen corpus manifest.
                "frontend_fingerprint": frozen,
            })
            old_path = list(sys.path)
            try:
                with context, patch.dict(sys.modules, _stub_frontend_modules()):
                    result = corpus.evaluate({"protocol_sha256": protocol_hash, "candidates": []})
            finally:
                sys.path[:] = old_path

            self.assertEqual(result["frontend_fingerprint_at_freeze"], frozen)
            self.assertIn("GitHub API-reported SPDX identifiers", result["license_basis_note"])
            self.assertIn("not a legal determination", result["license_basis_note"])
            self.assertTrue(result["post_evaluation_protocol_clarification"]["recorded_after_outcomes"])

    def test_partial_paired_helper_output_is_not_reported_as_differential(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output/corpus"
            protocol = root / "research/corpus/protocol.md"
            context = self._configure_temp_root(root, out, protocol)
            protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
            source_rel = "output/corpus/sources/acme/demo/commit/workflow.py"
            source_path = root / source_rel
            source_path.parent.mkdir(parents=True, exist_ok=True)
            raw = (
                b"from typing import TypedDict\n"
                b"class State(TypedDict):\n"
                b"    question: str\n"
            )
            source_path.write_bytes(raw)
            _write_json(out / "repository_manifest.json", {
                "protocol_sha256": protocol_hash,
                "selected_repositories": [{"full_name": "acme/demo", "commit": "commit"}],
                "frontend_fingerprint": {"sha256": "frozen-fingerprint", "files": []},
            })
            candidate = {
                "repository": "acme/demo", "commit": "commit",
                "path": "workflow.py", "source_snapshot": source_rel,
                "license_spdx": "MIT",
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            }
            old_path = list(sys.path)
            try:
                with context, patch.dict(
                    sys.modules, _stub_frontend_modules(include_differential=True)
                ):
                    result = corpus.evaluate({
                        "protocol_sha256": protocol_hash, "candidates": [candidate],
                    })
            finally:
                sys.path[:] = old_path

            attempt, = result["attempts"]
            self.assertEqual(attempt["admission"], "admitted")
            self.assertEqual(attempt["dynamic_differential"],
                             "not_claimed_evidence_incomplete")
            self.assertNotIn("trace_equal", attempt["dynamic_runs"][0])
            self.assertIn("graph_trace", attempt["dynamic_runs"][0]["missing_evidence"])

    def test_offline_selection_audit_is_repeatable_and_keeps_frozen_cohort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output/corpus"
            out.mkdir(parents=True)
            protocol = root / "protocol.md"
            protocol.write_text("frozen protocol fixture\n", encoding="utf-8")
            protocol_hash = hashlib.sha256(protocol.read_bytes()).hexdigest()
            repository = {
                "full_name": "acme/demo", "stargazers_count": 500,
                "private": False, "archived": False,
                "license": {"spdx_id": "MIT"},
            }
            _write_json(out / "github_search_snapshot.json", {
                "queries": [
                    {"query": "langgraph language:Python stars:>=100",
                     "response": {"items": [repository]}},
                    {"query": "topic:langgraph language:Python stars:>=100",
                     "response": {"items": [repository]}},
                ],
            })
            _write_json(out / "repository_manifest.json", {
                "protocol_sha256": protocol_hash,
                "selected_repositories": [{
                    "full_name": "acme/demo", "stars_at_selection": 500,
                    "license_spdx": "MIT",
                }],
            })
            spdx_path = out / "spdx_osi_license_list_v3.29.0.json"
            _write_json(spdx_path, {
                "licenseListVersion": "3.29.0",
                "licenses": [{"licenseId": "MIT", "isOsiApproved": True}],
            })
            with patch.multiple(corpus, ROOT=root, OUT=out, PROTOCOL=protocol,
                                SPDX_LICENSE_LIST=spdx_path):
                first = corpus.audit_frozen_selection()
                first_bytes = (out / "selection_audit.json").read_bytes()
                second = corpus.audit_frozen_selection()
                second_bytes = (out / "selection_audit.json").read_bytes()

            self.assertEqual(first["audit_status"], "pass")
            self.assertEqual(second["audit_status"], "pass")
            self.assertEqual(first["selected_count"], 1)
            self.assertEqual(first_bytes, second_bytes)


if __name__ == "__main__":
    unittest.main()
