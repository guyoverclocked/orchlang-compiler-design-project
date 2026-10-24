"""Issue/check a restricted, source-bound certificate with Lean as final checker."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.source_gate import issue, bind_certificate


def check(lean, pairs, directory=None):
    with tempfile.TemporaryDirectory(prefix="lean-json-", dir=directory) as temp:
        batch = Path(temp) / "batch.json"
        batch.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8", newline="\n")
        process = subprocess.run([str(lean), "--run", str(ROOT / "proof/FiniteRelational.lean"), str(batch)],
                                 cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
        if process.returncode or "sorryAx" in process.stdout or "uses 'sorry'" in process.stdout:
            raise ValueError("Lean checker failed: " + process.stderr + process.stdout)
        # #print axioms is emitted before the executable's single JSON result.
        result = json.loads(process.stdout.splitlines()[-1])
        if len(result) != len(pairs) or any(type(b) is not bool for b in result):
            raise ValueError("malformed checker response")
        return result, process.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["issue", "check"])
    p.add_argument("source", type=Path)
    p.add_argument("certificate", type=Path)
    p.add_argument("--lean", required=True, type=Path)
    args = p.parse_args()
    data = args.source.read_bytes()
    certificate = issue(data) if args.mode == "issue" else json.loads(args.certificate.read_text(encoding="utf-8"))
    pair = bind_certificate(data, certificate)
    result, _ = check(args.lean.resolve(), [pair])
    if result != [True]:
        raise ValueError("Lean rejected certificate")
    if args.mode == "issue":
        with args.certificate.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(certificate, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(dict(status="checked", source_sha256=certificate["source_sha256"],
                         scope="closed requests; trusted independent source reader; finite stateless kernels",
                         provider_conformance=False)))


if __name__ == "__main__":
    main()
