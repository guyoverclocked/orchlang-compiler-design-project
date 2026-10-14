# OrchLang

**Offline research software for token bounds, private workflow routing, exact usage channels, and independently replayed evidence.**

Nambi Rajan M · 24BAI0072 · Compiler Design Laboratory
Release candidate 0.5.0-rc3 · C++17 · MIT license

The [SCP strengthening package](docs/SCP_STRENGTHENING.md) adds returned-state
and finite-prefix IR proofs, completed-state differential checks, bounded
public-source workflow slices, robust full-history trace contracts, and broader
scaling evidence. Both external whole-file cohorts retain zero admissions.
API calibration and independent human reproduction remain pending. The
[rc2 publication upgrade](docs/PUBLICATION_UPGRADE.md) adds diagnosed resource
limits, shared-prefix exact replay, source-admission repairs, a narrow
machine-checked IR theorem, and frozen research evidence. The external-source
admission sample retained all 59 original candidates and admitted none; see
the [audit response](research/publication_upgrade/audit_response.md) for the
resulting claim boundaries. A software candidate is not an accepted journal paper.

## Start here

- [Current evidence and reproduction](docs/SCP_STRENGTHENING.md) and [faculty reproduction form](research/scp_strengthening/human_reproduction/REPORT_FORM.md)
- [Full technical report](docs/PAPER.md) and [focused SCP software-paper draft](docs/SCP_OSP_MANUSCRIPT.md)
- [Formal contract and proof sketch](docs/FORMAL_CONTRACT.md)
- [Installation](docs/INSTALLATION.md), [current demo](docs/REVIEW_DEMO.md), and [cyclic graph tutorial](docs/CYCLIC_WORKFLOWS.md)
- [Source-to-graph bridge](docs/SOURCE_GRAPH_BRIDGE.md) and [independent full-text validation](docs/RELATIONAL_STRESS.md)
- [Exact finite usage channels](docs/PROBABILISTIC_CHANNELS.md) and [stochastic proofs for every finite horizon](docs/STOCHASTIC_BISIMULATION.md)
- [Functioning HTML demo](demo/README.md) and [actual LangGraph source frontend](integrations/langgraph/source_frontend/README.md)
- [Current SCP requirements](docs/SCP_AUTHOR_REQUIREMENTS.md) and [official-template LaTeX manuscript](submission/research/manuscript/OrchLang_SCP_OSP.tex)
- [Publication strategy](docs/SUBMISSION_PLAN.md) and [verified journal shortlist](docs/JOURNAL_SHORTLIST.md)
- [ArchiveGate-style presentation package](submission/research/README.md)
- [Unchanged third-party source study](research/INCIDENT_TRIAGE_SOURCE_STUDY.md), [source protocol](research/INCIDENT_TRIAGE_ANALYSIS.md), and [concurrent meter finding](research/INCIDENT_TRIAGE_CONCURRENCY.md)

## The question

A workflow can have a safe worst-case budget and still reveal a secret through its usage record. Equal upper bounds do not mean equal actual usage. If a private flag selects between two differently sized public inputs, the input-token bill can reveal the selection even though no secret argument reaches a model.

OrchLang checks three properties before normal offline execution:

| Analysis | Result | Contract boundary |
|---|---|---|
| Unary cost | Output, input and total token bounds through calls, branches and bounded retries | Model cap, input bounds and complete-request accounting assumptions |
| Flow policy | Secret data kept from prompts/outputs/tools; untrusted data kept from tool effects without endorsement | Declared labels and trusted explicit releases/endorsements |
| Relational requests | Secret alternatives have matching modeled calls, requests, guards and retries | Shared outcome oracle; unrestricted billing theorem excludes declassification |

This is a focused application of established resource-aware information flow and relational cost reasoning. The guarantees require declared accounting and complete-outcome contracts. Real-provider invoices, prompt-injection resistance, and a new general noninterference theory are outside the claims. [Related work](docs/PRIOR_ART_MATRIX.md) includes constant-resource types, RelCost, Bounded Expectations, PPDL, LMQL/APPL/PDL and agent security systems.

## Build and use

A C++17 compiler and `make` are sufficient for the core. Python 3 is used by the research harnesses.

