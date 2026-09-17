#!/usr/bin/env python3
"""Generate the OrchLang benchmark corpus.

Two suites are produced.

``cost/`` varies the control-flow shape of a workflow -- chain length, branch
nesting, retry bounds, and combinations of the three -- because the shape is
exactly what separates a structural cost bound from a flat sum over call sites.

``security/`` pairs each unsafe workflow with a safe counterpart that differs
only in the one edit that makes it safe (an added endorsement, a declassifica-
tion, a moved effect).  Pairing them this way means a detector cannot score well
by rejecting everything: the safe half measures false positives directly.

Every file is generated from a fixed template, so the corpus is reproducible and
carries no hand-tuned examples.
"""

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
COST = os.path.join(HERE, 'cost')
SECURITY = os.path.join(HERE, 'security')

PREAMBLE = '''  input source: text max_tokens {inbound};
  model small = mock("offline-small") max_tokens {small};
  model large = mock("offline-large") max_tokens {large};
  prompt step(payload: text) -> text = "Process this payload: {{payload}}";
'''


def preamble(inbound=120, small=150, large=600):
    return PREAMBLE.format(inbound=inbound, small=small, large=large)


def workflow(name, budget, body, extra_preamble=None):
    head = 'workflow %s budget %d {\n' % (name, budget)
    return head + (extra_preamble if extra_preamble is not None else preamble()) + body + '}\n'


def write(directory, name, text):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text)
    return path


# --------------------------------------------------------------- cost suite --

def gen_cost():
    files = []

    # Straight-line chains: the bound should track the number of calls.
    for length in range(1, 6):
        body = ''
        previous = 'source'
        for index in range(length):
            body += '  let r%d: text = call step(%s) using small;\n' % (index, previous)
            previous = 'r%d' % index
        body += '  output %s;\n' % previous
        files.append(('chain_%d.orch' % length,
                      workflow('Chain%d' % length, 100000, body)))

    # Single branches with arms of differing cost: a flat sum over syntactic
    # call sites counts both arms, which no execution ever pays for.
    for arms in range(1, 5):
        body = '  let head: text = call step(source) using small;\n'
        body += '  if tokens(head) <= 150 {\n'
        for index in range(arms):
            body += '    let a%d: text = call step(source) using small;\n' % index
        body += '  } else {\n'
        for index in range(arms):
            body += '    let b%d: text = call step(source) using large;\n' % index
        body += '  }\n  output head;\n'
        files.append(('branch_%d.orch' % arms,
                      workflow('Branch%d' % arms, 100000, body)))

    # Nested branches: four leaf paths, only one of which runs.
    body = '  let head: text = call step(source) using small;\n'
    body += '  if tokens(head) <= 150 {\n'
    body += '    let x: text = call step(source) using small;\n'
    body += '    if tokens(x) <= 150 {\n'
    body += '      let x1: text = call step(source) using small;\n'
    body += '    } else {\n'
    body += '      let x2: text = call step(source) using large;\n'
    body += '    }\n  } else {\n'
    body += '    let y: text = call step(source) using large;\n'
    body += '    if tokens(y) <= 150 {\n'
    body += '      let y1: text = call step(source) using large;\n'
    body += '    } else {\n'
    body += '      let y2: text = call step(source) using large;\n'
    body += '    }\n  }\n  output head;\n'
    files.append(('branch_nested.orch', workflow('BranchNested', 100000, body)))

    # Retries: the shape a flat sum gets wrong in the unsafe direction, since
    # it counts one attempt where the workflow permits several.
    for bound in range(2, 7):
        body = '  retry %d {\n    let attempt: text = call step(source) using small;\n  }\n' % bound
        body += '  output source;\n'
        files.append(('retry_%d.orch' % bound,
                      workflow('Retry%d' % bound, 100000, body)))

    # Nested retries multiply.
    for outer, inner in ((2, 2), (2, 3), (3, 3)):
        body = '  retry %d {\n    retry %d {\n' % (outer, inner)
        body += '      let attempt: text = call step(source) using small;\n'
        body += '    }\n  }\n  output source;\n'
        files.append(('retry_nested_%dx%d.orch' % (outer, inner),
                      workflow('RetryNested%dx%d' % (outer, inner), 100000, body)))

    # Retry inside a branch, and a branch inside a retry.
    body = '  let head: text = call step(source) using small;\n'
    body += '  if tokens(head) <= 150 {\n'
    body += '    retry 3 {\n      let a: text = call step(source) using small;\n    }\n'
    body += '  } else {\n    let b: text = call step(source) using large;\n  }\n'
    body += '  output head;\n'
    files.append(('retry_in_branch.orch', workflow('RetryInBranch', 100000, body)))

    body = '  let head: text = call step(source) using small;\n'
    body += '  retry 3 {\n'
    body += '    if tokens(head) <= 150 {\n'
    body += '      let a: text = call step(source) using small;\n'
    body += '    } else {\n'
    body += '      let b: text = call step(source) using large;\n'
    body += '    }\n  }\n  output head;\n'
    files.append(('branch_in_retry.orch', workflow('BranchInRetry', 100000, body)))

    # Long chains with wide inputs, where the input half of the bound dominates.
    for inbound in (200, 800, 2000):
        body = '  let a: text = call step(source) using small;\n'
        body += '  let b: text = call step(a) using small;\n'
        body += '  output b;\n'
        files.append(('wide_input_%d.orch' % inbound,
                      workflow('WideInput%d' % inbound, 100000, body,
                               preamble(inbound=inbound))))

    return files


