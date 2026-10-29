#!/usr/bin/env bash
# (Re)start the full evaluation in the background, resuming from recorded runs.
#
# Usage:  experiments/resume.sh RUNS_DIR
# Env:    PYTHON (python with requirements.txt installed), LEAN (lean 4.19.0 binary),
#         ORCHLANG_MODELS (models.json written by experiments/fetch_models.py)
#
# Safe to run repeatedly: every runner skips inputs already present in its
# orig.jsonl / ours.jsonl, and the transparency test is skipped once its output
# exists. It refuses to start if an evaluation is already running.
#
# Progress:  tail RUNS_DIR/queue.log ; wc -l RUNS_DIR/*/*.jsonl
# Stop:      kill the PID printed below (not `pkill -f`, which can match your own shell).
set -euo pipefail
RUNS=${1:?runs directory, e.g. out/runs}
: "${PYTHON:?set PYTHON}" "${LEAN:?set LEAN}" "${ORCHLANG_MODELS:?set ORCHLANG_MODELS}"
cd "$(dirname "$0")/.."
if ps -eo args | grep -v grep | grep -q "experiments/run_workflow.py"; then
  echo "an evaluation is already running; not starting another" >&2
  exit 1
fi
mkdir -p "$RUNS" "$RUNS/replication"
LOG="$RUNS/chain.log"
setsid nohup bash -c "bash experiments/run_all.sh '$RUNS' && bash experiments/run_replication.sh '$RUNS/replication'" \
  >> "$LOG" 2>&1 < /dev/null &
echo "started evaluation, pid $!; queue log: $RUNS/queue.log"
