"""Exhaustive development precision census for verified algebraic rewrites.

The frozen historical corpus is rerun separately. This campaign is an authored
grammar, not an external workload or an estimate of real-program acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.dataflow_gate import (normalize, syntactic_normalize, read_source, reference_program)
from runtime.finite_reference import Reference, canonical
from runtime.replay_adapter import Replay, enumerate_replay
from scripts.check_dataflow import contract, lean_kernels, lean_trace, reference_trace, replay_trace
from scripts.dataflow_certificate import run_checker


def shapes(pipeline):
    empty=['skip']
    redundant=['public',0,pipeline,pipeline]
    idle=['public',0,empty,empty]
    trailing=['seq',pipeline[1],['seq',pipeline[2],idle]]
    return [pipeline, redundant, ['seq',idle,pipeline], trailing,
            ['public',0,['public',1,pipeline,pipeline],pipeline],
            ['seq',idle,['seq',redundant,idle]],
            ['public',0,pipeline,['public',1,pipeline,pipeline]],
            ['public',1,['seq',idle,pipeline],trailing]]


def source_shapes(pipeline):
    redundant='if flag {'+pipeline+'} else {'+pipeline+'}'
    idle='if flag {} else {}'
    return [pipeline, redundant, idle+pipeline, pipeline+idle,
            'if flag {if other {'+pipeline+'} else {'+pipeline+'}} else {'+pipeline+'}',
            idle+redundant+idle,
            'if flag {'+pipeline+'} else {if other {'+pipeline+'} else {'+pipeline+'}}',
            'if other {'+idle+pipeline+'} else {'+pipeline+idle+'}']


def request_terms():
    literal=lambda s:['literal',s]
    append=lambda a,b:['append',a,b]
    v=['var',1]
    base=append(literal('Next:'),v)
    return [base,append(literal(''),base),append(base,literal('')),
            append(append(literal('Ne'),literal('xt:')),v),
            append(literal('N'),append(literal('ext:'),v)),
            append(append(literal(''),literal('Next:')),append(v,literal(''))),
            append(append(literal('Next:'),literal('')),v),
            append(literal('Next:'),append(literal(''),v))]


def trace_with_requests(paths):
    return replay_trace(paths)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lean',required=True,type=Path)
    p.add_argument('--orchc',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    failures=[]
    write('manifest.json',dict(status='running'))
    protocol=dict(purpose='authored-development-grammar; not external workflows',
                  source_shapes=8,source_positive_pairs=64,source_negative_pairs=16,
                  core_request_shapes=8,core_positive_pairs=64,core_negative_pairs=8,
                  public_texts=['','a','é'],public_flags=[False,True],secret_flags=[False,True],
                  baseline='historical syntactic_normalize on identical core/assumptions',
                  expected_source_cases=80,expected_core_cases=72,
                  request_gain_scope='core only; source templates already fold adjacent literals',
                  units='UTF-8 bytes; independent of C++ mock tokenizer')
    write('protocol.json',protocol)
    c=contract('precision-v1',8)
    other=contract('precision-other',8)
    key,other_key=canonical(c),canonical(other)
    contracts={key:c,other_key:other}
    kernels={k:{'Seed:'+value:[dict(text='',p='1/2',status='ok'),dict(text='é',p='1/2',status='error')]
                for value in protocol['public_texts']} for k in contracts}
    for k in contracts:
        for request in ('Next:','Next:é','Next:a','Other:','Other:é','Next;','Next;é'):
            kernels[k][request]=[dict(text='x' if request.startswith('Next:') else 'xxx',p='1',status='ok')]
    first=['call',1,key,['append',['literal','Seed:'],['var',0]]]
    def pipeline(term=None,contract_key=key):
        return ['seq',first,['call',2,contract_key,term or request_terms()[0]]]
    source_call='let a:text=call start(x) using m; let b:text=call next(a) using m;'
    source_arms=source_shapes(source_call)
    sources=[]
    for left,right in itertools.product(range(8),repeat=2):
        sources.append(dict(label=f'shape-{left}-{right}',positive=True,
                            program=['secret',0,shapes(pipeline())[left],shapes(pipeline())[right]],
                            left=source_arms[left],right=source_arms[right],other_model=False))
    for left in range(8):
        for category in ('request','contract'):
            different=(['append',['literal','Other:'],['var',1]] if category=='request' else None)
            bad=pipeline(different,other_key if category=='contract' else key)
            right=source_call.replace('call next(a)','call different(a)') if category=='request' else source_call.replace('using m','using n')
            # The contract-negative changes both calls; construct that expected core explicitly.
            if category=='contract':
                bad=['seq',['call',1,other_key,first[3]],['call',2,other_key,request_terms()[0]]]
            sources.append(dict(label=f'negative-{category}-{left}',positive=False,
                                program=['secret',0,shapes(pipeline())[left],bad],
                                left=source_arms[left],right=right,other_model=category=='contract'))
    cores=[]
    terms=request_terms()
    for left,right in itertools.product(range(8),repeat=2):
        cores.append(dict(label=f'request-{left}-{right}',positive=True,
                          program=['secret',0,pipeline(terms[left]),pipeline(terms[right])]))
    for index in range(8):
        bad=(['append',['literal','Next;'],['var',1]] if index%2==0
             else ['append',['literal','Next:'],['var',0]])
        cores.append(dict(label=f'negative-request-{index}',positive=False,
                          program=['secret',0,pipeline(terms[index]),pipeline(bad)]))
    cases=[]
    rows=[]
    ctx_records=[]
    source_dir=args.output/'sources'
    source_dir.mkdir()
    try:
        for kind,groups in (('source',sources),('core',cores)):
            for entry in groups:
                program=entry['program']
                cpp=None
                if kind=='source':
                    source=('workflow Precision budget 10000 { input x:text max_tokens 64; '
                            'input flag:boolean max_tokens 1; input other:boolean max_tokens 1; '
                            'secret s:boolean max_tokens 1; model m=mock("precision-v1") max_tokens 8; '
                            'model n=mock("precision-other") max_tokens 8; '
                            'prompt start(t:text)->text="Seed:{t}"; prompt next(t:text)->text="Next:{t}"; '
                            'prompt different(t:text)->text="Other:{t}"; '
                            'if s {'+entry['left']+'} else {'+entry['right']+'} output "done"; }\n')
                    path=source_dir/(entry['label']+'.orch')
                    path.write_text(source,encoding='utf-8',newline='\n')
                    parsed=read_source(source.encode('utf-8'))
                    if parsed['program']!=program:
                        failures.append('reader reconstruction '+entry['label'])
                    run=subprocess.run([str(args.orchc.resolve()),'check',str(path.resolve())],cwd=ROOT,
                                       capture_output=True,text=True,encoding='utf-8',timeout=30)
                    cpp=dict(exit=run.returncode,stdout=run.stdout,stderr=run.stderr,
                             diagnostics=re.findall(r'error \[([A-Z]\d+)\]',run.stderr))
                    if run.returncode not in (0,1) or (run.returncode==1 and not cpp['diagnostics']):
                        failures.append('C++ infrastructure '+entry['label'])
                plan=normalize(program)
                baseline=syntactic_normalize(program) is not None
                accepted=plan is not None
                if accepted!=entry['positive']:
                    failures.append('unexpected acceptance '+entry['label'])
                executions=[]
                context_observations=[]
                for value,flag,other_flag,secret in itertools.product(protocol['public_texts'],(False,True),(False,True),(False,True)):
                    env={'v0':value,'public0':flag,'public1':other_flag,'secret0':secret}
                    ref=Reference(contracts,kernels).run(reference_program(program),env)
                    replay=enumerate_replay(Replay(contracts,kernels),reference_program(program),env)
                    ptrace=replay_trace(replay)
                    projected=Counter()
                    for (trace,requests),weight in ptrace.items():
                        projected[trace]+=weight
                    if dict(projected)!=reference_trace(ref):
                        failures.append('reference/replay '+entry['label'])
                    context_observations.append(ptrace)
                    ctx_records.append(dict(kind=kind,label=entry['label'],value=value,flag=flag,other=other_flag,
                                            secret=secret,reference=[dict(trace=t,p=str(w)) for t,w in reference_trace(ref).items()],
                                            replay=[dict(trace=t,requests=r,p=str(w)) for (t,r),w in ptrace.items()]))
                    executions.append(dict(public=[flag,other_flag],secret=[secret],store=[value],
                                           observe_slots=3,kernels=lean_kernels(kernels)))
                equivalent=all(a==b for a,b in zip(context_observations[::2],context_observations[1::2]))
                if accepted and not equivalent:
                    failures.append('accepted counterexample '+entry['label'])
                if not entry['positive'] and equivalent:
                    failures.append('negative case did not separate '+entry['label'])
                rows.append(dict(kind=kind,label=entry['label'],program=program,plan=plan,
                                 baseline_accepted=baseline,accepted=accepted,finite_equal=equivalent,cpp=cpp))
                cases.append(dict(program=program,execute=executions))
        write('programs.json',rows)
        write('contexts.json',ctx_records)
        write('lean-input.json',cases)
        results,_=run_checker(args.lean.resolve(),cases,args.output.resolve(),record_prefix='decision-lean',decision=True)
        write('lean-output.json',results)
        cursor=0
        for row,result in zip(rows,results):
            if result['checked']!=row['accepted']:
                failures.append('Lean decision '+row['label'])
            for runs in result['executions']:
                ctx=ctx_records[cursor]
                cursor+=1
                ref={tuple(tuple(e) for e in v['trace']):Fraction(v['p']) for v in ctx['reference']}
                replay={(tuple(tuple(e) for e in v['trace']),tuple(v['requests'])):Fraction(v['p']) for v in ctx['replay']}
                if lean_trace(runs)!=ref:
                    failures.append('Lean/reference '+row['label'])
                if lean_trace(runs,True)!=replay:
                    failures.append('Lean/replay '+row['label'])
        if cursor!=len(ctx_records):
            failures.append('incomplete Lean contexts')
        # Retain the exact historical eight policy differences, including source.
        historical_path=ROOT/'research/validated-2026-10-24/dataflow-v5/programs.json'
        historical=json.loads(historical_path.read_text(encoding='utf-8'))
        differences=[]
        for row in historical:
            if row['accepted']!=(row['cpp_exit']==0):
                differences.append(dict(id=row['id'],left=row['left'],right=row['right'],
                                        source=row['source'],cpp_diagnostics=row['cpp_diagnostics'],
                                        cpp_stderr=row['cpp_stderr'],lean_accepted=row['accepted'],
                                        interpretation='C++ PC taints response; downstream prompt violates IFC E230. Lean checks matched resource distributions under secret-Boolean/shared-kernel model.'))
        write('historical-policy-differences.json',dict(input_sha256=hashlib.sha256(historical_path.read_bytes()).hexdigest(),cases=differences))
        if len(differences)!=8 or any(set(row['cpp_diagnostics'])!={'E230'} for row in differences):
            failures.append('historical difference audit drift')
    except Exception as error:
        write('manifest.json',dict(status='failed',infrastructure_error=str(error),failures=failures))
        raise
    files=['proof/DataflowCore.lean','runtime/dataflow_gate.py','scripts/dataflow_certificate.py',
           'scripts/check_dataflow_precision.py','runtime/finite_reference.py','runtime/replay_adapter.py']
    counts={kind:dict(cases=sum(r['kind']==kind for r in rows),
                      baseline_accepted=sum(r['kind']==kind and r['baseline_accepted'] for r in rows),
                      accepted=sum(r['kind']==kind and r['accepted'] for r in rows),
                      gained=sum(r['kind']==kind and r['accepted'] and not r['baseline_accepted'] for r in rows),
                      rejected=sum(r['kind']==kind and not r['accepted'] for r in rows)) for kind in ('source','core')}
    manifest=dict(status='failed' if failures else 'completed',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  dirty_tree=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
                  files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                  executable_sha256=hashlib.sha256(args.orchc.read_bytes()).hexdigest(),counts=counts,
                  execution_contexts=len(ctx_records),historical_policy_differences=len(differences),
                  accepted_finite_counterexamples=sum(r['accepted'] and not r['finite_equal'] for r in rows),
                  failures=failures,spent_usd='0.00',provider_inference=False)
    write('manifest.json',manifest)
    print(json.dumps(manifest,indent=2))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
