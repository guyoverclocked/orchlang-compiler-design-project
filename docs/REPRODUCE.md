# Reproducing the evaluation

All results in the paper come from the pipeline below. Tested environment: Linux
x86-64, 4 CPU cores, 15 GB RAM, Python 3.13, Lean 4.19.0, llama-cpp-python 0.3.36
(CPU wheel), numpy 2.5.4, scikit-learn 1.9.1, pandas 3.1.0, pyarrow 26.0.0,
huggingface_hub 2.3.0, Jinja2 3.1.6. No GPU or API key is used.

## 1. Environment

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
# Lean 4.19.0: https://github.com/leanprover/lean4/releases/tag/v4.19.0
export LEAN=/path/to/lean-4.19.0/bin/lean
```

## 2. Proofs and tests (minutes)

```bash
$LEAN proof/ShapeCore.lean                 # prints the axioms of the main theorems
python -m unittest discover -s tests -v   # 9 tests; 2 more run when ORCHLANG_MODELS is set
python experiments/differential.py --programs 1000 --output out/differential.json
```

## 3. Models and data

```bash
python experiments/fetch_models.py models          # pinned revisions, SHA-256 checked
export ORCHLANG_MODELS=$PWD/models/models.json
python experiments/prepare_data.py                 # rebuilds experiments/data/ (committed)
```

`experiments/data/` is committed; `prepare_data.py` regenerates it byte for byte from
pinned Hugging Face dataset revisions with seed 7.

## 4. Experiments (about 13 CPU hours)

```bash
bash experiments/run_all.sh out/runs                # transparency test + nine workflows
python experiments/mutation.py --output out/mutation.json
```

`run_all.sh` is resumable: each runner skips inputs already recorded. Each workflow
directory holds `compile.json` (findings, labels, Lean verdicts for every strategy,
static shapes and costs) and `orig.jsonl` / `ours.jsonl` (one record per input with
the stored outputs and the full usage trace, including analysis-only fields that
the observer never sees: dummy flag, call site, natural length).

## 5. Tables and macros

```bash
python experiments/paper_static.py
python experiments/aggregate.py out/runs paper/generated \
    --mutation out/mutation.json --differential out/differential.json \
    --transparency out/runs/transparency.json
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

The raw records used for the paper are in `experiments/results/`.
