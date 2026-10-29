"""Inspect every native GGUF piece and falsify the byte-token envelope contract.

Exhaustive finite vocabulary checks support concrete constants. They do not
mechanize the native tokenizer algorithm or establish its correctness on all
strings; that implementation remains an explicit trusted primitive.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from orchlang import assurance as A, models as M


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    profiles=M.load_profiles(str(args.models))
    generator=random.Random(2901026)
    cases=['','a',' '*128,'\\'*128,'\x00','\x1f','漢字🙂'*128,
           '<|eot_id|>','<|im_start|>assistant\n','\u0085\u2028\u2029\u3000']
    alphabet='abcABC0123 \\{}[]<>\n\t漢字🙂é\x00\x1f'
    cases += [''.join(generator.choice(alphabet) for _ in range(generator.randrange(513))) for _ in range(2048)]
    summary={}
    for key,profile in profiles.items():
        tokenizer=M.tokenizer_for(profile.gguf)
        model=tokenizer._m
        lengths=[]
        witnesses=[]
        byte_pieces=set()
        for token in range(model.n_vocab()):
            piece=M.token_piece_bytes(model,token)
            lengths.append(len(piece))
            if len(piece)==1:
                byte_pieces.add(piece[0])
            if len(piece)>32:
                witnesses.append(dict(id=token,bytes=len(piece),wrapper_bytes=len(model.detokenize([token]))))
        maximum=max(lengths)
        raw_byte_replacements=[]
        for byte in range(256):
            ids=model.tokenize(bytes([byte]),add_bos=False,special=False)
            if len(ids)!=1 or M.detokenize_bytes(model,ids)!=bytes([byte]):
                raw_byte_replacements.append(byte)
        violations=[dict(index=i,bytes=len(text.encode('utf-8')),tokens=tokenizer.count(text))
                    for i,text in enumerate(cases) if tokenizer.count(text)>len(text.encode('utf-8'))]
        target=args.output/f'{key}-piece-lengths.json'
        target.write_text(json.dumps(lengths)+'\n',encoding='utf-8')
        witness=next(r for r in witnesses if r['bytes']==maximum)
        summary[key]=dict(gguf_sha256=A.sha256(profile.gguf),vocabulary_size=len(lengths),
                          maximum_piece_bytes=maximum,maximum_witness=witness,
                          pieces_exceeding_32_bytes=len(witnesses),
                          complete_byte_fallback_coverage=byte_pieces==set(range(256)),
                          missing_single_byte_pieces=sorted(set(range(256))-byte_pieces),
                          raw_single_byte_input_replacements=raw_byte_replacements,
                          raw_byte_probe_scope='Bytes 128..255 alone are invalid UTF-8, outside the String/input-guard contract.',
                          tokenizer_alpha_candidate=1,tokenizer_delta_candidate=0,
                          complete_request_cases=len(cases),token_bound_violations=violations,
                          piece_lengths_sha256=A.sha256(target),
                          metadata={k:v for k,v in model.metadata.items() if k in
                                    ('tokenizer.ggml.model','tokenizer.ggml.pre','llama.context_length','qwen2.context_length')})
        print(key,maximum,'bytes;',len(witnesses),'long pieces;',len(violations),'token-bound violations',flush=True)
    result=dict(schema='orchlang-concrete-vocabulary-envelope-v1',models=summary,
                python_wrapper_version=importlib.metadata.version('llama-cpp-python'),
                decoder_implementation_sha256=A.sha256(ROOT/'orchlang/models.py'),
                native_libraries={p.name:A.sha256(p) for p in Path(os.environ['ORCHLANG_GGML_BACKENDS']).glob('*.dll')}
                    if os.environ.get('ORCHLANG_GGML_BACKENDS') else {},
                native_tokenizer_algorithm_verified=False,
                interpretation='Finite table constants and fallback checks; universal tokenizer behavior remains a trusted byte-BPE algorithm contract.')
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
