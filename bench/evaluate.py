#!/usr/bin/env python3
"""Evaluate OrchLang's certified bounds, its relational rule, and its flow policy.

This harness is deliberately strict, because an earlier version of it was not.
It used to skip any file that failed to certify, count any nonzero exit code as
a successful security rejection, and return success even when a bound violation
had been recorded.  All three could hide exactly the failures the experiment
exists to find.  Here, every workflow must certify or the run aborts, every
rejection must carry the diagnostic family it was supposed to produce, and any
violation makes the process exit nonzero.

Experiments
-----------

E1  Unary soundness.  Execute every cost workflow under many seeds and check
    each execution against the certificate *componentwise* -- output tokens,
    input tokens, and total separately.  Checking only the total would have
    missed the split bug that an audit found.

E2  Baselines.  Compare against two rules a reasonable engineer might reach for:
    a flat sum over syntactic call sites, and a control-flow-aware rule that
    takes the larger branch arm but charges a retry body once.

E3  Tightness and branch coverage.  Report slack against the largest observed
    execution, together with how often each branch arm actually ran.  Slack
    measured through a dead arm means nothing, so coverage is reported beside it.

E4  Relational soundness.  For every accepted relational workflow, hold the seed
    and the public inputs fixed, enumerate every secret value, and require the
    billing vector to be identical throughout.

E5  Relational precision.  For every rejected relational workflow, search for a
    concrete witness: two secret values whose bills differ.  A rejection without
    a witness is flagged, because it may be a false positive.

E6  Flow policy conformance.  The paired security suite, checked against the
    diagnostic family each case is supposed to raise.
"""

import io
import itertools
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Overridable so `make verify` can reproduce the results without overwriting
# the committed ones, then compare the two.
RESULTS = os.environ.get('ORCHLANG_RESULTS_DIR', os.path.join(HERE, 'results'))
ORCHC = os.path.join(ROOT, 'orchc.exe' if os.name == 'nt' else 'orchc')

SEEDS = 200
PAIRED_SEEDS = 25

# Every unsafe security fixture must raise one of these, so that an unrelated
# parse error or a missing file can never be scored as a security success.
FLOW_CODES = {'E230', 'E231', 'E232', 'E233', 'E234', 'E235', 'E236'}

failures = []


def fail(message):
    failures.append(message)
    print('  FAIL: %s' % message)


def run(args):
    completed = subprocess.run([ORCHC] + args, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def diagnostic_codes(text):
    codes = set()
    for token in text.replace('[', ' [').split():
        if token.startswith('[') and token.endswith(']') and len(token) > 2:
            codes.add(token[1:-1])
    return codes


def certificate(path):
    code, out, err = run(['certify', path])
    if code != 0:
        return None
    return json.loads(out)['workflows'][0]


def execute(path, seed, pins=None):
    args = ['run', path, '--seed', str(seed)]
    for name, value in (pins or {}).items():
        args += ['--pin', '%s=%s' % (name, value)]
    code, out, err = run(args)
    if code != 0:
        return None

    result = {'total': 0, 'input': 0, 'output': 0, 'billing': {}, 'models': []}
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith('actual tokens'):
            parts = stripped.replace('(', ' ').replace(')', ' ').split()
            # "actual tokens  N  (input A + output B)" becomes
            # [actual, tokens, N, input, A, +, output, B]
            result['total'] = int(parts[2])
            result['input'] = int(parts[4])
            result['output'] = int(parts[7])
        elif ' calls ' in stripped and ' in ' in stripped:
            # "<model>  calls C  in I  out O"
            parts = stripped.split()
            result['billing'][parts[0]] = (int(parts[2]), int(parts[4]), int(parts[6]))
        elif 'via' in stripped and ' in ' in stripped:
            # "<binding> = <prompt> via <model>  in I out O"
            result['models'].append(stripped.split('via')[1].split()[0])
    return result


def billing_key(observation):
    return json.dumps(observation['billing'], sort_keys=True)


def orch_files(*parts):
    directory = os.path.join(HERE, *parts)
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, name) for name in os.listdir(directory)
                  if name.endswith('.orch'))


# ------------------------------------------------------------ E1, E2, E3 -----

def flat_baseline(document):
    """Sum every syntactic call's input and output caps.

    Retry-unaware and branch-unaware.  This is what the first version of this
    compiler did.  Note the name: it sums per-call *input and output* upper
    bounds, not just max_tokens.
    """
    code, out, err = run(['ir-json', document])
    if code != 0:
        return None
    total = 0
    for node in json.loads(out)['workflows'][0]['nodes']:
        if node['kind'] == 'Call':
            total += int(node['attributes'].get('out_tokens', 0))
            total += int(node['attributes'].get('in_tokens', 0))
    return total


