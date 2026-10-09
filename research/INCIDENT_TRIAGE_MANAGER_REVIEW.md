# Isolated session manager peer review

Review date: 2026-10-09. The source reviewed was the working-tree version of
`integrations/incident_triage/concurrency/isolated_session_manager.py` with
SHA-256 `1615fea07a72280d09e5114c2787e4451ca1f3ea0d8a875fb3f2ec84886f082b`;
the accompanying test file had SHA-256
`0343083db1b2e1537e2e249854f15992db14a6e993ecbb492b959d5dafb2ff05`.
These digests identify the review snapshot, not a frozen release.

## Findings

### Source loader collision: found, then fixed

The first review pass found that `_load_source_modules()` imported the generic
top-level name `run_study`. A preloaded `sys.modules["run_study"]` could supply
an unrelated `load_pinned_source()` function and modules whose `__module__`
strings were set to `triage.graph` and `triage.llm`. The independent source
replay still succeeded, so the manager returned `evidence.status ==
"verified"`. In a fresh locked-environment process I used that technique to
make `start()` report a fabricated pending session and `approve()` report a
fabricated approval. No repository files were changed for the reproduction.

The current working tree addresses this case by importing
`integrations.incident_triage.run_study`, checking the module and loader
origins, binding the harness file digest to the replayed study, and adding
wrong-origin and unrelated-top-level-module tests. I reran the original
top-level collision after that change; it loaded the real graph module from
the pinned snapshot. This evidence assumes a trusted Python process and does
not claim protection from arbitrary code already executing in that process.

### Cancellation cleanup: found, then fixed

The earlier `except Exception` cleanup missed `KeyboardInterrupt`,
`SystemExit`, and `asyncio.CancelledError`. An interruption during `start()`
could leave an unexpiring `starting` entry; an interruption during
`approve()` could leave a continuation available after partial mutation. The
current manager cleans up on `BaseException` and re-raises. Focused tests now
exercise cancellation in both paths.

### Idle expiry and capacity: improved; sweep remains needed for idle-only use

The first version required callers to invoke `expire_due()` before a new
session could use capacity held by expired apps. The current `start()` sweeps
expired sessions before reserving capacity, and a focused capacity-recovery
test covers that path. An otherwise idle process still retains expired apps
until a sweep or an operation touches them, so a long-lived host that needs
prompt memory release should schedule `expire_due()` periodically. This is
consistent with the documented manual sweep API; the manager has no janitor
thread.

### Evidence byte cap is checked after allocation

`_read_json()` currently calls `Path.read_bytes()` before comparing the
resulting buffer length with `MAX_EVIDENCE_JSON_BYTES` (16 MiB). The report,
attestation, and source-study files are rejected when oversized, but an
oversized or corrupted local file is fully allocated before rejection. A
bounded read of at most limit-plus-one bytes would make this a peak-memory
bound and avoid a file-growth race between a size check and read. The
dependency lock and harness digest are also read without a preflight, though
their checked-in files are small. This is a local evidence-file resource
hardening issue, not an upstream graph or workflow issue.

## Isolation and evidence boundary

The tests cover two distinct incidents starting in a controlled concurrent
schedule, separate graph and mock objects, matching call digests and source
usage rows, and approval on the same retained app without another model call.
They also cover capacity, duplicate IDs, discard, expiry, a busy session,
human review, malformed input, source tampering, source-loader collisions,
and cancellation. The parent reports 12 manager tests and 18 total
concurrency tests passing; this review independently reran only the
top-level-loader collision probe after its fix.

These checks support per-session separation for the tested local schedule.
They do not establish production service behavior or arbitrary-schedule
linearizability. The source keeps raw incident text in the in-memory graph
checkpoint until the session is closed; receipts omit prompt and response
text, while the manager documentation explicitly excludes checkpoint
privacy, persistence, and cross-process recovery. The default limits bound
active sessions, lifetime IDs, incident fields, model-call count, prompt and
response characters, and evidence size. The session-count limits are
operator-configurable; callers should keep those settings within their
memory budget.

## Root resolution after this peer-review snapshot

The evidence JSON reader now performs a bounded binary read of at most 16 MiB + 1 byte before decoding. A sparse oversized-file regression was added. This fixes the named reader allocation issue; it does not assert a total process-memory bound for Python, source parsing, or third-party libraries. The full concurrency/session suite now has 19 tests (6 witness + 13 manager). The final extension manifest records the new file hashes. This resolution was reproduced by the root agent, not independently re-reviewed by the peer reviewer.
