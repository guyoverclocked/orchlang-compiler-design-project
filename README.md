# OrchLang: source-bound validation of constant-shape LLM workflows

The second-round revision of 29 October includes a full homogeneous 1,684-pair
study with 10,698 audited model calls, source-derived byte-bounded admission for
all twelve variants, a native single-batch prefill prototype and a separate
150-pair categorical CRAG ablation. Every primary application pair preserves
saved outputs and its static shape. See [the review response](publication/SECOND_ROUND_RESPONSE_2026-10-29.md)
and [the researched alternatives](publication/ROUND2_RESEARCH_NOTES_2026-10-29.md).
Native sequence metadata and batching-sensitive output differences remain
explicit boundaries; normalization is cheaper for an exported-log observer.

The combined revision targets **Science of Computer Programming**. Start with
[the publication package](publication/README.md), [the prior-art assessment](publication/NOVELTY_AND_JOURNAL_ASSESSMENT.md)
and [the claim ledger](publication/CLAIM_LEDGER.md). The current manuscript is
[paper/main.tex](paper/main.tex); its rendered PDF is under `output/pdf/`.

OrchLang proposes padding, aligned dummy calls and bounded-loop completion to make
logical usage observations independent of secret inputs. Lean validates the core
transformation under explicit conformance and transparency assumptions. A trusted
source reader binds the original program and declared secrets independently of
candidate code. The runtime admits complete requests, keeps model units separate,
checks backend usage and records immutable provenance.

The verified observation is an ordered sequence of model contract/input/output
counts and instrumented tool names. Timing, failures, packets, external tool
traffic and provider invoices require additional contracts. The Python frontend,
serializer, tokenizer and backend remain trusted. See the manuscript for the
precise theorems and limits.

## Evidence

The current primary campaign contains 1,172 main pairs and 512 Qwen replication
pairs at clean production freeze `41a7d81`. Saved fields agree in all 1,684 pairs;
every shaped trace equals its static shape. Main-study median weighted logical
overhead is 1.84 times original usage, range 1.13–13.99. The complete current
evidence map is [ROUND2_INDEX.md](publication/evidence/ROUND2_INDEX.md).
The byte-bounded cohort separately tests 24 pairs and the categorical ablation
tests 150. Qwen CRAG answer accuracy rises from 38.0% to 56.0% under its inherited
scorer. All 47 configured tests pass. Earlier cohorts remain distinct historical
evidence; `publication/evidence-summary.json` describes their original counts.

The disk scientific revision is retained in `legacy/v1` with its own language,
accounting, proof and framework-replay evidence. Its confidentiality/integrity
policies are distinct from the usage-shaping observer.

## Quick checks

Use Python 3.12, Lean 4.19.0 and the pinned analysis dependencies:

```bash
pip install -r requirements-analysis.lock
lean proof/ShapeCore.lean
python -m unittest discover -s tests -v
python experiments/correspondence.py --programs 150 --output out/correspondence
```

Set `LEAN` to the Lean executable when needed. Model-free unit runs explicitly
skip two GGUF checks. See `publication/README.md` for model pins, complete-request
execution, standalone source-bound validation, full reproduction and legacy checks.
Never resume a new implementation into historical output directories.

## Release status

The combined work is isolated from the original disk checkout. The publication
package includes source comparison, novelty/journal assessment, evidence and
submission drafts. Human author review, declarations, an approved public archive
and actual journal submission are separate remaining actions. No acceptance or
public artifact DOI is claimed.

The independent-referee revision is explained in
[the response](publication/REFEREE_RESPONSE_2026-10-25.md). It adds a compiled
restricted-domain admission theorem, executable refusal/policy-omission cases,
current-code workflow and transparency checks, and complete history delivery.
The recommended submission route is an SCP **Research Paper**, with the software
framed as an offline assurance tool under its declared logical observer. Physical
failure/gateway refinement, public archival and human declarations remain explicit.

MIT software license; benchmark, prompt and model conditions remain in
`THIRD_PARTY_NOTICES.md` and `legacy/v1/THIRD_PARTY_NOTICES.md`.
