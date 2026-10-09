# Optional LangGraph execution

This directory adds a real LangGraph runtime for version-1 OrchLang request
graphs. It is optional and is currently supported from a repository checkout;
the core `orchlang-graph-tools` wheel does not package `integrations/`.

## Install the pinned runtime

The integration was built and exercised with Python 3.14.6 and the official
LangGraph Python distribution `1.2.14`. LangGraph declares an MIT license and
Python `>=3.10`. Its PyPI wheel SHA-256 is recorded in the benchmark result.
`requirements.in` pins LangGraph and `requirements.lock` pins the full
transitive runtime with hashes.

```sh
uv venv integrations/langgraph/.venv --python 3.14
uv pip sync --python integrations/langgraph/.venv/bin/python \
  integrations/langgraph/requirements.lock
```

The local lock resolves 38 packages. The source distribution, API and license
provenance are the official [LangGraph PyPI page](https://pypi.org/project/langgraph/),
[Python graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
and [LangGraph source repository](https://github.com/langchain-ai/langgraph).
The implementation uses `StateGraph`, `START`, `END`, conditional routing,
`compile()`, and the runtime `recursion_limit` config documented by LangGraph.

## Run one graph

Use the offline Ω fixture oracle by default; no provider credentials, network
model calls, or paid services are involved.

```sh
integrations/langgraph/.venv/bin/python -m integrations.langgraph.cli \
  examples/graphs/accepted/finite_private_chain.json \
  bench/results/graph_certificates/finite_private_chain.json \
  --store-json '{"query":"é🙂 Unicode","route":true}' \
  --seed 17 --max-calls 100 \
  --output /tmp/finite-private-chain.langgraph.json
```

The JSON result includes the source-bound replay attestation, exact ordered
request descriptors and full response strings, estimated input tokens, output
usage, per-contract ordinal, the call/control counts, and stopped or truncated
status. A call-cap prefix is truncated only when execution reaches the next
call; the graph still evaluates the control transition after its last allowed
call. `--recursion-limit` can set LangGraph's actual super-step cap. A
`GraphRecursionError`, control-step cap, malformed provider outcome, or byte
limit returns an incomplete failure status; it is never reported as a
successful stop or ordinary call truncation. The adapter also caps compilation
at 10,000 reachable LangGraph state nodes, below the independent replayer's
larger schema limit.

Python callers can pass a local full-text provider implementing
`OracleRequest -> OracleOutcome` to `execute_graph`. The request contains the
normalized resolved contract (including optional-price presence and value),
per-contract ordinal, exact template, ordered full-text arguments, graph name,
seed and byte divisor. Outcomes must contain response text and output-token
usage; the backend checks UTF-8 validity, that usage does not exceed the
contract cap, that the complete response fits that usage, and the per-value,
request, trace, call and control limits. `OfflineRequestSession` exposes the
same request/oracle contract as `request(model_alias, template, arguments)`
and `tokens(text)` for the separately documented source-authored frontend.

## Architecture and gate order

`prepare_graph` first invokes
[`audit/replay_graph_certificate.py`](../../audit/replay_graph_certificate.py)
on the exact input graph and certificate bytes. The independent replayer must
return a `verified` attestation bound to both byte strings. Only then does the
backend normalize the graph and, after runtime inputs pass their type/bound
checks, import LangGraph and build a `StateGraph`. The verified handle retains
immutable source bytes; every graph view used by execution is reconstructed
from those bytes, so edits to a caller's normalized read view cannot change
the graph that runs.

The backend creates one LangGraph node per reachable graph state. Each node
executes that state's ordered calls, then evaluates its `goto`, Boolean,
public-token, secret-token or `stop` transition. Conditional edges carry
control to the target state or `END`. The runtime trace counter still counts
every individual call and transition event, even when several events run in
one LangGraph node. This keeps the graph format's ordered semantics while
avoiding one framework node per individual call.

The offline `OfflineOmegaOracle` is a direct implementation of the published
fixture rule:
`Ω(resolved-contract, per-contract-ordinal, template, ordered-text-values)`.
It uses the complete graph name/seed/request key and returns deterministic
full text with capped output-token usage. The backend does not call or import
`orchgraph.reference_run`; that function is used only by tests and the finite
differential benchmark as the comparison implementation.

## Reproduce and inspect

Run the executable integration tests and the six-fixture plus source-export
benchmark with the isolated interpreter:

```sh
integrations/langgraph/.venv/bin/python -m unittest -v \
  integrations.langgraph.test_backend
integrations/langgraph/.venv/bin/python -m integrations.langgraph.benchmark
```

The benchmark writes [`bench/results/langgraph_integration.json`](../../bench/results/langgraph_integration.json).
It stores exact LangGraph traces and per-run stopped/truncated status, hashes
the graph/certificate/replayer/backend/lock inputs, and records finite
comparison counts. Source-export rows cover the seventeen graphs already
emitted by the bounded OrchLang source adapter. They are authored
adapter-generated test cases; they are not upstream framework ports or
evidence of external user adoption.

## Scope and limits

This is an executable adapter for the separate version-1 JSON graph model. It
does not compile OrchLang source to LangGraph, validate an arbitrary LangGraph
program, or call a real provider. Source-export evidence inherits the source
bridge's narrow-subset and unaudited-fidelity boundary. The independent replay
checks the supplied graph certificate; it cannot certify that an external
source program was faithfully represented by that graph.

The Ω provider is a deterministic test fixture, not a tokenizer or real model
contract. The static request theorem still assumes the documented shared
cap-respecting outcome oracle and additive full-request accounting in
compatible model units. Productive graph cycles can run until a runtime cap;
the certificate proves neither termination nor a finite total token or cost
bound. This integration does not change the core compiler, checker, source
bridge or existing workflow frameworks.
