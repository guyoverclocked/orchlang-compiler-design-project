"""Copy immutable run records, excluding executable files, with a hash inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--run',action='append',help='Copy these named runs instead of the original set')
    args=p.parse_args()
    names=('clean-cpu-v3','generated-v3','certificates-v3','replay-v3',
           'tokenizers-v3','mutations-v3','external-v4')
    if args.run:
        names=tuple(args.run)
    if any(not re.fullmatch('[a-z0-9-]+',name) for name in names):
        raise ValueError('run names must be simple folder names')
    hashes={}
    for name in names:
        target=args.output/name
        target.mkdir(parents=True,exist_ok=False)
        for path in sorted((args.runs/name).glob('*')):
            if path.is_file() and path.suffix in {'.json','.txt','.patch'}:
                destination=target/path.name
                shutil.copyfile(path,destination)
                if path.read_bytes()!=destination.read_bytes():
                    raise ValueError('copy mismatch')
                hashes[destination.relative_to(args.output).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    with (args.output/'files.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(hashes,stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(copied_files=len(hashes),output=str(args.output))))


if __name__=='__main__':
    main()
