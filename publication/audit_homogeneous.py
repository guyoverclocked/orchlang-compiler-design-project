"""Strictly audit every planned pair and native-API record in the full rerun."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from publication.audit_execution import audit_record
from publication.analyze_referee_revision import local_checks
from orchlang import assurance as A, models as M


def rows(path):
    raw=path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('partial trailing record: '+str(path))
    for line in raw.split(b'\n'):
        if line.strip(): yield json.loads(line)


def event_key(event):
    # Digest complete arrays while preserving duplicate multiplicities.
    value=[event.get('model'),event['request_sha256'],event['seed'],event['request_token_ids'],
           event.get('generated_token_ids',event.get('returned_ids')),event.get('visible_response',event.get('visible'))]
    return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory',type=Path)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    protocol=json.loads((args.directory/'protocol.json').read_text())
    if not (args.directory/'execution-finished.json').exists():
        raise ValueError('campaign is not finished')
    profiles=M.load_profiles(str(args.models))
    by_contract={profile.key:profile for profile in profiles.values()}
    tokenizers={key:M.tokenizer_for(profile.gguf) for key,profile in by_contract.items()}
    contracts=A.model_contracts(profiles)
    expected_commit=protocol['implementation']['git_commit']
    summary=[]
    dirty_explained=[]
    first=None
    for planned in protocol['plan']:
        group='replication' if planned['replication'] else 'main'
        directory=args.directory/group/planned['workflow']
        manifest=json.loads((directory/'run-manifest.json').read_text())
        assert manifest['git_commit']==expected_commit
        if manifest['git_dirty']:
            # A dirty flag is accepted only if every hashed implementation file
            # equals its blob in the recorded commit (non-code edits only).
            import subprocess
            for name,expected in manifest['implementation_sha256'].items():
                blob=subprocess.run(['git','-C',str(ROOT),'show',expected_commit+':'+name.replace(chr(92),'/')],
                                    capture_output=True,check=True).stdout
                assert hashlib.sha256(blob).hexdigest()==expected,'dirty run changed implementation: '+name
            dirty_explained.append(planned['workflow'])
        assert manifest['implementation_sha256']==protocol['implementation_hashes']
        for name,expected in manifest['implementation_sha256'].items():
            assert A.sha256(ROOT/name)==expected,'final production implementation differs from inference freeze: '+name
        assert manifest['backend_libraries']==protocol['backend_libraries']
        for model,expected in manifest['model_contracts'].items():
            assert contracts[model]==expected
        allowed=set(manifest['selected_ids'])
        assert len(allowed)==len(manifest['selected_ids'])==planned['pairs']
        refused=set()
        if (directory/'guard-refusals.jsonl').exists():
            refused={row['id'] for row in rows(directory/'guard-refusals.jsonl')}
            assert refused<=allowed and manifest.get('byte_bounded')
        allowed-=refused
        data={}
        event_counts=Counter()
        calls=0
        for condition in ('orig','ours'):
            data[condition]={}
            for row in rows(directory/(condition+'.jsonl')):
                assert row['id'] in allowed and row['id'] not in data[condition]
                calls+=audit_record(row,tokenizers,by_contract)
                event_counts.update(event_key(dict(model=trace[1],**event))
                                    for trace,event in zip([t for t in row['trace'] if t[0]=='llm'],row['execution_events']))
                assert not row['truncations']
                data[condition][row['id']]=row
                first=first or row
            assert set(data[condition])==allowed
        local_counts=Counter()
        local_calls=0
        for call in rows(directory/'local-calls.jsonl'):
            assert call['status']=='completed'
            assert not local_checks(call)
            local_counts[event_key(call)]+=1
            local_calls+=1
        assert event_counts==local_counts and calls==local_calls
        compile_info=json.loads((directory/'compile.json').read_text())
        shape=compile_info['strategies']['ours']['lean']['static_shape']
        observed=lambda row:[e[:4] if e[0]=='llm' else e[:2] for e in row['trace']]
        paired=sum(data['orig'][key]['store']==data['ours'][key]['store'] for key in allowed)
        shapes=sum(observed(row)==shape for row in data['ours'].values())
        failures=list(rows(directory/'failures.jsonl')) if (directory/'failures.jsonl').exists() else []
        assert not failures
        assert all(row['source_binding_sha256']==compile_info['source_binding']['binding_sha256']
                   for condition in data.values() for row in condition.values())
        summary.append(dict(group=group,workflow=planned['workflow'],pairs=len(allowed),guard_refused=len(refused),
                            saved_equal=paired,shape_equal=shapes,local_model_calls=calls,
                            distinct_shaped_traces=len({json.dumps(observed(row)) for row in data['ours'].values()}),
                            output_mismatches=[key for key in allowed if data['orig'][key]['store']!=data['ours'][key]['store']],
                            shape_mismatches=[key for key,row in data['ours'].items() if observed(row)!=shape]))
        print(group,planned['workflow'],len(allowed),'pairs;',paired,'equal;',calls,'calls',flush=True)
    damaged=deepcopy(first)
    next(event for event in damaged['trace'] if event[0]=='llm')[2]+=1
    try:
        audit_record(damaged)
    except AssertionError:
        detected=True
    else:
        raise AssertionError('negative audit control was missed')
    result=dict(schema='orchlang-homogeneous-full-audit-v1',commit=expected_commit,
                pairs=sum(r['pairs'] for r in summary),records=2*sum(r['pairs'] for r in summary),
                saved_equal=sum(r['saved_equal'] for r in summary),shape_equal=sum(r['shape_equal'] for r in summary),
                local_model_calls=sum(r['local_model_calls'] for r in summary),workflows=summary,
                complete=True,changed_count_detected=detected,guard_refused=sum(r['guard_refused'] for r in summary),
                dirty_flag_with_unchanged_implementation=dirty_explained,
                all_paired_outputs_equal=all(r['saved_equal']==r['pairs'] for r in summary),
                all_shapes_equal=all(r['shape_equal']==r['pairs'] for r in summary))
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='workflows'},indent=2))


if __name__=='__main__':main()
