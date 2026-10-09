#!/usr/bin/env python3
"""Execute pinned, unmodified incident-triage source under its offline mock.

This is a source execution harness, not a translator. It verifies the upstream
Git checkout and tracked-file hashes before importing the source. The only
injection is an instrumented wrapper around the repository's own MockLLM (or
an explicit one-shot malformed response for the retry experiment).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
from contextlib import ExitStack
from unittest.mock import patch
from typing import Any


HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "UPSTREAM_MANIFEST.json"
MAX_SOURCE_OUTPUT_BYTES = 16 * 1024 * 1024


class StudyError(RuntimeError):
    pass


def _network_blocker(attempts: list[str], api_name: str):
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(api_name)
        raise StudyError(f"network access disabled: {api_name}")
    return blocked


def _process_blocker(attempts: list[str], api_name: str):
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        attempts.append(api_name)
        raise StudyError(f"process creation disabled: {api_name}")
    return blocked


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def git_output(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        output = getattr(error, "output", "")
        raise StudyError(f"git {' '.join(args)} failed: {output or error}") from error


def verify_upstream(root: Path) -> dict[str, Any]:
    """Require the exact clean public checkout captured in the source manifest."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise StudyError("--upstream must name a checkout directory")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    commit = git_output(root, "rev-parse", "HEAD")
    tree = git_output(root, "rev-parse", "HEAD^{tree}")
    if commit != manifest["commit"] or tree != manifest["git_tree"]:
        raise StudyError(f"upstream revision mismatch: {commit} {tree}")
    if git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise StudyError("upstream checkout must be clean before source execution")

    tracked = git_output(root, "ls-files", "-z").split("\x00")
    tracked = sorted(path for path in tracked if path)
    expected = sorted(manifest["tracked_file_sha256"])
    if tracked != expected:
        raise StudyError("upstream tracked-file set differs from pinned manifest")
    for relative in expected:
        path = (root / relative).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise StudyError(f"upstream path escapes checkout: {relative}") from error
        if not path.is_file():
            raise StudyError(f"upstream tracked path is not a regular file: {relative}")
        observed = sha256_bytes(path.read_bytes())
        if observed != manifest["tracked_file_sha256"][relative]:
            raise StudyError(f"upstream source hash mismatch: {relative}")
    if manifest["license"] != "MIT" or "MIT License" not in (root / "LICENSE").read_text(
        encoding="utf-8"
    ):
        raise StudyError("pinned license check failed")
    return {
        "repository": manifest["repository"],
        "commit": commit,
        "git_tree": tree,
        "license": manifest["license"],
        "tracked_file_count": len(expected),
        "tracked_file_sha256": manifest["tracked_file_sha256"],
        "manifest_sha256": sha256_bytes(MANIFEST_PATH.read_bytes()),
    }


def load_pinned_source(root: Path):
    """Import only after hash validation; refuse an already loaded other copy."""
    if any(name == "triage" or name.startswith("triage.") for name in sys.modules):
        raise StudyError("triage package was imported before pinned source validation")
    src = str((root / "src").resolve(strict=True))
    sys.path.insert(0, src)
    os.environ["TRIAGE_LLM"] = "mock"
    try:
        graph = importlib.import_module("triage.graph")
        llm_module = importlib.import_module("triage.llm")
        models = importlib.import_module("triage.models")
        costs = importlib.import_module("triage.costs")
        config = importlib.import_module("triage.config")
    except Exception:
        sys.path.remove(src)
        raise
    if Path(graph.__file__).resolve() != (root / "src/triage/graph.py").resolve():
        raise StudyError("imported graph module is not the verified checkout")
    if Path(llm_module.__file__).resolve() != (root / "src/triage/llm.py").resolve():
        raise StudyError("imported mock provider is not the verified checkout")
    return graph, llm_module, models, costs, config


