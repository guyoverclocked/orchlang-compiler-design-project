# OrchLang SCP research artifact

## Third-round revision, 29 October 2026 (current)

The current manuscript is `paper/main.tex` / `paper/main.pdf`. Read
`THIRD_ROUND_RESPONSE_2026-10-29.md` for the point-by-point response.

- **Proofs.** `proof/RestrictedDomain.lean` and `proof/Utf8Envelope.lean` restate
  noninterference, preservation and budgets under restricted serving contracts
  and prove certified end-to-end theorems whose only run-time premise is the
  input guard. `python publication/check_proofs.py --output out/proofs.json`
  compiles all seven files with an axiom audit: 2,312 lines, 78 theorems, no
  `sorryAx`.
- **Certified study.** `python experiments/homogeneous_study.py campaign
  --byte-bounded --response-bytes 128 --context 21504 ...` runs every planned
  input in byte-bounded mode with a segmentation check before every dispatch.
  Evidence: `evidence/round3-certified-full`; analysis:
  `python publication/analyze_round3.py --certified <dir> --output <dir>`.
- **Boundary checks.** `experiments/serializer_roundtrip.py` (3,036 exact round
  trips; `--ascii-escaped` reproduces the fixed surrogate-escape defect),
  rerun correspondence, differential and fault-injection studies in
  `evidence/round3-checks`.

Earlier sections below describe earlier revisions and remain accurate for their
cohorts.

## Second-round revision, 29 October 2026

The current manuscript is `paper/main.tex` / `paper/main.pdf`. Read
`SECOND_ROUND_RESPONSE_2026-10-29.md` for the review response and
`ROUND2_RESEARCH_NOTES_2026-10-29.md` for the tested alternatives and remaining
research boundaries. `ACADEMIC_EDIT_ROUND2_2026-10-29.md` records the final prose
pass. Earlier review notes below describe earlier cohorts.

The full primary study is now homogeneous: **1,684/1,684 paired saved outputs
agree**, comprising 1,172 main pairs and 512 Qwen replication pairs, all at clean
implementation freeze `41a7d81f4756821cb3ce0d22e9aaf49930b4d7dc`. Every shaped trace
matches its static shape. The independent audit reconciles 3,368 execution
records and 10,698 model calls, including local eval/yield evidence and a
corrupted-count negative control. Production byte hashes still match this freeze.

`evidence/round2-homogeneous` contains every primary run and protocol;
`round2-full-audit.json` is its independent receipt. `round2-main-analysis` and
`round2-replication-analysis` contain the derived task, attack and cost results.
These runs replace the earlier version-fragmented tables in the main paper.
Historical raw observations remain immutable and are not pooled into this count.

The optional byte-bounded adapter exports actual source-bound candidates to
Lean's `staticCertificate`. All twelve variants pass at context 21,504;
their guard admits 1,682/1,684 planned inputs. The 24 separate executed pairs
preserve full runtime stores and certified shapes. See
`evidence/round2-concrete-admission-v3`. Both arms use explicit input, tool and
post-decoding response byte buffers. This is a declared interface, not a proof
of an unbounded native runtime. `round2-concrete-admission-v2` retains an earlier
32,768-context attempt that completed 16 pairs before device-memory allocation
failed at adaptive RAG, together with the exact hash-verified driver at failure.

The complete vocabulary scans in `round2-vocabulary-v2` find maximum raw native
piece length 128 bytes in all three GGUFs and expose the old fixed 32-byte decoder
buffer. The resizing decoder is included in the primary execution freeze.
Byte-BPE algorithm correspondence remains trusted; valid-UTF-8 finite tests
support the tokenizer assumption without proving native code.

`round2-native-prefill` tests one actual 128-token native submission with useful
and cover sequences. Its three configurations retain all 36 attempts. A
microbatch of one preserves 12/12 visible outputs; the two size-128 configurations
preserve 11/12 each. Sequence metadata reveals request length in every case.
`round2-categorical-full` separately evaluates a categorical prompt and constrained
JSON grammar on all 150 Qwen CRAG questions. Its grammar is a distinct model
contract and does not rewrite the primary cohort.

## Reproduce current checks

