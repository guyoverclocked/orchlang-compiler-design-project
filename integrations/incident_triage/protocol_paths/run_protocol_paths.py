#!/usr/bin/env python3
"""Exercise selected paths in the pinned, unchanged incident-triage source.

All model completions come from a fixed, local synthetic outcome schedule.
The source code and configuration are read-only; instrumentation wraps the
original tracker constructor and completion method and delegates to each
original implementation before recording observations.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent
MANIFEST_PATH = INTEGRATION / "UPSTREAM_MANIFEST.json"
DEFAULT_OUTPUT = HERE / "results" / "protocol_paths.json"
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
BUDGET_PREFIX_SPACES = 400_000
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
EMAILS = {"a": "alpha.synthetic@example.invalid", "b": "bravo.synthetic@example.invalid"}
INCIDENT_BODY = "A synthetic security incident occurred at the rear gate. Contact "
REPORTED_BY = "synthetic security operator"
MODEL_NAME = "gpt-4o-mini"


class ProtocolPathsError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _source_snapshot(root: Path) -> dict[str, Any]:
    """Verify the exact clean checkout and hash every manifest-listed file."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ProtocolPathsError("--upstream must name the pinned source checkout")
    manifest_raw = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        text=True, stderr=subprocess.STDOUT,
    ).strip()
    if commit != manifest["commit"] or tree != manifest["git_tree"] or status:
        raise ProtocolPathsError("source checkout identity or clean-worktree check failed")
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"], stderr=subprocess.STDOUT,
    ).decode("utf-8").split("\x00")
    tracked = sorted(name for name in tracked if name)
    expected_names = sorted(manifest["tracked_file_sha256"])
    if tracked != expected_names or len(expected_names) != 23:
        raise ProtocolPathsError("source tracked-file list differs from the 23-file pin")
    observed: dict[str, str] = {}
    for relative in expected_names:
        path = (root / relative).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ProtocolPathsError(f"source path escapes checkout: {relative}") from error
        digest = _sha(path.read_bytes())
        if digest != manifest["tracked_file_sha256"][relative]:
            raise ProtocolPathsError(f"source file digest mismatch: {relative}")
        observed[relative] = digest
    if manifest.get("license") != "MIT" or "MIT License" not in (root / "LICENSE").read_text(encoding="utf-8"):
        raise ProtocolPathsError("source license check failed")
    return {
        "repository": manifest["repository"],
        "commit": commit,
        "git_tree": tree,
        "license": manifest["license"],
        "manifest_sha256": _sha(manifest_raw),
        "tracked_file_count": len(observed),
        "tracked_file_sha256": observed,
    }


def _classification(*, category: str = "physical_security", severity: str = "high",
                     summary: str = "Synthetic fixed classification summary.",
                     people_at_risk: bool = False) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "summary": summary,
        "people_at_risk": people_at_risk,
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


LONG_SUMMARY = "S" * 295
NORMAL_CLASSIFICATION = _classification()
LONG_CLASSIFICATION = _classification(summary=LONG_SUMMARY)
LOW_RISK_CLASSIFICATION = _classification(
    category="operational", severity="low", summary="Low-severity synthetic case.", people_at_risk=False,
)
GOOD_ACTIONS = ["Review the synthetic report and notify the site duty manager"]
BUDGET_CLASSIFICATION_TEXT = _compact_json(NORMAL_CLASSIFICATION)
BUDGET_CLASSIFICATION_RESPONSE = (" " * BUDGET_PREFIX_SPACES) + BUDGET_CLASSIFICATION_TEXT

