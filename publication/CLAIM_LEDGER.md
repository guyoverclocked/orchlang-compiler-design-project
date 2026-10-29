# Claim-to-evidence ledger

## Current second-round revision, 29 October 2026

| Claim | Exact support | Status and boundary |
|---|---|---|
| One corrected implementation covers the full planned study | `evidence/round2-homogeneous`, `round2-full-audit.json` | 1,684/1,684 pairs at clean 41a7d81; saved equality and static shaped traces; 3,368 records and 10,698 model calls |
| Actual workflow candidates pass compositional admission | `orchlang/admission.py`, `proof/StaticAdmissionCLI.lean`, `round2-concrete-admission-v3` | All twelve variants at context 21,504; explicit buffers, alpha/delta tokenizer assumption and trusted native correspondence |
| Guard coverage and bounded execution are measured | `round2-analysis-v2/summary.json` | 1,682/1,684 input guards; two Calculator exclusions; 24 equal full-store/shape pairs; 188 audited calls; 36 tool clips, zero response clips |
| The corrected decoder retains complete pieces | `round2-vocabulary-v2`, three decoder regressions | Exhaustive native tables; maximum raw piece bytes 128; UTF-8 replacement expansion is handled by a separate buffer |
| One native prefill fixes the size projection | `round2-native-prefill` | All 36 attempts; 128 then 23 single-token submissions; sequence metadata reveals real length in every case |
| Joint prefill is universally transparent | Native prototype attempts | Not claimed; size-128 configurations preserve 11/12 each, microbatch one preserves 12/12 only in its finite cohort |
| Categorical grading improves this port's measured answer score | `round2-categorical-full`, `round2-analysis-v2` | 150 equal pairs, 600 categorical grades; 57 to 84 correct, 28 improved and one regressed; inherited scorer, combined prompt/grammar intervention |
| Both categorical routes occur uniformly | Same | False; 149 searches and one omission; no balanced branch-population claim |
| Final checks and academic edit preserve scientific content | `round2-core`, `round2-static-diagnostics`, `round2-manuscript-qa.json` | 47 configured tests; Lean checks; 72 static candidates; protected numbers/equations/citations; every PDF page inspected |
| Native admission and failures are fully verified | No such evidence | Not claimed; 32,768-context pilot allocation failure retained separately; tokenizer/parser/serving remain trusted |

The rows below document earlier versions and keep their original denominators.

## Earlier final revision, 29 October 2026

| Claim | Exact support | Status and boundary |
|---|---|---|
| A compositional certificate implies RunsIn for every guarded input and tape | `proof/AdmissionDomain.lean`: `static_certificate_sound`, `static_certificate_implies_RunsIn`, `static_certificate_domain` | Mechanized, no sorryAx; explicit envelope primitive contracts; no proof that heuristic GGUF targets satisfy them |
| The certificate checks useful calls and cover work without execution lookahead | `staticCertificate`, `boundE`, `coverCertificate`; ten `StaticAdmissionChecks.lean` guards | Executable Lean-level sufficient checker; no frontend inference of concrete GGUF envelope contracts |
| Uniform corrected-release pairs preserve fields and fixed shapes | `evidence/final-release-2026-10-29/summary.json` | 24 pairs across 12 variants, commit ee13731; targeted length extremes, not a full 1,684-pair rerun |
| Final local model records reconcile | `evidence/final-release-2026-10-29/independent-audit.json` | 48 records and 191 model calls, pinned request re-tokenization, prefix/ledger/eval checks and changed-count negative control |
| Qwen CRAG's grader vocabulary differs from its parser | `evidence/final-diagnostics-2026-10-29/diagnostics.json` | 600 parseable JSON grades, 518 numeric; none reaches its cap; parser-only normalization still routes all 150 inputs to search |
| Shapes are stable under tested alignment weights | Same diagnostics | 72 Lean-accepted candidates, 12 variants, six weights; no new inference or general optimality claim |
| Multi-token declared stops are supported | `runtime.LlamaBackend.declared_stop_ids`, `tests/test_stop_contract.py` | False: unsupported multi-token/empty declarations are explicitly rejected before workflow inference |
| A constant exported trace establishes model-server input hiding | Lower-level eval records and scope discussion | False for isolated prefill; two passes expose actual request length. Normalize reports is an applicable cheaper log-observer baseline |

