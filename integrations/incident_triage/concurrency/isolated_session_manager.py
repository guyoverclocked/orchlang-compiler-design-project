#!/usr/bin/env python3
"""Bounded offline session manager for the pinned incident-triage source.

Every accepted incident receives a fresh upstream ``build_graph`` instance,
tracker, wrapper, and memory checkpointer. The app is retained by incident ID
until approval, explicit discard, or expiry. Initialization fails closed
unless the checked-in upstream snapshot, locked runtime, and independent
source-projection replay all match their checked-in evidence.

This is an offline source-profile utility. It accepts no provider client and
never calls a provider. A pending LangGraph checkpoint still contains the raw
incident in process memory; this manager does not provide checkpoint
encryption, persistence, cross-process recovery, or a production service API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parent
REPO_ROOT = HERE.parents[2]
DEFAULT_SOURCE_ROOT = INTEGRATION / "upstream_snapshot"
SOURCE_REPORT = INTEGRATION / "source_analysis" / "artifacts" / "source_analysis.json"
SOURCE_ATTESTATION = INTEGRATION / "source_analysis" / "artifacts" / "source_analysis.attestation.json"
SOURCE_STUDY = INTEGRATION / "results" / "source_study.json"
LOCK_PATH = INTEGRATION / "requirements.lock"

FORMAT = "orchlang-incident-triage-isolated-session-manager"
VERSION = 1
DEFAULT_MAX_PENDING = 32
DEFAULT_MAX_LIFETIME_SESSIONS = 10_000
DEFAULT_TTL_SECONDS = 30 * 60.0
MAX_INCIDENT_ID_CHARS = 128
MAX_METADATA_CHARS = 256
MAX_INCIDENT_TEXT_CHARS = 4_000
MAX_INPUT_JSON_BYTES = 16 * 1024
MAX_EVIDENCE_JSON_BYTES = 16 * 1024 * 1024
MAX_PROMPT_CHARS = 64 * 1024
MAX_RESPONSE_CHARS = 64 * 1024


class SessionManagerError(RuntimeError):
    """Base class for bounded manager failures."""


class SourceGateError(SessionManagerError):
    """Source, runtime, or independent replay did not match the fixed profile."""


class InvalidIncident(SessionManagerError):
    """Input is outside the source model or manager bounds."""


class DuplicateSession(SessionManagerError):
    """An incident ID has already been used in this manager process."""


class SessionCapacityExceeded(SessionManagerError):
    """The active or lifetime session bound has been reached."""


class SessionNotFound(SessionManagerError):
    """No active app is retained for the requested incident ID."""


class SessionBusy(SessionManagerError):
    """Another operation is already mutating this session."""


class SessionExpired(SessionManagerError):
    """The retained app expired before approval or discard."""


class InvalidSessionState(SessionManagerError):
    """The source graph is not at an approvable pending gate."""


class _SourceCallError(SessionManagerError):
    """A pinned source call exceeded bounds or violated its expected contract."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _read_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_EVIDENCE_JSON_BYTES + 1)
        if len(raw) > MAX_EVIDENCE_JSON_BYTES:
            raise SourceGateError(f"{label} exceeds the local evidence byte bound")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise SourceGateError(f"cannot read fixed {label}: {error}") from error
    return raw, value


def _locked_versions() -> dict[str, str]:
    try:
        raw = LOCK_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise SourceGateError(f"cannot read dependency lock: {error}") from error
    versions: dict[str, str] = {}
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise SourceGateError(f"dependency lock line {line_number} is not exactly pinned")
        name, version = match.groups()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in versions:
            raise SourceGateError(f"dependency lock repeats normalized package {key}")
        versions[key] = version
    if not versions:
        raise SourceGateError("dependency lock contains no pinned packages")
    observed: dict[str, str] = {}
    for name in sorted(versions):
        try:
            observed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise SourceGateError(f"locked package is not installed: {name}") from error
    mismatch = {name: (versions[name], observed.get(name)) for name in versions
                if observed.get(name) != versions[name]}
    if mismatch:
        raise SourceGateError(f"installed dependencies differ from lock: {mismatch}")
    return observed


