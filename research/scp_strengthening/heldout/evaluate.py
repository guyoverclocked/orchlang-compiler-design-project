#!/usr/bin/env python3
"""One frozen static admission evaluation; no external Python is executed."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.publication_upgrade_corpus import mechanically_derived_contract
from integrations.langgraph.source_frontend.extract import FrontendError, extract_source

OUT = ROOT / "output/scp_strengthening/heldout"
TOOLS = ["integrations/langgraph/source_frontend/extract.py",
         "scripts/publication_upgrade_corpus.py", "research/scp_strengthening/heldout/evaluate.py"]
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
def fingerprint():
    return [{"path": path, "sha256": sha((ROOT/path).read_bytes())} for path in TOOLS]
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-implementation", action="store_true")
    parser.add_argument("--verify", action="store_true", help="check frozen outcome bytes/identities without rescoring")
    args = parser.parse_args()
    freeze_path = OUT / "implementation_freeze.json"
    result_path = OUT / "admission_results.json"
    source_path = OUT / "source_freeze.json"
    source_raw = source_path.read_bytes()
    sources = json.loads(source_raw)
    if args.freeze_implementation:
        if freeze_path.exists() or result_path.exists():
            raise RuntimeError("implementation/outcomes already frozen")
        write(freeze_path, {"frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                           "source_freeze_sha256": sha(source_raw), "tools": fingerprint(),
                           "extractor_unchanged_from_source_freeze": sha((ROOT/TOOLS[0]).read_bytes()) == sources["extractor_sha256_at_source_freeze"],
                           "scope": "static original whole-file grammar admission only; no source execution; no slice extraction attempted on holdout"})
        print("Frozen implementation before static held-out outcomes")
        return 0
    freeze_raw = freeze_path.read_bytes()
    freeze = json.loads(freeze_raw)
    if freeze["source_freeze_sha256"] != sha(source_raw) or freeze["tools"] != fingerprint():
        raise RuntimeError("frozen inputs or evaluated implementation drifted")
    candidates = [row for repo in sources["repositories"] for row in repo["candidates"]]
    for candidate in candidates:
        if sha((ROOT/candidate["source_snapshot"]).read_bytes()) != candidate["sha256"]:
            raise RuntimeError("candidate bytes drifted")
    if args.verify:
        doc = json.loads(result_path.read_bytes())
        if doc["source_freeze_sha256"] != sha(source_raw) or doc["implementation_freeze_sha256"] != sha(freeze_raw):
            raise RuntimeError("result binding mismatch")
        if len(doc["candidates"]) != len(candidates):
            raise RuntimeError("candidate denominator mismatch")
        for row, candidate in zip(doc["candidates"], candidates):
            if any(row[key] != candidate[key] for key in candidate):
                raise RuntimeError("candidate identity mismatch")
        if dict(Counter(row["admission"] for row in doc["candidates"])) != doc["admission_counts"]:
            raise RuntimeError("result summary mismatch")
        print(json.dumps({"verification": "pass", "admission_counts": doc["admission_counts"]}))
        return 0
    if result_path.exists():
        raise RuntimeError("one final held-out evaluation already completed; use --verify")
    rows=[]
    for item in candidates:
        raw=(ROOT/item["source_snapshot"]).read_bytes()
        contract, error=mechanically_derived_contract(raw,item["path"])
        row=dict(item, contract_basis="mechanical public text/bool declarations and literal request aliases as conditional grammar-probe premises; no provider/model fidelity attributed to source", contract_sha256=sha(contract or b""), dynamic_differential="not_run")
        if error:
            row.update(admission="not_attempted", reason=error)
        else:
            try:
                graph,mapping=extract_source(raw,contract or b"")
                row.update(admission="admitted", reason=None, graph_states=len(graph["states"]), dynamic_differential="pending_separate_review")
            except FrontendError as exc:
                row.update(admission="unsupported", reason=str(exc))
            except Exception as exc:
                row.update(admission="error", reason=type(exc).__name__+": "+str(exc))
        rows.append(row)
    counts=dict(Counter(row["admission"] for row in rows))
    reasons=dict(Counter(row["reason"].split(" at ")[0] for row in rows if row["reason"]))
    result={"evaluated_at_utc":datetime.now(timezone.utc).isoformat(),"source_freeze_sha256":sha(source_raw),"implementation_freeze_sha256":sha(freeze_raw),
            "selected_repositories":sources["repository_count"],"retrieved_repositories":sum(repo["status"]=="frozen" for repo in sources["repositories"]),
            "retrieved_python_paths":sources["python_path_count"],"candidate_count":len(rows),"retrieval_errors":[repo for repo in sources["repositories"] if repo["status"]!="frozen"],
            "noncandidate_parse_errors":sum(len(repo["parse_errors"]) for repo in sources["repositories"]),"admission_counts":counts,"first_rejection_counts":reasons,"candidates":rows,
            "scope":"one static whole-file evaluation; no arbitrary-source execution, inferred provider validation, source rewrite, or held-out workflow-slice claim",
            "interpretation":"convenience cohort, repository/file denominators distinct; unseen repository retrieval failure retained, not counted as unsupported/admitted"}
    write(result_path,result)
    print(json.dumps({key:result[key] for key in ("selected_repositories","retrieved_repositories","retrieved_python_paths","candidate_count","admission_counts","first_rejection_counts","noncandidate_parse_errors")},sort_keys=True))
    return 1 if counts.get("error") else 0
if __name__=="__main__":
    raise SystemExit(main())
