#!/usr/bin/env python3
"""Freeze cyclic-checker fixtures, certificate replay and finite trace probes."""
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys

from orchgraph import Graph, InvalidGraph, check, reference_run, strict_json
from replay_graph_certificate import replay

ROOT=Path(__file__).resolve().parents[1]
SEEDS=range(1,26)
TEXTS=['','short public question','é漢 UTF8 public text','PUBLIC'*12]
MAX_CALLS=120


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def billing_vector(run):
    """Finite-prefix usage grouped by the exact resolved model contract."""
    groups={}
    for event in run['trace']:
        identity=json.dumps(event['contract'],sort_keys=True,separators=(',',':'))
        if identity not in groups:
            groups[identity]={'contract':event['contract'],'call_count':0,'input_tokens':0,'output_tokens':0}
        group=groups[identity]
        group['call_count']+=1
        group['input_tokens']+=event['input_tokens'];group['output_tokens']+=event['output_tokens']
    return [groups[identity] for identity in sorted(groups)]


def requests(run):
    return [(e['contract'],e['ordinal'],e['template'],e['arguments']) for e in run['trace']]


def main():
    manifest=json.loads((ROOT/'examples/graphs/manifest.json').read_text())
    totals={'accepted':0,'rejected':0,'invalid':0,'replayed_certificates':0,
            'accepted_reference_runs':0,'accepted_secret_comparisons':0,'accepted_mismatches':0,
            'accepted_request_mismatches':0,'accepted_billing_mismatches':0,
            'accepted_call_accounting_checks':0,'rejected_secret_comparisons':0,
            'rejections_with_finite_witness':0,'rejections_without_finite_witness':0,
            'rejections_with_billing_witness':0,'rejections_without_billing_witness':0}
    rows=[];failures=[]
    for fixture in manifest:
        path=ROOT/fixture['path'];raw=path.read_bytes()
        row={'path':fixture['path'],'source_sha256':sha(path),'expected':fixture['expected']}
        try:graph=Graph(strict_json(raw))
        except InvalidGraph as error:
            row.update(status='invalid',diagnostic=str(error));totals['invalid']+=1
            if fixture['expected']!='invalid' or fixture['diagnostic'] not in str(error):failures.append(fixture['path']+': unexpected invalid graph')
            rows.append(row);continue
        report=check(graph);report['source_sha256']=sha(path);report['checker_sha256']=sha(ROOT/'audit/orchgraph.py')
        row.update(status=report['status'],product_nodes=len(report['nodes']),product_edges=report.get('product_edges'),
                   diagnostic=report.get('diagnostic'))
        if fixture['expected']=='accepted' and report['status']!='accepted':failures.append(fixture['path']+': unexpected rejection')
        if fixture['expected']=='rejected' and (report['status']!='rejected' or fixture['diagnostic'] not in report.get('diagnostic','')):
            failures.append(fixture['path']+': expected distinguishing obligation absent')
        if report['status']=='accepted':
            totals['accepted']+=1
            destination=ROOT/'bench/results/graph_certificates'/path.name
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            try:
                attestation=replay(raw,json.dumps(report,ensure_ascii=False).encode('utf-8'));totals['replayed_certificates']+=1
                row['independent_replay']=attestation
            except ValueError as error:failures.append(fixture['path']+': replay failed: '+str(error))
        else:totals['rejected']+=1
        secrets=[v for v,d in graph.inputs.items() if d['label']=='secret']
        if any(graph.inputs[s]['type']!='boolean' for s in secrets):raise ValueError('this finite probe grid expects Boolean secrets')
        assignments=list(itertools.product((False,True),repeat=len(secrets)))
        first_witness=first_billing_witness=None
        comparisons=mismatches=request_mismatches=billing_mismatches=0;calls=0;truncated_runs=0
        for seed in SEEDS:
            for text in TEXTS:
                public={v:(False if d['type']=='boolean' else text+' second' if v=='query2' else text)
                        for v,d in graph.inputs.items() if d['label']=='public'}
                runs=[]
                for assignment in assignments:
                    store={**public,**dict(zip(secrets,assignment))}
                    observation=reference_run(graph,store,seed,MAX_CALLS)
                    runs.append(observation);calls+=len(observation['trace'])
                    truncated_runs+=int(not observation['stopped'])
                    if report['status']=='accepted':
                        totals['accepted_reference_runs']+=1
                        for event in observation['trace']:
                            # Concrete full response/request values satisfy the
                            # declared graph's abstract accounting contracts.
                            if event['output_tokens']>event['contract']['max_tokens']:
                                failures.append(fixture['path']+': oracle cap exceeded')
                            if event['input_tokens']!=graph.estimate(event['template'])+sum(graph.estimate(a) for a in event['arguments']):
                                failures.append(fixture['path']+': request accounting disagreement')
                            totals['accepted_call_accounting_checks']+=1
                for index,other in enumerate(runs[1:],1):
                    comparisons+=1;different=other!=runs[0];mismatches+=int(different)
                    request_mismatches+=int(requests(other)!=requests(runs[0]))
                    left_billing,right_billing=billing_vector(runs[0]),billing_vector(other)
                    bill_different=left_billing!=right_billing;billing_mismatches+=int(bill_different)
                    if bill_different and first_billing_witness is None:
                        first_billing_witness={'seed':seed,'public_text':text,
                            'secret_left':dict(zip(secrets,assignments[0])),
                            'secret_right':dict(zip(secrets,assignments[index])),
                            'left_stopped':runs[0]['stopped'],'right_stopped':other['stopped'],
                            'left_billing':left_billing,'right_billing':right_billing,
                            'observation_horizon':'complete run if stopped; otherwise prefix of at most 120 calls'}
                    if different and first_witness is None:
                        first_witness={'seed':seed,'public_text':text,
                            'secret_left':dict(zip(secrets,assignments[0])),
                            'secret_right':dict(zip(secrets,assignments[index])),
                            'left_stopped':runs[0]['stopped'],'right_stopped':other['stopped'],
                            'left_call_count':len(runs[0]['trace']),'right_call_count':len(other['trace'])}
                        first=next((i for i,(a,b) in enumerate(zip(runs[0]['trace'],other['trace'])) if a!=b),
                                   min(len(runs[0]['trace']),len(other['trace'])))
                        first_witness['first_differing_event_index']=first
                        first_witness['left_event']=runs[0]['trace'][first] if first<len(runs[0]['trace']) else None
                        first_witness['right_event']=other['trace'][first] if first<len(other['trace']) else None
        row.update(comparisons=comparisons,mismatches=mismatches,request_mismatches=request_mismatches,
                   billing_mismatches=billing_mismatches,calls=calls,truncated_runs=truncated_runs,
                   first_witness=first_witness,first_billing_witness=first_billing_witness)
        if report['status']=='accepted':
            totals['accepted_secret_comparisons']+=comparisons;totals['accepted_mismatches']+=mismatches
            totals['accepted_request_mismatches']+=request_mismatches
            totals['accepted_billing_mismatches']+=billing_mismatches
            if mismatches:failures.append(fixture['path']+': accepted traces/usage/stop disagreed')
        else:
            totals['rejected_secret_comparisons']+=comparisons
            totals['rejections_with_finite_witness']+=int(first_witness is not None)
            totals['rejections_without_finite_witness']+=int(first_witness is None)
            totals['rejections_with_billing_witness']+=int(first_billing_witness is not None)
            totals['rejections_without_billing_witness']+=int(first_billing_witness is None)
        rows.append(row)
    if (totals['accepted'],totals['rejected'],totals['invalid'],totals['replayed_certificates'])!=(6,8,3,6):
        failures.append('development graph/replay corpus incomplete')
    result={'experiment':'17 authored graph fixtures, independent closure replay, finite shared-oracle full-text probes',
            'scope':'6 accepted / 8 rejected / 3 invalid; no external graph ports or mechanized metatheory',
            'grid':{'seeds':[1,25],'public_texts':TEXTS,'max_calls':MAX_CALLS,
                    'secrets':'all Boolean assignments; compare each with first per fixed public/seed slice'},
            'environment':{'platform':platform.platform(),'python':platform.python_version(),
                           'checker_sha256':sha(ROOT/'audit/orchgraph.py'),
                           'replayer_sha256':sha(ROOT/'audit/replay_graph_certificate.py'),
                           'generator_sha256':sha(ROOT/'audit/generate_graph_examples.py'),
                           'evaluator_sha256':sha(Path(__file__))},
            'totals':totals,'fixtures':rows,'failures':failures,
            'limits':['producer and reference value probe share schema code; replay implementation is separate',
                      'finite sampled executions do not prove the coinductive theorem',
                      'billing vectors are complete-run observations only for stopped runs; otherwise finite-prefix observations',
                      'unwitnessed rejections are unknown in this grid, not proved false positives',
                      'billable cycles may run forever; no finite whole-execution budget']}
    destination=ROOT/'bench/results/graphs.json'
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'totals':totals,'failures':failures},indent=2))
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