```sh
make check
./orchc check examples/valid/support_triage.orch
./orchc cost examples/valid/bounded_retry.orch
./orchc certify examples/research/accepted/chain_matched.orch
./orchc run examples/research/accepted/chain_matched.orch --seed 3 --json
```

No API key, model download, network request or real tool invocation is required.

To present the eight interactive examples, start the localhost server and open
<http://127.0.0.1:8765/>:

```sh
python3 demo/server.py
```

Stories 01–07 invoke the real local compiler or graph/stochastic analyzers and
their independent checks. Story 08 freshly replays source protocols and recorded
LangGraph concurrency/path evidence; it does not rerun LangGraph. Python 3.12+
is required for that pinned source's syntax. Opening `demo/index.html` directly
displays labeled saved evidence with digests; it does not run the current tools.

```orchlang
workflow MatchedChain budget 2000 {
  input query: text max_tokens 100;
  secret route: boolean;
  model m = mock("worker") max_tokens 60;
  prompt step(t: text) -> text = "Process {t}";
  if route {
    let a: text = call step(query) using m;
    let b: text = call step(a) using m;
  } else {
    let x: text = call step(query) using m;
    let y: text = call step(x) using m;
  }
  output query;
}
```

The first requests match, so their results match under the shared oracle; both second requests refer to that same prior position. The compiler now accepts this chain. Its effective labels still prohibit returning or emitting values under the secret branch.

## Productive cycles and replayable graph contracts

The separate experimental JSON front end supports finite control graphs with call-bearing cycles and mutable result registers. It checks a product `(pcL, pcR, R)`, keeps equal-value relations through dependent calls, and removes stale pairs when results are overwritten. Private alternatives are universal obligations. An accepted finite closure yields a source-bound certificate that an independently implemented replayer reconstructs from scratch.

```sh
python3 audit/orchgraph.py examples/graphs/accepted/matched_cyclic_chain.json --report /tmp/cycle.json
python3 audit/replay_graph_certificate.py examples/graphs/accepted/matched_cyclic_chain.json /tmp/cycle.json
python3 audit/source_to_graph.py examples/research/accepted/chain_matched.orch /tmp/chain.graph.json --compiler ./orchc
```

The accepted cyclic chain has 91 product nodes and 114 edges. Cycles preserve finite request/usage prefixes and stop positions under the shared complete-outcome contract; they may still run forever. No finite total budget follows. Reachable call-free cycles reject and resource exhaustion returns `unknown`. The bounded `.orch` grammar remains finite. The source bridge covers an explicit acyclic subset and binds the source, compiler, graph, certificate, and adapter snapshots; its translation is not mechanically verified.

The checker, finite-channel analyzer, stochastic-bisimulation analyzer and
their independent replayers are available in a Python wheel with no runtime
dependencies. [Installation and isolated package tests](docs/INSTALLATION.md)
document the commands and scope.

## Exact usage laws under declared finite models

An explicit rational outcome kernel can distinguish request equivalence from
usage-law equality. The finite analyzer retains complete values, control,
ordinals and bounded outcome history. It computes exact usage histograms,
total variation and Bayes vulnerability; mutual information has an exact
symbolic expression and an approximate numerical display. Independent
enumeration and report replay check exact claims.

Two examples make the observer matter:

- Output usage `1` or `3` with equal probability versus deterministic `2`
  has the same mean, but total variation `1`: the usage identifies the arm.
- Ordered usage `(1,3)` versus `(3,1)` has equal totals. Aggregate total
  variation is `0`; ordered-trace total variation is `1`.

A finite stochastic transducer and exact partition refinement can prove equal
ordered usage laws for **every finite call horizon**, including productive
cycles. It uses established probabilistic bisimulation. Independent replay
reconstructs the closure and verifies stability. Separate blocks are
`inconclusive`; resource exhaustion is `unknown`. The theorem covers the
supplied successful-outcome model, fixed public inputs and explicit secrets.
It excludes cumulative runtime resource monitors, termination and provider
probability validation.

