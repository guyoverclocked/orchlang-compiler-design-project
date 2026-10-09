# Source-linked analysis of the incident-triage workflow

## Result

The new adapter extracts a source-specific request and control dependency
protocol from the pinned LangGraph program and independently replays its
bindings. Under the stated premises, it supports this conditional result:

> For two valid incidents with equal `incident_id`, `site`, `reported_by`,
> and thread ID, if their exact ordered `redact_pii` outputs are equal, their
> configuration/assets/provider contract is fixed, each run uses a fresh
> serialized graph and checkpointer, and a shared complete outcome oracle
> couples matching model requests and call ordinals, then their model request,
> source-estimated usage, error-route, node, and interrupt observations through
> the pre-dispatch gate are equal.

This is a conditional argument for one source version. The bridge recognizes
exact helper AST fingerprints and independently rebuilds the serialized
contract; it does not prove arbitrary Python semantics. The OrchGraph
certificate covers only the first classifier request pair. The later request,
usage, and control dependencies are checked by the source-specific protocol,
not by a full workflow graph proof.

The report supports a compiler-linked case study and an auditable artifact. It
does not establish a new general information-flow theorem or a broad
Python-to-LangGraph translation result. Sanitizer adequacy remains a trusted
release premise. Source slicing, exception-aware dependencies, and
declassification are established topics; this result should be presented as a
pinned-project integration and exact dependency check, not as a new general
method.

## Source and evidence

