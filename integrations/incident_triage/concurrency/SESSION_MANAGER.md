# Offline isolated-session manager

`isolated_session_manager.py` is a small lifecycle wrapper for the pinned
incident-triage source. It addresses the shared closure state shown in the
concurrency study by building one fresh upstream graph per accepted incident
and retaining that same graph until its approval continuation, explicit
discard, or expiry.

The manager fails closed at construction unless all of these checks succeed:

1. The selected upstream tree matches the pinned commit, tree, tracked-file
   manifest, and MIT license.
2. Every installed distribution in `requirements.lock`, plus Python, LangGraph,
   Pydantic, and the lockfile digest, matches the source-analysis runtime
   record (Python 3.14.6, LangGraph 1.2.14, Pydantic 2.14.0 for this run).
3. The independent source-projection replay returns `verified` and exactly
   matches the saved attestation, including the report, source, graph, and
   certificate bindings.
4. The fully qualified source harness module, function origin and report-bound
   file digest must match the fixed repository file. Only then does it import
   the pinned source and construct a fresh graph with
   an explicit instance of the source repository's `MockLLM`.

At import time the offline profile sets `TRIAGE_LLM=mock` and disables the
LangSmith/LangChain tracing environment flags so ambient tracing configuration
cannot export prompts.

Before each graph build and approval continuation, the manager rechecks the
snapshot hashes and dependency-lock digest. It records hashes and source token
estimates for model calls, not prompt or response strings. Returned receipts
contain only call hashes, phases, source cost rows, status, and an error hash.

## Run the demonstration

Use the already locked offline environment from the repository root:

```sh
integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/concurrency/demo_isolated_sessions.py
```

The demo starts two synthetic non-PII incidents concurrently, reports their
separate `classify` and `draft` usage rows, then resumes each retained app
through the source `approve(app, thread_id)` function. It checks that approval
adds no model call. The only model used is the pinned deterministic mock.

The manager API is:

```python
manager = IsolatedSessionManager(max_pending=32, ttl_seconds=1800)
receipt = manager.start({
    "incident_id": "CASE-123",
    "site": "GTS-01",
    "reported_by": "synthetic operator",
    "text": "A synthetic incident with at least ten characters.",
})
approval = manager.approve("CASE-123")
```

`start` accepts exactly the four source `IncidentReport` fields. Each incident
ID is single-use for the lifetime of one manager process. Concurrent mutation
of the same app returns `SessionBusy`; distinct IDs may start concurrently.
Active pending and human-review apps count against `max_pending`. Human-review
states cannot be approved, but can be discarded. `expire_due()` releases idle
apps whose TTL elapsed; `start()` also sweeps expired idle apps before reserving
capacity. A session that is currently being mutated is skipped
until the next expiry sweep. The lifetime session count is bounded too; start a
new manager process after it is reached. Use one manager instance per process;
the pinned source loader refuses a preloaded `triage` package so that source
identity cannot be silently reused from another checkout.

## Limits

This is an offline repair demonstration for one hash-pinned source profile, not
a production-ready service or a general LangGraph isolation library. It does
not modify upstream code, provide cross-process approval recovery, use a web
server, or create a provider client. Restarting the process loses pending app
handles. LangGraph's in-memory checkpointer retains workflow state, including
raw incident text, until the app is approved, discarded, or expired; this
manager does not provide checkpoint privacy or encryption. The gate is a
source-specific AST/replay contract, not a mechanized proof of all Python or
LangGraph semantics. Usage rows remain the pinned source's `len(text)//4`
estimates, not provider billing receipts.

The loader checks guard against unrelated/preloaded module origins in a trusted
Python process. They are not a sandbox against arbitrary code execution or
monkey-patching inside that process. Cancellation during start or approval closes
the affected handle and re-raises the cancellation; approval cannot be retried
on a possibly partially advanced app.

## Tests

Run the lifecycle tests in the locked environment:

```sh
integrations/incident_triage/.venv/bin/python -m unittest discover \
  -s integrations/incident_triage/concurrency -p 'test_isolated_sessions.py' -v
```

They cover the required replay gate, concurrent starts, separate graph and
mock instances, exact source usage-row correspondence, approval on the same
retained apps with no added calls, duplicate and capacity handling, discard,
expiry, per-session locking, and the non-approvable human-review route.
The 13 manager tests also cover nonfinite TTLs, loader origin, cancellation, and
automatic expired-capacity recovery and bounded evidence JSON reads. Together with the six race-study tests,
the concurrency suite has 19 tests.
