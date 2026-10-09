#!/usr/bin/env python3
"""Independent standard-library verifier for the fixed protocol-path study.

It does not import the path runner, upstream modules, LangGraph, or Pydantic.
It reconstructs requests, outcomes, routes, source usage, and pair relations
from pinned fixture constants and the hash-verified source checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent
MANIFEST_PATH = INTEGRATION / "UPSTREAM_MANIFEST.json"
MAX_REPORT_BYTES = 8 * 1024 * 1024
EXPECTED_COMMIT = "c08f710acfeefe233329df613fe8358eaac5f350"
EXPECTED_TREE = "2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02"
EXPECTED_MANIFEST_SHA256 = "38e804b6470ad0c58f0da526f71ab39b7a7ad5a4a241c0e156569ba0ad203500"
EXPECTED_FILES = 23
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
USER_PREFIX = "INCIDENT REPORT: "
INCIDENT_BODY = "A synthetic security incident occurred at the rear gate. Contact "
EMAILS = {"a": "alpha.synthetic@example.invalid", "b": "bravo.synthetic@example.invalid"}
REPORTED_BY = "synthetic security operator"
MODEL = "gpt-4o-mini"
INPUT_PRICE = 0.15
OUTPUT_PRICE = 0.60
MAX_BUDGET = 0.05
BUDGET_PREFIX_SPACES = 400_000
GOOD_ACTIONS = ["Review the synthetic report and notify the site duty manager"]
FALLBACK_ACTIONS = ["Review incident manually; drafting agent returned invalid output"]


class ProtocolPathsVerificationError(ValueError):
    """The report, source binding, or reconstructed path observation is invalid."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolPathsVerificationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_report(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ProtocolPathsVerificationError("path report exceeds the byte cap")
    try:
        return raw, json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        if isinstance(error, ProtocolPathsVerificationError):
            raise
        raise ProtocolPathsVerificationError(f"invalid path report JSON: {error}") from error


def _classification(category: str = "physical_security", severity: str = "high",
                    summary: str = "Synthetic fixed classification summary.",
                    people_at_risk: bool = False) -> dict[str, Any]:
    return {"category": category, "severity": severity, "summary": summary,
            "people_at_risk": people_at_risk}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_parse_error(raw: str) -> str:
    try:
        json.loads(raw)
    except json.JSONDecodeError as error:
        return str(error)
    raise ProtocolPathsVerificationError("fixed malformed response unexpectedly parses as JSON")


LONG_SUMMARY = "S" * 295
NORMAL_CLASSIFICATION = _classification()
LONG_CLASSIFICATION = _classification(summary=LONG_SUMMARY)
LOW_RISK_CLASSIFICATION = _classification(
    category="operational", severity="low", summary="Low-severity synthetic case.", people_at_risk=False,
)


def _fixtures() -> dict[str, dict[str, Any]]:
    actions = _json(GOOD_ACTIONS)
    return {
        "repair_success": {
            "site": "GTS-01",
            "coverage": "invalid first classifier response, one valid repair, draft and interrupt",
            "responses": ["not-json", _json(NORMAL_CLASSIFICATION), actions],
            "classification": NORMAL_CLASSIFICATION,
            "actions": GOOD_ACTIONS,
        },
        "double_schema_failure": {
            "site": "GTS-01",
            "coverage": "two malformed classifier responses, terminal human-review route",
            "responses": ["not-json", "not-json"],
            "classification": None,
            "actions": None,
        },
        "long_summary": {
            "site": "GTS-01",
            "coverage": "schema-valid 295-character summary flows into draft user request",
            "responses": [_json(LONG_CLASSIFICATION), actions],
            "classification": LONG_CLASSIFICATION,
            "actions": GOOD_ACTIONS,
        },
        "draft_json_fallback": {
            "site": "GTS-01",
            "coverage": "invalid draft JSON selects source fallback action",
            "responses": [_json(NORMAL_CLASSIFICATION), "not-json"],
            "classification": NORMAL_CLASSIFICATION,
            "actions": FALLBACK_ACTIONS,
        },
        "critical_site_bump": {
            "site": "NCL-02",
            "coverage": "low-severity, no-risk classification is bumped at a critical site",
            "responses": [_json(LOW_RISK_CLASSIFICATION), actions],
            "classification": LOW_RISK_CLASSIFICATION,
            "actions": GOOD_ACTIONS,
        },
        "budget_guard": {
            "site": "GTS-01",
            "coverage": "400000 leading spaces count toward source usage and stop before draft",
            "responses": [" " * BUDGET_PREFIX_SPACES + _json(NORMAL_CLASSIFICATION)],
            "classification": NORMAL_CLASSIFICATION,
            "actions": None,
        },
    }


