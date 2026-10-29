# Response to the second-round review

The revision replaces the mixed-version main evaluation with a complete study
on one corrected implementation, connects static admission to actual source-derived
workflow candidates, and implements the requested native-prefill and categorical
grading experiments. The manuscript is now 29 pages. Earlier observations remain
in the artifact and a compact appendix, with their original identities.

The review's acceptance recommendation and score are informal assessments. The
changes below address its scientific roadmap; they do not guarantee a score or
an editorial outcome.

## 1. Connect the admission theorem to the compiler and pinned models

Implemented in `orchlang/admission.py`, `proof/StaticAdmissionCLI.lean`,
`proof/VocabularyEnvelope.lean` and `experiments/concrete_admission.py`.
The frontend derives finite byte bounds from source assignments and sizes actual
request expressions with the compositional envelope. Independent source-bound
validation checks the useful program and secrecy policy. Lean's actual
`staticCertificate` checks the serialized candidate, receiving-slot bounds,
dummy requests, response/tool bounds and context limits.

All nine main and three Qwen variants pass. At context 21,504 their largest
input-plus-output cell is 20,606. The input guard admits 1,682/1,684 planned
inputs; two Calculator questions exceed the chosen byte interface. A separate
24-pair execution cohort preserves full runtime stores and certified shapes.
Its independent audit reconciles 188 local model calls, 36 tool-buffer clips and
zero response-buffer clips. All twelve oversized-input controls refuse before
dispatch. Both original and shaped arms use the same explicit buffers.

The exhaustive native scans find a maximum raw token-piece length of **128 bytes**
in all three GGUFs. Each Llama vocabulary contains 231 pieces longer than
32 bytes; Qwen contains 240. This exposed a real fixed-buffer decoding defect:
the installed wrapper returned an empty piece for a 128-byte witness. The
production decoder now retries with the complete required buffer. The full
primary study was frozen after that correction.

The response bound is enforced after UTF-8 decoding, since replacement decoding
can expand raw bytes. The tokenizer assumption is alpha=1, delta=0 for complete
valid-UTF-8 requests with automatic BOS disabled. Complete byte coverage and
2,058 finite request probes per model support that assumption. Native algorithm
correspondence, parsing and physical serving remain trusted. A finite vocabulary
scan does not justify the review's suggested “end-to-end verified” wording.

An initial 32,768-context attempt completed 16 pairs before adaptive-workflow
allocation exhausted GPU memory. Its records, error log and exact hash-verified
driver are retained separately. The complete cohort uses a declared context of
21,504 and explicit backend closure between workflows. Token-context admission
does not prove total device-memory availability.

Manuscript: Section 4.4, Section 6.4 and Table 3. Evidence:
`evidence/round2-vocabulary-v2`, `round2-concrete-admission-v3`,
`round2-analysis-v2`; preliminary failure in `round2-concrete-admission-v2`.

## 2. Replace fragmented application tables with a full homogeneous rerun

All **1,684/1,684** planned original/shaped pairs complete at clean production
freeze `41a7d81f4756821cb3ce0d22e9aaf49930b4d7dc`: 1,172 main pairs and 512 Qwen
replication pairs. Every saved output agrees and every shaped trace equals its
static shape. The independent audit checks 3,368 execution records and **10,698
model calls**, re-tokenizes complete requests, reconstructs visible prefixes,
reconciles model-indexed ledgers and matches full local eval/yield records.
A corrupted-count negative control is detected. Production byte hashes still
match the inference freeze.

The main table now reports current task scores, original decision attacks,
one distinct shaped trace, empirical MI zero, and current logical costs.
Main-study median overhead is 1.84 times original usage, range 1.13–13.99.
Single-class attacks are omitted rather than presented as perfect security
results. The primary Qwen CRAG port remains unchanged for this comparison.

The native version, Vulkan GPU configuration, thread count, context, batch,
decoding policy, selected IDs and model/library hashes are recorded. New tables
are generated from these audited records. Earlier large cohorts no longer serve
as the primary final-code evaluation.

Manuscript: Sections 6.1–6.3, Table 2 and Appendix B. Evidence:
`round2-homogeneous`, `round2-full-audit.json`, `round2-main-analysis` and
`round2-replication-analysis`.

## 3. Implement and test a single native prefill submission

The new prototype submits one actual 128-token `llama_decode` batch, with useful
tokens on sequence 0, filler on sequence 1, independent positions and logits
requested only for the final useful token. It compares natural unpadded and
forced generation across two families, three prompt bodies and two visible caps.
All 36 attempted cases across three configurations are retained.

| Configuration | Exact single prefill | Equal visible outputs | Length recoverable from sequence metadata |
|---|---:|---:|---:|
| Native microbatch 128 | 12/12 | 11/12 | 12/12 |
| Native microbatch 1 | 12/12 | 12/12 | 12/12 |
| Microbatch 128, remove cover cache | 12/12 | 11/12 | 12/12 |

For each model, natural size traces have four values; shaped size traces have
one: 128 followed by 23 single-token submissions. This is an actual native-size
projection that report normalization above the API cannot reproduce by changing
reports alone. It does not conceal sequence/position/logit metadata from a server.
The size-128 counterexample also prevents an unqualified transparency claim.
The manuscript therefore implements the proposed experiment while correcting
the review's inference that one fixed-length submission proves general
server-boundary confidentiality.

Manuscript: Section 6.5 and Table 4. Evidence: `round2-native-prefill`.

## 4. Evaluate a categorical Qwen CRAG grader separately

The new ablation uses a categorical relevance prompt and a grammar accepting
only yes/no JSON. Grammar identity is part of the grader contract. Answer
generation, retrieval and the any-negative-of-four routing rule stay the same.

All **150/150** original/shaped pairs preserve saved fields, including the four
grades, and produce one shaped trace. All 600 original grades are valid JSON:
62 yes and 538 no. Both routes occur, with 149 searches and one omission.
The inherited answer score rises from **57/150 (38.0%) to 84/150 (56.0%)**;
28 answers improve and one regresses. These are paired descriptive results,
not independent human judgments of answer quality. The route distribution
remains highly imbalanced, and the combined intervention does not isolate the
prompt's effect from the grammar's effect. The audit reconciles 1,500 model calls.

Manuscript: Section 6.6. Evidence: `round2-categorical-full` and
`round2-analysis-v2`.

## 5. Retain established controls and complete editorial checks

All 47 configured tests pass. Lean checks the core, domain extension, ten static
admission controls, concrete checker interface and token-piece arithmetic without
`sorryAx`. A fresh 72-compilation weight study accepts all candidates and keeps
each of the twelve variant shapes unchanged at output weights 0.25, 1, 2, 4, 8
and 16. Existing differential/correspondence studies remain separately identified.

The four alleged typographical errors were checked against source and rendering:
the citation closes correctly, the profile is `llama1b`, the semantic states use
angle brackets, and historical added-stop labels contain `+ OK`. No model name
or formal symbol was changed to match an OCR transcription.

The academic-humanizer pass follows the completed scientific revision. Protected
numbers, equations and citation occurrences are unchanged. All original citations
are retained, bibliography keys are unique, and the compiled manuscript has no
undefined references or overfull boxes. Every rendered page was inspected;
the appendix layout was tightened to avoid a nearly empty final page.
`round2-manuscript-qa.json` records the 29-page PDF's checks and hash.

Source, raw observations, failed attempts, generated tables, proof/test receipts
and the final PDF are packaged together with an integrity manifest and Git
history. Reproduction instructions identify the complete current cohorts and
keep earlier evidence distinct.
