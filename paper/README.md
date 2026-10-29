# Manuscript sources

`main.tex` is the active SCP manuscript. It reads `refs.bib`, the `unified-*` and
`final-release-*` generated tables, and three formal presentation files:
`sections/core-syntax.tex`, `sections/core-semantics.tex`, and
`sections/core-validation.tex`. Other earlier section files remain historical
and are not included. Export attributes include the three active figures.

Regenerate tables with `python publication/build_evidence.py` from the repository
root. `--require-complete` checks completeness of the retained versioned campaign;
it does not assert a homogeneous current-release rerun. Final-release tables come
from `publication/analyze_final_release.py`. Compile with pdflatex, bibtex,
pdflatex, pdflatex, then render every page for visual inspection.
