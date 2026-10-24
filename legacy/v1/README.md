> **Legacy prototype (v1).** This directory preserves the first OrchLang prototype: a
> C++17 compiler with a relational billing-signature checker, finite certificate cores
> in Lean, and the evidence campaigns of September–October 2026. It is superseded by
> the constant-shape compiler, proofs and evaluation at the repository root and is kept
> for provenance only. Paths in this README and in its evidence records are relative to
> `legacy/v1/`; build with `make check` from this directory.

# OrchLang

A C++17 prototype and reproducible audit artifact for bounded workflow resource
analysis, declared information-flow policies and independently checked closed-
request and response-dependent certificates.

The original checker passed 95 tests but accepted a secret branch that consumed
2 versus 987 mock units at seed 1. That witness is preserved. The repaired
checker distinguishes resolved bindings, semantic contracts and request content.
The current paper is a scoped software contribution; general cloud privacy and
full-language verification are not established.

- **[Complete project explanation and publication status](docs/PUBLICATION_STATUS.md)**
- [Paper PDF, tested-source bundles and provenance](publication/README.md)
- [Current manuscript and scope](docs/SOFTWARE_PAPER.md)
- [Semantics, assumptions and trusted boundaries](docs/SEMANTICS.md)
- [Reproduction commands](docs/REPRODUCIBILITY.md)
- [Independent certificate path and replay](docs/CERTIFICATES.md)
- [Response-dependent dataflow certificates](docs/DATAFLOW_CERTIFICATES.md)
- [Clean-snapshot results](research/validated-2026-10-23/README.md)
- [Fresh GitHub-package validation](research/github-validation-2026-10-24/README.md)
- [Claim-to-evidence ledger](research/claims.csv)
- [Journal comparison and submission constraints](research/venue-search-2026-10-24.md)
- [Controlling publication plan](docs/PUBLICATION_MASTER_PLAN.md)

## What the software does

The frontend parses bounded workflows, checks declarations/types and declared
confidentiality/integrity policies, derives synthetic resource bounds and emits
structural IR. Sequential costs add, branches take componentwise maxima and
bounded retries multiply the body bound. A separate relational analysis compares
request construction and abstract contracts across secret branches. Rejection
means this analysis cannot certify its required relation, not proof that every
such workflow leaks.

```orch
workflow Triage budget 2500 {
    input ticket: text max_tokens 400;
    model m = mock("local-small") max_tokens 600;
    prompt classify(t: text) -> text = "Classify: {t}";
    let category: text = call classify(ticket) using m;
    output category;
}
```

`mock(...)` names an abstract mock contract. It does not load that model or
contact a service. C++ execution samples synthetic lengths rather than generating
text. Input accounting uses a byte/divisor estimate plus declared argument bounds
in `mock-length-v1` units. Output bounds assume the declared cap is honored.
Neither component is a provider-token theorem. Exact tokenizer probes retain
counterexamples to treating the estimate as such a theorem.

## Build and check

Requirements: a usable C++17 compiler, Python 3.10+ standard library, and optionally
Lean 4.19.0 for proof/certificate checks. The C++ core has no third-party library
or network dependency. Optional download scripts fetch pinned public research
artifacts outside the repository. GPU hardware and API keys are unnecessary.

```text
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/offline_check.py --cxx /absolute/path/to/g++ --lean /absolute/path/to/lean --output /new/run/directory
```

Output directories must be new. The full check builds fresh test/CLI executables,
records commands, exits, compiler flags, source hashes and dirty state, checks
all three Lean files, then exercises diagnostics, examples and mock resource bounds.
Use an absolute compiler path when the default PATH toolchain is outdated.
Windows commands and toolchain provenance are in the reproduction manual.
Lean proofs require only the pinned distribution's standard library.

## Compiler commands

| Command | Output |
|---|---|
| `orchc check file.orch` | Lexical, syntax, type, policy, cost and relational diagnostics |
| `orchc tokens file.orch` | Tokens and locations |
| `orchc ast file.orch` | Parsed tree |
| `orchc symbols file.orch` | Resolved declarations |
| `orchc cost file.orch` | Structural synthetic resource derivation |
| `orchc ir-json file.orch` | JSON structural IR |
| `orchc certify file.orch` | Explicitly labelled analysis report, not an independently checked proof |
| `orchc run file.orch --seed 1` | Offline length-only mock execution |

