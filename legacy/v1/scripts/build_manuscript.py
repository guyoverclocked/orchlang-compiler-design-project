"""Compile the saved manuscript twice and retain diagnostics/source hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--pdflatex",default=shutil.which("pdflatex"))
    a=p.parse_args()
    if not a.pdflatex:
        raise ValueError("pdflatex with elsarticle is required")
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/"docs/manuscript"
    commands=[]
    for _ in range(2):
        argv=[a.pdflatex,"-interaction=nonstopmode","-halt-on-error",
              "-output-directory="+str(out),"main.tex"]
        r=subprocess.run(argv,cwd=source,capture_output=True,text=True,timeout=180)
        commands.append(dict(argv=argv,exit=r.returncode,stdout=r.stdout,stderr=r.stderr))
        (out/"commands.json").write_text(json.dumps(commands,indent=2)+"\n",encoding="utf-8")
        if r.returncode:
            raise RuntimeError(r.stdout[-6000:]+r.stderr)
    log=(out/"main.log").read_text(encoding="utf-8",errors="replace")
    unresolved=bool(re.search(r"undefined references|Citation .+ undefined|Reference .+ undefined",log))
    manifest=dict(status="failed" if unresolved else "completed",
        undefined_references=unresolved,overfull_boxes=re.findall(r"Overfull .+? at lines? [^\n]+",log),
        pdf_sha256=hashlib.sha256((out/"main.pdf").read_bytes()).hexdigest(),
        sources={f.relative_to(source).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in source.rglob("*.tex")})
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status=manifest["status"],pdf=str(out/"main.pdf"),
                         overfull_boxes=manifest["overfull_boxes"])))
    return int(unresolved)


if __name__=="__main__":
    raise SystemExit(main())
