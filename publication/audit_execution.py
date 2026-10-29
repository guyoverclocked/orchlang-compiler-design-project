"""Independent record audit; optional re-tokenization uses the pinned GGUFs.

This checks retained observations, not external billing or physical attestation.
Active files may have an explicitly reported incomplete trailing write.
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def snapshot(path):
    if not path.exists():return {},False
    raw=path.read_bytes();partial=bool(raw and not raw.endswith(b'\n'))
    lines=raw.split(b'\n')[:-1]
    result={}
    for line in lines:
        if not line.strip():continue
        row=json.loads(line)
        if row['id'] in result:raise ValueError('duplicate retained ID: '+str(path))
        result[row['id']]=row
    return result,partial


def audit_record(row,tokenizers=None,profiles=None):
    llms=[e for e in row['trace'] if e[0]=='llm']
    events=row['execution_events']
    assert len(llms)==len(events),'private/public event denominator'
    totals=defaultdict(lambda:dict(input=0,output=0,calls=0))
    for trace,event in zip(llms,events):
        _,model,inp,out,*_=trace
        assert hashlib.sha256(event['request'].encode('utf-8')).hexdigest()==event['request_sha256'],'request hash'
        assert len(event['request_token_ids'])+event['isolated_pad_tokens']==inp,'complete input count'
        assert len(event['generated_token_ids'])==out,'generated-ID count'
        cap=event['generation_cap']
        assert out==cap if event['forced'] else out<=cap,'output cap'
        for key in ('request_token_ids','generated_token_ids'):
            assert all(type(t) is int and t>=0 for t in event[key]),'invalid token ID'
        if tokenizers is not None:
            tok=tokenizers[model]
            assert tok.encode(event['request'])==event['request_token_ids'],'pinned request re-tokenization'
            stops={tok._m.token_eos()}
            for stop in profiles[model].stop:
                ids=tok.encode(stop)
                assert len(ids)==1,'unsupported mult-token stop'
                stops.add(ids[0])
            ids=event['generated_token_ids']
            end=next((i for i,t in enumerate(ids) if t in stops),len(ids))
            if event['visible_cap'] is not None:end=min(end,event['visible_cap'])
            assert tok.decode(ids[:end])==event['visible_response'],'visible prefix reconstruction'
        totals[model]['input']+=inp;totals[model]['output']+=out;totals[model]['calls']+=1
    assert row['usage']['usage_complete'],'completed record has unknown usage'
    assert dict(totals)==row['usage']['confirmed'],'model-indexed ledger differs from trace'
    assert not row['usage']['unconfirmed'],'completed record retains a pending dispatch'
    return len(events)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',help='optional pinned model config for re-tokenization and visible-prefix reconstruction')
    parser.add_argument('--output',type=Path,help='new immutable audit receipt')
    parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    tokenizers=profiles=contracts=None
    if args.models:
        from orchlang import models as M,assurance as A
        raw=M.load_profiles(args.models)
        contracts=A.model_contracts(raw)
        profiles={profile.key:profile for profile in raw.values()}
        tokenizers={key:M.tokenizer_for(profile.gguf) for key,profile in profiles.items()}
    result=dict(schema='orchlang-independent-record-audit-v1',utc=datetime.now(timezone.utc).isoformat(),
                request_retokenized=bool(tokenizers),visible_prefix_reconstructed=bool(tokenizers),
                records=0,llm_events=0,campaigns={},failures=[],active_trailing_writes=[])
    first=None
    for directory in sorted((ROOT/'publication/evidence/completion').glob('*/*')):
        manifest_path=directory/'run-manifest.json'
        if not manifest_path.exists():continue
        manifest=json.loads(manifest_path.read_text())
        allowed=set(manifest['selected_ids'])
        if contracts is not None:
            for key,expected in manifest['model_contracts'].items():
                assert contracts[key]==expected,'configured model differs from retained contract: '+key
        counts={}
        for condition in ('orig','ours'):
            path=directory/f'{condition}.jsonl'
            rows,partial=snapshot(path)
            assert not set(rows)-allowed,'foreign retained IDs'
            if partial:result['active_trailing_writes'].append(str(path.relative_to(ROOT)))
            counts[condition]=len(rows)
            for item_id,row in rows.items():
                try:
                    result['llm_events']+=audit_record(row,tokenizers,profiles)
                    result['records']+=1
                    if first is None and row['execution_events']:first=row
                except (AssertionError,KeyError,ValueError) as error:
                    result['failures'].append(dict(campaign=str(directory.relative_to(ROOT)),condition=condition,id=item_id,error=str(error)))
        result['campaigns'][str(directory.relative_to(ROOT))]=counts
    if args.self_check:
        from copy import deepcopy
        assert first is not None,'no completed record available for the negative control'
        changed=deepcopy(first)
        next(e for e in changed['trace'] if e[0]=='llm')[2]+=1
        try:audit_record(changed)
        except AssertionError:result['tampered_count_detected']=True
        else:raise AssertionError('record auditor accepted a deliberately wrong input count')
    result['status']='failed' if result['failures'] else 'verified-completed-prefix'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
    return int(bool(result['failures']))


if __name__=='__main__':raise SystemExit(main())
