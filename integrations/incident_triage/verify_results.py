#!/usr/bin/env python3
"""Independent source-redaction/template and accounting checks for the report.

This verifier does not import or re-run the upstream workflow. It independently
reconstructs the pinned regex outputs and request-template assembly, then
checks source usage arithmetic and pair relations. It is not an independent
LangGraph semantics implementation or proof of the source's policy.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "UPSTREAM_MANIFEST.json"
RUNNER_PATH = HERE / "run_study.py"
LOCK_PATH = HERE / "requirements.lock"
TEST_PATH = HERE / "test_study.py"
EXPECTED_CASES = {
    "pii_email_a", "pii_email_b", "pii_phone_a", "pii_phone_b",
    "pii_national_insurance_a", "pii_national_insurance_b",
    "retry_email_a", "retry_email_b", "public_text_a", "public_text_b",
    "unlisted_name_a", "unlisted_name_b", "mock_marker_absent",
    "mock_marker_present", "unknown_site_route",
    "pii_presence_absent", "pii_presence_present", "pii_count_one",
    "pii_count_two", "pii_type_email", "pii_type_phone",
    "upstream_default_mock",
}
EXPECTED_PAIRS = {
    ("pii_email_a", "pii_email_b"): "equal",
    ("pii_phone_a", "pii_phone_b"): "equal",
    ("pii_national_insurance_a", "pii_national_insurance_b"): "equal",
    ("retry_email_a", "retry_email_b"): "equal",
    ("public_text_a", "public_text_b"): "different",
    ("unlisted_name_a", "unlisted_name_b"): "different",
    ("mock_marker_absent", "mock_marker_present"): "different",
    ("pii_presence_absent", "pii_presence_present"): "different",
    ("pii_count_one", "pii_count_two"): "different",
    ("pii_type_email", "pii_type_phone"): "different",
    ("public_text_a", "upstream_default_mock"): "equal",
}
EXPECTED_DIMENSIONS = {
    ("pii_email_a", "pii_email_b"): "email value substitution with fixed redacted skeleton",
    ("pii_phone_a", "pii_phone_b"): "phone value substitution with fixed redacted skeleton",
    ("pii_national_insurance_a", "pii_national_insurance_b"): "national_insurance value substitution with fixed redacted skeleton",
    ("retry_email_a", "retry_email_b"): "email value substitution through one repair retry",
    ("public_text_a", "public_text_b"): "public non-PII content mutation",
    ("unlisted_name_a", "unlisted_name_b"): "unlisted name-like public text",
    ("mock_marker_absent", "mock_marker_present"): "mock-specific redaction-marker heuristic",
    ("pii_presence_absent", "pii_presence_present"): "PII presence changes redacted skeleton",
    ("pii_count_one", "pii_count_two"): "PII occurrence count changes redacted skeleton",
    ("pii_type_email", "pii_type_phone"): "PII pattern type changes redaction marker",
    ("public_text_a", "upstream_default_mock"): "injected wrapper versus upstream default mock factory",
}

CLASSIFY_SYSTEM = (
    'You classify the incident report of a UK facilities and security operation. '
    'Respond with ONLY JSON: {"category": one of '
    '["physical_security","cyber","safety","operational","environmental"], '
    '"severity": one of ["low","medium","high","critical"], '
    '"summary": string (max 280 chars), "people_at_risk": boolean}.'
)
ACTIONS_SYSTEM = (
    "You draft recommended actions for a triaged incident. Respond with ONLY a "
    "JSON array of 2-5 short imperative action strings, specific to the category "
    "and priority given."
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?:\+44\s?|0)\d{2,4}[\s-]?\d{3}[\s-]?\d{3,4}")
NI_NUMBER_RE = re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b")


def _independent_redact(text: str) -> str:
    """Independent transcription of the three pinned source substitutions."""
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return NI_NUMBER_RE.sub("[NI-NUMBER]", text)


class VerificationError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _projection(case: dict[str, Any]) -> dict[str, Any]:
    return {key: case[key] for key in ("calls", "usage", "node_events", "terminal")}


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    """Validate complete report and return a compact verification summary."""
    _require(isinstance(report, dict), "report must be an object")
    _require(report.get("format") == "orchlang-incident-triage-source-study"
             and report.get("version") == 1, "unknown report format/version")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source = report.get("source")
    _require(isinstance(source, dict), "source binding missing")
    _require(source.get("commit") == manifest["commit"]
             and source.get("git_tree") == manifest["git_tree"]
             and source.get("tracked_file_sha256") == manifest["tracked_file_sha256"]
             and source.get("license") == "MIT"
             and source.get("verified_before_and_after_execution") is True,
             "upstream pin binding or before/after source verification mismatch")
    _require(source.get("manifest_sha256") == _sha(MANIFEST_PATH.read_bytes()),
             "manifest digest mismatch")
    harness = report.get("harness")
    _require(isinstance(harness, dict), "harness binding missing")
    _require(harness.get("run_study_sha256") == _sha(RUNNER_PATH.read_bytes()),
             "runner digest mismatch; regenerate result")
    _require(harness.get("manifest_sha256") == _sha(MANIFEST_PATH.read_bytes()),
             "harness manifest digest mismatch")
    _require(harness.get("dependency_lock_sha256") == _sha(LOCK_PATH.read_bytes()),
             "dependency lock digest mismatch")
    _require(harness.get("verifier_sha256") == _sha(Path(__file__).read_bytes()),
             "verifier digest mismatch")
    _require(harness.get("test_sha256") == _sha(TEST_PATH.read_bytes()),
             "test digest mismatch")
    _require(harness.get("langgraph") == "1.2.14", "unexpected LangGraph version")
    _require(harness.get("pydantic") == "2.14.0", "unexpected Pydantic version")

    execution = report.get("execution")
    _require(isinstance(execution, dict), "execution metadata missing")
    _require(execution.get("mode") == "unmodified upstream source, direct LangGraph execution",
             "unsupported execution mode")
    _require(execution.get("outbound_provider_calls") == 0,
             "provider call must remain disabled")
    provider_config = execution.get("provider_configuration")
    _require(provider_config == {
        "TRIAGE_LLM": "mock", "default_factory_runs": 1, "injected_wrapper_runs": 21
    }, "upstream mock/default-factory execution modes differ")
    _require(execution.get("network_calls") == 0
             and all(item in execution.get("network_guard", "") for item in
                     ("socket.socket connect/send methods", "socket.create_connection",
                      "socket.getaddrinfo")),
             "socket network guard metadata missing")
    _require(execution.get("process_calls") == 0
             and all(item in execution.get("process_guard", "") for item in
                     ("subprocess.Popen/run", "os.system/popen")),
             "process creation guard metadata missing")
    _require(execution.get("case_count") == len(EXPECTED_CASES), "case count mismatch")
    cases_list = report.get("cases")
    _require(isinstance(cases_list, list), "cases must be an array")
    _require(len(cases_list) == len(EXPECTED_CASES), "case row count mismatch")
    cases = {case.get("case_id"): case for case in cases_list if isinstance(case, dict)}
    _require(set(cases) == EXPECTED_CASES, "case identifiers differ from the fixed corpus")
    input_digest = _sha(json.dumps(
        [cases[key]["input"] for key in sorted(cases)], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    _require(harness.get("input_corpus_sha256") == input_digest,
             "input corpus digest mismatch")

    total_calls = total_nodes = total_usage = 0
    for case_id, case in cases.items():
        calls = case.get("calls")
        usage = case.get("usage")
        nodes = case.get("node_events")
        _require(isinstance(calls, list) and isinstance(usage, list) and isinstance(nodes, list),
                 f"malformed call/event rows in {case_id}")
        _require(len(calls) == len(usage), f"call/usage count mismatch in {case_id}")
        for index, (call, cost) in enumerate(zip(calls, usage, strict=True)):
            _require(isinstance(call, dict) and
                     set(call) == {"system", "user", "response"},
                     f"malformed call {case_id}[{index}]")
            _require(all(isinstance(call[k], str) for k in ("system", "user", "response")),
                     f"non-text call {case_id}[{index}]")
            _require(cost.get("index") == index, f"usage order mismatch in {case_id}")
            expected_input = max(1, len(call["system"] + call["user"]) // 4)
            expected_output = max(1, len(call["response"]) // 4)
            _require(cost.get("input_tokens") == expected_input
                     and cost.get("output_tokens") == expected_output,
                     f"source estimate arithmetic mismatch in {case_id}[{index}]")
            _require(cost.get("cost_usd") == 0.0,
                     f"mock cost should be zero in {case_id}[{index}]")
            _require(cost.get("node") in {"classify", "draft"},
                     f"unexpected model-call node in {case_id}")
        cost_tracker = case.get("cost_tracker")
        _require(isinstance(cost_tracker, dict)
                 and cost_tracker.get("model_name") == "mock"
                 and cost_tracker.get("entry_count") == len(usage)
                 and cost_tracker.get("total_cost_usd") == round(
                     sum(row["cost_usd"] for row in usage), 6
                 ), f"source CostTracker summary mismatch in {case_id}")
        for event in nodes:
            _require(isinstance(event, dict), f"malformed event in {case_id}")
            _require(event.get("kind") == "interrupt" or
                     (event.get("kind") == "node" and isinstance(event.get("name"), str)),
                     f"unknown event kind in {case_id}")
            if event.get("kind") == "interrupt":
                _require(event == {"kind": "interrupt", "before_node": "dispatch"},
                         f"unexpected interrupt event in {case_id}")
        node_names = [event["name"] for event in nodes if event["kind"] == "node"]
        if case_id == "unknown_site_route":
            _require(node_names == ["classify", "enrich", "human_review"]
                     and not any(event["kind"] == "interrupt" for event in nodes),
                     "unknown-site route or terminal differs")
        else:
            _require(node_names == ["classify", "enrich", "prioritise", "draft"]
                     and sum(event["kind"] == "interrupt" for event in nodes) == 1,
                     f"ordinary successful route differs in {case_id}")

        _require(case.get("execution_mode") in {
            "injected_mock_wrapper", "upstream_default_mock"
        }, f"unknown execution mode in {case_id}")
        _require(case.get("network_attempt_count") == 0,
                 f"network API was attempted in {case_id}")
        _require(case.get("process_attempt_count") == 0,
                 f"process creation was attempted in {case_id}")
        _require(case["input"].get("reported_by") == "synthetic operator"
                 and isinstance(case["input"].get("thread_id"), str),
                 f"input metadata incomplete in {case_id}")
        redacted = _independent_redact(case["input"].get("text", ""))
        _require(case.get("source_redacted_text") == redacted,
                 f"source redaction does not match independent transcription in {case_id}")
        _require(calls, f"missing model calls in {case_id}")
        classify_user = f"INCIDENT REPORT: {redacted}"
        _require(calls[0]["system"] == CLASSIFY_SYSTEM
                 and calls[0]["user"] == classify_user,
                 f"classifier template/input mismatch in {case_id}")

        if len(calls) == 3:
            repair = calls[1]
            _require(repair["system"] == CLASSIFY_SYSTEM
                     and repair["user"].startswith(
                         classify_user + "\n\nYour previous response failed validation with:\n"
                     )
                     and repair["user"].endswith(
                         "\nRespond again with ONLY valid JSON for the schema."
                     ), f"repair request was not derived from source template in {case_id}")
            classification_call = calls[1]
            expected_cost_nodes = ["classify", "classify", "draft"]
        else:
            classification_call = calls[0]
            expected_cost_nodes = ["classify", "draft"] if len(calls) == 2 else ["classify"]
        _require([row.get("node") for row in usage] == expected_cost_nodes,
                 f"source call accounting/order mismatch in {case_id}")
        parsed_classification = json.loads(classification_call["response"])
        _require(parsed_classification == case["terminal"].get("classification"),
                 f"classification response/state mismatch in {case_id}")
        if expected_cost_nodes[-1] == "draft":
            terminal = case["terminal"]
            cls, priority = terminal.get("classification"), terminal.get("priority")
            _require(isinstance(cls, dict) and isinstance(priority, dict),
                     f"draft state inputs missing in {case_id}")
            expected_draft_user = (
                f"category: {cls['category']}\npriority: {priority['level']}\n"
                f"summary: {cls['summary']}"
            )
            draft_call = calls[-1]
            _require(draft_call["system"] == ACTIONS_SYSTEM
                     and draft_call["user"] == expected_draft_user,
                     f"draft template/input mismatch in {case_id}")
            parsed_actions = json.loads(draft_call["response"])
            _require(terminal.get("recommended_actions") == [str(item) for item in parsed_actions][:5],
                     f"draft response/report mismatch in {case_id}")

        total_calls += len(calls)
        total_usage += len(usage)
        total_nodes += sum(event["kind"] == "node" for event in nodes)

    _require(total_calls == execution.get("model_call_count")
             == execution.get("cost_usage_rows"), "global call/usage totals differ")
    _require(total_nodes == execution.get("source_node_invocations"),
             "global node total differs")
    _require((len(cases), total_calls, total_nodes) == (22, 45, 87),
             "fixed source execution totals differ")

    pair_rows = report.get("pairs")
    _require(isinstance(pair_rows, list), "pair rows missing")
    observed_pairs = {}
    for pair in pair_rows:
        _require(isinstance(pair, dict), "malformed pair row")
        key = (pair.get("left"), pair.get("right"))
        _require(key not in observed_pairs, "duplicate pair row")
        observed_pairs[key] = pair
    _require(set(observed_pairs) == set(EXPECTED_PAIRS), "pair corpus differs")
    for key, expected in EXPECTED_PAIRS.items():
        pair = observed_pairs[key]
        left, right = cases[key[0]], cases[key[1]]
        actual = "equal" if _projection(left) == _projection(right) else "different"
        _require(pair.get("expected_relation") == expected
                 and pair.get("observed_relation") == actual == expected
                 and pair.get("dimension") == EXPECTED_DIMENSIONS[key],
                 f"pair relation mismatch: {key}")
        if key == ("public_text_a", "upstream_default_mock"):
            _require(left["input"] == right["input"],
                     "default-mock pair must run the identical source input and thread")
            _require(left["execution_mode"] == "injected_mock_wrapper"
                     and right["execution_mode"] == "upstream_default_mock",
                     "default mock factory path was not exercised")
        else:
            left_metadata = {k: v for k, v in left["input"].items() if k != "text"}
            right_metadata = {k: v for k, v in right["input"].items() if k != "text"}
            _require(left_metadata == right_metadata,
                     f"paired inputs changed non-text metadata: {key}")
            _require(left["input"]["text"] != right["input"]["text"],
                     f"paired inputs did not vary text: {key}")
        if key in {
            ("pii_email_a", "pii_email_b"),
            ("pii_phone_a", "pii_phone_b"),
            ("pii_national_insurance_a", "pii_national_insurance_b"),
            ("retry_email_a", "retry_email_b"),
        }:
            _require(left["source_redacted_text"] == right["source_redacted_text"],
                     f"value-substitution pair changed redacted text: {key}")
            _require(left["calls"][0]["user"] == right["calls"][0]["user"],
                     f"value-substitution pair changed classifier request: {key}")
        if key in {
            ("pii_presence_absent", "pii_presence_present"),
            ("pii_count_one", "pii_count_two"),
            ("pii_type_email", "pii_type_phone"),
        }:
            _require(left["source_redacted_text"] != right["source_redacted_text"]
                     and left["calls"][0]["user"] != right["calls"][0]["user"],
                     f"PII shape change was lost after source redaction: {key}")

    shape_cases = {
        "pii_presence_absent": 0,
        "pii_presence_present": 1,
        "pii_count_one": 1,
        "pii_count_two": 2,
        "pii_type_email": 1,
        "pii_type_phone": 0,
    }
    for case_id, email_count in shape_cases.items():
        redacted = cases[case_id]["source_redacted_text"]
        _require(redacted.count("[EMAIL]") == email_count,
                 f"email presence/count not represented as expected in {case_id}")
    _require("[EMAIL]" in cases["pii_type_email"]["source_redacted_text"]
             and "[PHONE]" in cases["pii_type_phone"]["source_redacted_text"],
             "PII type markers were conflated")

    for kind, raw_values in {
        "email": ("person@example.invalid", "a.very.long.synthetic.name@department.example.invalid"),
        "phone": ("07700 900123", "0113 496 0999"),
        "national_insurance": ("QQ 12 34 56 C", "ZZ987654Z"),
    }.items():
        left, right = cases[f"pii_{kind}_a"], cases[f"pii_{kind}_b"]
        _require(all(value in case["input"]["text"] for case, value in zip((left, right), raw_values, strict=True)),
                 f"unexpected synthetic source values for {kind}")
        for case in (left, right):
            call_bytes = json.dumps(case["calls"], ensure_ascii=False)
            _require(all(value not in call_bytes for value in raw_values),
                     f"listed PII marker appeared in model request/response for {kind}")

    retry_a, retry_b = cases["retry_email_a"], cases["retry_email_b"]
    _require(len(retry_a["calls"]) == len(retry_b["calls"]) == 3,
             "repair experiment did not make three calls")
    _require("failed validation" in retry_a["calls"][1]["user"].lower()
             and retry_a["calls"][1]["user"] == retry_b["calls"][1]["user"],
             "repair request was not source-generated/equal")
    _require(retry_a["calls"][0]["response"] == retry_b["calls"][0]["response"]
             == "intentional deterministic schema-failure probe",
             "fault injection differs from declared fixed retry")

    default_mock = cases["upstream_default_mock"]
    _require(default_mock["execution_mode"] == "upstream_default_mock"
             and default_mock["calls"] == cases["public_text_a"]["calls"]
             and default_mock["usage"] == cases["public_text_a"]["usage"],
             "upstream default mock factory differs from injected wrapper")

    route = cases["unknown_site_route"]
    route_nodes = [event["name"] for event in route["node_events"] if event["kind"] == "node"]
    _require(route_nodes == ["classify", "enrich", "human_review"],
             "unknown-site branch did not follow source route")
    _require(len(route["calls"]) == 1 and route["terminal"]["kind"] == "human_review",
             "unknown-site branch unexpectedly drafted or dispatched")

    marker_a, marker_b = cases["mock_marker_absent"], cases["mock_marker_present"]
    _require(marker_a["terminal"]["classification"]["category"] == "operational"
             and marker_b["terminal"]["classification"]["category"] == "cyber",
             "mock marker probe changed; re-review mock semantics")
    _require(report.get("assumptions_and_limits") and
             any("all-input theorem" in item for item in report["assumptions_and_limits"]),
             "scope limitations missing")
    _require(any(f.get("id") == "mock-email-marker-heuristic"
                 for f in report.get("findings", [])),
             "mock-specific caveat missing")

    return {
        "status": "verified",
        "source_commit": source["commit"],
        "case_count": len(cases),
        "call_count": total_calls,
        "source_node_invocations": total_nodes,
        "equal_pii_value_pairs": 3,
        "equal_retry_pairs": 1,
        "different_pii_shape_pairs": 3,
        "different_non_pii_or_mock_control_pairs": 3,
        "default_mock_factory_pair": "equal",
        "scope": "artifact integrity, independent source-redaction/template replay, exact recorded pair comparisons, and source-estimate arithmetic; not LangGraph semantic re-execution",
    }


def load_and_verify(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > 16 * 1024 * 1024:
            raise VerificationError("report exceeds 16 MiB bound")
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot parse report: {error}") from error
    return verify_report(doc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path,
                        default=HERE / "results" / "source_study.json")
    args = parser.parse_args(argv)
    try:
        result = load_and_verify(args.report)
    except (VerificationError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, sort_keys=True),
              file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
