"""Generate current-study tables only after every declared cohort is complete."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from publication.audit_homogeneous import rows,event_key
from publication.audit_execution import audit_record
from publication.analyze_referee_revision import local_checks
from orchlang import models as M,assurance as A

NAMES={'switch':'PF switch','routing':'Routing','chaining':'Chaining','evaluator':'Evaluator',
       'email':'Email','orchestrator':'Orchestrator','calculator':'Calculator','crag':'Corrective RAG','adaptive':'Adaptive RAG'}

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def percent(value):return f'{100*value:.1f}'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--study',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    evidence=ROOT/'publication/evidence'
    result=read(evidence/'round2-full-audit.json')
    assert result['complete'] and result['pairs']==1684
    assert result['all_paired_outputs_equal'] and result['all_shapes_equal']
    args.output.mkdir(parents=True,exist_ok=False)
    table=[];metrics=[]
    for group,total in [('main',1172),('replication',512)]:
        analyzed=read(evidence/f'round2-{group}-analysis/results.json')['workflows']
        assert sum(row['n'] for row in analyzed.values())==total
        for name,row in analyzed.items():
            attack=row['leak']['orig']['decision'];shaped=row['leak']['ours']['decision']
            assert row['function']['output_equal']==1 and row['conformant_runs']==row['n']
            assert row['leak']['ours']['distinct']==1 and shaped['mi_bits']==0
            ratio=row['ours_cost']['price']/row['orig_cost']['price']
            label=NAMES[name]+(' (Q)' if group=='replication' else '')
            ba=percent(attack['balanced']) if attack['classes']>1 else '--'
            acc=percent(row['function']['orig_acc']) if 'orig_acc' in row['function'] else '--'
            table.append(f"{label} & {row['n']} & {attack['classes']} & {ba} & 1 & 0 & {ratio:.2f} & {acc} \\\\")
            metrics.append(dict(group=group,workflow=name,n=row['n'],classes=attack['classes'],
                                original_BA=attack['balanced'] if attack['classes']>1 else None,
                                weighted_ratio=ratio,task_accuracy=row['function'].get('orig_acc')))
        if group=='main':table.append(r'\midrule')
    (ROOT/'paper/generated/round2-workflows.tex').write_text('\n'.join(table)+'\n',encoding='utf-8')
    concrete=evidence/'round2-concrete-admission-v3'
    assert (concrete/'execution-finished.json').exists()
    prepared=read(concrete/'protocol.json');certificate_rows=[];pairs=[];clips=Counter();local_calls=0
    profiles=M.load_profiles(str(concrete.parent/'round2-categorical-full/models.json'))
    by_contract={profile.key:profile for profile in profiles.values()}
    tokenizers={key:M.tokenizer_for(profile.gguf) for key,profile in by_contract.items()}
    for item in prepared['workflows']:
        directory=concrete/item['group']/item['workflow']
        completed=read(directory/'results.json');attempts=read(directory/'attempts.json')
        assert item['core_accepted'] and item['static_admission_accepted']
        assert completed['negative_guard']['refused_before_dispatch']
        assert len(completed['pairs'])==2 and all(all(p[k] for k in ('completed','full_store_equal','saved_equal','shape_equal')) for p in completed['pairs'])
        pairs.extend(completed['pairs'])
        for attempt in attempts:
            assert attempt['status']=='completed' and attempt['usage']['usage_complete']
            clips.update(clip['kind'] for clip in attempt['byte_clips'])
            events=attempt['execution_events'];traces=[e for e in attempt['trace'] if e[0]=='llm']
            for trace,event in zip(traces,events):
                tok=tokenizers[trace[1]]
                assert tok.encode(event['request'])==event['request_token_ids']
                ids=event['generated_token_ids'];stops={tok._m.token_eos()}
                stops.update(tok.encode(stop)[0] for stop in by_contract[trace[1]].stop)
                end=next((i for i,t in enumerate(ids) if t in stops),len(ids))
                if event['visible_cap'] is not None:end=min(end,event['visible_cap'])
                assert tok.decode(ids[:end])==event['visible_response_before_byte_bound']
                from orchlang.admission import clip_utf8
                assert clip_utf8(event['visible_response_before_byte_bound'],event['visible_byte_limit'])==event['visible_response']
            audit_record(dict(attempt,execution_events=[dict(event,visible_response=event['visible_response_before_byte_bound'])
                                                       for event in events]),tokenizers,by_contract)
            expected=Counter(event_key(dict(model=trace[1],**dict(event,visible_response=event['visible_response_before_byte_bound']))) for trace,event in zip(traces,events))
            actual=Counter()
            for call in attempt['local_observations']:
                assert not local_checks(call)
                actual[event_key(call)]+=1;local_calls+=1
            assert actual==expected
        bound=max(event[2]+event[3] for event in item['shape'] if event[0]=='llm')
        label=NAMES[item['workflow']]+(' (Q)' if item['group']=='qwen' else '')
        certificate_rows.append(f"{label} & {item['guard_admitted']}/{item['dataset_inputs']} & {bound:,} & 2/2 \\\\")
    assert len(pairs)==24
    (ROOT/'paper/generated/round2-admission.tex').write_text('\n'.join(certificate_rows)+'\n',encoding='utf-8')
    native=[];native_rows=[]
    for directory,label in [('batch-128','128'),('microbatch-1','1'),('cache-erasure','128 + cache removal')]:
        receipt=read(evidence/'round2-native-prefill'/directory/'summary.json')
        attempts=read(evidence/'round2-native-prefill'/directory/'attempts.json')
        assert receipt['attempted']==receipt['completed']==12
        assert receipt['single_exact_prefill']==receipt['useful_length_recoverable_from_sequence_metadata']==12
        assert all([c['shaped']['native_submissions'][0]['n_tokens']]==[128] and
                   [e['n_tokens'] for e in c['shaped']['native_submissions'][1:]]==[1]*23 for c in attempts)
        native.append(dict(configuration=directory,**receipt))
        native_rows.append(f"{label} & 12 & 12 & {receipt['equal']} & 12 \\\\")
    (ROOT/'paper/generated/round2-native.tex').write_text('\n'.join(native_rows)+'\n',encoding='utf-8')
    categorical=evidence/'round2-categorical-full'
    assert (categorical/'execution-finished.json').exists()
    data={condition:{row['id']:row for row in rows(categorical/f'run/{condition}.jsonl')} for condition in ('orig','ours')}
    assert len(data['orig'])==len(data['ours'])==150 and set(data['orig'])==set(data['ours'])
    event_counts=Counter();audited=0
    for condition in data.values():
        for row in condition.values():
            audited+=audit_record(row,tokenizers,by_contract)
            assert not row['truncations']
            event_counts.update(event_key(dict(model=trace[1],**event)) for trace,event in zip([t for t in row['trace'] if t[0]=='llm'],row['execution_events']))
    local=Counter()
    for call in rows(categorical/'run/local-calls.jsonl'):
        assert not local_checks(call);local[event_key(call)]+=1
    assert event_counts==local
    grades=Counter();routes=Counter();equal=0
    from experiments.aggregate import scorer
    items={row['id']:row for row in rows(ROOT/'experiments/data/crag.jsonl')}
    scores=[]
    for key,original in data['orig'].items():
        equal+=original['store']==data['ours'][key]['store']
        routes[original['store']['search']]+=1
        scores.append(scorer('crag',items[key])(original))
        for index in range(4):
            grade=json.loads(original['store'][f'g{index}'])['score']
            assert grade in ('yes','no');grades[grade]+=1
    shaped_traces={json.dumps([e[:4] if e[0]=='llm' else e[:2] for e in r['trace']]) for r in data['ours'].values()}
    assert equal==150 and len(shaped_traces)==1 and sum(grades.values())==600
    primary={row['id']:row for row in rows(args.study/'replication/crag/orig.jsonl')}
    assert set(primary)==set(data['orig'])
    primary_correct={key:scorer('crag',items[key])(row) for key,row in primary.items()}
    revised_correct={key:scorer('crag',items[key])(row) for key,row in data['orig'].items()}
    changes=Counter('improved' if revised_correct[key] else 'regressed'
                    for key in primary if primary_correct[key]!=revised_correct[key])
    crag=dict(pairs=150,saved_equal=equal,grade_counts=dict(grades),routes=dict(routes),
              task_accuracy=sum(scores)/len(scores),local_model_calls=audited,distinct_shaped_traces=len(shaped_traces),
              correct=sum(scores),primary_correct=sum(primary_correct.values()),
              primary_accuracy=sum(primary_correct.values())/150,paired_changes=dict(changes))
    vocabulary=read(evidence/'round2-vocabulary-v2/summary.json')
    ratios=[r['weighted_ratio'] for r in metrics if r['group']=='main']
    macros=dict(roundTwoPairs=result['pairs'],roundTwoCalls=result['local_model_calls'],
                roundTwoMedian=f'{statistics.median(ratios):.2f}',roundTwoMin=f'{min(ratios):.2f}',roundTwoMax=f'{max(ratios):.2f}',
                roundTwoGuard=sum(r['guard_admitted'] for r in prepared['workflows']),
                roundTwoByteCalls=local_calls,roundTwoToolClips=clips['tool'],roundTwoResponseClips=clips['llm'],
                categoricalYes=grades['yes'],categoricalNo=grades['no'],categoricalSearch=routes['yes'],
                categoricalNoSearch=routes['no'],categoricalTask=percent(crag['task_accuracy']),
                categoricalCorrect=crag['correct'],categoricalPrimaryCorrect=crag['primary_correct'],
                categoricalImproved=changes['improved'],categoricalRegressed=changes['regressed'])
    (ROOT/'paper/generated/round2-results.tex').write_text(''.join(f'\\newcommand{{\\{key}}}{{{value}}}\n' for key,value in macros.items()),encoding='utf-8')
    write(args.output/'summary.json',dict(driver_sha256=A.sha256(__file__),full=result,metrics=metrics,concrete=dict(pairs=len(pairs),local_model_calls=local_calls,
          guard_admitted=macros['roundTwoGuard'],clips=dict(clips)),native=native,categorical=crag,
          vocabulary={key:{k:v for k,v in item.items() if k in ('vocabulary_size','maximum_piece_bytes','pieces_exceeding_32_bytes','complete_request_cases')}
                      for key,item in vocabulary['models'].items()}))
    print(json.dumps(dict(macros=macros,categorical=crag),indent=2))

if __name__=='__main__':main()
