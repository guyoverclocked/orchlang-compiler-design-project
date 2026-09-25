#!/bin/sh
# Regenerates review_evidence/ from the commands that produce each file, so the
# evidence is always the current compiler's actual output.  Run from the
# repository root after `make check`; evaluation.txt is copied from the last
# `python bench/evaluate.py` run.
set -u
out=review_evidence
mkdir -p "$out"
run() { file="$1"; shift; "$@" > "$out/$file" 2>&1 || true; }

run test_output.txt              ./orchlang_tests
run valid_tokens.txt             ./orchc tokens  examples/valid/untrusted_endorsed.orch
run valid_ast.txt                ./orchc ast     examples/valid/untrusted_endorsed.orch
run valid_symbols.txt            ./orchc symbols examples/valid/untrusted_endorsed.orch
run valid_ir.txt                 ./orchc ir      examples/valid/branching_cost.orch
run analysis_report.txt          ./orchc certify examples/valid/untrusted_endorsed.orch
run lexical_errors.txt           ./orchc check   examples/invalid/lexical_errors.orch
run syntax_errors.txt            ./orchc check   examples/invalid/syntax_errors.orch
run multiple_errors.txt          ./orchc check   examples/invalid/multiple_errors.orch
run cost_derivation_branch.txt   ./orchc cost    examples/valid/branching_cost.orch
run cost_derivation_retry.txt    ./orchc cost    examples/valid/bounded_retry.orch
run cost_require_violated.txt    ./orchc check   examples/invalid/require_violated.orch
run cost_retry_overrun.txt       ./orchc check   examples/invalid/retry_budget.orch
run flow_implicit.txt            ./orchc check   examples/invalid/implicit_flow.orch
run flow_injection_to_sink.txt   ./orchc check   examples/invalid/untrusted_sink.orch
run flow_secret_to_sink.txt      ./orchc check   examples/invalid/secret_sink.orch
run relational_cost_channel.txt  ./orchc check   examples/invalid/cost_channel.orch
run relational_equal_bounds.txt  ./orchc check   examples/invalid/equal_bounds.orch
run relational_equal_size_sizes_rule.txt   ./orchc check audit/2026-09-25/equal_size_template.orch --relational-rule sizes
run relational_equal_size_content_rule.txt ./orchc check audit/2026-09-25/equal_size_template.orch
run paired_secret_0.txt          ./orchc run audit/2026-09-25/equal_size_template.orch --seed 3 --pin ticket=20 --pin enterprise=true  --provider content
run paired_secret_1.txt          ./orchc run audit/2026-09-25/equal_size_template.orch --seed 3 --pin ticket=20 --pin enterprise=false --provider content
run leakage_within_budget.txt    ./orchc check   bench/leakage/accept/OneBitTier.orch
run real_agentdojo_banking0.txt  ./orchc check   bench/real/ad-banking-0.orch
run real_agentdojo_banking0_annotated.txt  ./orchc check bench/real/ad-banking-0.annotated.orch
if [ -f bench/results/evaluation.txt ]; then cp bench/results/evaluation.txt "$out/evaluation.txt"; fi
echo "review_evidence regenerated"
