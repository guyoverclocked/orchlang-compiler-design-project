"""Reproduce two scoped cap-resolution probes against pinned Costwright source."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PIN = "2531c37cc2aa06472a2628bccfb527f185f6b4c0"
CASES = {
    "import-alias-capped": (
        'from langchain_openai import ChatOpenAI as Client\n'
        'client = Client(model="gpt-4o-mini", max_tokens=16)\n',
        "Recognize an imported constructor alias with an explicit cap.",
    ),
    "dynamic-model-conservative": (
        'from langchain_openai import ChatOpenAI\n'
        'model_name = "gpt-5"\n'
        'client = ChatOpenAI(model=model_name, max_tokens=16)\n',
        "Flag a dynamic model when the cap parameter may be ineffective.",
    ),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--costwright", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tree = args.costwright.resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
    if commit != PIN:
        raise ValueError("comparison requires Costwright commit " + PIN)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=tree, text=True).strip():
        raise ValueError("comparison source must be clean")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree / "src")
    records = []
    for name, (source, purpose) in CASES.items():
        fixture = out / (name + ".py")
        fixture.write_text(source, encoding="utf-8", newline="\n")
        command = [sys.executable, "-m", "costwright.cli", "caps", str(fixture), "--json"]
        process = subprocess.run(command, env=env, capture_output=True, text=True,
                                 encoding="utf-8", timeout=60)
        if process.returncode != 0:
            raise RuntimeError(process.stderr or process.stdout)
        result = json.loads(process.stdout)
        records.append(dict(id=name, purpose=purpose, argv=command,
                            exit=process.returncode, stdout=result, stderr=process.stderr,
                            source_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest()))
    manifest = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    source="https://github.com/eleata/costwright", source_commit=commit,
                    version="0.2.15", protocol="two-disclosed-development-probes",
                    scope="constructor cap resolution, not relational noninterference",
                    python=sys.version, records=records,
                    source_hashes={name:hashlib.sha256((tree / name).read_bytes()).hexdigest()
                                   for name in ("src/costwright/caps.py", "src/costwright/cli.py",
                                                "src/costwright/extract.py", "src/costwright/mapper.py",
                                                "README.md", "docs/NON-INTERFERENCE.md")})
    (out / "results.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8", newline="\n")
    print(json.dumps(dict(output=str(out), cases=len(records), source_commit=commit)))


if __name__ == "__main__":
    main()
