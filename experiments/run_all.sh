#!/usr/bin/env bash
# Runs every workflow over its dataset (orig and ours), sequentially.
# Usage: experiments/run_all.sh OUT_DIR   (env: ORCHLANG_MODELS, LEAN, PYTHON)
set -u
OUT=${1:?output directory}
PY=${PYTHON:-python}
D=experiments/data
mkdir -p "$OUT"
run() {  # name limit [extra args]
  local w=$1 n=$2; shift 2
  echo "== $w start $(date -u +%FT%TZ)" >> "$OUT/queue.log"
  $PY experiments/run_workflow.py --workflow workflows/$w.orch --data $D/$w.jsonl --out "$OUT/$w" \
      --limit "$n" "$@" >> "$OUT/$w.log" 2>&1
  echo "== $w exit $? $(date -u +%FT%TZ)" >> "$OUT/queue.log"
}
if [ ! -s "$OUT/transparency.json" ]; then
  echo "== transparency start $(date -u +%FT%TZ)" >> "$OUT/queue.log"
  $PY experiments/transparency.py --output "$OUT/transparency.json" > "$OUT/transparency.log" 2>&1
  echo "== transparency exit $? $(date -u +%FT%TZ)" >> "$OUT/queue.log"
fi
run switch 210 --keep response,intention,llm_result
run routing 150 --keep answer,decision
run chaining 150 --keep final,gate,joke
run evaluator 100 --keep joke,stop
run email 152 --keep reply,route,cls
run orchestrator 100 --keep report,plan
run calculator 100 --keep out,done
run crag 150 --keep answer,search --corpus $D/crag_corpus.jsonl --web $D/crag_web.jsonl
run adaptive 60 --keep gen,src,have,done --corpus $D/adaptive_corpus.jsonl --web $D/adaptive_web.jsonl
echo "== all done $(date -u +%FT%TZ)" >> "$OUT/queue.log"
