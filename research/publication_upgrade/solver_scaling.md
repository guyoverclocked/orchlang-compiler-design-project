# Trace-equivalence solver: diagnosis and scaling study

## Finding

The supplied audit correctly observed that a symmetric graph with 128 calls
per secret arm returned `unknown`, and that increasing the declared limits did
not help. The cap was safe: the report made no equality claim. It was also
misleading as a usability signal because the v1 report suppressed the reason.

I reproduced the old path before the fix by instrumenting its `_Unknown`
exception. Semantic closure and the exact row-span analysis had completed; the
producer failed in `_preflight_independent_replay` with
`independent replay basis-word product byte-work cap reached`. The preflight
charged every certificate word from the initial vector. For a chain, basis
words are successive prefixes of one path, so this repeated the same exact
matrix-vector products many times. The separate replay implementation used the
same from-scratch reconstruction strategy. This was avoidable verifier work,
not evidence that the model's semantic state closure or exact arithmetic had
reached its configured cap.

## Change and exactness boundary

The producer preflight and independent replayer now build a prefix trie for
each scenario pair. Each distinct word prefix `w` is evaluated once as
`mu A_w`; a child prefix extends its parent's exact rational row by the same
label matrix as before. Every certificate row is still compared coefficient
for coefficient with the independently reconstructed `mu A_w`, and the
replayer still checks independence, closure under every label matrix, stop and
nonterminal output, or an exact finite witness. The optimization changes
recomputation and deterministic work accounting. It does not change the
observer, state system, row-span criterion, or accepted theorem.

