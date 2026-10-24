"""Exhaustively compare development closed-request programs with a finite oracle."""
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.finite_reference import Reference, canonical, distribution


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_contract(revision, cap):
    return dict(provider="finite", revision=revision, tokenizer="utf8-bytes-v1",
                serializer="raw-utf8-v1", cap=cap, sampling="explicit-table",
                error_policy="status-in-outcome", accounting="all-attempts-input-and-output", state="stateless")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orchc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cli = args.orchc.resolve()
    protocol_file = ROOT / "bench/protocols/generated-development-v1.json"
    protocol = json.loads(protocol_file.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    variants = list(itertools.product(protocol["revisions"], protocol["caps"],
                                      protocol["requests"], protocol["calls_per_arm"]))
    rows, failures = [], []
    with tempfile.TemporaryDirectory(prefix="generated-", dir=args.output.resolve()) as scratch:
        source_path = Path(scratch) / "case.orch"
        for case_id, (left, right) in enumerate(itertools.product(variants, repeat=2)):
            contracts, kernels = {}, {}
            source_arms, ref_arms = [], []
            for side, (revision, cap, request, calls) in zip(("left", "right"), (left, right)):
                # Alternate alias spelling without selecting on outcomes.
                alias = side if case_id % 2 else "m"
                contracts[alias + side] = model_contract(revision, cap)
                kernels[canonical(contracts[alias + side])] = {
                    "yes": [dict(text="", p="1/2", status="ok"), dict(text="x", p="1/2", status="ok")],
                    "foo": [dict(text="", p="1/2", status="ok"), dict(text="x", p="1/2", status="ok")],
                    "no!": [dict(text="x" * cap, p="1", status="ok")]}
                source_arms.append(f'model {alias} = mock("{revision}") max_tokens {cap}; ' + " ".join(
                    f'let {side}{i}: text = call p("{request}") using {alias};' for i in range(calls)))
                ref_arms.append([dict(kind="call", model=alias + side, request=request, bind=side + str(i))
                                 for i in range(calls)])
            source = ('workflow Generated budget 1000 { secret s: boolean max_tokens 1; '
                      'prompt p(t: text) -> text = "{t}"; if s { ' + source_arms[0] +
                      ' } else { ' + source_arms[1] + ' } output "done"; }\n')
            source_path.write_text(source, encoding="utf-8", newline="\n")
            result = subprocess.run([str(cli), "check", str(source_path)], cwd=ROOT,
                                    encoding="utf-8", capture_output=True, timeout=30)
            codes = re.findall(r"error \[([A-Z]\d+)\]", result.stderr)
            infrastructure = result.returncode not in (0, 1) or (result.returncode == 1 and codes != ["E236"])
            reference = Reference(contracts, kernels)
            ref_program = [{"kind": "if", "guard": "s", "then": ref_arms[0], "else": ref_arms[1]}]
            l = reference.run(ref_program, {"s": True})
            r = reference.run(ref_program, {"s": False})
            equal = distribution(l) == distribution(r)
            accepted = result.returncode == 0
            # A conventional trace-identity checker on this closed grammar.
            # Same primitive assumptions, no claim that this is a novel rule.
            trace_identity = left == right
            if infrastructure or accepted != trace_identity or (accepted and not equal):
                failures.append(case_id)
            rows.append(dict(id=case_id, source=source, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                             left=left, right=right, source_exit=result.returncode, diagnostics=codes,
                             accepted=accepted, finite_equal=equal, trace_identity_accepts=trace_identity,
                             left_paths=len(l), right_paths=len(r), stderr=result.stderr,
                             infrastructure_failure=infrastructure))
    if len(rows) != protocol["expected_programs"]:
        failures.append("wrong program count")
    manifest = dict(schema_version="1", status="failed" if failures else "completed",
                    purpose=protocol["status"], timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    dirty_tree=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
                    protocol_sha256=sha(protocol_file), script_sha256=sha(Path(__file__).resolve()),
                    reference_sha256=sha(ROOT / "runtime/finite_reference.py"), executable_sha256=sha(cli),
                    programs=len(rows), unique_call_count_structures=len({(r["left"][3], r["right"][3]) for r in rows}),
                    accepted=sum(r["accepted"] for r in rows),
                    accepted_finite_counterexamples=sum(r["accepted"] and not r["finite_equal"] for r in rows),
                    finite_equivalent_rejected=sum(not r["accepted"] and r["finite_equal"] for r in rows),
                    trace_identity_disagreements=sum(r["accepted"] != r["trace_identity_accepts"] for r in rows),
                    external_workflows=0, failures=failures, spent_usd="0.00", outstanding_reserved_usd="0.00")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output / "programs.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
