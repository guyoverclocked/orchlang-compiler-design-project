"""Adversarial boundary probes of the incoming revision, without editing it."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'incoming-shape'))
from orchlang import compiler as K, core as C, models as M, runtime as R, syntax as S, validate as V

M.TEMPLATES['audit'] = M.Template('audit', None, '<{role}>{content}</>\n', '<a>', '<pad>', '</>\n')
PROFILE = M.Profile('m', '', 'audit', filler='.')
PROFILES = {'m':PROFILE}
TOKS = {'m':M.CharTokenizer()}
SOURCE = '''workflow Boundary {
input q: text secret max_tokens 4;
model m = "m";
prompt p(x) = user "{x}";
let r = call p(q) using m max_tokens 12;
output r;
}'''

def main():
    os.environ['LEAN'] = r'C:\Users\nambi\Documents\OrchLang Publication Work\tools\lean-4.19.0-windows\bin\lean.exe'
    prog = K.lower(S.parse(SOURCE), PROFILES)
    shaped = K.Shaper(prog, PROFILES, TOKS, 'ours').run()
    payloads = [V.payload(prog.high_vars(),prog.body,shaped,prog.secret_inputs()),
                V.payload([],prog.body,prog.body,prog.secret_inputs()),
                V.payload([],prog.body,prog.body,[])]
    verdicts = V.lean_validate_batch(payloads)
    rt = R.Runtime({'m':R.MockBackend(PROFILE)}, {}, {})
    forged_runs = [rt.run(prog.body,{0:q},0).observed() for q in ('a','bbbb')]

    class BrokenBackend(R.MockBackend):
        def generate(self,prompt,max_tokens,seed,forced,cap=None,pad_tokens=0):
            n = 1 if 'alpha' in prompt else 2
            return [ord('x')]*n, 'x'*n, self.count(prompt)+pad_tokens

    broken = R.Runtime({'m':BrokenBackend(PROFILE)}, {}, {})
    broken_runs = [broken.run(shaped,{0:q},0).observed() for q in ('alpha','b')]
    honest = R.Runtime({'m':R.MockBackend(PROFILE)}, {}, {})
    long_input = {0:'long input content '*100}
    before, after = honest.run(prog.body,long_input,0), honest.run(shaped,long_input,0)
    result = dict(source=SOURCE, payloads=payloads, lean_verdicts=verdicts,
        source_binding=dict(correct_metadata_accepts_shaped=verdicts[0]['accepted'],
            forgotten_label_with_independent_secret_list_rejected=not verdicts[1]['accepted'],
            forgotten_label_and_secret_list_accepts_unpadded=verdicts[2]['accepted'],
            accepted_unpadded_traces=forged_runs, traces_differ=forged_runs[0]!=forged_runs[1],
            interpretation='The JSON-supplied original and secret list remain trusted source bindings; this does not refute the conditional Lean theorem.'),
        runtime_conformance=dict(lean_accepted=verdicts[0]['accepted'], observed_traces=broken_runs,
            traces_differ=broken_runs[0]!=broken_runs[1],runtime_rejected=False,
            interpretation='A deliberately nonconforming backend is accepted by Runtime without output-length validation. This contradicts the runtime-checking prose, not World.Conforms => noninterference.'),
        overbound_input=dict(declared_max_tokens=4, supplied_char_tokens=len(long_input[0]),
            truncations=after.truncations, outputs_equal=before.store==after.store,
            runtime_rejected=False,
            interpretation='Inputs exceeding annotations can be silently truncated; functional preservation requires an enforced admissible-input domain.'))
    try:
        from tokenizers import Tokenizer
        directory=Path(r'C:\Users\nambi\Documents\OrchLang Publication Work\tokenizers-development-v1')
        bert=Tokenizer.from_file(str(directory/'bert-wordpiece.json'))
        gpt=Tokenizer.from_file(str(directory/'gpt2-bpe.json'))
        value='a'*1000
        class GPT:
            def count(self,text): return len(gpt.encode(text,add_special_tokens=False).ids)
        call=C.Call(1,1,'m',C.concat([C.ELit('<user>'),C.EVar(0),C.ELit('</>\n<a>')]),None,12)
        target=K.input_bound(call,{0:len(bert.encode(value,add_special_tokens=False).ids)},PROFILE,GPT())
        actual=GPT().count(C.eval_expr({0:value},call.req))
        result['cross_tokenizer_bound']=dict(bert_output_tokens=len(bert.encode(value,add_special_tokens=False).ids),
            gpt_request_tokens=actual,computed_target=target,underestimates=actual>target,
            interpretation='Scalar variable caps cannot be transferred between tokenizer units; runtime truncation can maintain shape while changing requests.')
    except ImportError:
        result['cross_tokenizer_bound']={'status':'tokenizers unavailable'}
    path=ROOT/'evidence/incoming-boundary-probes.json'
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source','payloads','lean_verdicts')},indent=2))

if __name__=='__main__': main()
