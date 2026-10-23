"""Frozen development comparison: source reconstruction and three text semantics."""
import argparse
import copy
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
from runtime.dataflow_gate import read_source, issue, bind_certificate, normalize, reference_program
from runtime.finite_reference import Reference, canonical, distribution, Unsupported
from runtime.replay_adapter import Replay, enumerate_replay
from scripts.dataflow_certificate import run_checker


def contract(revision,cap):
    return dict(provider='finite-replay',revision=revision,tokenizer='utf8-bytes-v1',
                serializer='raw-utf8-v1',cap=cap,sampling='explicit-table',error_policy='status-in-outcome',
                accounting='all-attempts-input-and-output',state='stateless')


def pair(a,b):
    return ['seq',a,b]


def arm(variant,side):
    revision,cap,first,second=variant
    key=canonical(contract(revision,cap))
    # Independently constructed from the declared grammar, not the source reader.
    first_expr=['append',['literal','Seed:'],['var',0]] if first=='public-input' else ['literal','Seed:fixed']
    second_expr=['append',['literal','Next:'],['var',1]] if second=='response' else ['literal','Next:constant']
    core=pair(['call',1,key,first_expr],['call',2,key,second_expr])
    first_params='t:text' if first=='public-input' else ''
    first_argument='x' if first=='public-input' else ''
    second_params='t:text' if second=='response' else ''
    second_argument=f'first_{side}' if second=='response' else ''
    source=(f'model {side} = mock("{revision}") max_tokens {cap}; '
            f'prompt start_{side}({first_params})->text="'+('Seed:{t}' if first=='public-input' else 'Seed:fixed')+'"; '
            f'prompt next_{side}({second_params})->text="'+('Next:{t}' if second=='response' else 'Next:constant')+'"; '
            f'let first_{side}:text=call start_{side}({first_argument}) using {side}; '
            f'let second_{side}:text=call next_{side}({second_argument}) using {side};')
    return core,source


def kernels_for(contracts,texts):
    result={}
    for key in contracts:
        rows={
            'Seed:fixed':[dict(text='z',p='1',status='ok')],
            'Next:':[dict(text='ok',p='1',status='ok')],
            'Next:é':[dict(text='xxx',p='1',status='ok')],
            'Next:z':[dict(text='go',p='1',status='ok')],
            'Next:constant':[dict(text='',p='1/2',status='ok'),dict(text='x',p='1/2',status='error')]}
        for value in texts:
            rows['Seed:'+value]=[dict(text='',p='1/2',status='ok'),dict(text='é',p='1/2',status='error')]
            rows['Tail:'+value]=[dict(text='t',p='1',status='ok')]
        result[key]=rows
    return result


def lean_kernels(kernels):
    return [[c,r,[[o['text'],o['status']=='error',Fraction(o['p']).numerator,Fraction(o['p']).denominator]
                  for o in outcomes]] for c,table in sorted(kernels.items()) for r,outcomes in sorted(table.items())]


def reference_trace(paths):
    result=Counter()
    for state,p in paths:
        result[tuple((e.contract,e.input,e.output,e.status=='error') for e in state.trace)]+=p
    return {k:v for k,v in result.items() if v}


def replay_trace(paths):
    result=Counter()
    for run in paths:
        result[(tuple((e[0],e[2],e[3],e[4]=='error') for e in run['trace']),run['requests'])]+=run['weight']
    return {k:v for k,v in result.items() if v}


def lean_trace(runs,with_requests=False):
    result=Counter()
    for run in runs:
        trace=tuple(tuple(e) for e in run['trace'])
        key=(trace,tuple(run['requests'])) if with_requests else trace
        result[key]+=Fraction(*run['p'])
    return {k:v for k,v in result.items() if v}


