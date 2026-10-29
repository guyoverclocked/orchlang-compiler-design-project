"""Generate paper numbers from retained observations; never infer completion."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/'publication'
NAMES={'switch':'Switch','routing':'Routing','chaining':'Chaining','evaluator':'Evaluator',
       'email':'Email','orchestrator':'Orchestrator','calculator':'Calculator','crag':'Corrective RAG','adaptive':'Adaptive RAG'}
PLANS={'main':{'crag':150,'adaptive':60},'replication':{'switch':210,'email':152,'crag':150},
       'conformance':{w:3 for w in list(NAMES)[:7]}}

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def rows(path):
    if not path.exists():return {}
    result={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        row=json.loads(line)
        if row['id'] in result:raise ValueError('duplicate observation: '+str(path))
        result[row['id']]=row
    return result

def obs(row):return [e[:4] if e[0]=='llm' else e[:2] for e in row['trace']]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args()
    historical=read(PUB/'evidence/historical-analysis/results.json')['workflows']
    result={'historical':historical,'completion':{},'definitions':{
        'pair':'one completed original and one completed shaped execution with the same dataset ID',
        'observer':'ordered (llm, contract, input, output) and (tool, name); excludes private audit fields and latency',
        'weighted_cost':'logical input + 4 * generated output; no currency or measured provider invoice',
        'fresh_subset':'first three retained dataset IDs per historically completed workflow; conformance only, no power claim'}}
    failures=[]
    for group,plan in PLANS.items():
        result['completion'][group]={}
        for name,expected in plan.items():
            directory=PUB/'evidence/completion'/group/name
            original,shaped=rows(directory/'orig.jsonl'),rows(directory/'ours.jsonl')
            manifest=read(directory/'run-manifest.json') if (directory/'run-manifest.json').exists() else None
            allowed=set(manifest['selected_ids']) if manifest else set()
            if manifest and (len(allowed)!=expected or len(manifest['selected_ids'])!=expected):
                raise ValueError('planned denominator differs from manifest: '+str(directory))
            if (set(original)|set(shaped))-allowed:
                raise ValueError('observations contain IDs outside their manifest: '+str(directory))
            common=sorted(original.keys()&shaped.keys())
            info=read(directory/'compile.json') if (directory/'compile.json').exists() else None
            shape=info['strategies']['ours']['lean']['static_shape'] if info else None
            if info:
                binding=info['source_binding']['binding_sha256']
                if any(row.get('source_binding_sha256')!=binding for row in [*original.values(),*shaped.values()]):
                    raise ValueError('observation source binding mismatch: '+str(directory))
            item=dict(expected=expected,original=len(original),shaped=len(shaped),paired=len(common),
                stores_equal=sum(original[i]['store']==shaped[i]['store'] for i in common),
                shape_equal=sum(obs(shaped[i])==shape for i in common),
                distinct_shaped_traces=len({json.dumps(obs(shaped[i])) for i in common}),
                truncations=sum(shaped[i]['truncations'] for i in common),
                complete_usage=sum(shaped[i].get('usage',{}).get('usage_complete',False) for i in common),
                failures=len(rows(directory/'failures.jsonl')) if (directory/'failures.jsonl').exists() else 0)
            item['status']='completed' if set(original)==set(shaped)==allowed and len(allowed)==expected else 'incomplete'
            if common:
                cost=lambda row:sum(e[2]+4*e[3] for e in row['trace'] if e[0]=='llm')
                item['weighted_overhead']=sum(cost(shaped[i]) for i in common)/sum(cost(original[i]) for i in common)
                item['mean_seconds']={c:statistics.mean(rows_[i]['wall'] for i in common) for c,rows_ in [('orig',original),('ours',shaped)]}
            if directory.exists():
                item['files']={p.name:digest(p) for p in directory.iterdir() if p.is_file()}
            if item['status']!='completed' or item['stores_equal']!=len(common) or item['shape_equal']!=len(common) or item['complete_usage']!=len(common) or item['truncations'] or item['failures']:
                failures.append(group+'/'+name)
            result['completion'][group][name]=item
    result['completion_failures_or_pending']=failures
    result['completed_main_pairs']=sum(r['n'] for r in historical.values())+sum(r['paired'] for r in result['completion']['main'].values())
    result['completed_replication_pairs']=sum(r['paired'] for r in result['completion']['replication'].values())
    result['fresh_conformance_pairs']=sum(r['paired'] for r in result['completion']['conformance'].values())
    (PUB/'evidence-summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    gen=ROOT/'paper/generated';gen.mkdir(exist_ok=True)
    macros={'historicalPairs':sum(r['n'] for r in historical.values()),
            'completionMainPairs':sum(r['paired'] for r in result['completion']['main'].values()),
            'replicationPairs':result['completed_replication_pairs'],'freshConformancePairs':result['fresh_conformance_pairs'],
            'historicalDecisionMedian':f"{100*statistics.median(r['leak']['orig']['decision']['balanced'] for r in historical.values()):.1f}",
            'historicalOverheadMedian':f"{statistics.median(r['ours_cost']['price']/r['orig_cost']['price'] for r in historical.values()):.2f}"}
    (gen/'unified-results.tex').write_text(''.join(f'\\newcommand{{\\{k}}}{{{v}}}\n' for k,v in macros.items()))
    with (gen/'unified-historical-table.tex').open('w') as f:
        for name in list(NAMES)[:7]:
            r=historical[name];L=r['leak'];fn=r['function'];acc=fn.get('orig_acc')
            f.write(f"{NAMES[name]} & {r['n']} & {100*L['orig']['decision']['chance_balanced']:.1f} & {100*L['orig']['decision']['balanced']:.1f} & {L['ours']['distinct']} & {L['ours']['decision']['mi_bits']:.1f} & {r['ours_cost']['price']/r['orig_cost']['price']:.2f} & "+(f'{100*acc:.1f}' if acc is not None else '--')+' \\\\\n')
    with (gen/'unified-completion-table.tex').open('w') as f:
        for group in PLANS:
            for name,r in result['completion'][group].items():
                label={'main':'Completion','replication':'Qwen replication','conformance':'Fresh check'}[group]
                f.write(f"{label}: {NAMES[name]} & {r['paired']}/{r['expected']} & {r['stores_equal']} & {r['shape_equal']} & {r['truncations']} \\\\\n")
    # Keep the new model/version cohorts separate from historical evidence.
    with (gen/'unified-new-cost-table.tex').open('w') as f:
        for group,analysis in [('main','completion-main-analysis'),('replication','replication-analysis')]:
            path=PUB/'evidence'/analysis/'results.json'
            if not path.exists():raise ValueError('missing completed-cohort analysis: '+str(path))
            for name,r in read(path)['workflows'].items():
                if r['n']!=PLANS[group][name]:raise ValueError('analysis denominator differs from plan')
                cohort='Llama' if group=='main' else 'Qwen'
                attack=r['leak']['orig']['decision']
                classes=attack['classes']
                accuracy=r['function'].get('orig_acc')
                ba='--' if classes<2 else f"{100*attack['balanced']:.1f}"
                task='--' if accuracy is None else f'{100*accuracy:.1f}'
                f.write(f"{cohort}: {NAMES[name]} & {r['n']} & {classes} & {ba} & {r['leak']['ours']['distinct']} & {r['leak']['ours']['decision']['mi_bits']:.1f} & {r['ours_cost']['price']/r['orig_cost']['price']:.2f} & {task} \\\\\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ('historical','completion')},indent=2))
    if args.require_complete and failures:raise SystemExit('Incomplete or failed campaigns: '+', '.join(failures))

if __name__=='__main__':main()
