#!/usr/bin/env python3
"""Freeze or run the separate six-operator completed-state truth-table check.

The only source bytes this runner executes are six explicitly authored
development fixtures already named by the primary completed-state protocol.
No held-out source path is accepted or discovered.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.langgraph.backend import (  # noqa: E402
    OfflineRequestSession,
    OracleOutcome,
    execute_verified,
    prepare_graph,
)
from integrations.langgraph.source_frontend.export import (  # noqa: E402
    _canonical as _export_canonical,
    export_bytes,
)
from integrations.langgraph.source_frontend.extract import parse_contracts  # noqa: E402
from integrations.langgraph.source_frontend.runtime import bind_session  # noqa: E402
from integrations.langgraph.source_frontend.study import (  # noqa: E402
    _graph_store,
    _source_app,
)


HERE = Path(__file__).resolve().parent
EXAMPLES = ROOT / "research/scp_strengthening/source_differential/examples"
PRIMARY = ROOT / "output/scp_strengthening/source_differential"
PROTOCOL_PATH = HERE / "truth_table_protocol.json"
RESULT_PATH = HERE / "truth_table_results.json"
PREFLIGHT_PROTOCOL_PATH = HERE / "truth_table_initial_protocol.json"
PREFLIGHT_RECORD_PATH = HERE / "truth_table_preflight_failure.json"
OPERATIONS = ("eq", "ge", "gt", "le", "lt", "ne")
TOKEN_COUNTS = (1, 2, 3)
SEED = 17
QUESTION = "q"
MAX_CALLS = 4
CHARS_PER_TOKEN = 4
ROUTES = {
    # This is the manually enumerated expected table for comparison with both
    # actual source and graph traces; it does not call the fixture's predicate.
    ("eq", 1): "no",  ("eq", 2): "yes", ("eq", 3): "no",
    ("ge", 1): "no",  ("ge", 2): "yes", ("ge", 3): "yes",
    ("gt", 1): "no",  ("gt", 2): "no",  ("gt", 3): "yes",
    ("le", 1): "yes", ("le", 2): "yes", ("le", 3): "no",
    ("lt", 1): "yes", ("lt", 2): "no",  ("lt", 3): "no",
    ("ne", 1): "yes", ("ne", 2): "no",  ("ne", 3): "yes",
}
TOOL_PATHS = (
    "integrations/langgraph/backend.py",
    "integrations/langgraph/source_frontend/extract.py",
    "integrations/langgraph/source_frontend/export.py",
    "integrations/langgraph/source_frontend/runtime.py",
    "integrations/langgraph/source_frontend/study.py",
    "research/scp_strengthening/source_differential/run.py",
    "research/scp_strengthening/completed_state_review/truth_table_run.py",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")


def _save(path: Path, value: Any) -> None:
    raw = _canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="." + path.name + ".", dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    temporary.replace(path)


def make_protocol() -> dict[str, Any]:
    cases = []
    for operation in OPERATIONS:
        name = f"token_route_{operation}"
        source = EXAMPLES / f"{name}.py"
        contracts = EXAMPLES / f"{name}.contracts.json"
        cases.append({
            "operation": operation,
            "name": name,
            "source": source.relative_to(ROOT).as_posix(),
            "source_sha256": _sha(source.read_bytes()),
            "contracts": contracts.relative_to(ROOT).as_posix(),
            "contracts_sha256": _sha(contracts.read_bytes()),
        })
    matrix = [
        {"operation": operation, "draft_output_tokens": count,
         "expected_route": ROUTES[(operation, count)]}
        for operation in OPERATIONS for count in TOKEN_COUNTS
    ]
    return {
        "format": "orchlang-completed-state-truth-table-protocol",
        "version": 1,
        "study_role": "post-primary-development coverage check; separate supplement",
        "preflight_history": {
            "initial_protocol_sha256": _sha(PREFLIGHT_PROTOCOL_PATH.read_bytes()),
            "initial_failure_record_sha256": _sha(PREFLIGHT_RECORD_PATH.read_bytes()),
            "reason": (
                "initial preflight stopped before compiling/invoking source or executing the backend; "
                "the harness passed compact graph bytes to replay although the exporter certificate "
                "binds its pretty-canonical graph bytes"
            ),
        },
        "source_selection": (
            "the six token_route_* development examples already named in the "
            "primary frozen protocol; no held-out sources are read or selected"
        ),
        "cases": cases,
        "matrix": matrix,
        "oracle": {
            "implementation": "one pure deterministic callable object passed unchanged to both executions",
            "response": "r repeated 4*n UTF-8 characters for every request in the run",
            "reported_output_tokens": "n for every request in the run",
            "chars_per_token": CHARS_PER_TOKEN,
            "seed": SEED,
            "question": QUESTION,
            "max_calls": MAX_CALLS,
            "source_session": "OfflineRequestSession(..., oracle=oracle)",
            "graph_backend": "execute_verified(..., oracle=oracle)",
        },
        "checks": [
            "actual source and backend have identical full ordered request/response/usage traces",
            "normal stop and complete source-field state projection agree",
            "the second event is answer-yes or answer-no exactly as manually listed in matrix",
            "completed source answer is the deterministic oracle response",
            "each operator observes both expected branches over counts 1, 2, 3",
        ],
        "primary_snapshot": {
            "protocol_sha256": _sha((PRIMARY / "protocol.json").read_bytes()),
            "results_sha256": _sha((PRIMARY / "results.json").read_bytes()),
            "expected_totals": {
                "completed_pairs": 96,
                "cutoff_pairs": 8,
                "call_events": 224,
                "all_checks_passed_pairs": 104,
            },
        },
        "tools": [{"path": path, "sha256": _sha((ROOT / path).read_bytes())}
                  for path in TOOL_PATHS],
        "limits_and_nonclaims": [
            "eighteen deterministic runs over existing development fixtures only",
            "not an original-source cohort or held-out evaluation",
            "not validation of a real provider or general Python/LangGraph support",
            "source execution is restricted to the six already admitted authored fixtures",
        ],
    }


def _verify_frozen(protocol: dict[str, Any]) -> None:
    planned = make_protocol()
    frozen_without_time = {key: value for key, value in protocol.items()
                           if key != "frozen_at_utc"}
    if frozen_without_time != planned:
        raise RuntimeError("current inputs/tools differ from the pre-execution frozen protocol")
    if not isinstance(protocol.get("frozen_at_utc"), str):
        raise RuntimeError("protocol is missing its freeze timestamp")
    primary_snapshot = protocol.get("primary_snapshot")
    if not isinstance(primary_snapshot, dict):
        raise RuntimeError("protocol is missing the primary study snapshot")
    for name, path in (("protocol_sha256", PRIMARY / "protocol.json"),
                       ("results_sha256", PRIMARY / "results.json")):
        if _sha(path.read_bytes()) != primary_snapshot.get(name):
            raise RuntimeError(f"primary frozen study changed after supplemental freeze: {name}")


def _source_run(app: Any, contracts: dict[str, Any], store: dict[str, Any],
                oracle: Any) -> dict[str, Any]:
    session = OfflineRequestSession(
        contracts["name"], SEED, contracts["models"], CHARS_PER_TOKEN,
        oracle=oracle, max_calls=MAX_CALLS,
    )
    final_state = None
    failure = None
    try:
        with bind_session(session):
            final_state = app.invoke(store, config={"recursion_limit": 256})
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)[:1000]}
    return {
        "status": "runtime_error" if failure is not None else "stopped",
        "stopped": failure is None,
        "trace": session.trace,
        "final_state": final_state,
        "failure": failure,
    }


def _project_source_state(final_values: Any, mapping: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(final_values, dict):
        return None
    fields = {item["source_key"]: item["graph_name"] for item in mapping["inputs"]}
    fields.update({item["source_key"]: item["graph_register"] for item in mapping["result_slots"]})
    if any(graph_name not in final_values for graph_name in fields.values()):
        return None
    return {source_key: final_values[graph_name] for source_key, graph_name in fields.items()}


def _run_one(operation: str, count: int, protocol: dict[str, Any]) -> dict[str, Any]:
    name = f"token_route_{operation}"
    case = next(item for item in protocol["cases"] if item["name"] == name)
    source_raw = (ROOT / case["source"]).read_bytes()
    contract_raw = (ROOT / case["contracts"]).read_bytes()
    contracts = parse_contracts(contract_raw)
    graph, provenance, graph_report, attestation = export_bytes(source_raw, contract_raw)
    if graph_report.get("status") != "accepted" or attestation is None:
        raise RuntimeError(f"known fixture {name} was not accepted and replay-attested")
    verified = prepare_graph(_export_canonical(graph), _export_canonical(graph_report))
    mapping = provenance["mapping"]
    app = _source_app(source_raw, mapping["compiled_variable"], str(ROOT / case["source"]))
    response = "r" * (CHARS_PER_TOKEN * count)

    def oracle(_request: Any) -> OracleOutcome:
        return OracleOutcome(response=response, output_tokens=count)

    # This expected route is an explicit fixture-independent lookup from the
    # frozen table; neither execution's token helper/predicate computes it.
    expected = ROUTES[(operation, count)]
    store = {"question": QUESTION}
    source = _source_run(app, contracts, store, oracle)
    backend = execute_verified(
        verified,
        _graph_store(mapping, store),
        SEED,
        oracle=oracle,
        max_calls=MAX_CALLS,
        recursion_limit=256,
    ).to_dict()

    source_trace = source["trace"]
    backend_trace = backend.get("trace")
    expected_templates = ["draft", f"answer-{expected}"]
    source_answer = source["final_state"].get("answer") if isinstance(source["final_state"], dict) else None
    state_projection = _project_source_state(backend.get("final_values"), mapping)
    checks = {
        "normal_stop": source["status"] == backend.get("status") == "stopped"
        and source["stopped"] is True and backend.get("stopped") is True,
        "full_trace_equal": _canonical(source_trace) == _canonical(backend_trace),
        "expected_templates_in_source": isinstance(source_trace, list)
        and [event.get("template") for event in source_trace] == expected_templates,
        "expected_templates_in_backend": isinstance(backend_trace, list)
        and [event.get("template") for event in backend_trace] == expected_templates,
        "reported_draft_usage": isinstance(source_trace, list) and bool(source_trace)
        and source_trace[0].get("output_tokens") == count,
        "completed_state_projection": isinstance(source["final_state"], dict)
        and _canonical(source["final_state"]) == _canonical(state_projection),
        "oracle_answer": source_answer == response,
    }
    return {
        "operation": operation,
        "case": name,
        "draft_output_tokens": count,
        "expected_route": expected,
        "expected_answer_template": f"answer-{expected}",
        "oracle_response": response,
        "seed": SEED,
        "inputs": store,
        "checks": checks,
        "source": source,
        "backend": backend,
        "backend_source_state_projection": state_projection,
    }


def run_experiment(protocol: dict[str, Any]) -> dict[str, Any]:
    _verify_frozen(protocol)
    rows = [_run_one(item["operation"], item["draft_output_tokens"], protocol)
            for item in protocol["matrix"]]
    summaries: dict[str, Any] = {}
    for operation in OPERATIONS:
        op_rows = [row for row in rows if row["operation"] == operation]
        branch_counts: dict[str, int] = {}
        wrong_route = 0
        for row in op_rows:
            branch = row["expected_route"]
            branch_counts[branch] = branch_counts.get(branch, 0) + 1
            actual = row["source"].get("trace", [])
            if (not actual or len(actual) < 2
                    or actual[1].get("template") != row["expected_answer_template"]):
                wrong_route += 1
        summaries[operation] = {
            "case_count": len(op_rows),
            "branches": branch_counts,
            "wrong_expected_route_count": wrong_route,
            "source_backend_trace_mismatches": sum(not row["checks"]["full_trace_equal"] for row in op_rows),
            "state_projection_mismatches": sum(not row["checks"]["completed_state_projection"] for row in op_rows),
        }
    failures = [
        {"operation": row["operation"], "draft_output_tokens": row["draft_output_tokens"],
         "failed_checks": [name for name, passed in row["checks"].items() if passed is not True]}
        for row in rows if not all(value is True for value in row["checks"].values())
    ]
    failures.extend(
        {"operation": operation, "failed_checks": ["both_expected_branches_not_observed"]}
        for operation, summary in summaries.items()
        if set(summary["branches"]) != {"yes", "no"}
    )
    return {
        "format": "orchlang-completed-state-truth-table-results",
        "version": 1,
        "protocol_sha256": _sha(PROTOCOL_PATH.read_bytes()),
        "primary_protocol_sha256": protocol["primary_snapshot"]["protocol_sha256"],
        "primary_results_sha256": protocol["primary_snapshot"]["results_sha256"],
        "environment": {
            "python": sys.version,
            "langgraph": importlib.metadata.version("langgraph"),
        },
        "counts": {
            "cases": len(rows),
            "operators": len(summaries),
            "operator_branch_cases": sum(sum(summary["branches"].values())
                                          for summary in summaries.values()),
            "full_traces_recorded": sum(isinstance(row["source"].get("trace"), list)
                                         and isinstance(row["backend"].get("trace"), list)
                                         for row in rows),
            "all_checks_passed": sum(all(value is True for value in row["checks"].values())
                                      for row in rows),
        },
        "operator_summary": summaries,
        "runs": rows,
        "failures": failures,
        "status": "pass" if not failures else "fail",
        "primary_study_unchanged": (
            _sha((PRIMARY / "protocol.json").read_bytes()) == protocol["primary_snapshot"]["protocol_sha256"]
            and _sha((PRIMARY / "results.json").read_bytes()) == protocol["primary_snapshot"]["results_sha256"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true",
                        help="write the separate pre-execution plan; never overwrites it")
    arguments = parser.parse_args()
    if arguments.freeze:
        if PROTOCOL_PATH.exists() or RESULT_PATH.exists():
            raise RuntimeError("supplement already has an artifact; protocol/results cannot be overwritten")
        planned = make_protocol()
        _save(PROTOCOL_PATH, dict(planned, frozen_at_utc=datetime.now(timezone.utc).isoformat()))
        print(f"Frozen separate 18-run truth-table plan: {PROTOCOL_PATH}")
        return 0
    if not PROTOCOL_PATH.exists():
        raise RuntimeError("freeze the separate protocol before source/backend execution")
    if RESULT_PATH.exists():
        raise RuntimeError("supplement results already exist; refusing to overwrite")
    protocol = json.loads(PROTOCOL_PATH.read_bytes())
    result = run_experiment(protocol)
    _save(RESULT_PATH, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "failures": result["failures"],
                      "primary_study_unchanged": result["primary_study_unchanged"]},
                     sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
