#!/usr/bin/env python3
"""Checks on the manuscript that the journal's rules and our own style rules require.

Run after a build (make check): abstract length, highlights, unresolved references,
overfull boxes, and the word list from the style checklist.
"""
import re
import sys

failures = []


def words_of(tex):
    tex = re.sub(r'\$[^$]*\$', 'X', tex)
    tex = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?', ' ', tex)
    tex = re.sub(r'[{}]', ' ', tex)
    return tex.split()


abstract = open('sections/abstract.tex', encoding='utf-8').read()
abstract = abstract.split('\\begin{abstract}')[1].split('\\end{abstract}')[0]
count = len(words_of(abstract))
print('abstract words: %d (limit 250)' % count)
if count > 250:
    failures.append('abstract has %d words' % count)

highlights = [line.strip() for line in open('highlights.txt', encoding='utf-8') if line.strip()]
print('highlights: %d (3-5 required)' % len(highlights))
if not 3 <= len(highlights) <= 5:
    failures.append('highlights: %d bullets' % len(highlights))
for line in highlights:
    print('  %2d  %s' % (len(line), line))
    if len(line) > 85:
        failures.append('highlight over 85 characters: ' + line)

try:
    log = open('main.log', encoding='latin-1').read()
    for pattern in ('Citation `', 'Reference `', 'Overfull \\hbox'):
        hits = log.count(pattern)
        print('%s occurrences in log: %d' % (pattern.strip('`\\'), hits))
        if hits and pattern != 'Overfull \\hbox':
            failures.append('%d unresolved %s' % (hits, pattern))
except FileNotFoundError:
    print('main.log missing: build first')

avoid = re.compile(r'\b(delv(e|es|ed|ing)|underscor(e|es|ed|ing)|showcas(e|es|ed|ing)|intricat(e|ely|acies)|'
                   r'meticulous(ly)?|commendable|pivotal|realms?|notabl(e|y)|noteworthy|innovative|'
                   r'versatil(e|ity)|seamless(ly)?|leverag(e|es|ed|ing)|harnessing|utiliz(e|es|ed|ing)|'
                   r'groundbreaking|transformative|unparalleled|remarkabl(e|y)|crucial|comprehensive|'
                   r'additionally|insights?|tapestry|testament|landscape|foster(s|ing)?|bolster(s|ed|ing)?|'
                   r'garner(s|ed|ing)?|streamlin(e|es|ed|ing)|unveil(s|ed|ing)?|paving|multifaceted|nuanced|'
                   r'interplay|novel|clearly|obviously|trivially|various|numerous|robust|'
                   r'it is (worth|important) (noting|to note)|not only|in conclusion|in summary|'
                   r'plays? an? (crucial|pivotal|key|vital) role)\b', re.I)
tails = re.compile(r', (highlighting|underscoring|showcasing|demonstrating|ensuring|enabling|paving|'
                   r'allowing|providing|offering|reflecting|indicating|making)\b')
import glob
for path in sorted(glob.glob('sections/*.tex')):
    for number, line in enumerate(open(path, encoding='utf-8'), 1):
        if line.lstrip().startswith('%'):
            continue
        for match in avoid.finditer(line):
            print('style: %s:%d: "%s"' % (path, number, match.group(0)))
        for match in tails.finditer(line):
            print('tail:  %s:%d: "%s"' % (path, number, match.group(0)))
dashes = sum(open(p, encoding='utf-8').read().count('---') for p in glob.glob('sections/*.tex'))
print('em dashes in sections: %d' % dashes)

if failures:
    print('\nFAILED:')
    for failure in failures:
        print('  - ' + failure)
    sys.exit(1)