FIXTURES = _fixtures()
EXPECTED_CLAIM = (
    "The six named synthetic path fixtures execute the corresponding pinned source paths under the declared local "
    "complete-outcome schedules; within each pair, equal redacted requests produce equal selected requests, "
    "source tracker rows, node updates, and terminal projections."
)
EXPECTED_NOT_CLAIMED = [
    "universal path coverage, universal source semantics, or a formal proof",
    "real-provider behavior, probability validity, output-cap enforcement, or external calls",
    "actual tokenization, monetary billing, or production budget adequacy",
    "privacy of the raw incident retained in state/checkpoint or returned by human_review",
    "dispatch execution, human approval behavior, or concurrency safety for a shared graph",
    "the six authored path schedules represent real user behavior or incident prevalence",
]
EXPECTED_ACCOUNTING = {
    "source_input_tokens": "max(1, len(system + user) // 4)",
    "source_output_tokens": "max(1, len(response) // 4)",
    "nominal_pricing_usd_per_million": {"input": INPUT_PRICE, "output": OUTPUT_PRICE},
    "call_cost": "round((input_tokens*input_price + output_tokens*output_price)/1000000, 6)",
    "running_total": "round(sum(recorded call costs), 6)",
    "budget_threshold_usd": MAX_BUDGET,
    "budget_predicate": "rounded_total_usd > MAX_COST_PER_INCIDENT_USD",
    "interpretation": "source estimator and configured nominal schedule only; no actual provider billing claim",
}


def _source_snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest_raw = MANIFEST_PATH.read_bytes()
    if _sha(manifest_raw) != EXPECTED_MANIFEST_SHA256:
        raise ProtocolPathsVerificationError("source manifest digest differs from verifier pin")
    manifest = json.loads(manifest_raw.decode("utf-8"), object_pairs_hook=_pairs)
    if manifest.get("commit") != EXPECTED_COMMIT or manifest.get("git_tree") != EXPECTED_TREE \
            or manifest.get("license") != "MIT" or manifest.get("version") != 1:
        raise ProtocolPathsVerificationError("manifest identity differs from verifier pin")
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         text=True, stderr=subprocess.STDOUT).strip()
        tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
                                       text=True, stderr=subprocess.STDOUT).strip()
        status = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            text=True, stderr=subprocess.STDOUT,
        ).strip()
        tracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"],
                                          stderr=subprocess.STDOUT).decode("utf-8").split("\x00")
    except (OSError, subprocess.SubprocessError) as error:
        raise ProtocolPathsVerificationError(f"cannot verify source checkout: {error}") from error
    tracked = sorted(name for name in tracked if name)
    expected_names = sorted(manifest["tracked_file_sha256"])
    if commit != EXPECTED_COMMIT or tree != EXPECTED_TREE or status:
        raise ProtocolPathsVerificationError("source checkout is not the clean pinned commit")
    if tracked != expected_names or len(expected_names) != EXPECTED_FILES:
        raise ProtocolPathsVerificationError("source file set differs from the 23-file manifest")
    hashes = {}
    for relative in expected_names:
        path = (root / relative).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ProtocolPathsVerificationError(f"source path escapes checkout: {relative}") from error
        digest = _sha(path.read_bytes())
        if digest != manifest["tracked_file_sha256"][relative]:
            raise ProtocolPathsVerificationError(f"pinned source bytes differ: {relative}")
        hashes[relative] = digest
    if "MIT License" not in (root / "LICENSE").read_text(encoding="utf-8"):
        raise ProtocolPathsVerificationError("source LICENSE contents are not MIT")
    return {
        "repository": manifest["repository"], "commit": commit, "git_tree": tree,
        "license": manifest["license"], "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "tracked_file_count": len(hashes), "tracked_file_sha256": hashes,
    }


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?:\+44\s?|0)\d{2,4}[\s-]?\d{3}[\s-]?\d{3,4}")
NI_RE = re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b")


