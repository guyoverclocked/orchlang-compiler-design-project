#!/usr/bin/env python3
"""Bind a compiler report to source, and independently recompute its token bound.

This is a second implementation of the *cost* semantics, not a verified type
checker or a proof of information-flow/relational safety. It never imports the
compiler or trusts its call-site extraction. It parses the submitted source,
resolves lexical model/prompt/value bindings and recomputes all three bounds.
The envelope records source and compiler SHA-256 digests for reproducibility.
"""

import argparse
import copy
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
SATURATION = 2**64 - 1  # This release is evaluated on a 64-bit size_t target.
TOKEN = re.compile(r'\s+|//[^\n]*|"(?:[^"\\\n]|\\[nt"\\])*"|'
                   r'\d+(?:\.\d+)?|[A-Za-z_][A-Za-z_0-9]*|'
                   r'->|<=|>=|==|!=|[{}():;,=<>]')


@dataclass(frozen=True)
class Bound:
    output: int = 0
    input: int = 0
    total: int = 0

    def add(self, other):
        return Bound(self.output + other.output, self.input + other.input,
                     self.total + other.total)

    def choice(self, other):
        return Bound(max(self.output, other.output), max(self.input, other.input),
                     max(self.total, other.total))

    def repeat(self, count):
        return Bound(self.output * count, self.input * count, self.total * count)

    def as_dict(self):
        return {'guaranteed_tokens': self.output, 'estimated_tokens': self.input,
                'total_tokens': self.total, 'component_sum_tokens': self.output + self.input}


