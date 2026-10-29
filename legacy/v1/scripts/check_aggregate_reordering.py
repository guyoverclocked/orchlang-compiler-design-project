"""Exhaustive authored source campaign for the aggregate-only verified judgment."""
import argparse
from collections import Counter
import copy
from datetime import datetime,timezone
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.aggregate_gate import read_source,accepts,actions
from runtime.source_gate import normalize as ordered_normalize
from runtime.finite_reference import Reference,canonical,Unsupported
from runtime.replay_adapter import Replay,enumerate_replay
from scripts.check_dataflow import contract
from scripts.decide_aggregate import run_checker


def observation(events,contracts):
    totals={c:[0,0,0,0] for c in contracts}
    for c,inputs,outputs,failed in events:
        value=totals[c]
        for index,amount in enumerate((inputs,outputs,1,int(failed))):
            value[index]+=amount
    return tuple((c,*v) for c,v in sorted(totals.items()))


def ref_distribution(paths,contracts,aggregate):
    result=Counter()
    for state,weight in paths:
        events=tuple((e.contract,e.input,e.output,e.status=='error') for e in state.trace)
        result[observation(events,contracts) if aggregate else events]+=weight
    return dict(result)


def replay_distribution(paths,contracts,aggregate):
    result=Counter()
    for run in paths:
        events=tuple((e[0],e[2],e[3],e[4]=='error') for e in run['trace'])
        result[observation(events,contracts) if aggregate else events]+=run['weight']
    return dict(result)


def lean_distribution(paths,aggregate):
    result=Counter()
    for run in paths:
        key=(tuple(sorted(tuple(e) for e in run['aggregate'])) if aggregate else
             tuple(tuple(e) for e in run['ordered']))
        result[key]+=Fraction(*run['p'])
    return dict(result)