# Fixed authored schedules; every paired run receives precisely the same
# response sequence for the same sequence of complete request calls.
PATH_FIXTURES: dict[str, dict[str, Any]] = {
    "repair_success": {
        "site": "GTS-01", "model": MODEL_NAME,
        "coverage": "invalid first classifier response, one valid repair, draft and interrupt",
        "responses": ["not-json", _compact_json(NORMAL_CLASSIFICATION), _compact_json(GOOD_ACTIONS)],
        "expected_classification": NORMAL_CLASSIFICATION,
        "expected_actions": GOOD_ACTIONS,
    },
    "double_schema_failure": {
        "site": "GTS-01", "model": MODEL_NAME,
        "coverage": "two malformed classifier responses, terminal human-review route",
        "responses": ["not-json", "not-json"],
        "expected_classification": None,
        "expected_actions": None,
    },
    "long_summary": {
        "site": "GTS-01", "model": MODEL_NAME,
        "coverage": "schema-valid 295-character summary flows into draft user request",
        "responses": [_compact_json(LONG_CLASSIFICATION), _compact_json(GOOD_ACTIONS)],
        "expected_classification": LONG_CLASSIFICATION,
        "expected_actions": GOOD_ACTIONS,
    },
    "draft_json_fallback": {
        "site": "GTS-01", "model": MODEL_NAME,
        "coverage": "invalid draft JSON selects source fallback action",
        "responses": [_compact_json(NORMAL_CLASSIFICATION), "not-json"],
        "expected_classification": NORMAL_CLASSIFICATION,
        "expected_actions": ["Review incident manually; drafting agent returned invalid output"],
    },
    "critical_site_bump": {
        "site": "NCL-02", "model": MODEL_NAME,
        "coverage": "low-severity, no-risk classification is bumped at a critical site",
        "responses": [_compact_json(LOW_RISK_CLASSIFICATION), _compact_json(GOOD_ACTIONS)],
        "expected_classification": LOW_RISK_CLASSIFICATION,
        "expected_actions": GOOD_ACTIONS,
    },
    "budget_guard": {
        "site": "GTS-01", "model": MODEL_NAME,
        "coverage": "400000 leading spaces count toward source usage and stop before draft",
        "responses": [BUDGET_CLASSIFICATION_RESPONSE],
        "expected_classification": NORMAL_CLASSIFICATION,
        "expected_actions": None,
    },
}


def _network_blocker(attempts: list[str], label: str):
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(label)
        raise ProtocolPathsError(f"network API disabled during path study: {label}")
    return blocked


def _process_blocker(attempts: list[str], label: str):
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(label)
        raise ProtocolPathsError(f"process creation disabled during path study: {label}")
    return blocked


def _response_observation(response: str) -> dict[str, Any]:
    digest = _sha(response.encode("utf-8"))
    if len(response) > 4096:
        spaces = len(response) - len(response.lstrip(" "))
        suffix = response[spaces:]
        if response != (" " * spaces) + suffix:
            raise ProtocolPathsError("large fixed response is not a simple leading-space fixture")
        return {
            "encoding": "leading_spaces_then_text",
            "space_count": spaces,
            "suffix": suffix,
            "character_count": len(response),
            "utf8_sha256": digest,
        }
    return {
        "encoding": "text",
        "text": response,
        "character_count": len(response),
        "utf8_sha256": digest,
    }


class FixedOutcomeOracle:
    """Local test double implementing only complete(system, user)."""

    def __init__(self, profile: dict[str, Any]):
        self.name = profile["model"]
        self.responses = list(profile["responses"])
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        index = len(self.calls)
        if index >= len(self.responses):
            raise ProtocolPathsError("source issued more calls than this fixed outcome schedule")
        response = self.responses[index]
        self.calls.append({"system": system, "user": user})
        return response


def _load_pinned_source(root: Path) -> tuple[Any, Any, Any, Any, Any]:
    if any(name == "triage" or name.startswith("triage.") for name in sys.modules):
        raise ProtocolPathsError("triage package was imported before source verification")
    src = str((root / "src").resolve(strict=True))
    sys.path.insert(0, src)
    os.environ["TRIAGE_LLM"] = "mock"
    try:
        graph = importlib.import_module("triage.graph")
        llm = importlib.import_module("triage.llm")
        models = importlib.import_module("triage.models")
        costs = importlib.import_module("triage.costs")
        config = importlib.import_module("triage.config")
    except Exception:
        sys.path.remove(src)
        raise
    if Path(graph.__file__).resolve() != (root / "src/triage/graph.py").resolve():
        raise ProtocolPathsError("imported graph module is not the hash-verified checkout")
    return graph, llm, models, costs, config


