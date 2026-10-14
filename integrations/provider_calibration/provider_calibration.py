#!/usr/bin/env python3
"""Prepare and (only after explicit approval) run provider usage calibration.

The default command validates a public fixture manifest and never constructs a
network transport.  The OpenAI adapter is deliberately small and uses the
Responses API over urllib; tests inject a fake transport instead.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Protocol


SCHEMA_VERSION = 1
ADAPTER_VERSION = "orchlang-provider-calibration/0.1.0"
API_BASE = "https://api.openai.com/v1"
DEFAULT_MANIFEST = Path(__file__).with_name("public_request_manifest.json")
DEFAULT_LINEAGE_BINDING = (
    Path(__file__).resolve().parents[2]
    / "research/scp_strengthening/provider_calibration/CAPSULE_LINEAGE_BINDING.json"
)
MAX_RESPONSE_CASES = 8
MAX_WIRE_REQUESTS = 16
MAX_INPUT_TOKENS_PER_CASE = 1024
MAX_OUTPUT_TOKENS_PER_CASE = 64
PROPOSED_BUDGET_USD = Decimal("0.25")
PENDING_MODEL_SENTINEL = "<EXACT_MODEL_ID_PENDING>"
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(OPENAI_API_KEY\s*[=:]\s*)[^\s,;]+"),
)


class CalibrationError(Exception):
    """A safe-to-display validation or execution error."""


class TransportError(Exception):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_type: str | None = None,
        error_code: str | None = None,
        error_param: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.error_type = error_type
        self.error_code = error_code
        self.error_param = error_param
        self.headers = headers or {}


class Transport(Protocol):
    def post(self, endpoint: str, payload: dict[str, Any]) -> "TransportResponse": ...


@dataclass(frozen=True)
class TransportResponse:
    http_status: int
    body: dict[str, Any]
    headers: dict[str, str]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _strict_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise CalibrationError(f"{label} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise CalibrationError(f"{label} must be a decimal string") from exc
    if not result.is_finite() or result < 0:
        raise CalibrationError(f"{label} must be finite and nonnegative")
    return result


def _manifest_digest(manifest: dict[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return sha256_json(body)


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"cannot read manifest: {exc.__class__.__name__}") from exc
    validate_manifest(manifest)
    if Path(path).resolve() == DEFAULT_MANIFEST.resolve():
        validate_lineage_binding(manifest)
    return manifest


def load_lineage_binding(manifest: dict[str, Any], path: str | Path = DEFAULT_LINEAGE_BINDING) -> dict[str, Any]:
    try:
        binding = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"cannot read capsule lineage binding: {exc.__class__.__name__}") from exc
    validate_lineage_binding(manifest, binding=binding, path=path)
    return binding


def validate_lineage_binding(
    manifest: dict[str, Any],
    *,
    binding: Any | None = None,
    path: str | Path = DEFAULT_LINEAGE_BINDING,
) -> None:
    if binding is None:
        try:
            binding = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationError(f"cannot read capsule lineage binding: {exc.__class__.__name__}") from exc
    if not isinstance(binding, dict) or binding.get("schema_version") != 1:
        raise CalibrationError("capsule lineage binding is missing or malformed")
    expected_digest = sha256_json({k: v for k, v in binding.items() if k != "binding_sha256"})
    if binding.get("binding_sha256") != expected_digest:
        raise CalibrationError("capsule lineage binding SHA-256 does not match its contents")
    if binding.get("binding_status") != "final_capsule_artifacts_declared_final_and_bound":
        raise CalibrationError("capsule result artifacts have not been declared final")
    if binding.get("frozen_readiness_manifest_sha256") != manifest.get("manifest_sha256"):
        raise CalibrationError("capsule lineage binding references a different frozen manifest")
    if binding.get("supersedes_pending_capsule_result_marker") is not True:
        raise CalibrationError("capsule lineage binding does not supersede the manifest's pending marker")
    if binding.get("historical_artifact_drift_guard_finding") != manifest.get("artifact_hash_guard_finding"):
        raise CalibrationError("capsule lineage binding dropped the recorded artifact-drift finding")
    profiles = {profile["id"]: profile for profile in manifest["envelope_profiles"]}
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(profiles):
        raise CalibrationError("capsule lineage binding has an unexpected artifact set")
    repository_root = Path(__file__).resolve().parents[2]
    seen_profiles: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise CalibrationError("capsule lineage artifact entry is malformed")
        profile_id = artifact.get("envelope_profile_id")
        profile = profiles.get(profile_id)
        if profile is None or profile_id in seen_profiles:
            raise CalibrationError("capsule lineage binding has unknown or duplicate profile")
        seen_profiles.add(profile_id)
        capsule_id = profile["source_capsule_id"]
        relative_path = artifact.get("capsule_result_artifact_path")
        expected_relative = f"research/scp_strengthening/workflow_capsules/{capsule_id}.json"
        if relative_path != expected_relative or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise CalibrationError(f"capsule lineage artifact path is unsafe for {profile_id}")
        if artifact.get("capsule_id") != capsule_id:
            raise CalibrationError(f"capsule lineage id mismatch for {profile_id}")
        if artifact.get("envelope_profile_sha256") != profile["profile_sha256"]:
            raise CalibrationError(f"capsule lineage profile digest mismatch for {profile_id}")
        if artifact.get("source_event_pointer") != profile["source_event_pointer"]:
            raise CalibrationError(f"capsule lineage event pointer mismatch for {profile_id}")
        if artifact.get("immutable_source_identity") != profile["immutable_source_identity"]:
            raise CalibrationError(f"immutable source identity mismatch for {profile_id}")
        artifact_path = repository_root / relative_path
        try:
            raw = artifact_path.read_bytes()
        except OSError as exc:
            raise CalibrationError(f"final capsule result artifact unavailable for {profile_id}") from exc
        if sha256_bytes(raw) != artifact.get("capsule_result_artifact_sha256"):
            raise CalibrationError(f"final capsule result artifact digest mismatch for {profile_id}")
        try:
            result = json.loads(raw.decode("utf-8")).get("result", {})
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CalibrationError(f"final capsule result artifact malformed for {profile_id}") from exc
        source = result.get("source", {}) if isinstance(result, dict) else {}
        identity = profile["immutable_source_identity"]
        if not isinstance(result, dict) or result.get("capsule_id") != capsule_id:
            raise CalibrationError(f"final capsule metadata id mismatch for {profile_id}")
        if any(source.get(key) != identity[key] for key in identity):
            raise CalibrationError(f"final capsule source identity drift for {profile_id}")


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise CalibrationError("manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationError("unsupported manifest schema_version")
    if manifest.get("manifest_sha256") != _manifest_digest(manifest):
        raise CalibrationError("manifest SHA-256 does not match its contents")
    prompts = manifest.get("prompts")
    profiles = manifest.get("envelope_profiles")
    cases = manifest.get("cases")
    if not isinstance(prompts, list) or not isinstance(profiles, list) or not isinstance(cases, list):
        raise CalibrationError("manifest requires prompts, envelope_profiles, and cases arrays")
    prompt_ids: set[str] = set()
    for prompt in prompts:
        if not isinstance(prompt, dict) or not isinstance(prompt.get("id"), str):
            raise CalibrationError("each prompt requires a string id")
        if prompt["id"] in prompt_ids:
            raise CalibrationError("prompt ids must be unique")
        prompt_ids.add(prompt["id"])
        text = prompt.get("text")
        if not isinstance(text, str) or not text.strip():
            raise CalibrationError("prompt text must be a nonempty string")
        if prompt.get("text_sha256") != sha256_bytes(text.encode("utf-8")):
            raise CalibrationError(f"prompt SHA-256 mismatch for {prompt['id']}")
    profile_ids: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
            raise CalibrationError("each envelope profile requires a string id")
        if profile["id"] in profile_ids:
            raise CalibrationError("envelope profile ids must be unique")
        profile_ids.add(profile["id"])
        if profile.get("input_form") not in {"text", "messages"}:
            raise CalibrationError(f"unsupported input_form in {profile['id']}")
        if profile.get("profile_sha256") != sha256_json(
            {k: v for k, v in profile.items() if k != "profile_sha256"}
        ):
            raise CalibrationError(f"envelope profile SHA-256 mismatch for {profile['id']}")
        source_identity = profile.get("immutable_source_identity")
        if not isinstance(source_identity, dict) or not all(
            isinstance(source_identity.get(key), str) and source_identity[key]
            for key in ("repository", "commit", "path", "sha256", "selection_sha256")
        ):
            raise CalibrationError(f"immutable source identity is missing for {profile['id']}")
    prompts_by_id = {prompt["id"]: prompt for prompt in prompts}
    profiles_by_id = {profile["id"]: profile for profile in profiles}
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise CalibrationError("each case requires a string id")
        if case["id"] in case_ids:
            raise CalibrationError("case ids must be unique")
        case_ids.add(case["id"])
        if case.get("prompt_id") not in prompt_ids or case.get("envelope_profile_id") not in profile_ids:
            raise CalibrationError(f"case {case['id']} refers to an unknown prompt or profile")
        expected_template = frozen_payload_template(
            case,
            prompts_by_id[case["prompt_id"]]["text"],
            profiles_by_id[case["envelope_profile_id"]],
        )
        if case.get("payload_template") != expected_template:
            raise CalibrationError(f"payload template differs from the frozen profile for {case['id']}")
        if case.get("payload_template_sha256") != sha256_json(expected_template):
            raise CalibrationError(f"payload template SHA-256 mismatch for {case['id']}")
    if len(cases) != MAX_RESPONSE_CASES:
        raise CalibrationError(f"this readiness fixture must contain exactly {MAX_RESPONSE_CASES} cases")
    caps = manifest.get("proposed_caps")
    if not isinstance(caps, dict):
        raise CalibrationError("manifest requires proposed_caps")
    if caps.get("max_response_requests") != MAX_RESPONSE_CASES:
        raise CalibrationError("max_response_requests must match the frozen cases")
    if caps.get("max_input_tokens_per_case") != MAX_INPUT_TOKENS_PER_CASE:
        raise CalibrationError("input token cap differs from the reviewed readiness fixture")
    if caps.get("max_output_tokens_per_case") != MAX_OUTPUT_TOKENS_PER_CASE:
        raise CalibrationError("output token cap differs from the reviewed readiness fixture")
    if caps.get("max_wire_requests") != MAX_WIRE_REQUESTS:
        raise CalibrationError("max_wire_requests must include eight preflights and eight responses")
    if caps.get("proposed_budget_usd") != str(PROPOSED_BUDGET_USD):
        raise CalibrationError("proposed budget differs from the reviewed readiness fixture")


def build_request_payload(case: dict[str, Any], prompt_text: str, model: str) -> dict[str, Any]:
    """Build the exact Responses payload without credentials or provider traffic."""
    profile = case["envelope_profile"]
    input_value: Any
    if profile["input_form"] == "text":
        input_value = prompt_text
    else:
        input_value = [{"role": "user", "content": prompt_text}]
    return {
        "model": model,
        "input": input_value,
        "max_output_tokens": MAX_OUTPUT_TOKENS_PER_CASE,
        "store": False,
    }


def frozen_payload_template(case: dict[str, Any], prompt_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Return the exact pre-model payload skeleton; the sentinel is never executable."""
    mapped_case = {**case, "envelope_profile": profile}
    response_payload = build_request_payload(mapped_case, prompt_text, PENDING_MODEL_SENTINEL)
    count_payload = {"model": PENDING_MODEL_SENTINEL, "input": response_payload["input"]}
    return {
        "provider_adapter": "openai-responses",
        "response_endpoint": "responses",
        "response_payload": response_payload,
        "input_count_endpoint": "responses/input_tokens",
        "input_count_payload": count_payload,
    }


