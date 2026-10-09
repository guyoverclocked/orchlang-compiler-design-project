#!/usr/bin/env python3
"""Controlled exact-usage channel study; synthetic kernels, no provider calls.

Compares a state-merging DP with an independent no-merge exhaustive DFS.
All cases are authored semantic tests, not held-out real-world measurements.
"""
from __future__ import annotations
from fractions import Fraction
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time
from orchgraph import Graph,check
from probabilistic_channels import analyze,canonical,producer_histogram,serialize
from probabilistic_reference import independent_histogram

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=[{'values':{'secret':False},'prior':'1/2'},{'values':{'secret':True},'prior':'1/2'}]


def call(template,result='r',args=(),model='m'):
    return {'model':model,'template':template,'arguments':list(args),'result':result}

def outcome(response,usage,p='1'):
    return {'response':response,'output_tokens':usage,'probability':str(p)}

def kernel(default=None,rules=(),window=0):
    return {'format':'orchlang-finite-outcome-kernel','version':1,'history_window':window,
            'defaults':{'m':default or [outcome('x',1)]},'rules':list(rules)}

def graph(name,left,right,*,left_next=None,right_next=None,extras=None,registers=None,inputs=None):
    return {'format':'orchlang-request-graph','version':1,'name':name,'chars_per_token':1,
            'inputs':{'secret':{'type':'boolean','label':'secret'},**(inputs or {})},
            'models':{'m':{'provider':'offline','model':'finite-worker','max_tokens':8}},
            'registers':registers or {'r':{'model':'m'}},'entry':'choose','states':{
            'choose':{'calls':[],'next':{'kind':'secret','guard':{'value':'secret'},'then':'left','else':'right'}},
            'left':{'calls':left,'next':left_next or {'kind':'stop'}},
            'right':{'calls':right,'next':right_next or {'kind':'stop'}},**(extras or {})}}

def rule(t,outcomes,**conditions):return {'model':'m','template':t,'outcomes':outcomes,**conditions}


def cases():
    bernoulli=[outcome('x',1,'1/2'),outcome('xx',2,'1/2')]
    result=[]
    g=graph('equivalent_dependent_chain',[call('Q','a'),call('R','r',[{'value':'a'}])],
            [call('Q','b'),call('R','r',[{'value':'b'}])],registers={v:{'model':'m'}for v in ('a','b','r')})
    result.append((g,kernel(bernoulli),{},'accepted'))
    result.append((graph('different_requests_equal_usage',[call('A')],[call('B')]),kernel(bernoulli),{},'rejected'))
    biased=[rule(t,[outcome('x',1,p),outcome('xx',2,1-p)])for t,p in [('A',Fraction(3,4)),('B',Fraction(1,4))]]
    result.append((graph('noisy_usage_bit',[call('A')],[call('B')]),kernel(rules=biased),{},'rejected'))
    result.append((graph('same_mean_distinct_laws',[call('A')],[call('B')]),kernel(rules=[
        rule('A',[outcome('x',1,'1/2'),outcome('xxx',3,'1/2')]),rule('B',[outcome('xx',2)])]),{},'rejected'))
    result.append((graph('aggregate_hides_order',[call('A'),call('A')],[call('B'),call('B')]),kernel(rules=[
        rule('A',[outcome('x',1)],ordinal=0),rule('A',[outcome('xxx',3)],ordinal=1),
        rule('B',[outcome('xxx',3)],ordinal=0),rule('B',[outcome('x',1)],ordinal=1)]),{},'rejected'))
    contract=Graph(g).models['m']
    event=lambda t,response:{'contract':contract,'ordinal':0,'template':t,'arguments':[],
                             'response':response,'input_tokens':1,'output_tokens':1}
    result.append((graph('history_conditioned_usage',[call('A'),call('C')],[call('B'),call('C')]),kernel(window=1,rules=[
        rule('A',[outcome('a',1)]),rule('B',[outcome('b',1)]),
        rule('C',[outcome('x',1)],history=[event('A','a')]),
        rule('C',[outcome('xxx',3)],history=[event('B','b')])]),{},'rejected'))
    guard=lambda state:{'kind':'public','guard':{'value':'r','op':'<=','limit':1},'then':state,'else':'done'}
    result.append((graph('biased_productive_cycle',[call('A')],[call('B')],left_next=guard('left'),right_next=guard('right'),
        extras={'done':{'calls':[],'next':{'kind':'stop'}}}),kernel(rules=biased),{},'rejected'))
    fixed=graph('fixed_public_context',[call('Q','r',[{'value':'q'}])],[call('Q','r',[{'literal':'q'}])],
                inputs={'q':{'type':'text','label':'public','max_tokens':8}})
    result.append((fixed,kernel(bernoulli),{'q':'q'},'rejected'))
    changed=copy.deepcopy(fixed);changed['name']='changed_public_context'
    result.append((changed,kernel(bernoulli),{'q':'qq'},'rejected'))
    loop=graph('merge_stress_productive_cycle',[],[],left_next={'kind':'goto','target':'loop'},right_next={'kind':'goto','target':'loop'},
               extras={'loop':{'calls':[call('Q')],'next':{'kind':'goto','target':'loop'}}})
    result.append((loop,kernel([outcome('a',1,'1/2'),outcome('b',1,'1/2')]),{},'accepted'))
    alias=copy.deepcopy(g);alias['name']='canonical_alias_chain';alias['models']['alias']=copy.deepcopy(alias['models']['m'])
    for c in alias['states']['right']['calls']:c['model']='alias'
    result.append((alias,kernel(bernoulli),{},'accepted'))
    return result