This is an implementation optimization, not a new equivalence algorithm.
Classical weighted-automata work already describes traversing the word tree
and pruning linearly dependent vectors. Kiefer et al. present that construction
and a deterministic bookkeeping improvement, while their later paper studies
equivalence for automata weighted over the rationals using randomized parallel
algorithms. These are related foundations, not a claim that their results prove
this certificate checker. OrchLang's contribution remains its selected
usage observer, finite rational model, fail-closed caps, and replayable
certificate path. See the original CAV paper by
[Kiefer et al. (2011)](https://people.mpi-sws.org/~joel/publications/langeqprobaut11.pdf)
and the rational-weighted-automata treatment by
[Kiefer et al. (2013)](https://doi.org/10.2168/LMCS-9(1:8)2013).

The report format is now version 2. UNKNOWN reports carry a bounded diagnostic
object with an enumerated reason and phase, plus deterministic work counters.
They still omit the closed system, alphabet, certificate, and claim. Scalar
counts for a fully completed closure may appear in telemetry; they do not
contain a partial system or establish a result. The replayer strictly checks
v2 metadata and continues to accept the prior v1 schema. It treats producer
telemetry as advisory and measures its own work independently.

## Reproduction

From the repository root, run:

```sh
python3 research/publication_upgrade/solver_scaling.py \
  --repetitions 5 \
  --sizes 2,8,16,32,64,128,256 \
  --output research/publication_upgrade/solver_scaling.json \
  --input-dir research/publication_upgrade/solver_inputs
python3 research/publication_upgrade/run_solver_baseline.py \
  --repetitions 5 \
  --sizes 2,8,16,32,64,128,256 \
  --output research/publication_upgrade/solver_scaling_baseline.json
python3 research/publication_upgrade/plot_solver_scaling.py \
  research/publication_upgrade/solver_scaling.json \
  research/publication_upgrade/solver_scaling \
  --baseline research/publication_upgrade/solver_scaling_baseline.json
```

The generator writes the exact graph inputs and kernel into `solver_inputs/`;
the JSON records their SHA-256 digests. Each measurement uses a fresh Python
worker process. One warmup runs per size by default, followed by five reported
repetitions. Producer analysis and independent certificate replay have
separate wall-time and OS high-water RSS measurements. The SVG is generated
separately from the saved JSON, so rendering the figure does not rerun or alter
the paired study. It writes both SVG and PDF plus a JSON file containing the
Matplotlib version and input/output hashes. Matplotlib is only needed for
figures; the producer, replayer, and scaling data collection use the standard
library. The baseline helper extracts commit
`5aa4ebc669a3fbae72d9a605be250624fd0bcbf5` to a temporary directory and runs
the same worker against those original producer and replay modules. It checks
that the baseline run used the same frozen input hashes as the optimized run.
Both result files record implementation source hashes and the study-worker
hash. The old producer's UNKNOWN report omitted meter data, so the harness
instruments its existing deterministic meter and closure return values in the
isolated process; this does not change its limits or analysis path.

The family contains two mirrored, deterministic call chains whose every call
has the same resolved contract and point-mass token usage. Both supplied
secret scenarios therefore have identical finite ordered usage-word laws.
The measured size is calls per arm. This is one controlled synthetic family;
it does not estimate performance on third-party workflows. Reported work-byte
counters are deterministic conservative meters, not process memory. RSS
includes the Python interpreter and is specific to this machine and runtime.

## Results

The medians, per-run samples, input hashes, implementation hashes, and status
counts are in [`solver_scaling.json`](solver_scaling.json) and
[`solver_scaling_baseline.json`](solver_scaling_baseline.json). The paired
Matplotlib figures are [`solver_scaling.svg`](solver_scaling.svg) and
[`solver_scaling.pdf`](solver_scaling.pdf); plotting provenance is recorded in
[`solver_scaling_plot_metadata.json`](solver_scaling_plot_metadata.json). The
same-machine comparison used seven frozen inputs, one warmup and five measured
repetitions per size. The graph/kernel hashes match exactly across both files.
Each producer/replayer wall timer starts after module imports; high-water RSS
includes interpreter startup and imports for both versions. The comparison is
valid for runs that both complete, while UNKNOWN timing is censored by an
early resource stop and must not be read as solver speed.

| Calls per arm | Original producer / replay | Updated producer / replay | Interpretation |
| ---: | --- | --- | --- |
| 2 | 5/5 equal / 5/5 verified | 5/5 equal / 5/5 verified | Same result |
| 8 | 5/5 equal / 5/5 verified | 5/5 equal / 5/5 verified | Same result |
| 16 | 5/5 equal / 5/5 verified | 5/5 equal / 5/5 verified | Same result |
| 32 | 5/5 equal / 5/5 verified | 5/5 equal / 5/5 verified | Same result |
| 64 | 5/5 equal / 5/5 verified | 5/5 equal / 5/5 verified | Direct performance comparison |
| 128 | 5/5 UNKNOWN / no certificate | 5/5 equal / 5/5 verified | Crosses the former default-cap boundary |
| 256 | 5/5 UNKNOWN / no certificate | 5/5 UNKNOWN / no certificate | Exposes the remaining work cap |

At 64 calls per arm, both implementations complete, so their replayer timings
are directly comparable. Use the recorded medians and min/max samples in the
paired JSONs; fresh machine runs naturally change the wall-time and RSS values.
Independently measured verifier work fell from
9,972,749 to 1,784,025 deterministic bytes, including the newly reserved parsed
basis-row storage. The basis-word matrix-product
estimate fell from 536,640 to 16,512 matrix-entry units because shared prefixes
are evaluated once. The study supports reduced verifier work in the
nested-prefix family. It does not establish a general time or memory reduction.

At 128 calls per arm, the old producer completed semantic closure (258 states,
256 transitions) and row-space analysis, then returned UNKNOWN while estimating
independent replay of certificate basis words. Its meter had consumed
67,081,608 of the 67,108,864-byte budget before attempting a 32,896-byte
product charge. The updated producer proves equality and its independent
replayer verifies the report in all five runs. There is no old replay-time baseline
at this size because the old producer did not emit a certificate. The report
size and process RSS are recorded in the paired JSONs.

At 256 calls per arm, both versions safely return UNKNOWN after completing the
same 514-state, 512-transition closure. The old cap event was another repeated
product estimate in replay closure checking; the updated diagnostic reports
`BYTE_WORK_CAP` in `certificate_replay_preflight`, during closure membership,
with 67,116,168 bytes observed against the 67,108,864-byte limit. The updated
report includes only bounded diagnostics and scalar closure telemetry; it has
no partial system, certificate, or equality claim. This is a concrete
improvement in observability and extends successful work through 128 calls per
arm, but the 256-call UNKNOWN remains a real default-cap limit.

This is one synthetic, nested-prefix family. It supports no general
scalability guarantee and no claim of a new equivalence algorithm. Further
performance claims need workflows varying branch count, outcome support,
history depth, alphabet size, rational denominator size, and scenario count.
