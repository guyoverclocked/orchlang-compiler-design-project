"""Supplementary exact-request port conformance on captured real model outcomes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.workflow_originals import port
from runtime.workflow_tape import CapturedTape


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--protocol", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    protocol = json.loads(args.protocol.read_text())
    cp = ROOT/protocol["corpus"]
    corpus = json.loads(cp.read_text())
    manifest = json.loads((args.run/"manifest.json").read_text())
    if sha(args.protocol) != manifest["protocol_sha256"] or sha(cp) != manifest["corpus_sha256"]:
        raise ValueError("replay must use the exact source run protocol/corpus")
    for kernel in corpus["kernels"]:
        if sha(cp.parent/kernel["file"]) != kernel["sha256"]:
            raise ValueError("replay kernel differs from frozen source run")
    for name in ("runtime/workflow_originals.py", "runtime/workflow_kernels.py"):
        if sha(ROOT/name) != manifest["implementation_sha256"][name]:
            raise ValueError("port implementation differs from actual source run")
    cases = {c["id"]:c for c in corpus["cases"]}
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for row in json.loads((args.run/"results.json").read_text()):
        original = row["arms"]["original"]
        item = {k:row[k] for k in ("id", "output_cap", "seed", "input_index", "inputs")}
        if original["status"] != "ok":
            item.update(status="unsupported-source-run-failed", error=original["error"])
        else:
            tape = CapturedTape(original["trace"], output_cap=row["output_cap"],
                                allow_reorder=row["id"] == "lg-parallel-graph")
            try:
                output = port(cases[row["id"]], row["inputs"], cp.parent, tape)
                usage = tape.finish()
                equal = output == original["output"]
                item.update(status="pass" if equal else "output-mismatch", output=output,
                            original_output=original["output"], outputs_equal=equal,
                            usage=usage, replay_trace=tape.trace)
            except Exception as error:
                item.update(status="failed", error=repr(error), replay_trace=tape.trace)
        rows.append(item)
    summary = dict(comparisons=len(rows), passed=sum(r["status"] == "pass" for r in rows),
        unsupported_source_failed=sum(r["status"] == "unsupported-source-run-failed" for r in rows),
        actual_generation_calls=0, replay_calls=sum(len(r.get("replay_trace",[])) for r in rows),
        exact_request_matches=sum(r.get("usage",{}).get("exact_requests_matched",0) for r in rows),
        statement="Conformance under common captured actual model outcomes. Zero new model generations; not independent-generation equivalence or all-input proof.")
    out = dict(summary=summary, generated_utc=datetime.now(timezone.utc).isoformat(),
               original_results_sha256=sha(args.run/"results.json"),
               protocol_sha256=sha(args.protocol),
               implementation_sha256={name:sha(ROOT/name) for name in (
                   "runtime/workflow_originals.py","runtime/workflow_kernels.py",
                   "runtime/workflow_tape.py","scripts/real_workflow_replay.py")},
               ordering="strict request order except explicitly independent lg-parallel-graph calls",
               rows=rows)
    (args.output/"conformance.json").write_text(json.dumps(out, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return int(summary["passed"] != len(rows))


if __name__ == "__main__":
    raise SystemExit(main())
