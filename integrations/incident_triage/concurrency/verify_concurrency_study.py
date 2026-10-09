#!/usr/bin/env python3
"""Independently validate the concurrency witness and its cost arithmetic.

This verifier does not import the upstream Python package or the experiment
runner. It checks the pinned checkout, request construction, deterministic
schedule, source tracker-row order, estimator arithmetic, and isolated
per-invocation control from the emitted JSON report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent
MANIFEST = INTEGRATION / "UPSTREAM_MANIFEST.json"
LOCK = INTEGRATION / "requirements.lock"
FORMAT = "orchlang-incident-triage-concurrency-study"
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
NI_RE = re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b")
EXPECTED_INPUTS = {
    "A": {
        "incident_id": "SYNTH-A", "site": "GTS-01",
        "reported_by": "synthetic operator",
        "text": "ALPHA SIGNAL: An intruder forced the rear loading gate.",
        "thread_id": "SYNTH-A",
    },
    "B": {
        "incident_id": "SYNTH-B", "site": "GTS-01",
        "reported_by": "synthetic operator",
        "text": "BRAVO SIGNAL: A minor water leak was found in the storage room.",
        "thread_id": "SYNTH-B",
    },
}


class VerificationError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args],
                                       stderr=subprocess.STDOUT, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"git {' '.join(args)} failed: {error}") from error


def _verify_source(root: Path, reported: dict[str, Any]) -> None:
    manifest = _read_json(MANIFEST)
    root = root.resolve(strict=True)
    _need(root.is_dir(), "upstream path is not a directory")
    _need(_git(root, "rev-parse", "HEAD") == manifest["commit"], "upstream commit mismatch")
    _need(_git(root, "rev-parse", "HEAD^{tree}") == manifest["git_tree"], "upstream tree mismatch")
    _need(not _git(root, "status", "--porcelain", "--untracked-files=all"),
          "upstream worktree is dirty")
    tracked = sorted(item for item in _git(root, "ls-files", "-z").split("\x00") if item)
    expected = sorted(manifest["tracked_file_sha256"])
    _need(tracked == expected, "upstream tracked file set mismatch")
    observed: dict[str, str] = {}
    for relative in expected:
        path = (root / relative).resolve(strict=True)
        _need(path.is_file() and path.is_relative_to(root), f"invalid upstream file {relative}")
        observed[relative] = _sha(path.read_bytes())
    _need(observed == manifest["tracked_file_sha256"], "upstream tracked file hash mismatch")
    _need(manifest["license"] == "MIT" and "MIT License" in (root / "LICENSE").read_text(
        encoding="utf-8"), "upstream license check failed")
    _need(reported.get("commit") == manifest["commit"]
          and reported.get("git_tree") == manifest["git_tree"]
          and reported.get("license") == "MIT"
          and reported.get("tracked_file_sha256") == observed
          and reported.get("tracked_file_count") == len(expected)
          and reported.get("manifest_sha256") == _sha(MANIFEST.read_bytes())
          and reported.get("verified_before_and_after_execution") is True,
          "report source binding does not match verified checkout")


def _redact(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return NI_RE.sub("[NI-NUMBER]", text)


def _estimate(text: str) -> int:
    return max(1, len(text) // 4)


def _expected_node_cost(call: dict[str, Any], node: str) -> dict[str, Any]:
    return {
        "node": node,
        "input_tokens": _estimate(call["system"] + call["user"]),
        "output_tokens": _estimate(call["response"]),
        "cost_usd": 0.0,
    }


def _check_calls(calls: list[dict[str, Any]], task: str,
                 classification: dict[str, Any], priority: dict[str, Any] | None) -> None:
    _need(len(calls) == (2 if priority is not None else 1), f"{task} call count mismatch")
    classify = calls[0]
    _need(classify.get("call_id") == f"{task}.classify"
          and classify.get("task") == task and classify.get("phase") == "classify",
          f"{task} classification call identity mismatch")
    source_text = EXPECTED_INPUTS[task]["text"]
    _need(classify.get("system") == CLASSIFY_SYSTEM
          and classify.get("user") == "INCIDENT REPORT: " + _redact(source_text),
          f"{task} classifier request differs from source template")
    _need(json.loads(classify["response"]) == classification,
          f"{task} classifier response/state mismatch")
    if priority is not None:
        draft = calls[1]
        expected_user = (
            f"category: {classification['category']}\n"
            f"priority: {priority['level']}\n"
            f"summary: {classification['summary']}"
        )
        _need(draft.get("call_id") == f"{task}.draft"
              and draft.get("task") == task and draft.get("phase") == "draft"
              and draft.get("system") == ACTIONS_SYSTEM
              and draft.get("user") == expected_user,
              f"{task} draft request differs from source formatting")


def _expected_shared_events() -> list[dict[str, Any]]:
    raw = [
        ("graph_invocation_started", {"task": "A"}),
        ("request_started", {"call_id": "A.classify"}),
        ("oracle_response_ready", {"call_id": "A.classify"}),
        ("held_before_tracking_return", {"call_id": "A.classify"}),
        ("graph_invocation_started", {"task": "B"}),
        ("request_started", {"call_id": "B.classify"}),
        ("oracle_response_ready", {"call_id": "B.classify"}),
        ("wrapper_return", {"call_id": "B.classify"}),
        ("request_started", {"call_id": "B.draft"}),
        ("oracle_response_ready", {"call_id": "B.draft"}),
        ("wrapper_return", {"call_id": "B.draft"}),
        ("graph_invocation_pending", {"task": "B"}),
        ("incident_B_completed_before_A_release", {}),
        ("released_to_tracking_return", {"call_id": "A.classify"}),
        ("wrapper_return", {"call_id": "A.classify"}),
        ("request_started", {"call_id": "A.draft"}),
        ("oracle_response_ready", {"call_id": "A.draft"}),
        ("wrapper_return", {"call_id": "A.draft"}),
        ("graph_invocation_pending", {"task": "A"}),
    ]
    return [{"sequence": index, "kind": kind, **fields}
            for index, (kind, fields) in enumerate(raw)]


def verify_report(report: Any, upstream: Path) -> dict[str, Any]:
    _need(isinstance(report, dict), "report must be an object")
    _need(report.get("format") == FORMAT and report.get("version") == 1
          and report.get("status") == "completed", "unknown or incomplete report")
    _verify_source(upstream, report.get("source", {}))

    harness = report.get("harness")
    _need(isinstance(harness, dict), "harness metadata missing")
    expected_hashes = {
        "runner_sha256": HERE / "run_concurrency_study.py",
        "verifier_sha256": Path(__file__),
        "test_sha256": HERE / "test_concurrency_study.py",
        "source_harness_sha256": INTEGRATION / "run_study.py",
        "manifest_sha256": MANIFEST,
        "dependency_lock_sha256": LOCK,
    }
    for key, path in expected_hashes.items():
        _need(harness.get(key) == _sha(path.read_bytes()), f"{key} mismatch")
    _need(isinstance(harness.get("python"), str)
          and isinstance(harness.get("langgraph"), str)
          and isinstance(harness.get("pydantic"), str), "runtime versions missing")
    _need(report.get("inputs") == EXPECTED_INPUTS, "synthetic input corpus mismatch")

    scope = report.get("scope")
    _need(isinstance(scope, dict)
          and scope.get("provider") == "pinned deterministic MockLLM only; no provider client or outbound network call"
          and scope.get("pii") == "synthetic non-PII text only"
          and "raw checkpoint/state confidentiality" in scope.get("excluded", []),
          "scope statement missing or changed")
    instrumentation = report.get("instrumentation")
    _need(isinstance(instrumentation, dict)
          and instrumentation.get("upstream_source_patched") is False
          and instrumentation.get("network_or_process_attempts") == [],
          "instrumentation or offline boundary mismatch")

    shared = report.get("shared_graph")
    _need(isinstance(shared, dict), "shared graph witness missing")
    calls_list = shared.get("call_responses")
    _need(isinstance(calls_list, list), "shared call responses missing")
    _need([row.get("call_id") for row in calls_list] == [
        "A.classify", "B.classify", "B.draft", "A.draft"
    ], "shared response records do not match the intended A/B schedule")
    shared_calls = {row["call_id"]: row for row in calls_list}
    runs = shared.get("runs")
    _need(isinstance(runs, dict) and set(runs) == {"A", "B"}, "shared run rows missing")
    a_terminal = runs["A"].get("terminal", {})
    b_terminal = runs["B"].get("terminal", {})
    for task, terminal in (("A", a_terminal), ("B", b_terminal)):
        _need(terminal.get("kind") == "pending_approval"
              and terminal.get("report_status") == "pending_approval"
              and terminal.get("error") is None,
              f"shared {task} did not reach the human pre-dispatch gate")
    a_cls = a_terminal.get("classification")
    b_cls = b_terminal.get("classification")
    a_priority = a_terminal.get("priority")
    b_priority = b_terminal.get("priority")
    _need(isinstance(a_cls, dict) and isinstance(b_cls, dict)
          and isinstance(a_priority, dict) and isinstance(b_priority, dict),
          "shared classification/priority values missing")
    _check_calls([shared_calls["A.classify"], shared_calls["A.draft"]], "A",
                 a_cls, a_priority)
    _check_calls([shared_calls["B.classify"], shared_calls["B.draft"]], "B",
                 b_cls, b_priority)

    event_rows = shared.get("events")
    _need(event_rows == _expected_shared_events(),
          "deterministic event schedule differs or A was not held before tracker return")
    tracker_order = shared.get("source_inferred_tracking_call_order")
    _need(tracker_order == ["B.classify", "B.draft", "A.classify", "A.draft"],
          "source-derived TrackingLLM return/record order mismatch")
    expected_rows_b = [
        _expected_shared_cost(shared_calls["B.classify"], "classify"),
        _expected_shared_cost(shared_calls["B.draft"], "draft"),
    ]
    expected_rows_a = expected_rows_b + [
        _expected_shared_cost(shared_calls["A.classify"], "draft"),
        _expected_shared_cost(shared_calls["A.draft"], "draft"),
    ]
    _need(runs["B"].get("cost_rows") == expected_rows_b,
          "B's same-app cost snapshot differs from source arithmetic")
    _need(runs["A"].get("cost_rows") == expected_rows_a,
          "A's same-app snapshot does not show cross-run rows/misattribution")
    _need(len(runs["A"]["cost_rows"]) == 4 and len(runs["B"]["cost_rows"]) == 2,
          "tracker row contamination count differs")
    _need(runs["A"]["cost_rows"][2]["node"] == "draft",
          "A classifier row was not misattributed to draft")

    def token_sum(rows: list[dict[str, Any]]) -> int:
        return sum(row["input_tokens"] + row["output_tokens"] for row in rows)

    unique_call_tokens = sum(
        token_sum([_expected_shared_cost(
            shared_calls[call_id], "classify" if call_id.endswith("classify") else "draft"
        )])
        for call_id in ("A.classify", "B.classify", "B.draft", "A.draft")
    )
    snapshot_tokens = token_sum(runs["A"]["cost_rows"]) + token_sum(runs["B"]["cost_rows"])
    duplicated_b_tokens = token_sum(runs["A"]["cost_rows"][:2])
    _need(snapshot_tokens == unique_call_tokens + duplicated_b_tokens,
          "per-run snapshots do not duplicate B's usage rows in A")

    isolated = report.get("isolated_per_invocation_graphs")
    _need(isinstance(isolated, dict), "isolated control missing")
    isolated_runs = isolated.get("runs")
    approvals = isolated.get("approvals")
    _need(isinstance(isolated_runs, dict) and set(isolated_runs) == {"A", "B"}
          and isinstance(approvals, dict) and set(approvals) == {"A", "B"},
          "isolated run/approval rows missing")
    for task in ("A", "B"):
        run = isolated_runs[task]
        terminal = run.get("terminal", {})
        _need(terminal.get("kind") == "pending_approval"
              and terminal.get("report_status") == "pending_approval",
              f"isolated {task} did not reach pending approval")
        calls = run.get("calls")
        _need(isinstance(calls, list), f"isolated {task} calls missing")
        cls, priority = terminal.get("classification"), terminal.get("priority")
        _need(isinstance(cls, dict) and isinstance(priority, dict),
              f"isolated {task} terminal fields missing")
        _check_calls(calls, task, cls, priority)
        expected_rows = [
            _expected_shared_cost(calls[0], "classify"),
            _expected_shared_cost(calls[1], "draft"),
        ]
        _need(run.get("cost_rows") == expected_rows,
              f"isolated {task} rows are contaminated or misattributed")
        approval = approvals[task]
        _need(approval == {
            "status": "approved", "call_count_before": 2,
            "call_count_after": 2, "thread_id": f"SYNTH-{task}",
        }, f"isolated {task} checkpoint continuation was not per-ID and call-free")

    return {
        "status": "verified",
        "shared_app": {
            "schedule_events": len(event_rows),
            "source_model_calls": len(calls_list),
            "B_cost_rows": len(runs["B"]["cost_rows"]),
            "A_cost_rows": len(runs["A"]["cost_rows"]),
            "A_classifier_recorded_as": runs["A"]["cost_rows"][2]["node"],
            "unique_call_tokens": unique_call_tokens,
            "sum_of_returned_state_snapshot_tokens": snapshot_tokens,
            "duplicated_B_tokens_in_A_snapshot": duplicated_b_tokens,
        },
        "isolated_apps": {
            "cost_rows_per_incident": {task: len(isolated_runs[task]["cost_rows"])
                                        for task in ("A", "B")},
            "per_id_approvals": {task: approvals[task]["status"] for task in ("A", "B")},
        },
        "claim_scope": "observed source CostTracker contamination and mutable current_node misattribution under one controlled schedule; not a general concurrency proof",
    }


def _expected_shared_cost(call: dict[str, Any], node: str) -> dict[str, Any]:
    return _expected_node_cost(call, node)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path,
                        default=HERE / "results" / "concurrency_study.json")
    parser.add_argument("--upstream", type=Path,
                        default=Path(os.environ.get("INCIDENT_TRIAGE_UPSTREAM",
                                                   "/tmp/agent-incident-triage-research")))
    args = parser.parse_args()
    try:
        result = verify_report(_read_json(args.report), args.upstream)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (VerificationError, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError) as error:
        print(f"concurrency witness rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
