"""Deterministic finite-table replay backend with explicit choice tapes.

This backend executes text requests and bills failed attempts. It is separate
from the enumerating reference interpreter. It does not contact or simulate the
latency, quality, hidden tokens, or accounting of a model provider.
"""
from fractions import Fraction
from .finite_reference import canonical, Unsupported


class NeedChoice(Exception):
    def __init__(self, count):
        self.count = count


class Replay:
    def __init__(self, contracts, kernels):
        self.contracts, self.kernels = contracts, kernels
        for c in contracts.values():
            canonical(c)
            if c['sampling'] != 'explicit-table' or c['error_policy'] != 'status-in-outcome':
                raise Unsupported('unsupported replay contract')
            self.count('', c['tokenizer'])

    @staticmethod
    def count(text, tokenizer):
        if tokenizer == 'utf8-bytes-v1':
            return len(text.encode('utf-8'))
        if tokenizer == 'unicode-codepoints-v1':
            return len(text)
        raise Unsupported('unknown replay tokenizer')

    def text(self, term):
        if isinstance(term, str):
            return term
        if isinstance(term, dict) and set(term) == {'var'}:
            result = self.env[term['var']]
            if not isinstance(result, str):
                raise ValueError('request variable must be text')
            return result
        if isinstance(term, dict) and set(term) == {'concat'}:
            return ''.join(self.text(t) for t in term['concat'])
        raise Unsupported('unsupported replay expression')

    def block(self, nodes, depth=0):
        if depth > 64:
            raise Unsupported('replay nesting limit')
        for node in nodes:
            kind = node['kind']
            if kind == 'call':
                contract = self.contracts[node['model']]
                key = canonical(contract)
                request = self.text(node['request'])
                table = self.kernels[key]
                outcomes = table.get(request, table.get('*'))
                if outcomes is None:
                    raise Unsupported('replay table has no matching request')
                weights = [Fraction(o['p']) for o in outcomes]
                if any(p < 0 for p in weights) or sum(weights) != 1:
                    raise ValueError('invalid replay probability table')
                # Validate all alternatives, including alternatives not selected.
                for o in outcomes:
                    if o['status'] not in {'ok', 'error'}:
                        raise ValueError('invalid replay status')
                    if self.count(o['text'], contract['tokenizer']) > contract['cap']:
                        raise ValueError('replay response exceeds output cap')
                if self.position == len(self.tape):
                    raise NeedChoice(len(outcomes))
                index = self.tape[self.position]
                self.position += 1
                if type(index) is not int or not 0 <= index < len(outcomes):
                    raise ValueError('invalid choice index')
                o = outcomes[index]
                self.weight *= weights[index]
                self.env[node['bind']] = o['text']
                self.trace.append((key, contract['tokenizer'], self.count(request, contract['tokenizer']),
                                   self.count(o['text'], contract['tokenizer']), o['status']))
                self.requests.append(request)
            elif kind == 'if':
                guard = self.env[node['guard']]
                if type(guard) is not bool:
                    raise ValueError('replay guard must be Boolean')
                outer = dict(self.env)
                self.block(node['then'] if guard else node['else'], depth+1)
                self.env = outer
            elif kind == 'retry':
                bound = node['bound']
                if type(bound) is not int or not 0 <= bound <= 16:
                    raise Unsupported('replay retry bound outside [0,16]')
                outer = dict(self.env)
                for _ in range(bound):
                    start = len(self.trace)
                    self.block(node['body'], depth+1)
                    self.env = dict(outer)
                    if all(event[4] == 'ok' for event in self.trace[start:]):
                        break
            elif kind == 'private_output':
                self.outputs.append(self.text(node['value']))
            else:
                raise Unsupported('unsupported replay instruction')

    def run(self, program, env, tape):
        self.env, self.tape, self.position = dict(env), tape, 0
        self.trace, self.requests, self.outputs, self.weight = [], [], [], Fraction(1)
        self.block(program)
        if self.position != len(tape):
            raise ValueError('unused choices in replay tape')
        return dict(trace=tuple(self.trace), requests=tuple(self.requests), private_outputs=tuple(self.outputs),
                    weight=self.weight)


def enumerate_replay(adapter, program, env, limit=100000):
    pending, result = [()], []
    visited = 0
    while pending:
        tape = pending.pop()
        visited += 1
        if visited > limit:
            raise Unsupported('replay enumeration limit')
        try:
            run = adapter.run(program, env, tape)
            if run['weight']:
                result.append(run)
        except NeedChoice as need:
            pending.extend(tape+(i,) for i in reversed(range(need.count)))
    if sum(run['weight'] for run in result) != 1:
        raise AssertionError('replay lost probability mass')
    return result
