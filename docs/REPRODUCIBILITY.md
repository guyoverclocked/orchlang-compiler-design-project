# Reproducing the October research candidate

## Requirements and scope

The compiler needs C++17 and make. The audit, finite-channel, stochastic and
local demo tools need Python 3.10+ and the standard library. The wheel builder
also needs local pip, setuptools and wheel; it does not contact a package
index. LangGraph is optional and uses its separate pinned environment.
All evaluated model behavior is offline. No provider keys, paid calls or
actual tool effects are used.

## Full run

From the repository root:

```sh
python3 audit/reproduce_final.py --sanitize --package
```

To reproduce the optional actual LangGraph backend and original Python source
executions as well, first set up the locked environment described in
[integrations/langgraph/README.md](../integrations/langgraph/README.md), then run:

```sh
python3 audit/reproduce_final.py --sanitize --package \
  --integration-python integrations/langgraph/.venv/bin/python
```

The script does not install the optional environment. It runs:

1. ASan/UBSan (when requested), optimized compiler regressions and examples.
2. All Python audit tests and the local demo's HTTP tests.
3. Accepted/rejected research sources, certificate and IR JSON checks.
4. Development experiments and both source-pattern oracle grids, including
   the compiler at immutable baseline `a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9`.
5. Independent full-text bounded stress, cyclic graph fixtures/property
   probes, and bounded source-to-graph differential execution.
6. Exact finite channels, independent enumeration and replay of all saved
   channel reports under both default and explicit larger resource caps.
7. Finite stochastic closure, independent certificate replay, finite-horizon
   DP corroboration and fresh resource-cap UNKNOWN probes.
   Exact rational trace-law decisions, independent proof/witness replay,
   finite DP corroboration and semantic report-mutation checks.
8. Optional LangGraph backend/frontend tests and both actual execution studies.
9. Optional offline wheel build/install/CLI checks outside the checkout.

The baseline must be locally available; the script never fetches it. A shallow
clone may need its history fetched beforehand. Compiler binary hashes can
vary across environments; compare each result with the binary that produced
it, rather than a universal expected hash.

`audit/final/manifest.json` records status, exact source/result hashes, stages,
exit codes, environment and selected optional features. A new run first
replaces an old PASSED manifest with RUNNING; failure records FAILED. Logs
remain beside the manifest. Hashes bind bytes; they do not prove correctness.

## Quick mode

```sh
python3 audit/reproduce_final.py --quick
```

This skips long grids and the baseline build. It writes `quick: true` and must
not be presented as a fresh complete evaluation. Result files from earlier
studies may still be inventoried; stage records and optional flags determine
what was actually repeated. A current full manuscript/deck uses a full run.

## Exact quantitative evidence

```sh
python3 audit/evaluate_probabilistic_channels.py
python3 audit/evaluate_probabilistic_replay.py
python3 audit/evaluate_stochastic_bisimulation.py
python3 audit/evaluate_trace_equivalence.py
```

The finite channel study has 130 analyses and 260 exact DP/independent-DFS
histogram comparisons. Saved reports independently replay at one million
paths, ten million work steps and one GiB deterministic byte work. The default
100,000 paths, one million steps and 64 MiB yield 129 VERIFIED and one UNKNOWN;
UNKNOWN has no equality or leakage conclusion. Byte work is a serialization
work estimate, not an RSS bound. Approximate logarithms and producer work
counters are excluded from replayed facts.

The all-finite-horizon study has 11 models: five PROVED_EQUAL and six
INCONCLUSIVE, all independently replayed. The proved cases pass 60 finite DP
checks (120 scenario histograms) at horizons 1, 2, 4, 8, 16 and 32 under both
observers. Partition stability, rather than that finite sampling, supports
the conclusion for every finite horizon. All 11 fresh state-cap reports and
attestations remain UNKNOWN. The theorem excludes cumulative runtime resource
monitors, termination and the validity of provider probabilities.

The exact trace-law study has 12 supplied finite models: six equality proofs
and six finite witnesses, all independently replayed. An equal-but-not-bisimilar
case is accepted. Equality cases pass 48 finite DP checks (96 histograms), and
all six exact witness masses agree with DP. Twelve fresh UNKNOWN probes and
twelve semantic report mutations have the expected outcomes. The every-finite-
horizon result comes from exact span closure and both stop/live output columns,
not from those finite samples. The algorithm is established prior art.

See [PROBABILISTIC_CHANNELS.md](PROBABILISTIC_CHANNELS.md) and
[STOCHASTIC_BISIMULATION.md](STOCHASTIC_BISIMULATION.md) for schemas and claims.

## Independent source-cost audit

```sh
python3 audit/certificate_audit.py bind \
  examples/research/accepted/chain_matched.orch /tmp/chain-report.json
python3 audit/certificate_audit.py verify \
  examples/research/accepted/chain_matched.orch /tmp/chain-report.json
```

This independently parses source and checks cost facts and derivations. It
does not verify typing, flow policy, relational obligations or release reasons.
The graph replayer, quantitative report replayer and stochastic replayer check
separate claims. None establishes provider premises or mechanizes metatheory.

## Evidence files

| File | Meaning |
|---|---|
| `bench/results/evaluation.txt` | Development grids and engineering baselines |
| `bench/results/sourced*.json` | Same partial source corpus, two oracle modes |
| `bench/sourced/manifest.json` | Pinned upstream files, omissions and projection hashes |
| `bench/results/relational_stress.json` | Independent bounded full-text stress |
| `bench/results/graphs.json`, `graph_adversarial.json` | Cyclic fixtures and producer-model property probes |
| `bench/results/source_graphs/evaluation.json` | Bounded source/graph differential study |
| `bench/results/langgraph*.json` | Actual optional backend and original-source studies |
| `bench/results/probabilistic_channels.json` | Controlled exact finite channel study |
| `bench/results/probabilistic_replay.json` | Independent exact report replay, including cap outcomes |
| `bench/results/stochastic_bisimulation.json` | Finite closure, replay and horizon cross-checks |
| `bench/results/trace_equivalence.json` | Exact all-finite-horizon laws, replayable witnesses, bisimulation gap, tampering and caps |
| `output/release/packaging_validation.json` | Isolated wheel installation and commands |
| `audit/final/manifest.json` | Completed stages and source/result inventory |

The 15 source patterns are author-created bounded projections, not full
framework ports. Repeated seeds, inputs, horizons and oracle modes are not
independent applications. Generated/stochastic cases are synthetic. Historical
September/Review 2 reports do not describe this candidate.

## Closing HTML demo and documents

```sh
python3 demo/server.py
```

Open <http://127.0.0.1:8765/>. It runs bounded fixed local checks. Directly
opening `demo/index.html` uses explicitly labeled saved evidence with digests.
See [demo/README.md](../demo/README.md) for controls and limits.

`submission/research/build_current_candidate.sh` builds the editable deck with the Codex Artifact
Tool and checks displayed result provenance. `scripts/build_paper_pdf.py`
renders the extended technical report. `scripts/build_scp_manuscript.py`
fills the downloaded official OSP LaTeX template without altering its
format settings. PDF/deck authoring dependencies are optional and are not
required to build or use the compiler and analysis wheel.