class SourceCost:
    """Small independent parser for the released finite OrchLang grammar."""

    def __init__(self, text, divisor):
        if not isinstance(divisor, int) or divisor < 1:
            raise ValueError('chars_per_token must be a positive integer')
        self.divisor, self.items, self.cursor, self.calls = divisor, [], 0, []
        self.derivations = {}
        position = 0
        while position < len(text):
            match = TOKEN.match(text, position)
            if not match:
                raise ValueError('unrecognized source token at byte/character offset %d' % position)
            word = match.group()
            if not word.isspace() and not word.startswith('//'):
                line = text.count('\n', 0, position) + 1
                line_start = text.rfind('\n', 0, position) + 1
                column = len(text[line_start:position].encode('utf-8')) + 1
                self.items.append((word, line, column))
            position = match.end()

    def peek(self):
        return self.items[self.cursor][0] if self.cursor < len(self.items) else '<EOF>'

    def take(self, expected=None):
        if self.cursor >= len(self.items):
            raise ValueError('unexpected end of source')
        token = self.items[self.cursor]
        if expected is not None and token[0] != expected:
            raise ValueError('expected %r, found %r at %d:%d' %
                             (expected, token[0], token[1], token[2]))
        self.cursor += 1
        return token

    def integer(self):
        value = self.take()[0]
        if not value.isdecimal():
            raise ValueError('expected nonnegative integer, found %r' % value)
        return int(value)

    @staticmethod
    def string(value):
        if not value.startswith('"'):
            raise ValueError('expected string, found %r' % value)
        return json.loads(value, strict=False)  # DSL strings allow literal control bytes

    def estimate(self, text):
        return (len(text.encode('utf-8')) + self.divisor - 1) // self.divisor

    def args(self):
        self.take('(')
        values = []
        if self.peek() != ')':
            values.append(self.take()[0])
            while self.peek() == ',':
                self.take(',')
                values.append(self.take()[0])
        self.take(')')
        return values

    def parameter_list(self):
        self.take('(')
        if self.peek() != ')':
            self.take(); self.take(':'); self.take()
            while self.peek() == ',':
                self.take(','); self.take(); self.take(':'); self.take()
        self.take(')')

    def condition(self):
        if self.peek() == 'tokens':
            self.take('tokens'); self.args(); self.take(); self.integer()
        else:
            self.take()

    def record(self, workflow, depth, rule, line, bound):
        self.derivations.setdefault(workflow, []).append(
            {'depth': depth, 'rule': rule, 'line': line, **bound.as_dict()})

    def block(self, environment, workflow, depth=0):
        self.take('{')
        environment = copy.deepcopy(environment)
        result = Bound()
        while self.peek() != '}':
            kind, line, column = self.take()
            contribution = Bound()
            if kind in ('input', 'secret'):
                name = self.take()[0]
                declared_type = 'text'
                if self.peek() == ':':
                    self.take(':'); declared_type = self.take()[0]
                if self.peek() == 'untrusted': self.take('untrusted')
                cap = None
                if self.peek() == 'max_tokens':
                    self.take('max_tokens'); cap = self.integer()
                self.take(';')
                environment[name] = ('value', cap)
            elif kind == 'model':
                name = self.take()[0]
                self.take('='); provider = self.take()[0]
                self.take('('); actual_id = self.string(self.take()[0]); self.take(')')
                self.take('max_tokens'); cap = self.integer()
                price = None
                if self.peek() == 'cost_per_token':
                    self.take('cost_per_token'); price = self.take()[0]
                self.take(';')
                environment[name] = ('model', cap, provider, actual_id, price)
            elif kind == 'prompt':
                name = self.take()[0]
                self.parameter_list(); self.take('->'); self.take(); self.take('=')
                text = self.string(self.take()[0]); self.take(';')
                environment[name] = ('prompt', self.estimate(text), text)
            elif kind == 'tool':
                self.take(); self.parameter_list(); self.take(';')
            elif kind == 'let':
                name = self.take()[0]
                self.take(':'); self.take(); self.take('=')
                _, call_line, call_column = self.take('call')
                prompt = self.take()[0]; arguments = self.args()
                self.take('using'); model = self.take()[0]; self.take(';')
                prompt_fact, model_fact = environment[prompt], environment[model]
                if prompt_fact[0] != 'prompt' or model_fact[0] != 'model':
                    raise ValueError('call target has wrong kind')
                argument_bounds, argument_atoms = [], []
                for argument in arguments:
                    if argument.startswith('"'):
                        literal = self.string(argument)
                        cap = self.estimate(literal)
                        expr_kind = 'text'
                        atom = {'kind': 'literal', 'literal_text': literal,
                                'literal_expr_kind': expr_kind}
                    elif argument in ('true', 'false'):
                        cap = self.estimate(argument)
                        atom = {'kind': 'literal', 'literal_text': argument,
                                'literal_expr_kind': 'boolean'}
                    elif re.fullmatch(r'\d+\.\d+', argument):
                        cap = self.estimate(argument)
                        atom = {'kind': 'literal', 'literal_text': argument,
                                'literal_expr_kind': 'decimal'}
                    elif re.fullmatch(r'\d+', argument):
                        cap = self.estimate(argument)
                        atom = {'kind': 'literal', 'literal_text': argument,
                                'literal_expr_kind': 'integer'}
                    else:
                        fact = environment[argument]
                        if fact[0] != 'value': raise ValueError('non-value argument')
                        cap = fact[1]
                        atom = {'kind': 'value', 'name': argument,
                                'literal_expr_kind': None}
                    if cap is None: raise ValueError('unknown argument bound')
                    argument_bounds.append(cap)
                    argument_atoms.append({**atom, 'token_bound': cap, 'position': len(argument_atoms)})
                output = model_fact[1]
                input_bound = prompt_fact[1] + sum(argument_bounds)
                contribution = Bound(output, input_bound, output + input_bound)
                self.calls.append({'workflow': workflow, 'line': line, 'column': column,
                                   'call_line': call_line, 'call_column': call_column,
                                   'provider': model_fact[2], 'model_id': model_fact[3],
                                   'model_max_tokens': output, 'prompt_template': prompt_fact[2],
                                   'template_tokens': prompt_fact[1],
                                   'argument_bounds': argument_bounds, 'arguments': argument_atoms,
                                   'result': name, 'prompt': prompt, 'model_alias': model,
                                   'has_unit_price': model_fact[4] is not None,
                                   'unit_price': float(model_fact[4]) if model_fact[4] is not None else 0.0})
                self.record(workflow, depth, 'call', line, contribution)
                environment[name] = ('value', output)
            elif kind == 'if':
                self.condition()
                self.record(workflow, depth, 'branch', line, Bound())
                first = self.block(environment, workflow, depth + 1)
                second = Bound()
                if self.peek() == 'else':
                    self.take('else'); second = self.block(environment, workflow, depth + 1)
                contribution = first.choice(second)
                self.record(workflow, depth, 'branch-max', line, contribution)
            elif kind == 'retry':
                count = self.integer()
                self.record(workflow, depth, 'retry', line, Bound())
                contribution = self.block(environment, workflow, depth + 1).repeat(count)
                self.record(workflow, depth, 'retry-scale', line, contribution)
            elif kind in ('declassify', 'endorse'):
                arguments = self.args(); self.take('as'); name = self.take()[0]
                self.take(':'); self.take(); self.take('because'); self.string(self.take()[0])
                self.take(';'); environment[name] = environment[arguments[0]]
            elif kind == 'require':
                self.take('tokens'); self.args(); self.take(); self.integer(); self.take(';')
            elif kind == 'emit':
                self.take(); self.args(); self.take(';')
            elif kind == 'output':
                self.take(); self.take(';')
            else:
                raise ValueError('unsupported statement %r at %d:%d' % (kind, line, column))
            result = result.add(contribution)
        self.take('}')
        return result

    def program(self):
        workflows = []
        while self.peek() != '<EOF>':
            self.take('workflow'); name = self.take()[0]
            self.take('budget'); budget = self.integer()
            bound = self.block({}, name)
            if bound.total >= SATURATION or bound.output >= SATURATION or bound.input >= SATURATION:
                raise ValueError('source bound saturates the 64-bit compiler target')
            workflows.append({'name': name, 'budget_tokens': budget, 'bound': bound.as_dict()})
        if not workflows: raise ValueError('empty program')
        return workflows


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(source, certificate):
    if certificate.get('format') != 'orchlang-safety-certificate':
        raise ValueError('unknown certificate format')
    if certificate.get('version', 1) >= 2 and digest(source) != certificate.get('source_sha256'):
        raise ValueError('compiler certificate source SHA-256 does not match')
    parser = SourceCost(source.decode('utf-8'), certificate['assumptions']['chars_per_token'])
    recomputed = parser.program()
    issued = certificate['workflows']
    if len(issued) != len(recomputed): raise ValueError('workflow count differs from source')
    for independent, compiler in zip(recomputed, issued):
        for key in ('name', 'budget_tokens'):
            if independent[key] != compiler[key]: raise ValueError('%s differs from source' % key)
        for key, value in independent['bound'].items():
            if compiler['bound'].get(key) != value:
                raise ValueError('%s: %s mismatch (independent %d, compiler %s)' %
                                 (independent['name'], key, value, compiler['bound'].get(key)))
        if independent['bound']['total_tokens'] > independent['budget_tokens']:
            raise ValueError('report admits a source above its budget')
        if compiler['bound'].get('defined') is not True or compiler['bound'].get('within_budget') is not True:
            raise ValueError('report does not assert a defined budget bound')
        if certificate.get('version', 1) >= 2:
            calls = [c for c in parser.calls if c['workflow'] == independent['name']]
            facts = compiler['call_facts']
            if len(calls) != len(facts): raise ValueError('call-fact count differs from source')
            for call, fact in zip(calls, facts):
                if (fact['location']['line'], fact['location']['column']) != (call['call_line'], call['call_column']):
                    raise ValueError('call-fact source location differs')
                for key in ('result', 'prompt', 'model_alias', 'template_tokens'):
                    if fact[key] != call[key]: raise ValueError('call-fact %s differs from source' % key)
                if fact['template_text'] != call['prompt_template']:
                    raise ValueError('call-fact exact template differs from source')
                contract = fact['model_contract']
                for issued_key, independent_key in (('provider', 'provider'), ('model', 'model_id'),
                    ('max_tokens', 'model_max_tokens'), ('has_unit_price', 'has_unit_price')):
                    if contract[issued_key] != call[independent_key]:
                        raise ValueError('resolved model %s differs from source' % issued_key)
                # max_digits10 JSON preserves the compiler's binary64 price.
                # Monetary rounding/soundness remains outside the token proof.
                if contract['unit_price'] != call['unit_price']:
                    raise ValueError('model presentation price differs from source')
                if len(fact['arguments']) != len(call['arguments']):
                    raise ValueError('call-fact argument count differs')
                for argument, issued_argument in zip(call['arguments'], fact['arguments']):
                    for key, value in argument.items():
                        if issued_argument[key] != value:
                            raise ValueError('ordered call argument %s differs from source' % key)
            expected = parser.derivations.get(independent['name'], [])
            issued_derivation = compiler['derivation']
            if len(expected) != len(issued_derivation): raise ValueError('derivation step count differs')
            for computed, step in zip(expected, issued_derivation):
                for key in ('depth', 'rule', 'line', 'guaranteed_tokens', 'estimated_tokens', 'total_tokens'):
                    if computed[key] != step[key]: raise ValueError('derivation %s differs from source' % key)
    return {'verified': 'source binding, resolved request cost facts and every token-cost derivation step',
            'workflows': len(recomputed), 'calls': len(parser.calls),
            'not_verified': ['type correctness', 'security labels', 'relational obligations',
                             'declassification/endorsement justifications', 'provider/tokenizer contracts']}


