# Presentation artifact audit

Audited 2026-10-09. This records the frozen current deck and the read-only audit
of earlier project artifacts. The source register and scripts are maintained
under `submission/research/`.

## Final review candidate with exact trace-law extension

`dist_current/` contains the final 32-slide presentation. The editable PPTX
preserves slide text, diagrams and evidence visuals as native PowerPoint shapes
and includes 32 populated speaker-note parts. Its SHA-256 is
`cd43811af560a893906d8ca134ee38918d70655a08dc96bb7251da6883091f36`. Artifact
Tool finalization reports 32 slides, clean package integrity, no layout
findings, and successful first-party import. The source-derived build is bound
to the sanitized/package-validated 44-stage manifest SHA-256
`65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035` and the
trace-equivalence report SHA-256
`9dddb048e411960b07c070c7fff2b169361c1df84ce786cfdb73b524bb56c861`.

All 32 slide PNGs and the PDF montage were visually inspected. The PDF SHA-256
is `aafa50ccf9cd2c174aa9b4e499e4b4e865f6764055b61c38af88ddb3396f45f9`; it has
32 raster pages and a verified clickable `http://127.0.0.1:8765/` link on the
final page. This host does not have LibreOffice installed, so the documented
fallback assembles the reviewed slide renders into a raster-page handout rather
than a vector export. The PPTX also carries an external hyperlink on slide 32.
PNG renders and montages are saved beside the deck.

The final deck's exact trace-equivalence slide covers the authored case where
strong bisimulation is inconclusive, H=2 ordered TV is zero, exact rational
row-span closure proves every finite ordered usage word for the supplied
kernel, and an independent replayer verifies the exact certificate. The strong
bisimulation status in that fixture is a fresh analyzer comparison, not
independently replayed in the trace-equivalence study. The appendix binds the
12-case study counts to its manifest-verified report. No general weighted-
automata novelty, provider distribution, termination, or cumulative-cycle-cost
claim is made.

## Previous review candidate, before exact trace-law extension

The earlier 32-slide candidate is preserved under
`.build/current/previous/`. Its PPTX SHA-256 is
`ad1ade7d16e3a96758bb9a62d901d87942b4996671affd7c9bdfd4673b494ce6`; its
previous PDF SHA-256 is
`7a069674c34ac3f12674eb1efaf9359f0729f25dfcce42d2a3e23307f80a0274`. The
pre-extension slide 21 did not include the exact span result or the new
independent replay. Those hashes are historical and do not identify the final
deck.

## Prior presentation and report packages

| Artifact | Source/generator | Audit finding |
|---|---|---|
| `submission/phase2/OrchLang_Phase2_Presentation_Nambi_Rajan_M.pptx` (18 slides) | `submission/phase2/build_deck.js` (PptxGenJS) | Strong existing story arc: motivating workflow, three compiler analyses, a negative result, tests, evaluation, audit response, scope, demo, reproducibility. Its result slide and counts predate the current upgrade. Slide 6 says “Every flow analysis accepts this”; slide 8 claims numeric cost reasoning cannot apply. Both overstate the evidence and prior-art boundary. Slide 7's old screenshot/source rendering has an overflow issue. Retain its useful narrative pacing, not its claims or old numbers. |
| `submission/phase2/OrchLang_Phase2_Report_Nambi_Rajan_M.docx` (273 paragraphs) | `submission/phase2/build_report.js` (docx package) | Dated 17 September 2026. Documents compiler stages and the earlier experiment, but reports 95 assertions, 34 examples, 63 generated workflows, 7,575 executions, and 225/425 paired outcomes. Those are historical. Its abstract also says the classical potential method does not transfer because model output is provider-chosen; this needs the more careful resource-aware IFC, RelCost, probabilistic resource, and PPDL discussion in the new review. |
| `submission/review2/OrchLang_Review_2_Presentation_Nambi_Rajan_M_Final.pptx` (12 slides) | `submission/review2/ORCHLANG_REVIEW_PRESENTATION.md` is the available textual source | Earlier front-end milestone: lexer, parser, AST, symbols, semantic analysis, and IR. It predates cost/runtime/relational upgrades, reports 45 tests, and includes a live-demo path under `/Users/nambi/Documents/Codex/2026-09-16/...` that does not match this checkout. Useful for compiler-pipeline explanations only. |
| `submission/review2/OrchLang_Review_2_Rubric_Report_Nambi_Rajan_M.docx` (236 paragraphs) | No matching generator found in `submission/review2/` | Earlier review report. Its scope explicitly ends at the compiler front end and 45 tests; it is not evidence for the current analyses or benchmark. |
| `audit/2026-09-17/build.ps1` and `build-manifest.txt` | Historical Windows/MinGW replay harness and environment record | Targets the `v2-static-certification` source snapshot and runs old unit, reproduction, and paired-input probes. It does not generate a deck or DOCX; its September 2026 binaries and logs are historical evidence, not the current compiler build. |

