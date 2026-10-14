# Run and provenance notes

The preregistration was timestamped `2026-10-14 16:09:48 UTC` before any worker timing. It fixes the question, finite rational kernel assumptions, outcome definitions, family dimensions, source snapshots, 20-second worker cap, one warmup, five measured repetitions, and summary treatment of UNKNOWN. Frozen input inventory SHA-256: `d21bf701827c285d7d9424774fdda4bd2f42c7df8b8be5126288bb9710992efb`. Generator SHA-256: `adf213eb40f3a7bf01dfd906fc3903a06c31d549003c4c53f104679b891ac42c`.

The seven primary input cases came from the existing `research/publication_upgrade/solver_scaling.py` generator and byte-match its frozen graph/kernel fixtures. Primary current and 5aa pre-optimization runs used the existing scaling scripts without source edits; only their input/output destinations were redirected into this study's output directory. The primary result files preserve their own raw samples and protocol metadata.

The structured run used 27 frozen cases. Each case had separate fresh worker processes for exact production, exact replay, bisimulation production, and bisimulation replay. Seven preregistered cases additionally ran exact production and replay under frozen commit `5aa4ebc669a3fbae72d9a605be250624fd0bcbf5`. Each output row preserves status, call time, process high-water RSS, report/certificate sizes where applicable, diagnostic/status counters, state/transition/label counts, witness lengths, and bounded-work values exposed by the operation. Replay used a freshly produced report for every repetition, including UNKNOWN reports. No timing worker was rerun after the normative final artifact was written.

The final normative raw file is [`structured_results.json`](../../../output/scp_strengthening/scalability/structured_results.json), SHA-256 `b377646d3c2b49a5e64504f45cfa6c69cb8f2c2ef548af106e9a5636d1b4b70a`. It records 122 groups, each with one warmup and five separately numbered measured rows, for 732 rows total. The final protocol embeds hashes for the preregistration, worker, input generator, primary script, and compared implementation sources. The old rc2/dd97 snapshot has no audit-tree diff from current across the registered modules; exact producer/replayer hashes are identical, so it was not timed as a redundant arm.

The previous structured-run files are retained in output for audit, but are not result sources:

| File | Why it is retained | Use |
|---|---|---|
| `structured_results_run1_hash_binding_diagnostic.json` | First bisimulation replay exposed a mismatch between canonical API hashes and the frozen-byte replay contract. The harness was corrected to bind the report to frozen input hashes. | Diagnostics only; do not cite as study data. |
| `structured_results_run2_valid_rows_provisional_summary.json` | Rows were valid, but summary aggregation omitted literal `unequal` from completed outcomes. | Provisional; superseded. |
| `structured_results_run3_provisional_mixed_version_summaries.json` | Unequal counting was fixed, but current and 5aa rows were not kept in separate summary groups. | Provisional; superseded. |
| `structured_results_run4_version_separated_no_bisim_work_counters.json` | Version-separated statuses were valid, but Bisim counters were read from the wrong report field and absent from these rows. | Provisional; superseded. |
| `structured_results.json` | Final run uses the corrected hash binding, complete status grouping, and Bisim producer/replayer bounded-work fields. | Normative raw rows and summaries. |

The executable validation `validate_structured_results.py` passed after the final run. It tested aggregation on a six-group synthetic sample (current and 5aa versions crossed with equal, unequal, and UNKNOWN cases) and confirmed known version-separated medians, status retention, and UNKNOWN exclusion. It also recomputed the final summaries from raw rows, checked all 122 groups against the preregistered repetition matrix, verified the required status totals, and inspected the saved history-conditioned exact witness.

The results remain bounded by the scope stated in [`RESULTS.md`](RESULTS.md) and the primary-method assumptions and citations in [`PREREGISTRATION.md`](PREREGISTRATION.md). No source under `audit/`, no old scaling result/protocol, and no manuscript was edited; no commit was made.