# ----------------------------------------------------------- security suite --

def gen_security():
    files = []

    tool_preamble = '''  input source: text max_tokens 120;
  input page: text untrusted max_tokens 300;
  secret API_KEY: text max_tokens 16;
  secret ALERT: boolean max_tokens 1;
  model small = mock("offline-small") max_tokens 150;
  tool publish(body: text);
  prompt step(payload: text) -> text = "Process this payload: {payload}";
'''

    def sec(name, body, unsafe):
        directory = os.path.join(SECURITY, 'unsafe' if unsafe else 'safe')
        return (directory, name, workflow(name.replace('.orch', ''), 100000, body, tool_preamble))

    # 1. Indirect prompt injection: untrusted page -> model -> external effect.
    files.append(sec('InjectionToSink.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  emit publish(summary);\n  output summary;\n', True))
    files.append(sec('InjectionEndorsed.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  endorse(summary) as vetted: text because "schema validated offline";\n'
                     '  emit publish(vetted);\n  output summary;\n', False))

    # 2. Injection laundered through a second model call.
    files.append(sec('InjectionTransitive.orch',
                     '  let first: text = call step(page) using small;\n'
                     '  let second: text = call step(first) using small;\n'
                     '  emit publish(second);\n  output second;\n', True))
    files.append(sec('InjectionTransitiveEndorsed.orch',
                     '  let first: text = call step(page) using small;\n'
                     '  let second: text = call step(first) using small;\n'
                     '  endorse(second) as vetted: text because "schema validated offline";\n'
                     '  emit publish(vetted);\n  output second;\n', False))

    # 3. Injection reaching a sink from inside a branch.
    files.append(sec('InjectionInBranch.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  if tokens(summary) <= 150 {\n    emit publish(summary);\n  }\n'
                     '  output summary;\n', True))
    files.append(sec('InjectionInBranchEndorsed.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  endorse(summary) as vetted: text because "schema validated offline";\n'
                     '  if tokens(vetted) <= 150 {\n    emit publish(vetted);\n  }\n'
                     '  output summary;\n', False))

    # 4. Injection reaching a sink from inside a retry.
    files.append(sec('InjectionInRetry.orch',
                     '  retry 2 {\n    let summary: text = call step(page) using small;\n'
                     '    emit publish(summary);\n  }\n  output source;\n', True))
    files.append(sec('InjectionInRetryEndorsed.orch',
                     '  retry 2 {\n    let summary: text = call step(page) using small;\n'
                     '    endorse(summary) as vetted: text because "schema validated offline";\n'
                     '    emit publish(vetted);\n  }\n  output source;\n', False))

    # 5. Secret passed straight to a prompt.
    files.append(sec('SecretToPrompt.orch',
                     '  let r: text = call step(API_KEY) using small;\n  output r;\n', True))
    files.append(sec('SecretToPromptDeclassified.orch',
                     '  declassify(API_KEY) as fingerprint: text because "only a hash prefix";\n'
                     '  let r: text = call step(fingerprint) using small;\n  output r;\n', False))

    # 6. Secret returned as the workflow result.
    files.append(sec('SecretAsOutput.orch',
                     '  let r: text = call step(source) using small;\n  output API_KEY;\n', True))
    files.append(sec('SecretAsOutputDeclassified.orch',
                     '  declassify(API_KEY) as fingerprint: text because "only a hash prefix";\n'
                     '  let r: text = call step(source) using small;\n  output fingerprint;\n', False))

    # 7. Secret handed to an external tool.
    files.append(sec('SecretToSink.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  emit publish(API_KEY);\n  output r;\n', True))
    files.append(sec('SecretToSinkDeclassified.orch',
                     '  declassify(API_KEY) as fingerprint: text because "only a hash prefix";\n'
                     '  let r: text = call step(source) using small;\n'
                     '  emit publish(fingerprint);\n  output r;\n', False))

    # 8. Implicit flow: the secret decides whether the effect happens.
    files.append(sec('SecretGuardedEffect.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  if ALERT {\n    emit publish(r);\n  }\n  output r;\n', True))
    files.append(sec('UnguardedEffect.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  emit publish(r);\n  output r;\n', False))

    # 9. Implicit flow that a relabelling inside the branch tries to launder.
    files.append(sec('SecretGuardedLaundered.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  if ALERT {\n'
                     '    endorse(r) as ok: text because "checked";\n'
                     '    emit publish(ok);\n  }\n  output r;\n', True))
    files.append(sec('EffectOutsideSecretBranch.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  endorse(r) as ok: text because "checked";\n'
                     '  emit publish(ok);\n  output r;\n', False))

    # 10. Untrusted data deciding whether an effect happens.
    files.append(sec('UntrustedGuardedEffect.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  if tokens(summary) <= 150 {\n'
                     '    emit publish(source);\n  }\n  output summary;\n', True))
    files.append(sec('TrustedGuardedEffect.orch',
                     '  let r: text = call step(source) using small;\n'
                     '  if tokens(r) <= 150 {\n'
                     '    emit publish(source);\n  }\n  output r;\n', False))

    # 11. Untrusted input mixed with trusted input in one call.
    files.append(sec('MixedTrustToSink.orch',
                     '  let mixed: text = call step(page) using small;\n'
                     '  let joined: text = call step(mixed) using small;\n'
                     '  emit publish(joined);\n  output joined;\n', True))
    files.append(sec('TrustedOnlyToSink.orch',
                     '  let clean: text = call step(source) using small;\n'
                     '  emit publish(clean);\n  output clean;\n', False))

    # 12. Untrusted model output returned to the caller is fine; only sinks are
    # guarded.  This pair checks the analysis does not over-reject.
    files.append(sec('UntrustedToSinkNoEndorse.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  emit publish(summary);\n  output source;\n', True))
    files.append(sec('UntrustedToOutputOnly.orch',
                     '  let summary: text = call step(page) using small;\n'
                     '  output summary;\n', False))

    return files


def main():
    written = 0
    for name, text in gen_cost():
        write(COST, name, text)
        written += 1
    for directory, name, text in gen_security():
        write(directory, name, text)
        written += 1
    print('generated %d benchmark workflows' % written)


if __name__ == '__main__':
    main()
