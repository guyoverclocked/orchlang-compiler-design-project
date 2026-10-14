#!/usr/bin/env python3
"""Read-only independent audit for the frozen completed-state study output."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STUDY_DIR = ROOT / "output/scp_strengthening/source_differential"
PROTOCOL_PATH = STUDY_DIR / "protocol.json"
RESULTS_PATH = STUDY_DIR / "results.json"
EXPECTED_CASES = {
    "multi_result_node",
    "mutable_result_chain",
    "token_route_eq",
    "token_route_ge",
    "token_route_gt",
    "token_route_le",
    "token_route_lt",
    "token_route_ne",
}
EXPECTED_TOOLS = {
    "integrations/langgraph/backend.py",
    "integrations/langgraph/source_frontend/extract.py",
    "integrations/langgraph/source_frontend/export.py",
    "integrations/langgraph/source_frontend/runtime.py",
    "integrations/langgraph/source_frontend/study.py",
    "research/scp_strengthening/source_differential/run.py",
}
EXPECTED_CHECKS = {
    "ordered_trace",
    "status",
    "stop",
    "complete_state",
    "expected_outcome",
    "no_runtime_error",
}
TOKEN_ROUTE = {
    "token_route_eq": lambda count: count == 2,
    "token_route_ge": lambda count: count >= 2,
    "token_route_gt": lambda count: count > 2,
    "token_route_le": lambda count: count <= 2,
    "token_route_lt": lambda count: count < 2,
    "token_route_ne": lambda count: count != 2,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _issue(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def evaluate_pair(row: dict[str, Any]) -> dict[str, Any]:
    """Recompute the six frozen checks and status/state invariants from a row."""
    issues: list[dict[str, str]] = []
    source = row.get("source")
    backend = row.get("backend")
    if not isinstance(source, dict) or not isinstance(backend, dict):
        return {"checks": {}, "issues": [_issue("malformed_pair", "source/backend must be objects")],
                "projection": None, "missing_registers": []}

    mapping = row.get("source_state_mapping")
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
    ):
        mapping = {}
        issues.append(_issue("malformed_mapping", "source_state_mapping must map text keys to text graph names"))

    source_state = source.get("final_state")
    final_values = backend.get("final_values")
    projection: dict[str, Any] | None = None
    missing_registers: list[str] = []
    complete_state_equal = False
    if source_state is None:
        projection = None
        complete_state_equal = (
            row.get("backend_source_state_projection") is None
            and final_values is None
        )
        if backend.get("final_values") is not None:
            issues.append(_issue("state_published_without_source_completion", "backend exposed final_values while source final_state is absent"))
    elif isinstance(source_state, dict):
        if not isinstance(final_values, dict):
            issues.append(_issue("missing_final_values", "source completed, but backend final_values is not an object"))
            projection = {}
        else:
            projection = {}
            for source_key in source_state:
                graph_name = mapping.get(source_key)
                if graph_name is None:
                    issues.append(_issue("unmapped_source_field", f"source field {source_key!r} has no graph mapping"))
                    continue
                if graph_name not in final_values:
                    missing_registers.append(graph_name)
                    issues.append(_issue("omitted_mapped_register", f"mapped state slot {graph_name!r} for {source_key!r} is absent"))
                    continue
                projection[source_key] = final_values[graph_name]
            if set(mapping) != set(source_state):
                issues.append(_issue(
                    "source_field_projection_not_total",
                    f"mapping keys {sorted(mapping)} differ from completed source fields {sorted(source_state)}",
                ))
            if len(set(mapping.values())) != len(mapping):
                issues.append(_issue("noninjective_source_mapping", "two source fields map to one graph value slot"))
            complete_state_equal = (
                set(projection) == set(source_state)
                and _canonical(source_state) == _canonical(projection)
                and _canonical(row.get("backend_source_state_projection")) == _canonical(projection)
            )
    else:
        issues.append(_issue("malformed_source_state", "source final_state must be an object or null"))

    source_trace = source.get("trace")
    backend_trace = backend.get("trace")
    checks = {
        "ordered_trace": _canonical(source_trace) == _canonical(backend_trace),
        "status": source.get("status") == backend.get("status"),
        "stop": type(source.get("stopped")) is bool
        and type(backend.get("stopped")) is bool
        and source.get("stopped") is backend.get("stopped"),
        "complete_state": complete_state_equal,
        "expected_outcome": source.get("status") == ("stopped" if row.get("max_calls") == 4 else "truncated"),
        "no_runtime_error": source.get("failure") is None and backend.get("failure") is None,
    }
    for name, passed in checks.items():
        if type(passed) is not bool or not passed:
            issues.append(_issue("differential_check_failed", name))

    cap = row.get("max_calls")
    backend_status = backend.get("status")
    if backend_status == "stopped":
        if backend.get("stopped") is not True or not isinstance(final_values, dict):
            issues.append(_issue("invalid_stop_snapshot", "normal stop requires stopped=true and final_values object"))
        if "truncated_at_calls" in backend:
            issues.append(_issue("stop_has_cutoff_marker", "normal stop must not carry a call-cutoff marker"))
    elif backend_status == "truncated":
        if backend.get("stopped") is not False or final_values is not None:
            issues.append(_issue("cutoff_published_state", "truncation must not publish stopped or final_values"))
        if backend.get("truncated_at_calls") != cap:
            issues.append(_issue("cutoff_marker_mismatch", "truncated_at_calls must equal the configured horizon"))
        if source_state is not None:
            issues.append(_issue("source_state_after_cutoff", "source final_state must be absent on exception cutoff"))
        if not isinstance(source_trace, list) or len(source_trace) != cap:
            issues.append(_issue("cutoff_trace_length", "source trace must contain exactly the allowed number of calls"))
        if not isinstance(backend_trace, list) or len(backend_trace) != cap:
            issues.append(_issue("cutoff_trace_length", "backend trace must contain exactly the allowed number of calls"))
    elif backend_status in {"runtime_error", "resource_limited"}:
        if backend.get("stopped") is not False or final_values is not None:
            issues.append(_issue("failed_run_published_state", "failed execution must not publish completion state"))
        if "truncated_at_calls" in backend:
            issues.append(_issue("failure_has_cutoff_marker", "runtime/resource failure is not ordinary call truncation"))
    else:
        issues.append(_issue("unknown_backend_status", f"unexpected status {backend_status!r}"))

    return {
        "checks": checks,
        "issues": issues,
        "projection": projection,
        "missing_registers": sorted(set(missing_registers)),
    }


def _protocol_issues(protocol: dict[str, Any], result: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    issues: list[dict[str, str]] = []
    integrity: dict[str, Any] = {}
    case_docs = protocol.get("cases")
    if not isinstance(case_docs, list):
        return [_issue("bad_protocol_cases", "protocol cases must be an array")], integrity
    names = [item.get("name") for item in case_docs if isinstance(item, dict)]
    if set(names) != EXPECTED_CASES or len(names) != len(EXPECTED_CASES):
        issues.append(_issue("case_selection_mismatch", "frozen protocol does not name exactly the eight authorized authored fixtures"))
    if protocol.get("selection") != "eight authored cases; multiple returned results, temporary local, overwritten state, all six token comparisons":
        issues.append(_issue("selection_note_mismatch", "selection statement differs from the frozen reviewed protocol"))

    actual_tool_paths = {
        item.get("path") for item in protocol.get("tools", []) if isinstance(item, dict)
    }
    if actual_tool_paths != EXPECTED_TOOLS:
        issues.append(_issue("tool_selection_mismatch", "protocol tool hashes do not cover the expected implementation and harness files"))
    tool_checks = []
    for item in protocol.get("tools", []):
        if not isinstance(item, dict):
            issues.append(_issue("malformed_tool_hash", "tool hash entry is not an object"))
            continue
        relative = item.get("path")
        if relative not in EXPECTED_TOOLS:
            continue
        path = ROOT / relative
        actual = _sha(path.read_bytes())
        match = actual == item.get("sha256")
        tool_checks.append({"path": relative, "matches_frozen_hash": match})
        if not match:
            issues.append(_issue("tool_hash_mismatch", relative))

    source_checks = []
    for item in case_docs:
        if not isinstance(item, dict):
            issues.append(_issue("malformed_case_hash", "case hash entry is not an object"))
            continue
        name = item.get("name")
        if name not in EXPECTED_CASES:
            issues.append(_issue("unexpected_case_name", repr(name)))
            continue
        expected_source = f"research/scp_strengthening/source_differential/examples/{name}.py"
        expected_contract = f"research/scp_strengthening/source_differential/examples/{name}.contracts.json"
        if item.get("source") != expected_source or item.get("contracts") != expected_contract:
            issues.append(_issue("case_path_outside_authored_fixtures", repr(name)))
            continue
        source_hash = _sha((ROOT / expected_source).read_bytes())
        contract_hash = _sha((ROOT / expected_contract).read_bytes())
        source_match = source_hash == item.get("source_sha256")
        contract_match = contract_hash == item.get("contracts_sha256")
        source_checks.append({"name": name, "source_matches_frozen_hash": source_match,
                              "contracts_match_frozen_hash": contract_match})
        if not source_match:
            issues.append(_issue("source_hash_mismatch", name))
        if not contract_match:
            issues.append(_issue("contracts_hash_mismatch", name))

    protocol_bytes = PROTOCOL_PATH.read_bytes()
    protocol_hash_matches = _sha(protocol_bytes) == result.get("protocol_sha256")
    if not protocol_hash_matches:
        issues.append(_issue("result_protocol_hash_mismatch", "results do not bind to the frozen protocol bytes"))
    frozen_at = datetime.fromisoformat(protocol["frozen_at_utc"].replace("Z", "+00:00"))
    results_mtime = datetime.fromtimestamp(RESULTS_PATH.stat().st_mtime, timezone.utc)
    execution_after_freeze = results_mtime >= frozen_at
    if not execution_after_freeze:
        issues.append(_issue("results_predate_protocol", "result file mtime precedes frozen protocol timestamp"))
    integrity.update({
        "protocol_sha256": _sha(protocol_bytes),
        "results_protocol_hash_matches": protocol_hash_matches,
        "protocol_frozen_at_utc": frozen_at.isoformat(),
        "results_file_mtime_utc": results_mtime.isoformat(),
        "results_mtime_after_freeze": execution_after_freeze,
        "tool_hashes": tool_checks,
        "source_contract_hashes": source_checks,
    })
    return issues, integrity


def audit_document(protocol: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    issues, integrity = _protocol_issues(protocol, result)
    if result.get("format") != "orchlang-completed-state-differential" or result.get("version") != 1:
        issues.append(_issue("result_schema_mismatch", "unexpected result format/version"))
    if result.get("failures") != []:
        issues.append(_issue("study_reported_failures", f"study result reports {len(result.get('failures', []))} failure(s)"))

    rows = result.get("runs")
    if not isinstance(rows, list):
        rows = []
        issues.append(_issue("missing_runs", "result runs must be an array"))
    computed_rows = []
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(_issue("malformed_run", f"runs[{index}] is not an object"))
            continue
        evaluated = evaluate_pair(row)
        checks = evaluated["checks"]
        if set(row.get("checks", {})) != EXPECTED_CHECKS:
            issues.append(_issue("check_set_mismatch", f"runs[{index}] does not store all six protocol checks"))
        for name, passed in checks.items():
            if row.get("checks", {}).get(name) is not passed:
                issues.append(_issue("stored_check_disagrees", f"runs[{index}] {name}"))
        for issue in evaluated["issues"]:
            issues.append(_issue(issue["code"], f"runs[{index}] {issue['detail']}"))
        computed_rows.append({"index": index, "case": row.get("case"),
                              "checks": checks, "issues": evaluated["issues"]})
        by_case[str(row.get("case"))].append(row)

    case_summary = []
    for name in sorted(EXPECTED_CASES):
        case_rows = by_case.get(name, [])
        completed = [row for row in case_rows if row.get("max_calls") == 4]
        cutoffs = [row for row in case_rows if row.get("max_calls") == 1]
        if len(completed) != 12 or len(cutoffs) != 1 or len(case_rows) != 13:
            issues.append(_issue("case_run_count_mismatch", f"{name}: expected 12 complete + 1 cutoff, got {len(completed)} + {len(cutoffs)}"))
        completed_fields = []
        hidden_registers: set[str] = set()
        for row in completed:
            fields = row.get("source_state_mapping", {})
            state = row.get("source", {}).get("final_state")
            values = row.get("backend", {}).get("final_values")
            if isinstance(state, dict):
                completed_fields.append(sorted(state))
            if isinstance(fields, dict) and isinstance(values, dict):
                hidden_registers.update(set(values) - set(fields.values()))
        field_sets = {tuple(field_set) for field_set in completed_fields}
        if len(field_sets) != 1 or (field_sets and set(next(iter(field_sets))) != set(completed[0].get("source_state_mapping", {}))):
            issues.append(_issue("case_state_fields_not_stable", name))
        case_summary.append({
            "name": name,
            "completed_pairs": len(completed),
            "cutoff_pairs": len(cutoffs),
            "completed_source_fields": list(next(iter(field_sets))) if len(field_sets) == 1 else [],
            "backend_only_registers": sorted(hidden_registers),
            "error_pairs": sum(
                row.get("source", {}).get("failure") is not None
                or row.get("backend", {}).get("failure") is not None
                for row in case_rows
            ),
        })

    computed_totals = {
        "completed_pairs": sum(row.get("max_calls") == 4 for row in rows),
        "cutoff_pairs": sum(row.get("max_calls") == 1 for row in rows),
        "call_events": sum(len(row.get("source", {}).get("trace", [])) for row in rows),
        "all_checks_passed_pairs": sum(
            all(value is True for value in row.get("checks", {}).values()) for row in rows
        ),
    }
    if result.get("totals") != computed_totals:
        issues.append(_issue("totals_mismatch", f"stored={result.get('totals')!r}; recomputed={computed_totals!r}"))
    if len(rows) != 104 or computed_totals != {
        "completed_pairs": 96, "cutoff_pairs": 8, "call_events": 224,
        "all_checks_passed_pairs": 104,
    }:
        issues.append(_issue("study_scope_count_mismatch", f"got {len(rows)} rows and {computed_totals!r}"))

    route_summary: dict[str, Any] = {}
    for name, predicate in TOKEN_ROUTE.items():
        branch_counts: Counter[str] = Counter()
        incorrect = 0
        for row in by_case.get(name, []):
            if row.get("max_calls") != 4:
                continue
            events = row.get("source", {}).get("trace", [])
            if not events:
                incorrect += 1
                continue
            answer = next((event for event in events if event.get("template", "").startswith("answer-")), None)
            if answer is None:
                incorrect += 1
                continue
            label = "yes" if answer["template"].endswith("yes") else "no"
            branch_counts[label] += 1
            if (label == "yes") != predicate(events[0]["output_tokens"]):
                incorrect += 1
        route_summary[name] = {"branch_counts": dict(branch_counts),
                               "wrong_operator_outcomes": incorrect,
                               "both_branches_observed": set(branch_counts) == {"yes", "no"}}

    return {
        "format": "orchlang-completed-state-review",
        "version": 1,
        "status": "pass" if not issues else "fail",
        "protocol_integrity": integrity,
        "totals": computed_totals,
        "case_summary": case_summary,
        "token_route_coverage": route_summary,
        "recomputed_rows": computed_rows,
        "observed_error_pairs": sum(item["error_pairs"] for item in case_summary),
        "issues": issues,
        "limits": [
            "only the eight frozen authored source examples and their contract files are read",
            "the row mapping is the frozen harness projection being audited; no arbitrary source is executed",
            "results are offline authored-fixture differentials, not provider validation or general LangGraph refinement",
            "the source harness records no final state after a call-cap exception; partial source checkpoint state is not compared",
        ],
    }


def audit_saved_study() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    protocol = json.loads(PROTOCOL_PATH.read_bytes())
    result = json.loads(RESULTS_PATH.read_bytes())
    return audit_document(protocol, result), protocol, result


def mutation_checks(protocol: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Alter only in-memory copies and confirm independent state checks fail."""
    sample = next(
        row for row in result["runs"]
        if row["case"] == "multi_result_node" and row["max_calls"] == 4
    )
    answer_register = sample["source_state_mapping"]["answer"]
    draft_register = sample["source_state_mapping"]["draft"]
    checks = []

    corrupt_value = deepcopy(result)
    corrupt_row = next(
        row for row in corrupt_value["runs"]
        if row["case"] == "multi_result_node" and row["max_calls"] == 4
    )
    corrupt_row["backend"]["final_values"][answer_register] = "INJECTED_CORRUPTION"
    report = audit_document(protocol, corrupt_value)
    checks.append({"mutation": "change a returned answer register",
                   "caught": report["status"] == "fail"
                   and any(issue["code"] == "differential_check_failed"
                           and "complete_state" in issue["detail"] for issue in report["issues"]),
                   "review_status": report["status"]})

    omitted_slot = deepcopy(result)
    omitted_row = next(
        row for row in omitted_slot["runs"]
        if row["case"] == "multi_result_node" and row["max_calls"] == 4
    )
    del omitted_row["backend"]["final_values"][draft_register]
    report = audit_document(protocol, omitted_slot)
    checks.append({"mutation": "remove a mapped draft result register",
                   "caught": report["status"] == "fail"
                   and any(issue["code"] == "omitted_mapped_register"
                           and draft_register in issue["detail"] for issue in report["issues"]),
                   "review_status": report["status"]})

    omitted_source_key = deepcopy(result)
    omitted_row = next(
        row for row in omitted_source_key["runs"]
        if row["case"] == "multi_result_node" and row["max_calls"] == 4
    )
    del omitted_row["source_state_mapping"]["answer"]
    report = audit_document(protocol, omitted_source_key)
    checks.append({"mutation": "remove the answer source-field mapping",
                   "caught": report["status"] == "fail"
                   and any(issue["code"] == "unmapped_source_field"
                           and "answer" in issue["detail"] for issue in report["issues"]),
                   "review_status": report["status"]})

    cutoff_state = deepcopy(result)
    cutoff_row = next(
        row for row in cutoff_state["runs"]
        if row["case"] == "multi_result_node" and row["max_calls"] == 1
    )
    cutoff_row["backend"]["final_values"] = {"lg_slot_0000": "PARTIAL_REGISTER"}
    report = audit_document(protocol, cutoff_state)
    checks.append({"mutation": "publish partial registers on the cutoff pair",
                   "caught": report["status"] == "fail"
                   and any(issue["code"] == "cutoff_published_state" for issue in report["issues"]),
                   "review_status": report["status"]})
    return checks


def run_review() -> dict[str, Any]:
    baseline, protocol, result = audit_saved_study()
    mutations = mutation_checks(protocol, result)
    if not all(item["caught"] for item in mutations):
        baseline["issues"].append(_issue("corruption_injection_missed", repr(mutations)))
        baseline["status"] = "fail"
    baseline["corruption_injection"] = mutations
    baseline["status"] = "pass" if not baseline["issues"] else "fail"
    return baseline


if __name__ == "__main__":
    print(json.dumps(run_review(), ensure_ascii=False, sort_keys=True, indent=2))