def _run_one(root: Path, modules: tuple[Any, ...], path_id: str, side: str) -> dict[str, Any]:
    graph_module, _llm_module, models, costs_module, config = modules
    profile = PATH_FIXTURES[path_id]
    case_id = f"{path_id}_{side}"
    text = INCIDENT_BODY + EMAILS[side] + "."
    incident_id = f"synthetic-protocol-path-{path_id}"
    thread_id = f"synthetic-protocol-thread-{path_id}"
    incident = models.IncidentReport.model_validate({
        "incident_id": incident_id,
        "site": profile["site"],
        "reported_by": REPORTED_BY,
        "text": text,
    })
    if graph_module.redact_pii(incident.text) != graph_module.redact_pii(INCIDENT_BODY + EMAILS["a"] + "."):
        raise ProtocolPathsError("paired synthetic emails did not retain one redacted skeleton")
    if profile["model"] not in config.PRICING:
        raise ProtocolPathsError("fixture model must resolve through existing source pricing")

    oracle = FixedOutcomeOracle(profile)
    calls: list[dict[str, Any]] = []
    trackers: list[Any] = []
    original_tracker_init = costs_module.CostTracker.__init__
    original_complete = costs_module.TrackingLLM.complete

    def observe_tracker_init(self: Any, model: str) -> None:
        original_tracker_init(self, model)
        trackers.append(self)

    def observe_complete(self: Any, system: str, user: str) -> str:
        # Delegate first so original provider call and exact source accounting
        # both execute unchanged. The observer only snapshots their results.
        response = original_complete(self, system, user)
        if not self.tracker.entries:
            raise ProtocolPathsError("source tracker did not record the just-completed call")
        entry = self.tracker.entries[-1].model_dump()
        calls.append({
            "ordinal": len(calls),
            "node": entry["node"],
            "system": system,
            "user": user,
            "response": _response_observation(response),
            "tracker_row": entry,
        })
        return response

    network_attempts: list[str] = []
    process_attempts: list[str] = []
    state: dict[str, Any] = {"incident": incident.model_dump()}
    node_events: list[dict[str, Any]] = []
    stream = None
    with ExitStack() as stack:
        for method in ("connect", "connect_ex", "send", "sendall", "sendto"):
            stack.enter_context(patch.object(
                socket.socket, method,
                side_effect=_network_blocker(network_attempts, f"socket.socket.{method}"),
            ))
        stack.enter_context(patch(
            "socket.create_connection",
            side_effect=_network_blocker(network_attempts, "socket.create_connection"),
        ))
        stack.enter_context(patch(
            "socket.getaddrinfo",
            side_effect=_network_blocker(network_attempts, "socket.getaddrinfo"),
        ))
        for target in ("subprocess.Popen", "subprocess.run", "os.system", "os.popen"):
            stack.enter_context(patch(
                target, side_effect=_process_blocker(process_attempts, target),
            ))
        stack.enter_context(patch.object(costs_module.CostTracker, "__init__", observe_tracker_init))
        stack.enter_context(patch.object(costs_module.TrackingLLM, "complete", observe_complete))
        app = graph_module.build_graph(llm=oracle)
        stream = app.stream(
            {"incident": incident.model_dump()},
            {"configurable": {"thread_id": thread_id}},
            stream_mode="updates",
        )
        try:
            for item in stream:
                if not isinstance(item, dict):
                    raise ProtocolPathsError("LangGraph emitted a non-object update")
                for node, update in item.items():
                    if node == "__interrupt__":
                        node_events.append({"kind": "interrupt", "before_node": "dispatch"})
                    else:
                        if not isinstance(update, dict):
                            raise ProtocolPathsError(f"unexpected node update from {node!r}")
                        state.update(update)
                        node_events.append({"kind": "node", "name": node,
                                            "update_keys": sorted(update)})
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()

    if len(trackers) != 1 or trackers[0].model != MODEL_NAME:
        raise ProtocolPathsError("expected one fresh cost tracker with the configured nominal model")
    if len(oracle.calls) != len(calls) or network_attempts or process_attempts:
        raise ProtocolPathsError("offline call capture or network/process guard failed")
    tracker_rows = [entry.model_dump() for entry in trackers[0].entries]
    if len(tracker_rows) != len(calls):
        raise ProtocolPathsError("completion observer and independent tracker row counts differ")
    if tracker_rows != [call["tracker_row"] for call in calls]:
        raise ProtocolPathsError("completion snapshots differ from final original tracker rows")
    state_costs_present = "costs" in state
    state_cost_rows = state.get("costs", [])
    if path_id != "double_schema_failure" and state_cost_rows != tracker_rows:
        raise ProtocolPathsError("node state costs do not match original tracker rows")
    if path_id == "double_schema_failure" and state_costs_present:
        raise ProtocolPathsError("double schema failure unexpectedly exposed costs in node state")

    report = state.get("report") or {}
    terminal = {
        "kind": "human_review" if state.get("error") else "pending_approval",
        "error": state.get("error"),
        "classification": report.get("classification") or state.get("classification"),
        "enrichment": report.get("enrichment") or state.get("enrichment"),
        "priority": report.get("priority") or state.get("priority"),
        "report_status": report.get("status"),
        "recommended_actions": report.get("recommended_actions"),
    }
    run = {
        "case_id": case_id,
        "path_id": path_id,
        "pair_side": side,
        "input": {
            "incident_id": incident_id,
            "site": profile["site"],
            "reported_by": incident.reported_by,
            "text": incident.text,
            "thread_id": thread_id,
        },
        "source_redacted_text": graph_module.redact_pii(incident.text),
        "calls": calls,
        "tracker_rows": tracker_rows,
        "state_costs_present": state_costs_present,
        "state_cost_rows": state_cost_rows,
        "node_events": node_events,
        "terminal": terminal,
        "network_attempt_count": len(network_attempts),
        "process_attempt_count": len(process_attempts),
        "oracle_kind": "fixed locally injected synthetic outcomes; no provider constructed",
    }
    if len(_canonical(run)) > MAX_OUTPUT_BYTES:
        raise ProtocolPathsError(f"single path run exceeds {MAX_OUTPUT_BYTES} report bytes")
    return run


