#!/usr/bin/env python3
"""Evaluate OrchLang's certified bounds, its relational rule, and its flow policy.

This harness is deliberately strict, because an earlier version of it was not.
It used to skip any file that failed to certify, count any nonzero exit code as
a successful security rejection, and return success even when a bound violation
had been recorded.  All three could hide exactly the failures the experiment
exists to find.  Here, every workflow must certify or the run aborts, every
rejection must carry the diagnostic family it was supposed to produce, and any
violation makes the process exit nonzero.

It was then made stricter again, because it shared a blind spot with the
analysis it checked.  The runtime it drove drew every model's output length
uniformly whatever the request said, and billed requests with the analysis's
own estimate, which are exactly the assumptions the withdrawn size rule needed;
so that rule's unsound acceptances could never be observed.  Every relational
claim is now checked under a content-dependent provider, a content-sensitive
tokenizer, and three couplings of the provider's randomness, and the requests
the runtime sends are re-billed with real tokenizers.

Experiments
-----------

E0  Audit regressions.  Every counterexample from the external audit of
    2026-09-17 and the self-audit of 2026-09-25 is still caught.
E1  Unary soundness, estimate model.  Execute every cost workflow under many
    seeds and check each execution componentwise -- output tokens, input
    tokens, total -- against the certificate.
E2  Baselines.  A flat sum over syntactic call sites, and a control-flow-aware
    rule that charges a retry body once.
E3  Tightness and branch coverage.
E4  Unary soundness, real tokenization.  The byte-bounded cost suite under the
    runtime's content-sensitive tokenizer: the guaranteed input bound must never
    be exceeded; how often the estimate is exceeded is reported.
E5  Relational soundness and precision, for all three rules.  For every
    relational workflow, enumerate the secrets under every provider, coupling
    and accounting mode and compare what the workflow's observer sees.  An
    accepted workflow that shows two different observations is a failure of
    the rule that accepted it; for the content rule it fails the harness.
E6  Real tokenizers.  Requests from workflows the withdrawn size rule accepts
    and the content rule rejects are re-billed with real tokenizers.
E7  Leakage bounds.  The number of distinct observations any execution
    produces must not exceed the certified class count; the interval-counting
    bound of Ngo et al. is reported alongside for comparison.
E8  Flow policy conformance on the paired security suite.
E9  Tokenizer facts, from bench/results/tokenizers.json (bench/tokenizers/
    measure.py), with the headline counterexamples re-verified live.
E10 A real model: does output length depend on request content?  From
    bench/results/provider.json (bench/provider/measure.py).
E11 Ported real-world workflows (bench/real/).

Usage:  python bench/evaluate.py [--offline] [--seeds N]
  --offline   skip E6, E9's live checks and E10's model, which need downloads;
              the report is then marked PARTIAL.
"""

import argparse
import io
import itertools
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

WORKERS = max(1, min(8, os.cpu_count() or 1))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, 'results')
ORCHC = os.path.join(ROOT, 'orchc.exe' if os.name == 'nt' else 'orchc')

SEEDS = 200
PAIRED_SEEDS = 10
MODES_TRACE = [(p, c, a) for p in ('uniform', 'content') for c in ('global', 'model', 'request')
               for a in ('estimate', 'tokenizer')]
MODES_COARSE = [(p, 'request', a) for p in ('uniform', 'content') for a in ('estimate', 'tokenizer')]

# Every unsafe security fixture must raise one of these, so that an unrelated
# parse error or a missing file can never be scored as a security success.
FLOW_CODES = {'E230', 'E231', 'E232', 'E233', 'E234', 'E235', 'E236'}

failures = []
skipped = []


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


def certificate(path, extra=()):
    code, out, err = run(['certify', path] + list(extra))
    if code != 0:
        return None
    return json.loads(out)['workflows'][0]


def execute(path, seed, pins=None, provider='uniform', coupling='global', accounting='estimate'):
    args = ['run', path, '--seed', str(seed), '--json', '--provider', provider,
            '--coupling', coupling, '--accounting', accounting]
    for name, value in (pins or {}).items():
        args += ['--pin', '%s=%s' % (name, value)]
    code, out, err = run(args)
    if code != 0:
        return None
    return json.loads(out)['workflows'][0]


