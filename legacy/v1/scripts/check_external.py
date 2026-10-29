"""Frozen external cost-projection check; never invokes upstream tools or APIs."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.structural_baseline import structural_bound


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--orchc", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--protocol-commit", required=True)
    args = p.parse_args()
    if not re.fullmatch("[0-9a-f]{40}", args.protocol_commit):
        raise ValueError("a real immutable protocol commit is required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("frozen projection run requires a clean source checkout; write results outside it")
    protocol_path = ROOT / "bench/protocols/external-projections-v1.json"
    protocol = json.loads(protocol_path.read_text())
    frozen = subprocess.check_output(["git", "show", args.protocol_commit + ":bench/protocols/external-projections-v1.json"], cwd=ROOT)
    if frozen != protocol_path.read_bytes():
        raise ValueError("working protocol differs from the immutable protocol commit")
    corpus_path = ROOT / protocol["corpus"]
    corpus = json.loads(corpus_path.read_text())
    frozen_corpus = subprocess.check_output(["git", "show", args.protocol_commit + ":" + protocol["corpus"]], cwd=ROOT)
    if frozen_corpus != corpus_path.read_bytes():
        raise ValueError("corpus differs from the frozen manifest")
    args.output.mkdir(parents=True, exist_ok=False)
    raw, rows, failures = [], [], []
    def checkpoint(status, error=None):
        partial = dict(status=status, source_commit=commit, protocol_commit=args.protocol_commit,
                       dirty_tree=False, completed_workflows=len(rows), failures=failures,
                       original_workflow_executions=0, spent_usd="0.00")
        if error:
            partial["infrastructure_error"] = error
        for name, data in (("manifest", partial), ("commands", raw), ("results", rows)):
            (args.output/(name+".json")).write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    checkpoint("running")
    def run(command):
        try:
            r = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            checkpoint("failed", str(error))
            raise
        raw.append(dict(argv=command, exit=r.returncode, stdout=r.stdout, stderr=r.stderr))
        checkpoint("running")
        if r.returncode:
            checkpoint("failed", r.stderr)
            raise ValueError("projection infrastructure/acceptance failure: " + r.stderr)
        return r.stdout
    for case in corpus["cases"]:
        path = corpus_path.parent / case["file"]
        if sha(path) != case["sha256"]:
            checkpoint("failed", "projection source differs from frozen hash")
            raise ValueError("projection source differs from frozen hash")
        run([str(args.orchc.resolve()), "check", str(path)])
        report = json.loads(run([str(args.orchc.resolve()), "certify", str(path)]))
        ir = json.loads(run([str(args.orchc.resolve()), "ir-json", str(path)]))["workflows"][0]
        baseline = structural_bound(ir)
        counted = copy.deepcopy(ir)
        for node in counted["nodes"]:
            if node["kind"] == "Call":
                node["attributes"].update(in_tokens="1", out_tokens="0")
        max_calls = structural_bound(counted)["total"]
        bound = report["workflows"][0]["bound"]
        actual_static = dict(input=bound["estimated_tokens"], output=bound["guaranteed_tokens"], total=bound["total_tokens"])
        if actual_static != baseline or max_calls != case["expected_max_calls"]:
            failures.append(case["id"] + ": bound/call-shape disagreement")
        observations = []
        for seed in protocol["seeds"]:
            result = run([str(args.orchc.resolve()), "run", str(path), "--seed", str(seed)])
            counts = re.search(r"actual tokens\s+(\d+)\s+\(input (\d+) \+ output (\d+)\)", result)
            calls = re.search(r"calls\s+(\d+)", result)
            if counts is None or calls is None:
                checkpoint("failed", "malformed mock observation")
                raise ValueError("malformed mock observation")
            total, i, o = map(int, counts.groups())
            obs = dict(seed=seed, total=total, input=i, output=o, calls=int(calls[1]))
            obs["violates"] = total > baseline["total"] or i > baseline["input"] or o > baseline["output"] or obs["calls"] > max_calls
            if obs["violates"]:
                failures.append(case["id"] + ": mock bound violation")
            observations.append(obs)
        rows.append(dict(id=case["id"], production=actual_static, structural=baseline, max_calls=max_calls,
                         observations=observations, source_sha256=case["sha256"],
                         source_lines=case["nonempty_source_lines"], input_bounds=case["input_bound_annotations"],
                         model_caps=case["model_cap_annotations"], original_workflow_executed=False))
        checkpoint("running")
    if len(rows) != 11:
        failures.append("incomplete corpus")
    manifest = dict(schema_version="1", status="failed" if failures else "completed", source_commit=commit,
                    protocol_commit=args.protocol_commit, dirty_tree=False, protocol_sha256=sha(protocol_path),
                    corpus_manifest_sha256=sha(corpus_path), observer=protocol["observer"], backend=protocol["backend"],
                    timestamp_utc=datetime.now(timezone.utc).isoformat(), seeds=protocol["seeds"],
                    planned_workflows=11, completed_workflows=len(rows), excluded_workflows=10,
                    original_workflow_executions=0, faithful_end_to_end_translations=0,
                    executable_sha256=sha(args.orchc), python=sys.version,
                    budget_usd_cap="5.00", spent_usd="0.00", outstanding_reserved_usd="0.00", failures=failures)
    for name, data in (("manifest", manifest), ("results", rows), ("commands", raw)):
        (args.output / (name + ".json")).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=manifest["status"], projections=len(rows), runs=sum(len(r["observations"]) for r in rows), failures=failures)))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