class RecordingMock:
    """Instrument the pinned deterministic MockLLM without changing its code."""

    name = "mock"

    def __init__(self, delegate: Any, *, fail_first_classification: bool = False):
        self.delegate = delegate
        self.fail_first_classification = fail_first_classification
        self.failed_once = False
        self.calls: list[dict[str, Any]] = []

    def complete(self, system: str, user: str) -> str:
        if not isinstance(system, str) or not isinstance(user, str):
            raise StudyError("upstream model request was not text")
        if self.fail_first_classification and "classify the incident" in system.lower() \
                and not self.failed_once:
            self.failed_once = True
            response = "intentional deterministic schema-failure probe"
        else:
            response = self.delegate.complete(system, user)
        if not isinstance(response, str):
            raise StudyError("offline mock returned a non-text response")
        row = {"system": system, "user": user, "response": response}
        if len(canonical_bytes(row)) > MAX_SOURCE_OUTPUT_BYTES:
            raise StudyError("single instrumented call exceeds output bound")
        self.calls.append(row)
        return response


def _incident(IncidentReport: type, text: str, *, incident_id: str,
              site: str = "GTS-01") -> Any:
    return IncidentReport.model_validate({
        "incident_id": incident_id,
        "site": site,
        "reported_by": "synthetic operator",
        "text": text,
    })


BASE_PII_TEXT = (
    "At the rear gate, an intruder forced the loading bay open. "
    "Contact {email}; callback {phone}; National Insurance {ni}."
)
PII_VALUES = {
    "email_short": "person@example.invalid",
    "email_long": "a.very.long.synthetic.name@department.example.invalid",
    "phone_short": "07700 900123",
    "phone_long": "0113 496 0999",
    "ni_short": "QQ 12 34 56 C",
    "ni_long": "ZZ987654Z",
}


def _text_variant(*, email: str | None = None, phone: str | None = None,
                  ni: str | None = None, body: str | None = None) -> str:
    return (body or BASE_PII_TEXT).format(
        email=email or PII_VALUES["email_short"],
        phone=phone or PII_VALUES["phone_short"],
        ni=ni or PII_VALUES["ni_short"],
    )


