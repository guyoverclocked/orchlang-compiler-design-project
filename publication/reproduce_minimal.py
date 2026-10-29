"""Portable minimal artifact replay into a new output directory.

Uses installed dependencies; it does not create an independent human or a fresh
machine. Optional model checks require the external pinned model configuration.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--models", type=Path)
    args = ap.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lean = os.environ.get("LEAN", "lean")
    env = dict(os.environ, LEAN=lean, LEAN_PATH=str(output))
    if args.models:
        env["ORCHLANG_MODELS"] = str(args.models.resolve())
    py = sys.executable
    commands = [
        ("file-manifest", [py, "publication/verify_package.py"]),
        ("core-proof", [lean, "-o", str(output / "ShapeCore.olean"), "proof/ShapeCore.lean"]),
        ("domain-proof", [lean, "-o", str(output / "AdmissionDomain.olean"), "proof/AdmissionDomain.lean"]),
        ("static-admission-checks", [lean, "proof/StaticAdmissionChecks.lean"]),
        ("static-admission-cli", [lean, "proof/StaticAdmissionCLI.lean"]),
        ("vocabulary-proof", [lean, "proof/VocabularyEnvelope.lean"]),
        ("admission-counterexample", [py, "experiments/admission_domain.py", "--output", str(output / "admission.json")]),
        ("source-binding-case", [py, "experiments/source_binding_case.py", "--output", str(output / "source-binding.json")]),
        ("strict-completion", [py, "publication/build_evidence.py", "--require-complete"]),
    ]
    if args.models:
        commands.append(("pinned-model-pair", [py, "experiments/run_workflow.py", "--workflow", "workflows/switch.orch",
                         "--data", "experiments/data/switch.jsonl", "--models", str(args.models.resolve()),
                         "--out", str(output / "model-pair"), "--limit", "1", "--keep", "response,intention,llm_result"]))
        commands.append(("standalone-source-check", [py, "-m", "orchlang", "check", "--source", "workflows/switch.orch",
                         "--artifact", str(output / "model-pair/validation-artifact.json"), "--models", str(args.models.resolve()),
                         "--output", str(output / "source-check.json")]))
    results = []
    for name, command in commands:
        with (output / (name + ".log")).open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        log = (output / (name + ".log")).read_text(encoding="utf-8")
        passed = result.returncode == 0 and ("sorryAx" not in log if name.endswith("proof") else True)
        if passed and name == "pinned-model-pair":
            records = {condition: [json.loads(line) for line in (output / f"model-pair/{condition}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                       for condition in ("orig", "ours")}
            manifest = json.loads((output / "model-pair/run-manifest.json").read_text(encoding="utf-8"))
            paired = (len(records["orig"]) == len(records["ours"]) == 1
                      and records["orig"][0]["id"] == records["ours"][0]["id"]
                      and records["orig"][0]["store"] == records["ours"][0]["store"]
                      and all(row["truncations"] == 0 and row["usage"]["usage_complete"] for rows in records.values() for row in rows))
            detail = dict(saved_store_equal=paired, git_commit=manifest["git_commit"],
                          source_export=manifest.get("source_export", False),
                          export_manifest_sha256=manifest.get("export_manifest_sha256"))
            (output / "model-pair-check.json").write_text(json.dumps(detail, indent=2) + "\n", encoding="utf-8")
            passed = paired
        results.append(dict(check=name, command=command, exit=result.returncode, passed=passed))
        print(name, "passed" if passed else "FAILED", flush=True)
        if not passed:
            break
    receipt = dict(schema="orchlang-minimal-replay-v1", root=str(ROOT), independent_human_replay=False,
                   model_configured=bool(args.models), checks=results, passed=all(r["passed"] for r in results) and len(results) == len(commands))
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return int(not receipt["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
