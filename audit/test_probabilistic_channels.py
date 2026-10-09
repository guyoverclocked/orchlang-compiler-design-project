#!/usr/bin/env python3
"""Exact, hand-calculable channel semantics and fail-closed regressions."""
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from probabilistic_channels import (ChannelError,analyze,canonical,channel_metrics,
                                   producer_histogram)


def fixture():
    graph={'format':'orchlang-request-graph','version':1,'name':'exact_channel',
           'chars_per_token':1,'inputs':{'secret':{'type':'boolean','label':'secret'}},
           'models':{'m':{'provider':'offline','model':'finite','max_tokens':4}},
           'registers':{'r':{'model':'m'}},'entry':'choose','states':{
           'choose':{'calls':[],'next':{'kind':'secret','guard':{'value':'secret'},'then':'left','else':'right'}},
           'left':{'calls':[{'model':'m','template':'A','arguments':[],'result':'r'}],'next':{'kind':'stop'}},
           'right':{'calls':[{'model':'m','template':'B','arguments':[],'result':'r'}],'next':{'kind':'stop'}}}}
    kernel={'format':'orchlang-finite-outcome-kernel','version':1,'defaults':{
        'm':[{'response':'x','output_tokens':1,'probability':'1'}]},'rules':[]}
    scenarios=[{'values':{'secret':False},'prior':'1/2'},{'values':{'secret':True},'prior':'1/2'}]
    return graph,kernel,scenarios


def outcomes(p):
    return [{'response':'x','output_tokens':1,'probability':str(p)},
            {'response':'xx','output_tokens':2,'probability':str(1-p)}]


