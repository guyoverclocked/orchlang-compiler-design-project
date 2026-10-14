from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.provider_calibration import provider_calibration as calibration


MODEL = "test-model-exact-id"
RATES = {
    "input": "0.05",
    "cached_input": "0.005",
    "cache_write": "0.0625",
    "output": "0.25",
}


def plan_fixture() -> dict:
    manifest = calibration.load_manifest()
    with patch.object(
        calibration,
        "local_tokenizer_count",
        side_effect=lambda text, encoding: {
            "status": "ok", "count": len(text), "encoding": encoding,
            "package_version": "offline-test", "scope": "visible_prompt_text_only",
        },
    ):
        return calibration.build_plan(
            manifest,
            provider="openai",
            model=MODEL,
            local_encoding="test_encoding",
            rates_per_million=RATES,
            budget_usd="0.25",
        )


def approved(plan: dict) -> dict:
    return {
        "affirmative": True,
        "provider": plan["provider"],
        "model": plan["requested_model"],
        "max_wire_requests": plan["caps"]["max_wire_requests"],
        "budget_usd": plan["approved_budget_usd"],
        "plan_sha256": plan["plan_sha256"],
    }


class FakeTransport:
    def __init__(self, *, fail_at: int | None = None, failure: Exception | None = None,
                 input_count: int = 21, malformed_count: bool = False,
                 usage: dict | None = None, incomplete_usage_at_response: int | None = None,
                 incomplete_usage: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_at = fail_at
        self.failure = failure or calibration.TransportError("synthetic transport failure")
        self.input_count = input_count
        self.malformed_count = malformed_count
        self.incomplete_usage_at_response = incomplete_usage_at_response
        self.incomplete_usage = incomplete_usage
        self.usage = usage or {
            "input_tokens": 21,
            "input_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 2},
            "output_tokens": 9,
            "output_tokens_details": {"reasoning_tokens": 6},
            "total_tokens": 30,
        }

    def post(self, endpoint: str, payload: dict) -> calibration.TransportResponse:
        self.calls.append((endpoint, payload))
        if self.fail_at == len(self.calls):
            raise self.failure
        if endpoint == "responses/input_tokens":
            body = {"object": "response.input_tokens"}
            if not self.malformed_count:
                body["input_tokens"] = self.input_count
            return calibration.TransportResponse(200, body, {"x-request-id": "req-count"})
        response_no = sum(1 for previous, _ in self.calls if previous == "responses")
        response_usage = self.usage
        if response_no == self.incomplete_usage_at_response:
            response_usage = self.incomplete_usage
        return calibration.TransportResponse(
            200,
            {
                "id": f"resp-{response_no}",
                "object": "response",
                "created_at": 1791936000,
                "model": MODEL,
                "status": "completed",
                "service_tier": "default",
                "output": [{
                    "type": "message",
                    "id": f"msg-{response_no}",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "synthetic output"}],
                }],
                "usage": response_usage,
            },
            {"x-request-id": f"req-{response_no}", "authorization": "do-not-store"},
        )


