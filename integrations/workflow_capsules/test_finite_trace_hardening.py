from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import run_capsule
import strict_json
import verify_finite_trace as verifier


ARTIFACTS = {
    "dili": verifier.ARTIFACT_DIR / "didilili-langgraphllm-one-node-finite-oracle-v1.json",
    "joshua": verifier.ARTIFACT_DIR / "joshuac215-kb-agent-sequential-async-finite-oracle-v1.json",
}


class StrictJSONTests(unittest.TestCase):
    def test_rejects_duplicate_keys_including_escaped_aliases(self) -> None:
        for raw in (b'{"x":1,"x":2}', b'{"x":1,"\\u0078":2}'):
            with self.subTest(raw=raw), self.assertRaises(strict_json.StrictJSONError):
                strict_json.loads(raw)

    def test_rejects_noncanonical_or_unbounded_numbers(self) -> None:
        for raw in (b"1e3", b"NaN", b"Infinity", b"-0", b"-0.0", b"0.8750"):
            with self.subTest(raw=raw), self.assertRaises(strict_json.StrictJSONError):
                strict_json.loads(raw)
        self.assertIs(type(strict_json.loads(b"true")), bool)
        with self.assertRaises(verifier.VerificationError):
            verifier.require_exact_int(True, "tamper.version")
        with self.assertRaises(verifier.VerificationError):
            verifier.fraction("1" + "0" * verifier.MAX_WEIGHT_DIGITS)
        with self.assertRaises(verifier.VerificationError):
            verifier.fraction(str(1 << verifier.MAX_WEIGHT_BITS))
        with self.assertRaises(verifier.VerificationError):
            verifier._bounded_fraction(verifier.Fraction(1 << 8193, 1), "test arithmetic")

    def test_rejects_invalid_utf8_surrogates_and_resource_limits(self) -> None:
        with self.assertRaises(strict_json.StrictJSONError):
            strict_json.loads(b'"\xff"')
        with self.assertRaises(strict_json.StrictJSONError):
            strict_json.loads(b'"\\ud800"')
        with self.assertRaises(strict_json.StrictJSONError):
            strict_json.loads(b"[" * (strict_json.MAX_JSON_DEPTH + 2) + b"0" + b"]" * (strict_json.MAX_JSON_DEPTH + 2))
        with self.assertRaises(strict_json.StrictJSONError):
            strict_json.loads(b"0" * (strict_json.MAX_JSON_BYTES + 1))
        too_many = b"[" + b",".join([b"0"] * (strict_json.MAX_JSON_ITEMS + 1)) + b"]"
        with self.assertRaises(strict_json.StrictJSONError):
            strict_json.loads(too_many)

    def test_rejects_symlink_json_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=verifier.ARTIFACT_DIR) as directory:
            root = Path(directory)
            target = root / "target.json"
            link = root / "link.json"
            target.write_text("{}", encoding="utf-8")
            link.symlink_to(target)
            with self.assertRaises(strict_json.StrictJSONError):
                strict_json.load(link)


class RunnerProtocolTests(unittest.TestCase):
    def test_preflight_requires_exact_typed_true_keyset(self) -> None:
        good = {key: True for key in sorted(run_capsule.PREFLIGHT_KEYS)}
        self.assertEqual(run_capsule._parse_preflight("PREFLIGHT_JSON:" + json.dumps(good)), good)
        self.assertIsNone(run_capsule._parse_preflight('PREFLIGHT_JSON:{"network_denied":true}'))
        duplicate = 'PREFLIGHT_JSON:{"fork_denied":true,"fork_denied":true,"network_denied":true,"unlisted_user_file_denied":true,"writes_denied":true}'
        self.assertIsNone(run_capsule._parse_preflight(duplicate))
        bool_as_int = dict(good, writes_denied=1)
        self.assertIsNone(run_capsule._parse_preflight("PREFLIGHT_JSON:" + json.dumps(bool_as_int)))
        false_check = dict(good, network_denied=False)
        self.assertIsNone(run_capsule._parse_preflight("PREFLIGHT_JSON:" + json.dumps(false_check)))

    def test_worker_protocol_is_strict_and_bounded(self) -> None:
        self.assertEqual(run_capsule._parse_capsule_output('CAPSULE_JSON:{"ok":true}'), ({"ok": True}, None))
        for raw in (
            'CAPSULE_JSON:{"x":1,"x":2}',
            'CAPSULE_JSON:{"x":1e2}',
            'CAPSULE_JSON:"not an object"',
        ):
            with self.subTest(raw=raw):
                result, error = run_capsule._parse_capsule_output(raw)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
        oversized = "x" * (run_capsule.MAX_CHILD_OUTPUT_BYTES + 1)
        result, error = run_capsule._parse_capsule_output(oversized)
        self.assertIsNone(result)
        self.assertIn("exceeds", error or "")


class FiniteTraceVerifierTamperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = {name: strict_json.load(path) for name, path in ARTIFACTS.items()}

    def _verify_tamper(self, artifact: str, mutate, message: str | None = None) -> None:
        changed = copy.deepcopy(self.base[artifact])
        mutate(changed)
        with tempfile.TemporaryDirectory(dir=verifier.ARTIFACT_DIR, prefix=".tampered-capsule-") as directory:
            path = Path(directory) / "capsule.json"
            path.write_text(json.dumps(changed, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            with self.assertRaises((verifier.VerificationError, strict_json.StrictJSONError)) as caught:
                verifier.verify(path)
            if message:
                self.assertIn(message, str(caught.exception))

    def test_both_frozen_capsules_still_pass(self) -> None:
        for path in ARTIFACTS.values():
            with self.subTest(path=path.name):
                certificate = verifier.verify(path)
                self.assertEqual(certificate["verification"], "PASS_CONDITIONAL_FINITE_TRACE_CERTIFICATE")

    def test_artifact_cannot_select_or_omit_replay_fields(self) -> None:
        self._verify_tamper("dili", lambda d: d["result"]["worlds"][0]["independent_replay"].update(compared_fields=[]), "fixed complete")
        self._verify_tamper("joshua", lambda d: d["result"]["worlds"][0]["independent_replay"]["compared_fields"].pop(), "fixed complete")
        self._verify_tamper("dili", lambda d: d["result"]["worlds"][0]["independent_replay"]["compared_fields"].append("trace_projection"), "duplicates")

    def test_weight_source_and_worker_tampering_fails_closed(self) -> None:
        self._verify_tamper("dili", lambda d: d["result"]["finite_support"]["model_responses"][0].update(weight="1/2"), "schedule support")
        self._verify_tamper("joshua", lambda d: d["result"]["worlds"][0].update(probability="1/6"), "replay differs")
        self._verify_tamper("dili", lambda d: d["result"]["source"].update(sha256="0" * 64), "fixed pinned-source")
        self._verify_tamper("joshua", lambda d: d.update(worker_sha256="0" * 64), "worker hash mismatch")

    def test_trace_state_and_status_tampering_fails(self) -> None:
        def drop_trace_event(data):
            data["result"]["worlds"][0]["trace_projection"]["ordered_events" if "ordered_events" in data["result"]["worlds"][0]["trace_projection"] else "ordered_execution_events"].pop()
        self._verify_tamper("dili", drop_trace_event, "replay differs")

        def alter_state(data):
            world = data["result"]["worlds"][0]
            state = world["trace_projection"]["last_observed_state"]
            state["messages"][0]["$message"]["data"]["content"] = "forged user input"
        self._verify_tamper("joshua", alter_state, "replay differs")

        def alter_status(data):
            world = next(item for item in data["result"]["worlds"] if item["run_status"] == "provider_error")
            world["run_status"] = "complete"
        self._verify_tamper("dili", alter_status, "replay differs")

        def alter_both_status_copies(data):
            world = next(item for item in data["result"]["worlds"] if item["run_status"] == "provider_error")
            world["run_status"] = "complete"
            world["independent_replay"]["second_observation"]["run_status"] = "complete"
        self._verify_tamper("joshua", alter_both_status_copies, "outcome/status pair")

    def test_response_status_is_checked_against_finite_oracle_schedule(self) -> None:
        def change_response(data):
            world = data["result"]["worlds"][0]
            event_key = "ordered_execution_events" if "ordered_execution_events" in world["trace_projection"] else "ordered_events"
            event = next(event for event in world["trace_projection"][event_key] if event["kind"] == "model_response")
            event["status"] = "raised"
            world["independent_replay"]["second_observation"]["trace_projection"] = copy.deepcopy(world["trace_projection"])
            world["trace_sha256"] = verifier.sha_value(world["trace_projection"])
            world["independent_replay"]["second_observation"]["trace_sha256"] = world["trace_sha256"]
        self._verify_tamper("dili", change_response)

    def test_preflight_and_bool_integer_tampering_fails(self) -> None:
        self._verify_tamper("dili", lambda d: d["preflight"]["checks"].pop("network_denied"), "fields differ")
        self._verify_tamper("joshua", lambda d: d.update(exit_code=True), "booleans are not integers")
        self._verify_tamper("dili", lambda d: d["result"]["finite_support"].update(elementary_world_count=True), "schedule support")
        def bool_horizon(data):
            world = data["result"]["worlds"][0]
            world["horizon_observed"]["model_calls"] = True
            world["independent_replay"]["second_observation"]["horizon_observed"]["model_calls"] = True
        self._verify_tamper("dili", bool_horizon, "booleans are not integers")

    def test_source_reader_rejects_symlink_and_escape(self) -> None:
        with tempfile.TemporaryDirectory(dir=verifier.ARTIFACT_DIR) as directory:
            root = Path(directory)
            target = root / "target.py"
            link = root / "link.py"
            target.write_text("x = 1\n", encoding="utf-8")
            link.symlink_to(target)
            with self.assertRaises(verifier.VerificationError):
                verifier._read_regular_beneath(root, Path("link.py"))
            with self.assertRaises(verifier.VerificationError):
                verifier._read_regular_beneath(root, Path("../escape.py"))

    def test_failed_cli_verification_removes_stale_success_certificate(self) -> None:
        capsule_id = "didilili-langgraphllm-one-node-finite-oracle-v1"
        with tempfile.TemporaryDirectory(dir=verifier.ARTIFACT_DIR, prefix=".stale-certificate-") as directory:
            output_dir = Path(directory)
            output = output_dir / f"{capsule_id}-certificate.json"
            output.write_text('{"verification":"PASS_CONDITIONAL_FINITE_TRACE_CERTIFICATE"}', encoding="utf-8")
            with mock.patch.object(verifier, "CERTIFICATE_DIR", output_dir), \
                 mock.patch.object(verifier, "verify", side_effect=verifier.VerificationError("tamper rejected")), \
                 mock.patch.object(sys, "argv", ["verify_finite_trace.py", str(ARTIFACTS["dili"])]), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verifier.main(), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