def observation(transcript, observer):
    """Everything one observer can see of one execution."""
    if observer == 'bill':
        return json.dumps(transcript['billing'], sort_keys=True)
    per = {}
    for call in transcript['calls']:
        provider = call['model_string'].split('/')[0] if observer == 'provider' else '*'
        per.setdefault(provider, []).append(
            (call['identity'], call['request'], call['response'], call['input_tokens'],
             call['output_tokens']))
    return json.dumps([per, transcript['retry_attempts']], sort_keys=True)


def orch_files(*parts):
    directory = os.path.join(HERE, *parts)
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, name) for name in os.listdir(directory)
                  if name.endswith('.orch'))


def header_options(path):
    first = io.open(path, encoding='utf-8').readline()
    observer = 'trace'
    if ' observer ' in first:
        observer = first.split(' observer ')[1].split()[0]
    return observer


# -------------------------------------------------------------------- E0 -----

AUDIT_17 = os.path.join(ROOT, 'audit', '2026-09-17')
AUDIT_25 = os.path.join(ROOT, 'audit', '2026-09-25')
# Each 2026-09-25 counterexample, and the withdrawn rule it refutes: that rule
# accepts it, the content rule rejects it, and the runtime must show the leak.
REFUTES = {
    'equal_size_literal': 'sizes',
    'equal_size_template': 'sizes',
    'shadowed_model': 'sizes',
    'shadowed_prompt': 'sizes',
    'retry_reorder': None,
}


