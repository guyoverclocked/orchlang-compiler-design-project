"""Frozen diagnostic: independent original-versus-original local generations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.local_model import LocalModel


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tokenizer", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    path=ROOT/"bench/protocols/real-workflows-repeatability-v1.json"
    protocol=json.loads(path.read_text())
    model_protocol=json.loads((ROOT/protocol["model_protocol"]).read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    backend=LocalModel(args.tokenizer,model_protocol["model"]["tokenizer_sha256"])
    rows=[]
    for case in protocol["cases"]:
        for repetition in range(protocol["repetitions"]):
            row=dict(id=case["id"],repetition=repetition,arms={})
            for arm in ("original_a","original_b"):
                backend.begin(input_cap=case["input_cap"], output_cap=case["output_cap"],
                              max_calls=1, seed=case["seed"])
                try:
                    text=backend.generate(prompt=case["rendered_request"], schema=case["schema"])
                    row["arms"][arm]=dict(status="ok",response=text,trace=backend.trace,usage=backend.totals())
                except Exception as error:
                    row["arms"][arm]=dict(status="failed",error=repr(error),trace=backend.trace,usage=backend.totals())
            a,b=row["arms"].values()
            row["exact_response_equal"]=a["status"]==b["status"]=="ok" and a["response"]==b["response"]
            rows.append(row)
            (args.output/"results.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(dict(id=case["id"],repetition=repetition,equal=row["exact_response_equal"])),flush=True)
    summary=dict(pairs=len(rows),exact_response_equal=sum(r["exact_response_equal"] for r in rows),
                 response_disagreements=sum(not r["exact_response_equal"] for r in rows),
                 actual_generation_calls=sum(a["usage"]["calls"] for r in rows for a in r["arms"].values()),
                 replay_calls=0)
    manifest=dict(protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  generated_utc=datetime.now(timezone.utc).isoformat(),model=backend.identity,summary=summary)
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
