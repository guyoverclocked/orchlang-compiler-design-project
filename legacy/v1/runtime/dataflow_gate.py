"""Trusted independent source reader for the text-valued Lean dataflow core.

Uses the restricted lexer's token operations, but reconstructs its own binding
slots and request expressions. Root public text/Boolean inputs are supported;
secret values are Boolean guards only. Call responses may feed later prompts.
Source retry, tools, reclassification and non-root/nonliteral output are unsupported.
This certifies a resource relation, not a source budget or provider contract.
"""
import json
import re
from .finite_reference import Unsupported, canonical
from .source_gate import Reader, sequence, sha


def syntactic_normalize(program):
    """Historical baseline: exact request trees and exact public/sequence shape."""
    kind = program[0]
    if kind in {'skip', 'call'}:
        return program
    if kind == 'seq':
        a, b = syntactic_normalize(program[1]), syntactic_normalize(program[2])
        return None if a is None or b is None else ['seq', a, b]
    if kind in {'public', 'secret'}:
        a, b = syntactic_normalize(program[2]), syntactic_normalize(program[3])
        if a is None or b is None:
            return None
        return ['public', program[1], a, b] if kind == 'public' else (a if a == b else None)
    if kind == 'retry':
        body = syntactic_normalize(program[2])
        return None if body is None else ['retry', program[1], body]
    raise Unsupported('unknown dataflow constructor')


def append_text(a, b):
    """Executable mirror of Lean appendText; never identifies different slots."""
    if a[0] == 'append':
        return append_text(a[1], append_text(a[2], b))
    if a[0] == 'literal':
        if a[1] == '':
            return b
        if b[0] == 'literal':
            return ['literal', a[1] + b[1]]
        if b[0] == 'append' and b[1][0] == 'literal':
            return ['append', ['literal', a[1] + b[1][1]], b[2]]
        return ['append', a, b]
    if a[0] == 'var':
        return a if b == ['literal', ''] else ['append', a, b]
    raise Unsupported('unknown dataflow text constructor')


def normalize_text(term):
    if term[0] in {'literal', 'var'}:
        return term
    if term[0] == 'append':
        return append_text(normalize_text(term[1]), normalize_text(term[2]))
    raise Unsupported('unknown dataflow text constructor')


def normalize(program):
    """Verified rewrites preserve complete text-store/ordered-trace semantics.

    This decision procedure recomputes its result; a serialized plan is an audit
    output, not a proof-carrying witness or a search/check complexity advantage.
    """
    kind = program[0]
    if kind == 'skip':
        return program
    if kind == 'call':
        return ['call', program[1], program[2], normalize_text(program[3])]
    if kind == 'seq':
        a, b = normalize(program[1]), normalize(program[2])
        if a is None or b is None:
            return None
        return b if a == ['skip'] else a if b == ['skip'] else ['seq', a, b]
    if kind in {'public', 'secret'}:
        a, b = normalize(program[2]), normalize(program[3])
        if a is None or b is None:
            return None
        if a == b:
            return a
        return ['public', program[1], a, b] if kind == 'public' else None
    if kind == 'retry':
        body = normalize(program[2])
        return None if body is None else ['retry', program[1], body]
    raise Unsupported('unknown dataflow constructor')


