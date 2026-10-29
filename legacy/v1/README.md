# OrchLang

OrchLang audits bounded language-model workflows using explicit resource,
request and execution contracts.

The current scientific revision adds mechanically proved semantic rewrites,
an aggregate observer for independent calls, exact pinned-tokenizer accounting,
and original-framework comparisons against a local Qwen model.

- [Scientific revision and review-response map](docs/REVISION_STATUS.md)
- [Scientific revision PDF](publication/OrchLang-scientific-revision-2026-10-24.pdf)
- [Current manuscript source](docs/manuscript/main.tex)
- [Verified ordered and aggregate decisions](docs/VERIFIED_PRECISION.md)
- [Exact tokenizer accounting](docs/EXACT_ACCOUNTING.md)
- [Original-framework and local-model experiments](docs/REAL_WORKFLOWS.md)
- [Reproduction instructions](docs/REPRODUCIBILITY.md)
- [Claim-to-evidence ledger](research/claims.csv)
- [Current research decisions](research/revision-2026-10-24/DECISIONS.md)

## What the software checks

| Path | Question | Evidence boundary |
|---|---|---|
| C++ frontend | Are declarations, policy checks and structural resource bounds valid? | Tested C++ implementation; synthetic mock unit |
| Ordered Lean decision | Are full request/response-dependent resource traces invariant under secret Boolean changes? | Restricted core, shared public inputs and stateless kernels |
| Aggregate Lean decision | Can two independent closed calls be exchanged without changing per-contract resource totals? | Aggregate observer, independent kernels, exactly two calls |
| Exact accounting | What do complete requests cost under a pinned tokenizer and output-cap contract? | Trusted Python tokenizer/source reader; explicit units |
| Local deployment | Do upstream engines and executable call kernels preserve requests and behavior on selected inputs? | Actual CPU inference, explicit host composition, retained failures |

The ordinary C++ check remains the product's combined source-policy judgment.
Resource-only Lean acceptance does not waive a confidentiality diagnostic.
The historical certify command produces an analysis report. Saved plans are
diagnostic outputs of recomputed normalization; the main formal interface
requires no certificate.

## Build and use

The core requires C++17 and Python 3.10+. Formal decisions require Lean 4.19.0.
Core validation needs no model, GPU, network or API key.

    python -m unittest discover -s tests -p "test_*.py" -v
    python scripts/offline_check.py --cxx /absolute/path/to/g++ --lean /absolute/path/to/lean --output /new/run

Examples of the verified decisions:

    python scripts/dataflow_certificate.py decide examples/certificates/dataflow_certificate.orch --lean /absolute/path/to/lean
    python scripts/decide_aggregate.py examples/certificates/aggregate_document_checks.orch --lean /absolute/path/to/lean

The optional exact tier pins Tokenizers 0.21.4 and artifact SHA-256 values.
It encodes full constructed requests. The docs include a direct .orch command,
dynamic finite execution, byte-contract assumptions and runtime-only admission.

The optional local-model study pins upstream revisions, framework dependencies,
a Qwen tokenizer, an Ollama model manifest and an explicit serializer.
Its corpus distinguishes direct source translation from host compositions.
Independent generations and captured-response replay are separate endpoints.

## Evidence

The new ordered source grammar accepts 64 of 80 cases, versus eight under
syntactic normalization. The core-expression grammar accepts 64 of 72, versus
eight. The aggregate grammar accepts 28 of 256, versus 16 under the ordered
baseline; all twelve gains intentionally differ in ordered observations.
These are constructed development grammars, not application-frequency estimates.

Exact accounting retains 5,344 text-policy observations, 8,996 concatenation
observations and 128 supported finite execution paths. Tokenization is not
additive: the pinned GPT-2 policy counts hello and world as two tokens
separately, but helloworld as three. The source analysis exposes its conditional
output-cap assumption instead of relabeling mock bounds as provider tokens.

Historical raw results and failures remain available. New experiments use
separate immutable directories. Ubuntu/Windows CI is configured; executed
local Windows and Ubuntu/WSL2 checks are distinguished from remote CI status.

Source exports exclude class submissions, agent handoffs and old packages;
those files remain recoverable locally and in Git history. Credentials,
private papers, model weights and compiled executables are excluded.

## License

Software: [MIT](LICENSE).
Template and upstream materials: [third-party notices](THIRD_PARTY_NOTICES.md).
