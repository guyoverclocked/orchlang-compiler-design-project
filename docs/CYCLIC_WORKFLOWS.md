# Cyclic request workflows (experimental JSON frontend)

`audit/orchgraph.py` checks a finite JSON graph whose visible actions are model
requests. It is a separate experimental frontend. The graph author supplies
the control flow, confidentiality labels, model contracts, and request
descriptors. A narrow source adapter can emit graphs for a bounded OrchLang
subset; it is described in [`SOURCE_GRAPH_BRIDGE.md`](SOURCE_GRAPH_BRIDGE.md)
and is not a verified translation.

The checker explores a finite self-product of the graph. It can therefore
check productive cycles without unrolling a fixed number of calls. The source
adapter handles only acyclic source programs; productive cycles must currently
be supplied directly in JSON. The graph result is a sufficient check for the
modeled graph under the assumptions below, not a general relational
verification method.

## Version 1 graph format

The input is strict JSON. Duplicate keys, unknown fields, invalid identifiers,
and invalid declarations are rejected. The top-level object has these fields:

| Field | Meaning |
| --- | --- |
| `format`, `version` | Must be `orchlang-request-graph` and integer `1`. |
| `name` | Graph identifier. |
| `inputs` | Named external Boolean or text values and their `public`/`secret` labels. Text inputs require a `max_tokens` bound. |
| `models` | Aliases mapped to a provider, actual model identifier, output cap, and optional nominal `unit_price`. |
| `registers` | Named model-result values, each associated with a model alias. |
| `states` | Named blocks, each with an ordered `calls` array and one `next` decision. |
| `entry` | Initial state name. |
| `chars_per_token` | Optional positive UTF-8 byte divisor for the graph's abstract input-usage estimate; defaults to 4. |

A call is `{ "model": alias, "template": string, "arguments": [...],
"result": register }`. Each ordered argument is either `{ "literal": string }`
or `{ "value": public_text_input_or_register }`. The template and literals
are exact abstract descriptor strings. They are not a serialization of the
request sent to a real provider.

Each state's `next` is one of:

* `{ "kind": "goto", "target": state }`
* `{ "kind": "stop" }`
* `{ "kind": "public"|"secret", "guard": ..., "then": state, "else": state }`

A Boolean input guard is `{ "value": name }`; a text input or result guard is
`{ "value": name, "op": "<"|"<="|">"|">="|"=="|"!=", "limit": n }`.
Text comparisons use the graph's estimated token count, not source characters.
The decision kind must agree with the confidentiality of its input; generated
result guards are public in this graph model. Only public text inputs may be
request arguments. A result register must have the same provider/model token
unit as its producing call and a cap at least as large as that call's cap.
Generated values cannot be passed across provider/model token units.

The complete, strict field contract is enforced by the checker and the
independent replayer. The authored fixtures under `examples/graphs/` are the
most direct reference for valid and rejected graphs.

## Accepted cyclic chain

The fixture [`matched_cyclic_chain.json`](../examples/graphs/accepted/matched_cyclic_chain.json)
uses a secret `route` bit to select either a left or right pair of calls. Both
arms first request `Process {value}` on the same public `query`, then use their
respective result in another request with the same model contract and
template. Each arm tests its second result with the same public threshold and
loops to the secret choice while the result is at most eight.

Check and independently replay its certificate:

```sh
python3 audit/orchgraph.py \
  examples/graphs/accepted/matched_cyclic_chain.json \
  --report /tmp/matched-cyclic.cert.json > /tmp/matched-cyclic.check.json
python3 audit/replay_graph_certificate.py \
  examples/graphs/accepted/matched_cyclic_chain.json \
  /tmp/matched-cyclic.cert.json \
  --attestation /tmp/matched-cyclic.attestation.json \
  > /tmp/matched-cyclic.replay.json
```

The fixture currently checks as `accepted` with 91 product nodes and 114
product edges; replay reports `verified`. These counts describe this fixture
and checker snapshot, not a general bound. Both commands should exit zero.

At the root, the relation pairs each public input with itself. When the two
secret arms make the first call, the call descriptors match: resolved model
contract, exact template, and ordered argument. The shared oracle justifies
pairing the newly written result registers. On the second call, those related
registers appear in the same argument position, so that request also matches
and adds a result pair. The public result guards then have related subjects
and identical predicates, so both runs take the same successor. The checker
explores every pairing of secret choices, including choices made at different
times. A revisit of an already-seen finite product state closes the productive
cycle coinductively. The offline `reference_run` probe materializes
deterministic full response strings with at most `min(max_tokens, 32)` abstract
tokens; that is a test generator, while the proof premise only requires a
shared, cap-respecting outcome oracle.

## Rejected stale-result relation