def boundary_cases():
    c=contract('boundary',8)
    key=canonical(c)
    call=lambda slot,request:['call',slot,key,request]
    first=call(0,['literal','start'])
    next_call=call(1,['append',['literal','Next:'],['var',0]])
    pipeline=pair(first,next_call)
    kernels={key:{'start':[dict(text='é',p='1/2',status='error'),dict(text='',p='1/2',status='ok')],
                  'Next:é':[dict(text='xxx',p='1',status='ok')],
                  'Next:':[dict(text='ok',p='1',status='ok')]}}
    cases=[('downstream-utf8',pipeline),('retry-two-pipeline',['retry',2,pipeline]),
           ('retry-zero',['retry',0,pipeline]),('empty-retry',['retry',16,['skip']]),
           ('nested-retry',['retry',2,['retry',2,first]]),
           ('public-false',['public',0,pipeline,['skip']]),
           ('lexical-shadow',pair(call(0,['literal','start']),
                                 pair(['secret',0,call(1,['literal','start']),call(1,['literal','start'])],
                                      call(2,['append',['literal','Next:'],['var',0]]))))]
    for name,program in cases:
        plan=normalize(program)
        yield name,dict(program=program,plan=plan,execute=[dict(public=[False],secret=[False],store=[],
                         observe_slots=3,kernels=lean_kernels(kernels))]),{key:c},kernels
    unequal_kernels={key:{'start':[dict(text='aa',p='1/2',status='ok'),dict(text='bb',p='1/2',status='ok')],
                          'Next:aa':[dict(text='x',p='1',status='ok')],
                          'Next:bb':[dict(text='xxx',p='1',status='ok')]}}
    dynamic=pair(first,next_call)
    fixed=pair(first,call(1,['literal','Next:aa']))
    unsafe=['secret',0,dynamic,fixed]
    yield 'equal-response-length-unequal-downstream',dict(program=unsafe,plan=dynamic,
        execute=[dict(public=[],secret=[flag],store=[],observe_slots=2,kernels=lean_kernels(unequal_kernels))
                 for flag in (False,True)]),{key:c},unequal_kernels


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lean',required=True,type=Path)
    p.add_argument('--orchc',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--protocol-commit',help='Require exact clean committed protocol for retained run')
    args=p.parse_args()
    protocol_path=ROOT/'bench/protocols/dataflow-development-v1.json'
    protocol=json.loads(protocol_path.read_text(encoding='utf-8'))
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
    if args.protocol_commit:
        if dirty:
            raise ValueError('frozen run requires a clean checkout')
        frozen=subprocess.check_output(['git','show',args.protocol_commit+':bench/protocols/dataflow-development-v1.json'],cwd=ROOT)
        if frozen!=protocol_path.read_bytes():
            raise ValueError('protocol bytes differ from frozen commit')
    args.output.mkdir(parents=True,exist_ok=False)
    failures,rows,cases,contexts,certificates,tamper_cases=[],[],[],[],[],[]
    source_tampers=0
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    write('manifest.json',dict(status='running',source_commit=commit,dirty_tree=dirty))
    grammar=protocol['arm_variants']
    variants=list(itertools.product(grammar['revisions'],grammar['caps'],grammar['first_request'],grammar['second_request']))
    tail_key=canonical(contract('tail',4))
    tail=['public',0,['call',3,tail_key,['append',['literal','Tail:'],['var',0]]],['skip']]
    with tempfile.TemporaryDirectory(prefix='dataflow-source-',dir=args.output.resolve()) as scratch:
        source_path=Path(scratch)/'case.orch'
        for index,(left,right) in enumerate(itertools.product(variants,repeat=2)):
            lc,ls=arm(left,'left')
            rc,rs=arm(right,'right')
            expected=pair(['secret',0,lc,rc],tail)
            plan=pair(lc,tail)
            source=('workflow Flow budget 10000 { input x:text max_tokens 64; '
                    'input flag:boolean max_tokens 1; secret s:boolean max_tokens 1; '
                    'model t=mock("tail") max_tokens 4; prompt tail(t:text)->text="Tail:{t}"; '
                    'if s {'+ls+'} else {'+rs+'} if flag { let z:text=call tail(x) using t; } else {} output "done"; }\n')
            data=source.encode('utf-8')
            parsed=read_source(data)
            if parsed['program']!=expected:
                failures.append(f'source reconstruction {index}')
            accepted=normalize(expected)==plan
            if accepted:
                cert=issue(data)
                bound=bind_certificate(data,cert)
                if bound['program']!=expected:
                    failures.append(f'source certificate binding {index}')
                certificates.append(dict(id=index,certificate=cert))
                tamper_cases.append(dict(program=expected,plan=['skip'],execute=[]))
                for changed in (data+b'\n',data.replace(b'max_tokens 64',b'max_tokens 63',1)):
                    try:
                        bind_certificate(changed,cert)
                        failures.append(f'source tamper accepted {index}')
                    except Unsupported:
                        source_tampers+=1
            source_path.write_text(source,encoding='utf-8',newline='\n')
            cpp=subprocess.run([str(args.orchc.resolve()),'check',str(source_path)],cwd=ROOT,
                               capture_output=True,text=True,encoding='utf-8',timeout=30)
            diagnostics=re.findall(r'error \[([A-Z]\d+)\]',cpp.stderr)
            if (cpp.returncode not in (0,1) or
                    (cpp.returncode==1 and (not diagnostics or set(diagnostics)-{'E230','E236'}))):
                failures.append(f'C++ infrastructure {index}')
            contracts={tail_key:contract('tail',4),canonical(contract(left[0],left[1])):contract(left[0],left[1]),
                       canonical(contract(right[0],right[1])):contract(right[0],right[1])}
            kernels=kernels_for(contracts,protocol['public_texts'])
            program=reference_program(expected)
            executions=[]
            these_contexts=[]
            for value,flag,secret in itertools.product(protocol['public_texts'],protocol['public_flags'],protocol['secrets']):
                env={'v0':value,'public0':flag,'secret0':secret}
                ref=Reference(contracts,kernels).run(program,env)
                replay=enumerate_replay(Replay(contracts,kernels),program,env)
                rtrace=reference_trace(ref)
                ptrace=replay_trace(replay)
                if rtrace!={k[0]:sum(v for (tr,req),v in ptrace.items() if tr==k[0]) for k in ptrace}:
                    failures.append(f'reference/replay disagreement {index}/{value}/{flag}/{secret}')
                ctx=dict(id=index,value=value,flag=flag,secret=secret,reference_paths=len(ref),
                         reference=[dict(trace=k,p=str(v)) for k,v in rtrace.items()],
                         replay=[dict(trace=k[0],requests=k[1],p=str(v)) for k,v in ptrace.items()])
                these_contexts.append(ctx)
                contexts.append(ctx)
                executions.append(dict(public=[flag],secret=[secret],store=[value],observe_slots=4,
                                       kernels=lean_kernels(kernels)))
            def context_distribution(ctx):
                return {tuple(tuple(e) for e in item['trace']):Fraction(item['p']) for item in ctx['reference']}
            finite_equal=all(context_distribution(a)==context_distribution(b)
                             for a,b in zip(these_contexts[::2],these_contexts[1::2]))
            if accepted and not finite_equal:
                failures.append(f'accepted finite counterexample {index}')
            rows.append(dict(id=index,left=left,right=right,source=source,source_sha256=hashlib.sha256(data).hexdigest(),
                             expected_core=expected,reader_equal=parsed['program']==expected,accepted=accepted,
                             finite_equal_all_contexts=finite_equal,cpp_exit=cpp.returncode,cpp_diagnostics=diagnostics,
                             cpp_stdout=cpp.stdout,cpp_stderr=cpp.stderr))
            cases.append(dict(program=expected,plan=plan,execute=executions))
    if len(rows)!=protocol['expected_source_programs'] or len(contexts)!=protocol['expected_execution_contexts']:
        failures.append('wrong census')
    write('programs.json',rows)
    write('contexts.json',contexts)
    write('certificates.json',certificates)
    write('lean-input.json',cases)
    try:
        results,stdout=run_checker(args.lean.resolve(),cases,args.output.resolve(),record_prefix='main-lean')
    except Exception as error:
        write('manifest.json',dict(status='failed',source_commit=commit,dirty_tree=dirty,
                                  infrastructure_error=str(error),spent_usd='0.00'))
        raise
    write('lean-output.json',results)
    (args.output/'lean.txt').write_text(stdout.splitlines()[0]+'\n'+'\n'.join(stdout.splitlines()[1:-1])+'\n',encoding='utf-8')
    cursor=0
    for row,result in zip(rows,results):
        if result['checked']!=row['accepted']:
            failures.append(f'Lean normalization {row["id"]}')
        for run in result['executions']:
            ctx=contexts[cursor]
            cursor+=1
            reference={tuple(tuple(e) for e in item['trace']):Fraction(item['p']) for item in ctx['reference']}
            replay={(tuple(tuple(e) for e in item['trace']),tuple(item['requests'])):Fraction(item['p']) for item in ctx['replay']}
            if lean_trace(run)!=reference:
                failures.append(f'Lean/reference execution {cursor-1}')
            if lean_trace(run,True)!=replay:
                failures.append(f'Lean/replay execution {cursor-1}')
    if cursor!=len(contexts):
        failures.append('incomplete Lean execution contexts')
    boundaries=list(boundary_cases())
    boundary_output,_=run_checker(args.lean.resolve(),[c[1] for c in boundaries],args.output.resolve(),record_prefix='boundary-lean')
    boundary_rows=[]
    for (name,case,contracts,kernels),result in zip(boundaries,boundary_output):
        agree=result['checked']==(normalize(case['program'])==case['plan'])
        reference_paths=0
        observations=[]
        for execution,runs in zip(case['execute'],result['executions']):
            env={**{'public'+str(i):v for i,v in enumerate(execution['public'])},
                 **{'secret'+str(i):v for i,v in enumerate(execution['secret'])},
                 **{'v'+str(i):v for i,v in enumerate(execution['store'])}}
            ref=Reference(contracts,kernels).run(reference_program(case['program']),env)
            replay=enumerate_replay(Replay(contracts,kernels),reference_program(case['program']),env)
            agree=agree and lean_trace(runs)==reference_trace(ref) and lean_trace(runs,True)==replay_trace(replay)
            reference_paths+=len(ref)
            observations.append(reference_trace(ref))
        if name=='equal-response-length-unequal-downstream' and observations[0]==observations[1]:
            failures.append('negative downstream witness did not separate observations')
        if not agree:
            failures.append('core boundary '+name)
        boundary_rows.append(dict(name=name,case=case,lean=result,reference_paths=reference_paths,agrees=agree))
    write('boundaries.json',boundary_rows)
    tamper_output,_=run_checker(args.lean.resolve(),tamper_cases,args.output.resolve(),record_prefix='tamper-lean')
    if any(r['checked'] for r in tamper_output):
        failures.append('altered plan accepted')
    write('altered-plans.json',dict(cases=tamper_cases,results=tamper_output))
    negative=[]
    base=boundaries[0][1]
    for category in ('text-constructor','secret-plan','negative-weight','zero-denominator',
                     'row-mass','duplicate-request','missing-request','execution-limit'):
        bad=copy.deepcopy(base)
        rows_kernel=bad['execute'][0]['kernels']
        if category=='text-constructor':
            bad['program'][1][3]=['unknown']
        elif category=='secret-plan':
            bad['plan']=['secret',0,['skip'],['skip']]
        elif category=='negative-weight':
            rows_kernel[0][2][0][2]=-1
        elif category=='zero-denominator':
            rows_kernel[0][2][0][3]=0
        elif category=='row-mass':
            rows_kernel[0][2][0][3]=2
        elif category=='duplicate-request':
            rows_kernel.append(copy.deepcopy(rows_kernel[0]))
        elif category=='missing-request':
            bad['execute'][0]['kernels']=[r for r in rows_kernel if r[1]!='start']
        elif category=='execution-limit':
            bad['program']=['retry',16,['retry',16,copy.deepcopy(base['program'][1])]]
            bad['plan']=copy.deepcopy(bad['program'])
        try:
            run_checker(args.lean.resolve(),[bad],args.output.resolve(),record_prefix='negative-'+category)
            failures.append('invalid evaluator input accepted: '+category)
            negative.append(dict(category=category,rejected=False,case=bad))
        except ValueError as error:
            negative.append(dict(category=category,rejected=True,case=bad,error=str(error)))
    write('negative-evaluator-inputs.json',negative)
    files=['proof/DataflowCore.lean','runtime/dataflow_gate.py','runtime/source_gate.py','runtime/finite_reference.py',
           'runtime/replay_adapter.py','scripts/check_dataflow.py','scripts/dataflow_certificate.py']
    manifest=dict(status='failed' if failures else 'completed',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  source_commit=commit,dirty_tree=dirty,protocol_commit=args.protocol_commit,
                  executable_sha256=hashlib.sha256(args.orchc.read_bytes()).hexdigest(),
                  protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                  files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                  source_programs=len(rows),source_reconstruction_disagreements=sum(not r['reader_equal'] for r in rows),
                  accepted=sum(r['accepted'] for r in rows),execution_contexts=len(contexts),
                  accepted_finite_counterexamples=sum(r['accepted'] and not r['finite_equal_all_contexts'] for r in rows),
                  lean_normalization_disagreements=sum(f.startswith('Lean normalization') for f in failures),
                  lean_reference_disagreements=sum(f.startswith('Lean/reference execution') for f in failures),
                  lean_replay_disagreements=sum(f.startswith('Lean/replay execution') for f in failures),
                  cpp_accepted=sum(r['cpp_exit']==0 for r in rows),cpp_e230_cases=sum('E230' in r['cpp_diagnostics'] for r in rows),
                  boundary_cases=len(boundary_rows),boundary_paths=sum(r['reference_paths'] for r in boundary_rows),
                  source_tampers_rejected=source_tampers,altered_plans_rejected=sum(not r['checked'] for r in tamper_output),
                  invalid_evaluator_inputs_rejected=sum(r['rejected'] for r in negative),
                  failures=failures,spent_usd='0.00',provider_inference=False)
    write('manifest.json',manifest)
    print(json.dumps(manifest,indent=2))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
