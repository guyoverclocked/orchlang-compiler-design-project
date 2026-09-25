#!/usr/bin/env python3
"""What candidate journals actually published, January 2023 to today.

Downloads the titles of every journal article each candidate journal
registered with Crossref since 2023-01-01 and counts titles matching the
topics of docs/PAPER.md.  Titles only, because most Elsevier journals deposit
no abstracts with Crossref and matching abstracts would favour the publishers
that do.  The counts back the venue ranking in docs/SUBMISSION_PLAN.md.

    python scripts/journal_survey.py            # cache in bench/.cache/journals
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'bench', '.cache', 'journals')
SINCE = '2023-01-01'

JOURNALS = [
    ('Science of Computer Programming', '0167-6423'),
    ('Journal of Computer Languages', '2590-1184'),
    ('The Art, Science, and Engineering of Programming', '2473-7321'),
    ('Int. J. on Software Tools for Technology Transfer', '1433-2779'),
    ('International Journal of Information Security', '1615-5262'),
    ('Journal of Computer Security', '0926-227X'),
    ('J. of Information Security and Applications', '2214-2126'),
    ('Computers & Security', '0167-4048'),
    ('Cybersecurity (Springer)', '2523-3246'),
    ('J. of Logical and Algebraic Methods in Programming', '2352-2208'),
    ('Journal of Systems and Software', '0164-1212'),
    ('IEEE Trans. Dependable and Secure Computing', '1545-5971'),
]

TOPICS = [
    ('LLM', r'\b(large language models?|LLMs?|GPT-?\d|ChatGPT|language model agents?|AI agents?|LLM agents?)\b'),
    ('prompt injection', r'prompt injection|jailbreak'),
    ('information flow', r'information[- ]flow|non-?interference|\btaint'),
    ('side channel/leakage', r'side[- ]channel|covert channel|timing channel|constant[- ]time|leakage'),
    ('resource/cost', r'resource (analysis|bound|usage|consumption)|cost analysis|amorti[sz]ed|worst[- ]case execution'),
    ('mechanised proof', r'\bCoq\b|\bRocq\b|Isabelle|\bLean\b|mechani[sz]ed|proof assistant|\bAgda\b'),
]


def fetch(url):
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'orchlang-journal-survey/1.0'})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except Exception as error:  # network hiccups and rate limits
            print('retrying (%s)' % error, file=sys.stderr)
            time.sleep(2 ** attempt)
    raise SystemExit('Crossref did not answer: ' + url)


def titles(issn):
    path = os.path.join(CACHE, issn + '.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    items, cursor = [], '*'
    while True:
        data = fetch('https://api.crossref.org/journals/%s/works?filter=from-pub-date:%s,type:journal-article'
                     '&select=DOI,title,published&rows=1000&cursor=%s'
                     % (issn, SINCE, urllib.parse.quote(cursor)))
        batch = data['message']['items']
        items += batch
        cursor = data['message'].get('next-cursor')
        if len(batch) < 1000:
            break
    os.makedirs(CACHE, exist_ok=True)
    json.dump(items, open(path, 'w', encoding='utf-8'))
    return items


def main():
    header = ['journal', 'articles'] + [name for name, _ in TOPICS]
    print(' | '.join(header))
    for name, issn in JOURNALS:
        items = titles(issn)
        counts = []
        for _, pattern in TOPICS:
            counts.append(sum(1 for item in items
                              if re.search(pattern, ' '.join(item.get('title') or []), re.I)))
        print(' | '.join([name, str(len(items))] + [str(c) for c in counts]))


if __name__ == '__main__':
    main()
