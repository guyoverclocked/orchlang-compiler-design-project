#!/usr/bin/env python3
"""Verify every OrchLang case study and reproduce its evidence.

Each case study models a documented incident as a vulnerable workflow and a
fixed one.  This script checks, for every file:

  - the exit status of `orchc check`;
  - the exact set of diagnostic codes, so an unrelated error can never pass
    for the expected one;
  - for accepted files, the certified bound and every escape hatch recorded in
    the certificate.

Two case studies also run experiments on the offline mock runtime:

  06  cost      execute both workflows under 200 seeds and count how often the
                hand-added estimate and the declared budget are exceeded, and
                whether the certified bound ever is (checked componentwise);
  07  billing   hold the seed and the public inputs fixed, flip the secret, and
                count how often the bill changes.

Everything written to case_studies/results/ is deterministic: no timestamps, no
timings, no absolute paths.  Rerunning this script on any machine must
reproduce those files byte for byte, which is what `make verify` checks.

Exits nonzero if any expectation fails.  Standard library only.
"""

import hashlib
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.dont_write_bytecode = True  # keep the import from littering bench/ with __pycache__

import evaluate as harness  # noqa: E402  (reuses the benchmark's orchc driver)

RESULTS = os.environ.get('ORCHLANG_CASE_RESULTS', os.path.join(HERE, 'results'))

COST_SEEDS = 200
PAIRED_SEEDS = 25

# role: vulnerable (must be rejected), fixed (must be accepted), or limitation
# (accepted, and kept to show what the compiler cannot see).
CASES = [
    {
        'id': '01_github_mcp',
        'title': 'GitHub MCP toxic agent flow',
        'incident': 'Invariant Labs, 26 May 2025',
        'source': 'https://invariantlabs.ai/blog/mcp-github-vulnerability',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E233'}),
            ('fixed.orch', 'fixed', set()),
        ],
    },
    {
        'id': '02_supabase_mcp',
        'title': 'Supabase MCP support-ticket leak',
        'incident': 'General Analysis, 8 July 2025',
        'source': 'https://generalanalysis.com/blog/supabase-mcp-blog',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E233'}),
            ('fixed.orch', 'fixed', set()),
        ],
    },
    {
        'id': '03_echoleak',
        'title': 'EchoLeak zero-click exfiltration, CVE-2025-32711',
        'incident': 'Aim Security, June 2025; arXiv:2509.10540',
        'source': 'https://arxiv.org/abs/2509.10540',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E233'}),
            ('fixed.orch', 'fixed', set()),
            ('limitation_rendering_undeclared.orch', 'limitation', set()),
        ],
    },
    {
        'id': '04_langchain_exec',
        'title': 'LangChain LLMMathChain code execution, CVE-2023-29374',
        'incident': 'GHSA-fprp-p869-w6q2, April 2023',
        'source': 'https://osv.dev/vulnerability/GHSA-fprp-p869-w6q2',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E233'}),
            ('fixed.orch', 'fixed', set()),
            ('limitation_trusted_input.orch', 'limitation', set()),
        ],
    },
    {
        'id': '05_credentials_in_prompt',
        'title': 'Credential in the system prompt',
        'incident': 'OWASP LLM07:2025 example scenario',
        'source': 'https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E230', 'E231'}),
            ('fixed.orch', 'fixed', set()),
        ],
    },
    {
        'id': '06_retry_overrun',
        'title': 'Retry loop budget overrun',
        'incident': 'Token Budgets catalogue, arXiv:2606.04056 (retry-loop cluster)',
        'source': 'https://arxiv.org/abs/2606.04056',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E260'}),
            ('fixed.orch', 'fixed', set()),
        ],
    },
    {
        'id': '07_billing_side_channel',
        'title': 'Bill reveals a confidential flag (constructed scenario)',
        'incident': 'Grounded in USENIX Security 2024, arXiv:2412.15431, arXiv:2511.03675',
        'source': 'https://arxiv.org/abs/2511.03675',
        'files': [
            ('vulnerable.orch', 'vulnerable', {'E236'}),
            ('fixed.orch', 'fixed', set()),
        ],
    },
]

failures = []
report = io.StringIO()


def say(line=''):
    print(line)
    report.write(line + '\n')


def fail(message):
    failures.append(message)
    say('    FAIL: ' + message)


