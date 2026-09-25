#!/usr/bin/env python3
"""Build upload/: a flat copy of the manuscript for Elsevier's Editorial Manager.

Editorial Manager cannot process LaTeX sources in sub-folders, so every \\input of a
section is inlined into one main.tex, the running example is copied next to it, and
the result is compiled once to prove that the flat copy builds on its own.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'upload')


def inline(text):
    def replace(match):
        name = match.group(1)
        with open(os.path.join(HERE, name + '.tex'), encoding='utf-8') as handle:
            return inline(handle.read())
    return re.sub(r'\\input\{(sections/[^}]+)\}', replace, text)


shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
with open(os.path.join(HERE, 'main.tex'), encoding='utf-8') as handle:
    source = inline(handle.read())
source = source.replace('\\lstinputlisting[basicstyle=\\ttfamily\\footnotesize]{examples/triage.orch}',
                        '\\lstinputlisting[basicstyle=\\ttfamily\\footnotesize]{triage.orch}')
if 'sections/' in source or 'examples/' in source.replace('bench/', ''):
    leftovers = [line for line in source.splitlines() if 'sections/' in line or '{examples/' in line]
    if leftovers:
        sys.exit('bundle: unresolved sub-folder paths: %s' % leftovers[:3])
with open(os.path.join(OUT, 'main.tex'), 'w', encoding='utf-8') as handle:
    handle.write(source)
for name in ['references.bib', 'elsarticle.cls', 'elsarticle-num.bst', 'highlights.docx'] + \
        sorted(f for f in os.listdir(HERE) if f.startswith('fig-') and f.endswith('.pdf')):
    shutil.copy(os.path.join(HERE, name), OUT)
shutil.copy(os.path.join(HERE, 'examples', 'triage.orch'), OUT)

for step in (['pdflatex', '-interaction=nonstopmode', 'main.tex'], ['bibtex', 'main'],
             ['pdflatex', '-interaction=nonstopmode', 'main.tex'],
             ['pdflatex', '-interaction=nonstopmode', 'main.tex']):
    subprocess.run(step, cwd=OUT, capture_output=True)
log = open(os.path.join(OUT, 'main.log'), encoding='latin-1').read()
if not os.path.exists(os.path.join(OUT, 'main.pdf')) or 'undefined' in log.split('Output written')[-1]:
    sys.exit('bundle: the flat copy did not build cleanly; see upload/main.log')
shutil.move(os.path.join(OUT, 'main.pdf'), os.path.join(OUT, 'manuscript.pdf'))
for name in os.listdir(OUT):
    if name.split('.')[-1] in ('aux', 'log', 'out', 'blg', 'spl'):
        os.remove(os.path.join(OUT, name))
print('upload/: ' + ', '.join(sorted(os.listdir(OUT))))
