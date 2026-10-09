# Installation and first verified results

OrchLang runs offline. The C++17 compiler is separate from the standard-library
Python analysis wheel and the optional pinned LangGraph runtime. No provider
account, API key, model download or paid service is required.

## Build the compiler

```sh
git clone https://github.com/guyoverclocked/orchlang-compiler-design-project.git
cd orchlang-compiler-design-project
git checkout codex/research-upgrade
make check
./orchc check examples/research/accepted/chain_matched.orch
```

Use the exact immutable candidate revision from the release manifest when
reproducing a paper; a branch can move. C++17 and make build the compiler.
Audit tools need Python 3.10+. Full research grids are optional for trying it.

## Run the closing HTML demo

```sh
python3 demo/server.py
```

Open <http://127.0.0.1:8765/>. Six fixed examples execute the real local tools
and display replay results, usage records, exact metrics and assumptions. The
server binds only to localhost and bounds requests, horizons and tool runtime.
Directly opening `demo/index.html` shows saved evidence; the banner explicitly
states that no current compiler run has occurred. [Demo guide](../demo/README.md).

## Graph checking and independent replay

```sh
python3 audit/orchgraph.py \
  examples/graphs/accepted/matched_cyclic_chain.json --report /tmp/cyclic.json
python3 audit/replay_graph_certificate.py \
  examples/graphs/accepted/matched_cyclic_chain.json /tmp/cyclic.json \
  --attestation /tmp/replay.json
```

This produces an accepted 91-node/114-edge product closure, followed by an
independently reconstructed `verified` attestation. The replayer does not
import its producer. `examples/graphs/rejected/overwritten_result_relation.json`
rejects with an unproved ordered argument relation. Product exhaustion yields
UNKNOWN; neither rejection nor UNKNOWN establishes safety.

## Install all Python analysis and replay commands

The wheel under `output/release/wheels/` contains nine modules and eight CLI
commands, with no third-party runtime dependency. It does not package the C++
compiler, source bridges, study scripts, demo or optional LangGraph runtime.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps \
  output/release/wheels/orchlang_graph_tools-0.5.0rc1-py3-none-any.whl
.venv/bin/orchlang-graph-check \
  examples/graphs/accepted/matched_cyclic_chain.json --report /tmp/cyclic.json
.venv/bin/orchlang-graph-replay \
  examples/graphs/accepted/matched_cyclic_chain.json /tmp/cyclic.json
```

| Installed command | Purpose |
|---|---|
| `orchlang-graph-check` | Sufficient request-equivalence product certificate |
| `orchlang-graph-replay` | Independent product-closure reconstruction |
| `orchlang-channel-analyze` | Exact finite usage channel under a supplied kernel |
| `orchlang-channel-replay` | Independent exact histogram/metric reconstruction |
| `orchlang-stochastic-bisimulation` | Sufficient usage-law equality for every finite horizon |
| `orchlang-stochastic-replay` | Independent finite closure and partition stability |
| `orchlang-trace-equivalence` | Exact all-finite-horizon ordered usage-law decision |
| `orchlang-trace-replay` | Independent row-span proof or finite-witness replay |

Every command supports `--help`. On Windows, venv commands are under
`Scripts/`. For a small end-to-end quantitative example:

```sh
.venv/bin/orchlang-channel-analyze \
  examples/channels/equivalent_dependent_chain.graph.json \
  examples/channels/equivalent_dependent_chain.kernel.json \
  --public-json '{}' \
  --scenarios-json '[{"values":{"secret":false},"prior":"1/2"},{"values":{"secret":true},"prior":"1/2"}]' \
  --horizon 2 --observer trace --report /tmp/channel.json
.venv/bin/orchlang-channel-replay /tmp/channel.json \
  examples/channels/equivalent_dependent_chain.graph.json \
  examples/channels/equivalent_dependent_chain.kernel.json
.venv/bin/orchlang-stochastic-bisimulation \
  examples/channels/equivalent_dependent_chain.graph.json \
  examples/channels/equivalent_dependent_chain.kernel.json \
  --public-json '{}' --scenarios-json '[{"secret":false},{"secret":true}]' \
  --report /tmp/bisimulation.json
.venv/bin/orchlang-stochastic-replay /tmp/bisimulation.json \
  examples/channels/equivalent_dependent_chain.graph.json \
  examples/channels/equivalent_dependent_chain.kernel.json
```

The finite report is COMPLETE with equal observation laws; the independent
report is VERIFIED. The closure result is PROVED_EQUAL and independently
VERIFIED. Priors belong to quantitative leakage; bisimulation uses explicit
secret assignments without priors. For a split partition, INCONCLUSIVE makes
no inequality claim. Resource caps return UNKNOWN and no partial proof.

For the equal-law example that sufficient bisimulation misses:

```sh
.venv/bin/orchlang-trace-equivalence \
  examples/channels/trace_equal_not_bisimilar.graph.json \
  examples/channels/trace_equal_not_bisimilar.kernel.json \
  --public-json '{}' --scenarios-json '[{"secret":false},{"secret":true}]' \
  --report /tmp/trace-laws.json
.venv/bin/orchlang-trace-replay /tmp/trace-laws.json \
  examples/channels/trace_equal_not_bisimilar.graph.json \
  examples/channels/trace_equal_not_bisimilar.kernel.json
```

The result is PROVED_EQUAL and independently VERIFIED. On
`same_mean_distinct_laws`, the decision is UNEQUAL with an exact finite word
witness. The checker decides the laws only for the supplied finite successful
model and listed inputs; it does not validate provider probabilities.

## Offline package build and optional framework

```sh
python3 scripts/package_graph_tools.py
```

The builder selects a locally available interpreter with setuptools/wheel,
builds without a package index, installs in a temporary venv and executes
outside the checkout. Twenty-three stages check installed metadata/imports,
graph/channel/stochastic and exact trace-law outputs, independent proof/witness
replay, wrong-source/tampering rejection and UNKNOWN.
Evidence is `output/release/packaging_validation.json`. It does not upload a
package or modify a global environment.

The optional runtime/source extraction is supported from a checkout. See
[LangGraph setup](../integrations/langgraph/README.md) and the
[actual Python source subset](../integrations/langgraph/source_frontend/README.md).

## Select the relevant guarantee

Bounds concern declared additive token accounting. Request equivalence is
conditional on a shared complete-outcome oracle. Quantitative and stochastic
results concern a supplied successful-outcome finite kernel, fixed public
inputs and selected secret assignments. Productive cycles need not terminate;
there is no finite total budget for an unbounded cycle. Provider invoices,
probability fitting, complete request envelopes and mechanized soundness are
not established. Model assumptions are part of each result.

[Contracts](FORMAL_CONTRACT.md), [finite channels](PROBABILISTIC_CHANNELS.md),
[stochastic closure](STOCHASTIC_BISIMULATION.md), [reproduction](REPRODUCIBILITY.md).