def resolved_cases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    validate_manifest(manifest)
    prompts = {p["id"]: p for p in manifest["prompts"]}
    profiles = {p["id"]: p for p in manifest["envelope_profiles"]}
    result: list[dict[str, Any]] = []
    for item in manifest["cases"]:
        result.append(
            {
                **item,
                "prompt": prompts[item["prompt_id"]],
                "envelope_profile": profiles[item["envelope_profile_id"]],
            }
        )
    return result


def abstract_declared_count(text: str) -> int:
    """Legacy character heuristic, retained as a distinct declared observer."""
    return max(1, len(text) // 4)


def local_tokenizer_count(text: str, encoding_name: str) -> dict[str, Any]:
    """Count visible text from a locally cached tiktoken encoding, never fetching vocab data."""
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return {"status": "unavailable", "reason": "tiktoken_not_installed", "count": None,
                "encoding": encoding_name, "package_version": None,
                "scope": "visible_prompt_text_only; excludes envelope serialization and provider framing"}
    try:
        load_module = importlib.import_module("tiktoken.load")

        class CacheMiss(Exception):
            pass

        # tiktoken's normal cache-miss path downloads the vocabulary. Replace only its
        # underlying file reader while loading; a cached file still works, while any
        # attempted fetch becomes a structured unavailable observation.
        def deny_vocabulary_fetch(_blobpath: str) -> bytes:
            raise CacheMiss("encoding vocabulary is not in the local cache")

        original_reader = load_module.read_file
        load_module.read_file = deny_vocabulary_fetch
        try:
            encoding = tiktoken.get_encoding(encoding_name)
        finally:
            load_module.read_file = original_reader
        count = len(encoding.encode(text, disallowed_special=()))
        version = getattr(tiktoken, "__version__", "unknown")
    except CacheMiss:
        return {"status": "unavailable", "reason": "encoding_vocabulary_not_cached", "count": None,
                "encoding": encoding_name, "package_version": getattr(tiktoken, "__version__", "unknown"),
                "scope": "visible_prompt_text_only; excludes envelope serialization and provider framing"}
    except Exception as exc:  # encoding lookup/encoding failure is a recorded observer failure.
        return {"status": "error", "reason": exc.__class__.__name__, "count": None,
                "encoding": encoding_name, "package_version": getattr(tiktoken, "__version__", "unknown"),
                "scope": "visible_prompt_text_only; excludes envelope serialization and provider framing"}
    return {"status": "ok", "reason": None, "count": count,
            "encoding": encoding_name, "package_version": version,
            "scope": "visible_prompt_text_only; excludes envelope serialization and provider framing"}


def normalized_usage(raw: Any) -> dict[str, Any]:
    """Preserve full provider counters and report validity without inventing missing values."""
    if not isinstance(raw, dict):
        return {
            "status": "missing_or_malformed",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cached_input_tokens": None,
            "cache_write_tokens": None,
            "reasoning_tokens": None,
            "raw_usage": _json_safe(raw),
        }
    input_tokens = raw.get("input_tokens")
    output_tokens = raw.get("output_tokens")
    total_tokens = raw.get("total_tokens")
    input_details = raw.get("input_tokens_details")
    output_details = raw.get("output_tokens_details")
    cached = input_details.get("cached_tokens") if isinstance(input_details, dict) else None
    cache_write = input_details.get("cache_write_tokens") if isinstance(input_details, dict) else None
    reasoning = output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
    required_valid = all(_strict_int(v) for v in (input_tokens, output_tokens, total_tokens))
    details_valid = all(v is None or _strict_int(v) for v in (cached, cache_write, reasoning))
    consistent = required_valid and total_tokens == input_tokens + output_tokens
    detail_consistent = (
        required_valid
        and (cached is None or cached <= input_tokens)
        and (cache_write is None or cache_write <= input_tokens)
        and (reasoning is None or reasoning <= output_tokens)
    )
    status = "complete" if required_valid and details_valid and consistent and detail_consistent else "incomplete_or_inconsistent"
    return {
        "status": status,
        "input_tokens": input_tokens if _strict_int(input_tokens) else None,
        "output_tokens": output_tokens if _strict_int(output_tokens) else None,
        "total_tokens": total_tokens if _strict_int(total_tokens) else None,
        "cached_input_tokens": cached if _strict_int(cached) else None,
        "cache_write_tokens": cache_write if _strict_int(cache_write) else None,
        "reasoning_tokens": reasoning if _strict_int(reasoning) else None,
        "raw_usage": _json_safe(raw),
    }


def _json_safe(value: Any) -> Any:
    """Keep malformed non-finite usage JSON-representable for durable receipts."""
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return {"$non_finite_float": repr(value)}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _redact_error_text(message: Any) -> dict[str, Any]:
    text = str(message or "")
    digest = sha256_bytes(text.encode("utf-8", errors="replace"))
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    # Provider messages can echo private input. Keep only a digest and length.
    return {"message_sha256": digest, "message_chars": len(text), "message_stored": False,
            "redacted_for_secret_patterns": redacted != text}


def _error_record(exc: BaseException) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exception_type": exc.__class__.__name__,
        "error_text": _redact_error_text(str(exc)),
    }
    for key in ("http_status", "error_type", "error_code", "error_param"):
        value = getattr(exc, key, None)
        if value is not None:
            result[key] = value
    headers = getattr(exc, "headers", None)
    if isinstance(headers, dict):
        safe_headers = _safe_response_headers(headers)
        if safe_headers:
            result["provider_headers"] = safe_headers
    return result