The final configured test log has 40 passing tests. Fresh correspondence repeats
6,320 executions and 604 validator checks; fresh differential testing covers
1,000 programs, 5,000 Lean checks and 16,000 comparisons. The entries below retain
the older cohorts and supplementary implementation provenance.

| Claim | Exact support | Status and limit |
|---|---|---|
| The original disk work was preserved | `evidence/core/disk-before.json`, `disk-after.json` and `preservation.json` | Passed: 1,181 files, HEAD, branch, status and refs unchanged |
| Candidate shaping cannot choose its own original or secret list at the source-bound boundary | `orchlang/assurance.py`, source-binding tests, standalone check receipt | Implemented and tested; Python reader/lowering remain trusted |
| Accepted core programs have equal logical usage traces for public-equal stores | `proof/ShapeCore.lean`: `noninterference`, `trace_noninterference`, `secret_inputs_sound` | Mechanized under `World.Conforms`, discipline, sites and declared-secret premises |
| Accepted shaping preserves useful store behavior | `erase_correct`, `validateProgram_sound` | Mechanized under `World.Transparent` and caps; original source must already correspond to the bound core |
| A complete shape has an exact per-model usage triple and satisfies an admitted budget | `shape_usage_exact`, `shape_budget_sound` | Mechanized logical counts; no currency, timing, concurrency or failure theorem |
| Complete requests are checked before dispatch; bad returned counts are detected | `runtime.py`, contract regression suite | Tested execution behavior; post-dispatch rejection cannot undo a leak |
| Budget units remain separate; unknown dispatch usage is not zero | `ledger.py`, unit/admission tests | Sequential Python implementation; no ownership or concurrent refinement proof |
| Three operational implementations agree in the finite audit world | `evidence/core/latest-correspondence/manifest.json`, all cases and expected results | 150 generated programs plus one targeted template program; 6,320 executions and 604 validator checks; character units |
| Generated differential cases pass | `evidence/core/unified-differential-v2.json` | 1,000 programs, 5,000 Lean checks, 16,000 comparisons; authored finite grammar |
| Actual GGUF templates and padding are tested | Configured unit log; model hashes | Finite byte/token checks on the named files; model-free runs skip two tests |
| Historical primary evidence contains 962 matching pairs | `evidence/core/retained-record-audit.json`; `experiments/results/runs` | Seven workflows; equality of saved outputs, not every hidden intermediate state |
| Historical shaped full traces equal static shapes | Same raw audit | Tool names included; 962/962 and no recorded truncation; logical host observer only |
| Median historical overhead is 1.83 times weighted logical usage | `evidence/historical-analysis/results.json`, `build_evidence.py` | Input + 4 output; range 1.13--14.47; no provider invoice |
| Full-observer attack reanalysis is reproducible | `experiments/analyze.py`, `aggregate.py`, retained analysis | Descriptive five-fold RF; no permutation significance or held-out deployment claim |
| Timing is protected | None | **Not claimed**; latency-augmented maximum BA is 100 percent |
| Preserved results are accurate or useful | Workflow-specific task scores only | **No general claim**; calculator 1 percent accuracy |
| The incoming 210-mutant study rejects all observed leaking faults | `experiments/results/mutation.json` | 103 observed leaking mutants, 12 operators, 18 accepted nonleaking mutants; finite oracle |
| The disk implementation is reproduced | Fresh `unified-disk-core` manifests/logs; disk evidence | 106 C++ tests, 82 Python tests, four Lean files; original framework replay separately 24/24 |
| The disk source checker is more permissive on the authored grammar | Disk precision manifest and cases | 64/80 versus 8/80, not a real-world population estimate |
| Aggregate and ordered observers are interchangeable | Counterexamples in disk aggregate study | **False**; 12 additional aggregate accepts intentionally differ in order |
| Exact tokenizer accounting supports every configuration | Disk exact-accounting summary | **False**; 40/64 supported, 24 explicitly unsupported |
| All planned missing model experiments and replication are complete | `evidence-summary.json`, completion raw directories, strict generator exit | Passed: 210/210 main completion, 512/512 Qwen replication, 21/21 separate conformance pairs; 1,172 total main pairs across versioned cohorts |
| New private accounting evidence reconciles with the public traces | `evidence/core/record-audit-final.json`, `audit_execution.py` | Passed: 1,486 records, 5,831 model events, pinned request re-tokenization, visible-prefix reconstruction and negative count control; not physical attestation |
| The Python frontend and production backend are verified | None | **Not claimed**; finite operational checks and explicit trusted boundary |
| The method is the first constant-resource, padding or routing-metadata defense | Prior-art matrix | **Not claimed**; component techniques and threat are established |
| The combined artifact is publicly archived and accepted by SCP | None | **Pending external actions**; local package and journal fit are not acceptance |

