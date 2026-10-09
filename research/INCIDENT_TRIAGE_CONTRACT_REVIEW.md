# Incident triage source: semantic contract for a compiler-linked analysis

**Review scope.** This note checks whether the compiler's shared-oracle request
analysis can be related soundly to the pinned `agent-incident-triage` source.
It is a contract review, not a translation or a claim that the compiler has
proved the upstream program. The reviewed upstream checkout is the MIT-licensed
[`codewithkachi/agent-incident-triage`](https://github.com/codewithkachi/agent-incident-triage)
at commit `c08f710acfeefe233329df613fe8358eaac5f350`, tree
`2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`. The source study binds all tracked
files and has an independent reproduction record in
[`integrations/incident_triage/README.md`](../integrations/incident_triage/README.md).

## Conditional paired-input claim

The following is a source-specific **single-invocation** claim. It concerns
model requests, source-estimated usage/cost rows, node/interrupt events, and the
terminal pre-dispatch route. It does not concern the full LangGraph state,
checkpoint contents, logs, or provider-side billing.

Let `I₀` and `I₁` be valid `IncidentReport` inputs in the pinned Pydantic and
Python environment. Require all public metadata to match exactly:
`incident_id`, `site`, and `reported_by`. Let their text fields be `t₀` and
`t₁`, both within the source's 10–4000 character validation bound, and require
the exact source function to produce equal strings:

```text
redact_pii(t₀) == redact_pii(t₁)
```

Run each input with the same graph source, same `data/sites.json`, same
`config.py` values, resolved model/provider and pricing, same dependency/runtime
semantics, and an isolated tracker/checkpointer with no concurrent invocation.
For the model, require a shared **complete outcome oracle**: at the same
resolved contract and per-contract call ordinal, equal complete requests
(system prompt and user prompt) return equal response text and any usage/cost
metadata included in the selected observation. The source has no request-side
provider usage metadata, so its current cost rows are recomputed from request
and response strings.

Under those conditions, both executions have the same ordered model request
and response strings, source-estimated usage/cost rows, route and pre-dispatch
node/interrupt trace. Their selected terminal projection is also equal. This
is a relational property for the stated pair relation; it is not a claim for
arbitrary changes to a secret incident text.

### Why raw incident text need not align after classification

In `src/triage/graph.py`, `classify` validates the incident and sends only
`"INCIDENT REPORT: " + redact_pii(incident.text)` to `CLASSIFY_SYSTEM` (lines
66–81). Once that exact request has been made, the graph's later nodes do not
read `incident.text`:

* `enrich` revalidates the raw incident but reads only `incident.site` and the
  already-produced classification category (lines 83–96).
* `prioritise` is a deterministic function of the classification's severity,
  risk flag, and the registry's site criticality (lines 98–113).
* `draft` checks the accumulated cost tracker and, when allowed, formats only
  classification category, priority level, and classification summary into
  its request (lines 115–138).
* `dispatch` only changes the report status to approved (lines 140–143).

Thus the two raw texts may differ while the downstream state components that
affect the selected observer remain aligned. This argument depends on the
current source and the metadata equality above. The raw `incident` is still
stored in LangGraph state, the memory checkpointer retains that state, and
`human_review` returns the whole state (lines 145–146). Therefore the claim
does **not** establish storage/checkpoint privacy or equality of the full
returned state. Continuing to approval also requires the same pending thread
and excludes state serialization from the observer.

### Path-by-path argument

1. **Initial classification.** Equal sanitized text and equal fixed system
   prompt give equal complete requests. Under the shared outcome oracle the
   returned string is equal.
2. **Successful parse.** `parse_structured` strips whitespace, optionally
   removes a Markdown fence, parses JSON, and validates the `Classification`
   Pydantic model (`src/triage/guardrails.py:31–39`). Equal response strings
   under the same version produce equal classification values.
3. **One repair attempt.** If the first response fails, `call_with_repair`
   constructs the second user prompt from the original user text and the exact
   `SchemaViolation` text (`guardrails.py:42–53`). Equal original requests and
   responses produce the same parse result/error and hence the same repair
   request. The second outcome is coupled at its corresponding contract
   ordinal. Equal success/failure determines the same next route.
4. **Schema-failure human review.** If the repair also fails, `classify`
   catches `SchemaViolation` and returns an error (`graph.py:72–80`); both
   executions then route to `human_review` (`graph.py:148–151, 162–165`). The
   internal tracker still contains both classification calls, but this error
   return does not include a `costs` field. A request/usage observer must read
   the tracker or instrument model calls; it cannot reconstruct that trace
   from the returned state's `costs` key alone.
5. **Unknown-site human review.** Equal `site` values and equal registry data
   make `enrich` either find the same site and category procedures or return
   the same unknown-site error (`graph.py:83–96`). The unknown-site route runs
   `classify → enrich → human_review` and skips priority and draft.
6. **Normal report path.** Equal classification values and site metadata make
   enrichment and priority equal. The `draft` budget guard sees equal tracker
   entries and pricing, so it either stops both runs before a draft call or
   permits both. If permitted, its formatted request is equal; equal draft
   outcomes then give equal parsed/fallback actions and report projection.
   The graph interrupts before dispatch (`graph.py:169–172`).

The proof uses ordinary deterministic reasoning about the inspected source and
the oracle premise; it is not derived from the finite 22-case study. The study
provides concrete execution checks for three source-listed value substitutions,
one injected successful repair, an unknown site, and several deliberately
non-equivalent mutations. It ran 22 cases, 45 model calls, and 87 node events.
It does not exercise second-repair failure or an over-budget branch.

## Conditions that are easy to miss

### Input validity and metadata

`IncidentReport.model_validate` occurs before the `try` block that catches the
classifier's `SchemaViolation` (`graph.py:71–73`). Invalid inputs can raise
before any modeled workflow route. The paired theorem therefore requires both
inputs to validate, not merely equal sanitized text. Keep all three metadata
fields equal even though `reported_by` is not subsequently read: metadata
validation, report identity, routing/site lookup, and external API behavior are
part of source semantics. The upstream model imposes `text` length 10–4000
(`models.py:16–23`).

The substitution premise is exact string equality after the three regex passes
in `guardrails.py:16–24`, in their actual order: email, phone, then National
Insurance number. It is not “same PII count,” “same marker types,” or “same
approximate length.” The README lists these three patterns as the intended
redaction set. Unmatched names and other sensitive strings can remain in the
request. Pattern presence, count, or type may change the sanitized skeleton;
those changes fall outside this equality premise and can change the request.

### Oracle and call alignment

The upstream `MockLLM` is a deterministic function of system and user strings
(`llm.py:38–49`), so the pinned mock satisfies the needed equal-request
coupling for the tested paths. The injected retry test replaces the first
classification outcome with a fixed malformed string in both runs; the
upstream `call_with_repair` implementation still executes. This is not a proof
that a deployed model behaves deterministically. `OpenAILLM` uses temperature
zero and JSON mode (`llm.py:90–107`), but that setting alone is not a formal
shared-outcome oracle. For a provider-backed claim, explicitly couple complete
requests by resolved provider/model contract and call ordinal, and specify
whether returned usage metadata is observed. An equal random seed or equal
prompt alone does not establish the coupling.

The source tracker is a closure shared by all invocations of one compiled graph:
`build_graph` creates one `CostTracker` and `TrackingLLM`, and `classify` clears
the shared entries list (`graph.py:60–70`). `tracked.current_node` is mutable
and is set by node execution (`costs.py:47–62`, `graph.py:66–67,115–124`).
Concurrent invocations can clear or interleave each other's entries and
misattribute a call. The conditional theorem therefore requires isolated,
serial calls or a separately justified per-invocation tracker. The source API
uses a singleton graph and incident ID as a thread ID (`api.py:19–25,34–45`),
so that isolation is not automatic for a concurrent service deployment.

For a paired checkpoint continuation, both runs must begin from equivalent
fresh pending states and use matching thread/checkpointer behavior. The
checkpoint contains the raw incident; that data is deliberately outside the
selected observer.

### Source usage and budget accounting

`CostTracker` estimates `max(1, len(text)//4)` for each prompt and completion,
uses the configured price table (falling back to mock pricing for unknown model
names), rounds each call and total dollar amount to six decimal places, and
compares the rounded total with `MAX_COST_PER_INCIDENT_USD`
(`costs.py:15–44`). `TrackingLLM` records `system + user` and the returned
string (`costs.py:59–62`). This is the source's character-count estimate and
nominal table-price decision; it is not a provider tokenizer count or verified
charge. Equal complete strings and fixed configuration imply equal source
rows and budget decisions, including a budget-triggered human route. The
current mock has zero prices, so the finite source study does not test a budget
threshold. A compiler estimate using UTF-8 bytes and a declared divisor is a
different cost contract unless the adapter states and verifies the mapping.

`data/sites.json`, `config.PRIORITY_MATRIX`, pricing, budget, model name, and
environment-selected provider must be fixed across the pair. `build_graph`
loads the registry when constructed (`graph.py:56–64`); a change between the
two graph constructions can invalidate the deterministic correspondence.

## What a compiler-linked analysis must establish

The native compiler's current relational checker compares resolved model
contracts and exact templates/ordered symbolic arguments, treats matched prior
results positionally, and checks both arms of secret-guarded branches
(`src/relational.cpp:132–164,192–310`; the checker is described in
`include/relational.hpp:3–7`). The analysis rejects direct secret prompt
contents with E230 (`src/semantic_analyzer.cpp:282–314`) and uses E236 for
undischarged secret-arm obligations (`src/relational.cpp:352–419`). This is a
useful target contract for a source adapter, but it is not by itself a
semantics for this Python/LangGraph source.

Before a source-derived certificate can support the paired claim, an adapter
must make these correspondences explicit and fail closed on anything outside
them:

1. **Bind the exact source.** Hash the upstream commit/tree and every translated
   source/data/config file. Analyze the same bytes that the pinned source
   execution or source gate validates; reject unknown statements and dynamic
   graph construction rather than silently skipping them.
2. **State the pair relation.** Capture equal valid public metadata and the
   exact post-redaction text relation. Treat the PII captures as replaceable
   only for this stated relation. Do not claim full secret-input NI for
   arbitrary changes to the incident text.
3. **Model redaction.** The adapter must establish the exact ordered regex
   transduction, including replacement strings and Python regex/text semantics.
   The sanitized result may be treated as public only under the explicit
   premise that the residual skeleton is public and the redaction function is
   an approved release. Merely renaming a raw secret input or assigning it a
   public label is not a proof. The compiler's `declassify`/endorsement site is
   a policy declaration; it does not verify that this sanitizer is correctly
   implemented.
4. **Preserve full request structure.** Include exact `CLASSIFY_SYSTEM`, the
   `INCIDENT REPORT: ` prefix, exact redacted content, exact repair suffix and
   error text, exact `ACTIONS_SYSTEM`, and the exact draft field order and
   separators. A token count or length-equal placeholder is insufficient.
5. **Model typed result flow.** Classification is a Pydantic object with
   `category`, `severity`, `summary`, and `people_at_risk`. The draft prompt
   interpolates `category`, `priority.level`, and arbitrary `summary` text.
   The adapter must preserve these field values/relationships, not flatten a
   whole result into a token count or Boolean flag. Equal first model response
   must imply the same parsed fields and downstream prompt; schema failure and
   repair must remain represented.
6. **Model source control and deterministic effects.** Include exception/error
   routes, one-retry bound, registry success/unknown-site case, priority matrix
   and criticality bump, pre-draft cost check, fallback action parsing, and
   interrupt-before-dispatch. Bind data/config versions. Reject unsupported
   concurrency, checkpoint continuation, callbacks, tool effects, or source
   extensions.
7. **State the observation and accounting.** Choose the exact request/usage,
   node, terminal, and interrupt fields being compared. If claiming source
   cost rows, reproduce the source `len//4`, lower bound of one, pricing
   fallback, per-call/total rounding, and threshold check. Do not relabel that
   estimate as provider billing. On classifier-failure paths, acquire costs
   from the tracker/call wrapper because `classify` omits `costs` from its
   error update.
8. **Account for coupling.** Require equal responses at matching full requests
   and per-contract ordinals, including the repair call. If the model can
   return usage metadata that the observer includes, couple that metadata as
   well. The pinned deterministic mock is one concrete model of this
   assumption; an arbitrary online provider is not.

### Feasibility assessment

There is no semantic obstacle to the narrow paired-input theorem: once the
exact sanitized classifier request and all public metadata/config are equal,
the inspected graph has no later use of the raw text that can separate the
selected request/usage observer. The normal path, one-repair path, unknown-site
human-review path, second-repair failure, and budget route all have explicit
source behavior that can be modeled under the conditions above.

The main obstacle is translation fidelity, not the relational argument. A
generic call graph that models only a call result's token count and flag does
not preserve the arbitrary parsed `summary` string later inserted into the
draft prompt. Nor does the existing source language provide a verified
`redact_pii` primitive. A source-specific bridge can support a defensible
analysis if it explicitly extracts the exact source templates and transformations,
tracks the structured classification fields or a semantically equivalent
opaque result, models the retry/error branch, and declares the sanitizer and
oracle assumptions above. Without that bridge and those proof obligations,
direct source runs are validation evidence for finite pairs, not compiler proof
of the upstream workflow.

## Mutations that should be checked

The existing source study already separates value substitution from presence,
count, and pattern-type changes; it also checks public-content mutation,
unlisted name-like text, a marker-sensitive mock case, injected successful
repair, unknown-site routing, and upstream default-mock construction. To test
the actual compiler/source correspondence more sharply, add static-source
mutations with expected outcomes:

* Change the classify template prefix or system prompt in only one arm/source
  version: request equality must fail even when token lengths match.
* Add one PII marker, change its type, or change its count: exact sanitized
  request equality must fail; a count-only signature must not pass.
* Change public `site` while retaining the same redacted report: reject the
  paired premise; test both known sites with different criticality and an
  unknown site so enrichment and human-review routing are covered.
* Mutate one classification field or one downstream interpolation/separator
  (`category`, `severity`/risk, `summary`, priority level): prove the draft
  request or priority changes. Include a summary containing Unicode and
  newlines to catch string/escaping mismatches.
* Make the first response schema-invalid in both executions and then vary only
  the repair output; the second call must be matched by its exact constructed
  prompt and ordinal. Make both attempts invalid to exercise error routing and
  verify call usage from the tracker, not from the returned state.
* Set nonzero prices and a budget just below, at, and above the rounded source
  total. Equal-pair runs must make the same pre-draft decision; change only a
  response length or request field to exercise divergence.
* Run two calls concurrently through one graph as a negative scope test. The
  checker must either exclude concurrency or the source implementation must
  isolate `CostTracker` and `current_node` by invocation.
* Change the pinned regex replacement/order or insert a newly recognized PII
  field without updating the adapter. Source-hash binding or extraction should
  invalidate the old certificate.
* Observe checkpoint/state JSON or the human-review returned state. The pair
  should be classified as outside the theorem because raw incident text is
  retained; this guards against overclaiming storage confidentiality.

An accepted/equal pair in these tests is evidence only for the explicit
relation and modeled source contract. A rejected source pair is not itself a
compiler counterexample unless the counterexample lies within the adapter's
declared input domain and the source mapping is independently checked.