def _safe_response_headers(headers: dict[str, str]) -> dict[str, str]:
    keep = {"x-request-id", "openai-processing-ms", "openai-version", "date", "retry-after"}
    return {k.lower(): v for k, v in headers.items() if k.lower() in keep}


def response_summary(body: dict[str, Any]) -> dict[str, Any]:
    output = body.get("output")
    output_items: list[dict[str, Any]] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                output_items.append({"type": "malformed"})
                continue
            summary: dict[str, Any] = {}
            for key in ("type", "id", "status", "role", "name", "call_id", "code", "language"):
                if key in item and isinstance(item[key], (str, int, bool)):
                    summary[key] = item[key]
            if item.get("type") == "message":
                contents = item.get("content")
                if isinstance(contents, list):
                    summary["content_items"] = []
                    for part in contents:
                        if not isinstance(part, dict):
                            summary["content_items"].append({"type": "malformed"})
                            continue
                        part_summary = {k: part[k] for k in ("type", "status") if k in part and isinstance(part[k], (str, int, bool))}
                        text = part.get("text")
                        if isinstance(text, str):
                            part_summary["text_chars"] = len(text)
                            part_summary["text_sha256"] = sha256_bytes(text.encode("utf-8"))
                        output_text = part.get("output_text")
                        if isinstance(output_text, str):
                            part_summary["text_chars"] = len(output_text)
                            part_summary["text_sha256"] = sha256_bytes(output_text.encode("utf-8"))
                        summary["content_items"].append(part_summary)
            for key in ("finish_reason", "refusal"):
                if key in item and isinstance(item[key], (str, bool)):
                    summary[key] = item[key]
            output_items.append(summary)
    error = body.get("error")
    safe_error = None
    if isinstance(error, dict):
        safe_error = {
            key: error[key]
            for key in ("type", "code", "param")
            if key in error and isinstance(error[key], (str, int, bool))
        }
        if "message" in error:
            safe_error["message"] = _redact_error_text(error["message"])
    details = body.get("incomplete_details")
    incomplete = {k: v for k, v in details.items() if k in {"reason"} and isinstance(v, (str, int, bool))} if isinstance(details, dict) else None
    return {
        "response_id": body.get("id") if isinstance(body.get("id"), str) else None,
        "response_object": body.get("object") if isinstance(body.get("object"), str) else None,
        "created_at": body.get("created_at") if _strict_int(body.get("created_at")) else None,
        "returned_model": body.get("model") if isinstance(body.get("model"), str) else None,
        "status": body.get("status") if isinstance(body.get("status"), str) else None,
        "service_tier": body.get("service_tier") if isinstance(body.get("service_tier"), str) else None,
        "incomplete_details": incomplete,
        "error": safe_error,
        "output_items": output_items,
        "usage": normalized_usage(body.get("usage")),
        "raw_usage_sha256": sha256_json(_json_safe(body.get("usage"))) if body.get("usage") is not None else None,
    }