def control_flow_baseline(document):
    """Take the larger branch arm, but charge a retry body only once.

    A strictly better rule than the flat sum, and still unsound, which is the
    point: branch-awareness alone does not rescue it.
    """
    code, out, err = run(['ir-json', document])
    if code != 0:
        return None
    nodes = json.loads(out)['workflows'][0]['nodes']
    per_region = {}
    for node in nodes:
        if node['kind'] != 'Call':
            continue
        cost = int(node['attributes'].get('out_tokens', 0)) + \
            int(node['attributes'].get('in_tokens', 0))
        per_region.setdefault(node['region'], 0)
        per_region[node['region']] += cost

    total = 0
    branch_groups = {}
    for region, cost in per_region.items():
        if '/then@' in region or '/else@' in region:
            head = region.rsplit('/', 1)[0]
            marker = region.rsplit('@', 1)[-1]
            branch_groups.setdefault((head, marker), []).append(cost)
        else:
            total += cost
    for costs in branch_groups.values():
        total += max(costs)
    return total


def evaluate_cost():
    rows = []
    totals = {'runs': 0, 'certified': 0, 'flat': 0, 'control_flow': 0,
              'output_component': 0, 'input_component': 0}

    for path in orch_files('cost'):
        name = os.path.basename(path)[:-5]
        document = certificate(path)
        if document is None:
            fail('cost workflow did not certify: %s' % name)
            continue
        bound = document['bound']
        flat = flat_baseline(path)
        cfa = control_flow_baseline(path)
        if flat is None or cfa is None:
            fail('could not compute a baseline for %s' % name)
            continue

        observed = []
        local = {'certified': 0, 'flat': 0, 'control_flow': 0,
                 'output_component': 0, 'input_component': 0}
        arms = set()
        for seed in range(1, SEEDS + 1):
            run_data = execute(path, seed)
            if run_data is None:
                fail('execution failed: %s seed %d' % (name, seed))
                continue
            observed.append(run_data['total'])
            totals['runs'] += 1
            arms.add(tuple(sorted(set(run_data['models']))))

            if run_data['total'] > bound['total_tokens']:
                local['certified'] += 1
            if run_data['output'] > bound['guaranteed_tokens']:
                local['output_component'] += 1
            if run_data['input'] > bound['estimated_tokens']:
                local['input_component'] += 1
            if run_data['total'] > flat:
                local['flat'] += 1
            if run_data['total'] > cfa:
                local['control_flow'] += 1

        for key in local:
            totals[key] += local[key]

        peak = max(observed) if observed else 0
        rows.append({
            'workflow': name,
            'certified': bound['total_tokens'],
            'out<=': bound['guaranteed_tokens'],
            'in<=': bound['estimated_tokens'],
            'flat': flat,
            'cfa': cfa,
            'peak': peak,
            'slack': round(bound['total_tokens'] / float(peak), 2) if peak else None,
            'paths': len(arms),
            'cert_viol': local['certified'],
            'comp_viol': local['output_component'] + local['input_component'],
            'flat_viol': local['flat'],
            'cfa_viol': local['control_flow'],
        })

    if totals['certified'] or totals['output_component'] or totals['input_component']:
        fail('the certified bound was violated (%d total, %d output, %d input)'
             % (totals['certified'], totals['output_component'], totals['input_component']))
    return rows, totals


# ------------------------------------------------------------- E4 and E5 -----

def secret_assignments(path):
    """Every combination of secret values the harness will pin."""
    text = io.open(path, encoding='utf-8').read()
    lengths, flags = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('secret '):
            continue
        name = line.split()[1].rstrip(':')
        if ': boolean' in line:
            flags.append(name)
        else:
            cap = 8
            if 'max_tokens' in line:
                cap = int(line.split('max_tokens')[1].split(';')[0].strip())
            lengths.append((name, cap))

    options = []
    for name in flags:
        options.append([(name, 'true'), (name, 'false')])
    for name, cap in lengths:
        options.append([(name, str(value)) for value in range(0, cap + 1)])
    if not options:
        return []
    return [dict(combination) for combination in itertools.product(*options)]