def template_expression(template, params, arguments):
    substitutions = dict(zip(params, arguments))
    pieces, position = [], 0
    for match in re.finditer(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', template):
        if match.start() > position:
            pieces.append(['literal', template[position:match.start()]])
        pieces.append(substitutions[match[1]])
        position = match.end()
    if position < len(template):
        pieces.append(['literal', template[position:]])
    if not pieces:
        return ['literal', '']
    # Merge adjacent literals, while retaining every response-variable slot.
    merged = []
    for piece in pieces:
        if merged and merged[-1][0] == piece[0] == 'literal':
            merged[-1] = ['literal', merged[-1][1] + piece[1]]
        else:
            merged.append(piece)
    result = merged[-1]
    for piece in reversed(merged[:-1]):
        result = ['append', piece, result]
    return result


class DataflowReader(Reader):
    def __init__(self, source):
        super().__init__(source)
        self.next_slot = 0
        self.public_inputs = []
        self.secret_guards = []
        self.contracts = {}

    def fresh(self):
        slot = self.next_slot
        self.next_slot += 1
        if self.next_slot > 128:
            raise Unsupported('dataflow slot limit')
        return slot

    def block(self, depth=0):
        if depth > 64:
            raise Unsupported('source nesting limit')
        self.take('{')
        self.scopes.append({})
        nodes = []
        while self.peek() != '}':
            tag = self.take()
            if tag in {'input', 'secret'}:
                if depth:
                    raise Unsupported('inputs/secret declarations must be at workflow root')
                name = self.ident()
                self.take(':')
                typ = self.take()
                if typ not in {'text', 'boolean'} or (tag == 'secret' and typ != 'boolean'):
                    raise Unsupported('only public text/Boolean inputs and secret Boolean guards supported')
                self.take('max_tokens')
                bound = self.natural()
                self.take(';')
                if typ == 'boolean' and bound != 1:
                    raise Unsupported('Boolean bound must be 1')
                if tag == 'secret':
                    index = len(self.secret_guards)
                    self.secret_guards.append(dict(id=index, name=name))
                    self.bind(name, ('guard', ('secret', index)))
                elif typ == 'boolean':
                    index = sum(i['type'] == 'boolean' for i in self.public_inputs)
                    self.public_inputs.append(dict(id=index, name=name, type=typ, declared_mock_bound=bound))
                    self.bind(name, ('guard', ('public', index)))
                else:
                    slot = self.fresh()
                    self.public_inputs.append(dict(id=slot, name=name, type=typ, declared_mock_bound=bound))
                    self.bind(name, ('value', slot))
            elif tag == 'model':
                name = self.ident()
                self.take('='); self.take('mock'); self.take('(')
                revision = self.string()
                self.take(')'); self.take('max_tokens')
                cap = self.natural()
                self.take(';')
                c = dict(provider='finite-replay', revision=revision, tokenizer='utf8-bytes-v1',
                         serializer='raw-utf8-v1', cap=cap, sampling='explicit-table',
                         error_policy='status-in-outcome', accounting='all-attempts-input-and-output',
                         state='stateless')
                key = canonical(c)
                self.contracts[key] = c
                self.bind(name, ('model', key))
            elif tag == 'prompt':
                name = self.ident()
                self.take('(')
                params = []
                if self.peek() != ')':
                    while True:
                        param = self.ident()
                        self.take(':'); self.take('text')
                        if param in params:
                            raise Unsupported('duplicate prompt parameter')
                        params.append(param)
                        if self.peek() != ',':
                            break
                        self.take(',')
                self.take(')'); self.take('->'); self.take('text'); self.take('=')
                template = self.string()
                self.take(';')
                stripped = re.sub(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', '', template)
                names = re.findall(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', template)
                if ('{' in stripped or '}' in stripped or any(n not in params for n in names) or
                        any(p not in names for p in params)):
                    raise Unsupported('unknown/malformed template substitution')
                self.bind(name, ('prompt', (params, template)))
            elif tag == 'let':
                name = self.ident()
                self.take(':'); self.take('text'); self.take('='); self.take('call')
                params, template = self.lookup(self.ident(), 'prompt')
                self.take('(')
                arguments = []
                if self.peek() != ')':
                    while True:
                        if self.peek().startswith('"'):
                            arguments.append(['literal', self.string()])
                        else:
                            arguments.append(['var', self.lookup(self.ident(), 'value')])
                        if self.peek() != ',':
                            break
                        self.take(',')
                self.take(')'); self.take('using')
                key = self.lookup(self.ident(), 'model')
                self.take(';')
                if len(params) != len(arguments):
                    raise Unsupported('prompt arity mismatch')
                request = template_expression(template, params, arguments)
                slot = self.fresh()
                nodes.append(['call', slot, key, request])
                self.bind(name, ('value', slot))
            elif tag == 'if':
                kind, guard = self.lookup(self.ident(), 'guard')
                start = self.next_slot
                left = self.block(depth+1)
                left_end = self.next_slot
                self.next_slot = start
                self.take('else')
                right = self.block(depth+1)
                self.next_slot = max(left_end, self.next_slot)
                nodes.append([kind, guard, left, right])
            elif tag == 'output':
                if depth:
                    raise Unsupported('dataflow source permits literal outputs only at workflow root')
                self.string(); self.take(';')
            else:
                raise Unsupported('statement outside dataflow fragment: '+tag)
        self.take('}')
        self.scopes.pop()
        return sequence(nodes)

    def read(self):
        self.take('workflow')
        workflow = self.ident()
        self.take('budget')
        budget = self.natural()
        program = self.block()
        if self.pos != len(self.tokens):
            raise Unsupported('only one complete workflow supported')
        return dict(workflow=workflow, declared_mock_budget=budget, program=program,
                    public_inputs=self.public_inputs, secret_guards=self.secret_guards,
                    contracts=self.contracts, slots=self.next_slot)


def read_source(data):
    if len(data) > 1000000:
        raise Unsupported('source byte limit')
    result = DataflowReader(data.decode('utf-8', errors='strict')).read()
    result['source_sha256'] = sha(data)
    return result


def issue(data):
    source = read_source(data)
    plan = normalize(source['program'])
    if plan is None:
        raise Unsupported('dataflow branches do not normalize to equal plans')
    return dict(format='orchlang-dataflow-v1', source_sha256=source['source_sha256'],
                program=source['program'], plan=plan)


def bind_certificate(data, certificate):
    source = read_source(data)
    if (set(certificate) != {'format', 'source_sha256', 'program', 'plan'} or
            certificate['format'] != 'orchlang-dataflow-v1' or
            certificate['source_sha256'] != source['source_sha256'] or
            certificate['program'] != source['program']):
        raise Unsupported('dataflow certificate does not match reconstructed source')
    return dict(program=source['program'], plan=certificate['plan'], execute=[])


def reference_text(term):
    if term[0] == 'literal':
        return term[1]
    if term[0] == 'var':
        return {'var': 'v'+str(term[1])}
    if term[0] == 'append':
        return {'concat': [reference_text(term[1]), reference_text(term[2])]}
    raise Unsupported('unknown dataflow text term')


def reference_program(program):
    kind = program[0]
    if kind == 'skip':
        return []
    if kind == 'call':
        return [dict(kind='call', bind='v'+str(program[1]), model=program[2], request=reference_text(program[3]))]
    if kind == 'seq':
        return reference_program(program[1]) + reference_program(program[2])
    if kind in {'public', 'secret'}:
        return [dict(kind='if', guard=kind+str(program[1]), then=reference_program(program[2]),
                     **{'else': reference_program(program[3])})]
    if kind == 'retry':
        return [dict(kind='retry', bound=program[1], body=reference_program(program[2]))]
    raise Unsupported('unknown dataflow program')
