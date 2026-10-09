#!/usr/bin/env python3
"""Evaluate the explicitly partial sourced patterns and freeze their evidence.

No upstream application or live LLM is executed. See sourced/manifest.json.
"""

import argparse
import hashlib
import importlib.util
import json
import pathlib
import platform
import subprocess
import sys

import evaluate as harness

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'bench/sourced/manifest.json'
RESULTS = ROOT / 'bench/results'
spec = importlib.util.spec_from_file_location('certificate_audit', ROOT / 'audit/certificate_audit.py')
auditor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = auditor
spec.loader.exec_module(auditor)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(query_length=37, use_tool=False, secret=False):
    return {'query': query_length, 'query2': 61, 'history': 400,
            'page': 200, 'page2': 250, 'observation': 90,
            'use_tool': 'true' if use_tool else 'false',
            'route': 'true' if secret else 'false'}


def baseline_verdict(binary, path):
    if binary is None: return None
    result = subprocess.run([str(binary), 'check', str(path)], capture_output=True, text=True)
    return {'accepted': result.returncode == 0,
            'diagnostics': sorted(harness.diagnostic_codes(result.stderr))}


def evaluate(baseline=None, request_sensitive=False):
    manifest = json.loads(MANIFEST.read_text())
    failures, rows = [], []
    totals = {'base_executions': 0, 'bound_violations': 0, 'source_reports_checked': 0,
              'balanced_comparisons': 0, 'balanced_mismatches': 0,
              'unbalanced_comparisons': 0, 'unbalanced_mismatches': 0,
              'balanced_accepted': 0, 'baseline_balanced_accepted': 0,
              'newly_accepted': 0, 'mutations_rejected': 0}
    if len(manifest['patterns']) != 15:
        failures.append('expected the pinned 15-pattern manifest')
    for pattern in manifest['patterns']:
        row = {'id': pattern['id'], 'framework': pattern['framework'], 'source_url': pattern['source_url']}
        for variant, artifact in pattern['variants'].items():
            path = ROOT / artifact['path']
            if sha(path) != artifact['sha256']:
                failures.append('%s/%s: manifest digest mismatch' % (pattern['id'], variant))
                continue
            status, out, err = harness.run(['check', str(path)])
            codes = harness.diagnostic_codes(err)
            expect_accept = variant != 'unbalanced'
            if (status == 0) != expect_accept:
                failures.append('%s/%s: unexpected compiler verdict (%s)' % (pattern['id'], variant, err.strip()))
                continue
            if not expect_accept and 'E236' not in codes:
                failures.append('%s: mutation rejected without E236' % pattern['id'])
                continue
            row[variant] = {'accepted': status == 0, 'diagnostics': sorted(codes),
                            'baseline': baseline_verdict(baseline, path)}
            if expect_accept:
                try:
                    envelope = auditor.bind(path, ROOT / 'orchc')
                    destination = RESULTS / 'source_bound_reports' / variant / (path.stem + '.json')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(json.dumps(envelope, indent=2) + '\n')
                    auditor.verify(path, envelope)
                    totals['source_reports_checked'] += 1
                except (ValueError, KeyError, IndexError) as error:
                    failures.append('%s/%s: independent cost audit: %s' % (pattern['id'], variant, error))
                    continue
                row[variant]['bound'] = envelope['certificate']['workflows'][0]['bound']
            if variant == 'base':
                bound = row[variant]['bound']
                branch_arms = {}
                for seed in range(1, 101):
                    observation = harness.execute(str(path), seed, pins((0, 37, 160)[seed % 3], seed % 2 == 0),
                                                  request_sensitive=request_sensitive)
                    if observation is None:
                        failures.append('%s: base execution failed seed %d' % (pattern['id'], seed))
                        continue
                    totals['base_executions'] += 1
                    violated = observation['output'] > bound['guaranteed_tokens'] or \
                        observation['input'] > bound['estimated_tokens'] or observation['total'] > bound['total_tokens']
                    totals['bound_violations'] += int(violated)
                    for decision in observation['branches']:
                        branch_arms.setdefault('%s:%s' % (decision['line'], decision['column']), set()).add(
                            decision['decision'])
                row[variant]['branch_coverage'] = {k: sorted(v) for k, v in branch_arms.items()}
            else:
                compared = mismatched = 0
                first_witness = None
                for seed in range(1, 26):
                    for size in (0, 37, 160):
                        for public_flag in (False, True):
                            pair = [harness.execute(str(path), seed, pins(size, public_flag, secret),
                                                    audit_unsafe=not expect_accept,
                                                    request_sensitive=request_sensitive)
                                    for secret in (False, True)]
                            if any(x is None for x in pair):
                                failures.append('%s/%s: paired run failed' % (pattern['id'], variant))
                                continue
                            compared += 1
                            different = harness.billing_key(pair[0]) != harness.billing_key(pair[1])
                            mismatched += int(different)
                            if different and first_witness is None:
                                first_witness = {'seed': seed, 'query_tokens': size, 'use_tool': public_flag,
                                                 'false_billing': pair[0]['billing'], 'true_billing': pair[1]['billing']}
                row[variant].update({'comparisons': compared, 'mismatches': mismatched,
                                     'first_witness': first_witness,
                                     'secret_entropy_bits': 1.0,
                                     'mean_conditional_leak_bits': round(mismatched / compared, 6) if compared else None})
                # A uniform Boolean secret, fixed public inputs and fixed oracle:
                # deterministic equal observations leak 0 bits, distinct ones 1.
                totals[variant + '_comparisons'] += compared
                totals[variant + '_mismatches'] += mismatched
                if variant == 'balanced':
                    totals['balanced_accepted'] += 1
                    if baseline is not None:
                        old = row[variant]['baseline']['accepted']
                        totals['baseline_balanced_accepted'] += int(old)
                        totals['newly_accepted'] += int(not old)
                    if mismatched: failures.append('%s: accepted balanced case changed billing' % pattern['id'])
                else:
                    totals['mutations_rejected'] += 1
                    if not mismatched: failures.append('%s: expected unequal-arm witness absent' % pattern['id'])
        rows.append(row)
    if totals['bound_violations']: failures.append('a componentwise bound was exceeded')
    if totals['base_executions'] != 1500: failures.append('base execution grid incomplete')
    if totals['balanced_comparisons'] != 2250 or totals['unbalanced_comparisons'] != 2250:
        failures.append('paired comparison grid incomplete')
    if totals['source_reports_checked'] != 30: failures.append('source report audit grid incomplete')
    document = {'experiment': '15 source-derived partial bounded patterns, three authored variants each',
                'oracle_mode': 'request-sensitive' if request_sensitive else 'ordinal',
                'limits': manifest['scope'], 'selection': manifest['selection'],
                'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                                'compiler_sha256': sha(ROOT / 'orchc'),
                                'manifest_sha256': sha(MANIFEST),
                                'baseline_commit': 'a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9' if baseline else None},
                'leak_metric': 'Conditional mutual information for a uniform Boolean secret in '
                               'each fixed public-input/shared-oracle slice, averaged over the '
                               'declared grid; offline mock only, not deployed attack capacity',
                'totals': totals, 'patterns': rows, 'failures': failures}
    RESULTS.mkdir(exist_ok=True)
    output_name = 'sourced_request_sensitive.json' if request_sensitive else 'sourced.json'
    (RESULTS / output_name).write_text(json.dumps(document, indent=2) + '\n')
    print(json.dumps({'totals': totals, 'failures': failures}, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--baseline', type=pathlib.Path, help='orchc built from a49fcdb')
    cli.add_argument('--request-sensitive-oracle', action='store_true')
    options = cli.parse_args()
    sys.exit(evaluate(options.baseline, options.request_sensitive_oracle))
