# OrchLang: constant-shape LLM workflows

LLM workflows route, loop and fan out on model outputs. Even when prompts and
responses are hidden, as the privacy modes of observability platforms and gateways
recommend, every call still leaves a usage record: which model, how many input and
output tokens, how long it took. When control flow depends on private content,
**that usage trace is a function of the content.**

OrchLang is a workflow language and compiler that closes this side channel by
construction, with a machine-checked guarantee:

- **Detect.** Information-flow labels find every call whose usage could depend on a
  secret: secret-derived requests, calls under secret branches, and secret-guarded loops.
- **Shape.** Secret-dependent requests are padded to an exact, tokenizer-checked size,
  outputs are forced to a fixed length, secret branches are aligned into a
  minimum-cost common call sequence with dummy calls, and secret loops run to their bound.
- **Validate.** An untrusted compiler emits the shaped program, and a Lean 4 validator
  accepts it only if it satisfies a padding discipline and only adds padding.
  [`proof/ShapeCore.lean`](proof/ShapeCore.lean) proves that every accepted program
  emits the same usage trace for all secrets, for every randomness tape and hence in
  distribution, and that it computes the original program's results when padding is
  transparent. The proof uses no axioms beyond Lean's `propext` and `Quot.sound`.

The paper is [`paper/main.tex`](paper/main.tex) ([PDF](paper/main.pdf)). Every number
in it is generated from the raw run records by the scripts in `experiments/`.

## Results at a glance

| | |
|---|---|
| Census | 37 of 54 example application workflows in LangGraph, LangChain docs and Prompt Flow (69%) have content-dependent control flow ([`experiments/census`](experiments/census)) |
| Ports | 9 faithful ports (routing, chaining, evaluator–optimizer, orchestrator–worker, Prompt Flow switch, email agent, corrective and adaptive RAG, calculator agent) ([`workflows/`](workflows)) |
| Attack | Content-free usage records reveal internal routing decisions in undefended workflows |
| Defense | Shaped workflows emit one constant trace per workflow; attacks fall to chance |
| Validation | Every shaped program re-validated in Lean; fault injection: every leaking compiler bug rejected |

See the paper's evaluation section for the measured values.

## Layout

| Path | Contents |
|---|---|
| `orchlang/` | Parser, label inference, token bounds, leak detector, shaping strategies, runtime over llama.cpp, tool library |
| `proof/ShapeCore.lean` | Core semantics, padding discipline, noninterference and preservation theorems, executable JSON validator |
| `workflows/` | OrchLang ports of the nine example workflows |
| `experiments/` | Dataset builders, runner, attacks, aggregation, census, differential testing, fault injection, transparency test |
| `paper/` | LaTeX source and generated tables |
| `tests/` | Unit tests (compiler, runtime, padding exactness, byte-exact chat templates) |
| `research/` | Verified literature record used for the paper's related work |
| `legacy/v1/` | The earlier OrchLang prototype (C++ compiler, relational cost checker, older Lean cores and evidence), kept for provenance |

## Quick start

Requirements: Python 3.10+, Lean 4.19.0 (for validation), and for model runs
`llama-cpp-python` with CPU support. No GPU or API key is needed.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v              # compiler and runtime tests
lean proof/ShapeCore.lean                            # check the proofs (prints axioms)
python experiments/differential.py --programs 200 --output /tmp/diff.json   # needs LEAN=/path/to/lean
```

Compile, validate and run one workflow:

```bash
python experiments/fetch_models.py models/          # pinned GGUF files (about 3 GB)
export ORCHLANG_MODELS=models/models.json LEAN=$(which lean)
python experiments/run_workflow.py --workflow workflows/email.orch \
    --data experiments/data/email.jsonl --out runs/email --limit 5
```

The runner prints the detector's findings, validates all four shaping strategies in
Lean, and records the usage trace of each run. See [`docs/TESTING.md`](docs/TESTING.md)
for every check and how to run it, [`docs/REPRODUCE.md`](docs/REPRODUCE.md) for the
full experiment pipeline, and [`experiments/results/`](experiments/results) for the
recorded logs and results (the full nine-workflow evaluation is in progress).

## License

MIT for the project software (see [LICENSE](LICENSE)). Datasets, models and ported
prompts retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