class ExactChannelTests(unittest.TestCase):
    def test_equal_laws_have_zero_bits_and_unit_vulnerability_ratio(self):
        g,k,s=fixture();result=analyze(g,k,{},s,1)
        self.assertEqual(result['status'],'complete')
        metrics=result['metrics']
        self.assertTrue(metrics['all_pairwise_observation_laws_equal'])
        self.assertEqual(metrics['pairwise'][0]['total_variation'],'0')
        self.assertEqual(metrics['bayes_vulnerability'],'1/2')
        self.assertEqual(metrics['min_entropy_vulnerability_ratio'],'1')
        self.assertEqual(metrics['min_entropy_leakage_bits_approx'],0)
        self.assertEqual(metrics['mutual_information_bits_approx'],0)
        self.assertTrue(all(t['ratio']=='1' for t in metrics['mutual_information_exact_expression']['terms']))

    def test_hand_calculated_noisy_bit_channel(self):
        g,k,s=fixture();k['rules']=[{'model':'m','template':t,'outcomes':outcomes(p)}for t,p in [('A',Fraction(3,4)),('B',Fraction(1,4))]]
        metrics=analyze(g,k,{},s,1)['metrics']
        self.assertEqual(metrics['pairwise'][0]['total_variation'],'1/2')
        self.assertEqual(metrics['pairwise'][0]['maximum_likelihood_ratio'],'3')
        self.assertEqual(metrics['bayes_vulnerability'],'3/4')
        self.assertEqual(metrics['min_entropy_vulnerability_ratio'],'3/2')
        self.assertAlmostEqual(metrics['mutual_information_bits_approx'],0.18872187554086717)

    def test_disjoint_channel_has_infinite_ratio_and_one_bit(self):
        g,k,s=fixture();k['rules']=[{'model':'m','template':'A','outcomes':[{'response':'xx','output_tokens':2,'probability':'1'}]}]
        metrics=analyze(g,k,{},s,1)['metrics']
        self.assertEqual(metrics['pairwise'][0]['total_variation'],'1')
        self.assertTrue(metrics['pairwise'][0]['infinite_likelihood_ratio'])
        self.assertIsNone(metrics['pairwise'][0]['maximum_likelihood_ratio'])
        self.assertEqual(metrics['bayes_vulnerability'],'1')
        self.assertEqual(metrics['min_entropy_leakage_bits_approx'],1)
        self.assertEqual(metrics['mutual_information_bits_approx'],1)

    def test_nonuniform_prior_vulnerability(self):
        g,k,s=fixture();s[0]['prior']='3/4';s[1]['prior']='1/4'
        m=analyze(g,k,{},s,1)['metrics']
        self.assertEqual(m['bayes_vulnerability'],'3/4');self.assertEqual(m['prior_bayes_vulnerability'],'3/4')
        self.assertEqual(m['min_entropy_vulnerability_ratio'],'1')

    def test_single_scenario_cannot_report_vacuous_zero_leakage(self):
        g,k,s=fixture();s[0]['prior']='1'
        with self.assertRaises(ChannelError):analyze(g,k,{},s[:1],1)
        with self.assertRaises(ChannelError):channel_metrics([{'b':Fraction(1)}],[Fraction(1)])

    def test_duplicate_secret_assignments_rejected(self):
        g,k,s=fixture();s[1]['values']=dict(s[0]['values'])
        with self.assertRaises(ChannelError):analyze(g,k,{},s,1)

    def test_prior_mass_and_scenario_schema_fail_closed(self):
        g,k,s=fixture();s[0]['prior']='1/3'
        with self.assertRaises(ChannelError):analyze(g,k,{},s,1)
        g,k,s=fixture();s[0]['values']['extra']=True
        with self.assertRaises(ChannelError):analyze(g,k,{},s,1)

    def test_probability_grammar_and_nonfinite_rejection(self):
        for p in ('01','01/1','1/01','0','0/1','1.0','1e-1','-1/2','2','1/0'):
            g,k,s=fixture();k['defaults']['m'][0]['probability']=p
            with self.subTest(probability=p),self.assertRaises((ChannelError,ValueError)):
                analyze(g,k,{},s,1)

    def test_histogram_metrics_reject_float_or_negative_mass(self):
        with self.assertRaises(ChannelError):channel_metrics([{'b':1.0},{'b':Fraction(1)}],[Fraction(1,2)]*2)
        with self.assertRaises(ChannelError):channel_metrics([{'b':Fraction(1)},{'b':Fraction(1)}],[.5,.5])

    def test_duplicate_support_combines_exactly(self):
        g,k,s=fixture();k['defaults']['m']=[{'response':'x','output_tokens':1,'probability':'1/3'},
                                         {'response':'x','output_tokens':1,'probability':'2/3'}]
        r=producer_histogram(g,k,{'secret':True},1)
        self.assertEqual(len(r['histogram']),1);self.assertEqual(r['mass'],1)

    def test_state_cap_returns_unknown_with_no_histogram_or_metrics(self):
        g,k,s=fixture();r=analyze(g,k,{},s,1,max_states=1)
        self.assertEqual(r['status'],'unknown');self.assertIsNone(r['metrics'])
        self.assertTrue(all(x['histogram']is None and x['mass']is None for x in r['rows']))

    def test_byte_work_cap_boundary_returns_unknown_without_partial_histogram(self):
        g,k,s=fixture();done=producer_histogram(g,k,{'secret':True},1)
        at=producer_histogram(g,k,{'secret':True},1,max_work_bytes=done['work_bytes_estimate'])
        below=producer_histogram(g,k,{'secret':True},1,max_work_bytes=done['work_bytes_estimate']-1)
        self.assertEqual(at['status'],'complete');self.assertEqual(below['status'],'unknown')
        self.assertIsNone(below['histogram']);self.assertIsNone(below['mass'])

    def test_horizon_continues_control_to_stop_or_next_call(self):
        g,k,s=fixture();g['states']['left']['next']={'kind':'goto','target':'done'}
        g['states']['done']={'calls':[],'next':{'kind':'stop'}}
        done=producer_histogram(g,k,{'secret':True},1)
        self.assertTrue(json.loads(next(iter(done['histogram'])))['stopped'])
        g['states']['left']['next']={'kind':'goto','target':'left'}
        prefix=producer_histogram(g,k,{'secret':True},1)
        self.assertFalse(json.loads(next(iter(prefix['histogram'])))['stopped'])

    def test_trace_observer_omits_requests_responses_and_keeps_order(self):
        g,k,s=fixture();r=producer_histogram(g,k,{'secret':True},1,observer='trace')
        obs=json.loads(next(iter(r['histogram'])))
        self.assertEqual(set(obs),{'stopped','usage_trace'})
        self.assertEqual(set(obs['usage_trace'][0]),{'contract','input_tokens','output_tokens'})

    def test_json_api_rejects_non_string_keys_before_coercion(self):
        g,k,s=fixture();k['defaults'][1]=k['defaults'].pop('m')
        with self.assertRaises(ChannelError):analyze(g,k,{},s,1)

    def test_cli_binds_exact_inputs_and_rejects_duplicate_json(self):
        g,k,s=fixture()
        with tempfile.TemporaryDirectory()as d:
            gp=Path(d)/'g.json';kp=Path(d)/'k.json';report=Path(d)/'report.json'
            gp.write_text(json.dumps(g));kp.write_text(json.dumps(k))
            cmd=[sys.executable,str(Path(__file__).with_name('probabilistic_channels.py')),str(gp),str(kp),
                 '--public-json','{}','--scenarios-json',json.dumps(s),'--horizon','1','--report',str(report)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            evidence=json.loads(report.read_text())
            self.assertEqual(evidence['secret_scenarios'],s)
            self.assertEqual(evidence['secret_scenarios_sha256'],hashlib.sha256(canonical(s).encode()).hexdigest())
            cmd[cmd.index('{}')]='{"extra":1,"extra":2}'
            self.assertEqual(subprocess.run(cmd,capture_output=True,text=True).returncode,1)

if __name__=='__main__':unittest.main()
