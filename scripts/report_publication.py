"""Generate manuscript evidence tables from retained successful offline records."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    files = dict(cpu='clean-cpu-v3/manifest.json', generated='generated-v3/manifest.json',
                 mutations='mutations-v3/mutations.json', tokenizers='tokenizers-v3/manifest.json',
                 certificates='certificates-v3/manifest.json', replay='replay-v3/manifest.json',
                 external='external-v4/manifest.json')
    manifests = {k:read(args.runs/v) for k,v in files.items()}
    if any(m['status'] != 'completed' for m in manifests.values()):
        raise ValueError('failed/incomplete evidence')
    commands = read(args.runs/'clean-cpu-v3/commands.json')
    cpp = next(re.search(r'Passed (\d+)/(\d+) tests',c['stdout']) for c in commands if 'orchlang_tests' in c['argv'][0])
    py = next(re.search(r'Ran (\d+) tests',c['stderr']) for c in commands if 'unittest' in c['argv'])
    if cpp is None or py is None or cpp[1] != cpp[2]:
        raise ValueError('test-count mismatch')
    ext = read(args.runs/'external-v4/results.json')
    tokens = read(args.runs/'tokenizers-v3/tokens.json')
    concat = read(args.runs/'tokenizers-v3/concatenations.json')
    costs = [r for r in read(args.runs/'clean-cpu-v3/results.json') if r['category']=='historical-cost-development']
    g,c,r = (manifests[k] for k in ('generated','certificates','replay'))
    metrics = dict(cpp_tests=int(cpp[1]),python_tests=int(py[1]),cost_workflows=len(costs),
                   cost_runs=sum(len(x['runs']) for x in costs),generated=g['programs'],accepted=g['accepted'],
                   accepted_finite_counterexamples=g['accepted_finite_counterexamples'],
                   finite_equal_rejections=g['finite_equivalent_rejected'],
                   trace_identity_disagreements=g['trace_identity_disagreements'],
                   mutants_detected=sum(x['status']=='detected' for x in manifests['mutations']['mutations']),
                   tokenizer_encodings=len(tokens),underestimates=sum(x['plain_exceeds_mock'] for x in tokens),
                   concatenations=len(concat),nonadditive=sum(not x['additive'] for x in concat),
                   certificates=c['certificates_issued'],lean_checks=c['lean_checks'],
                   source_tampers=c['source_tampers_rejected'],malformed_batches=c['malformed_batches_rejected'],
                   replay_cases=r['cases'],replay_paths=r['replay_paths'],external_projections=len(ext),
                   external_runs=sum(len(x['observations']) for x in ext),
                   external_bound_violations=sum(o['violates'] for x in ext for o in x['observations']),
                   external_baseline_disagreements=sum(x['production']!=x['structural'] for x in ext),
                   original_application_executions=manifests['external']['original_workflow_executions'],
                   spent_usd='0.00')
    summary = dict(metrics=metrics,
                   evidence={k:dict(path=v,sha256=hashlib.sha256((args.runs/v).read_bytes()).hexdigest(),
                                    source_commit=manifests[k].get('source_commit')) for k,v in files.items()})
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8',newline='\n')
    table = '| Projection | Max calls | Input bound | Output bound | Total bound | Mock runs |\n|---|---:|---:|---:|---:|---:|\n'
    tex = ('\\begin{tabular}{lrrrrr}\n\\hline\nProjection & Calls & Input & Output & Total & Runs \\\\\n\\hline\n')
    for row in ext:
        b=row['structural']
        values=[row['max_calls'],b['input'],b['output'],b['total'],len(row['observations'])]
        table += '| '+row['id']+' | '+' | '.join(map(str,values))+' |\n'
        tex += row['id'].replace('_',r'\_')+' & '+' & '.join(map(str,values))+' \\\\\n'
    tex += '\\hline\n\\end{tabular}\n'
    (args.output/'external.md').write_text(table,encoding='utf-8',newline='\n')
    (args.output/'external.tex').write_text(tex,encoding='utf-8',newline='\n')
    (args.output/'metrics.tex').write_text(''.join('\\newcommand{\\ev'+''.join(x.title() for x in k.split('_'))+'}{'+str(v)+'}\n' for k,v in metrics.items()),encoding='utf-8',newline='\n')
    print(json.dumps(metrics,indent=2))


if __name__ == '__main__':
    main()