Use Python 3.12, Lean 4.19.0, `requirements-analysis.lock`, and the pinned GGUF
configuration. Native inference used llama-cpp-python 0.3.36 with llama.cpp
[build b11490 / commit 9c2e0e491](https://github.com/ggml-org/llama.cpp/releases/tag/b11490).
The protocol records the exact Windows Vulkan DLL hashes. The native directory
and model files are external dependencies; their bytes must match for an exact
backend replay. Use new output directories rather than overwriting evidence.

```powershell
$env:LEAN='C:\path\to\lean.exe'
$env:LEAN_PATH=(Resolve-Path proof).Path
$env:ORCHLANG_MODELS='C:\path\to\models.json'
$env:LLAMA_CPP_LIB_PATH='C:\path\to\native-directory'
$env:ORCHLANG_GGML_BACKENDS=$env:LLAMA_CPP_LIB_PATH
$env:ORCHLANG_GPU_LAYERS='99'
$env:GGML_VK_VISIBLE_DEVICES='0'
& $env:LEAN -o proof/ShapeCore.olean proof/ShapeCore.lean
& $env:LEAN -o proof/AdmissionDomain.olean proof/AdmissionDomain.lean
& $env:LEAN proof/StaticAdmissionChecks.lean
& $env:LEAN proof/StaticAdmissionCLI.lean
& $env:LEAN proof/VocabularyEnvelope.lean
python -m unittest discover -s tests -v
python publication/audit_homogeneous.py publication/evidence/round2-homogeneous --models $env:ORCHLANG_MODELS --output out/new-full-audit.json
```

The configured suite passes 47 tests; proof/axiom logs are in `round2-core`.
For source-ZIP replay without Git, run:

```powershell
python publication/reproduce_minimal.py --output out/new-minimal --models $env:ORCHLANG_MODELS
```

For a new full primary campaign, clone the supplied Git bundle, check out the
clean inference freeze `41a7d81`, and run
`python experiments/homogeneous_study.py campaign --models C:/path/models.json --output C:/path/new-study`.
This driver requires a clean Git identity. Later commits add manuscript,
analysis and prototype files; they retain the frozen production byte hashes.

New envelope and native experiments can be regenerated from the final source:

```powershell
python experiments/vocabulary_envelopes.py --models $env:ORCHLANG_MODELS --output out/new-vocabulary
python experiments/concrete_admission.py prepare --models $env:ORCHLANG_MODELS --vocabulary out/new-vocabulary/summary.json --output out/new-admission
python experiments/concrete_admission.py execute --models $env:ORCHLANG_MODELS --output out/new-admission
$env:ORCHLANG_GPU_LAYERS='0'
python experiments/sequence_prefill.py --models $env:ORCHLANG_MODELS --ubatch 1 --output out/new-prefill
```

The categorical driver takes `--implementation` pointing to a checkout of the
inference freeze; keep that checkout separate from its new output directory.
`publication/analyze_round2.py` checks all final cohorts and emits manuscript
macros and tables. Every primary and supplementary denominator is explicit.

## Earlier package preparation (historical context)

This package combines the strongest supported parts of the latest disk scientific
revision and the incoming usage-shaping work. The target is **Science of Computer
Programming**. The manuscript is `paper/main.tex`; the final rendered copy is
`output/pdf/orchlang-scp-author-review.pdf`.

The 25 October referee revision is documented in
`REFEREE_RESPONSE_2026-10-25.md`, `SOURCE_EXECUTION_ASSUMPTIONS.md` and
`SUBMISSION_ROUTE.md`. The recommended track is **Research Paper / Experimental
Software Technology / Formal Techniques**. The revision adds a reached-domain
Lean theorem and visible-admission specification, a refusal counterexample,
an actual source-policy omission example, and separate current-code real-model
falsification studies. It does not claim physical failure refinement or a
provider-authoritative gateway. Exact revision outcomes live under
`evidence/referee-revision`; they never enlarge the original study denominators.

## Start here

1. Read `AUDIT_COMPARISON.md` for the audit of both frozen parents.
2. Read `NOVELTY_AND_JOURNAL_ASSESSMENT.md` for the prior-art matrix, specific
   contribution, reviewer risks and SCP fit.
3. Read `CLAIM_LEDGER.md` to distinguish proved properties, finite observations,
   trusted assumptions and external actions.
4. Inspect `evidence-summary.json` and the raw directories it references. Run
   `python publication/build_evidence.py --require-complete`; an incomplete
   campaign must fail this check and must not be described as complete.
5. Use `AUTHOR_REVIEW.md` for the remaining human decisions. The cover letter and
   declarations are drafts, not evidence of consent or a submission.

The final strict completion check passes: 1,172 main pairs (962 historical plus
210 new), 512 Qwen replication pairs and 21 separate conformance pairs. All saved
outputs agree and all shaped traces match. The independent pinned-model audit
passes on 1,486 new records and 5,831 model events. `STUDY_OUTCOME.md` summarizes
the improvement and the remaining scientific and publication limits.

## Source identities and separation

| Role | Identity |
|---|---|
| Shared historical main | `460bf3a453879618a86916ca6540bbf6b4f0e21c` |
| Latest disk scientific revision | `cef4772d1568af0b0042d97dcff6c396e8d95a52` on `research/defensible-publication` |
| Incoming usage-shaping revision | `9134aaea780d14d53eedb7423df6ad6f727c9599` on `claude/trusting-clarke-c7eqeh` |
| Combined implementation freeze | `6a24fe8` on isolated `research/unified-publication` |
| Corrected frontend/protocol release | `913530b`, checked separately with targeted real-model controls |

The original disk checkout was neither switched nor pulled over. Remote changes
were fetched into a separate clone. The latest disk source was exported into
`legacy/v1`. The new inference campaign runs from a detached immutable execution
checkout, so later manuscript edits cannot change its implementation. The
preservation receipt compares original HEAD, branch, refs, tracked bytes and
eleven untracked review artifacts. The final archive includes that receipt.

The older incoming research branch with cyclic/uncertain finite probability tools
was screened separately and is not folded into the main scientific narrative.
No public push, upload, journal submission or paid API call was performed.

Read `POST_FREEZE_CHANGES.md` before comparing versions. Large application runs
use `6a24fe8`; the corrected frontend uses `913530b`. Its 360 source/template
checks, 320 targeted operational executions and three real-model boundary pairs
are separate evidence. Do not infer unchanged full-corpus accuracy after that
frontend correction. Use the matching Git version when checking an old artifact.
Only one process may write each run directory.

## Reproduction

Use Python 3.12 and Lean 4.19.0. `requirements-analysis.lock` pins direct analysis
dependencies. `evidence/core/unified-environment-freeze.txt` lists the complete
local Python environment. Model inference additionally requires
`llama-cpp-python==0.3.36`; a CPU wheel is available from the extra index noted
in `requirements.txt`. Weights remain outside the archive.

```bash
python -m venv .venv
# Activate the environment for your shell.
pip install -r requirements-analysis.lock
export LEAN=/absolute/path/to/lean-4.19.0/bin/lean
$LEAN proof/ShapeCore.lean
python -m unittest discover -s tests -v
python experiments/differential.py --programs 1000 --runs 4 --output out/differential.json
python experiments/correspondence.py --programs 150 --output out/correspondence
```

PowerShell uses `$env:LEAN='C:\absolute\path\to\lean.exe'` instead of `export`.
Model-free tests explicitly skip two GGUF-dependent cases. Configure pinned
models and rerun the suite to exercise template bytes and tokenizer padding.

The extended proof requires an importable core object:

```bash
$LEAN -o proof/ShapeCore.olean proof/ShapeCore.lean
LEAN_PATH=proof $LEAN proof/AdmissionDomain.lean
python experiments/admission_domain.py --output out/admission-domain.json
python experiments/source_binding_case.py --output out/source-binding.json
```

PowerShell sets `$env:LEAN_PATH=(Resolve-Path proof).Path` before checking the
extension. These commands deliberately refuse to overwrite their new receipts.
The ideal admission adapter is noncomputable specification code; its
all-inputs-and-tapes certificate is a premise, not an implemented predictor.

```bash
pip install llama-cpp-python==0.3.36 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python experiments/fetch_models.py models --replication --completion-profile
export ORCHLANG_MODELS=$PWD/models/models.json
python -m unittest discover -s tests -v
python experiments/run_workflow.py --workflow workflows/switch.orch \
  --data experiments/data/switch.jsonl --out out/switch --limit 3 \
  --keep response,intention,llm_result
python -m orchlang check --source workflows/switch.orch \
  --artifact out/switch/validation-artifact.json --models "$ORCHLANG_MODELS" \
  --output out/check-receipt.json
```

The manifest rejects incompatible resume. Use a new directory after changing
source, implementation, models, data selection or decoding parameters. Never copy
old JSONL records into a new campaign. The private execution records include
request/response contents for public benchmark inputs; deployment records with
real secrets require a separate data-handling policy.

`--completion-profile` is required to reproduce the new campaign's two-stop Llama
profile. The historical downloader's default also included `<|eom_id|>`; do not
silently substitute it. `--configure-only` verifies already downloaded weights
and writes their pinned configuration without network access. Model contracts
in the raw manifests, rather than defaults, define each experiment.

For the retained disk scientific implementation:

```bash
cd legacy/v1
python scripts/offline_check.py --cxx /path/to/modern/g++ --lean "$LEAN" --output /new/disk-check
```

Use GCC with C++17 support. Exact-accounting and original-framework checks have
their own documented tokenizer/framework environments in `legacy/v1/docs`.
The full audit retains the failed incomplete-environment replay and the successful
24/24 replay using the specified framework environment.

Historical attack reanalysis includes tool names:

```bash
python experiments/aggregate.py experiments/results/runs out/historical-analysis \
  --mutation experiments/results/mutation.json \
  --differential publication/evidence/core/unified-differential-v2.json \
  --transparency experiments/results/transparency-isolated.json --perm 0
python publication/build_evidence.py --require-complete
cd paper
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

The descriptive classifier results use no permutation-significance claim.
Historical and new wall-clock measurements must remain separate. Completing a
campaign means all planned paired observations exist and its checks pass;
it does not mean arbitrary providers satisfy the abstract world assumptions.

Analyze the new cohorts separately, without pooling their timings or changing
their recorded implementation identities:

```bash
python experiments/aggregate.py publication/evidence/completion/main out/main-analysis --perm 0
python experiments/aggregate.py publication/evidence/completion/replication out/qwen-analysis --perm 0
python publication/audit_execution.py --models "$ORCHLANG_MODELS" --self-check \
  --output out/new-record-audit.json
```

The new analysis tables report single-class decision prediction as uninformative.
The record-audit output must be a new file; retained receipts are immutable.

## Licensing and archive contents

Project software uses the existing MIT license. Model and benchmark licenses,
upstream prompt attribution and notices remain in `THIRD_PARTY_NOTICES.md` and
`legacy/v1/THIRD_PARTY_NOTICES.md`. Do not redistribute model weights or private
literature PDFs as part of the submission archive. The Hard-KLAIM full text was
read locally but is not included. Source/evidence integrity hashes detect changes;
they do not prove legal permissions, independent review or scientific truth.

The archive manifest excludes its own hash and temporary builds. A separate
receipt hashes the completed archive. Extract into a fresh folder, verify the
manifest, and use the pinned sources before attempting independent reproduction.

```bash
python publication/verify_package.py
python publication/build_evidence.py --require-complete
```

The companion `orchlang-scp-source-history.bundle` preserves both the complete
combined branch and the latest disk branch. It is separate from the source ZIP
to avoid recursive/self-referential hashes. Restore it without changing another
checkout:

```bash
git clone -b research/unified-publication /path/to/orchlang-scp-source-history.bundle review-history
git -C review-history bundle verify /path/to/orchlang-scp-source-history.bundle
git -C review-history worktree add --detach ../inference-version 6a24fe8
```

Use that inference-version checkout for reproducing the large new campaigns.
The final release compiler is identified in `SOURCE_PROVENANCE.json`; later
paper/package commits do not relabel earlier model execution. Weights remain
external. `assemble_archive.py` builds a new ZIP from verified working bytes,
honoring the file list produced by `make_manifest.py` after staging. This avoids
line-ending changes silently invalidating raw-byte hashes.


Budget files limit each workflow execution separately, not the sum of a dataset
or multiple workers. `git_dirty` records the initial workspace condition; resume
identity uses the unchanged substantive manifest fields, including exact source,
implementation, data, model and decoding fingerprints. A changed implementation
still refuses resume. The current checkpoint test guards this distinction.

## Replaying the referee revision

The main revision protocol ran at `c2bb75c`, before the source-export runner fix.
Its 48 workflow pairs and 192 primitive pairs are kept separate from the original
study. The final runners can also operate from an exported source ZIP: the Git
identity is null and the export-manifest hash is recorded. The compiler/runtime
and proof bytes are unchanged; use the source-history bundle for byte-identical
reproduction of a recorded older runner.

```bash
python publication/analyze_referee_revision.py \
  publication/evidence/referee-revision/current-code-v1 \
  --output out/revision-summary.json
python publication/render_referee_results.py out/revision-summary.json
python publication/analyze_two_routes.py \
  publication/evidence/referee-revision/two-route-baselines \
  --output out/two-route-summary.json
python experiments/referee_revision.py --models "$ORCHLANG_MODELS" \
  --output out/new-revision-experiment
```

Run the last command only when a new inference reproduction is intended. It
performs 102 workflow/baseline executions and 192 paired primitive checks; its
protocol is written first, and its directory cannot be reused. The authored
two-route comparison is separate:

```bash
python experiments/revision_routing_baselines.py --models "$ORCHLANG_MODELS" \
  --output out/new-two-route-baselines
```

For the small complete artifact path, including an optional pinned model pair
and standalone source checker:

```bash
python publication/reproduce_minimal.py --output /new/replay-output \
  --models "$ORCHLANG_MODELS"
```

Omit `--models` for a model-free replay. It uses installed dependencies and does
not claim to provision a new machine. The final review delivery contains the
same-machine fresh-extraction replay receipt and logs outside the source ZIP,
avoiding recursive receipt/archive hashes. `REPLAY_CHECKLIST.md` is reserved for
a genuinely independent human reviewer.
