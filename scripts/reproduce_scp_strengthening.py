#!/usr/bin/env python3
"""Offline stage runner for rc3; fresh checks and recorded-data checks separated."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/scp_strengthening/reproduction"
FULL_PROFILE = ["native-core", "python-audit-tests", "frontend-tests",
                "conservative-contract-tests", "exact-contract-tests",
                "provider-fake-transport-tests", "capsule-verifier-tests",
                "provider-offline-manifest", "heldout-record-verification",
                "structured-record-validation", "finite-capsule-law-replay",
                "independent-row-ball-audit", "independent-exact-contract-audit",
                "isolated-wheel", "normalized-ir-proofs", "pinned-runtime-identity",
                "pinned-backend-tests", "completed-state-review-tests",
                "completed-state-fresh-replication"]

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def source_files(revision):
    names = subprocess.check_output(["git", "ls-tree", "-rz", "--name-only", revision], cwd=ROOT).decode().split("\0")
    # Evidence results, old PDFs/slides/archives and manuscript sources are
    # distinct from executable source. Every tracked executable/proof/config
    # byte is checked against its committed blob before and after stages.
    return [name for name in names if name and
            (name.endswith((".py", ".v", ".cpp", ".h", ".hpp", ".orch", ".toml", ".lock", ".yml", ".sh"))
             or name == "Makefile"
             or (name.endswith(".json") and name.startswith(("examples/", "integrations/"))))]
def check_source(revision, paths):
    committed = set(subprocess.check_output(["git", "ls-tree", "-rz", "--name-only", revision], cwd=ROOT).decode().split("\0"))
    # Reject untracked importable/executable source even if a local ignore rule
    # hides it. Runtime environments and bytecode caches are separate premises.
    runtime_roots = {".venv", "integrations/langgraph/.venv", "integrations/incident_triage/.venv"}
    source_suffixes = {".py", ".cpp", ".h", ".hpp", ".v", ".orch", ".sh"}
    for directory, folders, files in os.walk(ROOT, followlinks=False):
        base = Path(directory)
        for folder in list(folders):
            path = base / folder
            relative = path.relative_to(ROOT)
            if folder == ".git" or relative.as_posix() in runtime_roots:
                folders.remove(folder)
                continue
            if path.is_symlink():
                raise RuntimeError("symlink in executable source tree: " + str(relative))
        for filename in files:
            path = base / filename
            relative = path.relative_to(ROOT)
            if path.suffix not in source_suffixes:
                continue
            if path.is_symlink():
                raise RuntimeError("symlink in executable source tree: " + str(relative))
            name = relative.as_posix()
            if name not in committed:
                # Setuptools copies the committed wheel modules here. Permit
                # only exact committed copies, never a whole `build` subtree.
                candidate = "audit/" + path.name
                if (relative.parts[:2] == ("build", "lib") and len(relative.parts) == 3
                    and candidate in committed and path.suffix == ".py"):
                    expected = subprocess.check_output(["git", "show", revision + ":" + candidate], cwd=ROOT)
                    if path.read_bytes() == expected:
                        continue
                raise RuntimeError("executable source absent from declared revision: " + name)
    rows=[]
    for name in paths:
        raw=(ROOT/name).read_bytes()
        expected=subprocess.check_output(["git","show",revision+":"+name],cwd=ROOT)
        if raw!=expected:
            raise RuntimeError("source differs from declared revision: "+name)
        rows.append({"path":name,"sha256":sha(raw)})
    return rows
def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision",default="HEAD")
    parser.add_argument("--langgraph-python",type=Path)
    parser.add_argument("--coq",action="store_true")
    parser.add_argument("--native",action="store_true")
    parser.add_argument("--package",action="store_true")
    parser.add_argument("--output-dir",type=Path,default=OUT,
                        help="fresh result directory inside this checkout; use a new path for later replication")
    parser.add_argument("--allow-working-source",action="store_true",help="development checks only; never a frozen-revision claim")
    args=parser.parse_args()
    OUT=args.output_dir.absolute()
    if ROOT not in OUT.parents:
        raise RuntimeError("result directory must be inside the checkout")
    if (OUT/"reproduction.json").exists() and not args.allow_working_source:
        previous=json.loads((OUT/"reproduction.json").read_bytes())
        if previous.get("status")=="passed" and previous.get("frozen_source_verified"):
            raise RuntimeError("passed frozen run exists; choose a fresh --output-dir")
    revision=git("rev-parse",args.source_revision+"^{commit}")
    if git("rev-parse","HEAD")!=revision and not args.allow_working_source:
        raise RuntimeError("check out the declared source revision before frozen reproduction")
    if (OUT/"reproduction.json").exists() and not args.allow_working_source:
        previous_dir=OUT/"previous_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        previous_dir.mkdir(parents=True)
        for existing in [OUT/"reproduction.json",*OUT.glob("*.log")]:
            shutil.copy2(existing,previous_dir/existing.name)
    OUT.mkdir(parents=True,exist_ok=True)
    paths=source_files(revision)
    fingerprint=(check_source(revision,paths) if not args.allow_working_source else None)
    doc={"format":"orchlang-scp-strengthening-reproduction","version":1,"status":"running",
         "started_at_utc":datetime.now(timezone.utc).isoformat(),"source_revision":revision,
         "frozen_source_verified":not args.allow_working_source,"source_files":fingerprint,
         "environment":{"python":sys.version,"platform":platform.platform()},
         "paid_api_calls":0,"independent_human_reproduction":"not asserted", "stages":[]}
    manifest=OUT/"reproduction.json"
    def persist():
        manifest.write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n")
    persist()
    interpreter=sys.executable
    stages=[
        ("frontend-tests","fresh_execution",[interpreter,"-m","unittest","integrations.langgraph.source_frontend.test_extract","-q"]),
        ("conservative-contract-tests","fresh_execution",[interpreter,"-m","unittest","discover","-s","research/scp_strengthening/robust_usage","-p","test_*.py","-q"]),
        ("exact-contract-tests","fresh_execution",[interpreter,"-m","unittest","discover","-s","research/scp_strengthening/exact_uncertain_distance","-p","test_*.py","-q"]),
        ("provider-fake-transport-tests","fresh_execution",[interpreter,"-m","unittest","integrations.provider_calibration.test_provider_calibration","-q"]),
        ("capsule-verifier-tests","fresh_execution",[interpreter,"-m","unittest","discover","-s","integrations/workflow_capsules","-p","test_*.py","-q"]),
        ("provider-offline-manifest","recorded_contract_validation",[interpreter,"integrations/provider_calibration/provider_calibration.py","validate"]),
        ("heldout-record-verification","recorded_outcome_validation",[interpreter,"research/scp_strengthening/heldout/evaluate.py","--verify"]),
        ("structured-record-validation","recorded_timing_validation",[interpreter,"research/scp_strengthening/scalability/validate_structured_results.py"]),
        ("finite-capsule-law-replay","recorded_model_replay",[interpreter,"integrations/workflow_capsules/verify_finite_trace.py",*[
            "research/scp_strengthening/workflow_capsules/"+name+"-finite-oracle-v1.json" for name in
            ("didilili-langgraphllm-one-node","joshuac215-kb-agent-sequential-async")]]),
        ("independent-row-ball-audit","fresh_exact_enumeration",[interpreter,"research/scp_strengthening/second_adversarial_review/independent_finite_law_audit.py"]),
        ("independent-exact-contract-audit","fresh_exact_enumeration",[interpreter,"research/scp_strengthening/exact_distance_review/independent_crosscheck.py"]),
    ]
    if args.native:
        stages[0:0] = [
            ("native-core","fresh_execution",["make","-j4","check"]),
            ("python-audit-tests","fresh_execution",[interpreter,"-m","unittest","discover","-s","audit","-p","test_*.py","-q"]),
        ]
    if args.package:
        stages.append(("isolated-wheel","fresh_execution",[interpreter,"scripts/package_graph_tools.py","--output-dir","output/scp_strengthening/release"]))
    if args.coq:
        stages.append(("normalized-ir-proofs","fresh_proof_compilation",[interpreter,"research/scp_strengthening/second_adversarial_review/compile_proofs.py"]))
    if args.langgraph_python:
        # Resolving a venv's executable symlink selects the base interpreter
        # and loses the venv's installed dependencies. Preserve the launch path.
        pinned=str(args.langgraph_python.absolute())
        stages.extend([
            ("pinned-runtime-identity","runtime_premise_check",[pinned,"-c",
             "import importlib.metadata as m, json; v={p:m.version(p) for p in ('langgraph','langchain-core')}; print(json.dumps(v)); assert v == {'langgraph':'1.2.14','langchain-core':'1.6.9'}, v"]),
            ("pinned-backend-tests","fresh_execution",[pinned,"-m","unittest","integrations.langgraph.test_backend","-q"]),
            ("completed-state-review-tests","fresh_execution",[pinned,"-m","unittest","research.scp_strengthening.completed_state_review.test_completed_state_review","-q"]),
            ("completed-state-fresh-replication","fresh_source_backend_execution",[pinned,"scripts/replicate_completed_state.py","--output-dir",str(OUT/"state_replication")]),
        ])
    try:
        for name,kind,command in stages:
            start=time.monotonic()
            outcome=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=600)
            raw=(outcome.stdout+outcome.stderr).encode()
            logfile=OUT/(name+".log")
            logfile.write_bytes(raw)
            row={"stage":name,"kind":kind,"command":command,"exit_code":outcome.returncode,
                 "elapsed_seconds":time.monotonic()-start,"log":str(logfile.relative_to(ROOT)),"log_sha256":sha(raw)}
            doc["stages"].append(row)
            persist()
            print(name+": "+("PASS" if outcome.returncode==0 else "FAIL"),flush=True)
            if outcome.returncode:
                raise RuntimeError(name+" failed; inspect "+str(logfile))
        if fingerprint is not None and check_source(revision,paths)!=fingerprint:
            raise RuntimeError("source changed during reproduction")
        doc["status"]="passed"
    except Exception as exc:
        doc["status"]="failed"
        doc["failure"]=type(exc).__name__+": "+str(exc)
        print(doc["failure"],file=sys.stderr)
    finally:
        doc["completed_at_utc"]=datetime.now(timezone.utc).isoformat()
        persist()
    return 0 if doc["status"]=="passed" else 1
if __name__=="__main__":
    raise SystemExit(main())
