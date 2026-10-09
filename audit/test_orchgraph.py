#!/usr/bin/env python3
"""Focused regressions for the experimental cyclic product checker."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from generate_graph_examples import base, corpus
from orchgraph import Graph, InvalidGraph, check, strict_json, reference_run


class GraphCheckerTests(unittest.TestCase):
    def test_development_corpus_verdicts(self):
        for group,name,document,diagnostic in corpus():
            with self.subTest(name=name):
                if group=='invalid':
                    with self.assertRaisesRegex(InvalidGraph,diagnostic):Graph(document)
                else:
                    result=check(Graph(document))
                    self.assertEqual(result['status'],'accepted' if group=='accepted' else 'rejected')
                    if diagnostic:self.assertIn(diagnostic,result['diagnostic'])

    def test_matched_overwritten_registers_remain_sound(self):
        graph=Graph(base())
        self.assertEqual(check(graph)['status'],'accepted')
        for seed in range(16):
            runs=[reference_run(graph,{'query':'é漢 as a concrete public question','route':route},seed,100)
                  for route in (False,True)]
            self.assertEqual(runs[0],runs[1])
            for event in runs[0]['trace']:
                self.assertEqual(graph.estimate(event['response']),event['output_tokens'])
                self.assertLessEqual(event['output_tokens'],event['contract']['max_tokens'])

    def test_overwrite_kills_stale_equality(self):
        document=next(g for _,n,g,_ in corpus() if n=='overwritten_result_relation')
        result=check(Graph(document))
        self.assertEqual(result['status'],'rejected')
        self.assertIn('arguments',result['diagnostic'])

    def test_aliases_match_resolved_contracts(self):
        document=next(g for _,n,g,_ in corpus() if n=='canonical_alias_cycle')
        self.assertEqual(check(Graph(document))['status'],'accepted')

    def test_public_guard_must_use_initialized_related_values(self):
        document=base();document['entry']='guard'
        document['states']['guard']={'calls':[],'next':{'kind':'public',
            'guard':{'value':'a','op':'<=','limit':8},'then':'left','else':'right'}}
        result=check(Graph(document))
        self.assertEqual(result['status'],'rejected')
        self.assertIn('guards',result['diagnostic'])

    def test_request_must_use_initialized_related_values(self):
        document=base();document['states']['left']['calls'][0]['arguments']=[{'value':'a'}]
        self.assertEqual(check(Graph(document))['status'],'rejected')

    def test_cap_exhaustion_unknown_not_accepted(self):
        result=check(Graph(base()),1)
        self.assertEqual(result['status'],'unknown')

    def test_boolean_version_not_an_integer_version(self):
        document=base();document['version']=True
        with self.assertRaises(InvalidGraph):Graph(document)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(InvalidGraph):strict_json('{"version":1,"version":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(InvalidGraph):strict_json('{"price":NaN}')

    def test_nonfinite_price_rejected(self):
        document=base();document['models']['m']['unit_price']=float('inf')
        with self.assertRaises(InvalidGraph):Graph(document)

    def test_enormous_integer_price_rejected(self):
        document=base();document['models']['m']['unit_price']=10**400
        with self.assertRaises(InvalidGraph):Graph(document)

    def test_unknown_fields_fail_closed(self):
        document=base();document['models']['m']['temperature']='secret'
        with self.assertRaises(InvalidGraph):Graph(document)

    def test_deep_silent_acyclic_control_uses_iterative_validation(self):
        document=base();document['entry']='s0'
        for i in range(1500):document['states']['s'+str(i)]={'calls':[],
            'next':{'kind':'goto','target':'s'+str(i+1) if i<1499 else 'stop'}}
        graph=Graph(document)
        self.assertEqual(check(graph,5000)['status'],'accepted')

    def test_reachable_silent_cycle_rejected(self):
        document=base();document['states']['choose']['next']={'kind':'goto','target':'choose'}
        with self.assertRaisesRegex(InvalidGraph,'call-free cycle'):Graph(document)

    def test_unreachable_silent_cycle_cannot_change_execution(self):
        document=base();document['states']['unused']={'calls':[],'next':{'kind':'goto','target':'unused'}}
        self.assertEqual(check(Graph(document))['status'],'accepted')

    def test_typed_store_checked(self):
        graph=Graph(base())
        with self.assertRaises(InvalidGraph):reference_run(graph,{'query':'text','route':'false'},1)

    def test_input_bound_checked(self):
        graph=Graph(base())
        with self.assertRaises(InvalidGraph):reference_run(graph,{'query':'x'*129,'route':False},1)

    def test_stop_against_call_rejected(self):
        document=next(g for _,n,g,_ in corpus() if n=='one_sided_private_transition')
        self.assertEqual(check(Graph(document))['status'],'rejected')

    def test_all_private_successors_are_universal_obligations(self):
        graph=Graph(base());report=check(graph)
        self.assertEqual(report['nodes'][0]['rule'],'left-secret')
        self.assertEqual(len(report['nodes'][0]['successors']),2)
        self.assertTrue(any(n['rule']=='right-secret' and len(n['successors'])==2 for n in report['nodes']))

    def test_probe_budget_and_seed_are_bounded_integers(self):
        graph=Graph(base());store={'query':'text','route':False}
        for budget in (True,0,-1,1.5,10001):
            with self.subTest(budget=budget),self.assertRaises(InvalidGraph):
                reference_run(graph,store,1,budget)
        for seed in (True,-1,2**64,'fixed',float('nan'),{}):
            with self.subTest(seed=repr(seed)),self.assertRaises(InvalidGraph):
                reference_run(graph,store,seed,2)

    def test_probe_store_requires_mapping(self):
        with self.assertRaises(InvalidGraph):
            reference_run(Graph(base()),[('query','text'),('route',False)],1)

    def test_probe_exact_call_cap_still_observes_stop(self):
        document=base()
        for state in ('left','right'):document['states'][state]['next']={'kind':'stop'}
        graph=Graph(document);store={'query':'text','route':False}
        self.assertTrue(reference_run(graph,store,1,2)['stopped'])
        self.assertFalse(reference_run(graph,store,1,1)['stopped'])

    def test_probe_huge_divisor_does_not_allocate_response(self):
        document=base();document['chars_per_token']=2**64-2
        with self.assertRaisesRegex(InvalidGraph,'response.*byte limit'):
            reference_run(Graph(document),{'query':'text','route':False},1)

    def test_probe_control_steps_are_bounded(self):
        with patch('orchgraph.MAX_PROBE_CONTROL_STEPS',1):
            with self.assertRaisesRegex(InvalidGraph,'control-step'):
                reference_run(Graph(base()),{'query':'text','route':False},1)

    def test_probe_trace_bytes_are_bounded(self):
        with patch('orchgraph.MAX_PROBE_TRACE_BYTES',1):
            with self.assertRaisesRegex(InvalidGraph,'trace byte'):
                reference_run(Graph(base()),{'query':'text','route':False},1)

    def test_probe_large_public_input_fails_before_encoding(self):
        document=base();document['inputs']['query']['max_tokens']=2**64-2
        with self.assertRaisesRegex(InvalidGraph,'input.*byte limit'):
            reference_run(Graph(document),{'query':'x'*(1024*1024+1),'route':False},1)

    def test_scalar_utf8_required_for_inputs_and_request_literals(self):
        with self.assertRaisesRegex(InvalidGraph,'Unicode scalar'):
            reference_run(Graph(base()),{'query':'\ud800','route':False},1)
        for field in ('template','literal','provider'):
            document=base()
            if field=='template':document['states']['left']['calls'][0]['template']='\ud800'
            elif field=='literal':document['states']['left']['calls'][0]['arguments']=[{'literal':'\ud800'}]
            else:document['models']['m']['provider']='\ud800'
            with self.subTest(field=field),self.assertRaises(InvalidGraph):Graph(document)

    def test_unhashable_references_fail_as_invalid_graph(self):
        for field in ('entry','model','result','argument','guard','operator','target'):
            document=base()
            if field=='entry':document['entry']=[]
            elif field in ('model','result'):document['states']['left']['calls'][0][field]=[]
            elif field=='argument':document['states']['left']['calls'][0]['arguments']=[{'value':[]}]
            elif field=='guard':document['states']['choose']['next']['guard']['value']=[]
            elif field=='operator':document['states']['left']['next']['guard']['op']=[]
            else:document['states']['choose']['next']={'kind':'goto','target':[]}
            with self.subTest(field=field),self.assertRaises(InvalidGraph):Graph(document)

    def test_probe_uninitialized_values_fail_explicitly(self):
        document=base();document['states']['left']['calls'][0]['arguments']=[{'value':'a'}]
        with self.assertRaisesRegex(InvalidGraph,'uninitialized'):
            reference_run(Graph(document),{'query':'text','route':True},1)


if __name__=='__main__':unittest.main()
