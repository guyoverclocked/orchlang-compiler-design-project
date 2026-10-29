"""Verify the publication file manifest after extracting the review archive."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4<<20),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'publication/FILE_MANIFEST.json')
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    failures=[]
    for name,expected in manifest['files'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            failures.append(name+': unsafe path');continue
        if not path.is_file():failures.append(name+': missing')
        elif path.stat().st_size!=expected['bytes'] or digest(path)!=expected['sha256']:
            failures.append(name+': content differs')
    print(json.dumps(dict(status='failed' if failures else 'verified',
                         files_checked=len(manifest['files']),failures=failures),indent=2))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
