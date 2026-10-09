from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from isolated_session_manager import (
    DuplicateSession,
    InvalidIncident,
    InvalidSessionState,
    IsolatedSessionManager,
    SessionBusy,
    SessionCapacityExceeded,
    SessionExpired,
    SourceGateError,
    verify_source_gate,
    _read_json,
    MAX_EVIDENCE_JSON_BYTES,
)


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "upstream_snapshot"


class FakeClock:
    def __init__(self) -> None:
        self.value = 1_000.0
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            return self.value

    def advance(self, amount: float) -> None:
        with self.lock:
            self.value += amount


class IsolatedSessionManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.clock = FakeClock()
        cls.manager = IsolatedSessionManager(
            source_root=SOURCE, max_pending=3, ttl_seconds=60,
            max_lifetime_sessions=100, clock=cls.clock,
        )
        cls.counter = 0
        cls.counter_lock = threading.Lock()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.clock.advance(10_000)
        cls.manager.expire_due()

    def setUp(self) -> None:
        self.clock.value = 1_000.0
        self._ids: list[str] = []

    def tearDown(self) -> None:
        for incident_id in list(self.manager._sessions):
            try:
                self.manager.discard(incident_id)
            except (SessionExpired, InvalidSessionState):
                pass

    def incident(self, *, site: str = "GTS-01", text: str | None = None) -> dict[str, str]:
        with self.counter_lock:
            type(self).counter += 1
            serial = type(self).counter
        incident_id = f"SESSION-TEST-{serial}"
        self._ids.append(incident_id)
        return {
            "incident_id": incident_id,
            "site": site,
            "reported_by": "synthetic operator",
            "text": text or f"Synthetic incident {serial}: an intruder forced the gate open.",
        }

    def test_required_source_gate_is_verified_and_bound_to_locked_runtime(self) -> None:
        evidence = verify_source_gate(SOURCE)
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(evidence["source_commit"], "c08f710acfeefe233329df613fe8358eaac5f350")
        self.assertEqual(evidence["source_license"], "MIT")
        self.assertEqual(evidence["runtime"]["langgraph"], "1.2.14")
        self.assertEqual(evidence["runtime"]["pydantic"], "2.14.0")
        self.assertGreaterEqual(evidence["source_replay_checks"], 6)
        self.assertEqual(os.environ.get("TRIAGE_LLM"), "mock")
        self.assertEqual(os.environ.get("LANGSMITH_TRACING_V2"), "false")

    def test_nonfinite_lifetimes_are_rejected_before_source_loading(self) -> None:
        for ttl in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                IsolatedSessionManager(source_root=SOURCE, ttl_seconds=ttl)

    def test_evidence_json_reader_rejects_oversized_sparse_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix='incident-large-evidence-') as temp:
            path = Path(temp) / 'oversized.json'
            with path.open('wb') as stream:
                stream.truncate(MAX_EVIDENCE_JSON_BYTES + 1)
            with self.assertRaisesRegex(SourceGateError, 'evidence byte bound'):
                _read_json(path, 'oversized test evidence')

    def test_unrelated_top_level_harness_cannot_replace_fixed_loader(self) -> None:
        # The source harness intentionally refuses a pre-imported triage
        # package, so initialization is exercised in a fresh process.
        code = '''import sys, types
sys.path.insert(0, %s)
from isolated_session_manager import IsolatedSessionManager
unrelated = types.ModuleType('run_study')
def forbidden(_root):
    raise AssertionError('unrelated harness was called')
unrelated.load_pinned_source = forbidden
sys.modules['run_study'] = unrelated
manager = IsolatedSessionManager(max_pending=1)
assert manager.evidence['status'] == 'verified'
''' % repr(str(HERE))
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preloaded_package_harness_with_wrong_origin_is_rejected(self) -> None:
        from integrations import incident_triage
        fake = types.ModuleType('integrations.incident_triage.run_study')
        fake.__file__ = '/tmp/unrelated-incident-harness.py'
        fake.load_pinned_source = lambda _root: self.fail('unbound loader was called')
        with patch.object(incident_triage, 'run_study', fake), \
                patch.dict(sys.modules, {'integrations.incident_triage.run_study': fake}), \
                self.assertRaises(SourceGateError):
            IsolatedSessionManager(source_root=SOURCE, max_pending=1)

    def test_cancellation_releases_start_and_approval_handles(self) -> None:
        graph_module = self.manager._modules[0]
        interrupted_start = self.incident()
        with patch.object(graph_module, 'triage_incident', side_effect=KeyboardInterrupt('test cancellation')), \
                self.assertRaises(KeyboardInterrupt):
            self.manager.start(interrupted_start)
        self.assertEqual(self.manager.active_count, 0)
        with self.assertRaises(DuplicateSession):
            self.manager.start(interrupted_start)

        pending = self.incident()
        self.manager.start(pending)
        with patch.object(graph_module, 'approve', side_effect=KeyboardInterrupt('test cancellation')), \
                self.assertRaises(KeyboardInterrupt):
            self.manager.approve(pending['incident_id'])
        self.assertEqual(self.manager.active_count, 0)
        with self.assertRaises(InvalidSessionState):
            self.manager.approve(pending['incident_id'])

    def test_new_start_recovers_capacity_from_expired_idle_sessions(self) -> None:
        old = [self.incident() for _ in range(3)]
        for incident in old:
            self.manager.start(incident)
        self.clock.advance(61)
        current = self.incident()
        self.manager.start(current)
        self.assertEqual(self.manager.active_count, 1)
        for incident in old:
            with self.assertRaises(SessionExpired):
                self.manager.approve(incident['incident_id'])

    def test_source_gate_rejects_changed_snapshot_before_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix="incident-source-gate-") as temp:
            altered = Path(temp) / "snapshot"
            shutil.copytree(SOURCE, altered)
            graph = altered / "src" / "triage" / "graph.py"
            graph.write_bytes(graph.read_bytes() + b"\n# deliberately changed for a gate test\n")
            with self.assertRaises(SourceGateError):
                verify_source_gate(altered)

    def test_two_incidents_start_concurrently_with_isolated_correct_rows(self) -> None:
        cases = [
            self.incident(text="ALPHA SIGNAL: synthetic intruder forced the loading gate."),
            self.incident(text="BRAVO SIGNAL: synthetic water leak in a storage room."),
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(self.manager.start, cases))

        by_id = {receipt["incident_id"]: receipt for receipt in receipts}
        self.assertEqual(len(by_id), 2)
        self.assertEqual(self.manager.active_count, 2)
        sessions = [self.manager._sessions[item["incident_id"]] for item in receipts]
        self.assertIsNot(sessions[0].app, sessions[1].app)
        self.assertIsNot(sessions[0].mock, sessions[1].mock)
        for case in cases:
            receipt = by_id[case["incident_id"]]
            self.assertEqual(receipt["status"], "pending_approval")
            self.assertEqual(receipt["thread_id"], case["incident_id"])
            self.assertEqual([call["phase"] for call in receipt["model_calls"]],
                             ["classify", "draft"])
            self.assertEqual([row["node"] for row in receipt["cost_rows"]],
                             ["classify", "draft"])
            for call, row in zip(receipt["model_calls"], receipt["cost_rows"]):
                self.assertEqual(row["input_tokens"], call["input_tokens"])
                self.assertEqual(row["output_tokens"], call["output_tokens"])
                self.assertRegex(call["request_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(call["response_sha256"], r"^[0-9a-f]{64}$")
            serialized = json.dumps(receipt, sort_keys=True)
            self.assertNotIn(case["text"], serialized)

        # The handles keep the original apps and thread IDs until continuation.
        approvals = []
        graph_module = self.manager._modules[0]
        original_approve = graph_module.approve
        for case in cases:
            retained_app = self.manager._sessions[case["incident_id"]].app
            observed: list[tuple[object, str]] = []

            def observe(app: object, thread_id: str):
                observed.append((app, thread_id))
                return original_approve(app, thread_id)

            with patch.object(graph_module, "approve", side_effect=observe):
                approval = self.manager.approve(case["incident_id"])
            self.assertEqual(len(observed), 1)
            self.assertIs(observed[0][0], retained_app)
            self.assertEqual(observed[0][1], case["incident_id"])
            approvals.append(approval)
        for approval in approvals:
            self.assertEqual(approval["status"], "approved")
            self.assertEqual(approval["model_calls_before"], 2)
            self.assertEqual(approval["model_calls_after"], 2)
        self.assertEqual(self.manager.active_count, 0)
        for case in cases:
            with self.assertRaises(DuplicateSession):
                self.manager.start(case)

    def test_duplicate_capacity_discard_and_expiry(self) -> None:
        a, b, c = self.incident(), self.incident(), self.incident()
        self.manager.start(a)
        self.manager.start(b)
        with self.assertRaises(DuplicateSession):
            self.manager.start(a)
        self.assertEqual(self.manager.active_count, 2)

        # Fill the third slot, then verify a fourth fails before app creation.
        self.manager.start(c)
        d = self.incident()
        with self.assertRaises(SessionCapacityExceeded):
            self.manager.start(d)
        self.assertEqual(self.manager.active_count, 3)

        self.manager.discard(a["incident_id"])
        e = self.incident()
        self.manager.start(e)
        self.assertEqual(self.manager.active_count, 3)
        self.clock.advance(61)
        self.assertEqual(self.manager.expire_due(), sorted([
            b["incident_id"], c["incident_id"], e["incident_id"]
        ]))
        self.assertEqual(self.manager.active_count, 0)
        with self.assertRaises(SessionExpired):
            self.manager.approve(b["incident_id"])
        with self.assertRaises(DuplicateSession):
            self.manager.start(b)

    def test_per_session_lock_rejects_mutation_and_expiry_skips_busy_app(self) -> None:
        case = self.incident()
        self.manager.start(case)
        session = self.manager._sessions[case["incident_id"]]
        self.assertTrue(session.lock.acquire(blocking=False))
        try:
            with self.assertRaises(SessionBusy):
                self.manager.approve(case["incident_id"])
            with self.assertRaises(SessionBusy):
                self.manager.discard(case["incident_id"])
            self.clock.advance(61)
            self.assertEqual(self.manager.expire_due(), [])
            self.assertEqual(self.manager.active_count, 1)
        finally:
            session.lock.release()
        self.assertEqual(self.manager.expire_due(), [case["incident_id"]])

    def test_human_review_is_not_approvable_and_can_be_discarded(self) -> None:
        case = self.incident(site="UNKNOWN-SYNTHETIC-SITE")
        receipt = self.manager.start(case)
        self.assertEqual(receipt["status"], "human_review")
        self.assertEqual([call["phase"] for call in receipt["model_calls"]], ["classify"])
        with self.assertRaises(InvalidSessionState):
            self.manager.approve(case["incident_id"])
        self.manager.discard(case["incident_id"])
        with self.assertRaises(DuplicateSession):
            self.manager.start(case)

    def test_invalid_input_is_rejected_before_reserving_id(self) -> None:
        bad = self.incident()
        bad["extra"] = "not accepted"
        with self.assertRaises(InvalidIncident):
            self.manager.start(bad)
        clean = {key: value for key, value in bad.items() if key != "extra"}
        receipt = self.manager.start(clean)
        self.assertEqual(receipt["status"], "pending_approval")


if __name__ == "__main__":
    unittest.main()
