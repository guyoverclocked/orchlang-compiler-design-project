# Static frontend for LangGraph source

This package translates a deliberately small subset of real Python
`StateGraph` programs into OrchLang's separate request-graph JSON format. It
parses source with Python's AST and does not execute it. The exporter then runs
the request-graph checker and, only for accepted graphs, the independent
certificate replayer. This is a source-authored frontend for one explicit
subset; it is not a general Python or LangGraph compiler.

## Try it

Run the accepted dependent-chain example with the pinned optional LangGraph
environment:

```sh
integrations/langgraph/.venv/bin/python \
  integrations/langgraph/source_frontend/export.py \
  integrations/langgraph/source_frontend/examples/secret_dependent_chain.py \
  integrations/langgraph/source_frontend/examples/secret_dependent_chain.contracts.json \
  /tmp/secret-chain.graph.json --require-accepted
```

The exporter writes four files: the graph at the requested path,
`<stem>.certificate.json`, `<stem>.provenance.json`, and
`<stem>.attestation.json`. The provenance sidecar binds the source and
contracts bytes, graph, checker report, replay attestation, AST mapping, and
the relevant implementation hashes. A rejected graph receives a report but
no replay attestation. Use `--require-accepted` when rejection should make the
command fail.

The finite source/backend differential study is reproducible with:

```sh
integrations/langgraph/.venv/bin/python \
  -m integrations.langgraph.source_frontend.study
PYTHONPATH=integrations/langgraph:. python3 -m unittest -v \
  integrations.langgraph.source_frontend.test_extract
```

The study executes only its AST-validated authored fixtures under the pinned
LangGraph runtime. It compares full ordered request/response/usage traces
against the replay-gated JSON graph backend. Results are written to
[`bench/results/langgraph_source_study.json`](../../../bench/results/langgraph_source_study.json).
The current authored study has 36 source invocations: all 30 accepted
source/backend pairs and 6 rejected-graph source/value-probe runs matched
their comparison traces. It records 66 request events, 12 equal secret
assignment pairs for the accepted dependent chain, and 3 differing pairs for
the intentionally rejected secret-template case. These are finite results
for the listed fixtures, input values, and seeds.

## Contracts

The companion UTF-8 JSON document has this shape:

```json
{
  "format": "orchlang-langgraph-contracts",
  "version": 1,
  "name": "workflow_name",
  "chars_per_token": 4,
  "inputs": {
    "question": {"type": "text", "label": "public", "max_tokens": 64},
    "private_route": {"type": "boolean", "label": "secret"}
  },
  "models": {
    "writer": {
      "provider": "mock",
      "model": "text-gen-v1",
      "max_tokens": 12,
      "unit_price": 0.001
    }
  }
}
```

Only the declared inputs and canonical model contracts come from this file;
calls, route predicates, state updates, and graph edges are extracted from
Python source. Text inputs require a `max_tokens` bound; Boolean inputs must
not have one. Labels are `public` or `secret`. `chars_per_token` defaults to
4 and is an abstract UTF-8-byte divisor. Model contracts require provider,
actual model ID, and output cap; nominal unit price is optional. JSON prices
normalize to finite nonnegative binary64 values before contract identity
checks, so decimal rounding and underflow follow binary64 conversion. Price is
identity metadata in this adapter, not a computed charge or an exact decimal
tariff. Declared text bounds, model output caps, and the worst-case complete
modeled request must fit the offline runtime's 1 MiB value limit.

## Supported Python subset

Imports must be exactly the allowed names from `typing`, `langgraph.graph`,
and `integrations.langgraph.source_frontend.runtime`. The module declares one
plain `TypedDict` with `str` and `bool` fields, top-level node/router
functions, one `StateGraph(State)` builder, literal registrations and edges,
and one final `builder.compile()` assignment. Node names, route maps, and all
source-control choices are read from the AST, not copied from the contracts.

A node is a straight-line sequence of unique local request results followed
by one literal state-update dictionary:

```python
def draft(state):
    text = request(
        model="writer",
        template="draft-v1",
        arguments=[state["question"], "briefly"],
    )
    return {"draft": text}
```

Request arguments are ordered text literals, `state["text_field"]`, or an
earlier request result local. Direct secret input text is rejected. Model
aliases and templates must be string literals declared or supplied as
specified; dynamic keyword expansion, argument expressions, and unrecognized
statements fail closed. An earlier local result is immediately available to
later requests in its node. Returned state fields are written only after the
node finishes, matching LangGraph's atomic state update. Therefore, if a node
returns a request result as `draft` and later reads `state["draft"]` in that
same node, extraction rejects it: Python observes the old input state while a
per-call graph register would already contain the new result.

Edges are static `add_edge(START, node)`, node-to-node or node-to-`END`
edges, and two-way `add_conditional_edges` with a literal label-to-target
mapping. A router can return two literal labels according to either
`state["boolean_field"]` or a single comparison of
`tokens(state["text_field"])` with an integer literal. Operand reversal is
normalized. The exporter preserves whether the guard input is public or
secret and leaves the required relational gate to decide whether all
secret-controlled paths have the same modeled request trace.

The frontend rejects unmodeled constructs, including reducers, parallel
fan-out, `Send`/`Command`, retries, effects, declassification, dynamic graph
construction, loops inside node/router functions, early or nested returns,
state mutation, input writes, copies/aliases in returned values, and values
whose register is not definitely initialized on every incoming path. A
productive static cycle is allowed; it does not imply termination or a finite
total call/token budget.

## Runtime and evidence boundary

The source imports a pure test helper, not a provider SDK. `request(...)`
works only while an `OfflineRequestSession` is bound around an invocation;
outside that offline probe context it fails. The fixture oracle is keyed by
workflow name, seed, normalized resolved model contract, per-contract
ordinal, exact template, and ordered full-text arguments. Its deterministic
response respects the declared output cap. The JSON backend and source
helpers implement the same declared offline oracle for finite differential
checks; this does not establish actual provider behavior. The emitted usage
observations contain integer call/token counts and usage traces. The adapter
does not price requests, compute currency charges, or verify provider-reported
billing.

The exporter checks the exact bounded source and contract byte snapshots it
parses, but it does not prove that arbitrary source code was translated. A
successful result means: this source was admitted by the stated AST subset,
the generated graph received the separate graph check's status, and an
accepted graph's reported relation certificate was independently replayed.
It does not prove Python/LangGraph semantic equivalence for all programs,
termination, finite total resource bounds for cycles, or a deployed-provider
security or billing guarantee. The finite differential study is evidence for
its authored cases and inputs only.