[`overwritten_result_relation.json`](../examples/graphs/rejected/overwritten_result_relation.json)
is nearly aligned, but the left side writes register `a` twice while the right
side writes `x` and then `y`. The second paired call kills the old relation
that mentioned left-side `a`, then relates the new left value of `a` to right
value `y`. The following request uses `a` on the left and `x` on the right;
that pair is no longer justified.

```sh
python3 audit/orchgraph.py \
  examples/graphs/rejected/overwritten_result_relation.json
```

The expected exit code is 1, with diagnostic `ordered request arguments are
not proved equal`. A register's previous value cannot justify a later request
after that register has been assigned again.

## Checked property and assumptions

The observable event for a call is its resolved model contract together with
input and output usage. Resolved identity includes provider, actual model
identifier, output cap, and price-presence/value fields. Alias spelling is
not part of model identity. Calls must match in global order, which is a
sufficient condition and can reject workflows whose per-model event
projections match but whose cross-model interleavings differ.

The relational pass uses the shared oracle
`Ω(resolved-contract, per-contract-ordinal, template, ordered-text-values)`.
When the complete modeled request key agrees at the corresponding ordinal,
the oracle supplies the same complete abstract response and output usage.
The two ordinals agree inductively because every earlier call in the global
trace matched. The check compares exact template strings and ordered argument
atoms; it does not normalize whitespace or infer that distinct variable names
carry equal values.

Input usage is modeled as the estimate of the template plus the estimates of
each ordered argument. The estimate is `ceil(UTF8-bytes / chars_per_token)`
for strings, while declared text/result bounds are in compatible abstract
model units. This requires the full-request accounting premise: for every
target-model request, actual modeled input usage is bounded by this template
estimate plus the declared argument bounds. A provider's tokenizer boundary
effects or request-envelope overhead can violate that premise. The divisor is
a graph parameter, not a real-provider tokenizer guarantee. Output usage also
assumes a shared outcome oracle that respects the declared output cap.

The graph labels and public-input identities are premises. All executions
being compared give the same values to each public input; secret inputs may
vary independently. Graphs with explicit `declassification`, tool effects,
request serialization or independently sampled provider calls are outside the
model. This graph frontend does not check that a graph accurately represents
source code, and the checker/replayer do not validate a provider contract.

## Product rules and cycles

The checker explores work items `(pcL, pcR, R)`: one control position from
each run and a finite relation `R` of result/input values known equal. It
starts `R` with identity pairs for declared public inputs.

* A `goto` advances silently.
* A secret guard advances through both successors universally. If both sides
  reach secret guards, every pair of branch choices is checked.
* A public guard advances only if both sides test related values using the
  same operator and limit; both sides then follow the same arm.
* Calls match only if resolved contracts and exact templates agree, argument
  arrays agree positionally (same literal or related value), and the calls
  occupy the same event position. The result assignment first removes every
  old relation pair mentioning either destination register, then adds the
  new result pair.
* Only `stop` against `stop` closes a finite execution pair.

Reachable cycles containing calls are admitted by finite product closure. The
claim is equality of every finite usage-event prefix and synchronized stop
positions; it does not imply termination or a finite total token/cost bound.
Any reachable cycle of call-free states is rejected, including a silent goto
loop or a guard-only loop. If the product node cap is reached, the checker
returns `unknown` and exits 2; it does not accept a partial exploration.
`state_entry_bounds` in a report are local sums for calls placed in each
source state, not a bound for repeated visits.

This is an application of self-composition and relational product checking
to this finite request graph. The finite-state closure supports billable
cycles under the stated model; it is not a new general relational theory. See
[`CYCLIC_METHOD_REVIEW.md`](CYCLIC_METHOD_REVIEW.md) for the method review,
prior-work framing, and implementation evidence.

## Independent certificate replay

`audit/replay_graph_certificate.py GRAPH CERTIFICATE` independently parses
the graph and accepted certificate, recomputes the initial public relation,
and reconstructs the reachable product. It checks each local rule, relation
update, node identity, every required successor, complete reachable closure,
and selected source-state summaries. It rejects a non-accepted certificate,
source-hash mismatch, malformed schema, omitted branch edge, spurious relation,
unreachable fake node, and mismatched call/guard/stop evidence. The optional
`--attestation PATH` writes a JSON record binding hashes and replay counts.

Replay verifies that the supplied certificate is the full closure of this
graph under these local rules. The attestation is not a mechanized proof of
those rules, of the oracle/accounting assumptions, or of source-to-graph
fidelity. Neither checker nor replayer establishes a finite total budget,
termination, real-provider behavior, or a guarantee for an external workflow
that was not soundly represented by this JSON graph.

## Source adapter

For a runnable source example and its sidecar schema, see
[`SOURCE_GRAPH_BRIDGE.md`](SOURCE_GRAPH_BRIDGE.md). The adapter requires the
full compiler `check` gate and both graph proof passes. Its finite source
subset cannot express productive cycles, so it does not provide source
translation evidence for the cyclic fixture in this tutorial.
