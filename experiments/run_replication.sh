#!/usr/bin/env bash
# Cross-family replication on Qwen 2.5 1.5B (different tokenizer and chat template).
# Usage: experiments/run_replication.sh OUT_DIR
set -u
OUT=${1:?output directory}
PY=${PYTHON:-python}
D=experiments/data
mkdir -p "$OUT"
run() {
  local w=$1 n=$2; shift 2
  echo "== ${w}_qwen start $(date -u +%FT%TZ)" >> "$OUT/queue.log"
  $PY experiments/run_workflow.py --workflow workflows/replication/${w}_qwen.orch --data $D/$w.jsonl \
      --out "$OUT/${w}" --limit "$n" "$@" >> "$OUT/${w}.log" 2>&1
  echo "== ${w}_qwen exit $? $(date -u +%FT%TZ)" >> "$OUT/queue.log"
}
run switch 210 --keep response,intention,llm_result
run email 152 --keep reply,route,cls
run crag 150 --keep answer,search --corpus $D/crag_corpus.jsonl --web $D/crag_web.jsonl
echo "== all done $(date -u +%FT%TZ)" >> "$OUT/queue.log"
