# Pinned incident-triage protocol path coverage

This is a separate source-execution study for selected paths that were absent
from the earlier 22-run incident-triage corpus. It exercises the unmodified
MIT upstream checkout at commit `c08f710acfeefe233329df613fe8358eaac5f350`
with six locally authored response schedules. Each schedule is run twice,
changing only a synthetic email value that the source redactor maps to the
same `[EMAIL]` string. The runner creates a fresh graph and in-memory
checkpointer for each of the 12 executions.

## Covered paths and results

| Path | Observed source behavior |
|---|---|
| Repair success | Malformed initial response, exact repair prompt derived from the JSON parse error, valid classification, draft, interrupt before dispatch |
| Double schema failure | Both classification responses fail parsing; source routes to human review |
| Long summary | 295-character summary passes the 300-character Pydantic field limit and appears in the later draft request, despite the classifier prompt's 280-character wording |
| Draft fallback | Malformed draft JSON selects the source's manual-review fallback action |
| Critical-site bump | Low severity with no people at risk would be P4 at a standard site; critical-site policy moves it to P3 with a 240-minute SLA |
| Budget guard | A valid classification response with 400,000 leading spaces is parsed after `.strip()` but counted by source usage before drafting |

Across the six pairs the study recorded 24 model-interface calls, 24 original
tracker rows, 20 cost rows present in returned node state, 46 node update
events, and 8 pre-dispatch interrupt events. The four calls in the two
double-failure runs remain visible in the tracker wrapper even though the
terminal classifier update contains no `costs` field. All six paired selected
observations are equal: redacted text, exact requests and fixed responses,
tracker rows, node events, and terminal projections.

The budget fixture response is 400,125 characters. Under the pinned source
estimator it records 99 input tokens and 100,031 output tokens; the configured
nominal `gpt-4o-mini` price yields a rounded `$0.060033` row, above the `$0.05`
source guard. This is artificial offline path coverage only. No provider is
constructed, no external call occurs, and no money is spent.

## Independent replay and provenance

[`run_protocol_paths.py`](../integrations/incident_triage/protocol_paths/run_protocol_paths.py)
executes the source graph with a fixed local `complete(system, user)` oracle.
Its wrappers delegate to the original `CostTracker.__init__` and
`TrackingLLM.complete` implementations before copying tracker entries. The
runner checks the commit, tree, clean status, full 23-file manifest, and every
tracked-file hash before and after the executions. The before/after maps are
identical.

[`verify_protocol_paths.py`](../integrations/incident_triage/protocol_paths/verify_protocol_paths.py)
is an independent standard-library checker. It does not import the runner,
upstream Python package, LangGraph, or Pydantic. It reconstructs the fixed
responses and request strings (including the retry suffix), node routes,
terminal fields, full tracker rows, source estimator, configured pricing, and
pair comparisons. It separately checks the clean source checkout and all 23
file hashes. The saved attestation records nine checks; it attests this
fixed-fixture replay, not general program semantics.

Reproduce with the bundled source archive and the pinned execution
environment:

```sh
git clone integrations/incident_triage/upstream_c08f710.bundle /tmp/incident-triage-offline-clone
integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/protocol_paths/run_protocol_paths.py \
  --upstream /tmp/incident-triage-offline-clone
integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/protocol_paths/verify_protocol_paths.py \
  integrations/incident_triage/protocol_paths/results/protocol_paths.json \
  /tmp/incident-triage-offline-clone \
  --attestation integrations/incident_triage/protocol_paths/results/protocol_paths.attestation.json
INCIDENT_TRIAGE_UPSTREAM=/tmp/incident-triage-offline-clone \
  integrations/incident_triage/.venv/bin/python -m unittest discover \
  -s integrations/incident_triage/protocol_paths -p 'test_*.py' -v
```

The report was generated with Python 3.14.6, LangGraph 1.2.14, and Pydantic
2.14.0. The standard-library verifier and all 10 focused tests also pass with
Python 3.12.14. The report is 52,958 bytes. Its SHA-256 is
`e2abae3d5a44c034e476646ca332e6d5a119f47097cbf9e5bbd3e5ec5f29113b`.
The saved replay attestation is in
[`protocol_paths.attestation.json`](../integrations/incident_triage/protocol_paths/results/protocol_paths.attestation.json).

## Limits

The cases are authored fixtures, not external user workflows or incident
frequency evidence. They cover only the named paths and synthetic input
skeleton. The selected observer contains requests, source usage, node updates,
terminal classification/priority/actions and pre-dispatch interrupts. It does
not provide full-state privacy: raw incident text remains in graph state and
checkpoint, and `human_review` returns that state. No universal path-coverage,
provider behavior, real billing, dispatch, or concurrency claim follows.
