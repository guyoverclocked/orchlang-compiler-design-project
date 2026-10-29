"""Single-native-batch, sequence-isolated prefill prototype (greedy only).

The batch-size projection hides useful request length. Sequence membership,
positions and requested-logit metadata still expose it; this experiment does not
claim confidentiality against an observer with access to those fields.
"""
import argparse
from collections import Counter
import gc
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orchlang import models as M, runtime as R, assurance as A


class SequenceBatchBackend(R.LlamaBackend):
    def __init__(self,profile,ubatch=128):
        from contextlib import closing
        super().__init__(profile,n_ctx=4096,n_threads=4,temperature=0)
        from llama_cpp._internals import LlamaContext
        self.m._ctx.close()
        self.m.context_params.n_seq_max=2
        self.m.context_params.n_ubatch=ubatch
        self.m._ctx=self.m._stack.enter_context(closing(LlamaContext(model=self.m._model,
                         params=self.m.context_params,verbose=False)))

    def decode_batch(self,tokens,sequences,positions,logits,phase,observations):
        batch=self.m._batch
        if len(tokens)>batch._n_tokens:
            raise ValueError('prototype requires one native prefill batch within n_batch')
        batch.batch.n_tokens=len(tokens)
        for index,token in enumerate(tokens):
            batch.batch.token[index]=token
            batch.batch.pos[index]=positions[index]
            batch.batch.seq_id[index][0]=sequences[index]
            batch.batch.n_seq_id[index]=1
            batch.batch.logits[index]=logits[index]
        observations.append(dict(phase=phase,n_tokens=len(tokens),token_ids=tokens,
                                 sequence_ids=sequences,positions=positions,logits=logits))
        self.m._ctx.decode(batch)

    def masked_generate(self,prompt,target,forced,cap,drop_cover_cache=False):
        import numpy as np
        request=self.encode(prompt)
        if len(request)>target:
            raise ValueError('request exceeds single-batch target')
        self.m.reset()
        self.m._ctx.kv_cache_clear()
        filler=self.encode_plain(self.profile.filler)[-1]
        pad=target-len(request)
        observations=[]
        tokens=request+[filler]*pad
        sequences=[0]*len(request)+[1]*pad
        positions=list(range(len(request)))+list(range(pad))
        logits=[False]*target
        logits[len(request)-1]=True
        self.decode_batch(tokens,sequences,positions,logits,'prefill',observations)
        cache_operations=[]
        if drop_cover_cache:
            removed=self.m._ctx.kv_cache_seq_rm(1,0,-1)
            if removed is False:
                raise RuntimeError('cover cache removal failed')
            cache_operations.append(dict(operation='remove_sequence',sequence=1,begin=0,end=-1))
        out=[]
        first_stop=None
        for index in range(forced):
            scores=np.ctypeslib.as_array(self.m._ctx.get_logits_ith(-1),shape=(self.m.n_vocab(),))
            token=int(np.argmax(scores))
            if token in self.stop_ids and first_stop is None:
                first_stop=len(out)
            out.append(token)
            if index+1<forced:
                self.decode_batch([token],[0],[len(request)+index],[True],'decode',observations)
        visible=out[:min(cap,len(out) if first_stop is None else first_stop)]
        return dict(request_ids=request,output_ids=out,visible=self.decode(visible),
                    native_submissions=observations,cache_operations=cache_operations,
                    target=target,forced=forced,cap=cap)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--ubatch',type=int,default=128)
    ap.add_argument('--drop-cover-cache',action='store_true')
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    profiles=M.load_profiles(str(args.models))
    prompts=['','Reply with exactly OK.','Reply in one word: café 漢字🙂 a b c.']
    protocol=dict(schema='orchlang-native-prefill-protocol-v1',
                  driver_sha256=A.sha256(__file__),implementation=A.implementation_hashes(ROOT),
                  model_contracts=A.model_contracts({k:profiles[k] for k in ('llama1b','qwen1.5b')}),
                  prompts=prompts,visible_caps=[4,16],target=128,forced=24,
                  context=4096,threads=4,native_microbatch=args.ubatch,
                  drop_cover_cache=args.drop_cover_cache,
                  gpu_layers=os.environ.get('ORCHLANG_GPU_LAYERS','0'),
                  native_libraries={p.name:A.sha256(p) for p in Path(os.environ['ORCHLANG_GGML_BACKENDS']).glob('*.dll')}
                    if os.environ.get('ORCHLANG_GGML_BACKENDS') else {})
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    cases=[]
    for family in ('llama1b','qwen1.5b'):
        backend=SequenceBatchBackend(profiles[family],args.ubatch)
        for index,text in enumerate(prompts):
            prompt=profiles[family].tmpl.render([('user',text)])
            for cap in (4,16):
                backend.m._ctx.kv_cache_clear()
                natural_submissions=[]
                original_decode=backend.m._ctx.decode
                def record_natural(batch):
                    native=batch.batch
                    natural_submissions.append(dict(n_tokens=native.n_tokens,
                        sequence_ids=[native.seq_id[i][0] for i in range(native.n_tokens)],
                        positions=[native.pos[i] for i in range(native.n_tokens)]))
                    return original_decode(batch)
                backend.m._ctx.decode=record_natural
                try:
                    natural=backend.generate(prompt,cap,0,False)
                finally:
                    backend.m._ctx.decode=original_decode
                try:
                    shaped=backend.masked_generate(prompt,128,24,cap,args.drop_cover_cache)
                    prefills=[r for r in shaped['native_submissions'] if r['phase']=='prefill']
                    result=dict(family=family,prompt=index,cap=cap,status='completed',natural=natural[1],
                                natural_output_ids=natural[0],natural_submissions=natural_submissions,
                                equal=natural[1]==shaped['visible'],single_prefill=len(prefills)==1,
                                exact_prefill=len(prefills)==1 and prefills[0]['n_tokens']==128,
                                useful_length_recoverable=Counter(prefills[0]['sequence_ids'])[0]==len(shaped['request_ids']),
                                shaped=shaped)
                except Exception as error:
                    result=dict(family=family,prompt=index,cap=cap,status='failed',error=repr(error),natural=natural[1])
                cases.append(result)
                (args.output/'attempts.json').write_text(json.dumps(cases,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
                print(family,index,cap,result['status'],result.get('equal'),flush=True)
        del backend
        gc.collect()
    result=dict(schema='orchlang-sequence-isolated-prefill-v1',attempted=len(cases),
                completed=sum(r['status']=='completed' for r in cases),equal=sum(r.get('equal',False) for r in cases),
                single_exact_prefill=sum(r.get('single_prefill',False) and r.get('exact_prefill',False) for r in cases),
                useful_length_recoverable_from_sequence_metadata=sum(r.get('useful_length_recoverable',False) for r in cases),
                projections={family:dict(
                    natural_distinct_size_traces=len({tuple(x['n_tokens'] for x in r['natural_submissions'])
                        for r in cases if r['family']==family and r['status']=='completed'}),
                    shaped_distinct_size_traces=len({tuple(x['n_tokens'] for x in r['shaped']['native_submissions'])
                        for r in cases if r['family']==family and r['status']=='completed'})) for family in ('llama1b','qwen1.5b')},
                native_libraries={p.name:A.sha256(p) for p in Path(os.environ['ORCHLANG_GGML_BACKENDS']).glob('*.dll')}
                  if os.environ.get('ORCHLANG_GGML_BACKENDS') else {},
                gpu_layers=os.environ.get('ORCHLANG_GPU_LAYERS','0'),native_microbatch=args.ubatch,
                drop_cover_cache=args.drop_cover_cache,greedy_only=True,
                trust='local native-API instrumentation; no server/network/timing refinement')
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
