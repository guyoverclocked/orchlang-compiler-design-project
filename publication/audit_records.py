"""Independent, standard-library audit of retained records; no model execution."""
import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INC = ROOT / 'incoming-shape'
OUT = ROOT / 'evidence'
EXPECTED = dict(switch=210, routing=150, chaining=150, evaluator=100, email=152,
                orchestrator=100, calculator=100, crag=150, adaptive=60)

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []

def observation(trace):
    return tuple(('llm', e[1], e[2], e[3]) if e[0] == 'llm' else ('tool', e[1]) for e in trace)

def usage(row):
    tr = [e for e in row['trace'] if e[0] == 'llm']
    return dict(calls=len(tr), input=sum(e[2] for e in tr), output=sum(e[3] for e in tr),
                price=sum(e[2] + 4 * e[3] for e in tr))

def campaign(name):
    result = {}
    for wf, expected in EXPECTED.items():
        directory = INC / 'experiments/results' / name / wf
        original, shaped = rows(directory / 'orig.jsonl'), rows(directory / 'ours.jsonl')
        o, s = {r['id']: r for r in original}, {r['id']: r for r in shaped}
        ids = sorted(o.keys() & s.keys())
        static = load(directory / 'compile.json')['strategies']['ours']['lean']['static_shape'] if (directory / 'compile.json').exists() else None
        result[wf] = dict(expected=expected, original=len(original), shaped=len(shaped), paired=len(ids),
                          original_duplicates=len(original)-len(o), shaped_duplicates=len(shaped)-len(s),
                          unpaired_original=sorted(o.keys()-s.keys()), unpaired_shaped=sorted(s.keys()-o.keys()))
        if ids:
            distinct = {observation(s[i]['trace']) for i in ids}
            conform = sum(observation(s[i]['trace']) == tuple(tuple(e) for e in static) for i in ids) if static else None
            ou, su = [usage(o[i]) for i in ids], [usage(s[i]) for i in ids]
            result[wf].update(output_store_equal=sum(o[i]['store']==s[i]['store'] for i in ids),
                              full_trace_distinct=len(distinct), conformant=conform,
                              truncations=sum(s[i]['truncations'] for i in ids),
                              llm_events_original=sum(x['calls'] for x in ou), llm_events_shaped=sum(x['calls'] for x in su),
                              mean_original_usage={k: statistics.mean(x[k] for x in ou) for k in ou[0]},
                              mean_shaped_usage={k: statistics.mean(x[k] for x in su) for k in su[0]},
                              weighted_overhead=sum(x['price'] for x in su)/sum(x['price'] for x in ou))
    return result

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT/'remote'), *args], encoding='utf-8').strip()

def main():
    report = {name: campaign(name) for name in ('runs', 'runs-inband-preliminary')}
    report['main_totals'] = {key: sum(r.get(key, 0) for r in report['runs'].values()) for key in
                              ('expected','original','shaped','paired','output_store_equal','truncations','llm_events_original','llm_events_shaped')}
    report['replication_expected_pairs'] = 512
    report['replication_present'] = (INC/'experiments/results/runs/replication').exists()
    generated = load(INC/'paper/generated/results.json')
    report['generated_table_workflows'] = list(generated['workflows'])
    report['generated_table_counts'] = {wf: d['n'] for wf,d in generated['workflows'].items()}
    report['recorded_mutation_totals'] = load(INC/'experiments/results/mutation.json')['total']
    report['transparency'] = {name:load(INC/'experiments/results'/name).get('summary') for name in
                               ('transparency-isolated.json','transparency-inband.json')}
    files = {p.relative_to(INC).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (INC/'experiments/results').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    (OUT/'incoming-record-hashes.json').write_text(json.dumps(files,indent=2)+'\n')
    (OUT/'retained-record-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    refs = ['origin/main','disk/research-defensible-publication','origin/claude/trusting-clarke-c7eqeh',
            'origin/codex/scp-strengthening','origin/codex/publication-upgrade','origin/codex/research-upgrade']
    graph = {ref:dict(sha=git('rev-parse',ref),merge_base_with_disk=git('merge-base',ref,'disk/research-defensible-publication'),
                     distance_from_disk=git('rev-list','--left-right','--count',ref+'...disk/research-defensible-publication')) for ref in refs}
    graph['incoming_from_base_commits'] = git('rev-list','--count','origin/main..origin/claude/trusting-clarke-c7eqeh')
    graph['disk_from_base_commits'] = git('rev-list','--count','origin/main..disk/research-defensible-publication')
    graph['disk_cpp_diff_from_base'] = git('diff','--numstat','origin/main','disk/research-defensible-publication','--','src','include','tests/tests.cpp')
    graph['disk_changes_from_base'] = git('diff','--numstat','origin/main','disk/research-defensible-publication')
    (OUT/'branch-comparison.json').write_text(json.dumps(graph,indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('main_totals','generated_table_workflows','generated_table_counts','replication_present','recorded_mutation_totals')},indent=2))
    for wf,d in report['runs'].items():
        print(wf, {k:d.get(k) for k in ('paired','output_store_equal','full_trace_distinct','conformant','truncations','weighted_overhead')})

if __name__ == '__main__':
    main()
