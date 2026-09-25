#!/usr/bin/env python3
"""Check that every port's prompt text is the source's text (PROTOCOL.md P1).

Every string literal of every port -- prompt templates and literal arguments --
is split at its placeholders.  Each resulting piece of text is covered greedily
by the longest prefixes that occur in some string constant of the pinned
source: string literals and f-string parts of the notebook's code, the LangChain
Hub prompts it pulls, or AgentDojo's system message and task prompt.  A piece
passes if every uncovered stretch is shorter than 20 characters (the glue a
port adds between messages, or an f-string's own short literals).  A JSON piece
(a tool schema, P4) passes if each of its string values of 20 characters or
more passes.

Needs the pinned sources:  bash bench/real/fetch_sources.sh
Prints a table and exits nonzero if any piece fails.
"""
import ast
import glob
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', '.cache', 'real')
MIN_RUN = 20
REPO_DIR = {'anthropics/anthropic-cookbook': 'anthropic-cookbook',
            'langchain-ai/langgraph': 'langgraph', 'ethz-spylab/agentdojo': 'agentdojo'}


def python_strings(code):
    """Every string constant in a piece of Python code, f-string parts included."""
    lines = [line for line in code.split('\n') if not line.lstrip().startswith(('%', '!'))]
    try:
        tree = ast.parse('\n'.join(lines))
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
    return found


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_strings(item)


def source_strings(candidate, canaries):
    source = candidate['source']
    root = os.path.join(CACHE, REPO_DIR[source['repo']])
    strings = []
    path = os.path.join(root, source['path'])
    if path.endswith('.ipynb'):
        notebook = json.load(open(path, encoding='utf-8'))
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                strings += python_strings(''.join(cell['source']))
    else:
        strings += python_strings(open(path, encoding='utf-8').read())
    for name in source.get('hub_prompts', {}):
        hub = json.load(open(os.path.join(CACHE, 'hub', name.replace('/', '__') + '.json')))
        strings += list(json_strings(hub['manifest']))
    if source['repo'] == 'ethz-spylab/agentdojo':
        system = yaml.safe_load(open(os.path.join(root, 'src', 'agentdojo', 'data', 'system_messages.yaml')))
        strings.append(system['default'])
        strings.append(canaries[candidate['id']]['prompt'])
    return [s for s in strings if s]


def literals(path):
    """(kind, text) for every string literal in an .orch file, unescaped, with
    placeholders replaced by a separator."""
    text = open(path, encoding='utf-8').read()
    text = '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('//'))
    # Only prompt templates and call arguments are the source's text; model
    # strings and endorsement justifications are the port's own.
    sources = [m.group(1) for m in re.finditer(r'\bprompt\s+\w+\([^)]*\)\s*->\s*\w+\s*=\s*"((?:[^"\\]|\\.)*)"', text)]
    for call in re.finditer(r'\bcall\s+\w+\(([^;]*)\)\s*using', text):
        sources += re.findall(r'"((?:[^"\\]|\\.)*)"', call.group(1))
    out = []
    for raw in sources:
        pieces, current, index = [], [], 0
        while index < len(raw):
            pair = raw[index:index + 2]
            if pair in ('{{', '}}'):
                current.append(pair[0])
                index += 2
                continue
            placeholder = re.match(r'\{[A-Za-z_][A-Za-z0-9_]*\}', raw[index:])
            if placeholder:
                pieces.append(''.join(current))
                current = []
                index += placeholder.end()
                continue
            if raw[index] == '\\' and index + 1 < len(raw):
                current.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\'}[raw[index + 1]])
                index += 2
                continue
            current.append(raw[index])
            index += 1
        pieces.append(''.join(current))
        out.extend(piece for piece in pieces if piece.strip())
    return out


def uncovered(piece, strings):
    """Stretches of piece not covered by long prefixes found in strings."""
    gaps, gap, index = [], [], 0
    while index < len(piece):
        low, high = 0, len(piece) - index
        while low < high:  # longest k with piece[index:index+k] in some string
            mid = (low + high + 1) // 2
            chunk = piece[index:index + mid]
            if any(chunk in s for s in strings):
                low = mid
            else:
                high = mid - 1
        if low >= min(MIN_RUN, len(piece) - index) and low > 0:
            if gap:
                gaps.append(''.join(gap))
                gap = []
            index += low
        else:
            gap.append(piece[index])
            index += 1
    if gap:
        gaps.append(''.join(gap))
    return gaps


def is_json(part):
    stripped = part.strip()
    if not (stripped.startswith('{') and stripped.endswith('}')):
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def check_piece(piece, strings):
    """Stretches of 20 characters or more that no source string covers."""
    gaps, prose = [], []
    for part in piece.split('\n\n'):
        schema = is_json(part)
        if schema is None:
            prose.append(part)
            continue
        for value in json_strings(schema):
            if len(value) >= MIN_RUN:
                gaps += [gap for gap in uncovered(value, strings) if len(gap) >= MIN_RUN]
    gaps += [gap for gap in uncovered('\n\n'.join(prose), strings) if len(gap) >= MIN_RUN]
    return gaps


def main():
    manifest = json.load(open(os.path.join(HERE, 'manifest.json')))
    canaries = json.load(open(os.path.join(HERE, 'agentdojo_canaries.json')))
    if not os.path.isdir(CACHE):
        sys.exit('sources not found; run bench/real/fetch_sources.sh')
    failures, rows = 0, []
    for candidate in manifest['candidates']:
        if candidate['decision'] != 'port':
            continue
        strings = source_strings(candidate, canaries)
        for path in sorted(glob.glob(os.path.join(HERE, candidate['id'] + '*.orch'))):
            pieces = literals(path)
            total = sum(len(p) for p in pieces)
            bad = []
            glue = 0
            for piece in pieces:
                bad += check_piece(piece, strings)
                prose = '\n\n'.join(p for p in piece.split('\n\n') if is_json(p) is None)
                glue += sum(len(g) for g in uncovered(prose, strings) if len(g) < MIN_RUN)
            rows.append((os.path.basename(path), len(pieces), total, glue, len(bad)))
            for gap in bad:
                failures += 1
                print('  UNSOURCED in %s: %r' % (os.path.basename(path), gap[:120]))
    print('%-40s %7s %8s %6s %5s' % ('port', 'pieces', 'chars', 'glue', 'bad'))
    for row in rows:
        print('%-40s %7d %8d %6d %5d' % row)
    print('%d unsourced stretches' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
