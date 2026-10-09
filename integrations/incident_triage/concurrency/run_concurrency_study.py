#!/usr/bin/env python3
"""Deterministically expose the pinned graph's shared tracker race.

The upstream checkout is imported only after its existing pinned manifest has
been verified. Instrumentation is confined to the complete() wrapper boundary:
the offline source MockLLM still computes every response, while a threading
event pauses incident A after its response is ready but before TrackingLLM can
record it. No upstream source file is patched or rewritten.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import threading
from typing import Any
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent
sys.path.insert(0, str(INTEGRATION))
import run_study as source_study  # noqa: E402

FORMAT = "orchlang-incident-triage-concurrency-study"
VERSION = 1
WAIT_SECONDS = 30
MAX_JSON_BYTES = 16 * 1024 * 1024


class StudyError(RuntimeError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _blocked(api_name: str, attempts: list[str]):
    def call(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(api_name)
        raise StudyError(f"offline study blocked {api_name}")
    return call


def offline_execution_guard():
    """Block outbound sockets and process creation while a graph is running."""
    stack = ExitStack()
    attempts: list[str] = []
    for method in ("connect", "connect_ex", "send", "sendall", "sendto"):
        stack.enter_context(patch.object(
            socket.socket, method,
            side_effect=_blocked(f"socket.socket.{method}", attempts),
        ))
    stack.enter_context(patch(
        "socket.create_connection",
        side_effect=_blocked("socket.create_connection", attempts),
    ))
    stack.enter_context(patch(
        "socket.getaddrinfo",
        side_effect=_blocked("socket.getaddrinfo", attempts),
    ))
    for target in ("subprocess.Popen", "subprocess.run", "os.system", "os.popen"):
        stack.enter_context(patch(target, side_effect=_blocked(target, attempts)))
    return stack, attempts


def _task_and_phase(system: str, user: str) -> tuple[str, str]:
    lowered = user.lower()
    if "alpha signal" in lowered:
        task = "A"
    elif "bravo signal" in lowered:
        task = "B"
    else:
        raise StudyError("could not identify synthetic incident in model request")
    if "classify the incident" in system.lower():
        phase = "classify"
    elif "recommended actions" in system.lower():
        phase = "draft"
    else:
        raise StudyError("unexpected model system prompt in pinned source")
    return task, phase


class ScheduledMock:
    """Wrap the pinned MockLLM and hold exactly A's first response before return."""

    name = "mock"

    def __init__(self, delegate: Any):
        self.delegate = delegate
        self.pause_started = threading.Event()
        self.release_pause = threading.Event()
        self.events: list[dict[str, Any]] = []
        self.calls: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def event(self, kind: str, **fields: Any) -> None:
        with self._lock:
            self.events.append({"sequence": len(self.events), "kind": kind, **fields})

    def complete(self, system: str, user: str) -> str:
        if not isinstance(system, str) or not isinstance(user, str):
            raise StudyError("upstream model request was not text")
        task, phase = _task_and_phase(system, user)
        call_id = f"{task}.{phase}"
        self.event("request_started", call_id=call_id)
        response = self.delegate.complete(system, user)
        if not isinstance(response, str):
            raise StudyError("pinned offline mock returned a non-text response")
        with self._lock:
            if call_id in self.calls:
                raise StudyError(f"duplicate synthetic call id {call_id}")
            self.calls[call_id] = {
                "call_id": call_id,
                "task": task,
                "phase": phase,
                "system": system,
                "user": user,
                "response": response,
            }
            self.events.append({"sequence": len(self.events), "kind": "oracle_response_ready",
                                "call_id": call_id})
        if call_id == "A.classify":
            self.event("held_before_tracking_return", call_id=call_id)
            self.pause_started.set()
            if not self.release_pause.wait(WAIT_SECONDS):
                raise StudyError("timed out waiting to release incident A")
            self.event("released_to_tracking_return", call_id=call_id)
        self.event("wrapper_return", call_id=call_id)
        return response

    def ordered_calls(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(self.calls[key]) for key in ("A.classify", "B.classify",
                                                        "B.draft", "A.draft")]


class RecordingMock:
    """Unsynchronized per-app capture for the isolated mitigation runs."""

    name = "mock"

    def __init__(self, delegate: Any, task: str):
        self.delegate = delegate
        self.task = task
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def complete(self, system: str, user: str) -> str:
        task, phase = _task_and_phase(system, user)
        if task != self.task:
            raise StudyError(f"isolated {self.task} graph received task {task}")
        response = self.delegate.complete(system, user)
        with self._lock:
            self.calls.append({
                "call_id": f"{task}.{phase}",
                "task": task,
                "phase": phase,
                "system": system,
                "user": user,
                "response": response,
            })
        return response