def evaluate_audits():
    """Every audit counterexample, still caught.

    2026-09-17: equal_bounds must be rejected and must really leak; the other
    four were accepted programs whose certificate the runtime exceeded, so they
    are executed and checked componentwise.  2026-09-25: each must be rejected
    by the content rule, accepted by the withdrawn rule it refutes, and leak.
    """
    rows = []
    for name in ('literal', 'boolean', 'split', 'shadow'):
        path = os.path.join(AUDIT_17, name + '.orch')
        document = certificate(path)
        if document is None:
            fail('audit counterexample %s no longer certifies' % name)
            continue
        bound = document['bound']
        violations = 0
        for seed in range(1, SEEDS + 1):
            data = execute(path, seed)
            if data is None:
                fail('audit counterexample %s failed to run at seed %d' % (name, seed))
                continue
            if (data['input_tokens'] + data['output_tokens'] > bound['total_tokens'] or
                    data['output_tokens'] > bound['output_tokens'] or
                    data['input_tokens'] > bound['input_tokens_estimated']):
                violations += 1
        if violations:
            fail('audit counterexample %s exceeds its certificate in %d runs' % (name, violations))
        rows.append({'audit': '2026-09-17', 'case': name, 'check': 'bound held in %d runs' % SEEDS,
                     'result': 'ok' if not violations else 'VIOLATED'})

    path = os.path.join(AUDIT_17, 'equal_bounds.orch')
    code, out, err = run(['check', path])
    worst, _, _ = empirical_leak(path)
    ok = code != 0 and 'E236' in diagnostic_codes(err) and worst > 1
    if not ok:
        fail('audit counterexample equal_bounds is not both rejected and leaking')
    rows.append({'audit': '2026-09-17', 'case': 'equal_bounds',
                 'check': 'rejected (E236), leaks under the runtime', 'result': 'ok' if ok else 'FAILED'})

    for name, refuted in sorted(REFUTES.items()):
        path = os.path.join(AUDIT_25, name + '.orch')
        code, out, err = run(['check', path])
        rejected = code != 0 and 'E236' in diagnostic_codes(err)
        accepted_by_refuted = True
        if refuted:
            accepted_by_refuted = run(['check', path, '--relational-rule', refuted])[0] == 0
        worst, _, _ = empirical_leak(path)
        ok = rejected and accepted_by_refuted and worst > 1
        if not ok:
            fail('audit counterexample %s: rejected=%s, accepted by %s=%s, leaks=%s'
                 % (name, rejected, refuted, accepted_by_refuted, worst > 1))
        rows.append({'audit': '2026-09-25', 'case': name,
                     'check': 'rejected, leaks' + (', %s rule accepts' % refuted if refuted else ''),
                     'result': 'ok' if ok else 'FAILED'})
    return rows


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
            total = run_data['input_tokens'] + run_data['output_tokens']
            observed.append(total)
            totals['runs'] += 1
            arms.add(tuple(sorted({call['model'] for call in run_data['calls']})))

            if total > bound['total_tokens']:
                local['certified'] += 1
            if run_data['output_tokens'] > bound['output_tokens']:
                local['output_component'] += 1
            if run_data['input_tokens'] > bound['input_tokens_estimated']:
                local['input_component'] += 1
            if total > flat:
                local['flat'] += 1
            if total > cfa:
                local['control_flow'] += 1

        for key in local:
            totals[key] += local[key]

        peak = max(observed) if observed else 0
        rows.append({
            'workflow': name,
            'certified': bound['total_tokens'],
            'out<=': bound['output_tokens'],
            'in<=': bound['input_tokens_estimated'],
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


# ------------------------------------------------------------------- E4 ------

def evaluate_real_tokenization():
    """The byte-bounded cost suite under the content-sensitive tokenizer."""
    rows = []
    totals = {'runs': 0, 'guaranteed_input': 0, 'output': 0, 'estimate_exceeded': 0}
    for path in orch_files('cost_bytes'):
        name = os.path.basename(path)[:-5]
        document = certificate(path)
        if document is None:
            fail('byte-bounded cost workflow did not certify: %s' % name)
            continue
        bound = document['bound']
        if bound['input_tokens_guaranteed'] is None:
            fail('byte-bounded workflow %s has no guaranteed input bound: %s'
                 % (name, bound.get('input_guarantee_missing')))
            continue
        local = {'guaranteed_input': 0, 'output': 0, 'estimate_exceeded': 0}
        peak_input = 0
        runs = 0
        for provider in ('uniform', 'content'):
            for seed in range(1, SEEDS // 2 + 1):
                run_data = execute(path, seed, provider=provider, accounting='tokenizer')
                if run_data is None:
                    fail('execution failed: %s seed %d' % (name, seed))
                    continue
                runs += 1
                peak_input = max(peak_input, run_data['input_tokens'])
                if run_data['input_tokens'] > bound['input_tokens_guaranteed']:
                    local['guaranteed_input'] += 1
                if run_data['output_tokens'] > bound['output_tokens']:
                    local['output'] += 1
                if run_data['input_tokens'] > bound['input_tokens_estimated']:
                    local['estimate_exceeded'] += 1
        totals['runs'] += runs
        for key in local:
            totals[key] += local[key]
        rows.append({'workflow': name, 'in_est': bound['input_tokens_estimated'],
                     'in_guar': bound['input_tokens_guaranteed'], 'peak_in': peak_input,
                     'guar_slack': round(bound['input_tokens_guaranteed'] / float(peak_input), 2)
                     if peak_input else None,
                     'guar_viol': local['guaranteed_input'], 'est_exceeded': local['estimate_exceeded'],
                     'runs': runs})
    if totals['guaranteed_input'] or totals['output']:
        fail('the guaranteed bound was violated under real tokenization (%d input, %d output)'
             % (totals['guaranteed_input'], totals['output']))
    return rows, totals


# ------------------------------------------------------------------- E5 ------

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
                cap = int(line.split('max_tokens')[1].split(';')[0].split()[0])
            lengths.append((name, cap))

    options = []
    for name in flags:
        options.append([(name, 'true'), (name, 'false')])
    for name, cap in lengths:
        options.append([(name, str(value)) for value in range(0, cap + 1)])
    if not options:
        return []
    return [dict(combination) for combination in itertools.product(*options)]


PUBLIC_PINS = {'x': 37, 'y': 37, 'source': 40, 'page': 55, 'ticket': 12}


def empirical_leak(path, seeds=PAIRED_SEEDS):
    """Distinct observations per seed as the secrets vary, in every mode.

    Returns (worst count over all seeds and modes, the modes that produced more
    than one observation, the number of comparisons made).
    """
    observer = header_options(path)
    modes = MODES_TRACE if observer == 'trace' else MODES_COARSE
    assignments = secret_assignments(path)
    jobs = []
    for provider, coupling, accounting in modes:
        for seed in range(1, seeds + 1):
            for index, assignment in enumerate(assignments):
                pins = dict(PUBLIC_PINS)
                pins.update(assignment)
                jobs.append(((provider, coupling, accounting, seed), index, pins))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        transcripts = list(pool.map(
            lambda job: execute(path, job[0][3], job[2], job[0][0], job[0][1], job[0][2]), jobs))
    seen = {}
    for (key, index, pins), transcript in zip(jobs, transcripts):
        if transcript is None:
            fail('paired execution failed: %s %s' % (os.path.basename(path), key))
            continue
        seen.setdefault(key, set()).add(observation(transcript, observer))
    worst = max((len(values) for values in seen.values()), default=0)
    leaking_modes = sorted({'%s/%s/%s' % key[:3] for key, values in seen.items() if len(values) > 1})
    comparisons = len(seen) * max(0, len(assignments) - 1)
    return worst, leaking_modes, comparisons


def old_harness_leak(path, seeds=PAIRED_SEEDS):
    assignments = secret_assignments(path)
    for seed in range(1, seeds + 1):
        seen = set()
        for assignment in assignments:
            pins = dict(PUBLIC_PINS)
            pins.update(assignment)
            transcript = execute(path, seed, pins, 'uniform', 'global', 'estimate')
            if transcript is not None:
                seen.add(observation(transcript, 'bill'))
        if len(seen) > 1:
            return True
    return False


def evaluate_relational():
    rows = []
    per_rule = {rule: {'accepted': 0, 'accepted_leaking': 0, 'rejected': 0,
                       'rejected_without_witness': 0} for rule in ('bounds', 'sizes', 'content')}
    accepted_comparisons = 0

    for expectation in ('accept', 'reject'):
        for path in orch_files('relational', expectation):
            name = os.path.basename(path)[:-5]
            verdicts = {}
            for rule in ('bounds', 'sizes', 'content'):
                code, out, err = run(['check', path, '--relational-rule', rule])
                verdicts[rule] = 'accept' if code == 0 else 'reject'
                if code != 0 and 'E236' not in diagnostic_codes(err):
                    fail('%s rule rejected %s without citing E236 (%s)'
                         % (rule, name, ' '.join(sorted(diagnostic_codes(err)))))
            if verdicts['content'] != expectation:
                fail('relational workflow %s expected %s, content rule said %s'
                     % (name, expectation, verdicts['content']))

            worst, leaking_modes, comparisons = empirical_leak(path)
            leaks = worst > 1
            # What the previous harness could see: bills only, under the
            # uniform provider, global coupling and estimate accounting.
            old_harness_witness = leaks and old_harness_leak(path)
            for rule in ('bounds', 'sizes', 'content'):
                if verdicts[rule] == 'accept':
                    per_rule[rule]['accepted'] += 1
                    if leaks:
                        per_rule[rule]['accepted_leaking'] += 1
                else:
                    per_rule[rule]['rejected'] += 1
                    if not leaks:
                        per_rule[rule]['rejected_without_witness'] += 1
            if verdicts['content'] == 'accept':
                accepted_comparisons += comparisons
                if leaks:
                    fail('content rule accepted %s but its observer saw %d different observations '
                         'for one seed (modes %s)' % (name, worst, ', '.join(leaking_modes)))

            rows.append({
                'workflow': name,
                'observer': header_options(path),
                'bounds': verdicts['bounds'],
                'sizes': verdicts['sizes'],
                'content': verdicts['content'],
                'leaks': 'yes' if leaks else 'no',
                'old_harness_sees_it': ('yes' if old_harness_witness else 'no') if leaks else '-',
                'witness_modes': len(leaking_modes),
            })
    return rows, per_rule, accepted_comparisons


# ------------------------------------------------------------------- E6 ------

REAL_TOKENIZERS = ['r50k_base', 'cl100k_base', 'o200k_base']


def load_real_tokenizers():
    try:
        import tiktoken
    except ImportError:
        return None
    encoders = {}
    for name in REAL_TOKENIZERS:
        encoder = tiktoken.get_encoding(name)
        encoders[name] = (lambda e: (lambda text: len(e.encode(text, disallowed_special=()))))(encoder)
    return encoders


def evaluate_real_rebilling(relational_rows, offline):
    """Re-bill the requests of workflows the size rule accepts and the content
    rule rejects, with real tokenizers and with the provider held fixed."""
    if offline:
        skipped.append('E6 real-tokenizer re-billing')
        return None
    encoders = load_real_tokenizers()
    if encoders is None:
        fail('E6 needs tiktoken (pip install -r bench/requirements.txt), or pass --offline')
        return None
    rows = []
    for row in relational_rows:
        if not (row['sizes'] == 'accept' and row['content'] == 'reject'):
            continue
        path = os.path.join(HERE, 'relational', 'reject', row['workflow'] + '.orch')
        if not os.path.exists(path):
            path = os.path.join(HERE, 'relational', 'accept', row['workflow'] + '.orch')
        bills = {}
        for flag in ('true', 'false'):
            pins = dict(PUBLIC_PINS)
            pins.update({'flag': flag, 's': 0})
            transcript = execute(path, 1, pins)
            requests = [(call['model_string'], call['request']) for call in transcript['calls']]
            bills[flag] = {name: [(model, count(request)) for model, request in requests]
                           for name, count in encoders.items()}
        differing = [name for name in encoders if bills['true'][name] != bills['false'][name]]
        rows.append({'workflow': row['workflow'],
                     'differs_under': ' '.join(differing) if differing else 'none',
                     'example': '%s vs %s' % (bills['true'][REAL_TOKENIZERS[0]],
                                              bills['false'][REAL_TOKENIZERS[0]])})
    return rows


# ------------------------------------------------------------------- E7 ------

def evaluate_leakage():
    rows = []
    for expectation in ('accept', 'reject'):
        for path in orch_files('leakage', expectation):
            name = os.path.basename(path)[:-5]
            code, out, err = run(['check', path])
            verdict = 'accept' if code == 0 else 'reject'
            if verdict != expectation:
                fail('leakage workflow %s expected %s, got %s' % (name, expectation, verdict))
            document = certificate(path) if verdict == 'accept' else None
            if verdict == 'accept' and document is None:
                fail('accepted leakage workflow %s did not certify' % name)
                continue
            if document is None:
                # Rejected: read the class count from the diagnostic.
                classes = None
                for line in err.splitlines():
                    if 'distinguishable behaviours' in line:
                        classes = int(line.split(' has ')[1].split()[0])
                bits = math.log2(classes) if classes else None
                budget = None
                interval_bits = None
            else:
                leakage = document['leakage']
                classes = leakage['classes']
                bits = leakage['bound_bits']
                budget = leakage['budget_bits']
                bound = document['bound']
                interval_bits = math.log2(bound['total_tokens'] - bound['lower_total_tokens'] + 1)
            worst, leaking_modes, comparisons = empirical_leak(path)
            if classes is not None and worst > classes:
                fail('%s produced %d distinct observations for one seed, above its certified %d '
                     'classes' % (name, worst, classes))
            rows.append({'workflow': name, 'expected': expectation, 'verdict': verdict,
                         'budget': budget if budget is not None else '-',
                         'classes': classes, 'bound_bits': round(bits, 3) if bits is not None else '-',
                         'observed_max': worst,
                         'interval_bits': round(interval_bits, 2) if interval_bits is not None else '-'})

    # The interval bound on workflows the content rule proves leak nothing,
    # among those that call a model at all.
    vacuous = []
    for path in orch_files('relational', 'accept') + orch_files('leakage', 'accept'):
        document = certificate(path)
        if document['leakage']['classes'] != 1 or document['bound']['output_tokens'] == 0:
            continue
        bound = document['bound']
        vacuous.append(math.log2(bound['total_tokens'] - bound['lower_total_tokens'] + 1))
    return rows, vacuous


# ------------------------------------------------------------------- E8 ------

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
                     'codes': ' '.join(sorted(c for c in codes if c.startswith('E')))})

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
                     'codes': ' '.join(sorted(c for c in codes if c.startswith('E')))})

    return rows, counts


