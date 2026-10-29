# Verified analysis revision: completed local evidence

Local date: 24 October 2026, Asia/Calcutta. JSON timestamps are UTC. These are
local development runs, not independent human validation. USD 0 spent; no model
inference or provider API was used by these campaigns.

| Run | Status | Result |
|---|---|---|
| dataflow-precision-v1 | Failed, retained | 32 expected-core source reconstruction mismatches; source sequence association repaired in v2 |
| dataflow-precision-v2 | Completed | 80 source cases: baseline 8/new 64; 72 core cases: baseline 8/new 64; 3,648 contexts; zero accepted finite counterexamples or execution disagreements |
| dataflow-regression-v1 | Completed | Original 256 pipelines: Lean 16/C++ 8; 3,072 contexts; eight core boundaries; all negative checks pass |
| aggregate-reordering-v1 | Completed | 256 source cases: ordered 16/aggregate 28; 12 gains all differ under ordered observation; 512 contexts/2,048 paths; eight malformed cases rejected; three authored source illustrations |
| aggregate-private-results-v1 | Completed | Same 256 cases/512 contexts/2,048 paths; joint aggregate/complete-response multiset preserved for all 28 accepts; zero three-way disagreements; ordinary JSON output unchanged |

The ordered precision gains preserve the original full state-transformer
judgment. The aggregate gains rely on a separately named observer that discards
order, and apply only to two independent closed calls per arm. They do not
certify response-dependent reordering, content confidentiality or source budgets.
See `docs/VERIFIED_PRECISION.md` for the exact theorems and policy-difference table.

The manifests record an evolving working tree with source-file hashes. They do
not claim a clean commit freeze. A final release rerun can bind the same protocol
to a committed source snapshot; the current raw results retain their provenance.
