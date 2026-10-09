# Incident triage tracker concurrency study

This study executes the unchanged pinned LangGraph source from
[`../UPSTREAM_MANIFEST.json`](../UPSTREAM_MANIFEST.json). It deterministically
interleaves two synthetic incidents through **one** `build_graph()` instance,
then compares the result with one graph instance per incident. The wrapper
delegates every response to the upstream offline `MockLLM`; it pauses only
after incident A's classification response exists and before the wrapper
returns it to `TrackingLLM.complete`. No upstream Python file is modified, no
provider client is instantiated, and network/process operations are blocked
during graph calls and approvals.

## Run and verify

From the project root, use the source study's locked environment and verified
checkout:

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

The generated witness is
[`results/concurrency_study.json`](results/concurrency_study.json). The runner
checks commit, Git tree, clean worktree, tracked file set, every tracked source
hash, and license before importing the upstream package; it repeats these
checks after execution. The independent verifier recomputes the exact prompts,
source token estimates, row order, contamination, and per-ID approval facts. It
does not import or execute upstream code.

## Observed behavior

The fixed schedule pauses A after the pinned mock has produced its classifier
response. B then completes classification and drafting on the same graph. When
A resumes, the shared `TrackingLLM.current_node` is still `"draft"`; its
classification cost row is therefore recorded as a draft row. B's two tracker
rows are also present in A's returned `state["costs"]` snapshot. Under this
schedule, B returns two rows and A returns four for its two own calls.

The isolation control creates one unchanged source graph/tracker/checkpointer
per incident and executes both apps concurrently. Each pending state has only
its own classifier and draft rows with the correct node names. Each app is
retained by incident ID and can resume its own pending thread through the
source `approve()` function; that continuation dispatches without another
model call.

The source estimator reports 456 units across the four unique shared-app model
calls. A's returned snapshot contains B's 231 units, so adding the A and B
snapshots gives 687 units. The isolated snapshots contain 225 for A and 231
for B, with no duplicate rows. The pinned mock's configured price is zero;
these are source-estimated token units, not dollar charges.

## Scope

The result demonstrates one real race in the pinned source's graph factory:
`build_graph()` closes over one `CostTracker` and one `TrackingLLM`; classifier
entry clears shared entries, while each node mutates `current_node`. This is a
controlled source deployment/isolation finding. The per-invocation graph is a
mitigation demonstrated by direct source execution; it is not an upstream
patch or a general concurrency proof.

The selected observer is exact model request/response strings, source
`NodeCost` rows, pending/approved status, and the deterministic wrapper event
order. The mock's source estimator is `max(1, len(text) // 4)` and its price is
zero. The study does not establish provider token counts or charges. It does
not inspect or protect checkpoint privacy: raw incident text remains in
LangGraph state and is persisted by the checkpointer. The reports use only
synthetic non-PII text.