An exact rational row-span checker also **decides ordered trace-law equality**
for the supplied finite model and selected stores. It independently replays
equality certificates or exact finite inequality witnesses. An authored case
has equal usage laws despite a bisimulation split, demonstrating the extra
precision. This specializes established weighted-automaton equivalence;
[TRACE_EQUIVALENCE.md](docs/TRACE_EQUIVALENCE.md) gives the scope and budgets.

```sh
python3 audit/evaluate_probabilistic_channels.py
python3 audit/evaluate_probabilistic_replay.py
python3 audit/evaluate_stochastic_bisimulation.py
python3 audit/evaluate_trace_equivalence.py
```

## Actual LangGraph execution and source

The optional pinned LangGraph 1.2.14 backend executes replayed graphs using a
bounded offline request session. A restricted AST frontend reads calls and
edges from actual Python `StateGraph` programs and rejects unsupported
behavior. Its finite source/backend comparisons execute the original authored
Python functions. [Runtime setup](integrations/langgraph/README.md) and
[source subset](integrations/langgraph/source_frontend/README.md) explain the
admitted syntax, atomic state updates, provenance and limitations. These
adapters do not establish arbitrary Python translation or external adoption.

## Unchanged third-party source and per-incident usage

A separate case study executes the MIT-licensed `agent-incident-triage`
workflow at immutable revision `c08f710acfeefe233329df613fe8358eaac5f350`.
All 23 original files and a local Git bundle are included with their hashes.
The 22-run source study and six paired scripted paths exercise exact requests,
repair/schema failures, full summaries, draft fallback and the source budget
guard. They use offline outcomes, including an explicitly artificial oversized
response for the nominal-price guard; no provider invoice is measured.

A strict source-specific AST protocol independently checks the complete
pre-dispatch dependency argument. The generated OrchGraph certificate covers
only the first classifier request pair. Neither is a generic Python translator
or a mechanized proof of Python semantics. Equal exact redactor output, valid
public metadata, fixed configuration, fresh isolated apps and a shared complete
outcome oracle are premises. Raw incident state/checkpoint privacy is excluded.

One controlled concurrent schedule on the original shared app records another
incident's usage rows and mislabels a classification row. Four unique calls
have 456 source-estimated units, while summing both returned snapshots gives
687, including 231 foreign units in A's snapshot. Mock prices are zero.
A bounded, replay-gated offline manager creates one fresh graph per incident
and retains it for approval; it is a repair demonstration for this source
profile, not a production service or general concurrency verifier.

## What changed in this upgrade

- Resolve provider/model/cap/price contracts instead of trusting source alias spelling.
- Compare exact template and typed-literal bytes, ordered lexical/prior-result atoms, and canonical model contracts.
- Separate explicit data dependence from effective program-counter dependence for matched model chains.
- Preserve lexical scopes and aligned call positions through nested branches/retries.
- Reject cross-model generated-value bound reuse without a tokenizer conversion contract (`E267`).
- Gate normal CLI and API execution on cost and relational checks; validate pin names/types/bounds.
- Expose source-located branch/retry traces and structured usage JSON.
- Bind certificate v3 to source SHA-256, record call facts and whole-workflow release scope.
- Independently parse source and recompute/report-audit every token-cost derivation in Python.
- Check productive request cycles with overwrite-sensitive product relations and independent closure replay.
- Export a declared bounded source subset, bind exact source/compiler snapshots, and compare source/graph full-value execution.
- Compute exact finite usage channels and independently replay exact histograms and metrics.
- Prove a sufficient usage-law equality for every finite horizon by finite stochastic closure.
- Decide ordered usage-law equality in the supplied finite model by exact rational row spans, with independently replayed proofs or finite witnesses.
- Extract actual restricted Python LangGraph source and execute a replay-gated LangGraph backend.
- Supply a nine-module, eight-command wheel tested outside the checkout, and a functioning HTML demo.

## Evidence

The evidence includes 112 C++ regressions, 203 Python audit tests (including 21
source-cost tests), nine demo HTTP tests, and 31 optional LangGraph tests.
The closing demo now has nine HTTP tests. The separately scoped incident
extension has 12 direct-source, 13 source-protocol, 19 concurrency/session, and
10 path-replay tests. Its 16-stage reproduction is recorded separately.
Address/undefined-behavior sanitizer checks and the shipped examples pass.
The full reproduction manifest binds builds, sources and result files.