class ProviderCalibrationTests(unittest.TestCase):
    def test_default_validation_is_offline_and_manifest_hashes_are_frozen(self) -> None:
        stdout = io.StringIO()
        with patch.object(calibration.urllib.request, "urlopen", side_effect=AssertionError("network used")):
            with patch.object(calibration.urllib.request, "build_opener", side_effect=AssertionError("opener created")):
                with patch.object(calibration, "OpenAIResponsesTransport", side_effect=AssertionError("transport created")):
                    with contextlib.redirect_stdout(stdout):
                        self.assertEqual(calibration.main([]), 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["network"], "disabled")
        manifest = calibration.load_manifest()
        self.assertEqual(len(manifest["prompts"]), 4)
        self.assertEqual(len(manifest["cases"]), 8)
        self.assertEqual(manifest["provider_selection"].startswith("pending"), True)
        self.assertIsNone(manifest["model_selection"])

    def test_envelope_manifest_binds_immutable_source_identity_and_records_artifact_drift(self) -> None:
        manifest = calibration.load_manifest()
        profiles = {item["id"]: item for item in manifest["envelope_profiles"]}
        self.assertEqual(profiles["envelope_messages"]["input_form"], "messages")
        self.assertEqual(profiles["envelope_text"]["input_form"], "text")
        for profile in profiles.values():
            self.assertEqual(len(profile["immutable_source_identity"]["sha256"]), 64)
            self.assertEqual(len(profile["immutable_source_identity"]["commit"]), 40)
            self.assertIn("pending", profile["capsule_result_artifact_binding"])
            self.assertIn("shape only", profile["profile_scope"])
        self.assertIn("drift_observed", manifest["artifact_hash_guard_finding"]["status"])
        self.assertEqual(len(manifest["artifact_hash_guard_finding"]["historical_observations"]), 2)
        binding = calibration.load_lineage_binding(manifest)
        self.assertEqual(binding["frozen_readiness_manifest_sha256"], manifest["manifest_sha256"])
        self.assertEqual(len(binding["artifacts"]), 2)
        tampered_binding = json.loads(json.dumps(binding))
        tampered_binding["artifacts"][0]["capsule_result_artifact_sha256"] = "0" * 64
        tampered_binding["binding_sha256"] = calibration.sha256_json({
            k: v for k, v in tampered_binding.items() if k != "binding_sha256"
        })
        with self.assertRaisesRegex(calibration.CalibrationError, "result artifact digest mismatch"):
            calibration.validate_lineage_binding(manifest, binding=tampered_binding)
        self.assertTrue(all("text" in prompt for prompt in manifest["prompts"]))
        for case in manifest["cases"]:
            self.assertEqual(case["payload_template"]["response_payload"]["model"], "<EXACT_MODEL_ID_PENDING>")
            self.assertEqual(len(case["payload_template_sha256"]), 64)
            self.assertEqual(case["payload_template"]["response_payload"]["max_output_tokens"], 64)
            self.assertIs(case["payload_template"]["response_payload"]["store"], False)

    def test_local_tokenizer_cache_miss_cannot_fetch_vocab(self) -> None:
        fake_tiktoken = types.ModuleType("tiktoken")
        fake_tiktoken.__version__ = "offline-fake"
        fake_load = types.ModuleType("tiktoken.load")
        fake_load.read_file = lambda _path: self.fail("vocabulary network reader must be blocked")

        def fake_get_encoding(_name):
            return fake_load.read_file("https://vocab.invalid/fake")

        fake_tiktoken.get_encoding = fake_get_encoding
        fake_tiktoken.load = fake_load
        with patch.dict(sys.modules, {"tiktoken": fake_tiktoken, "tiktoken.load": fake_load}):
            result = calibration.local_tokenizer_count("public prompt", "encoding-that-misses-cache")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "encoding_vocabulary_not_cached")
        self.assertIsNone(result["count"])

    def test_local_tokenizer_uses_an_available_local_encoding(self) -> None:
        fake_tiktoken = types.ModuleType("tiktoken")
        fake_tiktoken.__version__ = "offline-fake"
        fake_load = types.ModuleType("tiktoken.load")
        fake_load.read_file = lambda _path: self.fail("cached path should not read vocab file")
        fake_tiktoken.get_encoding = lambda _name: types.SimpleNamespace(
            encode=lambda text, disallowed_special=(): list(range(len(text)))
        )
        fake_tiktoken.load = fake_load
        with patch.dict(sys.modules, {"tiktoken": fake_tiktoken, "tiktoken.load": fake_load}):
            result = calibration.local_tokenizer_count("local text", "cached-encoding")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], len("local text"))

    def test_openai_transport_redirects_are_disabled_to_preserve_wire_call_cap(self) -> None:
        handler = calibration._NoRedirectHandler()
        request = calibration.urllib.request.Request("https://example.invalid")
        self.assertIsNone(handler.redirect_request(request, None, 302, "Found", {}, "https://other.invalid"))

    def test_frozen_plan_hashes_both_exact_payloads_and_reserves_input_preflights(self) -> None:
        plan = plan_fixture()
        calibration.validate_plan(plan)
        self.assertEqual(plan["caps"]["max_response_requests"], 8)
        self.assertEqual(plan["caps"]["max_wire_requests"], 16)
        self.assertEqual(plan["caps"]["max_output_tokens_per_case"], 64)
        self.assertEqual(plan["nominal_cost_reserve"]["preflight_requests_assumed_billed_as_input"], True)
        self.assertEqual(plan["nominal_cost_reserve"]["amount_usd"], "0.0011520000")
        first = plan["cases"][0]
        self.assertEqual(first["request_payload"]["store"], False)
        self.assertEqual(first["request_payload"]["max_output_tokens"], 64)
        self.assertEqual(first["request_sha256"], calibration.sha256_json({
            "provider": "openai", "endpoint": "responses", "payload": first["request_payload"],
        }))
        self.assertEqual(first["input_count_request_sha256"], calibration.sha256_json({
            "provider": "openai", "endpoint": "responses/input_tokens",
            "payload": first["input_count_payload"],
        }))

    def test_execution_refuses_missing_or_mismatched_human_approval_before_transport(self) -> None:
        plan = plan_fixture()
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            with self.assertRaisesRegex(calibration.CalibrationError, "affirmative authorization"):
                calibration.execute_plan(plan, transport, output)
            self.assertFalse(output.exists())
            self.assertEqual(transport.calls, [])
            bad = approved(plan)
            bad["budget_usd"] = "0.01"
            with self.assertRaisesRegex(calibration.CalibrationError, "authorization budget_usd"):
                calibration.execute_plan(plan, transport, output, approval=bad)
            self.assertEqual(transport.calls, [])

    def test_cost_guard_rejects_a_plan_that_exceeds_the_user_budget(self) -> None:
        manifest = calibration.load_manifest()
        with patch.object(calibration, "local_tokenizer_count", return_value={"status": "unavailable"}):
            with self.assertRaisesRegex(calibration.CalibrationError, "exceeds approved budget"):
                calibration.build_plan(
                    manifest,
                    provider="openai",
                    model=MODEL,
                    local_encoding="test_encoding",
                    rates_per_million={
                        "input": "1000", "cached_input": "1000", "cache_write": "1000", "output": "1000",
                    },
                    budget_usd="0.25",
                )

    def test_plan_validation_rejects_changed_rates_without_recomputed_reserve(self) -> None:
        plan = plan_fixture()
        plan["pricing_assumptions_usd_per_million"]["output"] = "1000"
        plan["plan_sha256"] = calibration.sha256_json({k: v for k, v in plan.items() if k != "plan_sha256"})
        with self.assertRaisesRegex(calibration.CalibrationError, "cost reserve does not match"):
            calibration.validate_plan(plan)

    def test_input_cap_or_malformed_preflight_stops_before_responses(self) -> None:
        plan = plan_fixture()
        for transport, expected in (
            (FakeTransport(input_count=1025), "input_token_cap_exceeded"),
            (FakeTransport(malformed_count=True), "malformed_input_count"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "receipts.json"
                result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
                persisted = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(result["run_status"], "stopped_before_responses") if expected == "input_token_cap_exceeded" else self.assertEqual(result["run_status"], "stopped_after_error")
                self.assertEqual(persisted["receipts"][-1]["request_status"], expected)
                self.assertFalse(any(endpoint == "responses" for endpoint, _ in transport.calls))
                self.assertEqual(len(transport.calls), 1)

    def test_response_usage_above_output_cap_stops_batch(self) -> None:
        plan = plan_fixture()
        over_cap_usage = {
            "input_tokens": 21,
            "output_tokens": 65,
            "total_tokens": 86,
            "input_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 6},
        }
        transport = FakeTransport(incomplete_usage_at_response=1, incomplete_usage=over_cap_usage)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["run_status"], "stopped_after_token_cap_anomaly")
        self.assertEqual(len(transport.calls), 9)
        self.assertEqual(persisted["receipts"][-1]["request_status"], "reported_usage_exceeds_token_cap")

    def test_batch_is_limited_to_16_calls_and_records_full_usage_without_raw_prompts(self) -> None:
        plan = plan_fixture()
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            saved = output.read_text(encoding="utf-8")
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["run_status"], "complete")
        self.assertEqual(len(transport.calls), 16)
        self.assertEqual(result["wire_requests_started"], 16)
        self.assertEqual(result["response_requests_started"], 8)
        response_receipts = [r for r in persisted["receipts"] if r["endpoint"] == "responses"]
        self.assertEqual(len(response_receipts), 8)
        usage = response_receipts[0]["response_metadata"]["usage"]
        self.assertEqual(usage["status"], "complete")
        self.assertEqual(usage["cached_input_tokens"], 4)
        self.assertEqual(usage["cache_write_tokens"], 2)
        self.assertEqual(usage["reasoning_tokens"], 6)
        self.assertEqual(usage["output_tokens"], 9)
        self.assertEqual(usage["raw_usage"]["output_tokens_details"]["reasoning_tokens"], 6)
        self.assertNotIn("synthetic output", saved)
        self.assertNotIn("ORCH-CAL-0", saved)
        self.assertNotIn("do-not-store", saved)
        self.assertIn("text_sha256", response_receipts[0]["response_metadata"]["output_items"][0]["content_items"][0])

    def test_missing_inconsistent_and_malformed_usage_are_not_silently_repaired(self) -> None:
        self.assertEqual(calibration.normalized_usage(None)["status"], "missing_or_malformed")
        self.assertEqual(
            calibration.normalized_usage({"input_tokens": 3, "output_tokens": 2})["status"],
            "incomplete_or_inconsistent",
        )
        self.assertEqual(
            calibration.normalized_usage({
                "input_tokens": 3, "output_tokens": 2, "total_tokens": 99,
            })["status"],
            "incomplete_or_inconsistent",
        )
        self.assertEqual(
            calibration.normalized_usage({
                "input_tokens": True, "output_tokens": 2, "total_tokens": 3,
            })["status"],
            "incomplete_or_inconsistent",
        )
        self.assertEqual(
            calibration.normalized_usage({
                "input_tokens": 3, "output_tokens": 2, "total_tokens": 5,
                "input_tokens_details": {"cached_tokens": 4},
                "output_tokens_details": {"reasoning_tokens": 3},
            })["status"],
            "incomplete_or_inconsistent",
        )
        malformed_nonfinite = calibration.normalized_usage({
            "input_tokens": float("nan"), "output_tokens": 2, "total_tokens": 3,
        })
        self.assertEqual(malformed_nonfinite["status"], "incomplete_or_inconsistent")
        self.assertEqual(malformed_nonfinite["raw_usage"]["input_tokens"], {"$non_finite_float": "nan"})

    def test_nonfinite_malformed_usage_is_durable_and_stops_partial_batch(self) -> None:
        plan = plan_fixture()
        malformed = {
            "input_tokens": float("nan"),
            "output_tokens": 2,
            "total_tokens": 3,
        }
        transport = FakeTransport(incomplete_usage_at_response=1, incomplete_usage=malformed)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["run_status"], "stopped_after_incomplete_usage")
        self.assertEqual(len(transport.calls), 9)
        raw_input = persisted["receipts"][-1]["response_metadata"]["usage"]["raw_usage"]["input_tokens"]
        self.assertEqual(raw_input, {"$non_finite_float": "nan"})

    def test_incomplete_usage_preserves_partial_batch_and_stops_without_retry(self) -> None:
        plan = plan_fixture()
        missing_usage = {"input_tokens": 12, "output_tokens": 3}
        transport = FakeTransport(incomplete_usage_at_response=3, incomplete_usage=missing_usage)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["run_status"], "stopped_after_incomplete_usage")
        self.assertEqual(len(transport.calls), 11)
        self.assertEqual(persisted["receipts"][-1]["endpoint"], "responses")
        self.assertEqual(persisted["receipts"][-1]["request_status"], "response_usage_incomplete")
        self.assertEqual(persisted["receipts"][-1]["response_metadata"]["usage"]["status"], "incomplete_or_inconsistent")
        self.assertEqual(sum(1 for e, _ in transport.calls if e == "responses"), 3)
        self.assertEqual(persisted["receipts"][8]["response_metadata"]["usage"]["status"], "complete")
        self.assertEqual(persisted["receipts"][9]["response_metadata"]["usage"]["status"], "complete")

    def test_non_completed_response_is_recorded_and_stops_batch(self) -> None:
        plan = plan_fixture()
        transport = FakeTransport()
        original_post = transport.post

        def incomplete_post(endpoint: str, payload: dict) -> calibration.TransportResponse:
            response = original_post(endpoint, payload)
            if endpoint == "responses":
                response.body["status"] = "incomplete"
                response.body["incomplete_details"] = {"reason": "max_output_tokens"}
            return response

        transport.post = incomplete_post
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["run_status"], "stopped_after_non_completed_response")
        receipt = persisted["receipts"][-1]
        self.assertEqual(receipt["response_metadata"]["status"], "incomplete")
        self.assertEqual(receipt["response_metadata"]["incomplete_details"]["reason"], "max_output_tokens")
        self.assertEqual(len(transport.calls), 9)

    def test_transport_error_is_redacted_persisted_and_never_retried(self) -> None:
        plan = plan_fixture()
        transport = FakeTransport(
            fail_at=1,
            failure=calibration.TransportError("Bearer sk-secretcredential123456 echoed input", error_type="transport"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            saved = output.read_text(encoding="utf-8")
            persisted = json.loads(saved)
        self.assertEqual(result["run_status"], "stopped_after_error")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(persisted["receipts"][0]["request_status"], "transport_error_unknown_delivery")
        self.assertNotIn("secretcredential", saved)
        self.assertNotIn("echoed input", saved)
        self.assertEqual(persisted["receipts"][0]["transport_error"]["error_text"]["message_stored"], False)

    def test_http_error_code_and_status_are_recorded_without_retry(self) -> None:
        plan = plan_fixture()
        transport = FakeTransport(
            fail_at=1,
            failure=calibration.TransportError(
                "invalid request", http_status=429, error_type="rate_limit_error", error_code="rate_limit_exceeded",
                headers={"X-Request-Id": "req-429", "Authorization": "do-not-store"},
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "receipts.json"
            result = calibration.execute_plan(plan, transport, output, approval=approved(plan))
            persisted = json.loads(output.read_text(encoding="utf-8"))
        receipt = persisted["receipts"][0]
        self.assertEqual(result["run_status"], "stopped_after_error")
        self.assertEqual(receipt["request_status"], "http_error")
        self.assertEqual(receipt["transport_error"]["http_status"], 429)
        self.assertEqual(receipt["transport_error"]["error_code"], "rate_limit_exceeded")
        self.assertEqual(receipt["transport_error"]["provider_headers"]["x-request-id"], "req-429")
        self.assertNotIn("authorization", receipt["transport_error"]["provider_headers"])
        self.assertEqual(len(transport.calls), 1)

    def test_tampered_request_payload_is_rejected_by_plan_validation(self) -> None:
        plan = plan_fixture()
        plan["cases"][0]["request_payload"]["input"] = "tampered"
        plan["plan_sha256"] = calibration.sha256_json({k: v for k, v in plan.items() if k != "plan_sha256"})
        with self.assertRaisesRegex(calibration.CalibrationError, "input-count payload differs"):
            calibration.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
