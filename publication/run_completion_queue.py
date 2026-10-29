"""Execute the declared completion protocol from an immutable source checkout."""
import json,os,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
CODE=ROOT/'execution-freeze'
OUT=ROOT/'unified-publication/publication/evidence/completion'
PY=ROOT/'analysis-venv/Scripts/python.exe'
MODELS=ROOT/'models-pinned/models.json'
ENV={**os.environ,'LEAN':r'C:\Users\nambi\Documents\OrchLang Publication Work\tools\lean-4.19.0-windows\bin\lean.exe',
     'ORCHLANG_MODELS':str(MODELS),'ORCHLANG_GPU_LAYERS':'0'}
KEEP={'switch':'response,intention,llm_result','routing':'answer,decision','chaining':'final,gate,joke',
      'evaluator':'joke,stop','email':'reply,route,cls','orchestrator':'report,plan','calculator':'out,done',
      'crag':'answer,search','adaptive':'gen,src,have,done'}
def log(event):
    with (OUT/'queue.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),**event))+'\n')
def run(name,limit,group='conformance',rep=False):
    workflow=f'workflows/replication/{name}_qwen.orch' if rep else f'workflows/{name}.orch'
    command=[str(PY),'experiments/run_workflow.py','--workflow',workflow,'--data',f'experiments/data/{name}.jsonl',
             '--out',str(OUT/group/name),'--limit',str(limit),'--keep',KEEP[name]]
    if name in ('crag','adaptive'):
        command+=['--corpus',f'experiments/data/{name}_corpus.jsonl','--web',f'experiments/data/{name}_web.jsonl']
    log(dict(event='start',workflow=name,group=group,command=command))
    with (ROOT/f'evidence/completion-{group}-{name}.log').open('w',encoding='utf-8') as f:
        result=subprocess.run(command,cwd=CODE,env=ENV,stdout=f,stderr=subprocess.STDOUT)
    log(dict(event='exit',workflow=name,group=group,exit=result.returncode))
    return result.returncode

def wait(key):
    reported=False
    while key not in (json.loads(MODELS.read_text()) if MODELS.exists() else {}):
        if not reported:log(dict(event='await-pinned-model',model=key));reported=True
        time.sleep(15)

if __name__=='__main__':
    import sys
    group=sys.argv[1]
    OUT.mkdir(parents=True,exist_ok=True)
    if group=='main':
        for name in ('switch','routing','chaining','evaluator','email','orchestrator','calculator'):run(name,3)
        log(dict(event='conformance-subset-finished'))
        wait('llama3b');run('adaptive',60,'main')
    elif group=='replication':
        wait('qwen1.5b')
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(run,name,n,'replication',True) for name,n in (('switch',210),('email',152),('crag',150))]
            for future in futures:future.result()
    log(dict(event='queue-finished',group=group))
