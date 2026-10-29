"""Compile every Lean file in dependency order and audit the printed axioms.

Fails if any file does not compile, if any printed declaration depends on
`sorryAx`, or if a declaration uses an axiom outside Lean's standard
`propext`, `Quot.sound` and `Classical.choice`. Writes a JSON receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ORDER = [("ShapeCore", True), ("AdmissionDomain", True), ("Utf8Envelope", True),
         ("RestrictedDomain", True), ("VocabularyEnvelope", False),
         ("StaticAdmissionChecks", False), ("StaticAdmissionCLI", False)]
ALLOWED = {"propext", "Quot.sound", "Classical.choice"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    lean = os.environ.get("LEAN", "lean")
    env = dict(os.environ, LEAN_PATH=str(ROOT / "proof"))
    env.pop("ORCHLANG_ADMISSION_INPUT", None)
    files, declarations, failures = [], {}, []
    for name, emit in ORDER:
        source = ROOT / "proof" / f"{name}.lean"
        command = [lean] + (["-o", str(ROOT / "proof" / f"{name}.olean")] if emit else []) + [str(source)]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        lines = [l for l in (result.stdout + result.stderr).splitlines() if l.strip()]
        for line in lines:
            match = re.match(r"'(.+)' depends on axioms: \[(.*)\]", line)
            if match:
                axioms = [a.strip() for a in match.group(2).split(",") if a.strip()]
                declarations[match.group(1)] = axioms
                if not set(axioms) <= ALLOWED:
                    failures.append(f"{match.group(1)} uses {sorted(set(axioms) - ALLOWED)}")
            elif "does not depend on any axioms" in line:
                declarations[line.split("'")[1]] = []
            else:
                failures.append(f"{name}: {line}")
        if result.returncode:
            failures.append(f"{name}: exit {result.returncode}")
        files.append(dict(file=f"proof/{name}.lean", exit=result.returncode,
                          lines=sum(1 for _ in source.open(encoding="utf-8")),
                          theorems=sum(1 for l in source.open(encoding="utf-8") if l.startswith("theorem ")),
                          sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    receipt = dict(schema="orchlang-proof-receipt-v1", lean=subprocess.run([lean, "--version"], capture_output=True,
                   text=True).stdout.strip(), files=files, declarations=declarations,
                   total_lines=sum(f["lines"] for f in files), total_theorems=sum(f["theorems"] for f in files),
                   sorry_free=not any("sorryAx" in a for a in declarations.values()),
                   failures=failures, passed=not failures)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("total_lines", "total_theorems", "sorry_free", "passed")}))
    for failure in failures:
        print("FAIL", failure, file=sys.stderr)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