def _verify_runtime(source_report: Mapping[str, Any]) -> dict[str, Any]:
    lock_raw = LOCK_PATH.read_bytes()
    lock_digest = _sha256(lock_raw)
    expected = source_report.get("runtime_provenance")
    if not isinstance(expected, dict):
        raise SourceGateError("source report has no runtime provenance")
    versions = _locked_versions()
    actual = {
        "python": platform.python_version(),
        "langgraph": importlib.metadata.version("langgraph"),
        "pydantic": importlib.metadata.version("pydantic"),
        "dependency_lock_sha256": lock_digest,
    }
    for field_name in actual:
        if expected.get(field_name) != actual[field_name]:
            raise SourceGateError(
                f"runtime field {field_name} differs from source report: "
                f"expected {expected.get(field_name)!r}, observed {actual[field_name]!r}"
            )
    return {**actual, "locked_distribution_count": len(versions)}


def verify_source_gate(source_root: Path = DEFAULT_SOURCE_ROOT) -> dict[str, Any]:
    """Validate snapshot bytes, pinned runtime, and saved independent replay.

    This gate does not execute upstream Python. It uses the independent
    ``replay_projection`` checker, then requires the checked-in attestation to
    match that fresh result byte-semantically.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from integrations.incident_triage.source_analysis.bridge import load_verified_source
        from integrations.incident_triage.source_analysis.replay_projection import replay_projection
    except Exception as error:
        raise SourceGateError(f"cannot load fixed source gate modules: {error}") from error
    root = Path(source_root).resolve(strict=True)
    try:
        _files, source = load_verified_source(root)
    except Exception as error:
        raise SourceGateError(f"pinned upstream source check failed: {error}") from error
    report_raw, report = _read_json(SOURCE_REPORT, "source analysis report")
    attestation_raw, saved_attestation = _read_json(SOURCE_ATTESTATION, "source replay attestation")
    if not isinstance(report, dict) or not isinstance(saved_attestation, dict):
        raise SourceGateError("fixed source evidence must be JSON objects")
    if report.get("source") != source:
        raise SourceGateError("source report does not bind the selected pinned snapshot")
    try:
        replay = replay_projection(SOURCE_REPORT, root, SOURCE_STUDY)
    except Exception as error:
        raise SourceGateError(f"independent source replay failed: {error}") from error
    if replay.get("status") != "verified" or saved_attestation != replay:
        raise SourceGateError("saved attestation does not match the fresh independent replay")
    runtime = _verify_runtime(report)
    return {
        "status": "verified",
        "source_commit": source["commit"],
        "source_tree": source["git_tree"],
        "source_license": source["license"],
        "source_manifest_sha256": source["manifest_sha256"],
        "source_report_sha256": _sha256(report_raw),
        "source_attestation_sha256": _sha256(attestation_raw),
        "source_study_sha256": replay["source_study_sha256"],
        "source_replay_checker_sha256": replay["replay_checker_sha256"],
        "source_replay_graph_sha256": replay["graph"]["graph_sha256"],
        "source_replay_certificate_sha256": replay["graph"]["certificate_sha256"],
        "source_replay_checks": len(replay["checks"]),
        "runtime": runtime,
        "source_root": str(root),
    }


def _source_still_bound(source_root: Path, expected: Mapping[str, Any]) -> None:
    """Recheck source bytes around each graph build and continuation."""
    try:
        from integrations.incident_triage.source_analysis.bridge import load_verified_source
        _files, source = load_verified_source(source_root)
    except Exception as error:
        raise SourceGateError(f"pinned source changed or failed verification: {error}") from error
    if source.get("commit") != expected.get("source_commit") \
            or source.get("git_tree") != expected.get("source_tree") \
            or source.get("manifest_sha256") != expected.get("source_manifest_sha256"):
        raise SourceGateError("pinned source identity changed during manager lifetime")
    if _sha256(LOCK_PATH.read_bytes()) != expected["runtime"]["dependency_lock_sha256"]:
        raise SourceGateError("dependency lock changed during manager lifetime")


def _source_estimate(text: str) -> int:
    return max(1, len(text) // 4)


class _DigestOnlyMock:
    """Call the exact pinned MockLLM while retaining no prompt/response text."""

    name = "mock"

    def __init__(self, delegate: Any, classify_system: str, draft_system: str):
        self._delegate = delegate
        self._classify_system = classify_system
        self._draft_system = draft_system
        self._calls: list[dict[str, Any]] = []

    @property
    def calls(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(call) for call in self._calls)

    def complete(self, system: str, user: str) -> str:
        if not isinstance(system, str) or not isinstance(user, str):
            raise _SourceCallError("source mock request must contain text")
        if len(self._calls) >= 3:
            raise _SourceCallError("source graph exceeded its three-completion bound")
        if len(system) + len(user) > MAX_PROMPT_CHARS:
            raise _SourceCallError("source mock request exceeds the manager bound")
        if system == self._classify_system:
            phase = "classify"
        elif system == self._draft_system:
            phase = "draft"
        else:
            raise _SourceCallError("pinned graph issued an unrecognized model system prompt")
        response = self._delegate.complete(system, user)
        if not isinstance(response, str) or len(response) > MAX_RESPONSE_CHARS:
            raise _SourceCallError("pinned mock response is non-text or exceeds the manager bound")
        request_bytes = _json_bytes([system, user])
        response_bytes = response.encode("utf-8")
        self._calls.append({
            "phase": phase,
            "request_sha256": _sha256(request_bytes),
            "response_sha256": _sha256(response_bytes),
            "input_tokens": _source_estimate(system + user),
            "output_tokens": _source_estimate(response),
        })
        return response


@dataclass
class _Session:
    incident_id: str
    thread_id: str
    status: str
    created_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    expires_at: float | None = None
    app: Any | None = None
    mock: _DigestOnlyMock | None = None
    cost_rows: list[dict[str, Any]] = field(default_factory=list)
    last_error_sha256: str | None = None


def _public_cost_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        raise _SourceCallError("source cost rows violate the manager bound")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"node", "input_tokens", "output_tokens", "cost_usd"}:
            raise _SourceCallError("source cost row has an unexpected shape")
        node = row["node"]
        input_tokens = row["input_tokens"]
        output_tokens = row["output_tokens"]
        cost = row["cost_usd"]
        if node not in {"classify", "draft"} or type(input_tokens) is not int or type(output_tokens) is not int \
                or input_tokens < 1 or output_tokens < 1 or not isinstance(cost, (int, float)) \
                or not math.isfinite(cost):
            raise _SourceCallError("source cost row has invalid values")
        rows.append({"node": node, "input_tokens": input_tokens,
                     "output_tokens": output_tokens, "cost_usd": float(cost)})
    return rows


def _check_rows_against_calls(rows: list[dict[str, Any]], calls: tuple[dict[str, Any], ...]) -> None:
    if not rows:
        # The pinned source's schema-repair failure returns an error update
        # without copying tracker entries into state; the digest wrapper still
        # reports those calls without retaining their contents.
        return
    if len(rows) != len(calls):
        raise _SourceCallError("returned source cost rows do not match captured mock calls")
    for row, call in zip(rows, calls):
        if row["node"] != call["phase"] or row["input_tokens"] != call["input_tokens"] \
                or row["output_tokens"] != call["output_tokens"] or row["cost_usd"] != 0.0:
            raise _SourceCallError("source tracker arithmetic differs from the observed mock request")


def _incident_model(modules: tuple[Any, ...], value: Mapping[str, Any]) -> Any:
    if not isinstance(value, Mapping) or set(value) != {"incident_id", "site", "reported_by", "text"}:
        raise InvalidIncident("incident must contain exactly incident_id, site, reported_by, and text")
    text_fields = ("incident_id", "site", "reported_by", "text")
    if any(not isinstance(value.get(field_name), str) for field_name in text_fields):
        raise InvalidIncident("all incident fields must be strings")
    try:
        for field_name in text_fields:
            value[field_name].encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise InvalidIncident("incident fields must be valid UTF-8 text") from error
    if not value["incident_id"] or len(value["incident_id"]) > MAX_INCIDENT_ID_CHARS:
        raise InvalidIncident("incident_id must be nonempty and at most 128 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in value["incident_id"]):
        raise InvalidIncident("incident_id cannot contain control characters")
    if len(value["site"]) > MAX_METADATA_CHARS or len(value["reported_by"]) > MAX_METADATA_CHARS:
        raise InvalidIncident("site and reported_by are limited to 256 characters each")
    if len(value["text"]) < 10 or len(value["text"]) > MAX_INCIDENT_TEXT_CHARS:
        raise InvalidIncident("incident text must contain 10–4,000 characters")
    try:
        if len(_json_bytes(dict(value))) > MAX_INPUT_JSON_BYTES:
            raise InvalidIncident("serialized incident exceeds the manager input bound")
        model = modules[2].IncidentReport.model_validate(dict(value))
    except InvalidIncident:
        raise
    except Exception as error:
        raise InvalidIncident(f"incident failed the pinned source schema: {error}") from error
    return model


class IsolatedSessionManager:
    """Manage bounded, per-incident instances of the pinned offline graph.

    ``start`` runs to the source's pre-dispatch gate. ``approve`` continues the
    same graph/checkpointer and removes the handle after successful dispatch.
    Each active ID is single-use for this manager's lifetime, including after
    discard/expiry, so a delayed approval cannot target a replacement case.
    """

    def __init__(self, *, source_root: Path = DEFAULT_SOURCE_ROOT,
                 max_pending: int = DEFAULT_MAX_PENDING,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 max_lifetime_sessions: int = DEFAULT_MAX_LIFETIME_SESSIONS,
                 clock: Callable[[], float] = time.monotonic):
        if type(max_pending) is not int or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) \
                or not math.isfinite(ttl_seconds) or ttl_seconds <= 0 or ttl_seconds > 24 * 60 * 60:
            raise ValueError("ttl_seconds must be in (0, 86400]")
        if type(max_lifetime_sessions) is not int or max_lifetime_sessions < max_pending:
            raise ValueError("max_lifetime_sessions must be >= max_pending")
        self.source_root = Path(source_root).resolve(strict=True)
        self.max_pending = max_pending
        self.ttl_seconds = float(ttl_seconds)
        self.max_lifetime_sessions = max_lifetime_sessions
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}
        self._used_ids: set[str] = set()
        self._terminal: dict[str, str] = {}

        self.evidence = verify_source_gate(self.source_root)
        self._source_binding = self.evidence
        self._modules = self._load_source_modules(self.source_root)

    @staticmethod
    def _load_source_modules(source_root: Path) -> tuple[Any, ...]:
        # This occurs only after verify_source_gate succeeded. The exact pinned
        # run harness additionally refuses any preloaded triage package and
        # checks that imports came from the selected checkout.
        from integrations.incident_triage import run_study as source_study

        expected_harness = (INTEGRATION / 'run_study.py').resolve()
        origin = getattr(source_study, '__file__', None)
        loader = getattr(source_study, 'load_pinned_source', None)
        loader_code = getattr(loader, '__code__', None)
        if origin is None or Path(origin).resolve() != expected_harness \
                or loader_code is None or Path(loader_code.co_filename).resolve() != expected_harness \
                or getattr(loader, '__globals__', None) is not vars(source_study):
            raise SourceGateError('source harness module/function origin differs from the fixed repository file')
        _study_raw, study = _read_json(SOURCE_STUDY, 'source study')
        if _sha256(expected_harness.read_bytes()) != study.get('harness', {}).get('run_study_sha256'):
            raise SourceGateError('source harness bytes differ from the independently replayed source study')

        # This manager is intentionally an offline profile. Keep tracing off
        # for its lifetime as well as injecting MockLLM explicitly, so an
        # ambient LangSmith tracing setting cannot export prompts.
        os.environ["TRIAGE_LLM"] = "mock"
        os.environ["LANGSMITH_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGCHAIN_TRACING"] = "false"
        try:
            modules = source_study.load_pinned_source(source_root)
        except Exception as error:
            raise SourceGateError(f"cannot import the verified upstream source: {error}") from error
        graph_module, llm_module, _models, _costs, config = modules
        if config.LLM_PROVIDER != "mock":
            raise SourceGateError("pinned source did not load with its offline mock provider")
        if graph_module.build_graph.__module__ != "triage.graph" \
                or llm_module.MockLLM.__module__ != "triage.llm":
            raise SourceGateError("pinned graph/mock module identity is unexpected")
        return modules

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def sessions(self) -> list[dict[str, Any]]:
        """Return metadata only; never return incident, prompt, or checkpoint text."""
        now = self._clock()
        with self._lock:
            return [
                {"incident_id": item.incident_id, "thread_id": item.thread_id,
                 "status": item.status,
                 "expires_in_seconds": (max(0.0, item.expires_at - now)
                                        if item.expires_at is not None else None)}
                for item in sorted(self._sessions.values(), key=lambda session: session.created_at)
            ]

    def start(self, incident_value: Mapping[str, Any]) -> dict[str, Any]:
        incident = _incident_model(self._modules, incident_value)
        self.expire_due()
        incident_id = incident.incident_id
        now = self._clock()
        session = _Session(incident_id=incident_id, thread_id=incident_id,
                           status="starting", created_at=now)
        # Reserve atomically before doing graph work, preventing duplicate
        # starts and ensuring the active app bound cannot be exceeded.
        session.lock.acquire()
        reserved = False
        try:
            with self._lock:
                if incident_id in self._used_ids:
                    raise DuplicateSession("incident_id has already been used by this manager")
                if len(self._sessions) >= self.max_pending:
                    raise SessionCapacityExceeded("active session capacity is full")
                if len(self._used_ids) >= self.max_lifetime_sessions:
                    raise SessionCapacityExceeded("manager lifetime session limit is full; restart the manager")
                self._used_ids.add(incident_id)
                self._sessions[incident_id] = session
                reserved = True

            _source_still_bound(self.source_root, self._source_binding)
            graph_module, llm_module, _models, _costs, _config = self._modules
            if llm_module.MockLLM.__module__ != "triage.llm":
                raise SourceGateError("refusing to instantiate a non-pinned mock")
            mock = _DigestOnlyMock(llm_module.MockLLM(), graph_module.CLASSIFY_SYSTEM,
                                   graph_module.ACTIONS_SYSTEM)
            app = graph_module.build_graph(llm=mock)
            if not hasattr(app, "invoke"):
                raise SourceGateError("pinned graph factory did not return an invokable app")
            session.app = app
            session.mock = mock
            state = graph_module.triage_incident(app, incident, thread_id=session.thread_id)
            _source_still_bound(self.source_root, self._source_binding)
            if not isinstance(state, dict):
                raise _SourceCallError("upstream graph returned a non-object state")
            rows = _public_cost_rows(state.get("costs"))
            calls = mock.calls
            _check_rows_against_calls(rows, calls)
            if state.get("error"):
                status = "human_review"
                error_sha256 = _sha256(str(state["error"]).encode("utf-8"))
            else:
                report = state.get("report")
                if not isinstance(report, dict) or report.get("status") != "pending_approval":
                    raise _SourceCallError("source did not stop at the expected approval gate")
                if len(calls) < 2 or len(calls) > 3:
                    raise _SourceCallError("source model call count is outside its bounded retry contract")
                status = "pending_approval"
                error_sha256 = None
            session.cost_rows = rows
            session.last_error_sha256 = error_sha256
            with self._lock:
                session.status = status
                session.expires_at = self._clock() + self.ttl_seconds
            return self._receipt(session)
        except BaseException:
            if reserved:
                with self._lock:
                    self._sessions.pop(incident_id, None)
                    self._terminal[incident_id] = "failed"
                session.status = "failed"
                session.app = None
                session.mock = None
            raise
        finally:
            session.lock.release()

    @staticmethod
    def _receipt(session: _Session) -> dict[str, Any]:
        return {
            "incident_id": session.incident_id,
            "thread_id": session.thread_id,
            "status": session.status,
            "model_calls": list(session.mock.calls) if session.mock is not None else [],
            "cost_rows": [dict(row) for row in session.cost_rows],
            "error_sha256": session.last_error_sha256,
        }

    def approve(self, incident_id: str) -> dict[str, Any]:
        session = self._lookup(incident_id)
        if not session.lock.acquire(blocking=False):
            raise SessionBusy("another operation is already using this incident app")
        try:
            self._require_registered(session)
            self._expire_if_due(session)
            if session.status != "pending_approval" or session.app is None or session.mock is None:
                raise InvalidSessionState("only a pending pre-dispatch session can be approved")
            _source_still_bound(self.source_root, self._source_binding)
            before = len(session.mock.calls)
            graph_module = self._modules[0]
            state = graph_module.approve(session.app, session.thread_id)
            _source_still_bound(self.source_root, self._source_binding)
            after = len(session.mock.calls)
            if before != after:
                raise _SourceCallError("approval unexpectedly made an additional model call")
            report = state.get("report") if isinstance(state, dict) else None
            if not isinstance(report, dict) or report.get("status") != "approved":
                raise _SourceCallError("pinned approval continuation did not reach approved status")
            result = {"incident_id": session.incident_id, "thread_id": session.thread_id,
                      "status": "approved", "model_calls_before": before,
                      "model_calls_after": after}
            with self._lock:
                session.status = "approved"
                self._sessions.pop(session.incident_id, None)
                self._terminal[session.incident_id] = "approved"
                session.app = None
                session.mock = None
            return result
        except BaseException:
            if session.status == "pending_approval":
                with self._lock:
                    session.status = "failed"
                    self._sessions.pop(session.incident_id, None)
                    self._terminal[session.incident_id] = "failed"
                    session.app = None
                    session.mock = None
            raise
        finally:
            session.lock.release()

    def discard(self, incident_id: str) -> dict[str, Any]:
        session = self._lookup(incident_id)
        if not session.lock.acquire(blocking=False):
            raise SessionBusy("another operation is already using this incident app")
        try:
            self._require_registered(session)
            self._expire_if_due(session)
            with self._lock:
                if self._sessions.get(session.incident_id) is not session:
                    self._raise_terminal(session.incident_id)
                prior_status = session.status
                session.status = "discarded"
                self._sessions.pop(session.incident_id)
                self._terminal[session.incident_id] = "discarded"
                session.app = None
                session.mock = None
            return {"incident_id": incident_id, "status": "discarded",
                    "previous_status": prior_status}
        finally:
            session.lock.release()

    def expire_due(self) -> list[str]:
        """Release expired handles; a session being mutated is skipped safely."""
        now = self._clock()
        with self._lock:
            candidates = list(self._sessions.values())
        expired: list[str] = []
        for session in candidates:
            if not session.lock.acquire(blocking=False):
                continue
            try:
                if session.expires_at is None or now < session.expires_at:
                    continue
                with self._lock:
                    if self._sessions.get(session.incident_id) is not session:
                        continue
                    session.status = "expired"
                    self._sessions.pop(session.incident_id)
                    self._terminal[session.incident_id] = "expired"
                    session.app = None
                    session.mock = None
                    expired.append(session.incident_id)
            finally:
                session.lock.release()
        return sorted(expired)

    def _lookup(self, incident_id: str) -> _Session:
        if not isinstance(incident_id, str):
            raise SessionNotFound("incident ID must be text")
        with self._lock:
            session = self._sessions.get(incident_id)
            if session is not None:
                return session
            terminal = self._terminal.get(incident_id)
            if terminal == "expired":
                raise SessionExpired("the incident app expired and was released")
            if terminal is not None:
                raise InvalidSessionState(f"the incident session is already closed ({terminal})")
        raise SessionNotFound("no retained app exists for this incident ID")

    def _require_registered(self, session: _Session) -> None:
        with self._lock:
            if self._sessions.get(session.incident_id) is not session:
                self._raise_terminal(session.incident_id)

    def _expire_if_due(self, session: _Session) -> None:
        if session.expires_at is None or self._clock() < session.expires_at:
            return
        with self._lock:
            if self._sessions.get(session.incident_id) is session:
                session.status = "expired"
                self._sessions.pop(session.incident_id)
                self._terminal[session.incident_id] = "expired"
                session.app = None
                session.mock = None
        raise SessionExpired("the incident app expired and was released")

    def _raise_terminal(self, incident_id: str) -> None:
        terminal = self._terminal.get(incident_id)
        if terminal == "expired":
            raise SessionExpired("the incident app expired and was released")
        if terminal is not None:
            raise InvalidSessionState(f"the incident session is already closed ({terminal})")
        raise SessionNotFound("no retained app exists for this incident ID")


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_ROOT,
                        help="path to the pinned upstream snapshot or exact clean checkout")
    parser.add_argument("--max-pending", type=int, default=2)
    parser.add_argument("--ttl-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)
    try:
        manager = IsolatedSessionManager(source_root=args.source, max_pending=args.max_pending,
                                         ttl_seconds=args.ttl_seconds)
        incidents = [
            {"incident_id": "OFFLINE-DEMO-A", "site": "GTS-01",
             "reported_by": "synthetic operator",
             "text": "An intruder forced the rear loading gate open."},
            {"incident_id": "OFFLINE-DEMO-B", "site": "GTS-01",
             "reported_by": "synthetic operator",
             "text": "A minor water leak was found in the storage room."},
        ]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(incidents)) as pool:
            started = list(pool.map(manager.start, incidents))
        approvals = [manager.approve(item["incident_id"]) for item in started]
        print(json.dumps({"format": FORMAT, "version": VERSION,
                          "gate": manager.evidence,
                          "starts": started, "approvals": approvals,
                          "active_sessions_after_approval": manager.active_count,
                          "network": "disabled by fixed source profile: pinned MockLLM only"},
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (SessionManagerError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"isolated offline session demo failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