def _synthetic_incidents(models: Any) -> dict[str, Any]:
    texts = {
        "A": "ALPHA SIGNAL: An intruder forced the rear loading gate.",
        "B": "BRAVO SIGNAL: A minor water leak was found in the storage room.",
    }
    return {
        task: models.IncidentReport.model_validate({
            "incident_id": f"SYNTH-{task}",
            "site": "GTS-01",
            "reported_by": "synthetic operator",
            "text": text,
        })
        for task, text in texts.items()
    }


def _invoke(graph_module: Any, app: Any, incident: Any, task: str,
            before_invoke=None, after_invoke=None) -> dict[str, Any]:
    if before_invoke is not None:
        before_invoke(task)
    state = graph_module.triage_incident(app, incident, thread_id=f"SYNTH-{task}")
    if after_invoke is not None:
        after_invoke(task)
    return state


def _run_shared_graph(graph_module: Any, llm_module: Any, models: Any,
                      incidents: dict[str, Any], network_attempts: list[str]) -> dict[str, Any]:
    scheduled = ScheduledMock(llm_module.MockLLM())
    app = graph_module.build_graph(llm=scheduled)

    def started(task: str) -> None:
        scheduled.event("graph_invocation_started", task=task)

    def finished(task: str) -> None:
        scheduled.event("graph_invocation_pending", task=task)

    stack, blocked = offline_execution_guard()
    try:
        with stack:
            with ThreadPoolExecutor(max_workers=2) as pool:
                future_a = pool.submit(_invoke, graph_module, app, incidents["A"], "A",
                                       started, finished)
                try:
                    if not scheduled.pause_started.wait(WAIT_SECONDS):
                        raise StudyError("incident A never reached the scheduled model pause")
                    future_b = pool.submit(_invoke, graph_module, app, incidents["B"], "B",
                                           started, finished)
                    state_b = future_b.result(timeout=WAIT_SECONDS)
                    scheduled.event("incident_B_completed_before_A_release")
                    scheduled.release_pause.set()
                    state_a = future_a.result(timeout=WAIT_SECONDS)
                finally:
                    # Release before the executor waits for workers, including
                    # on a failed assertion or timeout.
                    scheduled.release_pause.set()
    finally:
        scheduled.release_pause.set()
    network_attempts.extend(blocked)
    return {
        "call_responses": scheduled.ordered_calls(),
        "events": list(scheduled.events),
        "runs": {
            "A": {"thread_id": "SYNTH-A", "terminal": _terminal(state_a),
                  "cost_rows": state_a.get("costs", [])},
            "B": {"thread_id": "SYNTH-B", "terminal": _terminal(state_b),
                  "cost_rows": state_b.get("costs", [])},
        },
        "source_inferred_tracking_call_order": [
            "B.classify", "B.draft", "A.classify", "A.draft"
        ],
        "isolation_note": (
            "One build_graph instance owns one mutable tracker and current_node; "
            "the scheduled call order makes B finish both calls before A's "
            "classification wrapper returns to TrackingLLM.complete."
        ),
    }


def _terminal(state: dict[str, Any]) -> dict[str, Any]:
    report = state.get("report") or {}
    return {
        "kind": "human_review" if state.get("error") else "pending_approval",
        "error": state.get("error"),
        "report_status": report.get("status"),
        "classification": report.get("classification") or state.get("classification"),
        "priority": report.get("priority") or state.get("priority"),
        "recommended_actions": report.get("recommended_actions"),
    }


def _run_isolated_apps(graph_module: Any, llm_module: Any, incidents: dict[str, Any],
                      network_attempts: list[str]) -> dict[str, Any]:
    applications: dict[str, Any] = {}
    wrappers: dict[str, RecordingMock] = {}
    pending: dict[str, dict[str, Any]] = {}
    stack, blocked = offline_execution_guard()
    try:
        with stack:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                for task in ("A", "B"):
                    wrapper = RecordingMock(llm_module.MockLLM(), task)
                    app = graph_module.build_graph(llm=wrapper)
                    wrappers[task] = wrapper
                    applications[task] = app
                    futures[task] = pool.submit(
                        graph_module.triage_incident, app, incidents[task], f"SYNTH-{task}"
                    )
                for task in ("A", "B"):
                    state = futures[task].result(timeout=WAIT_SECONDS)
                    pending[task] = {
                        "thread_id": f"SYNTH-{task}",
                        "terminal": _terminal(state),
                        "cost_rows": state.get("costs", []),
                        "calls": list(wrappers[task].calls),
                    }
    finally:
        network_attempts.extend(blocked)

    approvals: dict[str, dict[str, Any]] = {}
    stack, blocked_approval = offline_execution_guard()
    try:
        with stack:
            for task in ("A", "B"):
                call_count_before = len(wrappers[task].calls)
                state = graph_module.approve(applications[task], f"SYNTH-{task}")
                call_count_after = len(wrappers[task].calls)
                approvals[task] = {
                    "status": state["report"]["status"],
                    "call_count_before": call_count_before,
                    "call_count_after": call_count_after,
                    "thread_id": f"SYNTH-{task}",
                }
    finally:
        network_attempts.extend(blocked_approval)
    return {"runs": pending, "approvals": approvals}


