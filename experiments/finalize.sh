#!/usr/bin/env bash
# Turn finished runs into the committed results, tables, figures and PDF.
#
# Usage:  experiments/finalize.sh RUNS_DIR [REPLICATION_DIR]
# Env:    PYTHON, LEAN, ORCHLANG_MODELS (as for resume.sh); PERM (permutation rounds,
#         default 200)
#
# Steps (each writes into the repository; re-running overwrites):
#   1. copy raw run records into experiments/results/runs/ (and replication/)
#   2. Lean proof check and unit tests -> experiments/results/logs/
#   3. differential test (1,000 programs) and fault injection -> experiments/results/
#   4. cap-tuning analysis -> experiments/results/cap-tuning.json
#   5. aggregate (attacks, permutation tests, costs, function) -> paper/generated/
#      and experiments/results/aggregate*.json
#   6. census/code statistics, leakage figure, OpenTelemetry span sample
#   7. build paper/main.pdf
# Afterwards: read docs/HANDOFF.md section "Finalizing the paper text".
set -euo pipefail
RUNS=${1:?runs directory}
REPL=${2:-}
: "${PYTHON:?set PYTHON}" "${LEAN:?set LEAN}" "${ORCHLANG_MODELS:?set ORCHLANG_MODELS}"
PERM=${PERM:-200}
cd "$(dirname "$0")/.."
R=experiments/results
mkdir -p $R/logs $R/runs paper/figures

echo "[1/7] copying raw records"
for d in "$RUNS"/*/; do
  w=$(basename "$d")
  [ -f "$d/compile.json" ] || continue
  mkdir -p "$R/runs/$w"
  cp "$d"/compile.json "$R/runs/$w/"
  cp "$d"/*.jsonl "$R/runs/$w/" 2>/dev/null || true
  [ -f "$RUNS/$w.log" ] && grep -v llama_context "$RUNS/$w.log" | tail -n 20 > "$R/runs/$w/run.log" || true
done
[ -f "$RUNS/transparency.json" ] && cp "$RUNS/transparency.json" $R/transparency-isolated.json
[ -f "$RUNS/queue.log" ] && cp "$RUNS/queue.log" $R/logs/queue.log
if [ -n "$REPL" ] && [ -d "$REPL" ]; then
  for d in "$REPL"/*/; do
    w=$(basename "$d"); [ -f "$d/compile.json" ] || continue
    mkdir -p "$R/replication/$w"; cp "$d"/compile.json "$d"/*.jsonl "$R/replication/$w/" 2>/dev/null || true
  done
fi

echo "[2/7] proofs and unit tests"
( cd proof && "$LEAN" --version && "$LEAN" ShapeCore.lean ) > $R/logs/lean-check.log 2>&1
$PYTHON -m unittest discover -s tests -v 2>&1 | grep -v llama_context > $R/logs/unit-tests.log
tail -n 3 $R/logs/unit-tests.log

echo "[3/7] differential test and fault injection"
$PYTHON experiments/differential.py --programs 1000 --runs 4 --output $R/differential.json > $R/logs/differential.log 2>&1
$PYTHON experiments/mutation.py --output $R/mutation.json 2>&1 | grep -v llama_context > $R/logs/mutation.log

echo "[4/7] cap tuning"
$PYTHON experiments/cap_tuning.py "$RUNS" --output $R/cap-tuning.json 2>&1 | grep -v llama_context > $R/logs/cap-tuning.log

echo "[5/7] aggregation (permutation rounds: $PERM)"
TR=$R/transparency-isolated.json; [ -f $TR ] || TR=$R/transparency-inband.json
$PYTHON experiments/aggregate.py $R/runs paper/generated --perm "$PERM" \
  --mutation $R/mutation.json --differential $R/differential.json --transparency $TR > $R/logs/aggregate.log 2>&1
cp paper/generated/results.json $R/aggregate-main.json
if [ -d $R/replication ]; then
  $PYTHON experiments/aggregate.py $R/replication paper/generated/replication > $R/logs/aggregate-replication.log 2>&1 || true
  [ -f paper/generated/replication/results.json ] && cp paper/generated/replication/results.json $R/aggregate-replication.json
fi
if [ -d $R/runs-inband-preliminary ]; then
  $PYTHON experiments/aggregate.py $R/runs-inband-preliminary paper/generated/inband > $R/logs/aggregate-inband.log 2>&1 || true
  [ -f paper/generated/inband/results.json ] && cp paper/generated/inband/results.json $R/aggregate-inband.json
fi

echo "[6/7] statistics, figure, telemetry sample"
$PYTHON experiments/paper_static.py > /dev/null
$PYTHON experiments/figures.py paper/generated/results.json paper/figures/leakage.pdf
[ -f $R/runs/email/ours.jsonl ] && $PYTHON experiments/export_otel.py $R/runs/email/ours.jsonl $R/otel-sample-email-shaped.jsonl
[ -f $R/runs/email/orig.jsonl ] && $PYTHON experiments/export_otel.py $R/runs/email/orig.jsonl $R/otel-sample-email-undefended.jsonl

echo "[7/7] paper"
( cd paper && pdflatex -interaction=nonstopmode main.tex > /dev/null; bibtex main > /dev/null || true;
  pdflatex -interaction=nonstopmode main.tex > /dev/null; pdflatex -interaction=nonstopmode main.tex | grep -E "^!|Output written" || true )
echo "done: review paper/main.pdf and docs/HANDOFF.md"