def expected_totals(histogram):
    totals={}
    for observation,p in histogram.items():
        obs=json.loads(observation)
        if 'billing'in obs:
            events=obs['billing']
            rows=[(canonical(e['contract']),e['call_count'],e['input_tokens'],e['output_tokens'])for e in events]
        else:
            rows=[(canonical(e['contract']),1,e['input_tokens'],e['output_tokens'])for e in obs['usage_trace']]
        for identity,n,i,o in rows:
            current=totals.setdefault(identity,[Fraction(0)]*3)
            for j,x in enumerate((n,i,o)):current[j]+=p*x
    # Canonical include zero contracts only in aggregate; add zero rows in trace comparison callers.
    return totals


def main():
    target=ROOT/'examples/channels';out=ROOT/'bench/results/probabilistic_channels'
    target.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    report={'format':'orchlang-controlled-finite-usage-study','version':1,
            'scope':'authored synthetic finite success-only kernels; no provider distribution fitting, currency, errors or infinite-horizon analysis',
            'producer_sha256':hashlib.sha256((ROOT/'audit/probabilistic_channels.py').read_bytes()).hexdigest(),
            'reference_sha256':hashlib.sha256((ROOT/'audit/probabilistic_reference.py').read_bytes()).hexdigest(),
            'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'rows':[],'fixtures':[],'failures':[]}
    summary={'fixtures':0,'accepted_structurally':0,'rejected_structurally':0,'channel_analyses':0,
             'histogram_comparisons':0,'exact_unit_mass_rows':0,'different_histograms':0,
             'aggregate_zero_channels':0,'trace_zero_channels':0,'mean_equal_but_positive_tv_analyses':0,
             'unknown_resource_probes':0,'dp_call_transitions':0,'dfs_call_transitions':0,'dfs_leaf_paths':0}
    for g,k,public,expected_status in cases():
        name=g['name'];gp=target/(name+'.graph.json');kp=target/(name+'.kernel.json')
        gp.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n');kp.write_text(json.dumps(k,ensure_ascii=False,indent=2)+'\n')
        structural=check(Graph(g));status=structural['status'];summary['fixtures']+=1
        summary[status+'_structurally']+=1
        if status!=expected_status:report['failures'].append(name+': unexpected structural status '+status)
        bindings={'graph':str(gp.relative_to(ROOT)),'kernel':str(kp.relative_to(ROOT)),
                  'source_sha256':hashlib.sha256(gp.read_bytes()).hexdigest(),'kernel_sha256':hashlib.sha256(kp.read_bytes()).hexdigest()}
        report['fixtures'].append({'name':name,'structural_status':status,**bindings})
        horizons=range(1,7)if name!='merge_stress_productive_cycle'else (1,2,4,8,12)
        for h in horizons:
            laws={}
            for observer in ('aggregate','trace'):
                started=time.perf_counter();channel=analyze(g,k,public,SCENARIOS,h,observer=observer,max_work_bytes=1024**3)
                elapsed=time.perf_counter()-started
                if channel['status']!='complete':report['failures'].append(name+': DP unknown');continue
                summary['channel_analyses']+=1
                summaries=[]
                for index,scenario in enumerate(SCENARIOS):
                    r=channel['rows'][index];start=time.perf_counter()
                    ref=independent_histogram(g,k,{**public,**scenario['values']},h,observer=observer,max_work_bytes=1024**3)
                    ref_elapsed=time.perf_counter()-start
                    summary['histogram_comparisons']+=1
                    equal=ref['status']=='complete'and ref['histogram']==r['histogram']and ref['mass']==r['mass']==1
                    if not equal:summary['different_histograms']+=1;report['failures'].append(name+': DP/DFS mismatch')
                    else:summary['exact_unit_mass_rows']+=1
                    summary['dp_call_transitions']+=r['call_transitions'];summary['dfs_call_transitions']+=ref['call_transitions']
                    summary['dfs_leaf_paths']+=ref.get('leaf_paths',0)
                    summaries.append({'scenario_index':index,'histogram_equal':equal,'dp_state_visits':r['state_visits'],
                                      'dp_transitions':r['call_transitions'],'dfs_leaf_paths':ref.get('leaf_paths'),
                                      'dfs_transitions':ref['call_transitions'],'dfs_seconds_advisory':ref_elapsed,
                                      'dp_work_bytes_estimate':r['work_bytes_estimate'],'dfs_work_bytes':ref.get('work_bytes')})
                metrics=channel['metrics'];zero=metrics['all_pairwise_observation_laws_equal']
                if zero:summary[observer+'_zero_channels']+=1
                mean_equal=expected_totals(channel['rows'][0]['histogram'])==expected_totals(channel['rows'][1]['histogram'])
                if mean_equal and not zero:summary['mean_equal_but_positive_tv_analyses']+=1
                evidence=serialize(channel)
                evidence.update(format='orchlang-finite-usage-channel',version=1,**{key:bindings[key]for key in ('source_sha256','kernel_sha256')},
                                analyzer_sha256=report['producer_sha256'],
                                public_store_sha256=hashlib.sha256(canonical(public).encode()).hexdigest(),
                                secret_scenarios_sha256=hashlib.sha256(canonical(SCENARIOS).encode()).hexdigest(),
                                max_states=100000,max_work_bytes=1024**3,
                                rule_precedence='first matching rule in supplied order, otherwise resolved-contract default',scope=report['scope'])
                ep=out/(name+'.h'+str(h)+'.'+observer+'.json');ep.write_text(json.dumps(evidence,indent=2)+'\n')
                tv=Fraction(metrics['pairwise'][0]['total_variation']);laws[observer]=tv
                report['rows'].append({'name':name,'horizon':h,'observer':observer,'structural_status':status,
                                       'total_variation':str(tv),'mean_usage_vectors_equal':mean_equal,
                                       'bayes_vulnerability':metrics['bayes_vulnerability'],
                                       'mutual_information_bits_approx':metrics['mutual_information_bits_approx'],
                                       'evidence':str(ep.relative_to(ROOT)),'evidence_sha256':hashlib.sha256(ep.read_bytes()).hexdigest(),
                                       'dp_seconds_advisory':elapsed,'comparisons':summaries})
            if laws['aggregate']>laws['trace']:report['failures'].append(name+': coarsening TV increased')
        unknown=analyze(g,k,public,SCENARIOS,1,max_states=1)
        if unknown['status']=='unknown'and unknown['metrics']is None and all(r['histogram']is None for r in unknown['rows']):
            summary['unknown_resource_probes']+=1
        else:report['failures'].append(name+': resource cap did not fail closed')
    # Hand-derived feature checks are independent of the enumerator comparisons.
    def tv(name,h,observer='aggregate'):
        return next(r['total_variation']for r in report['rows']if r['name']==name and r['horizon']==h and r['observer']==observer)
    for name,h,obs,expected in [('different_requests_equal_usage',1,'aggregate','0'),('noisy_usage_bit',1,'aggregate','1/2'),
        ('same_mean_distinct_laws',1,'aggregate','1'),('aggregate_hides_order',2,'aggregate','0'),
        ('aggregate_hides_order',2,'trace','1'),('history_conditioned_usage',2,'aggregate','1'),
        ('fixed_public_context',1,'aggregate','0'),('changed_public_context',1,'aggregate','1')]:
        if tv(name,h,obs)!=expected:report['failures'].append('hand-derived TV failed: '+name)
    report['summary']=summary;report['status']='passed'if not report['failures']else'failed'
    (ROOT/'bench/results/probabilistic_channels.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'summary':summary,'status':report['status'],'failures':report['failures']},indent=2))
    return 0 if not report['failures']else 1

if __name__=='__main__':sys.exit(main())
