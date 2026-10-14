#!/usr/bin/env python3
"""Bind frozen code, fresh offline checks, recorded studies and final papers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "scripts"))
from reproduce_scp_strengthening import check_source, source_files, FULL_PROFILE

OUT=ROOT/"output/scp_strengthening/publication"
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def record(path):
    return {"path":str(path.relative_to(ROOT)),"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision",required=True)
    parser.add_argument("--manuscript",type=Path,required=True)
    parser.add_argument("--pdf",type=Path,required=True)
    parser.add_argument("--supplement",type=Path,required=True)
    parser.add_argument("--supplement-pdf",type=Path,required=True)
    parser.add_argument("--reproduction-manifest",type=Path,
                        default=ROOT/"output/scp_strengthening/reproduction/reproduction.json")
    args=parser.parse_args()
    revision=subprocess.check_output(["git","rev-parse",args.source_revision+"^{commit}"],cwd=ROOT).decode().strip()
    paths=source_files(revision)
    fingerprint=check_source(revision,paths)
    reproduction_path=args.reproduction_manifest.resolve()
    replication_result=reproduction_path.parent/"state_replication/results.json"
    reproduction=json.loads(reproduction_path.read_bytes())
    if (reproduction["status"]!="passed" or not reproduction["frozen_source_verified"]
        or reproduction["source_revision"]!=revision or reproduction["source_files"]!=fingerprint):
        raise RuntimeError("a passed exact-revision reproduction is required")
    if ([row["stage"] for row in reproduction["stages"]] != FULL_PROFILE
        or any(row["exit_code"] != 0 for row in reproduction["stages"])):
        raise RuntimeError("full ordered reproduction profile must pass every stage")
    stage_logs={row["stage"]: row["log"] for row in reproduction["stages"]}
    manuscripts=[args.manuscript.resolve(),args.supplement.resolve()]
    for path in manuscripts:
        text=path.read_text()
        if ("\\newcommand{\\SourceRevision}{"+revision+"}") not in text:
            raise RuntimeError("paper does not bind the exact code revision: "+str(path))
    papers=[*manuscripts,args.pdf.resolve(),args.supplement_pdf.resolve()]
    for path in papers:
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("paper artifact missing/empty: "+str(path))
    build_path=OUT/"pdf_build.json"
    build=json.loads(build_path.read_bytes())
    if build["status"]!="passed" or len(build["documents"])!=2:
        raise RuntimeError("successful two-document PDF build receipt required")
    for source,pdf in ((manuscripts[0],args.pdf.resolve()),(manuscripts[1],args.supplement_pdf.resolve())):
        pairs=[item for item in build["documents"] if item["source"]==record(source) and item["pdf"]==record(pdf) and item["exit_code"]==0]
        if len(pairs)!=1:
            raise RuntimeError("PDF-to-TeX build binding differs from the final files")
    for row in reproduction["stages"]:
        log=ROOT/row["log"]
        if sha(log.read_bytes())!=row["log_sha256"]:
            raise RuntimeError("stage log digest differs: "+row["stage"])
    evidence=[]
    for base in (ROOT/"research/scp_strengthening",ROOT/"output/scp_strengthening"):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or OUT in path.parents:
                continue
            if path.suffix in {".json",".md",".log",".csv",".pdf",".svg",".whl"}:
                evidence.append(path)
    for document in build["documents"]:
        build_log=ROOT/document["log"]["path"]
        if record(build_log)!=document["log"]:
            raise RuntimeError("PDF build log digest differs")
        evidence.append(build_log)
    evidence.extend([*papers,build_path,reproduction_path])
    evidence.extend(ROOT/row["log"] for row in reproduction["stages"])
    evidence=sorted(set(evidence))
    OUT.mkdir(parents=True,exist_ok=True)
    source_zip=OUT/"OrchLang_0.5.0rc3_source.zip"
    subprocess.run(["git","archive","--format=zip","--output",str(source_zip),revision],cwd=ROOT,check=True)
    claims=[
        {"id":"IR","claim":"normalized returned-state and finite-prefix graph refinement","evidence":["proofs/scp_strengthening/SequentialUpdates.v",stage_logs["normalized-ir-proofs"]]},
        {"id":"STATE","claim":"96 completed and 8 cutoff authored pairs; 18 separate supplementary comparisons","evidence":["output/scp_strengthening/source_differential/results.json","research/scp_strengthening/completed_state_review/truth_table_results.json",str(replication_result.relative_to(ROOT))]},
        {"id":"SLICE","claim":"two earlier recorded finite public-source slices (6/12 schedules); fresh stage replays their recorded models, without source execution or whole-file admission","evidence":["research/scp_strengthening/workflow_capsules/REPORT.md",stage_logs["finite-capsule-law-replay"]]},
        {"id":"TRANSFER","claim":"0 admitted; 9/9 held-out candidates unsupported; 1/12 selected repositories had a retrieval failure","evidence":["output/scp_strengthening/heldout/admission_results.json","output/scp_strengthening/heldout/implementation_freeze.json"]},
        {"id":"EXACT","claim":"finite rectangular contract TV 1/2 versus conservative bound 1; exact/oracle checks","evidence":["research/scp_strengthening/exact_uncertain_distance/experiment_results.json",stage_logs["independent-exact-contract-audit"]]},
        {"id":"SCALE","claim":"27 structured cases; 122 groups; 732 raw / 610 measured rows; UNKNOWN retained","evidence":["output/scp_strengthening/scalability/structured_results.json","research/scp_strengthening/scalability/RUN_NOTES.md"]},
        {"id":"API","claim":"offline runner only; provider/model/budget approval pending","evidence":["integrations/provider_calibration/public_request_manifest.json","research/scp_strengthening/provider_calibration/PLAN.md"]},
    ]
    indexed={item["path"] for item in fingerprint}|{str(path.relative_to(ROOT)) for path in evidence}
    for claim in claims:
        for name in claim["evidence"]:
            if name not in indexed or not (ROOT/name).is_file():
                raise RuntimeError("claim evidence missing from source/evidence indices: "+name)
    manifest={"format":"orchlang-scp-strengthening-evidence-index","version":1,
              "software_version":"0.5.0rc3","source_revision":revision,
              "source_archive":record(source_zip),"executable_source_files":fingerprint,
              "reproduction":record(reproduction_path),"papers":[record(path) for path in papers],
              "evidence_files":[record(path) for path in evidence],"claims":claims,
              "author_fields":"placeholders by request","paid_api_calls":0,
              "human_reproduction":"pending","journal_submission":"not performed",
              "custody_scope":"hash/byte custody and passed-stage binding; scientific validity remains the separate proofs/checkers and stated premises"}
    index=OUT/"evidence_index.json"
    index.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    evidence_zip=OUT/"OrchLang_0.5.0rc3_evidence.zip"
    with zipfile.ZipFile(evidence_zip,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in evidence:
            archive.write(path,str(path.relative_to(ROOT)))
        archive.write(index,str(index.relative_to(ROOT)))
    for path in (source_zip,evidence_zip):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("archive CRC failed")
    with zipfile.ZipFile(source_zip) as archive:
        for item in fingerprint:
            if sha(archive.read(item["path"]))!=item["sha256"]:
                raise RuntimeError("archived source hash differs")
    with zipfile.ZipFile(evidence_zip) as archive:
        for item in manifest["evidence_files"]:
            if sha(archive.read(item["path"]))!=item["sha256"]:
                raise RuntimeError("archived evidence hash differs")
    receipt={"source_revision":revision,"evidence_index":record(index),"archives":[record(source_zip),record(evidence_zip)],
             "source_file_count":len(fingerprint),"evidence_file_count":len(evidence),"checks":"source/evidence byte hashes and bothZIP CRC passed"}
    (OUT/"archive_receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print(json.dumps(receipt,sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