# ------------------------------------------------------------------ E9, E10 --

def evaluate_tokenizer_facts(offline):
    path = os.path.join(RESULTS, 'tokenizers.json')
    if not os.path.exists(path):
        fail('bench/results/tokenizers.json is missing; run bench/tokenizers/measure.py')
        return None
    facts = json.load(open(path, encoding='utf-8'))
    if facts.get('quick'):
        fail('bench/results/tokenizers.json was produced with --quick; rerun without it')
    live = []
    if offline:
        skipped.append('E9 live tokenizer checks')
    else:
        encoders = load_real_tokenizers()
        if encoders is None:
            fail('E9 needs tiktoken (pip install -r bench/requirements.txt), or pass --offline')
        else:
            checks = [
                ('r50k_base', 'aaaa', 1), ('r50k_base', 'bbbb', 2),
                ('cl100k_base', ' Attribute', 1), ('cl100k_base', 'profiles', 1),
                ('cl100k_base', ' Attributeprofiles', 6),
            ]
            for name, text, expected in checks:
                got = encoders[name](text)
                live.append((name, text, expected, got))
                if got != expected:
                    fail('live tokenizer check: %s(%r) = %d, expected %d' % (name, text, got, expected))
    return facts, live


def evaluate_provider(offline):
    path = os.path.join(RESULTS, 'provider.json')
    if not os.path.exists(path):
        fail('bench/results/provider.json is missing; run bench/provider/measure.py')
        return None
    return json.load(open(path, encoding='utf-8'))


