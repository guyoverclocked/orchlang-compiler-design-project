#!/usr/bin/env python3
"""Experimental cyclic request-protocol frontend for OrchLang research.

Product-state checking establishes a sufficient relation on two executions of
one finite graph, under a shared complete request/outcome oracle. It does not
bound the total cost or prove termination of billable cycles. See
../docs/CYCLIC_METHOD_REVIEW.md for the proof contract and prior art.
"""
from __future__ import annotations
import argparse
from collections import deque
from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import re
import sys

FORMAT = 'orchlang-request-graph'
CERT_FORMAT = 'orchlang-cyclic-request-certificate'
NAME = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')
MAX_TOKEN = 2**64 - 2
OPS = {'<', '<=', '>', '>=', '==', '!='}
MAX_PROBE_CALLS = 10000
MAX_PROBE_VALUE_BYTES = 1024 * 1024
MAX_PROBE_TRACE_BYTES = 16 * 1024 * 1024
MAX_PROBE_CONTROL_STEPS = 1000000
MAX_SOURCE_BYTES = 16 * 1024 * 1024


class InvalidGraph(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise InvalidGraph('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise InvalidGraph('nonfinite JSON number: ' + value)
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=constant)


def keys(value, required, optional=()):
    if not isinstance(value, dict): raise InvalidGraph('expected JSON object')
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise InvalidGraph('object fields: missing %s; unknown %s' % (sorted(missing), sorted(unknown)))


def natural(value, upper=MAX_TOKEN, minimum=0):
    if type(value) is not int or not minimum <= value <= upper:
        raise InvalidGraph('integer outside [%d, %d]: %r' % (minimum, upper, value))
    return value


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise InvalidGraph('invalid identifier: %r' % value)
    return value


def utf8(value):
    if not isinstance(value, str): raise InvalidGraph('expected UTF-8 text')
    try:
        return value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise InvalidGraph('text must contain valid Unicode scalar values') from error


class Graph:
    def __init__(self, document):
        keys(document, ['format', 'version', 'name', 'inputs', 'registers', 'models', 'states', 'entry'], ['chars_per_token'])
        if document['format'] != FORMAT or type(document['version']) is not int or document['version'] != 1:
            raise InvalidGraph('unknown graph format/version')
        self.name = name(document['name'])
        self.divisor = natural(document.get('chars_per_token', 4), minimum=1)
        self.inputs, self.registers, self.models, self.states = {}, {}, {}, {}
        for group in ('inputs', 'registers', 'models', 'states'):
            if not isinstance(document[group], dict): raise InvalidGraph(group + ' must be an object')
        for alias, model in document['models'].items():
            name(alias); keys(model, ['provider', 'model', 'max_tokens'], ['unit_price'])
            if not all(isinstance(model[k], str) and model[k] for k in ('provider', 'model')):
                raise InvalidGraph('provider/model must be nonempty strings')
            for field in ('provider', 'model'): utf8(model[field])
            cap = natural(model['max_tokens'], minimum=1)
            price = model.get('unit_price', 0.0)
            try:
                finite_price = type(price) in (int, float) and math.isfinite(float(price)) and price >= 0
            except OverflowError:
                finite_price = False
            if not finite_price:
                raise InvalidGraph('model price must be finite and nonnegative')
            self.models[alias] = {'provider': model['provider'], 'model': model['model'], 'max_tokens': cap,
                                  'has_unit_price': 'unit_price' in model, 'unit_price': float(price) or 0.0}
        for variable, declaration in document['inputs'].items():
            name(variable); keys(declaration, ['type', 'label'], ['max_tokens'])
            if declaration['type'] not in ('text', 'boolean') or declaration['label'] not in ('public', 'secret'):
                raise InvalidGraph('input requires text/boolean and public/secret')
            if declaration['type'] == 'text' and 'max_tokens' not in declaration:
                raise InvalidGraph('text input needs max_tokens')
            cap = natural(declaration.get('max_tokens', 1))
            self.inputs[variable] = {**declaration, 'max_tokens': cap}
        for variable, declaration in document['registers'].items():
            name(variable); keys(declaration, ['model'])
            name(declaration['model'])
            if variable in self.inputs: raise InvalidGraph('input/register name collision: ' + variable)
            if declaration['model'] not in self.models: raise InvalidGraph('unknown register token unit')
            self.registers[variable] = dict(declaration)
        for state, body in document['states'].items():
            name(state); keys(body, ['calls', 'next'])
            if not isinstance(body['calls'], list): raise InvalidGraph('calls must be an array')
            calls = []
            for call in body['calls']:
                keys(call, ['model', 'template', 'arguments', 'result'])
                name(call['model']); name(call['result'])
                if call['model'] not in self.models: raise InvalidGraph('unknown call model')
                if call['result'] not in self.registers: raise InvalidGraph('call result must be a declared text register')
                if not isinstance(call['template'], str) or not isinstance(call['arguments'], list):
                    raise InvalidGraph('call requires string template and argument array')
                utf8(call['template'])
                contract = self.models[call['model']]
                register_model = self.models[self.registers[call['result']]['model']]
                if self.unit(contract) != self.unit(register_model) or contract['max_tokens'] > register_model['max_tokens']:
                    raise InvalidGraph('result register token-unit/cap contract disagrees')
                for argument in call['arguments']:
                    keys(argument, [], ['literal', 'value'])
                    if set(argument) not in ({'literal'}, {'value'}): raise InvalidGraph('one argument atom required')
                    if 'literal' in argument:
                        if not isinstance(argument['literal'], str): raise InvalidGraph('literal arguments must be text')
                        utf8(argument['literal'])
                    else:
                        variable = name(argument['value'])
                        if variable in self.inputs:
                            if self.inputs[variable]['label'] != 'public' or self.inputs[variable]['type'] != 'text':
                                raise InvalidGraph('only public text inputs can reach requests')
                        elif variable in self.registers:
                            producer = self.models[self.registers[variable]['model']]
                            if self.unit(producer) != self.unit(contract):
                                raise InvalidGraph('generated token units cannot cross provider/model identities')
                        else: raise InvalidGraph('unknown request value: ' + str(variable))
                calls.append(dict(call))
            decision = body['next']; keys(decision, ['kind'], ['target', 'guard', 'then', 'else'])
            if decision['kind'] == 'goto':
                keys(decision, ['kind', 'target'])
                name(decision['target'])
            elif decision['kind'] == 'stop':
                keys(decision, ['kind'])
            elif decision['kind'] in ('public', 'secret'):
                keys(decision, ['kind', 'guard', 'then', 'else'])
                name(decision['then']); name(decision['else'])
                guard = decision['guard']; keys(guard, ['value'], ['op', 'limit'])
                variable = name(guard['value'])
                if variable not in self.inputs and variable not in self.registers: raise InvalidGraph('unknown guard value')
                is_boolean = variable in self.inputs and self.inputs[variable]['type'] == 'boolean'
                if is_boolean:
                    keys(guard, ['value'])
                else:
                    keys(guard, ['value', 'op', 'limit'])
                    if not isinstance(guard['op'], str) or guard['op'] not in OPS: raise InvalidGraph('unknown comparison')
                    natural(guard['limit'])
                confidential = variable in self.inputs and self.inputs[variable]['label'] == 'secret'
                if (decision['kind'] == 'secret') != confidential:
                    raise InvalidGraph('decision label must match its input/register confidentiality')
            else: raise InvalidGraph('unknown decision kind')
            self.states[state] = {'calls': calls, 'next': decision}
        self.entry = name(document['entry'])
        if self.entry not in self.states: raise InvalidGraph('unknown entry state')
        for body in self.states.values():
            for target in self.targets(body['next']):
                if target not in self.states: raise InvalidGraph('unknown successor state: ' + str(target))
        self.reachable = set()
        todo = [self.entry]
        while todo:
            state = todo.pop()
            if state in self.reachable: continue
            self.reachable.add(state); todo.extend(self.targets(self.states[state]['next']))
        # Productive call cycles are allowed. Call-free cycles can hide a
        # termination distinction, so this prototype excludes them altogether.
        empty = {s for s in self.reachable if not self.states[s]['calls']}
        visiting, visited = set(), set()
        for start in sorted(empty):
            stack = [(start, False)]
            while stack:
                state, exiting = stack.pop()
                if exiting:
                    visiting.remove(state); visited.add(state)
                    continue
                if state in visited: continue
                if state in visiting: raise InvalidGraph('reachable call-free cycle at ' + state)
                visiting.add(state); stack.append((state, True))
                stack.extend((target, False) for target in reversed(self.targets(self.states[state]['next']))
                             if target in empty)

    @staticmethod
    def unit(contract):
        return contract['provider'], contract['model']

    @staticmethod
    def targets(decision):
        if decision['kind'] == 'goto': return [decision['target']]
        if decision['kind'] in ('public', 'secret'): return [decision['then'], decision['else']]
        return []

    def event(self, pc):
        state, index = pc
        calls = self.states[state]['calls']
        if index < len(calls): return 'call', calls[index]
        if index != len(calls): raise InvalidGraph('invalid program counter')
        decision = self.states[state]['next']
        return decision['kind'], decision

    def argument_bound(self, atom):
        if 'literal' in atom: return self.estimate(atom['literal'])
        variable = atom['value']
        if variable in self.inputs: return self.inputs[variable]['max_tokens']
        return self.models[self.registers[variable]['model']]['max_tokens']

    def estimate(self, text):
        return (len(utf8(text)) + self.divisor - 1) // self.divisor

    def state_bounds(self):
        result = {}
        for state in sorted(self.reachable):
            output = input_ = 0
            for call in self.states[state]['calls']:
                output += self.models[call['model']]['max_tokens']
                input_ += self.estimate(call['template']) + sum(self.argument_bound(a) for a in call['arguments'])
            result[state] = {'output_tokens': output, 'input_tokens': input_, 'total_tokens': output + input_}
        return result


def related_atom(left, right, relation):
    if 'literal' in left or 'literal' in right:
        return 'literal' in left and 'literal' in right and left['literal'] == right['literal']
    return (left['value'], right['value']) in relation


def obligation(graph, left, right, relation):
    """One local product rule. Successors are universal proof obligations."""
    lk, le = graph.event(left); rk, re = graph.event(right)
    unchanged = lambda l, r: (l, r, relation)
    if lk == 'goto': return 'left-goto', [unchanged((le['target'], 0), right)], None
    if rk == 'goto': return 'right-goto', [unchanged(left, (re['target'], 0))], None
    if lk == 'secret':
        return 'left-secret', [unchanged((le[a], 0), right) for a in ('then', 'else')], None
    if rk == 'secret':
        return 'right-secret', [unchanged(left, (re[a], 0)) for a in ('then', 'else')], None
    if lk != rk: return 'mismatch', [], 'observable events differ: %s versus %s' % (lk, rk)
    if lk == 'stop': return 'stop', [], None
    if lk == 'public':
        lg, rg = le['guard'], re['guard']
        if (lg['value'], rg['value']) not in relation or {k:v for k,v in lg.items() if k != 'value'} != {k:v for k,v in rg.items() if k != 'value'}:
            return 'mismatch', [], 'public guards are not proved equal'
        return 'public-choice', [unchanged((le[a], 0), (re[a], 0)) for a in ('then', 'else')], None
    if lk == 'call':
        if graph.models[le['model']] != graph.models[re['model']]:
            return 'mismatch', [], 'resolved model contracts differ'
        if le['template'] != re['template']:
            return 'mismatch', [], 'exact request templates differ'
        if len(le['arguments']) != len(re['arguments']) or not all(related_atom(a,b,relation) for a,b in zip(le['arguments'],re['arguments'])):
            return 'mismatch', [], 'ordered request arguments are not proved equal'
        lreg, rreg = le['result'], re['result']
        after = frozenset((a,b) for a,b in relation if a != lreg and b != rreg) | {(lreg,rreg)}
        return 'matched-call', [((left[0],left[1]+1), (right[0],right[1]+1), after)], None
    raise InvalidGraph('unhandled product event')


def check(graph, max_nodes=50000):
    natural(max_nodes, upper=1000000, minimum=1)
    initial = frozenset((v,v) for v,d in graph.inputs.items() if d['label'] == 'public')
    root = ((graph.entry,0),(graph.entry,0),initial)
    identities, nodes, predecessors, todo = {root:0}, [], {}, deque([root])
    report = {'format': CERT_FORMAT, 'version': 1, 'graph_name': graph.name, 'status': 'accepted',
              'root': 0, 'nodes': nodes, 'max_nodes': max_nodes,
              'semantics': {'oracle': 'shared Omega(resolved-contract,per-contract-ordinal,template,ordered-text-values)',
                            'inputs': 'all public external values agree; secret inputs may differ',
                            'claim': 'equal complete request/usage traces and stop positions under the shared oracle',
                            'cycles': 'every finite trace prefix; no termination or finite total-cost claim',
                            'input_accounting': 'complete additive request contract in compatible token units',
                            'unsupported': ['declassification','tools','request serialization','independent provider sampling','call-free cycles']},
              'state_entry_bounds': graph.state_bounds(),
              'reachable_source_states': sorted(graph.reachable)}
    def path_to(key):
        path = [identities[key]]
        while key in predecessors:
            key = predecessors[key]; path.append(identities[key])
        return list(reversed(path))
    while todo:
        key = todo.popleft(); left,right,relation = key
        rule, successors, error = obligation(graph,left,right,relation)
        node = {'id': identities[key], 'left': list(left), 'right': list(right),
                'equal_values': [list(p) for p in sorted(relation)], 'rule': rule, 'successors': []}
        if node['id'] != len(nodes): raise AssertionError('non-BFS proof order')
        nodes.append(node)
        if error:
            report.update(status='rejected', diagnostic=error, mismatch_path=path_to(key))
            break
        for successor in successors:
            if successor not in identities:
                if len(identities) >= max_nodes:
                    report.update(status='unknown', diagnostic='product-node resource cap reached', mismatch_path=path_to(key))
                    return report
                identities[successor] = len(identities); predecessors[successor] = key; todo.append(successor)
            node['successors'].append(identities[successor])
    report['product_nodes'] = len(nodes)
    report['product_edges'] = sum(len(n['successors']) for n in nodes)
    return report


def reference_run(graph, store, seed, max_calls=100):
    """Full-value probe sharing producer schema; not an independent interpreter.

    Resource limits apply to this diagnostic probe, not to the static theorem.
    A cap reached before a call yields a truncated prefix; stop/control events
    are still inspected after the final permitted call.
    """
    natural(seed, upper=2**64-1)
    natural(max_calls, upper=MAX_PROBE_CALLS, minimum=1)
    if not isinstance(store, Mapping) or not all(isinstance(k, str) for k in store):
        raise InvalidGraph('reference store must be a mapping with string keys')
    if set(store) != set(graph.inputs): raise InvalidGraph('reference store must name each input once')
    values = dict(store)
    for variable,declaration in graph.inputs.items():
        value = values[variable]
        if declaration['type'] == 'boolean':
            if type(value) is not bool: raise InvalidGraph('Boolean input type mismatch')
        else:
            if isinstance(value, str) and len(value) > MAX_PROBE_VALUE_BYTES:
                raise InvalidGraph('reference input exceeds value byte limit')
            if not isinstance(value,str) or graph.estimate(value) > declaration['max_tokens']:
                raise InvalidGraph('text input type/bound mismatch')
            if len(utf8(value)) > MAX_PROBE_VALUE_BYTES:
                raise InvalidGraph('reference input exceeds value byte limit')
    pc, ordinals, trace = (graph.entry,0), {}, []
    control_steps = trace_bytes = 0
    while True:
        control_steps += 1
        if control_steps > MAX_PROBE_CONTROL_STEPS:
            raise InvalidGraph('reference control-step resource cap reached')
        kind,event = graph.event(pc)
        if kind == 'stop': return {'trace':trace,'stopped':True}
        if kind == 'goto': pc = (event['target'],0); continue
        if kind in ('public','secret'):
            guard = event['guard']
            if guard['value'] not in values: raise InvalidGraph('reference guard uses uninitialized register')
            value = values[guard['value']]
            if 'op' not in guard: decision = value
            else:
                a,b = graph.estimate(value),guard['limit']; op=guard['op']
                decision = {'<':a<b,'<=':a<=b,'>':a>b,'>=':a>=b,'==':a==b,'!=':a!=b}[op]
            pc = (event['then' if decision else 'else'],0); continue
        if len(trace) >= max_calls:
            return {'trace':trace,'stopped':False,'truncated_at_calls':max_calls}
        contract = graph.models[event['model']]
        contract_key = json.dumps(contract,sort_keys=True,separators=(',',':'))
        ordinal = ordinals.get(contract_key,0);ordinals[contract_key]=ordinal+1
        if any('value' in a and a['value'] not in values for a in event['arguments']):
            raise InvalidGraph('reference request uses uninitialized register')
        arguments = [a['literal'] if 'literal' in a else values[a['value']] for a in event['arguments']]
        request_bytes = len(utf8(event['template'])) + sum(len(utf8(a)) for a in arguments)
        if request_bytes > MAX_PROBE_VALUE_BYTES:
            raise InvalidGraph('reference request exceeds value byte limit')
        key = json.dumps([graph.name,seed,contract,ordinal,event['template'],arguments],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        digest = hashlib.sha256(key.encode('utf-8')).digest()
        output_tokens = int.from_bytes(digest[:8],'big') % (min(contract['max_tokens'],32)+1)
        response_bytes = output_tokens * graph.divisor
        if response_bytes > MAX_PROBE_VALUE_BYTES:
            raise InvalidGraph('reference response exceeds value byte limit')
        trace_bytes += request_bytes + response_bytes
        if trace_bytes > MAX_PROBE_TRACE_BYTES:
            raise InvalidGraph('reference trace byte resource cap reached')
        # Exact response bytes, not a token-count-only placeholder. Each unit
        # is divisor bytes, and the alphabet depends on the complete request.
        alphabet = 'abcdefghijklmNOPQRSTUVWXYZ0123456789'
        response = ''.join(alphabet[digest[i%32]%len(alphabet)] for i in range(response_bytes))
        input_tokens = graph.estimate(event['template']) + sum(graph.estimate(a) for a in arguments)
        trace.append({'contract':contract,'ordinal':ordinal,'template':event['template'],
                      'arguments':arguments,'response':response,'input_tokens':input_tokens,'output_tokens':output_tokens})
        values[event['result']]=response;pc=(pc[0],pc[1]+1)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('source',type=Path)
    cli.add_argument('--report',type=Path)
    cli.add_argument('--max-nodes',type=int,default=50000)
    args=cli.parse_args()
    try:
        if args.source.stat().st_size > MAX_SOURCE_BYTES: raise InvalidGraph('graph source exceeds byte resource cap')
        raw=args.source.read_bytes();graph=Graph(strict_json(raw));report=check(graph,args.max_nodes)
        report['source_sha256']=sha(raw);report['checker_sha256']=sha(Path(__file__).read_bytes())
        text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
        if args.report: args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(text)
        print(text,end='')
        return 0 if report['status']=='accepted' else 2 if report['status']=='unknown' else 1
    except (InvalidGraph,ValueError,KeyError,TypeError,OverflowError,RecursionError,OSError) as error:
        print('graph check failed closed: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':
    sys.exit(main())