def _redact(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return NI_RE.sub("[NI-NUMBER]", text)


def _response_observation(response: str) -> dict[str, Any]:
    digest = _sha(response.encode("utf-8"))
    if len(response) > 4096:
        spaces = len(response) - len(response.lstrip(" "))
        suffix = response[spaces:]
        if response != (" " * spaces) + suffix:
            raise ProtocolPathsVerificationError("expected fixed large response shape changed")
        return {"encoding": "leading_spaces_then_text", "space_count": spaces,
                "suffix": suffix, "character_count": len(response), "utf8_sha256": digest}
    return {"encoding": "text", "text": response,
            "character_count": len(response), "utf8_sha256": digest}


def _expected_priority(classification: dict[str, Any] | None, site: dict[str, Any]) -> dict[str, Any] | None:
    if classification is None:
        return None
    matrix = {
        ("critical", True): ("P1", 15), ("critical", False): ("P1", 15),
        ("high", True): ("P1", 15), ("high", False): ("P2", 60),
        ("medium", True): ("P2", 60), ("medium", False): ("P3", 240),
        ("low", True): ("P3", 240), ("low", False): ("P4", 1440),
    }
    level, sla = matrix[(classification["severity"], classification["people_at_risk"])]
    if site["criticality"] == "critical" and level != "P1":
        level = f"P{int(level[1]) - 1}"
        sla = {"P1": 15, "P2": 60, "P3": 240}[level]
    return {
        "level": level,
        "rationale": (f"severity={classification['severity']}, "
                      f"people_at_risk={classification['people_at_risk']}, "
                      f"site_criticality={site['criticality']}"),
        "response_sla_minutes": sla,
    }


def _expected_path(path_id: str, side: str, sites: dict[str, Any]) -> dict[str, Any]:
    fixture = FIXTURES[path_id]
    site_id = fixture["site"]
    text = INCIDENT_BODY + EMAILS[side] + "."
    redacted = _redact(text)
    classifier_user = USER_PREFIX + redacted
    responses = fixture["responses"]
    classification = fixture["classification"]
    source_site = sites[site_id]
    enrichment = None
    priority = _expected_priority(classification, source_site)
    if classification is not None:
        enrichment = {
            "site_name": source_site["name"],
            "site_criticality": source_site["criticality"],
            "related_procedures": source_site["procedures"].get(classification["category"], []),
            "prior_incidents_at_site": source_site["prior_incidents"],
        }

    requests: list[tuple[str, str, str]] = []
    if path_id in {"repair_success", "double_schema_failure"}:
        requests.append(("classify", CLASSIFY_SYSTEM, classifier_user))
        first_error = _json_parse_error(responses[0])
        repair_user = (
            classifier_user + "\n\nYour previous response failed validation with:\n"
            + first_error + "\nRespond again with ONLY valid JSON for the schema."
        )
        requests.append(("classify", CLASSIFY_SYSTEM, repair_user))
        if path_id == "repair_success":
            draft_user = (f"category: {classification['category']}\npriority: {priority['level']}\n"
                          f"summary: {classification['summary']}")
            requests.append(("draft", ACTIONS_SYSTEM, draft_user))
    else:
        requests.append(("classify", CLASSIFY_SYSTEM, classifier_user))
        if path_id != "budget_guard":
            draft_user = (f"category: {classification['category']}\npriority: {priority['level']}\n"
                          f"summary: {classification['summary']}")
            requests.append(("draft", ACTIONS_SYSTEM, draft_user))

    calls = []
    tracker_rows = []
    total = 0.0
    for ordinal, ((node, system, user), response) in enumerate(zip(requests, responses, strict=True)):
        input_tokens = max(1, len(system + user) // 4)
        output_tokens = max(1, len(response) // 4)
        cost_usd = round((input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE) / 1_000_000, 6)
        row = {"node": node, "input_tokens": input_tokens,
               "output_tokens": output_tokens, "cost_usd": cost_usd}
        total = round(total + cost_usd, 6)
        calls.append({
            "ordinal": ordinal, "node": node, "system": system, "user": user,
            "response": _response_observation(response), "tracker_row": row,
        })
        tracker_rows.append(row)

    state_keys = {"incident"}
    events = []
    if path_id == "double_schema_failure":
        events.append({"kind": "node", "name": "classify", "update_keys": ["error"]})
        state_keys.add("error")
        events.append({"kind": "node", "name": "human_review", "update_keys": sorted(state_keys)})
        terminal = {
            "kind": "human_review",
            "error": f"classification failed schema validation: {_json_parse_error(responses[1])}",
            "classification": None, "enrichment": None, "priority": None,
            "report_status": None, "recommended_actions": None,
        }
        state_costs_present = False
        state_cost_rows = []
    elif path_id == "budget_guard":
        events.append({"kind": "node", "name": "classify", "update_keys": ["classification", "costs"]})
        state_keys.update({"classification", "costs"})
        events.append({"kind": "node", "name": "enrich", "update_keys": ["enrichment"]})
        state_keys.add("enrichment")
        events.append({"kind": "node", "name": "prioritise", "update_keys": ["priority"]})
        state_keys.add("priority")
        events.append({"kind": "node", "name": "draft", "update_keys": ["error"]})
        state_keys.add("error")
        events.append({"kind": "node", "name": "human_review", "update_keys": sorted(state_keys)})
        terminal = {
            "kind": "human_review", "error": f"cost budget exceeded (${total})",
            "classification": classification, "enrichment": enrichment, "priority": priority,
            "report_status": None, "recommended_actions": None,
        }
        state_costs_present = True
        state_cost_rows = tracker_rows
        if total <= MAX_BUDGET:
            raise ProtocolPathsVerificationError("authored budget fixture does not cross source threshold")
    else:
        events.append({"kind": "node", "name": "classify", "update_keys": ["classification", "costs"]})
        state_keys.update({"classification", "costs"})
        events.append({"kind": "node", "name": "enrich", "update_keys": ["enrichment"]})
        state_keys.add("enrichment")
        events.append({"kind": "node", "name": "prioritise", "update_keys": ["priority"]})
        state_keys.add("priority")
        events.append({"kind": "node", "name": "draft", "update_keys": ["costs", "report"]})
        state_keys.add("report")
        events.append({"kind": "interrupt", "before_node": "dispatch"})
        terminal = {
            "kind": "pending_approval", "error": None, "classification": classification,
            "enrichment": enrichment, "priority": priority,
            "report_status": "pending_approval", "recommended_actions": fixture["actions"],
        }
        state_costs_present = True
        state_cost_rows = tracker_rows

    return {
        "case_id": f"{path_id}_{side}",
        "path_id": path_id,
        "pair_side": side,
        "input": {
            "incident_id": f"synthetic-protocol-path-{path_id}",
            "site": site_id,
            "reported_by": REPORTED_BY,
            "text": text,
            "thread_id": f"synthetic-protocol-thread-{path_id}",
        },
        "source_redacted_text": redacted,
        "calls": calls,
        "tracker_rows": tracker_rows,
        "state_costs_present": state_costs_present,
        "state_cost_rows": state_cost_rows,
        "node_events": events,
        "terminal": terminal,
        "network_attempt_count": 0,
        "process_attempt_count": 0,
        "oracle_kind": "fixed locally injected synthetic outcomes; no provider constructed",
    }


def _projection(run: dict[str, Any]) -> dict[str, Any]:
    return {key: run[key] for key in (
        "source_redacted_text", "calls", "tracker_rows", "state_costs_present",
        "state_cost_rows", "node_events", "terminal",
    )}


def _verify_execution(report: dict[str, Any], expected_runs: list[dict[str, Any]]) -> None:
    execution = report["execution"]
    expected_execution = {
        "mode": "direct execution of pinned source graph with fresh graph and MemorySaver per run",
        "instrumentation": (
            "wrapper calls original CostTracker.__init__ and TrackingLLM.complete unchanged, then snapshots tracker "
            "entries; node state costs are recorded separately and may be absent after terminal schema failure"
        ),
        "oracle": {
            "kind": "fixed locally authored deterministic complete-outcome schedule",
            "shared_within_each_pair": True,
            "model_interface": "complete(system,user) only",
            "network_or_provider": "none",
            "profiles": {
                name: {
                    "coverage": fixture["coverage"], "model": MODEL,
                    "response_count": len(fixture["responses"]),
                    "response_sha256": [_sha(response.encode("utf-8")) for response in fixture["responses"]],
                    "response_character_count": [len(response) for response in fixture["responses"]],
                }
                for name, fixture in FIXTURES.items()
            },
        },
        "source_before_after_all_23_files_equal": True,
        "path_count": 6,
        "pair_count": 6,
        "run_count": 12,
        "call_count": sum(len(run["calls"]) for run in expected_runs),
        "tracker_row_count": sum(len(run["tracker_rows"]) for run in expected_runs),
        "state_cost_row_count": sum(len(run["state_cost_rows"]) for run in expected_runs),
        "node_event_count": sum(len(run["node_events"]) for run in expected_runs),
        "interrupt_event_count": sum(
            event["kind"] == "interrupt" for run in expected_runs for event in run["node_events"]
        ),
    }
    if execution != expected_execution:
        raise ProtocolPathsVerificationError("execution counts or oracle provenance differ")


def verify_report(report: Any, upstream_root: Path) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ProtocolPathsVerificationError("report must be an object")
    expected_top_keys = {
        "format", "version", "claim", "not_claimed", "source", "runtime", "execution",
        "accounting", "path_specs", "pairs", "runs",
    }
    if set(report) != expected_top_keys \
            or report.get("format") != "orchlang-incident-triage-protocol-path-study" \
            or report.get("version") != 1:
        raise ProtocolPathsVerificationError("unknown protocol-path report fields or version")
    if report["claim"] != EXPECTED_CLAIM or report["not_claimed"] != EXPECTED_NOT_CLAIMED:
        raise ProtocolPathsVerificationError("claim or limitation list differs from pinned schema")

    source_snapshot = _source_snapshot(upstream_root)
    expected_source = {
        "repository": source_snapshot["repository"], "commit": source_snapshot["commit"],
        "git_tree": source_snapshot["git_tree"], "license": "MIT",
        "manifest_sha256": EXPECTED_MANIFEST_SHA256, "tracked_file_count": EXPECTED_FILES,
        "tracked_file_sha256_before": source_snapshot["tracked_file_sha256"],
        "tracked_file_sha256_after": source_snapshot["tracked_file_sha256"],
    }
    if report["source"] != expected_source:
        raise ProtocolPathsVerificationError("before/after source binding differs from all 23 pinned files")

    runtime = report["runtime"]
    runtime_keys = {
        "python", "langgraph", "pydantic", "provider", "configured_source_default",
        "nominal_model_name_for_tracker", "outbound_provider_calls", "network_attempts", "process_attempts",
    }
    if set(runtime) != runtime_keys or runtime.get("langgraph") != "1.2.14" \
            or runtime.get("pydantic") != "2.14.0" \
            or not isinstance(runtime.get("python"), str) \
            or not re.fullmatch(r"3\.(12|14)\.\d+", runtime["python"]) \
            or runtime.get("provider") != "none; fixed synthetic complete() oracle passed directly to source graph" \
            or runtime.get("configured_source_default") != "mock" \
            or runtime.get("nominal_model_name_for_tracker") != MODEL \
            or (runtime.get("outbound_provider_calls"), runtime.get("network_attempts"),
                runtime.get("process_attempts")) != (0, 0, 0):
        raise ProtocolPathsVerificationError("runtime provenance or offline-only declaration differs")
    if report["accounting"] != EXPECTED_ACCOUNTING:
        raise ProtocolPathsVerificationError("source estimator, nominal pricing, or budget declaration differs")

    sites = json.loads((upstream_root / "data/sites.json").read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    specs = [{"path_id": path_id, "site": fixture["site"], "coverage": fixture["coverage"]}
             for path_id, fixture in FIXTURES.items()]
    if report["path_specs"] != specs:
        raise ProtocolPathsVerificationError("path specification set differs from verifier fixtures")
    expected_runs = [_expected_path(path_id, side, sites)
                     for path_id in FIXTURES for side in ("a", "b")]
    actual_runs = report["runs"]
    if not isinstance(actual_runs, list) or len(actual_runs) != 12:
        raise ProtocolPathsVerificationError("expected exactly 12 paired source executions")
    if actual_runs != expected_runs:
        actual_by_case = {row.get("case_id"): row for row in actual_runs if isinstance(row, dict)}
        for expected in expected_runs:
            if actual_by_case.get(expected["case_id"]) != expected:
                raise ProtocolPathsVerificationError(
                    f"request, outcome, usage, route, or node projection differs: {expected['case_id']}"
                )
        raise ProtocolPathsVerificationError("source run ordering differs")

    expected_pairs = []
    for path_id, fixture in FIXTURES.items():
        left = next(row for row in expected_runs if row["case_id"] == f"{path_id}_a")
        right = next(row for row in expected_runs if row["case_id"] == f"{path_id}_b")
        if left["input"]["text"] == right["input"]["text"]:
            raise ProtocolPathsVerificationError("synthetic pair does not vary the email value")
        if _projection(left) != _projection(right):
            raise ProtocolPathsVerificationError("independently reconstructed pair observations are not equal")
        expected_pairs.append({
            "path_id": path_id, "left": f"{path_id}_a", "right": f"{path_id}_b",
            "expected_relation": "equal under exact-redacted request and fixed outcomes",
            "observed_relation": "equal", "coverage": fixture["coverage"],
            "call_count_per_run": len(left["calls"]),
        })
    if report["pairs"] != expected_pairs:
        raise ProtocolPathsVerificationError("pair table differs from reconstructed observations")
    _verify_execution(report, expected_runs)

    return {
        "format": "orchlang-incident-triage-protocol-path-attestation",
        "version": 1,
        "status": "verified",
        "claim_kind": "independent fixed-fixture reconstruction of selected unchanged-source paths",
        "source_commit": EXPECTED_COMMIT,
        "source_file_count": EXPECTED_FILES,
        "path_count": 6,
        "pair_count": 6,
        "run_count": 12,
        "call_count": sum(len(run["calls"]) for run in expected_runs),
        "tracker_row_count": sum(len(run["tracker_rows"]) for run in expected_runs),
        "pair_relations": ["equal"] * 6,
        "checks": [
            "all 23 source file hashes and clean checkout identity",
            "fixed synthetic outcome schedules and exact full request strings",
            "repair prompt includes the independently derived JSON parse error",
            "source token estimator, configured nominal pricing, row costs, and budget branch",
            "classification summary, critical-site priority, and malformed-draft fallback projections",
            "double schema failure tracker rows despite absent node-state costs",
            "actual LangGraph update and dispatch-interrupt event sequences",
            "six equal-redacted synthetic pairs have equal selected observations",
            "source bytes unchanged from before to after study execution",
        ],
        "limitations": [
            "Only the six named fixed schedules and valid synthetic input skeleton are covered.",
            "The oracle outputs are authored outcomes; no real model/provider executes.",
            "Configured gpt-4o-mini prices exercise source arithmetic only and do not represent incurred cost.",
            "Raw incident values remain in graph state/checkpoint; full-state privacy is not observed.",
            "The budget probe's leading spaces and 400000-character response are artificial.",
            "No universal control-flow completeness, security, billing, or user-adoption claim follows.",
        ],
    }


def verify_report_file(report_path: Path, upstream_root: Path) -> tuple[dict[str, Any], str]:
    raw = report_path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ProtocolPathsVerificationError("path report exceeds the byte cap")
    try:
        report = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        if isinstance(error, ProtocolPathsVerificationError):
            raise
        raise ProtocolPathsVerificationError(f"invalid report JSON: {error}") from error
    attestation = verify_report(report, upstream_root)
    attestation["report_sha256"] = _sha(raw)
    return attestation, _sha(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args(argv)
    try:
        attestation, report_hash = verify_report_file(args.report, args.upstream)
        payload = json.dumps(attestation, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        if args.attestation:
            args.attestation.write_bytes(payload)
        print(json.dumps({
            "status": attestation["status"],
            "report_sha256": report_hash,
            "source_commit": attestation["source_commit"],
            "paths": attestation["path_count"],
            "pairs": attestation["pair_count"],
            "runs": attestation["run_count"],
            "calls": attestation["call_count"],
            "tracker_rows": attestation["tracker_row_count"],
            "checks": len(attestation["checks"]),
        }, indent=2))
        return 0
    except (ProtocolPathsVerificationError, OSError, ValueError, TypeError, KeyError,
            subprocess.SubprocessError, RecursionError) as error:
        print(f"protocol path report rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
