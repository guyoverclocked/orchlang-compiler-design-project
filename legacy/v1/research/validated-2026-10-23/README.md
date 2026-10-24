# Retained clean-snapshot evidence

These are successful local engineering runs, not independent human replication.
Raw JSON/text files are copied byte-for-byte from immutable output directories
outside the clean checkout. See files.json for content hashes. Binary executables
are excluded from the source artifact; build commands and binary hashes remain.

Test source snapshot: `6f325be2d00b8f617b09fb3f7f3f50b4e8f91f82` (local v3).
Amended external corpus/runner: `7a0095dd4346dae7045308ceffcc60ede8962647` (v4).
C++ source/include bytes in those snapshots are identical. External execution
uses the binary freshly built at v3 and retains its exact SHA256. Snapshot v4
changes corpus naming, failure recording, and supporting prose, not C++ analysis.
Git bundles in the local deliverable reconstruct both tested source snapshots.
Public archival release is pending; these are not advertised as public tags.

| Directory | Result and scope |
|---|---|
| clean-cpu-v3 | 106 C++ tests; 31 Python tests; both Lean proofs; 23 existing cost workflows/115 mock runs |
| generated-v3 | 576 programs; 24 accepted; zero supplied-kernel accepted counterexamples; no trace-identity advantage; 16 kernel-specific equivalent rejections |
| certificates-v3 | 624 Lean checks; 24 source certificates; 48 modified sources/24 altered plans rejected; four malformed JSON batches fail closed |
| replay-v3 | 12 finite text cases; 48 exact weighted paths; independent replay/reference agreement |
| tokenizers-v3 | 24 fixed encodings; 13 exceed byte/divisor estimate; six of ten concatenations nonadditive |
| mutations-v3 | Four successfully compiled semantic faults detected by behavioral failures |
| external-v4 | 11 authored projections; 220 mock executions; zero component bound violations and baseline disagreements |
| tables | Machine-generated summary and per-projection table, with source manifest hashes |

The complete external run follows a disclosed amendment after a parser failure;
see research/protocol-amendments.md. Earlier partial outcomes were not retained
by the aborting runner and are not used. The patched runner persists each command.
The census remains 21 candidates with ten exclusions; zero original applications
or faithful functional translations were executed. There are no provider privacy,
population significance, throughput, external adoption or precision-superiority
claims. No model inference or API key was used. Paid spending/reservations: $0.
