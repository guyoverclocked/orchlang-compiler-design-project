from collections import Counter
from fractions import Fraction
import itertools
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.finite_reference import Reference, canonical, Unsupported, distribution
from runtime.replay_adapter import Replay, enumerate_replay
from tests.test_finite_reference import contract, call, outcome


def reference_observations(paths):
    result = Counter()
    for state, weight in paths:
        trace = tuple((e.contract, e.unit, e.input, e.output, e.status) for e in state.trace)
        result[(trace, state.private_outputs)] += weight
    return {k:v for k,v in result.items() if v}


def replay_observations(paths):
    result = Counter()
    for run in paths:
        result[(run['trace'], run['private_outputs'])] += run['weight']
    return dict(result)


def conformance_cases():
    # Fixed cross-product: 2 tokenizer units x 3 retry caps x 2 guards.
    for unit, bound, flag in itertools.product(('utf8-bytes-v1','unicode-codepoints-v1'), (0,1,2), (False,True)):
        c = contract(tokenizer=unit, cap=8)
        contracts = {'m':c, 'alias':dict(c)}
        kernel = {canonical(c): {'*':[outcome('é','1/2'), outcome('','1/2','error')]}}
        branch = dict(kind='if', guard='public', then=[call('é', model='alias')], **{'else':[]})
        nodes = [dict(kind='retry', bound=bound, body=[call('é'), branch]),
                 dict(kind='private_output', value={'var':'secret'})]
        yield f'{unit}/{bound}/{flag}', contracts, kernel, nodes, dict(public=flag,secret='retained')


class ReplayTests(unittest.TestCase):
    def test_reference_agreement_census(self):
        for name, contracts, kernels, program, env in conformance_cases():
            with self.subTest(case=name):
                self.assertEqual(reference_observations(Reference(contracts,kernels).run(program,env)),
                                 replay_observations(enumerate_replay(Replay(contracts,kernels),program,env)))

    def test_failed_attempts_counted_and_stop_on_success(self):
        c = contract()
        adapter = Replay({'m':c}, {canonical(c):{'*':[outcome('x','1/2'),outcome('','1/2','error')]}})
        program = [dict(kind='retry',bound=2,body=[call()])]
        paths = enumerate_replay(adapter, program, {})
        self.assertEqual(sorted((len(p['trace']),p['weight']) for p in paths),
                         [(1,Fraction(1,2)),(2,Fraction(1,4)),(2,Fraction(1,4))])

    def test_response_text_and_utf8_serialization(self):
        c = contract()
        adapter = Replay({'m':c}, {canonical(c):{'*':[outcome('é')]}})
        result = adapter.run([call('yes',bind='x'),call({'concat':['prefix:',{'var':'x'}]})], {}, [0,0])
        self.assertEqual(result['requests'], ('yes','prefix:é'))
        self.assertEqual(result['trace'][1][2],9)

    def test_preflight_unselected_cap_violation(self):
        c = contract(cap=1)
        adapter = Replay({'m':c},{canonical(c):{'*':[outcome('x','1/2'),outcome('xx','1/2')]}})
        with self.assertRaises(ValueError):
            adapter.run([call()],{},[0])

    def test_missing_request_mass_status_and_unknown_unit(self):
        c = contract()
        for outcomes in ([outcome('x','1/3')],[outcome('x',status='timeout')]):
            with self.assertRaises(ValueError):
                Replay({'m':c},{canonical(c):{'*':outcomes}}).run([call()],{},[0])
        with self.assertRaises(Unsupported):
            Replay({'m':c},{canonical(c):{}}).run([call()],{},[0])
        with self.assertRaises(Unsupported):
            Replay({'m':contract(tokenizer='unknown')},{})

    def test_lexical_response_does_not_escape(self):
        c = contract()
        a = Replay({'m':c},{canonical(c):{'*':[outcome('x')]}})
        with self.assertRaises(KeyError):
            a.run([dict(kind='if',guard='g',then=[call(bind='x')],**{'else':[]}),
                   call({'var':'x'})], {'g':True},[0,0])


if __name__ == '__main__':
    unittest.main()
