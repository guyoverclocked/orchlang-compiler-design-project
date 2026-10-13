#!/usr/bin/env python3
"""Replay a pre-v2 trace certificate preserved in the original audit bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audit"))
from replay_trace_equivalence import replay_report  # noqa: E402


FIXTURE = ROOT / "audit/fixtures/trace_equivalence_v1"
EXPECTED_SHA256 = {
    "report.json": "ec969951ceac607e3c3d704a021b9ad1b314debaf1df59b325c72fd2b32eb425",
    "graph.json": "c77e56e662c39ab51931407318ba256588d516636e76840def04315cd4d4c870",
    "kernel.json": "d317590e0f0d593348efa6c5219f8c55651a53355d65ab150af61fd988977a16",
}


class ArchivedTraceReportTests(unittest.TestCase):
    def test_original_version_one_bundle_report_replays(self):
        blobs = {name: (FIXTURE / name).read_bytes() for name in EXPECTED_SHA256}
        for name, raw in blobs.items():
            self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256[name])

        report = json.loads(blobs["report.json"])
        self.assertEqual(report["version"], 1)
        self.assertNotIn("diagnostics", report)
        self.assertNotIn("telemetry", report)

        result = replay_report(blobs["report.json"], blobs["graph.json"],
                               blobs["kernel.json"])
        self.assertEqual(result["status"], "verified", result.get("diagnostic"))
        self.assertEqual(result["decision"], "proved_equal")
        self.assertTrue(result["all_finite_horizons_claim"])


if __name__ == "__main__":
    unittest.main()