def evaluate_relational():
    rows = []
    accepted_checked = 0
    accepted_violations = 0
    rejected_with_witness = 0
    rejected_without_witness = 0

    public_pins = {'x': 37, 'y': 61, 'source': 40, 'page': 55}

    for expectation in ('accept', 'reject'):
        for path in orch_files('relational', expectation):
            name = os.path.basename(path)[:-5]
            code, out, err = run(['check', path])
            accepted = code == 0
            codes = diagnostic_codes(err)

            if expectation == 'accept' and not accepted:
                fail('relational workflow expected to be accepted was rejected: %s (%s)'
                     % (name, ' '.join(sorted(codes))))
                continue
            if expectation == 'reject' and accepted:
                fail('relational workflow expected to be rejected was accepted: %s' % name)
                continue
            if expectation == 'reject' and 'E236' not in codes:
                fail('relational rejection of %s did not cite E236 (%s)'
                     % (name, ' '.join(sorted(codes))))
                continue

            assignments = secret_assignments(path)
            if not assignments:
                fail('no secrets to vary in %s' % name)
                continue

            differing = 0
            compared = 0
            witness = None
            for seed in range(1, PAIRED_SEEDS + 1):
                observations = {}
                for assignment in assignments:
                    pins = dict(public_pins)
                    pins.update(assignment)
                    observation = execute(path, seed, pins)
                    if observation is None:
                        fail('paired execution failed: %s seed %d' % (name, seed))
                        continue
                    observations[json.dumps(assignment, sort_keys=True)] = observation

                keys = sorted(observations)
                if len(keys) < 2:
                    continue
                reference = billing_key(observations[keys[0]])
                for key in keys[1:]:
                    compared += 1
                    if billing_key(observations[key]) != reference:
                        differing += 1
                        if witness is None:
                            witness = '%s vs %s' % (keys[0], key)

            if expectation == 'accept':
                accepted_checked += compared
                if differing:
                    accepted_violations += differing
                    fail('accepted workflow %s changed its bill with the secret (%d of %d '
                         'comparisons; e.g. %s)' % (name, differing, compared, witness))
            else:
                if differing:
                    rejected_with_witness += 1
                else:
                    rejected_without_witness += 1

            rows.append({
                'workflow': name,
                'expected': expectation,
                'verdict': 'accept' if accepted else 'reject',
                'comparisons': compared,
                'bills_differ': differing,
                'witness': (witness or '')[:48],
            })

    return rows, {
        'accepted_comparisons': accepted_checked,
        'accepted_violations': accepted_violations,
        'rejected_with_witness': rejected_with_witness,
        'rejected_without_witness': rejected_without_witness,
    }


# ------------------------------------------------------------------- E6 ------

def evaluate_security():
    rows = []
    counts = {'tp': 0, 'fn': 0, 'tn': 0, 'fp': 0}

    for path in orch_files('security', 'unsafe'):
        code, out, err = run(['check', path])
        codes = diagnostic_codes(err)
        name = os.path.basename(path)[:-5]
        if code == 0:
            counts['fn'] += 1
            fail('unsafe workflow accepted: %s' % name)
            verdict = 'ACCEPT'
        elif not (codes & FLOW_CODES):
            counts['fn'] += 1
            fail('unsafe workflow %s was rejected, but not for a flow reason (%s)'
                 % (name, ' '.join(sorted(codes)) or 'no codes'))
            verdict = 'wrong-reason'
        else:
            counts['tp'] += 1
            verdict = 'reject'
        rows.append({'workflow': name, 'expected': 'reject', 'verdict': verdict,
                     'codes': ' '.join(sorted(codes))})

    for path in orch_files('security', 'safe'):
        code, out, err = run(['check', path])
        codes = diagnostic_codes(err)
        name = os.path.basename(path)[:-5]
        if code == 0:
            counts['tn'] += 1
            verdict = 'accept'
        else:
            counts['fp'] += 1
            fail('safe workflow rejected: %s (%s)' % (name, ' '.join(sorted(codes))))
            verdict = 'REJECT'
        rows.append({'workflow': name, 'expected': 'accept', 'verdict': verdict,
                     'codes': ' '.join(sorted(codes))})

    return rows, counts


