# Pinned incident-triage graph: deterministic concurrency finding

## Finding

The pinned `agent-incident-triage` graph has invocation-shared tracking state.
With two incidents running concurrently through the same compiled graph, an
interleaving can put one incident's cost rows in the other incident's returned
state and can label a classification call as a draft call. The behavior comes
from the upstream graph factory and tracker, not from a compiler analysis.

This was reproduced against the unchanged MIT-licensed upstream repository
[`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
at commit `c08f710acfeefe233329df613fe8358eaac5f350` and tree
`2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`. All 23 tracked file hashes, the
clean Git worktree, commit/tree IDs, and the license were checked before and
after graph execution. The locked runtime was Python 3.14.6, LangGraph 1.2.14,
and Pydantic 2.14.0.

## Source path

In `src/triage/graph.py`, `build_graph` constructs one `CostTracker` and one
`TrackingLLM` in its closure (`graph.py:60–64`). Every invocation of the
compiled graph shares those objects. At the start of `classify`, the code
changes the shared wrapper's `current_node` to `"classify"` and clears the
shared `tracker.entries` list (`graph.py:66–70`). At the start of `draft`, it
changes `current_node` to `"draft"` (`graph.py:115–118`).

`TrackingLLM.complete` first calls the underlying model, then reads the mutable
`current_node` and records the request/completion on the shared tracker
(`src/triage/costs.py:47–62`). The model call may yield while another graph
invocation changes that field or clears/appends to the list. LangGraph's
per-thread checkpointer state does not make these closure objects per-thread.
The upstream FastAPI `_graph()` also caches one compiled graph in a process
singleton, while `/triage` assigns a distinct incident ID as `thread_id`
(`src/triage/api.py:19–25,34–45`).

## Controlled schedule and observation

The new runner in
[`integrations/incident_triage/concurrency/run_concurrency_study.py`](../integrations/incident_triage/concurrency/run_concurrency_study.py)
executes the upstream `build_graph` and nodes unchanged. It wraps only the
`complete(system, user)` boundary, delegates each response to the pinned
deterministic `MockLLM`, and uses a thread event to impose this schedule:

1. Incident A enters `classify`. The source sets `current_node = "classify"`
   and clears the tracker. Its mock response is computed, then the wrapper
   pauses before returning to `TrackingLLM.complete`.
2. Incident B enters `classify` on the **same graph**. It sets the shared node
   to `classify`, clears the tracker, records its classification, continues
   through enrichment and priority, and sets the shared node to `draft`.
3. B records its draft call and reaches the source's pending pre-dispatch
   interrupt. B's returned state contains its two cost rows.
4. The harness releases A. A returns from the underlying mock call into
   `TrackingLLM.complete`; the current shared node is still `draft`, so A's
   classification row is appended as a draft row. A continues to its own
   draft. Its returned cost snapshot includes B's two rows plus its two calls.

The inputs are synthetic non-PII text, use distinct incident/thread IDs, and
target the same known site. Network and process-creation APIs are blocked while
the graph runs and while approvals resume. The schedule contains 19 asserted
events and four observed source model calls.

### Observed usage rows

The source estimator is `max(1, len(system + user) // 4)` for input and
`max(1, len(response) // 4)` for output (`costs.py:15–17,24–35`). The source
MockLLM's price is zero, so the table reports estimated token units; it makes
no claim about provider tokenization or currency charges.

| Snapshot | Returned rows in order | Estimated tokens in snapshot |
|---|---|---:|
| B on shared graph | B classify, B draft | 231 |
| A on shared graph | B classify, B draft, A classify labeled `draft`, A draft | 456 |
| A with isolated graph | A classify, A draft | 225 |
| B with isolated graph | B classify, B draft | 231 |

The four unique calls consume 456 source-estimated tokens in aggregate. Adding
the two shared-graph per-run snapshots yields 687 because B's 231 tokens are
also present in A's snapshot. The row values themselves remain correct for the
corresponding prompt and completion; the task ownership and node attribution
are wrong. Because the pinned mock has zero prices, the experiment does not
measure an incorrect dollar amount or trigger the budget branch. Under a
nonzero pricing configuration, the same shared list can influence another
invocation's pre-draft budget check; that effect is a source-code consequence,
not a measured result here.

### Isolated per-invocation control

The mitigation control builds one unmodified graph per incident, concurrently
runs both, and keeps each app associated with its thread ID. Each closure then
owns a separate tracker, mutable node field, and memory checkpointer. The
returned pending states each have exactly their own two rows, labeled
`classify` and `draft`; recomputed requests and source usage match those rows.
The harness then resumes each pending workflow through `approve(app,
thread_id)`. Both become `approved`, retain their own thread ID, and make no
additional model call.

This demonstrates a usable isolation wrapper for active pending incidents.
An API implementation would need to retain each app until its approval or
expiry, then release it. The study does not implement such lifecycle
management. An upstream code fix could instead make the tracker and node label
invocation-local, but that change was not tested or included.

### Bounded offline session manager

The study now includes a runnable lifecycle wrapper in
[`isolated_session_manager.py`](../integrations/incident_triage/concurrency/isolated_session_manager.py).
It builds a fresh pinned graph with an explicit upstream `MockLLM` for each
accepted incident, keeps that exact app under its incident/thread ID through
the pre-dispatch approval gate, and resumes it through the upstream
`approve(app, thread_id)` function. It rejects reused IDs and concurrent
mutation of one app, bounds retained sessions, and releases idle apps on
explicit discard or expiry. Distinct IDs can start concurrently.

Manager initialization requires the pinned-source checks, the exact locked
runtime, and a fresh successful independent source-projection replay matching
the checked-in attestation. The manager returns prompt/response digests,
source-estimated usage rows, and status metadata; it retains no prompt strings
in its own call log. It fixes the provider selector to the mock and disables
LangSmith/LangChain tracing flags to keep this profile offline. Its LangGraph
in-memory checkpoint still holds raw incident state while a session is
pending. Approval, discard, or expiry releases the app handle. This utility
has no network server and never creates
a provider client; it is an offline repair for the pinned source profile, not
a production-ready lifecycle service. Full assumptions and limitations are in
[`SESSION_MANAGER.md`](../integrations/incident_triage/concurrency/SESSION_MANAGER.md).

Run its two-incident demonstration and lifecycle tests from the repository
root using the locked source environment:

```sh
integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/concurrency/demo_isolated_sessions.py

integrations/incident_triage/.venv/bin/python -m unittest discover \
  -s integrations/incident_triage/concurrency -p 'test_isolated_sessions.py' -v
```

The lifecycle suite has seven tests; the combined concurrency suite passes all
19 tests (including nonfinite lifetimes, loader origin, cancellation, expiry capacity recovery, and bounded evidence reads). The current manager gate binds source report
`0fd0eaa631ab5deb2da3ac396860271b87cc4eca6be1500f746dee29bfcb262a`, its
saved independent attestation
`7d02eb18f68ad409debed23702939945fc86d6c50656eaa4e71ec20cee28b033`, and
replay checker
`4d7917f19810e230e26d7573c5a7cbe8bb74a7649064a5084d89b127bde58175`.

| Added artifact | SHA-256 |
|---|---|
| `integrations/incident_triage/concurrency/isolated_session_manager.py` | `17b737386ff0bef1cbe9919da2876b865dfa15d7e746d792a68bbf3034c281a4` |
| `integrations/incident_triage/concurrency/demo_isolated_sessions.py` | `f766d63c448b031ac948c99f41806638f36403b2e4ea31e89f8aa91a3a8d71e0` |
| `integrations/incident_triage/concurrency/test_isolated_sessions.py` | `f36160bd43e82435f0af368ff39688857f62acaf2e851cdebd053e3fee5c9e27` |
| `integrations/incident_triage/concurrency/SESSION_MANAGER.md` | `70582dc33dca6729c5ff25ace92a685bcaca200f6de51f2bdebb4217ae667814` |

## Independent witness validation and reproduction

The evidence JSON is
[`integrations/incident_triage/concurrency/results/concurrency_study.json`](../integrations/incident_triage/concurrency/results/concurrency_study.json).
Its independent checker,
[`verify_concurrency_study.py`](../integrations/incident_triage/concurrency/verify_concurrency_study.py),
does not import the upstream package or runner. It checks the source checkout
against the manifest, verifies the deterministic event order and call prompts,
reconstructs the source estimate arithmetic and tracker-record order from the
schedule, checks the shared-graph row contamination/misattribution, and checks
the isolated per-ID rows and approval continuation. It rejects tampered node
labels, missing foreign rows, or a changed schedule. The record-order inference
is tied to the hash-bound upstream `TrackingLLM.complete` implementation; the
checker is not a second LangGraph interpreter.

Run from the project root using the already locked source-study environment:

```sh
INCIDENT_TRIAGE_UPSTREAM=/tmp/agent-incident-triage-research \
  integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/concurrency/run_concurrency_study.py

integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/concurrency/verify_concurrency_study.py

INCIDENT_TRIAGE_UPSTREAM=/tmp/agent-incident-triage-research \
  integrations/incident_triage/.venv/bin/python -m unittest discover \
  -s integrations/incident_triage/concurrency -p 'test_*.py' -v
```

The study ran six tests successfully. The runner report and the one controlled
schedule are byte-stable in the pinned environment. Recorded SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `run_concurrency_study.py` | `7c8136cc435e79d426f8296e32a64b03d7f3a21098e48ab685f148f653f4454f` |
| `verify_concurrency_study.py` | `add37e31e08ad72188a5a6081522e9359124a5ea16669966501425cd847a7632` |
| `test_concurrency_study.py` | `09c9e3e8334bbf358603de5228d55be39a6e4c324f9090f9fc35d2b441f04407` |
| `results/concurrency_study.json` | `9ffaa057d7a8e3f73a908f1c4933f13404890331d6e4c112793e0aac86a1c232` |

## Threat model and limitations

This is a deterministic demonstration of a real shared-state race in one
concrete source revision. It shows that using different LangGraph thread IDs
does not isolate the factory's tracker. It does not establish that every
concurrent schedule is faulty, quantify production frequency, or prove the
same behavior in later source versions. It also does not change upstream code,
prove compiler properties, or report a security vulnerability in the project's
stated redaction/approval boundary.

The observer is exact model system/user/response strings, source-estimated
`NodeCost` rows, pending/approved status, and the forced event schedule. Raw
incident text is retained in the source graph/checkpoint; checkpoint privacy is
outside this study. The model is the pinned offline mock, not an online
provider, and the cost values are source estimates rather than provider
charges. The race schedule is controlled evidence, not a general concurrency
model-checking result.