# ------------------------------------------------------------------ E11 ------

def evaluate_real_workflows():
    manifest = os.path.join(HERE, 'real', 'manifest.json')
    if not os.path.exists(manifest):
        return None
    entries = json.load(open(manifest, encoding='utf-8'))
    rows = []
    for entry in entries['workflows']:
        path = os.path.join(HERE, 'real', entry['file'])
        code, out, err = run(['check', path])
        codes = sorted(c for c in diagnostic_codes(err) if c[0] in 'EW')
        verdict = 'accept' if code == 0 else 'reject'
        if verdict != entry['expected']:
            fail('real workflow %s expected %s, got %s (%s)'
                 % (entry['file'], entry['expected'], verdict, ' '.join(codes)))
        rows.append({'workflow': entry['file'][:-5], 'split': entry['split'],
                     'source': entry['source_short'], 'verdict': verdict,
                     'codes': ' '.join(codes), 'escapes': entry.get('trusted_escapes', 0)})
    return rows, entries


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
    global SEEDS, PAIRED_SEEDS
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true',
                        help='skip experiments that need downloads; the report is marked PARTIAL')
    parser.add_argument('--seeds', type=int, default=SEEDS)
    parser.add_argument('--paired-seeds', type=int, default=PAIRED_SEEDS)
    args = parser.parse_args()
    SEEDS = args.seeds
    PAIRED_SEEDS = args.paired_seeds

    if not os.path.exists(ORCHC):
        print('build orchc first', file=sys.stderr)
        return 2
    os.makedirs(RESULTS, exist_ok=True)

    print('E0: audit counterexamples ...')
    audit_rows = evaluate_audits()
    print('E1-E3: executing the cost suite (%d seeds each) ...' % SEEDS)
    cost_rows, cost_totals = evaluate_cost()
    print('E4: byte-bounded cost suite under real tokenization ...')
    bytes_rows, bytes_totals = evaluate_real_tokenization()
    print('E5: relational suite, three rules, every mode ...')
    relational_rows, per_rule, accepted_comparisons = evaluate_relational()
    print('E6: re-billing with real tokenizers ...')
    rebill_rows = evaluate_real_rebilling(relational_rows, args.offline)
    print('E7: leakage bounds ...')
    leakage_rows, vacuous = evaluate_leakage()
    print('E8: flow policy conformance ...')
    security_rows, security_counts = evaluate_security()
    print('E9-E10: tokenizer and provider facts ...')
    tokenizer = evaluate_tokenizer_facts(args.offline)
    provider = evaluate_provider(args.offline)
    print('E11: ported real workflows ...')
    real = evaluate_real_workflows()

    print('timing ...')
    timed = orch_files('cost') + orch_files('security', 'safe') + orch_files('relational', 'accept')
    start = time.time()
    for path in timed:
        run(['certify', path])
    elapsed = time.time() - start

    report = io.StringIO()
    report.write('OrchLang evaluation\n===================\n\n')
    if skipped:
        report.write('PARTIAL RUN: skipped %s (--offline).\n\n' % '; '.join(skipped))

    report.write('E0  audit counterexamples, still caught\n\n')
    report.write(table(audit_rows, ['audit', 'case', 'check', 'result']))
    report.write('\n')

    report.write('E1-E3  certified bound versus observed execution, estimate model\n')
    report.write('       (%d workflows, %d executions; "paths" counts distinct model-sets\n'
                 '        observed, so 1 means a branch arm never ran)\n\n'
                 % (len(cost_rows), cost_totals['runs']))
    report.write(table(cost_rows, ['workflow', 'certified', 'out<=', 'in<=', 'flat', 'cfa',
                                   'peak', 'slack', 'paths', 'cert_viol', 'comp_viol',
                                   'flat_viol', 'cfa_viol']))
    report.write('\n')
    runs = cost_totals['runs'] or 1
    report.write('  certified total exceeded        : %d of %d\n' % (cost_totals['certified'], runs))
    report.write('  certified output component      : %d of %d\n'
                 % (cost_totals['output_component'], runs))
    report.write('  certified input component       : %d of %d\n'
                 % (cost_totals['input_component'], runs))
    report.write('  flat per-call sum exceeded      : %d of %d (%.1f%%)\n'
                 % (cost_totals['flat'], runs, 100.0 * cost_totals['flat'] / runs))
    report.write('  control-flow-aware rule exceeded: %d of %d (%.1f%%)\n'
                 % (cost_totals['control_flow'], runs, 100.0 * cost_totals['control_flow'] / runs))
    slacks = [r['slack'] for r in cost_rows if r['slack']]
    if slacks:
        report.write('  slack vs peak observed          : median %.2fx, range %.2f-%.2fx\n'
                     % (sorted(slacks)[len(slacks) // 2], min(slacks), max(slacks)))
    dead = [r['workflow'] for r in cost_rows if r['paths'] < 2 and 'branch' in r['workflow']]
    report.write('  branch workflows with a dead arm: %d\n' % len(dead))
    report.write('\n  This checks the implementation against its own estimate model; E4 checks\n'
                 '  the guaranteed bound against a content-sensitive tokenizer.\n\n')

    report.write('E4  guaranteed input bound under real tokenization (content-sensitive\n'
                 '    tokenizer, uniform and content-dependent providers)\n\n')
    report.write(table(bytes_rows, ['workflow', 'in_est', 'in_guar', 'peak_in', 'guar_slack',
                                    'guar_viol', 'est_exceeded', 'runs']))
    bruns = bytes_totals['runs'] or 1
    report.write('\n  guaranteed input exceeded       : %d of %d\n'
                 % (bytes_totals['guaranteed_input'], bruns))
    report.write('  output bound exceeded           : %d of %d\n' % (bytes_totals['output'], bruns))
    report.write('  estimated input exceeded        : %d of %d (%.1f%%) -- an estimate, not a bound\n'
                 % (bytes_totals['estimate_exceeded'], bruns,
                    100.0 * bytes_totals['estimate_exceeded'] / bruns))
    gslack = sorted(r['guar_slack'] for r in bytes_rows if r['guar_slack'])
    if gslack:
        report.write('  guaranteed slack vs peak input  : median %.2fx, range %.2f-%.2fx\n'
                     % (gslack[len(gslack) // 2], gslack[0], gslack[-1]))
    report.write('\n')

    report.write('E5  relational verdicts of three rules, and whether the secret moves what\n'
                 '    the workflow\'s observer sees (%d seeds x every provider/coupling/\n'
                 '    accounting mode x every secret value)\n\n' % PAIRED_SEEDS)
    report.write(table(relational_rows, ['workflow', 'observer', 'bounds', 'sizes', 'content',
                                         'leaks', 'old_harness_sees_it', 'witness_modes']))
    report.write('\n  rule     accepted  of which leak  rejected  rejected without a witness\n')
    for rule in ('bounds', 'sizes', 'content'):
        stats = per_rule[rule]
        report.write('  %-7s  %8d  %13d  %8d  %26d\n'
                     % (rule, stats['accepted'], stats['accepted_leaking'], stats['rejected'],
                        stats['rejected_without_witness']))
    report.write('\n  content rule, accepted workflows: %d paired comparisons, 0 may differ\n'
                 % accepted_comparisons)
    report.write('  "old_harness_sees_it": whether the leak shows in the bill under the\n'
                 '  uniform provider, global coupling and estimate accounting, which is all\n'
                 '  the previous harness compared.\n\n')

    report.write('E6  requests re-billed with real tokenizers (provider held fixed)\n\n')
    if rebill_rows is None:
        report.write('  skipped\n\n')
    else:
        report.write(table(rebill_rows, ['workflow', 'differs_under', 'example']))
        report.write('\n')

    report.write('E7  leakage bounds\n\n')
    report.write(table(leakage_rows, ['workflow', 'expected', 'verdict', 'budget', 'classes',
                                      'bound_bits', 'observed_max', 'interval_bits']))
    if vacuous:
        report.write('\n  interval-counting bound (Ngo et al., Lemma 6-7) on the %d workflows that\n'
                     '  call a model and that the content rule proves leak nothing: %.1f to %.1f\n'
                     '  bits, where the certified bound is 0\n'
                     % (len(vacuous), min(vacuous), max(vacuous)))
    report.write('\n')

    report.write('E8  flow policy conformance on the paired security suite\n\n')
    report.write(table(security_rows, ['workflow', 'expected', 'verdict', 'codes']))
    report.write('\n')
    report.write('  unsafe rejected for a flow reason : %d\n' % security_counts['tp'])
    report.write('  unsafe accepted or wrong reason   : %d\n' % security_counts['fn'])
    report.write('  safe accepted                     : %d\n' % security_counts['tn'])
    report.write('  safe rejected                     : %d\n' % security_counts['fp'])
    report.write('\n'
                 '  This measures conformance to the declared policy, not robustness to\n'
                 '  adversarial text: the safe variants differ from the unsafe ones by a\n'
                 '  trusted endorsement or declassification, which the compiler records\n'
                 '  rather than verifies.\n\n')

    report.write('E9  tokenizer facts (bench/results/tokenizers.txt has the full table)\n\n')
    if tokenizer is not None:
        facts, live = tokenizer
        t = facts['tokenizers']
        report.write('  %d tokenizers, %d UDHR languages, %d code files, %d JSON files\n'
                     % (len(t), facts['corpora']['udhr_languages'], len(facts['corpora']['code_files']),
                        len(facts['corpora']['json_files'])))
        report.write('  max concatenation defect tokens(u+v)-tokens(u)-tokens(v): %d to %d\n'
                     % (min(e['q4_concatenation']['max_defect'] for e in t.values()),
                        max(e['q4_concatenation']['max_defect'] for e in t.values())))
        report.write('  max re-encoded tokens per generated token, same tokenizer: %.2f to %.2f\n'
                     % (min(e['q3_sequences']['max_reencoded_tokens_per_generated_token'] for e in t.values()),
                        max(e['q3_sequences']['max_reencoded_tokens_per_generated_token'] for e in t.values())))
        over = [n for n, e in t.items() if e['q1_code_points']['max_tokens_minus_bytes'] > 0]
        report.write('  tokenizers with tokens > bytes on some code point: %d (%s)\n'
                     % (len(over), ', '.join(over)))
        ml = [e['q5_estimate']['multilingual']['estimate_exceeded_pct'] for e in t.values()]
        code = [e['q5_estimate']['code']['estimate_exceeded_pct'] for e in t.values()]
        report.write('  chars/4 estimate exceeded: %.1f-%.1f%% of multilingual windows, '
                     '%.1f-%.1f%% of code windows\n' % (min(ml), max(ml), min(code), max(code)))
        q7 = [e['q7_equal_length']['counts_differ_pct'] for e in t.values()]
        report.write('  equal-length string pairs with different token counts: %.1f-%.1f%%\n'
                     % (min(q7), max(q7)))
        for name, text, expected, got in live:
            report.write('  live: %s(%r) = %d\n' % (name, text, got))
    report.write('\n')

    report.write('E10 a real model: output length versus request content\n\n')
    if provider is not None:
        summary = provider['summary']
        report.write('  model %s (revision %s), %d prompt pairs of equal token length,\n'
                     '  %d seeds each, sampling on\n'
                     % (provider['model'], provider['revision'][:12], summary['pairs'],
                        summary['seeds']))
        report.write('  pairs whose output lengths differed under a shared seed: %d of %d\n'
                     % (summary['pairs_differing'], summary['pairs']))
        report.write('  mean absolute output-length difference: %.1f tokens\n'
                     % summary['mean_abs_difference'])
        report.write('  identical request and seed gave identical output: %d of %d\n'
                     % (summary['determinism_identical'], summary['determinism_trials']))
    report.write('\n')

    report.write('E11 ported real-world workflows (bench/real/)\n\n')
    if real is None:
        report.write('  none ported\n\n')
    else:
        rows, entries = real
        report.write(table(rows, ['workflow', 'split', 'source', 'verdict', 'codes', 'escapes']))
        report.write('\n  %d workflows ported; %d candidates excluded (bench/real/EXCLUSIONS.md)\n\n'
                     % (len(rows), len(entries.get('excluded', []))))

    report.write('Analysis cost\n\n')
    report.write('  %d workflows certified in %.2f s (%.1f ms each, including process startup;\n'
                 '  this is not an isolated measurement of analyser time)\n'
                 % (len(timed), elapsed, 1000.0 * elapsed / len(timed)))

    if failures:
        report.write('\nFAILURES (%d)\n\n' % len(failures))
        for message in failures:
            report.write('  - %s\n' % message)

    text = report.getvalue()
    io.open(os.path.join(RESULTS, 'evaluation.txt'), 'w', encoding='utf-8', newline='\n').write(text)
    for name, rows in (('cost', cost_rows), ('cost_bytes', bytes_rows),
                       ('relational', relational_rows), ('leakage', leakage_rows),
                       ('security', security_rows), ('rebilling', rebill_rows or [])):
        io.open(os.path.join(RESULTS, name + '.json'), 'w', encoding='utf-8', newline='\n').write(
            json.dumps(rows, indent=2) + '\n')
    print()
    print(text)

    if failures:
        print('%d experiment assertion(s) failed' % len(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
