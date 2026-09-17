#!/usr/bin/env python3
"""Evaluate OrchLang's certified bounds and its information-flow analysis.

Four questions are answered, and each writes a table to ``bench/results/``.

RQ1  Is the certified token bound ever exceeded by a real execution?
     Every cost workflow is run under many seeds and every run is checked
     against its certificate.  A single violation falsifies the soundness
     claim, so the interesting number is the count, not an average.

RQ2  Does the flat rule -- sum each syntactic call's max_tokens, the rule the
     first version of this compiler used and the obvious thing to reach for --
     actually hold?  The same runs are checked against it.

RQ3  How much slack does the bound carry?  Reported as bound divided by the
     largest observed execution, so a reader can see the price of soundness.

RQ4  Does the information-flow analysis separate the unsafe workflows from
     their safe counterparts?  The suite is paired, so false positives are
     measured on workflows that differ from an unsafe one by a single edit.
"""

import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, 'results')
ORCHC = os.path.join(ROOT, 'orchc.exe' if os.name == 'nt' else 'orchc')

SEEDS = 200


def run(args):
    completed = subprocess.run([ORCHC] + args, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def certified_bound(path):
    """The compiler's certified total, and its two components."""
    code, out, err = run(['certify', path])
    if code != 0:
        return None
    document = json.loads(out)
    workflow = document['workflows'][0]
    return workflow['bound']


def flat_bound(path):
    """The rule this compiler used before: add up every syntactic call's cap.

    It ignores that a branch runs one arm, and -- the part that matters -- it
    ignores that a retry block runs its body more than once.
    """
    code, out, err = run(['ir-json', path])
    if code != 0:
        return None
    document = json.loads(out)
    total = 0
    for node in document['workflows'][0]['nodes']:
        if node['kind'] == 'Call':
            total += int(node['attributes'].get('out_tokens', 0))
            total += int(node['attributes'].get('in_tokens', 0))
    return total


def actual_tokens(path, seed):
    code, out, err = run(['run', path, '--seed', str(seed)])
    if code != 0:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('actual tokens'):
            return int(line.split()[2])
    return None


def cost_files():
    directory = os.path.join(HERE, 'cost')
    return sorted(os.path.join(directory, name) for name in os.listdir(directory)
                  if name.endswith('.orch'))


def security_files(kind):
    directory = os.path.join(HERE, 'security', kind)
    return sorted(os.path.join(directory, name) for name in os.listdir(directory)
                  if name.endswith('.orch'))


def evaluate_cost():
    rows = []
    certified_violations = 0
    flat_violations = 0
    total_runs = 0

    for path in cost_files():
        name = os.path.basename(path)[:-5]
        certified = certified_bound(path)
        flat = flat_bound(path)
        if certified is None or flat is None:
            print('  skipped (did not certify): %s' % name)
            continue

        observed = []
        local_certified_violations = 0
        local_flat_violations = 0
        for seed in range(1, SEEDS + 1):
            actual = actual_tokens(path, seed)
            if actual is None:
                continue
            observed.append(actual)
            total_runs += 1
            if actual > certified['total_tokens']:
                local_certified_violations += 1
            if actual > flat:
                local_flat_violations += 1

        certified_violations += local_certified_violations
        flat_violations += local_flat_violations
        peak = max(observed) if observed else 0
        mean = sum(observed) / float(len(observed)) if observed else 0.0

        rows.append({
            'workflow': name,
            'certified': certified['total_tokens'],
            'guaranteed': certified['guaranteed_tokens'],
            'estimated': certified['estimated_tokens'],
            'flat': flat,
            'peak_actual': peak,
            'mean_actual': round(mean, 1),
            'slack_vs_peak': round(certified['total_tokens'] / float(peak), 2) if peak else None,
            'certified_violations': local_certified_violations,
            'flat_violations': local_flat_violations,
            'runs': len(observed),
        })

    return rows, certified_violations, flat_violations, total_runs


def evaluate_security():
    unsafe = security_files('unsafe')
    safe = security_files('safe')

    rows = []
    true_positive = 0
    false_negative = 0
    for path in unsafe:
        code, out, err = run(['check', path])
        rejected = code != 0
        codes = sorted({token.strip('[]') for token in err.split()
                        if token.startswith('[E') or token.startswith('[W')})
        rows.append({'workflow': os.path.basename(path)[:-5], 'expected': 'reject',
                     'verdict': 'reject' if rejected else 'ACCEPT', 'codes': ' '.join(codes)})
        if rejected:
            true_positive += 1
        else:
            false_negative += 1

    true_negative = 0
    false_positive = 0
    for path in safe:
        code, out, err = run(['check', path])
        accepted = code == 0
        codes = sorted({token.strip('[]') for token in err.split()
                        if token.startswith('[E') or token.startswith('[W')})
        rows.append({'workflow': os.path.basename(path)[:-5], 'expected': 'accept',
                     'verdict': 'accept' if accepted else 'REJECT', 'codes': ' '.join(codes)})
        if accepted:
            true_negative += 1
        else:
            false_positive += 1

    return rows, true_positive, false_negative, true_negative, false_positive


def evaluate_timing():
    paths = cost_files() + security_files('safe')
    start = time.time()
    for path in paths:
        run(['certify', path])
    elapsed = time.time() - start
    return len(paths), elapsed


def table(rows, columns):
    if not rows:
        return '(no rows)\n'
    widths = {c: max(len(c), max(len(str(r.get(c, ''))) for r in rows)) for c in columns}
    out = '  '.join(c.ljust(widths[c]) for c in columns) + '\n'
    out += '  '.join('-' * widths[c] for c in columns) + '\n'
    for row in rows:
        out += '  '.join(str(row.get(c, '')).ljust(widths[c]) for c in columns) + '\n'
    return out


def main():
    if not os.path.exists(ORCHC):
        print('build orchc first', file=sys.stderr)
        return 1
    os.makedirs(RESULTS, exist_ok=True)

    print('RQ1-RQ3: executing the cost suite under %d seeds each ...' % SEEDS)
    cost_rows, certified_violations, flat_violations, total_runs = evaluate_cost()

    print('RQ4: checking the paired security suite ...')
    security_rows, tp, fn, tn, fp = evaluate_security()

    print('timing ...')
    timed_files, elapsed = evaluate_timing()

    report = io.StringIO()
    report.write('OrchLang evaluation\n')
    report.write('===================\n\n')

    report.write('RQ1/RQ2/RQ3  certified bound vs observed execution (%d workflows, %d runs)\n\n'
                 % (len(cost_rows), total_runs))
    report.write(table(cost_rows, ['workflow', 'certified', 'guaranteed', 'estimated', 'flat',
                                   'peak_actual', 'mean_actual', 'slack_vs_peak',
                                   'certified_violations', 'flat_violations']))
    report.write('\n')
    report.write('  certified bound exceeded : %d of %d runs\n' % (certified_violations, total_runs))
    report.write('  flat bound exceeded      : %d of %d runs (%.1f%%)\n'
                 % (flat_violations, total_runs,
                    100.0 * flat_violations / total_runs if total_runs else 0.0))
    unsound_workflows = [r['workflow'] for r in cost_rows if r['flat_violations'] > 0]
    report.write('  workflows where the flat bound is unsound: %d of %d\n'
                 % (len(unsound_workflows), len(cost_rows)))
    if unsound_workflows:
        report.write('    %s\n' % ', '.join(unsound_workflows))
    slacks = [r['slack_vs_peak'] for r in cost_rows if r['slack_vs_peak']]
    if slacks:
        report.write('  slack vs peak observed: median %.2fx, min %.2fx, max %.2fx\n'
                     % (sorted(slacks)[len(slacks) // 2], min(slacks), max(slacks)))
    report.write('\n')

    report.write('RQ4  information-flow analysis on the paired security suite\n\n')
    report.write(table(security_rows, ['workflow', 'expected', 'verdict', 'codes']))
    report.write('\n')
    report.write('  unsafe rejected (true positive) : %d\n' % tp)
    report.write('  unsafe accepted (false negative): %d\n' % fn)
    report.write('  safe accepted   (true negative) : %d\n' % tn)
    report.write('  safe rejected   (false positive): %d\n' % fp)
    if tp + fn:
        report.write('  recall    %.3f\n' % (tp / float(tp + fn)))
    if tp + fp:
        report.write('  precision %.3f\n' % (tp / float(tp + fp)))
    report.write('\n')

    report.write('Analysis cost\n\n')
    report.write('  %d workflows certified in %.2f s (%.1f ms each, including process startup)\n'
                 % (timed_files, elapsed, 1000.0 * elapsed / timed_files))

    text = report.getvalue()
    io.open(os.path.join(RESULTS, 'evaluation.txt'), 'w', encoding='utf-8',
            newline='\n').write(text)
    io.open(os.path.join(RESULTS, 'cost.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(cost_rows, indent=2))
    io.open(os.path.join(RESULTS, 'security.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(security_rows, indent=2))
    print()
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