def _projection(run: dict[str, Any]) -> dict[str, Any]:
    return {key: run[key] for key in (
        "source_redacted_text", "calls", "tracker_rows", "state_costs_present",
        "state_cost_rows", "node_events", "terminal",
    )}


def run_protocol_paths(upstream: Path, output: Path) -> dict[str, Any]:
    upstream = upstream.resolve(strict=True)
    source_before = _source_snapshot(upstream)
    modules = _load_pinned_source(upstream)
    _graph, _llm, _models, _costs, config = modules
    runs = []
    for path_id in PATH_FIXTURES:
        for side in ("a", "b"):
            runs.append(_run_one(upstream, modules, path_id, side))
    source_after = _source_snapshot(upstream)
    if source_before != source_after:
        raise ProtocolPathsError("one or more of the 23 pinned source files changed during execution")

    run_map = {row["case_id"]: row for row in runs}
    pairs = []
    for path_id, profile in PATH_FIXTURES.items():
        left = run_map[f"{path_id}_a"]
        right = run_map[f"{path_id}_b"]
        if left["input"]["text"] == right["input"]["text"]:
            raise ProtocolPathsError(f"{path_id}: synthetic pair did not vary the email value")
        equal = _projection(left) == _projection(right)
        if not equal:
            raise ProtocolPathsError(f"{path_id}: fixed-outcome paired observations differ")
        pairs.append({
            "path_id": path_id,
            "left": left["case_id"],
            "right": right["case_id"],
            "expected_relation": "equal under exact-redacted request and fixed outcomes",
            "observed_relation": "equal" if equal else "different",
            "coverage": profile["coverage"],
            "call_count_per_run": len(left["calls"]),
        })

    report = {
        "format": "orchlang-incident-triage-protocol-path-study",
        "version": 1,
        "claim": (
            "The six named synthetic path fixtures execute the corresponding pinned source paths under the declared local "
            "complete-outcome schedules; within each pair, equal redacted requests produce equal selected requests, "
            "source tracker rows, node updates, and terminal projections."
        ),
        "not_claimed": [
            "universal path coverage, universal source semantics, or a formal proof",
            "real-provider behavior, probability validity, output-cap enforcement, or external calls",
            "actual tokenization, monetary billing, or production budget adequacy",
            "privacy of the raw incident retained in state/checkpoint or returned by human_review",
            "dispatch execution, human approval behavior, or concurrency safety for a shared graph",
            "the six authored path schedules represent real user behavior or incident prevalence",
        ],
        "source": {
            "repository": source_before["repository"],
            "commit": source_before["commit"],
            "git_tree": source_before["git_tree"],
            "license": source_before["license"],
            "manifest_sha256": source_before["manifest_sha256"],
            "tracked_file_count": source_before["tracked_file_count"],
            "tracked_file_sha256_before": source_before["tracked_file_sha256"],
            "tracked_file_sha256_after": source_after["tracked_file_sha256"],
        },
        "runtime": {
            "python": sys.version.split()[0],
            "langgraph": metadata.version("langgraph"),
            "pydantic": metadata.version("pydantic"),
            "provider": "none; fixed synthetic complete() oracle passed directly to source graph",
            "configured_source_default": config.LLM_PROVIDER,
            "nominal_model_name_for_tracker": MODEL_NAME,
            "outbound_provider_calls": 0,
            "network_attempts": 0,
            "process_attempts": 0,
        },
        "execution": {
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
                        "coverage": profile["coverage"],
                        "model": profile["model"],
                        "response_count": len(profile["responses"]),
                        "response_sha256": [_sha(response.encode("utf-8")) for response in profile["responses"]],
                        "response_character_count": [len(response) for response in profile["responses"]],
                    }
                    for name, profile in PATH_FIXTURES.items()
                },
            },
            "source_before_after_all_23_files_equal": True,
            "path_count": len(PATH_FIXTURES),
            "pair_count": len(pairs),
            "run_count": len(runs),
            "call_count": sum(len(row["calls"]) for row in runs),
            "tracker_row_count": sum(len(row["tracker_rows"]) for row in runs),
            "state_cost_row_count": sum(len(row["state_cost_rows"]) for row in runs),
            "node_event_count": sum(len(row["node_events"]) for row in runs),
            "interrupt_event_count": sum(
                event["kind"] == "interrupt" for row in runs for event in row["node_events"]
            ),
        },
        "accounting": {
            "source_input_tokens": "max(1, len(system + user) // 4)",
            "source_output_tokens": "max(1, len(response) // 4)",
            "nominal_pricing_usd_per_million": config.PRICING[MODEL_NAME],
            "call_cost": "round((input_tokens*input_price + output_tokens*output_price)/1000000, 6)",
            "running_total": "round(sum(recorded call costs), 6)",
            "budget_threshold_usd": config.MAX_COST_PER_INCIDENT_USD,
            "budget_predicate": "rounded_total_usd > MAX_COST_PER_INCIDENT_USD",
            "interpretation": "source estimator and configured nominal schedule only; no actual provider billing claim",
        },
        "path_specs": [
            {"path_id": name, **{key: value for key, value in profile.items()
                                  if key in {"site", "coverage"}}}
            for name, profile in PATH_FIXTURES.items()
        ],
        "pairs": pairs,
        "runs": runs,
    }
    encoded = _canonical(report)
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ProtocolPathsError(f"study exceeds {MAX_OUTPUT_BYTES} bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True,
                        help="clean local Git checkout of the pinned commit")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = run_protocol_paths(args.upstream, args.output)
        print(json.dumps({
            "status": "generated",
            "report": str(args.output),
            "source_commit": report["source"]["commit"],
            "paths": report["execution"]["path_count"],
            "paired_runs": report["execution"]["run_count"],
            "calls": report["execution"]["call_count"],
            "tracker_rows": report["execution"]["tracker_row_count"],
            "source_hashes_unchanged": report["execution"]["source_before_after_all_23_files_equal"],
        }, indent=2))
        return 0
    except (ProtocolPathsError, OSError, subprocess.SubprocessError, ValueError, KeyError,
            TypeError, RecursionError) as error:
        print(f"protocol path study failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