The older PPTX packages are editable PowerPoint files, and their source files
remain in the repository. Both review candidates were rebuilt from native
PowerPoint text and shapes, with source maps and speaker notes. The final
candidate adds the exact trace-law story and is bound to the frozen manifest.

The local ArchiveGate reference is a separate design package, not an OrchLang
submission. Its 14-slide PowerPoint/PDF and `slide_source/` assets were inspected
as the visual reference. The new deck follows its warm-cream/navy alternation,
coral/teal accents, short editorial headings, and evidence-led composition;
it does not reuse ArchiveGate content.

## Repository-level text audited in the pre-upgrade snapshot

- `docs/PAPER.md` was the earlier research draft at audit time. It had a useful equal-cap
  counterexample and a clear distinction between unary and relational claims,
  but it overstates the absence of numeric/potential methods and cites old
  benchmark denominators. The upgraded paper must own the final theorem scope,
  request/oracle relation, results, and limitations.
- `docs/LANGUAGE_SPEC.md` was the language reference to re-check against the
  upgraded compiler; exact behavior and rule names needed revalidation.
- The earlier `README.md` was promotional in its opening sentence (“almost nothing
  else catches”) and generalized about classical resource methods. Do not use
  those historical phrases as talk claims.
- `submission/review2/ORCHLANG_REVIEW_PRESENTATION.md` provides a dated
  8–9-minute script for the earlier front-end review, not the current talk.
- `submission/phase2/build_deck.js` and `build_report.js` are the source
  generators for the earlier phase-2 artifacts. No edits were made to them.

## Consequence for the new deck

The final talk keeps the legible compiler-review pacing and the concrete
counterexample, while framing each claim under an explicit observation and
oracle/request relation. It treats resource-aware noninterference, relational
cost analysis, probabilistic cost/LLM-flow work, quantitative side channels,
probabilistic bisimulation, weighted-automata equivalence and agent-workflow
checks as established prior art. The row-span extension is a finite LLM usage
specialization with replayable certificates, not a new general equivalence
algorithm.
Old counts, old diagnostics, and old command paths are not copied into the final
deck. Every displayed implementation result must come from the final run and
the saved source-bound evidence.

The canonical talk source, timed scripts, and bibliography are `outline.md`,
`script_8min.md`, `script_15min.md`, and `sources.md`. They explain the exact
trace-law extension and its limits. `README.md` documents the strict rebuild
and PDF raster fallback. `dist_current/` contains the final candidate; the
earlier candidate remains in `.build/current/previous/`.

The independent publication review is in `docs/FINAL_PUBLICATION_REVIEW.md`.
The final independent assessment is recorded in
[`docs/FINAL_PUBLICATION_REVIEW.md`](../../docs/FINAL_PUBLICATION_REVIEW.md):
overall applied-project novelty 5.8/10, applied method 5.9/10, research
software 6.5/10, evidence 7.0/10, SCP OSP originality/significance 6.2/10,
equal-weight six-criterion candidate quality 7.4/10, target fit 8.5/10, and
fundamental theory 3.0/10. These are internal review aids, not journal ratings
or acceptance probabilities; a novelty score of 8 is not supported. The main
deck deliberately omits numerical scores.
