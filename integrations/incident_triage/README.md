# Pinned incident-triage source study

This study executes the **unmodified** MIT-licensed LangGraph repository
[`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
at commit `c08f710acfeefe233329df613fe8358eaac5f350`. It runs the repository's
own deterministic `MockLLM` through both its default `build_graph()` factory
(`TRIAGE_LLM=mock`) and the supported `build_graph(llm=...)` injection point.
The upstream
`redact_pii`, `call_with_repair`, graph nodes/routes, `TrackingLLM`,
`CostTracker`, registry enrichment, priority computation, and pre-dispatch
interrupt all execute from that checkout.

The harness does **not** translate this source to OrchLang, rewrite its graph,
or call an online model. The source input and dependency lock are hash-bound
before import and the source hashes are rechecked after all runs. Graph
execution blocks socket connection/send/DNS methods and process creation. A
separate verifier independently reconstructs source redaction, checks exact
classifier/repair/draft request templates, validates source token-estimate
arithmetic and event accounting, and recomputes listed pair comparisons. It
does not independently execute LangGraph or prove the upstream policy.

## Reproduce

The tested runtime was Python 3.14.6, LangGraph 1.2.14, and Pydantic 2.14.0.
The exact resolved Python dependency set is in [`requirements.lock`](requirements.lock).
The harness itself uses only the pinned source's offline mock; it never
instantiates the optional OpenAI client.

Fetch the exact source revision once, then run the local study without a
provider key or runtime network access:

```sh
git clone --no-checkout https://github.com/codewithkachi/agent-incident-triage.git /tmp/incident-triage-upstream
git -C /tmp/incident-triage-upstream checkout --detach c08f710acfeefe233329df613fe8358eaac5f350

python3 -m venv integrations/incident_triage/.venv
integrations/incident_triage/.venv/bin/python -m pip install -r integrations/incident_triage/requirements.lock

INCIDENT_TRIAGE_UPSTREAM=/tmp/incident-triage-upstream \
  integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/run_study.py

integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/verify_results.py

INCIDENT_TRIAGE_UPSTREAM=/tmp/incident-triage-upstream \
  integrations/incident_triage/.venv/bin/python \
  -m unittest discover -s integrations/incident_triage -p 'test_*.py' -v
```

The runner refuses any commit, tree, file hash, or worktree status that differs
from [`UPSTREAM_MANIFEST.json`](UPSTREAM_MANIFEST.json). The generated report
is [`results/source_study.json`](results/source_study.json).

## Fixed study cases

The runner executes 22 input cases through the source graph. Each run uses a
fresh graph/checkpointer and a fixed thread ID. Three value-substitution pairs
vary only a matched email, phone, or National Insurance-shaped value; each pair
retains identical redacted text. A second email pair exercises the source
repair branch by injecting exactly one fixed invalid classification response.
Three additional pairs distinguish PII presence, occurrence count, and pattern
type; these are expected to change the redacted skeleton and exact request.
Other controls change ordinary incident text, a name-like string outside the
listed patterns, or add a redacted email to neutral text. One unknown-site run
follows the source error route to `human_review`. An additional run uses the
upstream default mock factory on the same input as an injected-wrapper run.

For every model call, the wrapper stores exact system prompt, user prompt, and
mock response. The final graph state supplies the real source-generated usage
rows. An independent arithmetic check recomputes the upstream estimate
`max(1, len(system + user) // 4)` and the matching output estimate for each
recorded call. These are the repository's character-based estimates and
zero-priced mock rows, not provider token counts or currency charges.

The pinned mock considers the request text, not a random seed. Matching request
strings therefore produce identical mock responses in these paired runs. This
is deterministic source execution evidence, not an experiment over a
probabilistic shared oracle.

## Observed result

The result contains 22 direct LangGraph runs, 45 model calls, 45 source usage
rows, and 87 source node invocations. All three value-substitution pairs and
the injected-retry email pair have identical ordered request/response, usage,
node-event, and terminal projections. Presence, count, and type changes yield
different exact redacted requests. The default-factory run matches its
injected-wrapper counterpart. The public-content and unlisted-name pairs
differ. The unknown-site case runs `classify → enrich → human_review` and does
not run the draft node. A source-specific mock behavior is also recorded: the source
redactor emits `[EMAIL]`, while the mock classifies by substring and includes
`email` as a cyber keyword; on neutral text that marker changes the mock's
classification to `cyber`. This is expressly a mock artifact, not a statement
about real providers.

## Scope

The upstream README documents redaction for emails, UK phone numbers, and
National Insurance numbers before model input. The study only checks the
listed source patterns using synthetic values. It does not establish that the
patterns cover general PII. It also does not check checkpoint privacy: the
source graph retains the original `incident` object in state and uses
`MemorySaver`; only the model-call projection is compared here.

The result is finite and tied to the pinned source, exact fixtures, injected
mock, LangGraph/Pydantic versions, and this harness. It is not a deployed
provider guarantee, an all-input proof, a full OrchLang translation, or a
finding that the upstream project violates its stated boundary.
