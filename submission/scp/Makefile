# Build the Science of Computer Programming manuscript.
#
#   make            figures, then the manuscript PDF
#   make data       regenerate figure data from bench/results (needs a prior evaluation run)
#   make check      abstract and highlights limits, unresolved references, overfull boxes
#   make bundle     flat directory for Editorial Manager (no sub-folders, .bbl included)
#
# Figures are compiled to PDF here, so the submission system never has to
# compile TikZ or pgfplots itself.

FIGURES := $(patsubst figures/%.tex,fig-%.pdf,$(filter-out figures/common.tex,$(wildcard figures/*.tex)))

.PHONY: all data check bundle examples clean

all: main.pdf

fig-%.pdf: figures/%.tex $(wildcard figures/data/*.csv)
	cd figures && pdflatex -interaction=nonstopmode -halt-on-error $*.tex > /dev/null
	mv figures/$*.pdf $@

main.pdf: main.tex $(wildcard sections/*.tex) references.bib highlights.txt $(FIGURES)
	latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex > /dev/null
	@grep -E "Warning: (Citation|Reference)" main.log || true

data:
	cd ../.. && python3 submission/scp/figures/data.py

check: main.pdf
	python3 check.py

bundle: main.pdf highlights.docx
	python3 bundle.py

highlights.docx: highlights.txt build_highlights.js
	cd ../.. && node submission/scp/build_highlights.js

examples:
	python3 examples/run.py

clean:
	latexmk -C main.tex > /dev/null 2>&1 || true
	rm -f fig-*.pdf figures/*.aux figures/*.log
	rm -rf upload
