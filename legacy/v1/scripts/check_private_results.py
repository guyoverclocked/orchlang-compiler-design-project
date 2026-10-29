"""Check joint aggregate/response-multiset invariance on the retained action grammar."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.aggregate_gate import actions,read_source
from runtime.finite_reference import Reference
from runtime.replay_adapter import Replay,enumerate_replay
from scripts.check_dataflow import contract
from scripts.check_aggregate_reordering import observation,ref_arm
from scripts.decide_aggregate import run_checker


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lean',required=True,type=Path)
    p.add_argument('--campaign',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    def write(name,value):
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    write('manifest.json',dict(status='running'))
    historical=json.loads((args.campaign/'manifest.json').read_text(encoding='utf-8'))
    if historical['status']!='completed':
        raise ValueError('requires a completed original aggregate campaign')
    cases=json.loads((args.campaign/'lean-input.json').read_text(encoding='utf-8'))
    expected=json.loads((args.campaign/'lean-output.json').read_text(encoding='utf-8'))
    programs=json.loads((args.campaign/'programs.json').read_text(encoding='utf-8'))
    failures=[]
    try:
        # Existing JSON output is deliberately unchanged by the richer mode.
        ordinary=run_checker(args.lean.resolve(),cases,args.output.resolve(),record_prefix='compatibility')
        if ordinary!=expected:
            failures.append('old aggregate output changed')
        results=run_checker(args.lean.resolve(),cases,args.output.resolve(),record_prefix='private',private_results=True)
        write('lean-output.json',results)
        records=[]
        paths=0
        for index,(case,result,source) in enumerate(zip(cases,results,programs)):
            if read_source(source['source'].encode('utf-8'))['program']!=case['program']:
                failures.append(f'source reconstruction {index}')
            contracts={key:json.loads(key) for key in {row[0] for row in case['kernels']}}
            kernels={key:{} for key in contracts}
            for key,request,denominator,outcomes in case['kernels']:
                kernels[key][request]=[dict(text=text,status='error' if failed else 'ok',p=str(Fraction(weight,denominator)))
                                       for text,failed,weight in outcomes]
            universe=sorted(set(c[1] for arm in actions(case['program']) for c in arm))
            joint=[]
            these=[]
            for side,arm in zip(('left','right'),actions(case['program'])):
                # This is an explicit trusted-caller archive in the finite IR;
                # it does not introduce a public output into source semantics.
                body=ref_arm(arm)+[dict(kind='private_output',value={'var':'v'+str(i)}) for i in range(2)]
                reference=Reference(contracts,kernels).run(body,{})
                replay=enumerate_replay(Replay(contracts,kernels),body,{})
                paths+=len(reference)
                ref_dist,replay_dist,lean_dist=Counter(),Counter(),Counter()
                for state,weight in reference:
                    events=tuple((e.contract,e.input,e.output,e.status=='error') for e in state.trace)
                    archive=tuple(sorted((c[1],c[2],response,event[3])
                                         for c,response,event in zip(arm,state.private_outputs,events)))
                    ref_dist[(observation(events,universe),archive)]+=weight
                for run in replay:
                    events=tuple((e[0],e[2],e[3],e[4]=='error') for e in run['trace'])
                    archive=tuple(sorted((c[1],c[2],response,event[3])
                                         for c,response,event in zip(arm,run['private_outputs'],events)))
                    replay_dist[(observation(events,universe),archive)]+=run['weight']
                for run in result[side]:
                    key=(tuple(sorted(tuple(e) for e in run['aggregate'])),
                         tuple(sorted(tuple(r) for r in run['private_results'])))
                    lean_dist[key]+=Fraction(*run['p'])
                if ref_dist!=replay_dist or ref_dist!=lean_dist:
                    failures.append(f'joint execution disagreement {index}/{side}')
                joint.append(ref_dist)
                these.append(dict(side=side,joint=[dict(aggregate=k[0],private_results=k[1],p=str(v))
                                                 for k,v in ref_dist.items()]))
            if result['checked']!=source['accepted']:
                failures.append(f'acceptance changed {index}')
            equivalent=joint[0]==joint[1]
            if result['checked'] and not equivalent:
                failures.append(f'accepted joint counterexample {index}')
            records.append(dict(id=index,accepted=result['checked'],joint_equal=equivalent,contexts=these))
        write('joint-contexts.json',records)
        scenarios=[]
        for path in sorted((ROOT/'examples/certificates').glob('aggregate_*.orch')):
            data=path.read_bytes()
            parsed=read_source(data)
            answer=run_checker(args.lean.resolve(),[dict(program=parsed['program'],execute=False)],args.output.resolve(),
                               record_prefix='scenario-'+path.stem)[0]
            scenarios.append(dict(path=str(path.relative_to(ROOT)),source_sha256=parsed['source_sha256'],
                                  source=data.decode('utf-8'),accepted=answer['checked']))
        write('illustrative-scenarios.json',scenarios)
    except Exception as error:
        write('manifest.json',dict(status='failed',infrastructure_error=str(error),failures=failures))
        raise
    files=['proof/AggregateReordering.lean','scripts/decide_aggregate.py','scripts/check_private_results.py']
    manifest=dict(status='failed' if failures else 'completed',timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  dirty_tree=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
                  files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                  historical_manifest_sha256=hashlib.sha256((args.campaign/'manifest.json').read_bytes()).hexdigest(),
                  source_cases=len(cases),accepted=sum(r['checked'] for r in results),execution_contexts=2*len(cases),
                  weighted_paths=paths,old_aggregate_output_unchanged=ordinary==expected,
                  accepted_joint_counterexamples=sum(r['accepted'] and not r['joint_equal'] for r in records),
                  joint_execution_disagreements=sum(f.startswith('joint execution') for f in failures),
                  failures=failures,spent_usd='0.00',provider_inference=False)
    write('manifest.json',manifest)
    print(json.dumps(manifest,indent=2))
    return int(bool(failures))


if __name__=='__main__':
    raise SystemExit(main())
