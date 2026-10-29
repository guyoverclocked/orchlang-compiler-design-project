"""Auditable range downloader for existing public pinned model artifacts."""
import concurrent.futures
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'unified-publication'))
sys.path.insert(0,str(ROOT/'unified-publication/experiments'))
# This standalone downloader intentionally does not require Hugging Face's Xet
# client. The source-protocol identities are copied without changing their pins.
MODELS={
 'llama1b':('bartowski/Llama-3.2-1B-Instruct-GGUF','067b946cf014b7c697f3654f621d577a3e3afd1c','Llama-3.2-1B-Instruct-Q4_K_M.gguf','llama3','6f85a640a97cf2bf5b8e764087b1e83da0fdb51d7c9fab7d0fece9385611df83'),
 'llama3b':('bartowski/Llama-3.2-3B-Instruct-GGUF','5ab33fa94d1d04e903623ae72c95d1696f09f9e8','Llama-3.2-3B-Instruct-Q4_K_M.gguf','llama3','6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff'),
 'qwen1.5b':('Qwen/Qwen2.5-1.5B-Instruct-GGUF','91cad51170dc346986eccefdc2dd33a9da36ead9','qwen2.5-1.5b-instruct-q4_k_m.gguf','qwen2','6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e')}

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()

def fetch(key,config,directory):
 repo,rev,name,template,expected=config
 target=directory/name
 if target.exists() and digest(target)==expected:return target
 url=f'https://huggingface.co/{repo}/resolve/{rev}/{name}'
 with urllib.request.urlopen(urllib.request.Request(url+'?audit=length',headers={'Range':'bytes=0-0'}),timeout=40) as r:
  total=int(r.headers['Content-Range'].rsplit('/',1)[1])
 print(key,'bytes',total,flush=True)
 chunks=directory/(key+'-parts');chunks.mkdir(exist_ok=True)
 size=8<<20
 def part(index):
  start=index*size;end=min(total,start+size)-1;p=chunks/f'{index:05d}.part'
  if p.exists() and p.stat().st_size==end-start+1:return p
  for retry in range(4):
   try:
    req=urllib.request.Request(url+f'?audit_part={index}',headers={'Range':f'bytes={start}-{end}'})
    with urllib.request.urlopen(req,timeout=60) as response:
     if response.status!=206 or response.headers.get('Content-Range','').split('/')[0]!=f'bytes {start}-{end}':
      raise ValueError('range response differs from request')
     raw=response.read(end-start+2)
    if len(raw)!=end-start+1:raise ValueError('incomplete range')
    p.write_bytes(raw)
    return p
   except Exception:
    if retry==3:raise
    time.sleep(2)
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
  parts=list(pool.map(part,range((total+size-1)//size)))
 temporary=target.with_suffix('.partial')
 with temporary.open('wb') as stream:
  for p in parts:
   with p.open('rb') as block:
    for data in iter(lambda:block.read(1<<20),b''):stream.write(data)
 if digest(temporary)!=expected:raise ValueError('pinned model checksum mismatch: '+key)
 temporary.replace(target)
 print(key,'verified',expected,flush=True)
 return target

def main():
 directory=ROOT/'models-pinned';directory.mkdir(exist_ok=True)
 profiles={}
 for key in sys.argv[1:] or MODELS:
  config=MODELS[key];target=fetch(key,config,directory)
  profiles[key]=dict(gguf=target.name,template=config[3],sha256=config[4],pad_mode='isolated',
                     stop=['<|eot_id|>','<|end_of_text|>'] if config[3]=='llama3' else ['<|im_end|>','<|endoftext|>'])
  path=directory/'models.json'
  previous=json.loads(path.read_text()) if path.exists() else {}
  previous.update(profiles);path.write_text(json.dumps(previous,indent=2)+'\n')

if __name__=='__main__':main()
