# Changes after the inference freeze

The real-model completion campaign uses immutable implementation commit `6a24fe8`.
Completed records bind that exact implementation. The final review branch also
contains `ac9e5c4`, which adds three failure-path safeguards:

- serialize known prefix usage and unconfirmed reservations in failure records;
- clear prior execution trace state before a new admission attempt;
- reject budget keys that do not name configured model contracts.

Documentation also distinguishes logical isolated-padding usage from an actual
provider invoice and sizing targets from sound static bounds. These wording
corrections do not change inference behavior.

The model downloader now writes SHA pins and can reproduce the completion
campaign's exact two-stop Llama profile with `--completion-profile`; its historical
default remains separately available. `--configure-only` verifies local files
without downloading them. This corrects reproduction tooling, not retained data.

These changes do not alter the successful no-budget executions in the frozen
campaign. Their separate regression and 6,000-execution correspondence run are
retained in `evidence/core`. The final software and the experimental implementation
are identified separately; the old records are not relabelled as new executions.

Replication workflows may execute concurrently as separate CPU workers, each
with four threads and a separate backend. This is an orchestration setting, not
workflow concurrency in the semantics. Wall-clock times are descriptive and are
not used for an inter-campaign performance or timing-security claim.

## Frontend and protocol correction (`913530b`)

A cross-layer test exposed a value-ordering error: rendering around symbolic
markers and substituting afterwards does not trim the evaluated message. Two
of three adversarial whitespace cases differed from direct rendering. The fix
evaluates the whole message first, represents trim explicitly in Python and Lean,
and stops interpreting literal NUL bytes in prompts as substitution markers.

The regressions compare 360 source requests across two template families, five
layouts and 36 boundary values. Lean's whitespace classification is checked
over every Python code point. One targeted program covers 32 contexts, two
kernels and five variants (320 executions), alongside 6,000 generated executions.
All 33 configured tests and 6,320 operational comparisons pass. Three real-model
boundary pairs preserve outputs and have one intended request hash.

The Unicode cases also exposed LF framing versus Python `splitlines()` in the
JSON bridge. It now treats Unicode separators as data, decodes UTF-8 and rejects
wrong verdict counts/types and inconsistent exit statuses. Empty candidate maps
and missing verdict batches cannot yield vacuous receipts.

The application campaign stays frozen at `6a24fe8`. Its requests and costs are
not relabelled as executions of the corrected frontend. Its versioned results
remain observations of that implementation; the small boundary cohort does not
establish unchanged application accuracy after this correction. Reproduction and
source-artifact checking must use the matching implementation version.


## Canonical requests and evidence reuse (`5b44617`)

Concatenation is normalized without moving pieces through trim or escape.
This prevents a change in message/frame grouping from changing sizing slack for
an otherwise identical request. Exact comparison confirms that the old and current
source bindings, model contracts and all four candidate core programs are equal
for switch, email and corrective-RAG Qwen adaptations. The equality receipts are
in `evidence/compiler-identity`. This supports core-level evidence comparison;
it is not a physical-runtime equivalence theorem or a relabelling of old inference.
The Llama frontend qualification above remains explicit.

The scheduling parent for the existing Qwen switch worker was retired while its
active inference process continued. A disposable process-survival probe and a
preserved-prefix SHA receipt document this transition. The remaining scheduler
waits for switch completion before email and for main corrective-RAG completion
before starting Qwen corrective RAG. This bounds memory contention and prevents
two writers from entering one evidence directory. All inference remains at four
threads per worker. The control scripts are historical Windows orchestration
snapshots; use the portable experiment runners for a fresh reproduction.

## Completed evidence and analysis (25 October 2026)

All planned missing observations are now retained: 210 main completion pairs,
512 cross-family replication pairs and 21 separate conformance pairs. The strict
evidence generator passes with no missing, failed, mismatched or truncated pair.
The independent audit re-tokenizes requests and reconstructs visible prefixes
for 1,486 new execution records containing 5,831 model events; all checks pass,
and a deliberately corrupted count is detected.

The Qwen corrective-RAG decision cohort has only one observed class. This exposed a table
writer's assumption that every classifier result contains prediction mutual
information. The analysis now reports zero prediction information for the
single-class case and an explicit unavailable value without scikit-learn. This
repairs analysis output only; no retained execution or inference implementation
was changed. A 100-percent single-class score is uninformative about leakage.

## Independent-referee revision (25 October 2026)

`c2bb75c` freezes the new admission-domain proof, refusal/policy-omission examples,
and local-instrumentation experiment. Its 48 application pairs and 192 primitive
pairs complete with equal paired outputs and exact shaped/count observations.
The local JSON audit reconciles 646 model calls; 224 natural calls expose a
yielded stop ID outside the declared logical returned-ID count. Six of 18
unmodified greedy comparisons differ from historical saved fields. These facts
are retained separately; the old inference denominator/version is unchanged.

`9743f2d` fixes runner provenance when a reviewer uses a source ZIP without Git.
A null Git identity and export-manifest hash replace a failed Git query or an
incorrect parent-repository attribution. Compiler, runtime and Lean proof bytes
are unchanged from `c2bb75c`. This maintenance commit also adds an authored
two-route baseline experiment: 20 real executions and 24 local model calls,
including actual cover generation, are separate from the main revision protocol.
All saved fields agree, and alignment uses one model call where all-branches
shaping uses two. Application switch controls retain equal usage for these two
strategies, so no universal saving is inferred.

The 37-test configured suite includes two admission and two export-provenance
regressions in addition to the old 33. A fresh extracted-package model pair and
standalone checker exercise final runner portability; replay receipts travel in
the outer review delivery. This is same-machine automated replay, not independent
human reproduction or a public archival deposit.
