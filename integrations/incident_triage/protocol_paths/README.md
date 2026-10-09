# Incident triage source protocol path coverage

This study runs six explicitly authored response schedules through the
unchanged, MIT-licensed incident-triage source at commit
`c08f710acfeefe233329df613fe8358eaac5f350`. Each schedule is run twice with
synthetic email values that redact to the same source request. A fresh graph
and in-memory checkpointer are created for every run.

The covered paths are:

| Path | Source behavior exercised |
|---|---|
| `repair_success` | Malformed first classifier response, source-derived repair prompt, valid repair, draft, interrupt before dispatch |
| `double_schema_failure` | Malformed initial and repair responses, error route to human review |
| `long_summary` | Valid 295-character `Classification.summary` accepted by the 300-character schema and included in the draft request |
| `draft_json_fallback` | Malformed draft JSON selects the source fallback action |
| `critical_site_bump` | Low-severity/no-risk classification is raised from P4 to P3 for the critical site |
| `budget_guard` | 400,000 leading spaces in a valid classification response count toward the source estimator and stop before the draft call |

The local `FixedOutcomeOracle` implements only `complete(system, user)` and
returns the fixed responses in the checked report schema. It does not create a
provider client or use a network service. Runtime wrappers call the original
`CostTracker.__init__` and `TrackingLLM.complete` methods and then snapshot the
tracker entries. That captures the two schema-failure rows even though the
source classifier returns an error update without a `costs` field. No source
file is changed; the harness checks all 23 tracked source hashes before and
after execution.

The independent verifier uses only the Python standard library. It imports
neither this runner nor the source application, LangGraph, or Pydantic. It
reconstructs the classifier and repair requests, fixed complete outcomes,
draft request, selected routes and updates, tracker rows, source estimator,
configured nominal pricing, and pair projections. It independently parses
the report and checks the complete clean Git checkout and all 23 file hashes.

The 400,000-space response is a synthetic input to the offline oracle. Its
reported usage and approximately `$0.060033` source estimate exercise the
source's configured `gpt-4o-mini` arithmetic and `$0.05` guard only. No money
is spent, and this is not evidence of provider tokenization or billing. The
response is compactly recorded as a leading-space count, suffix, character
count, and SHA-256; the verifier reconstructs it from its own fixed fixture.

## Reproduce

The bundled source archive allows an offline checkout without changing the
upstream files. The execution runner needs the pinned LangGraph/Pydantic
environment from `integrations/incident_triage/.venv`; the independent
verifier and tests need only Python's standard library.

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

The committed study was generated with Python 3.14.6, LangGraph 1.2.14, and
Pydantic 2.14.0. The standard-library verifier and focused tests also pass
under Python 3.12.14.

## Scope

The six pairs cover selected, controlled source paths; they do not establish
universal path coverage or source-wide semantics. The oracle outcomes are
authored fixtures rather than model outputs. The trace projection covers
requests, source usage rows, selected state updates, terminal classification,
priority, actions and route, plus the pre-dispatch interrupt. Raw incident
text remains in the LangGraph state and checkpoint, and the human-review node
returns that state. This study makes no full-state privacy, real-provider,
actual-billing, dispatch, or user-population claim.