| Experiment | Recorded outcome |
|---|---|
| 23 synthetic cost workflows, 4,600 offline runs | Zero output/input/total bound violations |
| Seven accepted synthetic relational fixtures | Zero differences in 2,975 comparisons |
| Seven leaking synthetic rejections | Every fixture has a witness |
| 13 unsafe/safe flow-policy pairs | All intended verdicts |
| 15 source-derived patterns, 45 authored bounded variants | Partial projections from PDL/APPL/LMQL with immutable provenance/exclusions |
| Balanced source variants, each oracle mode | 15/15 accepted, zero differences in 2,250 paired comparisons |
| Pre-upgrade compiler on identical balanced files | 8/15 accepted; seven additional patterns now admitted |
| One-extra-call source mutations, each mode | All 15 rejected; all 2,250 paired slices differ |
| Base source variants, each mode | Zero violations in 1,500 runs; 30 base/balanced reports independently audited |
| Independent full-text bounded stress | 144 positives/120 mutations; zero accepted request/usage mismatches in 13,824 secret comparisons |
| Negative full-text probes | 117 witnessed; three retry mutations remain unknown on the finite grid |
| Authored graph fixtures | Six accepted certificates independently replay; eight rejections and three invalid models |
| Accepted graph value grid | Zero request/billing/stop differences in 800 secret comparisons over 1,400 runs |
| Rejected graph value grid | Eight of eight have finite billing witnesses; complete only for stopped runs |
| Independent graph replayer | 33 semantic/tamper tests; no producer imports |
| Bounded source bridge | 17/20 exports; 720 source/graph run pairs agree; three retry exclusions |
| Actual LangGraph backend | 888 runs / 4,528 call-event pairs agree; 24 call-cap prefixes |
| Actual Python LangGraph source | 30 accepted trace pairs / six rejected value probes agree |
| Finite rational usage study | 11 kernels; 130 analyses / 260 exact independent histogram comparisons agree |
| Independent channel report replay | All 130 verify at explicit larger caps; 129 verify / one UNKNOWN at default caps |
| Stochastic bisimulation | Five proved equal / six inconclusive; all 11 independently replay |
| Finite cross-checks of proved models | 60 checks / 120 unit-mass histograms; all 11 fresh state-cap probes UNKNOWN |
| Exact all-finite-horizon trace laws | 12 cases: six proofs/six finite witnesses, all independently replayed; 48 equality DP checks and six witness checks; all fresh cap/tamper probes match expectations |
| Installed wheel | 23 offline build/install/CLI stages; tampering rejects; UNKNOWN preserves no equality claim |
| Third-party source protocol | 22 recorded runs; seven independent checks; classifier-only graph slice; full source-specific dependency argument |
| Third-party path coverage | Six authored paired paths / 12 runs / 24 calls; all pairs independently replay equal |
| Shared source meter | One controlled 19-event schedule; 456 unique vs 687 summed snapshot units; isolated apps keep two own rows each |
| Closing HTML demo | Eight fixed stories; nine HTTP tests; fresh execution, fresh replay and saved evidence clearly labeled |

The two modes repeat the same patterns/grid; their counts are not pooled as independent applications. `bench/results/sourced.json` records ordinal draws; `sourced_request_sensitive.json` adds template/literal bytes and abstract value fields to response draws. The request-sensitive mock still has no generated text. The development corpus has three conservative rejections whose ordinal bills agree in 300 comparisons, exposing precision limits.

## Reproduce

```sh
python3 bench/generate.py
python3 bench/generate_sourced.py
python3 -m unittest discover -s audit -p 'test_*.py' -v
python3 bench/evaluate.py
python3 bench/evaluate_sourced.py
python3 bench/evaluate_sourced.py --request-sensitive-oracle
python3 audit/reproduce_final.py --sanitize --package
```

Pass `--baseline /path/to/a49fcdb/orchc` to the sourced harness to reproduce the 8/15 comparison. [The reproducibility guide](docs/REPRODUCIBILITY.md) describes building that immutable revision without changing this checkout.