# ---------------------------------------------------------------- output -----

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
        return 2
    os.makedirs(RESULTS, exist_ok=True)

    print('E1-E3: executing the cost suite (%d seeds each) ...' % SEEDS)
    cost_rows, cost_totals = evaluate_cost()

    print('E4-E5: paired relational experiment ...')
    relational_rows, relational_totals = evaluate_relational()

    print('E6: flow policy conformance ...')
    security_rows, security_counts = evaluate_security()

    print('timing ...')
    timed = orch_files('cost') + orch_files('security', 'safe')
    start = time.time()
    for path in timed:
        run(['certify', path])
    elapsed = time.time() - start

    report = io.StringIO()
    report.write('OrchLang evaluation\n===================\n\n')

    report.write('E1-E3  certified bound versus observed execution\n')
    report.write('       (%d workflows, %d executions; "paths" counts distinct model-sets\n'
                 '        observed, so 1 means a branch arm never ran)\n\n'
                 % (len(cost_rows), cost_totals['runs']))
    report.write(table(cost_rows, ['workflow', 'certified', 'out<=', 'in<=', 'flat', 'cfa',
                                   'peak', 'slack', 'paths', 'cert_viol', 'comp_viol',
                                   'flat_viol', 'cfa_viol']))
    report.write('\n')
    report.write('  certified total exceeded        : %d of %d\n'
                 % (cost_totals['certified'], cost_totals['runs']))
    report.write('  certified output component      : %d of %d\n'
                 % (cost_totals['output_component'], cost_totals['runs']))
    report.write('  certified input component       : %d of %d\n'
                 % (cost_totals['input_component'], cost_totals['runs']))
    report.write('  flat per-call sum exceeded      : %d of %d (%.1f%%)\n'
                 % (cost_totals['flat'], cost_totals['runs'],
                    100.0 * cost_totals['flat'] / cost_totals['runs'] if cost_totals['runs'] else 0))
    report.write('  control-flow-aware rule exceeded: %d of %d (%.1f%%)\n'
                 % (cost_totals['control_flow'], cost_totals['runs'],
                    100.0 * cost_totals['control_flow'] / cost_totals['runs']
                    if cost_totals['runs'] else 0))
    slacks = [r['slack'] for r in cost_rows if r['slack']]
    if slacks:
        report.write('  slack vs peak observed          : median %.2fx, range %.2f-%.2fx\n'
                     % (sorted(slacks)[len(slacks) // 2], min(slacks), max(slacks)))
    dead = [r['workflow'] for r in cost_rows if r['paths'] < 2 and 'branch' in r['workflow']]
    report.write('  branch workflows with a dead arm: %d\n' % len(dead))
    if dead:
        report.write('    %s\n' % ', '.join(dead))
    report.write('\n')

    report.write('E4-E5  relational obligation: does the secret move the bill?\n\n')
    report.write(table(relational_rows, ['workflow', 'expected', 'verdict', 'comparisons',
                                         'bills_differ', 'witness']))
    report.write('\n')
    report.write('  accepted workflows: %d paired comparisons, %d showed a different bill\n'
                 % (relational_totals['accepted_comparisons'],
                    relational_totals['accepted_violations']))
    report.write('  rejected workflows: %d had a concrete leaking witness, %d had none\n'
                 % (relational_totals['rejected_with_witness'],
                    relational_totals['rejected_without_witness']))
    report.write('\n')

    report.write('E6  flow policy conformance on the paired security suite\n\n')
    report.write(table(security_rows, ['workflow', 'expected', 'verdict', 'codes']))
    report.write('\n')
    report.write('  unsafe rejected for a flow reason : %d\n' % security_counts['tp'])
    report.write('  unsafe accepted or wrong reason   : %d\n' % security_counts['fn'])
    report.write('  safe accepted                     : %d\n' % security_counts['tn'])
    report.write('  safe rejected                     : %d\n' % security_counts['fp'])
    report.write('\n')
    report.write('  This measures conformance to the declared policy, not robustness to\n'
                 '  adversarial text: the safe variants differ from the unsafe ones by a\n'
                 '  trusted endorsement or declassification, which the compiler records\n'
                 '  rather than verifies.\n\n')

    report.write('Analysis cost\n\n')
    report.write('  %d workflows certified in %.2f s (%.1f ms each, including process startup;\n'
                 '  this is not an isolated measurement of analyser time)\n'
                 % (len(timed), elapsed, 1000.0 * elapsed / len(timed)))

    if failures:
        report.write('\nFAILURES (%d)\n\n' % len(failures))
        for message in failures:
            report.write('  - %s\n' % message)

    text = report.getvalue()
    io.open(os.path.join(RESULTS, 'evaluation.txt'), 'w', encoding='utf-8',
            newline='\n').write(text)
    io.open(os.path.join(RESULTS, 'cost.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(cost_rows, indent=2))
    io.open(os.path.join(RESULTS, 'relational.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(relational_rows, indent=2))
    io.open(os.path.join(RESULTS, 'security.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(security_rows, indent=2))
    print()
    print(text)

    if failures:
        print('%d experiment assertion(s) failed' % len(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