def ref_arm(arm):
    return [dict(kind='call',model=call[1],request=call[2],bind='v'+str(i)) for i,call in enumerate(arm)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lean',required=True,type=Path)
    p.add_argument('--orchc',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    write('manifest.json',dict(status='running'))
    protocol=dict(purpose='authored development grammar, not external workflow execution',
                  action_contracts=['A','B'],requests=['yes','no!'],calls_per_arm=2,
                  expected_source_cases=256,expected_accepts=28,expected_ordered_accepts=16,
                  kernel_denominators=[2,3,4,5],outcomes_per_action=2,
                  observer='per-contract UTF-8 input/output totals, calls, failures',
                  assumptions='independent stateless full-action kernels; exact rational finite rows')
    write('protocol.json',protocol)
    contracts={canonical(contract(rev,8)):contract(rev,8) for rev in ('A','B')}
    variants=list(itertools.product(('A','B'),('yes','no!')))
    action_values=[['call',canonical(contract(rev,8)),request] for rev,request in variants]
    kernels={key:{} for key in contracts}
    lean_kernels=[]
    for index,(rev,request) in enumerate(variants):
        key=canonical(contract(rev,8))
        denominator=index+2
        first_weight=(1 if index<2 else index)
        response=('x','xxx','q','zzzzz')[index]
        outcomes=[dict(text=response,status='ok',p=str(Fraction(first_weight,denominator))),
                  dict(text='é' if index%2==0 else '',status='error',p=str(Fraction(denominator-first_weight,denominator)))]
        kernels[key][request]=outcomes
        lean_kernels.append([key,request,denominator,[[response,False,first_weight],
                                                   [outcomes[1]['text'],True,denominator-first_weight]]])
    sequences=list(itertools.product(range(4),repeat=2))
    rows,cases,contexts,failures=[],[],[],[]
    source_dir=args.output/'sources'
    source_dir.mkdir()
    for case_id,(left,right) in enumerate(itertools.product(sequences,repeat=2)):
        def make_arm(sequence):
            return ' '.join(f'let v{i}:text=call p("{variants[index][1]}") using {variants[index][0].lower()};'
                            for i,index in enumerate(sequence))
        source=('workflow AggregateGenerated budget 10000 { secret s:boolean max_tokens 1; '
                'model a=mock("A") max_tokens 8; model b=mock("B") max_tokens 8; '
                'prompt p(t:text)->text="{t}"; if s {'+make_arm(left)+'} else {'+make_arm(right)+'} output "done"; }\n')
        data=source.encode('utf-8')
        path=source_dir/(f'case-{case_id:03d}.orch')
        path.write_bytes(data)
        parsed=read_source(data)
        expected=['branch',0,['seq',*[action_values[i] for i in left]],['seq',*[action_values[i] for i in right]]]
        if parsed['program']!=expected:
            failures.append(f'reader reconstruction {case_id}')
        accepted=accepts(parsed['program'])
        baseline=ordered_normalize(parsed['program']) is not None
        if accepted!=(sorted(left)==sorted(right)):
            failures.append(f'acceptance oracle {case_id}')
        universe=sorted(set(call[1] for arm in actions(expected) for call in arm))
        finite=[]
        record=[]
        for side,arm in zip(('left','right'),actions(expected)):
            ref=Reference(contracts,kernels).run(ref_arm(arm),{})
            replay=enumerate_replay(Replay(contracts,kernels),ref_arm(arm),{})
            agg=ref_distribution(ref,universe,True)
            ordered=ref_distribution(ref,universe,False)
            if agg!=replay_distribution(replay,universe,True) or ordered!=replay_distribution(replay,universe,False):
                failures.append(f'reference/replay {case_id}/{side}')
            finite.append((agg,ordered))
            record.append(dict(side=side,aggregate=[dict(observation=k,p=str(v)) for k,v in agg.items()],
                               ordered=[dict(observation=k,p=str(v)) for k,v in ordered.items()],paths=len(ref)))
        aggregate_equal=finite[0][0]==finite[1][0]
        ordered_equal=finite[0][1]==finite[1][1]
        if accepted and not aggregate_equal:
            failures.append(f'accepted aggregate counterexample {case_id}')
        cpp=subprocess.run([str(args.orchc.resolve()),'check',str(path.resolve())],cwd=ROOT,
                           capture_output=True,text=True,encoding='utf-8',timeout=30)
        diagnostics=re.findall(r'error \[([A-Z]\d+)\]',cpp.stderr)
        if cpp.returncode not in (0,1) or (cpp.returncode==1 and not diagnostics):
            failures.append(f'C++ infrastructure {case_id}')
        rows.append(dict(id=case_id,source_sha256=parsed['source_sha256'],source=source,program=expected,
                         accepted=accepted,ordered_baseline_accepted=baseline,aggregate_equal=aggregate_equal,
                         ordered_equal=ordered_equal,cpp_exit=cpp.returncode,cpp_diagnostics=diagnostics,
                         cpp_stderr=cpp.stderr))
        contexts.append(record)
        cases.append(dict(program=expected,execute=True,kernels=lean_kernels))
    write('programs.json',rows)
    write('contexts.json',contexts)
    write('lean-input.json',cases)
    try:
        results=run_checker(args.lean.resolve(),cases,args.output.resolve(),record_prefix='main-lean')
        write('lean-output.json',results)
        for row,record,result in zip(rows,contexts,results):
            if result['checked']!=row['accepted']:
                failures.append(f'Lean decision {row["id"]}')
            for side,ctx in zip(('left','right'),record):
                for aggregate,name in ((True,'aggregate'),(False,'ordered')):
                    expected={tuple(tuple(e) for e in item['observation']):Fraction(item['p']) for item in ctx[name]}
                    if lean_distribution(result[side],aggregate)!=expected:
                        failures.append(f'Lean/reference {row["id"]}/{side}/{name}')
        # Three illustrative source scenarios, separate from the generated census.
        scenarios=[]
        for example in sorted((ROOT/'examples/certificates').glob('aggregate_*.orch')):
            parsed=read_source(example.read_bytes())
            result=run_checker(args.lean.resolve(),[dict(program=parsed['program'],execute=False)],args.output.resolve(),
                               record_prefix='scenario-'+example.stem)[0]
            baseline=ordered_normalize(parsed['program']) is not None
            if not result['checked'] or baseline:
                failures.append('illustrative scenario '+example.name)
            scenarios.append(dict(path=str(example.relative_to(ROOT)),source_sha256=parsed['source_sha256'],
                                  aggregate_accepted=result['checked'],ordered_baseline_accepted=baseline,
                                  status='authored illustration, not external workload'))
        write('illustrative-scenarios.json',scenarios)
        negatives=[]
        base=copy.deepcopy(cases[1])
        for category in ('zero-denominator','wrong-mass','negative-numerator','duplicate-action','missing-action','bad-constructor','dependent-request','three-calls'):
            bad=copy.deepcopy(base)
            if category=='zero-denominator': bad['kernels'][0][2]=0
            elif category=='wrong-mass': bad['kernels'][0][2]+=1
            elif category=='negative-numerator': bad['kernels'][0][3][0][2]=-1
            elif category=='duplicate-action': bad['kernels'].append(copy.deepcopy(bad['kernels'][0]))
            elif category=='missing-action': bad['kernels']=bad['kernels'][1:]
            elif category=='bad-constructor': bad['program'][0]='unknown'
            elif category=='dependent-request': bad['program'][2][2][2]=['var',0]
            elif category=='three-calls': bad['program'][2][2]=['seq',bad['program'][2][2],copy.deepcopy(bad['program'][2][2])]
            try:
                run_checker(args.lean.resolve(),[bad],args.output.resolve(),record_prefix='negative-'+category)
                negatives.append(dict(category=category,rejected=False))
                failures.append('invalid input accepted '+category)
            except ValueError as error:
                negatives.append(dict(category=category,rejected=True,error=str(error),case=bad))
        write('invalid-inputs.json',negatives)
    except Exception as error:
        write('manifest.json',dict(status='failed',infrastructure_error=str(error),failures=failures))
        raise
    files=['proof/AggregateReordering.lean','runtime/aggregate_gate.py','runtime/source_gate.py',
           'scripts/decide_aggregate.py','scripts/check_aggregate_reordering.py',
           'runtime/finite_reference.py','runtime/replay_adapter.py']
    manifest=dict(status='failed' if failures else 'completed',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  dirty_tree=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
                  files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                  executable_sha256=hashlib.sha256(args.orchc.read_bytes()).hexdigest(),
                  source_cases=len(rows),ordered_baseline_accepted=sum(r['ordered_baseline_accepted'] for r in rows),
                  aggregate_accepted=sum(r['accepted'] for r in rows),
                  aggregate_gains=sum(r['accepted'] and not r['ordered_baseline_accepted'] for r in rows),
                  accepted_with_different_ordered_distributions=sum(r['accepted'] and not r['ordered_equal'] for r in rows),
                  accepted_finite_counterexamples=sum(r['accepted'] and not r['aggregate_equal'] for r in rows),
                  execution_contexts=2*len(rows),weighted_paths=sum(c['paths'] for pair in contexts for c in pair),
                  malformed_inputs_rejected=sum(r['rejected'] for r in negatives),
                  illustrative_scenarios=len(scenarios),failures=failures,spent_usd='0.00',provider_inference=False)
    write('manifest.json',manifest)
    print(json.dumps(manifest,indent=2))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
