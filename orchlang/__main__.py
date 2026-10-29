"""Independent source-bound validation of an exported compiler artifact."""
import argparse
import json
from pathlib import Path
from . import assurance as A, models as M


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['check'])
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--models',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    receipt=A.check_artifact(args.source.read_bytes(),M.load_profiles(args.models),
                             json.loads(args.artifact.read_text(encoding='utf-8')))
    receipt['artifact_sha256']=A.sha256(args.artifact)
    receipt['checker_sha256']=A.sha256(Path(__file__).resolve().parents[1]/'proof/ShapeCore.lean')
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['accepted'] else 1


if __name__=='__main__':raise SystemExit(main())
