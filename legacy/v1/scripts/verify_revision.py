"""Check committed source bytes against a completed clean validation's hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--ref",default="HEAD")
    a=p.parse_args()
    manifest=json.loads((a.run/"manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "completed" or manifest["dirty_tree"]:
        raise ValueError("a completed clean-checkout validation is required")
    recorded=json.loads((a.run/"source-files.json").read_text(encoding="utf-8"))
    failures=[]
    for name,expected in recorded.items():
        r=subprocess.run(["git","show",a.ref+":"+name],cwd=ROOT,capture_output=True)
        if r.returncode or hashlib.sha256(r.stdout).hexdigest() != expected:
            failures.append(name)
    print(json.dumps(dict(status="failed" if failures else "completed",
        tested_source_commit=manifest["source_commit"],compared_ref=a.ref,
        checked_files=len(recorded),mismatches=failures),indent=2))
    return int(bool(failures))


if __name__=="__main__":
    raise SystemExit(main())