Numeric prose changes from either parent were scientific corrections based on
raw evidence, not stylistic edits. Subsequent clarity editing preserves the
corrected numbers, hypotheses and citations. The manuscript deliberately reports
negative results that the earlier draft's broad wording obscured.


Latest cross-layer receipts are under `evidence/core/latest-correspondence` and
`evidence/core/latest-unit-tests.log`. The three Qwen compiler-identity receipts
compare the frozen and corrected source bindings, model contracts and all four
candidate programs exactly. `evidence/template-boundary` contains three separate
real-model controls. `evidence/budget-check-v2` contains a successful exact-budget
control and an expected insufficient-budget refusal before any dispatch.
Application inference is still attributed to its recorded implementation.

For the final paper, the logical observer reads wrapper accounting records.
Normalization is an applicable alternative with lower execution cost. Executed
cover work tests resource envelopes and supplies no additional confidentiality at
that exported-log interface. An external billing/gateway adapter is unverified.

## Independent-referee revision

| Claim | Exact support | Status and limit |
|---|---|---|
| Fixed-shape execution needs conformance only for reached request contracts | `proof/AdmissionDomain.lean`: `shape_exec_on`; actual Lean axiom log | Mechanized under `ConformsOn` and `RunsIn`; not a physical refinement |
| Refusal/completion observations agree | `admitted_noninterference`, `certified_domain_noninterference` | Requires uniform admission or an all-inputs/all-tapes domain certificate; ideal adapter is noncomputable |
| Fail-closed admission always protects secret lengths | `evidence/referee-revision/admission-domain.json` | **False**; short input completes and oversized input refuses; separate finite domain passes 45 executions |
| Lost dispatch remains observable with reserved usage | `tests/test_admission_domain.py`, configured 35-test log | Passed negative regression; no failure-noninterference claim |
| Source-derived policy binding has a consequential rejection | `evidence/referee-revision/source-binding-case.json` | Actual Lean accepts weakened-policy core, rejects it under source policy, accepts repair |
| Corrected code preserves paired visible results in a new bounded cohort | `evidence/referee-revision/current-code-v1/workflow-attempts.jsonl` and reconciled summary | 48 planned pairs, three adaptations, two families, two temperatures; finite selected cohort, not corpus accuracy |
| Local inference exposes the same observer as a provider bill | Local eval/generate records and EOS/prefill reconciliation | **Not claimed**; local API observations are separately trusted; provider authority remains absent |
| New primitive testing proves general transparency | 192-pair attempted matrix and its summary | **Not claimed**; fixed finite prompt/stop/cap/seed/settings falsification only |
| The final software was independently reproduced by a human on a new machine | `REPLAY_CHECKLIST.md` | **Pending**; local fresh-directory replay is identified separately |

The referee revision does not change the 1,172 primary-study / 512 replication
denominators. New comparisons also report divergence from old saved fields;
preservation within a current original/shaped pair does not establish equality
with an older implementation's result.