def _money_per_million(token_count: int, rate: Decimal) -> Decimal:
    return (Decimal(token_count) * rate / Decimal(1_000_000)).quantize(
        Decimal("0.0000000001"), rounding=ROUND_CEILING
    )


def build_plan(
    manifest: dict[str, Any],
    *,
    provider: str,
    model: str,
    local_encoding: str,
    rates_per_million: dict[str, str],
    budget_usd: str,
) -> dict[str, Any]:
    validate_manifest(manifest)
    if provider != "openai":
        raise CalibrationError("the included live adapter currently supports provider=openai only")
    if not model or model.strip() != model:
        raise CalibrationError("model must be a nonempty exact provider model ID")
    if not local_encoding:
        raise CalibrationError("local_encoding must be named explicitly")
    required_rates = {"input", "cached_input", "cache_write", "output"}
    if set(rates_per_million) != required_rates:
        raise CalibrationError("rates must specify input, cached_input, cache_write, and output")
    rates = {k: _decimal(v, f"rate {k}") for k, v in rates_per_million.items()}
    budget = _decimal(budget_usd, "budget_usd")
    if budget > PROPOSED_BUDGET_USD:
        raise CalibrationError(f"budget_usd exceeds proposed limit {PROPOSED_BUDGET_USD}")
    cases = resolved_cases(manifest)
    plans = []
    for case in cases:
        payload = build_request_payload(case, case["prompt"]["text"], model)
        count_payload = {"model": model, "input": payload["input"]}
        local_text = case["prompt"]["text"]
        plans.append({
            "case_id": case["id"],
            "prompt_id": case["prompt_id"],
            "prompt_sha256": case["prompt"]["text_sha256"],
            "envelope_profile_id": case["envelope_profile_id"],
            "request_payload": payload,
            "input_count_payload": count_payload,
            "request_sha256": sha256_json({"provider": provider, "endpoint": "responses", "payload": payload}),
            "input_count_request_sha256": sha256_json({"provider": provider, "endpoint": "responses/input_tokens", "payload": count_payload}),
            "abstract_declared_observer": {
                "input_tokens": abstract_declared_count(local_text),
                "output_tokens": None,
                "method": "max(1, len(UTF-8-decoded prompt string in Python code points) // 4); envelope overhead excluded",
            },
            "local_tokenizer_observer": local_tokenizer_count(local_text, local_encoding),
        })
    max_input = MAX_INPUT_TOKENS_PER_CASE
    max_output = MAX_OUTPUT_TOKENS_PER_CASE
    worst_input_rate = max(rates["input"], rates["cached_input"], rates["cache_write"])
    preflight_cost = sum(
        (_money_per_million(max_input, worst_input_rate) for _ in plans), Decimal("0")
    )
    response_cost = sum(
        (_money_per_million(max_input, worst_input_rate)
         + _money_per_million(max_output, rates["output"]) for _ in plans), Decimal("0")
    )
    cost_bound = preflight_cost + response_cost
    if cost_bound > budget:
        raise CalibrationError(
            f"nominal worst-case estimate {cost_bound} exceeds approved budget {budget}; no response call can start"
        )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": manifest["experiment_id"],
        "source_manifest_sha256": manifest["manifest_sha256"],
        "provider": provider,
        "requested_model": model,
        "local_encoding": local_encoding,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "adapter_version": ADAPTER_VERSION,
        "caps": {
            "max_response_requests": len(plans),
            "max_input_tokens_per_case": max_input,
            "max_output_tokens_per_case": max_output,
            "max_wire_requests": MAX_WIRE_REQUESTS,
            "max_retries": 0,
            "automatic_escalation": False,
            "tools": False,
            "storage": False,
        },
        "approved_budget_usd": str(budget),
        "pricing_assumptions_usd_per_million": {k: str(v) for k, v in rates.items()},
        "nominal_cost_reserve": {
            "amount_usd": str(cost_bound),
            "preflight_requests_assumed_billed_as_input": True,
            "input_rate_used": str(worst_input_rate),
            "output_rate_used": str(rates["output"]),
            "note": "estimate only; reserves each preflight and response input at the highest listed input/cache rate and each response output at the supplied rate",
        },
        "cost_limit_is_not_invoice_cap": True,
        "cases": plans,
    }
    plan["plan_sha256"] = sha256_json(plan)
    return plan