The analyzed source is the MIT-licensed
[`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
repository at commit `c08f710acfeefe233329df613fe8358eaac5f350`, tree
`2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`. The exact 23-file snapshot and
original license are retained under
[`integrations/incident_triage/upstream_snapshot/`](../integrations/incident_triage/upstream_snapshot/).
The bridge generation path verifies every manifest-listed file. The
independent standard-library replay binds the manifest and the seven files
used directly by the protocol: `graph.py`, `guardrails.py`, `models.py`,
`costs.py`, `config.py`, `llm.py`, and `data/sites.json`.

The actual upstream source study is separate from the adapter. It ran 22
unmodified LangGraph cases, with 45 model calls, 45 source usage rows, and 87
node events. The independent source replay re-computes the first-request
projection for all 22 cases and all 11 listed pairs: five pairs have equal
redacted text and classifier requests; six differ. Those counts are finite
observations from the pinned deterministic mock. The mock has no online
provider or network calls.

The adapter emits one self-composition graph for the exact first classifier
request. Both branches receive the same public
`classifier_user_message` and use the extracted source system string. The
independent cyclic certificate replay reports 11 product nodes and 10 edges.
The AST contract connects the source relation to that graph input; the regex
implementation itself is not a graph primitive. The synthetic Boolean branch
selector exists only to construct the analysis product.

The protocol retains the request path beyond classification:

1. `IncidentReport.model_validate` checks the four input fields and the
   10–4000 character text bound before the classifier's schema-error handler.
2. `redact_pii` applies the exact ordered email, phone, and National
   Insurance substitutions. The classifier user message is the literal prefix
   `INCIDENT REPORT: ` followed by that result.
3. `Classification` keeps its literal category and severity choices, Boolean
   risk field, and arbitrary summary string up to 300 characters. The
   classifier prompt says 280; the adapter preserves this source mismatch.
   The full `summary` value is included in the later draft prompt.
4. `parse_structured` strips the response, removes the pinned Markdown fence
   when present, parses JSON, and validates the Pydantic schema. One failed
   response generates the exact repair prompt with the original user string
   and validation error. A second schema failure returns an error and routes
   to human review. The tracker/wrapper, rather than the returned error state,
   supplies the call rows on this path.
5. The site registry determines enrichment from the equal public `site` and
   the model's category. Unknown sites route to human review. Priority uses
   the exact severity/risk matrix and the registry's critical-site adjustment.
6. Before draft, the source checks its running budget. If allowed, it uses the
   fixed action system prompt and exact category/priority/summary template.
   The workflow interrupts before `dispatch`.

There are at most three model completions before the gate: one classifier
response, one optional repair response, and one draft response. Error branches
can stop earlier.

The source usage and cost formula is kept separate from OrchGraph accounting.
The source counts Python Unicode code points with
`max(1, len(system + user) // 4)` and `max(1, len(response) // 4)`, computes a
nominal table-price amount rounded to six decimal places, rounds the running
total, and checks `total > $0.05`. The source study uses the zero-priced mock.
The protocol makes no claim about provider token counts or charges.

The shared outcome premise is keyed by resolved provider/model contract, call
ordinal, and exact system/user strings. Equal outcomes include response text
and any source-observed usage metadata. The pinned source wrapper does not
expose provider usage receipts. For the full pre-dispatch relation, both sides
must share outcomes at the initial classification call, optional repair, and
draft call. The deterministic mock satisfies equal-request coupling for the
captured source study; a live model is not established by temperature or a
matching prompt alone.

## Mutation and concurrency checks

Three **authored** mutations are kept separate from the pinned-source result:

| Mutation | Rejected AST obligation |
|---|---|
| Replace `redact_pii(incident.text)` with `incident.text` in `classify` | The classifier's `clean_text` must be exactly the redactor applied to validated incident text. |
| Add a raw-text argument used only in the repair prompt | `call_with_repair` may accept only system, user, and schema; its retry string may depend only on the original user and `SchemaViolation`. |
| Append `state['incident']['text']` to the draft request | The draft prompt may depend only on classification category, priority level, and classification summary. |

Each probe reports `semantic_AST_dependency_check`; it is not treated as a
manifest/hash rejection. The upstream snapshot is unchanged. These probes are
adapter tests, not findings of an upstream privacy violation.

The source's closure-scoped tracker is mutable: `build_graph` shares its
tracker and `current_node`, and `classify` clears the tracker. A separate
controlled concurrency study reproduced a shared-graph schedule that moved
231 source-estimated units from B's snapshot into A's and labeled A's
classification row as draft. Its four unique calls total 456 units, while
adding per-run snapshots yields 687. Isolated per-incident graphs returned
the correct rows. This is why the source relation requires serialized fresh
graphs/checkpointers. The race study does not show raw PII value leakage and
does not measure a nonzero-price budget effect.

## Limits

The policy is the exact relation `redact_pii(t_left) == redact_pii(t_right)`.
Matched values can differ when this exact output remains equal. Marker
presence, count, and pattern type remain visible in the output and may change
the result; the relation does not protect those changes or sensitive text the
patterns miss. The upstream state and MemorySaver checkpoint retain the raw
incident, and `human_review` returns the full state. Storage/checkpoint
privacy is excluded.

Other exclusions are invalid Pydantic inputs that raise before the route,
concurrent invocations on one graph, provider/network failures, arbitrary
source/config changes, external human decisions, dispatch effects, provider
usage receipts, and provider-side billing. The source has no output cap in the
selected wrapper. The generated graph's required `max_tokens: 1` output cap is
adapter-only and irrelevant to its one-call proof.

The source contract is deliberately conservative. Selected function bodies
must match known AST digests and additional semantic checks reject unknown
dependencies. This prevents silent acceptance of source edits, but means the
accepted family is essentially the pinned program. It is evidence of one
source-linked compiler integration, not an extensible Python frontend.

## Reproduction and artifacts

The extractor and verifier use Python's standard library and the repository's
standard-library graph checker. Python 3.12 or later is required to parse the
source's generic function syntax. The separately executed upstream study is
bound to Python 3.14.6, LangGraph 1.2.14, Pydantic 2.14.0, and the hash-bound
dependency lock.

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

Thirteen source-analysis tests pass, including independent source re-extraction,
graph certificate replay, all three semantic mutation probes, source and
artifact tampering, and finite-case projection checks. The independent replay
attestation has seven checks. The bridge and replayer produce matching helper
fingerprints and matching attestations under Python 3.12.11, 3.12.14, and
3.14.6. The claim remains a source-specific conditional argument.

| Artifact | SHA-256 |
|---|---|
| `source_analysis/bridge.py` | `c0c845f7cef1f74663981a5db96c0f0eb989241b24746cb6708362ad49393fa8` |
| `source_analysis/replay_projection.py` | `4d7917f19810e230e26d7573c5a7cbe8bb74a7649064a5084d89b127bde58175` |
| `source_analysis/test_source_analysis.py` | `9145d19feb779361b757c9f7e338e85ffe5fb336d21e0520d367173058792e8c` |
| `source_analysis/artifacts/source_analysis.json` | `0fd0eaa631ab5deb2da3ac396860271b87cc4eca6be1500f746dee29bfcb262a` |
| `source_analysis/artifacts/source_analysis.attestation.json` | `7d02eb18f68ad409debed23702939945fc86d6c50656eaa4e71ec20cee28b033` |
| `source_analysis/artifacts/classifier_request.graph.json` | `81ffdf3bacbd5e7ad96f76a4757e971e8801996f2d0b716d5aad24353889b282` |
| `source_analysis/artifacts/classifier_request.certificate.json` | `5f8dfbe841c58ee6bfa0d6788a47115992faae8b2beba3ed75b417f61a5850fa` |
| `source_analysis/artifacts/classifier_request.attestation.json` | `6b753260b7f3a2096073ed8bc139021a93dd4a5a5a2f168cfabf74cf61a41f4c` |
| `source_analysis/README.md` | `71127deb5984fb360a02042c74e6cec204fb3bdff1612d82f750fd6998687315` |
