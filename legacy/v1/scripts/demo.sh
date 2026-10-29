#!/bin/sh
set -eu

make clean
make check
./orchc tokens examples/valid/support_triage.orch
./orchc ast examples/valid/support_triage.orch
./orchc symbols examples/valid/support_triage.orch
./orchc check examples/invalid/multiple_errors.orch || true
./orchc ir examples/valid/support_triage.orch