def _run_one(root: Path, modules: tuple[Any, ...], case_id: str, text: str,
             *, site: str = "GTS-01", incident_id: str | None = None,
             thread_id: str | None = None,
             fail_first_classification: bool = False,
             use_default_mock: bool = False) -> dict[str, Any]:
    graph_module, llm_module, models, costs_module, config = modules
    if use_default_mock and config.LLM_PROVIDER != "mock":
        raise StudyError("upstream default provider is not pinned to mock")
    if use_default_mock and fail_first_classification:
        raise StudyError("default-mock probe cannot inject a retry failure")
    llm = None if use_default_mock else RecordingMock(
        llm_module.MockLLM(), fail_first_classification=fail_first_classification
    )
    calls: list[dict[str, Any]] = [] if use_default_mock else llm.calls
    original_mock_complete = llm_module.MockLLM.complete

    def observe_default_mock(self: Any, system: str, user: str) -> str:
        response = original_mock_complete(self, system, user)
        if not all(isinstance(value, str) for value in (system, user, response)):
            raise StudyError("upstream default mock produced a non-text call")
        calls.append({"system": system, "user": user, "response": response})
        return response

    source_incident_id = incident_id or case_id
    incident = _incident(models.IncidentReport, text, incident_id=source_incident_id, site=site)
    redacted = graph_module.redact_pii(incident.text)
    state: dict[str, Any] = {"incident": incident.model_dump()}
    node_events: list[dict[str, Any]] = []
    network_attempts: list[str] = []
    process_attempts: list[str] = []
    effective_thread_id = thread_id or f"source-study-{case_id}"
    try:
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
            if use_default_mock:
                stack.enter_context(patch.object(llm_module.MockLLM, "complete", observe_default_mock))
            app = graph_module.build_graph() if use_default_mock else graph_module.build_graph(llm=llm)
            stream = app.stream(
                {"incident": incident.model_dump()},
                {"configurable": {"thread_id": effective_thread_id}},
                stream_mode="updates",
            )
            for item in stream:
                if not isinstance(item, dict):
                    raise StudyError("LangGraph emitted a non-object update event")
                for node, update in item.items():
                    if node == "__interrupt__":
                        node_events.append({"kind": "interrupt", "before_node": "dispatch"})
                        continue
                    if not isinstance(update, dict):
                        raise StudyError(f"unexpected state update from node {node!r}")
                    state.update(update)
                    node_events.append({"kind": "node", "name": node,
                                        "update_keys": sorted(update)})
    finally:
        close = getattr(locals().get("stream"), "close", None)
        if close is not None:
            close()

    if len(calls) != len(state.get("costs", [])):
        raise StudyError(f"model call / source cost row count mismatch in {case_id}")
    if network_attempts:
        raise StudyError(f"network API attempted in {case_id}: {network_attempts}")
    if process_attempts:
        raise StudyError(f"process creation attempted in {case_id}: {process_attempts}")
    usage: list[dict[str, Any]] = []
    for index, (call, cost) in enumerate(zip(calls, state.get("costs", []), strict=True)):
        estimate_input = max(1, len(call["system"] + call["user"]) // 4)
        estimate_output = max(1, len(call["response"]) // 4)
        if cost["input_tokens"] != estimate_input or cost["output_tokens"] != estimate_output:
            raise StudyError(f"upstream token estimate mismatch at {case_id} call {index}")
        usage.append({
            "index": index,
            "node": cost["node"],
            "input_tokens": cost["input_tokens"],
            "output_tokens": cost["output_tokens"],
            "cost_usd": cost["cost_usd"],
        })

    report = state.get("report")
    result = {
        "case_id": case_id,
        "input": {"incident_id": source_incident_id, "site": site,
                  "reported_by": incident.reported_by, "text": incident.text,
                  "thread_id": effective_thread_id},
        "execution_mode": "upstream_default_mock" if use_default_mock else "injected_mock_wrapper",
        "network_attempt_count": len(network_attempts),
        "process_attempt_count": len(process_attempts),
        "cost_tracker": {
            "model_name": llm_module.MockLLM.name,
            "entry_count": len(usage),
            "total_cost_usd": round(sum(row["cost_usd"] for row in usage), 6),
        },
        "source_redacted_text": redacted,
        "node_events": node_events,
        "calls": calls,
        "usage": usage,
        "terminal": {
            "kind": "human_review" if state.get("error") else "pending_approval",
            "error": state.get("error"),
            "classification": (report or {}).get("classification") or state.get("classification"),
            "priority": (report or {}).get("priority") or state.get("priority"),
            "report_status": (report or {}).get("status"),
            "recommended_actions": (report or {}).get("recommended_actions"),
        },
    }
    if len(canonical_bytes(result)) > MAX_SOURCE_OUTPUT_BYTES:
        raise StudyError("case exceeds bounded JSON output size")
    return result


def trace_projection(case: dict[str, Any]) -> dict[str, Any]:
    """Observation compared in pairs: exact calls, upstream usage, and route."""
    return {
        "calls": case["calls"],
        "usage": case["usage"],
        "node_events": case["node_events"],
        "terminal": case["terminal"],
    }


def _pair(cases: dict[str, dict[str, Any]], left: str, right: str,
          *, expected: str, dimension: str) -> dict[str, Any]:
    same = trace_projection(cases[left]) == trace_projection(cases[right])
    if (expected == "equal") != same:
        raise StudyError(f"unexpected observed trace relation for {left} / {right}")
    return {"left": left, "right": right, "expected_relation": expected,
            "observed_relation": "equal" if same else "different",
            "dimension": dimension,
            "call_count": len(cases[left]["calls"])}


def run_study(upstream: Path) -> dict[str, Any]:
    upstream = upstream.resolve(strict=True)
    source = verify_upstream(upstream)
    modules = load_pinned_source(upstream)
    graph_module, llm_module, models, costs_module, config = modules

    cases: dict[str, dict[str, Any]] = {}
    pair_specs: list[dict[str, str]] = []

    # Three orthogonal source-listed PII changes; each pair holds every other
    # input field and all non-PII text fixed.
    pii_pairs = {
        "email": ("email_short", "email_long"),
        "phone": ("phone_short", "phone_long"),
        "national_insurance": ("ni_short", "ni_long"),
    }
    for kind, (short_key, long_key) in pii_pairs.items():
        for suffix, key in (("a", short_key), ("b", long_key)):
            values = dict(PII_VALUES)
            values[short_key] = PII_VALUES[key]
            values[long_key] = PII_VALUES[key]
            text = BASE_PII_TEXT.format(
                email=values["email_short"],
                phone=values["phone_short"],
                ni=values["ni_short"],
            )
            case_id = f"pii_{kind}_{suffix}"
            cases[case_id] = _run_one(
                upstream, modules, case_id, text,
                incident_id=f"paired-pii-{kind}",
                thread_id=f"source-study-paired-pii-{kind}",
            )
        left = f"pii_{kind}_a"
        right = f"pii_{kind}_b"
        if cases[left]["input"]["text"] == cases[right]["input"]["text"]:
            raise StudyError(f"PII pair {kind} did not vary its chosen value")
        if cases[left]["source_redacted_text"] != cases[right]["source_redacted_text"]:
            raise StudyError(f"source redactor did not normalize PII pair {kind}")
        pair_specs.append({"left": left, "right": right, "expected": "equal",
                           "dimension": f"{kind} value substitution with fixed redacted skeleton"})

    # Presence, multiplicity, and type are separate from value substitution.
    # The words around the fixed contact slot are unchanged within each pair.
    shape_cases = {
        "pii_presence_absent": "At the rear gate, callback field: .",
        "pii_presence_present": (
            "At the rear gate, callback field: " + PII_VALUES["email_short"] + "."
        ),
        "pii_count_one": (
            "At the rear gate, contacts: " + PII_VALUES["email_short"] + " ."
        ),
        "pii_count_two": (
            "At the rear gate, contacts: " + PII_VALUES["email_short"] + " "
            + PII_VALUES["email_long"] + "."
        ),
        "pii_type_email": (
            "At the rear gate, callback: " + PII_VALUES["email_short"] + "."
        ),
        "pii_type_phone": (
            "At the rear gate, callback: " + PII_VALUES["phone_short"] + "."
        ),
    }
    shape_groups = {
        "pii_presence_absent": "presence", "pii_presence_present": "presence",
        "pii_count_one": "count", "pii_count_two": "count",
        "pii_type_email": "type", "pii_type_phone": "type",
    }
    for case_id, text in shape_cases.items():
        group = shape_groups[case_id]
        cases[case_id] = _run_one(
            upstream, modules, case_id, text,
            incident_id=f"paired-pii-shape-{group}",
            thread_id=f"source-study-pii-shape-{group}",
        )
    pair_specs.extend([
        {"left": "pii_presence_absent", "right": "pii_presence_present",
         "expected": "different", "dimension": "PII presence changes redacted skeleton"},
        {"left": "pii_count_one", "right": "pii_count_two",
         "expected": "different", "dimension": "PII occurrence count changes redacted skeleton"},
        {"left": "pii_type_email", "right": "pii_type_phone",
         "expected": "different", "dimension": "PII pattern type changes redaction marker"},
    ])

    # Re-exercise the exact source retry path with a deterministic first
    # classification failure. Only the injected offline model wrapper differs.
    retry_texts = [
        ("retry_email_a", _text_variant(email=PII_VALUES["email_short"])),
        ("retry_email_b", _text_variant(email=PII_VALUES["email_long"])),
    ]
    for case_id, text in retry_texts:
        cases[case_id] = _run_one(upstream, modules, case_id, text,
                                  incident_id="paired-retry-email",
                                  thread_id="source-study-paired-retry-email",
                                  fail_first_classification=True)
    pair_specs.append({"left": "retry_email_a", "right": "retry_email_b",
                       "expected": "equal", "dimension": "email value substitution through one repair retry"})

    # A public incident-content change must reach the classifier and can alter
    # its deterministic mock response and the downstream request.
    public_a = "A person reported an incident at the rear gate after closing."
    public_b = "A ransomware incident affected the network server after closing."
    cases["public_text_a"] = _run_one(
        upstream, modules, "public_text_a", public_a,
        incident_id="paired-public-text", thread_id="source-study-paired-public-text")
    cases["public_text_b"] = _run_one(
        upstream, modules, "public_text_b", public_b,
        incident_id="paired-public-text", thread_id="source-study-paired-public-text")
    pair_specs.append({"left": "public_text_a", "right": "public_text_b",
                       "expected": "different", "dimension": "public non-PII content mutation"})

    # Exercise the upstream default factory path with TRIAGE_LLM=mock, rather
    # than passing a model object. Its class-method wrapper delegates to the
    # original pinned MockLLM.complete body while capturing exact strings.
    cases["upstream_default_mock"] = _run_one(
        upstream, modules, "upstream_default_mock", public_a,
        incident_id="paired-public-text", thread_id="source-study-paired-public-text",
        use_default_mock=True,
    )
    pair_specs.append({"left": "public_text_a", "right": "upstream_default_mock",
                       "expected": "equal", "dimension": "injected wrapper versus upstream default mock factory"})

    # A name-like value is deliberately outside the README's three listed
    # patterns; record that it remains in the model request as a scope check.
    name_a = "A person named Jane Example reported a security incident at the rear gate."
    name_b = "A person named Alex Example reported a security incident at the rear gate."
    cases["unlisted_name_a"] = _run_one(
        upstream, modules, "unlisted_name_a", name_a,
        incident_id="paired-unlisted-name", thread_id="source-study-paired-unlisted-name")
    cases["unlisted_name_b"] = _run_one(
        upstream, modules, "unlisted_name_b", name_b,
        incident_id="paired-unlisted-name", thread_id="source-study-paired-unlisted-name")
    pair_specs.append({"left": "unlisted_name_a", "right": "unlisted_name_b",
                       "expected": "different", "dimension": "unlisted name-like public text"})

    # The pinned MockLLM searches the literal text "email"; its [EMAIL] mask
    # can therefore change its heuristic answer. This is a mock-only probe.
    neutral = "A routine report concerns activity near the site entrance."
    with_email = neutral + " Contact person@example.invalid."
    cases["mock_marker_absent"] = _run_one(upstream, modules,
                                           "mock_marker_absent", neutral,
                                           incident_id="paired-mock-marker",
                                           thread_id="source-study-paired-mock-marker")
    cases["mock_marker_present"] = _run_one(upstream, modules,
                                            "mock_marker_present", with_email,
                                            incident_id="paired-mock-marker",
                                            thread_id="source-study-paired-mock-marker")
    pair_specs.append({"left": "mock_marker_absent", "right": "mock_marker_present",
                       "expected": "different", "dimension": "mock-specific redaction-marker heuristic"})

    # Exercise the source-generated error route. The classifier runs once;
    # unknown-site enrichment sends control to human_review and skips draft.
    cases["unknown_site_route"] = _run_one(
        upstream, modules, "unknown_site_route",
        "A routine security incident occurred at an unlisted location.",
        site="NOT-A-SITE",
    )

    source_after = verify_upstream(upstream)
    checked_source_fields = (
        "commit", "git_tree", "license", "tracked_file_count",
        "tracked_file_sha256", "manifest_sha256",
    )
    if any(source_after[field] != source[field] for field in checked_source_fields):
        raise StudyError("upstream checkout changed during source execution")
    source["verified_before_and_after_execution"] = True
    pairs = [_pair(cases, spec["left"], spec["right"], expected=spec["expected"],
                   dimension=spec["dimension"])
             for spec in pair_specs]
    call_count = sum(len(case["calls"]) for case in cases.values())
    case_rows = [cases[key] for key in sorted(cases)]
    input_corpus_sha256 = sha256_bytes(canonical_bytes(
        [case["input"] for case in case_rows]
    ))
    return {
        "format": "orchlang-incident-triage-source-study",
        "version": 1,
        "source": source,
        "execution": {
            "mode": "unmodified upstream source, direct LangGraph execution",
            "provider": "none; upstream default mock and injected instrumented upstream MockLLM",
            "provider_configuration": {
                "TRIAGE_LLM": config.LLM_PROVIDER,
                "default_factory_runs": sum(
                    case["execution_mode"] == "upstream_default_mock"
                    for case in cases.values()
                ),
                "injected_wrapper_runs": sum(
                    case["execution_mode"] == "injected_mock_wrapper"
                    for case in cases.values()
                ),
            },
            "outbound_provider_calls": 0,
            "network_calls": sum(case["network_attempt_count"] for case in cases.values()),
            "process_calls": sum(case["process_attempt_count"] for case in cases.values()),
            "network_guard": (
                "socket.socket connect/send methods, socket.create_connection, and "
                "socket.getaddrinfo fail closed during graph execution"
            ),
            "process_guard": "subprocess.Popen/run and os.system/popen fail closed during graph execution",
            "source_node_invocations": sum(
                sum(event["kind"] == "node" for event in case["node_events"])
                for case in cases.values()
            ),
            "case_count": len(cases),
            "model_call_count": call_count,
            "cost_usage_rows": sum(len(case["usage"]) for case in cases.values()),
            "source_cost_model": (
                "estimate_tokens(text)=max(1,len(text)//4); call input is system+user; "
                "output is the exact deterministic mock string"
            ),
            "mock_contract": (
                "Pinned triage.llm.MockLLM is deterministic from system/user text; "
                "paired executions rerun identical requests and therefore produce "
                "identical responses. The retry probe injects one fixed malformed "
                "classification response before delegating to that same mock. "
                "One case calls build_graph() with TRIAGE_LLM=mock and instruments "
                "the upstream MockLLM method while preserving its body."
            ),
        },
        "study_questions": {
            "observation": "exact ordered system/user/response strings, source token-cost rows, node/update events, interrupt, and selected terminal projection",
            "not_compared_as_whole_output": [
                "raw incident object retained in graph state/checkpoints",
                "internal logger output",
                "runtime metadata outside the captured stream updates and selected terminal fields",
            ],
            "pii_pairs_expected_equal": True,
            "pii_shape_pairs_expected_different": True,
            "retry_pair_expected_equal": True,
            "public_mutation_expected_different": True,
            "unlisted_name_expected_different": True,
            "unknown_site_route_expected": ["classify", "enrich", "human_review"],
        },
        "pairs": pairs,
        "cases": case_rows,
        "findings": [
            {
                "id": "redacted-pair-trace-equality",
                "observation": "For each paired value in the three README-listed PII patterns, the upstream redactor produced identical text and the executed graph produced identical full request/response, reported-usage, node-event, and terminal records.",
                "scope": "Only the synthetic input pairs, pinned code, deterministic mock, injected retry schedule, and collected observations in this report.",
            },
            {
                "id": "retry-path-preserves-pair-equality",
                "observation": "With one deterministic malformed classifier response, the upstream retry helper generated the same repair prompt for both email variants, and the entire three-call graph traces matched.",
                "scope": "One fixed failure position and fixed mock response; not all provider errors or retries.",
            },
            {
                "id": "redaction-shape-remains-observable",
                "observation": "The redactor normalizes matched values, but its output retains marker presence, occurrence count, and pattern type. The presence, count, and type probes therefore use different exact classifier requests and are not value-substitution equality pairs.",
                "scope": "Three fixed synthetic comparisons under the pinned deterministic mock; no provider or all-input inference.",
            },
            {
                "id": "default-mock-factory-equivalence",
                "observation": "For one fixed public incident, direct build_graph() with TRIAGE_LLM=mock matched the injected-wrapper run in exact captured model calls, source usage rows, node events, and terminal projection.",
                "scope": "One deterministic mock case; instrumentation delegates to the pinned MockLLM.complete implementation.",
            },
            {
                "id": "unsupported-name-remains-in-input",
                "observation": "The two synthetic name-like strings are outside the three README-listed patterns; they remained in source-redacted text and the classifier requests differed.",
                "scope": "This is outside the documented pattern list and is not reported as a violation of that limited promise.",
            },
            {
                "id": "mock-email-marker-heuristic",
                "observation": "The source mock's keyword list includes 'email'; because the source redactor emits '[EMAIL]', adding a redacted email can affect the mock's heuristic classification on neutral text.",
                "scope": "Mock-specific behavior only; no inference about real LLM classifiers.",
            },
            {
                "id": "raw-state-remains-outside-request-projection",
                "observation": "The graph input state retains the original incident object while the classify prompt uses redacted incident.text; this run records request traces, not checkpoint confidentiality.",
                "scope": "No claim about persistence security or storage encryption.",
            },
        ],
        "assumptions_and_limits": [
            "No real personal data, API key, or provider endpoint is used.",
            "The tracked source hashes, commit, and tree are checked before import and after all graph runs; outbound socket connect and datagram send operations fail closed during graph execution.",
            "The upstream default factory is exercised once with TRIAGE_LLM=mock; other cases pass an instrumented wrapper around the pinned MockLLM.",
            "No source-to-graph translation is performed or claimed.",
            "Usage rows are source estimates, not provider-reported token counts or monetary billing.",
            "The mock is deterministic and not a probabilistic shared-oracle implementation.",
            "The source redactor covers only its explicit regexes; this study does not establish general PII removal.",
            "The graph uses LangGraph MemorySaver and retains the original input state; this study does not analyze checkpoint or other storage confidentiality.",
            "Finite direct executions do not establish an all-input theorem, deployed-provider security, or general noninterference.",
        ],
        "harness": {
            "run_study_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "manifest_sha256": sha256_bytes(MANIFEST_PATH.read_bytes()),
            "dependency_lock_sha256": sha256_bytes((HERE / "requirements.lock").read_bytes()),
            "verifier_sha256": sha256_bytes((HERE / "verify_results.py").read_bytes()),
            "test_sha256": sha256_bytes((HERE / "test_study.py").read_bytes()),
            "input_corpus_sha256": input_corpus_sha256,
            "python": sys.version.split()[0],
            "langgraph": metadata.version("langgraph"),
            "pydantic": metadata.version("pydantic"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path,
                        default=Path(os.environ["INCIDENT_TRIAGE_UPSTREAM"])
                        if os.environ.get("INCIDENT_TRIAGE_UPSTREAM") else None,
                        help="clean checkout at the pinned commit (or INCIDENT_TRIAGE_UPSTREAM)")
    parser.add_argument("--output", type=Path,
                        default=HERE / "results" / "source_study.json")
    args = parser.parse_args(argv)
    if args.upstream is None:
        parser.error("--upstream or INCIDENT_TRIAGE_UPSTREAM is required")
    try:
        report = run_study(args.upstream)
        raw = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if len(raw) > MAX_SOURCE_OUTPUT_BYTES:
            raise StudyError("study report exceeds output size limit")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    except (StudyError, OSError, ValueError, KeyError) as error:
        print(f"source-study failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output),
                      "cases": report["execution"]["case_count"],
                      "calls": report["execution"]["model_call_count"],
                      "source_commit": report["source"]["commit"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
