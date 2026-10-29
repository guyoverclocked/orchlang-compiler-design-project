"""Build fresh C++ test and CLI binaries with ASan/UBSan, retaining commands."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx",default="g++")
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if os.name == "nt":
        raise ValueError("this sanitizer tier requires the documented Linux toolchain")
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    commands,failures=[],[]
    def run(argv,expected=0):
        start=time.perf_counter()
        r=subprocess.run(list(map(str,argv)),cwd=ROOT,capture_output=True,text=True,timeout=300)
        commands.append(dict(argv=list(map(str,argv)),exit=r.returncode,stdout=r.stdout,
            stderr=r.stderr,seconds=time.perf_counter()-start))
        if r.returncode != expected:
            failures.append(dict(command=len(commands)-1,expected=expected,exit=r.returncode))
        return r
    version=run([a.cxx,"--version"]).stdout
    sources=sorted((ROOT/"src").glob("*.cpp"))
    core=[f for f in sources if f.name != "main.cpp"]
    flags=["-std=c++17","-Wall","-Wextra","-pedantic","-O1","-g",
        "-fsanitize=address,undefined","-fno-omit-frame-pointer","-Iinclude"]
    tests,cli=out/"orchlang_tests",out/"orchc"
    run([a.cxx,*flags,*core,ROOT/"tests/tests.cpp","-o",tests])
    run([a.cxx,*flags,*core,ROOT/"src/main.cpp","-o",cli])
    if not failures:
        r=run([tests])
        if not re.search(r"Passed 106/106 tests",r.stdout):
            failures.append("C++ test census did not complete")
        for f in sorted((ROOT/"examples/valid").glob("*.orch")):
            run([cli,"check",f])
            run([cli,"certify",f])
        for f in sorted((ROOT/"examples/invalid").glob("*.orch")):
            run([cli,"check",f],1)
    manifest=dict(status="failed" if failures else "completed",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),compiler=version,flags=flags,
        source_hashes={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
            for f in [*sources,*sorted((ROOT/"include").glob("*.hpp")),ROOT/"tests/tests.cpp"]},
        failures=failures,source_commit=subprocess.check_output(
            ["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        dirty_tree=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip()))
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (out/"commands.json").write_text(json.dumps(commands,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status=manifest["status"],commands=len(commands),failures=failures)))
    return int(bool(failures))


if __name__=="__main__":
    raise SystemExit(main())
