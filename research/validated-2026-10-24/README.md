# Text-dataflow strengthening: retained evidence

Clean source/protocol freeze: `00420ef202dc260fc98237ac584a6210a61e1e5e`.
Local date: 24 October 2026, Asia/Calcutta. Raw manifests use UTC timestamps.
These are local engineering runs, not independent human review or reproduction.
files.json hashes the copied records; failed/incomplete runs are also retained.

| Run | Status and scope |
|---|---|
| dataflow-v5 | Completed: 256 source programs, 16 accepted, 3,072 execution contexts; zero source reconstruction, normalization, Lean/reference or Lean/replay disagreements; zero accepted supplied-kernel counterexamples |
| dataflow-v5 boundaries | Eight hand-authored core cases, 23 weighted paths; includes equal-response-length/unequal-downstream witness, which is rejected |
| dataflow-v5 negative inputs | 32 modified sources, 16 altered plans and eight malformed/invalid evaluator inputs rejected |
| dataflow-cpu-v5 | Completed: 106 C++ tests, 47 Python tests, three Lean files checked; original cost/examples/regressions rerun |
| closed-dataflow-v5 | Completed: earlier 576-source/624-check campaign still passes with the tightened reader |
| dataflow-v4 | Failed: all execution comparisons agreed, but 240 authored sources violated E222; zero-argument syntax repair disclosed |
| dataflow-v3 | Incomplete/failed: combined JSON exceeded the transport guard; its stale `running` manifest is not evidence of completion |

The source generator constructs expected cores separately from the reader.
The kernels depend on actual request strings; responses feed later requests.
The eight boundaries are additional tests, not extra generated source programs.
Root outputs must be literal; source retry remains excluded. Core retry errors
are status values and bodies complete before retry decisions. The reference
erases lexical locals while the SSA core retains unreachable slots; conformance
compares requests/events, not those private store representations.

The C++ checker accepts eight cases, while the dataflow normalizer accepts 16.
C++ reports E230 in 192 cases because its PC-label policy differs. This is not a
precision ranking or authority to release secret contents. No general logic,
full source proof, held-out performance result or provider conformance is claimed.
The finite probability tables are checked by runtime conditions; their validity
is not a mechanized probability theorem. New proof assumptions and parser trust
remain explicit in docs/DATAFLOW_CERTIFICATES.md.

The compiled C++ executable used for secondary diagnostics was freshly built in
the earlier v3 CPU run. Its hash is in the campaign manifest; C++ source bytes
are unchanged. The new CPU run also rebuilds the compiler and confirms regressions.
See research/dataflow-development-notes.md for both protocol amendments.
No API key, inference, GPU or paid service was used. Spend/reservations: USD 0.

Final derived output is tables-v2. The original tables/ numeric summary is
unchanged, but its TeX used a diagnostic number inside a control-sequence name.
That rendering error was repaired in report_dataflow.py; the manuscript inputs
only the alphabetic macro output from tables-v2. All nine revised PDF pages were
rendered and visually checked, with no overfull boxes or unresolved citations.