def run_study(upstream: Path) -> dict[str, Any]:
    upstream = upstream.resolve(strict=True)
    source_before = source_study.verify_upstream(upstream)
    graph_module, llm_module, models, _costs, config = source_study.load_pinned_source(upstream)
    if config.LLM_PROVIDER != "mock":
        raise StudyError("pinned offline configuration did not select the mock")
    incidents = _synthetic_incidents(models)

    blocked_network_attempts: list[str] = []
    shared = _run_shared_graph(graph_module, llm_module, models, incidents,
                               blocked_network_attempts)
    isolated = _run_isolated_apps(graph_module, llm_module, incidents,
                                  blocked_network_attempts)
    source_after = source_study.verify_upstream(upstream)
    source_fields = ("commit", "git_tree", "license", "tracked_file_count",
                     "tracked_file_sha256", "manifest_sha256")
    if any(source_before[field] != source_after[field] for field in source_fields):
        raise StudyError("upstream checkout changed during graph executions")
    if blocked_network_attempts:
        raise StudyError("network/process operation was attempted: " + repr(blocked_network_attempts))

    manifest_path = INTEGRATION / "UPSTREAM_MANIFEST.json"
    lock_path = INTEGRATION / "requirements.lock"
    harness = {
        "runner_sha256": sha256(Path(__file__).read_bytes()),
        "verifier_sha256": sha256((HERE / "verify_concurrency_study.py").read_bytes()),
        "test_sha256": sha256((HERE / "test_concurrency_study.py").read_bytes()),
        "source_harness_sha256": sha256((INTEGRATION / "run_study.py").read_bytes()),
        "manifest_sha256": sha256(manifest_path.read_bytes()),
        "dependency_lock_sha256": sha256(lock_path.read_bytes()),
        "python": platform.python_version(),
        "langgraph": metadata.version("langgraph"),
        "pydantic": metadata.version("pydantic"),
    }
    report = {
        "format": FORMAT,
        "version": VERSION,
        "status": "completed",
        "source": {**source_before, "verified_before_and_after_execution": True},
        "harness": harness,
        "scope": {
            "source_execution": "unchanged pinned LangGraph files; one graph shared for the race, separate graphs for the isolation control",
            "provider": "pinned deterministic MockLLM only; no provider client or outbound network call",
            "pii": "synthetic non-PII text only",
            "observer": ["captured exact system/user/response strings", "source NodeCost rows",
                         "pending/approved status", "deterministic wrapper event order"],
            "excluded": ["raw checkpoint/state confidentiality", "provider billing", "uncontrolled schedules", "general concurrency verification"],
        },
        "instrumentation": {
            "boundary": "wrapper around complete(system,user); delegates every response to the pinned MockLLM",
            "schedule": "hold A.classify after the mock response is ready but before wrapper return; B completes classify and draft on the same app; then release A",
            "upstream_source_patched": False,
            "network_or_process_attempts": blocked_network_attempts,
        },
        "inputs": {
            task: {"incident_id": incidents[task].incident_id,
                  "site": incidents[task].site,
                  "reported_by": incidents[task].reported_by,
                  "text": incidents[task].text,
                  "thread_id": f"SYNTH-{task}"}
            for task in ("A", "B")
        },
        "shared_graph": shared,
        "isolated_per_invocation_graphs": isolated,
    }
    if len(canonical_bytes(report)) > MAX_JSON_BYTES:
        raise StudyError("study report exceeds bounded JSON size")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path,
                        default=Path(os.environ.get("INCIDENT_TRIAGE_UPSTREAM",
                                                   "/tmp/agent-incident-triage-research")))
    parser.add_argument("--output", type=Path,
                        default=HERE / "results" / "concurrency_study.json")
    args = parser.parse_args()
    try:
        report = run_study(args.upstream)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (StudyError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"incident concurrency study failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
