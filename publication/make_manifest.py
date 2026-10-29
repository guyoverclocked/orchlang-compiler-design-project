"""Build the review manifest from the Git index; run after staging final files."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'publication/FILE_MANIFEST.json'
names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
names=list(filter(None,names))
attrs=subprocess.check_output(['git','check-attr','-z','--stdin','export-ignore'],cwd=ROOT,
    input=('\0'.join(names)+'\0').encode()).decode().split('\0')
excluded={attrs[i] for i in range(0,len(attrs)-2,3) if attrs[i+2]=='set'}
files={}
for name in sorted(names):
    path=ROOT/name
    if path==target or name in excluded or not path.is_file():continue
    raw=path.read_bytes()
    files[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
target.write_text(json.dumps(dict(schema='orchlang-review-file-manifest-v1',
    git_parent_before_release=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    files=files),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(files=len(files),bytes=sum(v['bytes'] for v in files.values()),manifest=str(target))))