```sh
python3 audit/certificate_audit.py bind examples/research/accepted/chain_matched.orch /tmp/chain-report.json
python3 audit/certificate_audit.py verify examples/research/accepted/chain_matched.orch /tmp/chain-report.json
```

The source auditor checks cost arithmetic and report integrity. The separate graph replayer checks complete product closure. Neither mechanically proves its metatheory or provider premises. The generated-AST full-text interpreter is independent of C++ runtime/certificates; graph value/property probes share producer schema code.

To also repeat the pinned LangGraph tests and both actual execution studies,
pass `--integration-python integrations/langgraph/.venv/bin/python` after
setting up that optional environment. The script never installs its runtime.

To repeat the separately pinned incident-triage extension after installing its
documented Python 3.14.6 lock, run:

```sh
python3 audit/reproduce_incident_triage.py \
  --integration-python integrations/incident_triage/.venv/bin/python
```

This reconstructs the clean upstream checkout from the included local bundle;
it installs nothing and uses no provider. See [source custody](integrations/incident_triage/SOURCE_SNAPSHOT.md).

## Commands and scope

`tokens`, `check`, `ast`, `symbols`, `ir`, `ir-json`, `cost`, `certify`, `run`.

- `--chars-per-token N`: UTF-8 byte divisor, default 4; the full request-accounting premise remains necessary.
- `--seed N`, `--retry-failure P`, `--pin name=N|true|false`: offline inputs/oracle controls. Pins must respect declared types and bounds.
- `--json`: structured run trace.
- `--request-sensitive-oracle`: opt-in modeled-request response draws.
- `--audit-unsafe`: explicit offline witness bypass for cost/relational rejections; parsing, typing and input contracts remain checked.

The C++ runtime uses `mock` calls; graph calls are declared abstract contracts and remain offline. The token theorem assumes cap-respecting outcomes and bounded complete-request input accounting. There is no verified provider tokenizer, request serializer, price/discount/cache model, actual invoice observer, or independent-seed pathwise guarantee. The new mechanized result covers only normalized straight-line request/local-result refinement under an atomic-read side condition; it does not prove source extraction or the full compiler. Declassification deliberately releases secrecy; reports withhold the unrestricted billing claim. Endorsement/declassification do not execute their written reasons.

## Repository map

`src/`, `include/` implement the compiler; `tests/` its regressions; `examples/` the shipped and research fixtures; `bench/` generated and sourced experiments; `audit/` analysis and independent checks; `integrations/` the optional runtime/source adapters; `demo/` the closing HTML exhibit; `research/` the source catalog; `docs/` the report, contracts and reviews; `submission/research/` the presentation and publisher manuscript; `output/` PDFs and the installable wheel.

Earlier Review 2/Phase 2 submissions and September audits are historical. Their counts and theorem wording describe earlier versions. Archived drafts are under `docs/archive/`; use current docs for presentation and publication.

## License and attribution

The project uses the [MIT license](LICENSE). All original repository commits identify Nambi Rajan M; the authenticated GitHub account matches the repository owner. MIT was selected under the owner's delegated project authority for this local release candidate. Upstream source-pattern attribution and development-tool notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Human authors should review the release and AI-assistance disclosure before journal submission. Journal submission and human author sign-off have not occurred. The release manifest identifies any publicly prepared candidate; a software candidate is not a reviewed journal article.

## Current SCP publication candidate

The rc3 [main paper](submission/research/manuscript/OrchLang_SCP_Strengthened.tex) ([PDF](output/pdf/OrchLang_SCP_Strengthened.pdf)) and [technical supplement](submission/research/manuscript/OrchLang_SCP_Technical_Supplement.tex) ([PDF](output/pdf/OrchLang_SCP_Technical_Supplement.pdf)) bind frozen code `8533214105aad0cc015ea1e1c2aad4057515aff7`. All 19 local reproduction stages and six CI jobs passed on that revision. Read the [faculty/author handoff](research/scp_strengthening/human_reproduction/SUBMISSION_HANDOFF.md) and [archive receipt](output/scp_strengthening/publication/archive_receipt.json). This is a prepared research candidate; author approval, independent human reproduction, live API calibration and journal submission remain pending.
