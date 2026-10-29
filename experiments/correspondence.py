"""Three-way core execution comparison: Lean exec, independent JSON, production.

This is a constructed development grammar and finite deterministic primitive
world. It is not model inference or a source-to-provider refinement theorem.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments'))
from orchlang import compiler as K,core as C,models as M,runtime as R,validate
from reference.shape import execute as reference
from differential import Gen,FakeProg,PROFILE,CharTok


class TableBackend(R.MockBackend):
    def __init__(self,profile,variant):
        super().__init__(profile)
        self.variant=variant;self.rows={}

    def generate(self,prompt,n,seed,forced,cap=None,pad_tokens=0):
        values=("ab","caaaa","b") if not self.variant else ("bc","a","ccab")
        text=values[sum(prompt.encode("utf-8"))%3]
        self.rows[(self.profile.key,prompt)]=text
        visible=text[:cap if cap is not None else n]
        ids=[ord(c) for c in visible]
        return (ids+[0]*(n-len(ids)) if forced else ids),visible,len(prompt)+pad_tokens


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--programs',type=int,default=150)
    p.add_argument('--seed',type=int,default=271828)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--lean',default=os.environ.get('LEAN','lean'))
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source_paths=[*sorted((ROOT/'orchlang').glob('*.py')),ROOT/'proof/ShapeCore.lean',
                  ROOT/'reference/shape.py',ROOT/'experiments/differential.py',Path(__file__)]
    source_before={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in source_paths}
    rng=random.Random(a.seed)
    cases=[];expected=[];metadata=[];validators=[];failures=[]
    strategies=('original','ours','naive','uniform','padall')
    def add_execution(candidates,store,nv,number,variant,context):
        original_store=None
        for strategy,program in candidates.items():
            backend=TableBackend(PROFILE,variant)
            runtime=R.Runtime({'m':backend},{'upper':lambda v:v.upper()[:6],'first':lambda v:v[:1]},{})
            run=runtime.run(program,store,context)
            observed=dict(trace=[list(e) for e in run.observed()],store=[[i,run.store.get(i,'')] for i in range(nv)])
            case=dict(program=C.stmt_json(program),store=list(store.items()),store_limit=nv,
                      kernels=[[m,q,v] for (m,q),v in sorted(backend.rows.items())])
            own=reference(case)
            if own!=observed:failures.append(dict(program=number,strategy=strategy,error='reference/production disagreement'))
            if strategy=='original':original_store=observed['store']
            elif observed['store']!=original_store:failures.append(dict(program=number,strategy=strategy,error='functional preservation disagreement'))
            cases.append(case);expected.append(observed)
            metadata.append(dict(program=number,variant=variant,context=context,strategy=strategy))
    for number in range(a.programs):
        nv=rng.randint(2,5)
        body=Gen(rng,nv).stmt(rng.randint(1,4))
        secrets={i for i in range(nv) if rng.random()<0.5}
        gamma=K.infer_labels(body,{i:C.HIGH if i in secrets else C.LOW for i in range(nv)})
        fp=FakeProg(body,gamma,{i:6 for i in range(nv)})
        candidates={'original':body,**{s:K.Shaper(fp,{'m':PROFILE},{'m':CharTok()},s).run() for s in strategies[1:]}}
        for s in strategies[1:]:validators.append(validate.payload(sorted(i for i,l in gamma.items() if l==C.HIGH),body,candidates[s],sorted(secrets)))
        for variant in (0,1):
            for context in range(4):
                store={i:rng.choice(('','a','b','ab')) for i in range(nv)}
                add_execution(candidates,store,nv,number,variant,context)
    # One targeted program, 32 contexts, two kernels, five variants: 320 extra
    # executions. Keep its denominator separate from the generated grammar.
    request=C.concat([C.ELit('<user>'),C.ETrim(C.EVar(0)),C.ELit('</>\n<a>')])
    trim=C.Call(1,1,'m',request,None,6)
    gamma={0:C.HIGH,1:C.HIGH};fp=FakeProg(trim,gamma,{0:6,1:6})
    candidates={'original':trim,**{s:K.Shaper(fp,{'m':PROFILE},{'m':CharTok()},s).run() for s in strategies[1:]}}
    validators.extend(validate.payload([0,1],trim,candidates[s],[0]) for s in strategies[1:])
    values=['','\0a\0','\u200ba\u200b']+[chr(c)+'a'+chr(c) for c in range(0x110000) if chr(c).isspace()]
    for variant in (0,1):
        for context,value in enumerate(values):add_execution(candidates,{0:value,1:'old'},2,'template-trim',variant,context)
    checked=validate.lean_validate_batch(validators,a.lean)
    if not all(x['accepted'] for x in checked):failures.append('a shaped candidate failed Lean validation')
    input_path=a.output/'lean-input.json'
    input_path.write_text(json.dumps(cases,ensure_ascii=False)+'\n',encoding='utf-8')
    start=time.perf_counter()
    command=[a.lean,'--run',str(ROOT/'proof/ShapeCore.lean'),'execute',str(input_path.resolve())]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=600,cwd=ROOT)
    (a.output/'lean-stdout.log').write_text(result.stdout,encoding='utf-8')
    (a.output/'lean-stderr.log').write_text(result.stderr,encoding='utf-8')
    if result.returncode:
        failures.append(dict(error='Lean execution infrastructure failure',exit=result.returncode))
        actual=[]
    else:actual=json.loads(result.stdout.rstrip('\r\n').rsplit('\n',1)[-1])
    if len(actual)!=len(expected):failures.append('Lean execution denominator mismatch')
    for index,(left,right) in enumerate(zip(actual,expected)):
        if left!=right:failures.append({**metadata[index], 'error':'Lean/production execution disagreement','lean':left,'production':right})
    (a.output/'expected.json').write_text(json.dumps(expected,indent=1)+'\n')
    (a.output/'cases.json').write_text(json.dumps(metadata,indent=1)+'\n')
    source_after={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in source_paths}
    if source_before!=source_after:failures.append('source changed during operational comparison')
    manifest=dict(status='failed' if failures else 'completed',programs=a.programs,seed=a.seed,
        targeted_programs=1,targeted_contexts=len(values),
        execution_contexts=len(cases),validator_checks=len(validators),lean_seconds=time.perf_counter()-start,
        comparisons=['Lean exec','independent JSON interpreter','production Runtime'],
        source_before=source_before,source_after=source_after,
        unit='character counts in a finite deterministic audit world; no provider tokens',
        files={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (
            ROOT/'proof/ShapeCore.lean',ROOT/'reference/shape.py',ROOT/'orchlang/runtime.py',Path(__file__))},
        command=command,command_exit=result.returncode,failures=failures,spent_api_usd='0.00')
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2));return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
