"""Write a new ZIP containing the exact working-file bytes in FILE_MANIFEST.

Run make_manifest.py after staging the final package, then verify_package.py.
The ZIP lives outside the source tree and never contains itself or model weights.
Git history is supplied separately as a verified bundle.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    output=args.output.resolve()
    if output.is_relative_to(ROOT):raise ValueError('archive must be outside its source tree')
    manifest_path=ROOT/'publication/FILE_MANIFEST.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    files={**manifest['files'],'publication/FILE_MANIFEST.json':None}
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'x',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for name,expected in sorted(files.items()):
            path=(ROOT/name).resolve()
            if not path.is_relative_to(ROOT):raise ValueError('unsafe manifest path: '+name)
            raw=path.read_bytes()
            if expected and (len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']):
                raise ValueError('file changed after manifest: '+name)
            archive.writestr(name,raw)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:raise ValueError('archive CRC check failed')
        if set(archive.namelist())!=set(files):raise ValueError('archive member set differs')
    print(json.dumps(dict(archive=str(output),members=len(files),bytes=output.stat().st_size)))


if __name__=='__main__':main()
