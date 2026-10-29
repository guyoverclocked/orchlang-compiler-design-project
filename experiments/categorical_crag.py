"""Separate CRAG ablation: unambiguous categorical prompt plus contracted grammar.

The original any-negative-document search rule and dataset are retained. Branch
diversity is measured, never forced by relabeling examples or changing that rule.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--implementation',type=Path,required=True)
    ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--limit',type=int,default=0)
    args=ap.parse_args()
    implementation=args.implementation.resolve()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(implementation))
    from orchlang import runtime as R, assurance as A
    from experiments import run_workflow as runner
    from experiments.referee_revision import InstrumentedBackend
    original=(implementation/'workflows/replication/crag_qwen.orch').read_text(encoding='utf-8')
    prompt=('Decide whether the FACT contains information that helps answer the QUESTION. '
            'Return exactly {"score":"yes"} or {"score":"no"}. Do not explain.\n'
            'QUESTION: {question}\nFACT: {documents}')
    source,count=re.subn(r'  prompt grader\(question, documents\) = user ".*?";\n',
                        lambda _: '  prompt grader(question, documents) = user '+json.dumps(prompt)+';\n',
                        original,flags=re.S)
    assert count==1
    source=source.replace('  model llm = "qwen1.5b";',
                          '  model llm = "qwen1.5b";\n  model grader = "qwen-categorical";')
    assert source.count('using llm max_tokens 16;')==4
    source=source.replace('using llm max_tokens 16;','using grader max_tokens 16;')
    path=output/'categorical-crag.orch'
    path.write_text(source,encoding='utf-8')
    config=json.loads(args.models.read_text(encoding='utf-8'))
    for profile in config.values():
        profile['gguf']=str((args.models.resolve().parent/profile['gguf']).resolve())
    grammar=r'root ::= "{\"score\":\"yes\"}" | "{\"score\":\"no\"}"'
    config['qwen-categorical']={**config['qwen1.5b'],'decoding_grammar':grammar}
    model_path=output/'models.json'
    model_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    protocol=dict(schema='orchlang-categorical-crag-ablation-v1',implementation=runner.source_checkout_identity(implementation),
                  implementation_hashes=A.implementation_hashes(implementation),
                  driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  source_sha256=A.sha256(path),grammar=grammar,
                  routing_rule='unchanged: web search if any of four grades is not yes',limit=args.limit,
                  primary_corpus_modified=False)
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    class StreamingBackend(InstrumentedBackend):
        def generate(self,*values,**options):
            try:
                return super().generate(*values,**options)
            finally:
                with (output/'run/local-calls.jsonl').open('a',encoding='utf-8') as stream:
                    for call in self.calls:
                        stream.write(json.dumps(dict(model=self.profile.key,**call))+'\n')
                self.calls.clear()
    R.LlamaBackend=StreamingBackend
    os.chdir(implementation)
    sys.argv=['run_workflow','--workflow',str(path),'--data','experiments/data/crag.jsonl',
              '--models',str(model_path),'--out',str(output/'run'),'--keep','answer,search,g0,g1,g2,g3',
              '--corpus','experiments/data/crag_corpus.jsonl','--web','experiments/data/crag_web.jsonl']
    if args.limit: sys.argv+=['--limit',str(args.limit)]
    runner.main()
    (output/'execution-finished.json').write_text(json.dumps(dict(completed=True))+'\n',encoding='utf-8')


if __name__=='__main__':main()
