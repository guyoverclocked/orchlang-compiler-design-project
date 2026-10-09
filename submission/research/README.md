# OrchLang review presentation

This folder contains source for the editable 32-slide review deck, timed scripts,
citations, and visual QA artifacts. `dist_current/` contains the final current
candidate, built against the refreshed 44-stage reproduction manifest and the
frozen exact trace-law report. The pre-extension PPTX remains archived under
`.build/current/previous/`.

- `dist_current/OrchLang_Current_Software_Review.pptx` — editable slides with speaker notes;
- `dist_current/OrchLang_Current_Software_Review.pdf` — 32-page handout;
- `dist_current/slide_png/`, `dist_current/pdf_slide_png/`, and `dist_current/montage.png` — renders and visual QA;
- `script_8min.md` and `script_15min.md` — timed talk scripts.

The deck follows the local ArchiveGate reference's visual rhythm: 16:9 canvas,
warm cream and deep navy, coral/teal/rust accents, editorial headings, and
evidence-led diagrams. Text, diagrams, and data visuals use editable native
PowerPoint shapes. The reference package is
`/Users/nambi/Documents/OS Project/ArchiveGate_Review1_Package/01_Presentation/ArchiveGate_Review1_Deck.pptx`.

## Build

From the repository root, run `./submission/research/build_current_candidate.sh`.
The script uses the bundled `@oai/artifact-tool` and finalizes an editable PPTX.
Before export, its evidence loader requires a complete sanitized and
package-validated final manifest, binds every displayed report to its SHA-256,
checks the compiler and analysis-source hashes, and verifies stochastic
bisimulation and exact trace-equivalence artifacts. It refuses to build from
stale evidence. The frozen `audit/final/manifest.json` SHA-256 is
`65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035`; the bound
`bench/results/trace_equivalence.json` SHA-256 is
`9dddb048e411960b07c070c7fff2b169361c1df84ce786cfdb73b524bb56c861`. This
build does not rerun the compiler or research studies.

The build exports 32 slide renders under `dist_current/slide_png/` and a
montage. Rebuilding archives the previous PPTX under `.build/current/previous/`
before finalization. Run `./submission/research/render_current_pdf.sh` to convert
the PPTX with LibreOffice when it is available, verify all 32 PDF pages, and
create PDF-derived slide PNGs plus a montage. If LibreOffice is unavailable,
the script assembles the reviewed Artifact Tool slide renders into a 32-page
raster PDF; the last slide's demo URL remains clickable. The current PDF uses
that documented fallback because LibreOffice is unavailable on this host.
Temporary candidates and validation receipts live in `.build/current/`.

The main slide outline is [`outline.md`](outline.md); timed scripts are
[`script_8min.md`](script_8min.md) and [`script_15min.md`](script_15min.md).
The citation register is [`sources.md`](sources.md), and the read-only audit of
the earlier project artifacts is [`artifact_audit.md`](artifact_audit.md).
The `current_review_*` source drafts are retained alongside those canonical
copies.

## Evidence boundaries

The deck separates bounded C++ compiler results, cyclic JSON graph checks,
restricted source adapters, offline LangGraph execution, finite-kernel channel
analyses, sufficient strong bisimulation and exact trace-law equivalence. These
families use different inputs, observers and denominators; their counts are not
pooled. A strong-bisimulation split is inconclusive. Exact rational row-span
analysis can prove equality for some split cases or return a finite word
witness. The exact row-space method and its replay scope are documented in
[`docs/TRACE_EQUIVALENCE.md`](../../docs/TRACE_EQUIVALENCE.md). Both tools use
supplied finite kernels, not provider probability estimates. Productive graph
cycles establish usage-prefix equality, not termination or a finite total-cost
bound. Reported tests and certificate replay support inspection but do not
replace a mechanized soundness proof.

The source-pattern corpus consists of partial projections with authored
variants, not complete framework ports. Source adapters cover restricted
subsets and are not verified general translators. The runtime and examples use
offline response models; no live provider invoice or behavior is claimed.
Relevant conditions and source citations appear in slide notes and
[`sources.md`](sources.md).

## Publication assessment

The final independent review in [`docs/FINAL_PUBLICATION_REVIEW.md`](../../docs/FINAL_PUBLICATION_REVIEW.md)
rates overall applied-project novelty at 5.8/10 (4.5/10 initially), applied
method at 5.9/10 (3.5/10 initially), research-software quality at 6.5/10
(4.0/10 initially), evidence at 7.0/10 (2.0/10 initially), SCP OSP
originality/significance at 6.2/10, the equal-weight six-criterion
candidate-quality proxy at 7.4/10, target fit at 8.5/10, and fundamental
theory at 3.0/10. These are internal review aids, not journal ratings or
acceptance probabilities; a novelty score of 8 is not supported. The main deck
stays score-free.