`--pin name=value` fixes a declared runtime input; invalid names/types or lengths
beyond a declaration are errors. `--chars-per-token` configures the synthetic
byte divisor and never certifies a real tokenizer bound. Consult
[LANGUAGE_SPEC.md](docs/LANGUAGE_SPEC.md) for full syntax and supported options.

## Independently checked closed requests

`scripts/closed_certificate.py` reparses a restricted source fragment without
calling the C++ analyzer. It constructs full requests, binds source bytes/core
to an untrusted plan and invokes the executable Lean JSON checker. Supported
source includes secret Boolean guards, lexical models, text prompts and literal
arguments/outputs. Inputs, downstream responses, source retries, tools and
reclassification fail closed. The reader/serialization/hash binding are trusted
Python; their correctness is not mechanized. This path does not check the C++
mock budget as a byte-token budget.

```text
python scripts/closed_certificate.py issue examples/valid/closed_certificate.orch /new/certificate.json --lean /absolute/path/to/lean
python scripts/closed_certificate.py check examples/valid/closed_certificate.orch /new/certificate.json --lean /absolute/path/to/lean
```

The Lean result concerns equal weighted traces for shared, stateless,
request-indexed kernels in the closed core. Probability interpretation requires
normalized nonnegative finite tables. It covers bounded early-stop retry with
billed failures, but source retry is excluded because the C++ mock uses a
different failure rule. Independent text reference/replay executors expose this
difference rather than silently equating their semantics.

The additional [text-dataflow path](docs/DATAFLOW_CERTIFICATES.md) admits shared
public text/Boolean inputs and actual response bindings used in later requests.
Its Lean theorem covers state-transformer semantics under stateless kernels and
secret Boolean control. Source retry, secret text, tools and reclassification
remain unsupported; outputs must be root literals. The trusted Python source
reader is not a verified parser. This judgment does not override the C++ PC-label
policy or certify its source budget. Use the separate example/CLI:

```text
python scripts/dataflow_certificate.py issue examples/certificates/dataflow_certificate.orch /new/dataflow-certificate.json --lean /absolute/path/to/lean
python scripts/dataflow_certificate.py check examples/certificates/dataflow_certificate.orch /new/dataflow-certificate.json --lean /absolute/path/to/lean
```

## Evidence and limitations

Current clean local validation passes 106 C++ tests and 47 Python tests; three Lean files
compile without admitted proofs. Development enumeration checks 576 programs,
accepts 24 and finds no accepted counterexample under the supplied kernels.
There is no observed precision advantage over conventional trace identity.
Four injected semantic faults are detected. The separate certificate campaign
records 624 checks; replay/reference agree on 12 cases and 48 weighted paths.

The new dataflow campaign covers 256 pipeline programs and 3,072 contexts. Lean,
reference and replay execution agree throughout; 16 are accepted with no
supplied-kernel counterexamples. Eight core boundary cases cover 23 weighted
paths. Failed campaign attempts and their operational/source-generator repairs
are retained. The C++ checker accepts eight cases under a distinct confidentiality
policy; these counts establish no precision ranking. Full data:
[24 October evidence](research/validated-2026-10-24/README.md).

The amended external protocol evaluates 11 authored cost projections from a
21-candidate census, with 220 mock runs and no componentwise bound violations.
They are not original application executions or faithful functional translations.
Compiler and competent structural bounds agree. Full raw observations,
protocol amendments, hashes, scope and derived tables are retained. No model
inference or paid API was used; spend and reservations remain USD 0 of a USD 5 cap.

Independent human reproduction, final author verification/declarations and
public archival release are still required before submission. No acceptance
prediction, production adoption, full source theorem or provider privacy is
claimed. [Historical README](docs/HISTORICAL_README.md) and older benchmark
outputs are retained as historical records and are superseded by the current
claim ledger.

## License

Project software: [MIT](LICENSE), selected by the owner. Optional dependency,
upstream projection and Elsevier template notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
