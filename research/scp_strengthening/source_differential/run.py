#!/usr/bin/env python3
"""Completed-state differential checks of eight explicitly authored workflows.

Only source admitted by the existing AST gate is executed. The finite offline
oracle is shared deliberately; this validates lowering against that oracle,
not the oracle against a deployed provider.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from integrations.langgraph.backend import execute_verified, prepare_graph
from integrations.langgraph.source_frontend.export import export_bytes, _canonical
from integrations.langgraph.source_frontend.extract import parse_contracts
from integrations.langgraph.source_frontend.study import _source_app, _run_source, _graph_store

HERE = Path(__file__).resolve().parent
OUT = ROOT / "output/scp_strengthening/source_differential"
INPUTS = ("", "ordinary public question", "café 🌱 λ", "same words with punctuation?!")
SEEDS = (1, 17, 29)
TOOLS = ("integrations/langgraph/backend.py", "integrations/langgraph/source_frontend/extract.py",
         "integrations/langgraph/source_frontend/export.py", "integrations/langgraph/source_frontend/runtime.py",
         "integrations/langgraph/source_frontend/study.py", "research/scp_strengthening/source_differential/run.py")

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(_canonical(doc))
    temporary.replace(path)

def protocol():
    cases = []
    for source in sorted((HERE / "examples").glob("*.py")):
        contracts = source.with_suffix(".contracts.json")
        cases.append({"name": source.stem, "source": str(source.relative_to(ROOT)),
                      "source_sha256": sha(source.read_bytes()), "contracts": str(contracts.relative_to(ROOT)),
                      "contracts_sha256": sha(contracts.read_bytes())})
    return {"format": "orchlang-completed-state-study", "version": 1,
            "selection": "eight authored cases; multiple returned results, temporary local, overwritten state, all six token comparisons",
            "cases": cases, "public_text_inputs": list(INPUTS), "seeds": list(SEEDS),
            "complete_max_calls": 4, "cutoff_max_calls": 1,
            "tools": [{"path": path, "sha256": sha((ROOT / path).read_bytes())} for path in TOOLS],
            "criteria": "equal exact ordered request/response/usage trace and stop status; complete named source state equals projection of backend final_values; no completed state reported at cutoff",
            "excluded_claims": ["external original source admission", "all-program Python refinement", "real provider usage", "equality of partial eager registers to atomic source updates"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    frozen_path = OUT / "protocol.json"
    planned = protocol()
    if args.freeze:
        if frozen_path.exists():
            raise RuntimeError("study already frozen; do not overwrite before/after outcomes")
        save(frozen_path, dict(planned, frozen_at_utc=datetime.now(timezone.utc).isoformat()))
        print("Frozen eight authored cases before execution")
        return 0
    frozen = json.loads(frozen_path.read_bytes())
    comparable = {key: value for key, value in frozen.items() if key != "frozen_at_utc"}
    if comparable != planned:
        raise RuntimeError("inputs/tool snapshot differs from frozen protocol")
    rows = []
    failures = []
    for case in frozen["cases"]:
        source_path = ROOT / case["source"]
        raw_source = source_path.read_bytes()
        raw_contract = (ROOT / case["contracts"]).read_bytes()
        contract = parse_contracts(raw_contract)
        graph, provenance, report, attestation = export_bytes(raw_source, raw_contract)
        if report["status"] != "accepted" or attestation is None:
            failures.append({"case": case["name"], "phase": "graph admission", "report": report})
            continue
        verified = prepare_graph(_canonical(graph), _canonical(report))
        mapping = provenance["mapping"]
        artifact_path = OUT / (case["name"] + ".graph.json")
        save(artifact_path, graph)
        save(OUT / (case["name"] + ".certificate.json"), report)
        save(OUT / (case["name"] + ".provenance.json"), provenance)
        save(OUT / (case["name"] + ".attestation.json"), attestation)
        source_app = _source_app(raw_source, mapping["compiled_variable"], str(source_path))
        tasks = [(text, seed, 4) for text in INPUTS for seed in SEEDS]
        tasks.append((INPUTS[1], SEEDS[0], 1))
        for text, seed, cap in tasks:
            store = {"question": text}
            left = _run_source(source_app, contract, store, seed, cap)
            right = execute_verified(verified, _graph_store(mapping, store), seed,
                                     max_calls=cap, recursion_limit=256).to_dict()
            fields = {item["source_key"]: item["graph_name"] for item in mapping["inputs"]}
            fields.update({item["source_key"]: item["graph_register"] for item in mapping["result_slots"]})
            target_state = ({key: right["final_values"][value] for key, value in fields.items()
                             if value in right["final_values"]} if right["final_values"] is not None else None)
            tests = {"ordered_trace": _canonical(left["trace"]) == _canonical(right["trace"]),
                     "status": left["status"] == right["status"],
                     "stop": left["stopped"] is right["stopped"],
                     "complete_state": _canonical(left["final_state"]) == _canonical(target_state),
                     "expected_outcome": left["status"] == ("stopped" if cap == 4 else "truncated"),
                     "no_runtime_error": left["failure"] is None and right.get("failure") is None}
            row = {"case": case["name"], "input": store, "seed": seed, "max_calls": cap,
                   "checks": tests, "source": left, "backend": right,
                   "backend_source_state_projection": target_state, "source_state_mapping": fields}
            rows.append(row)
            if not all(tests.values()):
                failures.append({"case": case["name"], "input": store, "seed": seed, "max_calls": cap,
                                 "failed_checks": [key for key, value in tests.items() if not value]})
    result = {"format": "orchlang-completed-state-differential", "version": 1,
              "protocol_sha256": sha(frozen_path.read_bytes()),
              "environment": {"python": sys.version, "langgraph": importlib.metadata.version("langgraph")},
              "runs": rows, "failures": failures,
              "totals": {"completed_pairs": sum(row["max_calls"] == 4 for row in rows),
                         "cutoff_pairs": sum(row["max_calls"] == 1 for row in rows),
                         "call_events": sum(len(row["source"]["trace"]) for row in rows),
                         "all_checks_passed_pairs": sum(all(row["checks"].values()) for row in rows)}}
    save(OUT / "results.json", result)
    print(json.dumps({"totals": result["totals"], "failures": failures}, sort_keys=True))
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