def bind(source_path, compiler):
    source = source_path.read_bytes()
    result = subprocess.run([str(compiler), 'certify', str(source_path)],
                            capture_output=True, text=True)
    if result.returncode: raise ValueError('certify failed: ' + result.stderr.strip())
    certificate = json.loads(result.stdout)
    return {'format': 'orchlang-source-bound-report', 'version': 1,
            'source_sha256': digest(source), 'compiler_sha256': digest(compiler.read_bytes()),
            'source_name': source_path.name, 'certificate': certificate,
            'independent_cost_audit': audit(source, certificate)}


def verify(source_path, envelope):
    if envelope.get('format') != 'orchlang-source-bound-report' or envelope.get('version') != 1:
        raise ValueError('unknown report envelope')
    source = source_path.read_bytes()
    if digest(source) != envelope.get('source_sha256'):
        raise ValueError('source SHA-256 does not match the bound report')
    return audit(source, envelope['certificate'])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['bind', 'verify'])
    cli.add_argument('source', type=pathlib.Path)
    cli.add_argument('report', type=pathlib.Path)
    cli.add_argument('--compiler', type=pathlib.Path, default=ROOT / 'orchc')
    args = cli.parse_args()
    try:
        if args.mode == 'bind':
            envelope = bind(args.source.resolve(), args.compiler.resolve())
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(envelope, indent=2) + '\n')
            result = envelope['independent_cost_audit']
        else:
            result = verify(args.source, json.loads(args.report.read_text()))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, IndexError, OSError, json.JSONDecodeError) as error:
        print('report audit failed: %s' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
