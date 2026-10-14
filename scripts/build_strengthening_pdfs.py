#!/usr/bin/env python3
"""Export the two saved standalone TeX sources and bind their PDF build bytes.

Use the app compiler first for document diagnostics. This Tectonic step exports
PDFs and a custody receipt; it does not replace scientific or visual review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def record(path):
    return {"path":str(path.relative_to(ROOT)),"bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript",type=Path,required=True)
    parser.add_argument("--supplement",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"output/pdf")
    args=parser.parse_args()
    compiler=shutil.which("tectonic")
    if compiler is None:
        raise RuntimeError("PDF export requires Tectonic; preserve source and use app preview")
    destination=args.output_dir.resolve()
    destination.mkdir(parents=True,exist_ok=True)
    publication=ROOT/"output/scp_strengthening/publication"
    publication.mkdir(parents=True,exist_ok=True)
    receipt={"status":"running","compiler":compiler,
             "compiler_version":subprocess.check_output([compiler,"--version"]).decode().strip(),
             "builder":record(Path(__file__).resolve()),"documents":[],
             "scope":"recorded export command/source/PDF custody; visual QA and scientific validity are separate"}
    for path in (args.manuscript.resolve(),args.supplement.resolve()):
        before=record(path)
        command=[compiler,"--keep-logs","--outdir",str(destination),str(path)]
        result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=180)
        log=publication/(path.stem+".build.log")
        log.write_text(result.stdout+result.stderr)
        if result.returncode or record(path)!=before:
            receipt["status"]="failed"
            receipt["documents"].append({"source":before,"exit_code":result.returncode,"log":record(log)})
            (publication/"pdf_build.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
            raise RuntimeError("PDF export failed or source drifted: "+str(path))
        pdf=destination/(path.stem+".pdf")
        entry={"source":before,"pdf":record(pdf),"command":command,"exit_code":0,"log":record(log)}
        if shutil.which("pdfinfo"):
            entry["pdfinfo"]=subprocess.check_output(["pdfinfo",str(pdf)]).decode()
        receipt["documents"].append(entry)
    receipt["status"]="passed"
    (publication/"pdf_build.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":receipt["status"],"documents":[row["pdf"]["path"] for row in receipt["documents"]]}))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
