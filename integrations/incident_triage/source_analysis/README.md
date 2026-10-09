# Incident triage source-linked analysis

This adapter recognizes one pinned Python/LangGraph project and derives its
pre-dispatch request dependency contract from Python ASTs. The accepted source
family is deliberately narrow: selected helper bodies must match fixed
normalized-AST fingerprints, and every required field, branch, template,
estimator, and route is checked. This is not a general Python information-flow
analyzer or a generic LangGraph-to-OrchGraph translator.

The pinned source is the MIT-licensed
[`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
at commit `c08f710acfeefe233329df613fe8358eaac5f350`, tree
`2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`. The complete 23-file source
snapshot is checked in at `integrations/incident_triage/upstream_snapshot/`;
the original source manifest and license are retained. The source report binds
seven directly analyzed source/asset files, while bridge generation verifies
every tracked snapshot file against the upstream manifest.

## What the bridge checks

The source relation is exact equality after the ordered upstream helper:

```text
redact_pii(text_left) == redact_pii(text_right)
```

It also requires valid `IncidentReport` values and equal
`incident_id`, `site`, `reported_by`, and graph thread ID. It derives and
records the full request/control dependency chain through the interrupt before
dispatch:

- The initial classifier system and user strings, including the exact prefix
  and `redact_pii(incident.text)` expression.
- All four typed `Classification` fields. The arbitrary validated `summary`
  string remains an explicit dependency of the later draft prompt. The source
  prompt says 280 characters while the Pydantic schema permits 300; that
  mismatch is preserved.
- `parse_structured` behavior and the exact one-repair request, including the
  error text returned by Pydantic validation. The second schema failure routes
  to human review; its call rows must be read from the tracker/wrapper because
  the node result omits `costs`.
- Site registry enrichment, the priority matrix and critical-site bump, the
  draft system/user prompt, and the pre-dispatch human gate.
- The source's exact usage and budget arithmetic:
  `max(1, len(system + user) // 4)`, `max(1, len(response) // 4)`, rounded
  Python-float per-call cost, rounded running total, and the strict
  `total > $0.05` check before drafting.
  These use Python character counts and configured nominal prices. They are
  not provider token counts or actual billing.
- The shared complete-outcome oracle premise and the requirement for a fresh
  graph/checkpointer and serialized invocation. A compiled graph closes over
  mutable tracker state, and `classify` clears that state.

The source makes at most three model completions before the gate: one
classifier response, one optional repair response, and one action-draft
response. Schema, site, or budget errors can stop earlier.

An OrchGraph self-composition certificate is generated only for the first
classifier request pair. Its two branches receive one equal public
`classifier_user_message` and send the source-derived system template plus
that message. The source AST contract establishes how that message relates to
the two valid inputs; the regex sanitizer itself is not represented as an
OrchGraph primitive. Therefore the graph certificate alone is not a proof of
the entire upstream workflow.

The independent source replayer re-reads and parses the pinned source, rebuilds
the dependency contract, checks the source study projections and authored
mutation obligations, then independently replays the classifier graph
certificate. It does not import or execute the bridge or upstream application.
It verifies a source-specific conditional argument, not a mechanized proof of
Python or Pydantic semantics.

## Reproduce

The checked-in snapshot can be analyzed without a clone, network, or external
provider. Python 3.12 or later is needed to parse the pinned source's generic
function syntax. The normalized AST fingerprints omit empty optional fields
that vary between Python releases; bridge generation and independent replay
were verified under Python 3.12.11, 3.12.14, and 3.14.6. The finite source
execution study used Python 3.14.6, LangGraph 1.2.14, and Pydantic 2.14.0;
its dependency lock is hash-bound in the report. The source-analysis bridge
and replayer themselves use the Python standard library plus the repository's
standard-library OrchGraph checker.

```sh
python3 integrations/incident_triage/source_analysis/bridge.py \
  --upstream integrations/incident_triage/upstream_snapshot \
  --study integrations/incident_triage/results/source_study.json \
  --output-dir integrations/incident_triage/source_analysis/artifacts

python3 integrations/incident_triage/source_analysis/replay_projection.py \
  integrations/incident_triage/source_analysis/artifacts/source_analysis.json \
  integrations/incident_triage/upstream_snapshot \
  --study integrations/incident_triage/results/source_study.json

python3 -m unittest integrations.incident_triage.source_analysis.test_source_analysis -v
```

`bridge.py` also accepts a clean exact upstream Git worktree with `--upstream`.
For a source checkout, it checks commit, tree, tracked-file state, and all
manifest file hashes. For a snapshot, it verifies every manifest-listed file.
The independent replay takes its source root as a positional argument and
checks the seven bound source/asset files without requiring Git.

## Evidence and limits

The frozen source study contains 22 actual runs, 45 model calls, 45 source
usage rows, and 87 node events. Independent AST projection checking covers 11
listed pairs: five have equal exact redacted text and first classifier
requests; six differ. The study uses only the pinned deterministic mock and
does not establish online provider behavior. Three authored source mutations
that add raw text to classifier, repair, or draft requests are rejected by
separate AST dependency obligations. They are adapter tests, not upstream
vulnerabilities.

The relation protects matched values only when the entire redacted text is
equal. It does not protect PII marker presence, count, pattern type, unmatched
sensitive text, or raw incident storage. The original incident remains in
LangGraph state and its memory checkpoint, and `human_review` returns that
state. Invalid Pydantic inputs, concurrent use of one compiled graph, provider
errors, the human decision, and dispatch effects are outside the claim.

The source estimator differs from OrchGraph's UTF-8 byte-based accounting.
The source has no output cap or provider usage receipt in its wrapper. The
protocol preserves the source estimator and budget branch for the conditional
dependency argument, but it makes no source billing-conformance or provider
usage claim. The pinned graph proof is a classifier request slice; later
source operations are checked through exact source-specific dependencies, not
lowered into a second full LangGraph model.