def relative(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')


def sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def lifted_budget_copy(path):
    """A copy with the budget raised, so a workflow rejected only for E260 can
    still be analysed.  The budget changes the final comparison, not any bound."""
    source = io.open(path, encoding='utf-8').read()
    handle = tempfile.NamedTemporaryFile('w', suffix='.orch', delete=False, encoding='utf-8')
    handle.write(re.sub(r'budget \d+', 'budget 1000000000', source, count=1))
    handle.close()
    return handle.name


# ---------------------------------------------------------------- verdicts --

def check_file(case, name, role, expected_codes):
    path = os.path.join(HERE, case['id'], name)
    code, out, err = harness.run(['check', relative(path)])
    codes = harness.diagnostic_codes(err)
    entry = {'file': relative(path), 'role': role, 'sha256': sha256(path),
             'exit': code, 'codes': sorted(codes)}

    transcript = '$ orchc check %s\n%s%s[exit %d]\n' % (relative(path), out, err, code)

    if role == 'vulnerable':
        ok = code == 1 and codes == expected_codes
        if not ok:
            fail('%s: expected rejection with exactly %s, got exit %d with %s'
                 % (relative(path), sorted(expected_codes), code, sorted(codes)))
        entry['diagnostics'] = [line for line in err.splitlines() if 'error [' in line]
    else:
        ok = code == 0 and not codes
        if not ok:
            fail('%s: expected acceptance, got exit %d with %s' % (relative(path), code, sorted(codes)))
        cert = harness.certificate(relative(path))
        if cert is None:
            fail('%s: accepted but no certificate' % relative(path))
        else:
            entry['certified_tokens'] = cert['bound']['total_tokens']
            entry['budget_tokens'] = cert['budget_tokens']
            entry['escape_hatches'] = [
                {'operation': item['operation'], 'source': item['source'],
                 'justification': item['justification']}
                for item in cert['reclassifications']]
            ccode, cout, cerr = harness.run(['certify', relative(path)])
            transcript += '\n$ orchc certify %s\n%s' % (relative(path), cout)

    write(os.path.join(RESULTS, case['id'], name.replace('.orch', '.txt')), transcript)

    verdict = 'rejected' if code == 1 else 'accepted' if code == 0 else 'exit %d' % code
    detail = ' '.join(sorted(codes)) if codes else 'bound %s' % entry.get('certified_tokens', '?')
    say('    %-4s %-10s %-40s %-8s %s' % ('ok' if ok else 'FAIL', role, name, verdict, detail))
    return entry


# ------------------------------------------------------------- experiments --

def cost_experiment(case):
    vulnerable = os.path.join(HERE, case['id'], 'vulnerable.orch')
    fixed = os.path.join(HERE, case['id'], 'fixed.orch')

    lifted = lifted_budget_copy(vulnerable)
    try:
        flat = harness.flat_baseline(lifted)
        vulnerable_cert = harness.certificate(lifted)['bound']
    finally:
        os.unlink(lifted)
    fixed_cert = harness.certificate(relative(fixed))['bound']
    budget = int(re.search(r'budget (\d+)', io.open(vulnerable, encoding='utf-8').read()).group(1))

    result = {'seeds': COST_SEEDS, 'hand_added_estimate': flat, 'budget': budget}
    for label, path, cert in (('vulnerable', vulnerable, vulnerable_cert),
                              ('fixed', fixed, fixed_cert)):
        runs = [harness.execute(relative(path), seed) for seed in range(1, COST_SEEDS + 1)]
        if any(run is None for run in runs):
            fail('%s: a mock execution failed' % relative(path))
            return result
        totals = [run['total'] for run in runs]
        over_certified = sum(1 for run in runs if run['total'] > cert['total_tokens']
                             or run['output'] > cert['guaranteed_tokens']
                             or run['input'] > cert['estimated_tokens'])
        result[label] = {
            'certified_tokens': cert['total_tokens'],
            'max_observed': max(totals),
            'median_observed': sorted(totals)[len(totals) // 2],
            'runs_over_hand_added_estimate': sum(1 for t in totals if t > flat),
            'runs_over_budget': sum(1 for t in totals if t > budget),
            'runs_over_certified_bound': over_certified,
        }
        if over_certified:
            fail('%s: the certified bound was exceeded in %d runs' % (relative(path), over_certified))

    v, f = result['vulnerable'], result['fixed']
    if v['runs_over_budget'] == 0:
        fail('06: no execution of the vulnerable workflow overran its budget; the case no longer shows the incident')
    if f['runs_over_budget'] != 0:
        fail('06: the fixed workflow overran its budget')

    say('    cost experiment, %d seeds each; hand-added estimate %d tokens, budget %d'
        % (COST_SEEDS, flat, budget))
    for label in ('vulnerable', 'fixed'):
        r = result[label]
        say('      %-10s certified %6d  max %6d  median %6d  over estimate %3d  over budget %3d  over certified %d'
            % (label, r['certified_tokens'], r['max_observed'], r['median_observed'],
               r['runs_over_hand_added_estimate'], r['runs_over_budget'],
               r['runs_over_certified_bound']))
    return result


def billing_experiment(case):
    public_pins = {'question': 120, 'handbook': 1500}
    secret = 'on_improvement_plan'
    result = {'seeds': PAIRED_SEEDS, 'public_pins': public_pins, 'secret': secret}
    for label in ('vulnerable', 'fixed'):
        path = relative(os.path.join(HERE, case['id'], label + '.orch'))
        differing, witness = 0, None
        for seed in range(1, PAIRED_SEEDS + 1):
            bills = {}
            for value in ('false', 'true'):
                pins = dict(public_pins)
                pins[secret] = value
                run = harness.execute(path, seed, pins)
                if run is None:
                    fail('%s: a paired execution failed' % path)
                    return result
                bills[value] = run['billing']
            if bills['false'] != bills['true']:
                differing += 1
                if witness is None:
                    witness = {'seed': seed,
                               'secret_false': {k: list(v) for k, v in bills['false'].items()},
                               'secret_true': {k: list(v) for k, v in bills['true'].items()}}
        result[label] = {'pairs': PAIRED_SEEDS, 'pairs_with_different_bill': differing,
                         'witness': witness}

    if result['vulnerable']['pairs_with_different_bill'] == 0:
        fail('07: the vulnerable workflow never billed differently; the leak was not reproduced')
    if result['fixed']['pairs_with_different_bill'] != 0:
        fail('07: the fixed workflow billed differently for different secrets')

    say('    paired billing experiment, %d seeds, public inputs pinned, secret flipped'
        % PAIRED_SEEDS)
    for label in ('vulnerable', 'fixed'):
        r = result[label]
        say('      %-10s bill changed with the secret in %d of %d pairs'
            % (label, r['pairs_with_different_bill'], r['pairs']))
    w = result['vulnerable']['witness']
    if w:
        def fmt(bill):
            return ', '.join('%s: %d call, %d in, %d out' % (m, c[0], c[1], c[2])
                             for m, c in sorted(bill.items()))
        say('      witness, seed %d: secret false bills {%s}; secret true bills {%s}'
            % (w['seed'], fmt(w['secret_false']), fmt(w['secret_true'])))
    return result


# -------------------------------------------------------------------- main --

def main():
    if not os.path.exists(harness.ORCHC):
        print('build orchc first: make', file=sys.stderr)
        return 2

    os.chdir(ROOT)
    summary = {'format': 'orchlang-case-study-results', 'version': 1, 'cases': []}

    say('OrchLang case studies')
    say('=====================')
    for case in CASES:
        say('')
        say('%s  %s' % (case['id'], case['title']))
        say('    incident: %s' % case['incident'])
        say('    source:   %s' % case['source'])
        entry = {'id': case['id'], 'title': case['title'], 'incident': case['incident'],
                 'source': case['source'], 'files': []}
        for name, role, codes in case['files']:
            entry['files'].append(check_file(case, name, role, codes))
        if case['id'] == '06_retry_overrun':
            entry['experiment'] = cost_experiment(case)
        if case['id'] == '07_billing_side_channel':
            entry['experiment'] = billing_experiment(case)
        summary['cases'].append(entry)

    files = [f for case in summary['cases'] for f in case['files']]
    vulnerable = [f for f in files if f['role'] == 'vulnerable']
    fixed = [f for f in files if f['role'] == 'fixed']
    say('')
    say('Summary')
    say('    vulnerable workflows rejected with the expected codes: %d of %d'
        % (sum(1 for f in vulnerable if f['exit'] == 1), len(vulnerable)))
    say('    fixed workflows accepted with a certificate:           %d of %d'
        % (sum(1 for f in fixed if f['exit'] == 0), len(fixed)))
    say('    limitation files accepted, as documented:              %d of %d'
        % (sum(1 for f in files if f['role'] == 'limitation' and f['exit'] == 0),
           sum(1 for f in files if f['role'] == 'limitation')))
    say('    expectation failures:                                  %d' % len(failures))

    summary['failures'] = failures
    write(os.path.join(RESULTS, 'results.json'), json.dumps(summary, indent=2, sort_keys=True) + '\n')
    write(os.path.join(RESULTS, 'results.txt'), report.getvalue())
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
