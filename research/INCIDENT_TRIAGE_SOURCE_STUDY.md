# Direct source study: MIT LangGraph incident triage

**Status:** completed finite source execution study; no compiler translation or provider claim.

## Summary

The pinned MIT project [`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage/tree/c08f710acfeefe233329df613fe8358eaac5f350) provides a real source-level PII-to-model path: `classify` reads a nested incident text value, applies the repository's `redact_pii`, sends a formatted request to a model wrapper, and can make one schema-repair call. The graph then enriches, computes policy priority, drafts actions, and stops at a human approval interrupt. The README documents redaction for email, UK phone, and National Insurance patterns before model input, plus cost tracking and human approval.

I executed the exact clean upstream checkout through its own `build_graph` function and LangGraph runtime. The only injected component was an instrumented wrapper around the repository's own deterministic `MockLLM`; one retry experiment returned a fixed malformed response once and then delegated to that same mock. The source redactor, nodes, graph routes, retry helper, usage tracker, priority logic, and interrupt were not reimplemented or replaced. No provider key or external model call was used.

Across 22 actual graph runs, the harness captured 45 exact model calls, 45 upstream cost/usage rows, and 87 source node invocations. Three pairs changing only one source-listed synthetic PII value produced identical complete request/response traces, reported usage rows, node events, and terminal projections. The same held when the classification call retried once. Separate PII-presence, occurrence-count, and pattern-type pairs produced different redacted prompts, as the source preserves those structural distinctions. The source-shaped unknown-site case went to `human_review` after `classify` and `enrich`, with no draft call. A run through the upstream default mock factory matched the injected-wrapper run on identical input.

This is a small authored open-source demo with a mock-first test setup. The result adds source-grounded execution evidence beyond authored OrchLang programs, but it does not establish a general security theorem, an upstream vulnerability, or a real-provider guarantee.

## Pinned source and custody

- Repository: [`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
- Revision: [`c08f710acfeefe233329df613fe8358eaac5f350`](https://github.com/codewithkachi/agent-incident-triage/tree/c08f710acfeefe233329df613fe8358eaac5f350)
- Git tree: `2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`
- License: MIT, verified in the pinned [`LICENSE`](https://github.com/codewithkachi/agent-incident-triage/blob/c08f710acfeefe233329df613fe8358eaac5f350/LICENSE)
- Tracked file count: 23; byte SHA-256 values for every tracked file are bound in [`UPSTREAM_MANIFEST.json`](../integrations/incident_triage/UPSTREAM_MANIFEST.json).
- Important source file hashes: `graph.py` `0fc931ff7edb64cc26d9eb8b7aa8ec3b05bcefbb667641a30610456ddde4138b`; `guardrails.py` `94d086fb139eff7c7b3bf7ca0b49055c4a7b0a13509913ca855fb6a04a110b5d`; `costs.py` `f1393f1ceada49308d689b47ed736fb864a872ca31bc6bbe7e84265be288d92f`; `llm.py` `2a92f378b51921e312b678ad3aab5a6d7aadd5a7f96d5cc641488e7833ce710a`.

The runner verifies the detached commit, git tree, clean worktree, tracked path set, every tracked file hash, and MIT license marker before import, then repeats those checks after all graph executions. It imports directly from the verified upstream `src/` directory. It does not copy, edit, or translate upstream source.

## Source path and stated boundary

[`src/triage/graph.py`](https://github.com/codewithkachi/agent-incident-triage/blob/c08f710acfeefe233329df613fe8358eaac5f350/src/triage/graph.py) defines `TriageState` and constructs a LangGraph `StateGraph`. In its `classify` node, it validates the incoming `IncidentReport`, runs `redact_pii(incident.text)`, and passes the cleaned string into `call_with_repair` (`graph.py`, lines 66–82). [`guardrails.py`](https://github.com/codewithkachi/agent-incident-triage/blob/c08f710acfeefe233329df613fe8358eaac5f350/src/triage/guardrails.py) defines the three regular-expression substitutions: email to `[EMAIL]`, phone to `[PHONE]`, and NI-shaped value to `[NI-NUMBER]` (lines 16–24). Its `call_with_repair` makes one retry with the schema error included in the repair request (lines 42–53).

After classification, the source performs deterministic site-registry enrichment and policy-priority computation. `draft` formats the generated summary and priority into a second model request, tracks usage, and returns a report. Error routes lead to `human_review`; the graph compiles with `interrupt_before=["dispatch"]` (`graph.py`, lines 83–172). [`costs.py`](https://github.com/codewithkachi/agent-incident-triage/blob/c08f710acfeefe233329df613fe8358eaac5f350/src/triage/costs.py) records each call with `estimate_tokens(text) = max(1, len(text) // 4)`, and estimates input from concatenated system and user strings. [`llm.py`](https://github.com/codewithkachi/agent-incident-triage/blob/c08f710acfeefe233329df613fe8358eaac5f350/src/triage/llm.py) contains the default deterministic rule-based mock. These are source-side character heuristics and a deterministic mock; they are not provider token reports or provider behavior.

The README's boundary is specifically that its three listed identifier classes are redacted before model input. It does not promise to scrub all PII or all sinks. The graph retains the original `incident` object in state and uses `MemorySaver`; this study compares model-call projections and makes no checkpoint/storage confidentiality claim.

## Execution and instrumentation

Study code is in [`integrations/incident_triage/`](../integrations/incident_triage/):

- [`run_study.py`](../integrations/incident_triage/run_study.py) checks the source pin and loads its real `triage.graph`, `triage.guardrails`, `triage.llm`, and `triage.costs` modules. It constructs the graph through the source's `build_graph(llm=...)` API and consumes `app.stream(..., stream_mode="updates")`.
- `RecordingMock` delegates to upstream `MockLLM.complete` and records exact system prompt, user prompt, and response strings. One additional run calls `build_graph()` without an injected model while `TRIAGE_LLM=mock`; a scoped method wrapper captures requests while calling the original upstream `MockLLM.complete` body. LangGraph node update names and the pre-dispatch interrupt are captured. The final state contains the actual source `NodeCost` rows, aligned with the recorded calls and checked against the source estimate formula. The harness blocks socket connect/send methods, `socket.create_connection`, `socket.getaddrinfo`, and process-creation APIs during each graph run; it aborts if any guarded operation is attempted.
- The retry pair injects one fixed non-JSON response for the first classification call, then delegates to the pinned mock. It exercises the upstream `call_with_repair` code without changing the source graph or retry helper.
- [`verify_results.py`](../integrations/incident_triage/verify_results.py) is a separate verifier. It does not import or rerun upstream code. It independently applies the three pinned regex substitutions to every raw input, checks exact classifier, repair, and draft templates, reconstructs each source usage estimate, verifies call-to-cost-row ordering, and checks pair projections and fixed corpus fields. This is a separate artifact check, not an independent LangGraph semantics implementation.
- [`test_study.py`](../integrations/incident_triage/test_study.py) has 12 standard-library tests, including tampered-cost, prompt, and redaction rejection.

The test environment used Python 3.14.6, LangGraph 1.2.14, and Pydantic 2.14.0. Exact resolved dependencies and output hashes are recorded in `integrations/incident_triage/requirements.lock` and the result JSON. Upstream's own broad dependency ranges remain unchanged.

## Input pairs and observations

For each of the email, phone, and NI value-substitution experiments, two synthetic incident strings differ in exactly one matching value. Site, incident ID, reporter, thread ID, and all non-PII text are fixed within each pair. The inputs use reserved/example-shaped data only. Values include `person@example.invalid` versus a longer `.invalid` email, two pattern-matched phone strings, and `QQ 12 34 56 C` versus `ZZ987654Z`. The phone values `07700 900123` and `0113 496 0999` fall in number ranges Ofcom lists for TV/radio drama use ([Ofcom ranges](https://www.ofcom.org.uk/phones-and-broadband/phone-numbers/numbers-for-drama), checked 2026-10-09).

For all three value pairs, upstream redaction produced the same full sanitized incident text. Both actual model requests then matched exactly, including the second request formed from the classification summary. The deterministic mock responses, source usage rows, node sequences, and pending-approval report projections also matched. Each normal value pair had two calls, with identical classification and drafting usage estimates (112/54 and 86/26 tokens respectively under the source's `len // 4` estimator).

Three additional pairs test the distinction between replacing a value and changing redaction structure. Removing an email changes marker presence; adding a second email changes marker count; substituting a phone for an email changes marker type (`[PHONE]` versus `[EMAIL]`). Each change produces a different source-redacted classifier request. These are intentionally reported as different requests, not as failures of value-substitution equality. The report also includes one source-default `build_graph()` execution; its exact prompts, response strings, source usage rows, node events, and terminal projection match the injected-wrapper run on the same incident and thread.

For the retry pair, the malformed first classification response caused the real helper to produce a second request containing the same source-generated validation error for both email variants. Each run made three calls in order: classify, classify-repair, draft. All three exact call strings/responses and usage rows matched across the pair.

Three contrasts check that the harness observes changes instead of blindly normalizing every input:

- The ordinary text mutation changed the mock classification from `physical_security` / low / P4 to `cyber` / critical / P1 and changed the second request.
- Name-like strings outside the README's listed regex categories remained in the first model prompt and yielded different exact prompts/summaries. This is outside the stated three-pattern coverage; it is not reported as a violation of the documented limited promise.
- A mock-only negative control found that `[EMAIL]` itself contains the mock's keyword `email`. Adding a redacted email to neutral text changes this simplistic mock classification from `operational` to `cyber`. This documents a behavior of the pinned mock, not a finding about LLM providers.

For the invalid-site case, LangGraph actually ran `classify → enrich → human_review`; no `draft` call or dispatch occurred. Ordinary successful cases ran `classify → enrich → prioritise → draft` and stopped at the configured interrupt before `dispatch`.

Full input, request, response, usage, event, and result rows for all 22 executions are in [`results/source_study.json`](../integrations/incident_triage/results/source_study.json). The report explicitly marks the listed-pattern, deterministic-mock, finite-case, and storage-scope limits.

## Reproduction and checks

From the repository root, after fetching the pinned upstream checkout:

```sh
INCIDENT_TRIAGE_UPSTREAM=/path/to/agent-incident-triage \
  integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/run_study.py

integrations/incident_triage/.venv/bin/python \
  integrations/incident_triage/verify_results.py

INCIDENT_TRIAGE_UPSTREAM=/path/to/agent-incident-triage \
  integrations/incident_triage/.venv/bin/python \
  -m unittest discover -s integrations/incident_triage -p 'test_*.py' -v
```

Observed checks:

- Runner: 22 cases, 45 calls, pinned commit `c08f710acfeefe233329df613fe8358eaac5f350`.
- Independent artifact verifier: `verified`, 22 cases, 45 calls, 87 source node invocations; three equal PII value pairs, one equal repair pair, three different PII-shape pairs, three different public/mock controls, and one equal default-factory pair.
- Unit tests: 12 passed. One deprecation warning comes from the installed LangSmith dependency on Python 3.14; it does not affect the result.
- Result: 95,843 bytes, SHA-256 `3f10906bb8fdd2283c59b188863304ecb2431c662ca0be3c0a04aaadfa05e9ab`. The run corpus SHA-256 is `dbd784dcec978e4e6160d7664e96a741a8546a1bb5587fdf32bc7aed46a7457a`. Bound harness hashes: runner `f13bdebb6d2442802ae9ed0663e1d05ee1a014fd9a3e69222a078cacb281e399`, verifier `3fe4dae778e4ef411b42e97a5f205891b3171288dac8180c292a3ad1adbe467a`, tests `d0eb09bc5f94a57c622db5aeca0c78ae58b4c0dde87b6892a1a9b37979e55001`, source manifest `38e804b6470ad0c58f0da526f71ab39b7a7ad5a4a241c0e156569ba0ad203500`, dependency lock `b9599a3084f6b8f47aea39da6f04e1808296a3371b58f8ae5d39ca827154ca6b`. The verifier rejects if its bound local files differ.

## Interpretation limits

This is direct execution of one fixed upstream revision under one selected current LangGraph/Pydantic environment and a deterministic source mock. The injected one-failure retry is a controlled probe, not a characterization of every provider error. The sample values are synthetic; the output usage fields are the source's rough character-based estimates, with zero mock price. The observer records model request/response strings, cost rows, node events, and a selected terminal projection. It does not assert equality of every field in graph state, including the retained original incident, or other runtime metadata. Identical recorded mock traces on selected pairs do not establish all-input noninterference, that regex redaction covers general identifiers, that raw state is protected in storage, or that real models/providers have matching behavior. The study is not a translation through the frozen source frontend and makes no claim about generic source-to-graph correctness.
