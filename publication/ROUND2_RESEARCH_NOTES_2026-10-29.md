# Research and implementation choices

The second review was read together with the first review's actionable roadmap.
Its numerical ratings are informal opinions. This revision prioritizes executable
connections and new measurements rather than treating a score as a scientific
target.

## Source-derived admission

Implemented: a byte-bounded value interface on both original and shaped programs,
source-derived slot bounds, expression-envelope targets, independent source-bound
validation, and the actual Lean `staticCertificate` on serialized application
candidates. All twelve variants pass. The final context is 21,504; the largest
candidate needs 20,606 input-plus-output tokens. Initial stores are guarded before
dispatch, tools are byte-buffered, and visible responses are buffered after UTF-8
decoding. The guard admits 1,682/1,684 planned inputs; two Calculator inputs are
outside this advertised domain.

The vocabulary scan measures **raw native piece bytes**, not a universal bound on
the UTF-8 encoding of replacement-decoded strings. All three pinned vocabularies
have a maximum of 128 raw bytes per piece. Invalid UTF-8 replacement can expand a
decoded string, so the post-decoding buffer is required for the declared string
bound. The earlier fixed 32-byte wrapper returned an empty piece for an ordinary
128-byte witness. The resizing decoder is part of production freeze `41a7d81`.

The native implementation uses a byte-BPE path. Its algorithm correspondence is
trusted, while the measured vocabulary constants, complete byte coverage and
2,058 valid-UTF-8 requests per model are retained evidence. Automatic BOS is
disabled and the expression already contains the complete chat framing, giving
the declared assumption alpha=1, delta=0. Neither a vocabulary scan nor the Lean
arithmetic lemma verifies C++, the Python frontend, JSON decoding or allocation
success. The review's proposed phrase “end-to-end verified” would overstate this
boundary.

The first scan also tested singleton raw bytes 0x80–0xff as tokenizer inputs.
Those are invalid UTF-8 and are normalized by the native tokenizer. The refined
scan checks actual single-byte vocabulary pieces and valid source strings; the
original unsupported-byte observations remain retained rather than being called
counterexamples inside the source-string domain.

Primary source: [pinned native vocabulary implementation](https://github.com/ggml-org/llama.cpp/blob/9c2e0e491/src/llama-vocab.cpp).

## Serving alternatives

| Approach | What it provides | Evidence or remaining boundary |
|---|---|---|
| Exported-report normalization | Fixed reporting trace at low execution cost | Applicable to a log-only observer; cannot alter actual native submissions |
| Existing isolated prefill | Consumes a fixed logical envelope without exposing filler to useful attention | Separate request and filler submissions reveal request length below the wrapper |
| Joint native batch with separate sequence IDs | One exact 128-token native prefill; fixed native-size projection | Implemented, with retained sequence-metadata leakage and batching-sensitive output mismatch |
| Microbatch size one | All 12 tested visible outputs agree | Finite preservation evidence; no universal transparency proof or throughput claim |
| Erase cover sequence after prefill | Removes cover KV entries before decoding | Tested control; does not remove the one observed size-128 mismatch |
| Token-ID transport | Avoids re-tokenization within a shared tokenizer | Useful future interface; cross-model text and tool values still need explicit bounds |
| Public paced release | Could address a different timing observer | Requires a deadline/refusal model and new measurements; not inferred from logical counts |

All 36 final native-prototype attempts remain in their denominators. Natural
size traces have four distinct values per model, versus one shaped size trace.
Sequence membership recovers real request length in every case. This supports a
restricted native-size observer and refutes the review's implication that one
length-T submission alone proves protection against a server with full metadata.

Primary sources: [native batch fields](https://github.com/ggml-org/llama.cpp/blob/9c2e0e491/include/llama.h),
[the exact native release](https://github.com/ggml-org/llama.cpp/releases/tag/b11490).

## Categorical CRAG

The separately evaluated intervention combines an unambiguous categorical prompt
with a grammar restricted to yes/no JSON. The grammar is a distinct grader model
contract; answer generation and the any-negative-of-four routing rule stay the
same. All 150 pairs complete with equal saved outputs. All 600 grades have valid
categorical JSON (62 yes, 538 no); 149 questions search and one skips search.
Inherited answer accuracy rises from 57/150 to 84/150, with 28 improved and one
regressed answer. Grammar compliance does not establish relevance accuracy, and
the combined intervention does not isolate prompt and grammar effects. The
primary prompt and historical responses are preserved.

## Evidence and presentation

The full primary campaign uses one clean corrected production identity, pinned
native libraries, complete selected-ID sets and streaming local evidence. Its
1,684 pairs and 10,698 audited model calls replace the old mixed-version tables.
Historical cohorts move to a compact appendix and remain reproducible in the
artifact. Additional admission and CRAG experiments have separate denominators.

An initial 32,768-context admission run exhausted GPU memory before adaptive
execution after completing 16 pairs. Its logs and exact driver are retained.
The successful cohort uses a predeclared 21,504 context and explicitly releases
backends between workflows. This is evidence of the physical-resource boundary,
not a theorem that a token-context check bounds total device allocations.

The review's four alleged typographical errors were checked against source:
the citation is generated with its closing bracket, the profile is `llama1b`,
the semantics use angle brackets, and the historical added-stop labels all use
`+ OK`. Rendered pages are also checked in the final PDF pass. No scientific
symbol or model identity is changed to match an OCR reading.