def validate_plan(plan: Any) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationError("unsupported or malformed run plan")
    if plan.get("plan_sha256") != sha256_json({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise CalibrationError("run plan SHA-256 does not match its contents")
    if (plan.get("provider") != "openai" or not isinstance(plan.get("requested_model"), str)
            or not plan["requested_model"] or plan["requested_model"].strip() != plan["requested_model"]):
        raise CalibrationError("run plan must name an OpenAI provider and exact model")
    caps = plan.get("caps")
    if not isinstance(caps, dict) or caps.get("max_retries") != 0 or caps.get("automatic_escalation") is not False:
        raise CalibrationError("run plan must disable retries and automatic escalation")
    if caps.get("tools") is not False or caps.get("storage") is not False:
        raise CalibrationError("run plan must disable tools and response storage")
    if caps.get("max_response_requests") != MAX_RESPONSE_CASES or caps.get("max_wire_requests") != MAX_WIRE_REQUESTS:
        raise CalibrationError("run plan exceeds reviewed call caps")
    if caps.get("max_input_tokens_per_case") != MAX_INPUT_TOKENS_PER_CASE or caps.get("max_output_tokens_per_case") != MAX_OUTPUT_TOKENS_PER_CASE:
        raise CalibrationError("run plan token caps differ from the reviewed fixture")
    if not isinstance(plan.get("cases"), list) or len(plan["cases"]) != MAX_RESPONSE_CASES:
        raise CalibrationError("run plan has an unexpected number of cases")
    budget = _decimal(plan.get("approved_budget_usd"), "approved_budget_usd")
    if budget > PROPOSED_BUDGET_USD:
        raise CalibrationError("run plan exceeds the proposed budget")
    reserve = plan.get("nominal_cost_reserve")
    if not isinstance(reserve, dict):
        raise CalibrationError("run plan is missing its cost reserve")
    reserve_amount = _decimal(reserve.get("amount_usd"), "nominal reserve amount")
    if reserve_amount > budget:
        raise CalibrationError("run plan reserve exceeds its approved budget")
    if plan.get("cost_limit_is_not_invoice_cap") is not True:
        raise CalibrationError("run plan must disclose that the estimate is not an invoice cap")
    rates_object = plan.get("pricing_assumptions_usd_per_million")
    if not isinstance(rates_object, dict) or set(rates_object) != {"input", "cached_input", "cache_write", "output"}:
        raise CalibrationError("run plan pricing assumptions are malformed")
    rates = {key: _decimal(value, f"rate {key}") for key, value in rates_object.items()}
    high_input_rate = max(rates["input"], rates["cached_input"], rates["cache_write"])
    seen_cases: set[str] = set()
    for case in plan["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise CalibrationError("run plan case is malformed")
        if case["case_id"] in seen_cases:
            raise CalibrationError("run plan case ids must be unique")
        seen_cases.add(case["case_id"])
        payload = case.get("request_payload")
        count_payload = case.get("input_count_payload")
        if not isinstance(payload, dict) or not isinstance(count_payload, dict):
            raise CalibrationError("run plan request payload is malformed")
        if payload.get("model") != plan["requested_model"] or payload.get("store") is not False:
            raise CalibrationError("run plan request model or storage setting differs")
        if payload.get("max_output_tokens") != MAX_OUTPUT_TOKENS_PER_CASE:
            raise CalibrationError("run plan output token cap differs")
        expected_count_payload = {"model": payload.get("model"), "input": payload.get("input")}
        if count_payload != expected_count_payload:
            raise CalibrationError("input-count payload differs from the frozen response input")
        expected_request_hash = sha256_json({
            "provider": plan["provider"], "endpoint": "responses", "payload": payload,
        })
        expected_count_hash = sha256_json({
            "provider": plan["provider"], "endpoint": "responses/input_tokens", "payload": count_payload,
        })
        if case.get("request_sha256") != expected_request_hash or case.get("input_count_request_sha256") != expected_count_hash:
            raise CalibrationError("run plan request hash differs from its payload")
    expected_preflight = sum(
        (_money_per_million(MAX_INPUT_TOKENS_PER_CASE, high_input_rate) for _ in plan["cases"]),
        Decimal("0"),
    )
    expected_response = sum(
        (_money_per_million(MAX_INPUT_TOKENS_PER_CASE, high_input_rate)
         + _money_per_million(MAX_OUTPUT_TOKENS_PER_CASE, rates["output"])
         for _ in plan["cases"]),
        Decimal("0"),
    )
    expected_reserve = expected_preflight + expected_response
    if reserve_amount != expected_reserve:
        raise CalibrationError("run plan cost reserve does not match its rates and call/token caps")
    if reserve.get("preflight_requests_assumed_billed_as_input") is not True:
        raise CalibrationError("run plan must conservatively reserve input-count calls")


class OpenAIResponsesTransport:
    """Single-attempt OpenAI HTTP adapter. Construct only after explicit approval."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise CalibrationError("OPENAI_API_KEY is unavailable")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def post(self, endpoint: str, payload: dict[str, Any]) -> TransportResponse:
        if endpoint not in {"responses/input_tokens", "responses"}:
            raise CalibrationError("unsupported OpenAI endpoint")
        request = urllib.request.Request(
            f"{API_BASE}/{endpoint}",
            data=canonical_bytes(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": ADAPTER_VERSION,
            },
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=self._timeout_seconds) as response:
                raw_body = response.read()
                status = response.status
                headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw_body = exc.read()
            headers = dict(exc.headers.items()) if exc.headers else {}
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No retries: the provider may have received and billed the request.
            raise TransportError(
                exc.__class__.__name__,
                error_type="transport_error_unknown_delivery",
            ) from None
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TransportError(
                "provider returned a non-JSON response",
                http_status=status,
                error_type="malformed_provider_response",
            ) from None
        if not isinstance(body, dict):
            raise TransportError(
                "provider returned a non-object response",
                http_status=status,
                error_type="malformed_provider_response",
            )
        if status >= 400:
            error = body.get("error") if isinstance(body.get("error"), dict) else {}
            raise TransportError(
                str(error.get("message", "provider request failed")),
                http_status=status,
                error_type=str(error.get("type")) if error.get("type") is not None else None,
                error_code=str(error.get("code")) if error.get("code") is not None else None,
                error_param=str(error.get("param")) if error.get("param") is not None else None,
                headers=headers,
            )
        return TransportResponse(status, body, headers)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A redirect could create another wire request, so stop at the first response."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _input_count(body: dict[str, Any]) -> int | None:
    value = body.get("input_tokens")
    return value if _strict_int(value) else None


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(encoded)
        tmp.flush()
        os.fsync(tmp.fileno())
        temporary = Path(tmp.name)
    temporary.replace(path)


def execute_plan(
    plan: dict[str, Any],
    transport: Transport,
    output_path: str | Path,
    *,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one sequential batch through an injected transport; never retry."""
    validate_plan(plan)
    if approval is None or approval.get("affirmative") is not True:
        raise CalibrationError("explicit affirmative authorization is required")
    for key in ("provider", "model", "max_wire_requests", "budget_usd", "plan_sha256"):
        if approval.get(key) != {
            "provider": plan["provider"],
            "model": plan["requested_model"],
            "max_wire_requests": plan["caps"]["max_wire_requests"],
            "budget_usd": plan["approved_budget_usd"],
            "plan_sha256": plan["plan_sha256"],
        }[key]:
            raise CalibrationError(f"authorization {key} does not match the frozen plan")
    out_path = Path(output_path)
    state = {
        "schema_version": SCHEMA_VERSION,
        "receipt_schema": "provider-usage-receipt-v1",
        "run_plan_sha256": plan["plan_sha256"],
        "provider": plan["provider"],
        "requested_model": plan["requested_model"],
        "adapter_version": plan["adapter_version"],
        "run_status": "running",
        "wire_requests_started": 0,
        "response_requests_started": 0,
        "invoice_cap_guarantee": False,
        "receipts": [],
    }
    if out_path.exists():
        raise CalibrationError("output already exists; refusing to repeat or overwrite a prior run")
    _write_state(out_path, state)
    approved_budget = Decimal(plan["approved_budget_usd"])
    price = {k: Decimal(v) for k, v in plan["pricing_assumptions_usd_per_million"].items()}
    high_input_rate = max(price["input"], price["cached_input"], price["cache_write"])
    cumulative_reserve = Decimal("0")

    def attempt(case_id: str, endpoint: str, payload: dict[str, Any], digest: str) -> TransportResponse | None:
        nonlocal state
        state["wire_requests_started"] += 1
        receipt = {
            "case_id": case_id,
            "endpoint": endpoint,
            "request_sha256": digest,
            "request_status": "started",
            "http_status": None,
            "response_metadata": None,
            "transport_error": None,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        state["receipts"].append(receipt)
        _write_state(out_path, state)
        try:
            response = transport.post(endpoint, payload)
        except Exception as exc:  # Persist and stop even for unexpected adapter failures.
            receipt["request_status"] = (
                "http_error" if getattr(exc, "http_status", None) is not None
                else "transport_error_unknown_delivery"
            )
            receipt["transport_error"] = _error_record(exc)
            state["run_status"] = "stopped_after_error"
            _write_state(out_path, state)
            return None
        receipt["request_status"] = "returned"
        receipt["http_status"] = response.http_status
        receipt["provider_headers"] = _safe_response_headers(response.headers)
        receipt["response_metadata"] = response_summary(response.body) if endpoint == "responses" else {
            "input_tokens": _input_count(response.body),
            "response_object": response.body.get("object") if isinstance(response.body.get("object"), str) else None,
        }
        _write_state(out_path, state)
        if response.http_status >= 400:
            receipt["request_status"] = "http_error"
            state["run_status"] = "stopped_after_error"
            _write_state(out_path, state)
            return None
        return response

    try:
        preflight_counts: dict[str, int] = {}
        for case in plan["cases"]:
            count_response = attempt(
                case["case_id"], "responses/input_tokens", case["input_count_payload"],
                case["input_count_request_sha256"],
            )
            if count_response is None:
                return state
            count = _input_count(count_response.body)
            if count is None:
                state["receipts"][-1]["request_status"] = "malformed_input_count"
                state["run_status"] = "stopped_after_error"
                _write_state(out_path, state)
                return state
            if count > plan["caps"]["max_input_tokens_per_case"]:
                state["receipts"][-1]["request_status"] = "input_token_cap_exceeded"
                state["receipts"][-1]["reported_input_tokens"] = count
                state["run_status"] = "stopped_before_responses"
                _write_state(out_path, state)
                return state
            preflight_counts[case["case_id"]] = count
            reserve = _money_per_million(count, high_input_rate)
            cumulative_reserve += reserve
            state["receipts"][-1]["reported_input_tokens"] = count
            state["receipts"][-1]["nominal_preflight_cost_usd"] = str(reserve)
            state["nominal_preflight_cost_usd"] = str(cumulative_reserve)
        # Before the first completion call, reserve all count calls and every response's
        # exact preflight input plus the configured maximum generated-token allowance.
        completion_reserve = sum(
            (_money_per_million(preflight_counts[c["case_id"]], high_input_rate)
             + _money_per_million(MAX_OUTPUT_TOKENS_PER_CASE, price["output"])
             for c in plan["cases"]), Decimal("0")
        )
        if cumulative_reserve + completion_reserve > approved_budget:
            state["run_status"] = "stopped_before_responses_budget_guard"
            state["budget_guard"] = {
                "reserved_usd": str(cumulative_reserve + completion_reserve),
                "approved_budget_usd": str(approved_budget),
            }
            _write_state(out_path, state)
            return state
        for case in plan["cases"]:
            state["response_requests_started"] += 1
            response = attempt(
                case["case_id"], "responses", case["request_payload"], case["request_sha256"]
            )
            state["receipts"][-1]["abstract_declared_observer"] = case["abstract_declared_observer"]
            state["receipts"][-1]["local_tokenizer_observer"] = case["local_tokenizer_observer"]
            _write_state(out_path, state)
            if response is None:
                return state
            metadata = response_summary(response.body)
            state["receipts"][-1]["response_metadata"] = metadata
            state["receipts"][-1]["usage_complete"] = metadata["usage"]["status"] == "complete"
            if metadata["status"] != "completed":
                state["receipts"][-1]["request_status"] = "response_not_completed"
                state["run_status"] = "stopped_after_non_completed_response"
                _write_state(out_path, state)
                return state
            if metadata["usage"]["status"] != "complete":
                state["receipts"][-1]["request_status"] = "response_usage_incomplete"
                state["run_status"] = "stopped_after_incomplete_usage"
                _write_state(out_path, state)
                return state
            usage = metadata["usage"]
            expected_input = preflight_counts[case["case_id"]]
            observed_input = usage["input_tokens"]
            observed_output = usage["output_tokens"]
            state["receipts"][-1]["input_count_comparison"] = {
                "preflight_input_tokens": expected_input,
                "response_input_tokens": observed_input,
                "difference": observed_input - expected_input,
            }
            if (observed_input > plan["caps"]["max_input_tokens_per_case"]
                    or observed_output > plan["caps"]["max_output_tokens_per_case"]):
                state["receipts"][-1]["request_status"] = "reported_usage_exceeds_token_cap"
                state["receipts"][-1]["nominal_response_cost_usd"] = None
                state["run_status"] = "stopped_after_token_cap_anomaly"
                _write_state(out_path, state)
                return state
            response_cost = (
                _money_per_million(observed_input, high_input_rate)
                + _money_per_million(observed_output, price["output"])
            )
            state["receipts"][-1]["nominal_response_cost_usd"] = str(response_cost)
            state["observed_nominal_cost_usd"] = str(
                Decimal(state.get("observed_nominal_cost_usd", "0")) + response_cost
            )
            state["nominal_cost_estimate_usd"] = str(
                Decimal(state.get("nominal_preflight_cost_usd", "0"))
                + Decimal(state.get("observed_nominal_cost_usd", "0"))
            )
            _write_state(out_path, state)
    finally:
        if state["run_status"] == "running":
            state["run_status"] = "complete"
            state["nominal_cost_reserve_usd"] = str(cumulative_reserve + completion_reserve)
            if "nominal_cost_estimate_usd" not in state:
                state["nominal_cost_estimate_usd"] = state.get("nominal_preflight_cost_usd", "0")
            _write_state(out_path, state)
    return state


def _read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"cannot read JSON file: {exc.__class__.__name__}") from exc


def _write_json(path: str | Path, value: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="offline validation only; no network")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    plan = subparsers.add_parser("plan", help="freeze exact request bodies and hashes offline")
    plan.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    plan.add_argument("--provider", required=True)
    plan.add_argument("--model", required=True)
    plan.add_argument("--local-encoding", required=True)
    plan.add_argument("--input-price-per-million", required=True)
    plan.add_argument("--cached-input-price-per-million", required=True)
    plan.add_argument("--cache-write-price-per-million", required=True)
    plan.add_argument("--output-price-per-million", required=True)
    plan.add_argument("--budget-usd", required=True)
    plan.add_argument("--out", type=Path, required=True)
    execute = subparsers.add_parser("execute", help="execute a previously frozen plan after approval")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--approve-real-api", choices=("yes",), required=True)
    execute.add_argument("--provider", required=True)
    execute.add_argument("--model", required=True)
    execute.add_argument("--max-wire-requests", type=int, required=True)
    execute.add_argument("--budget-usd", required=True)
    execute.add_argument("--plan-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    effective_argv = sys.argv[1:] if argv is None else argv
    if not effective_argv:
        effective_argv = ["validate"]
    args = _build_parser().parse_args(effective_argv)
    try:
        if args.command == "validate":
            manifest = load_manifest(args.manifest)
            lineage_binding = load_lineage_binding(manifest) if args.manifest.resolve() == DEFAULT_MANIFEST.resolve() else None
            print(json.dumps({
                "status": "valid",
                "experiment_id": manifest["experiment_id"],
                "manifest_sha256": manifest["manifest_sha256"],
                "lineage_binding_sha256": lineage_binding["binding_sha256"] if lineage_binding else None,
                "response_cases": len(manifest["cases"]),
                "max_wire_requests": manifest["proposed_caps"]["max_wire_requests"],
                "network": "disabled",
            }, sort_keys=True))
            return 0
        if args.command == "plan":
            manifest = load_manifest(args.manifest)
            plan = build_plan(
                manifest,
                provider=args.provider,
                model=args.model,
                local_encoding=args.local_encoding,
                rates_per_million={
                    "input": args.input_price_per_million,
                    "cached_input": args.cached_input_price_per_million,
                    "cache_write": args.cache_write_price_per_million,
                    "output": args.output_price_per_million,
                },
                budget_usd=args.budget_usd,
            )
            _write_json(args.out, plan)
            print(json.dumps({
                "status": "plan_frozen_offline",
                "plan_path": str(args.out),
                "plan_sha256": plan["plan_sha256"],
                "response_requests": len(plan["cases"]),
                "max_wire_requests": plan["caps"]["max_wire_requests"],
                "nominal_cost_reserve_usd": plan["nominal_cost_reserve"]["amount_usd"],
                "network": "disabled",
            }, sort_keys=True))
            return 0
        if args.command == "execute":
            plan = _read_json(args.plan)
            validate_plan(plan)
            # Approval fields must agree with the already frozen plan before the credential
            # provider is consulted or an HTTP transport is constructed.
            approval = {
                "affirmative": args.approve_real_api == "yes",
                "provider": args.provider,
                "model": args.model,
                "max_wire_requests": args.max_wire_requests,
                "budget_usd": args.budget_usd,
                "plan_sha256": args.plan_sha256,
            }
            expected = {
                "provider": plan["provider"],
                "model": plan["requested_model"],
                "max_wire_requests": plan["caps"]["max_wire_requests"],
                "budget_usd": plan["approved_budget_usd"],
                "plan_sha256": plan["plan_sha256"],
            }
            if any(approval[k] != v for k, v in expected.items()):
                raise CalibrationError("approval values do not match the frozen plan")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise CalibrationError("OPENAI_API_KEY is unavailable; no request was attempted")
            transport = OpenAIResponsesTransport(api_key)
            result = execute_plan(plan, transport, args.output, approval=approval)
            print(json.dumps({
                "run_status": result["run_status"],
                "output_path": str(args.output),
                "wire_requests_started": result["wire_requests_started"],
                "response_requests_started": result["response_requests_started"],
                "invoice_cap_guarantee": result.get("invoice_cap_guarantee", False),
            }, sort_keys=True))
            return 0 if result["run_status"] == "complete" else 2
    except CalibrationError as exc:
        print(f"provider calibration: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
