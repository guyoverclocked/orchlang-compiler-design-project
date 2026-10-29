"""Fault injection, not a competitive baseline. Mutates isolated copies only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("conflate-model-binding", "src/relational.cpp",
     "node.model = site.modelContract;", "node.model = site.modelName;", "cpp"),
    ("erase-request-content", "src/relational.cpp",
     "model == other.model && inputSize == other.inputSize &&\n"
     "                   requestTemplate == other.requestTemplate &&\n"
     "                   requestArguments == other.requestArguments",
     "model == other.model && inputSize == other.inputSize", "cpp"),
    ("omit-retry-multiplication", "src/cost_analyzer.cpp",
     "const CostBound bound = repeat(body, retry.bound);", "const CostBound bound = body;", "cpp"),
    ("drop-billed-failure", "runtime/finite_reference.py",
     "trace=state.trace + (event,)",
     'trace=state.trace + (() if event.status == "error" else (event,))', "python"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["PATH"] = str(Path(args.cxx).resolve().parent) + os.pathsep + env["PATH"]
    records = []
    for name, relative, old, new, language in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="mutation-", dir=args.scratch.resolve()) as temp:
            workspace = Path(temp)
            for folder in ("src", "include", "tests", "runtime", "bench"):
                shutil.copytree(ROOT / folder, workspace / folder,
                                ignore=shutil.ignore_patterns("__pycache__", "*.exe", "results", "raw"))
            path = workspace / relative
            original = path.read_text(encoding="utf-8")
            if original.count(old) != 1:
                raise ValueError(name + ": mutation target must occur exactly once")
            path.write_text(original.replace(old, new), encoding="utf-8")
            record = dict(id=name, kind="deliberately-unsound-fault-injection",
                          source_sha256=hashlib.sha256(original.encode()).hexdigest())
            if language == "cpp":
                sources = sorted(p for p in (workspace / "src").glob("*.cpp") if p.name != "main.cpp")
                binary = workspace / ("tests.exe" if os.name == "nt" else "tests-bin")
                cmd = [args.cxx, "-std=c++17", "-Wall", "-Wextra", "-pedantic", "-O2",
                       "-Iinclude", *map(str, sources), "tests/tests.cpp", "-o", str(binary)]
                built = subprocess.run(cmd, cwd=workspace, env=env, capture_output=True,
                                       encoding="utf-8", errors="replace", timeout=300)
                record["build_exit"] = built.returncode
                record["build_stderr"] = built.stderr
                if built.returncode:
                    record["status"] = "infrastructure-failure"
                    records.append(record)
                    continue
                test_cmd = [str(binary)]
            else:
                test_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                            "-p", "test_finite_reference.py", "-v"]
            result = subprocess.run(test_cmd, cwd=workspace, env=env, capture_output=True,
                                    encoding="utf-8", errors="replace", timeout=300)
            marker = "FAIL " if language == "cpp" else "FAIL: "
            detected = result.returncode == 1 and marker in result.stderr
            record.update(status="detected" if detected else "survived-or-infrastructure-failure",
                          test_exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
            records.append(record)
            print(name + ": " + record["status"], flush=True)
    failed = any(record["status"] != "detected" for record in records)
    (args.output / "mutations.json").write_text(json.dumps(dict(
        purpose="development-fault-injection", status="failed" if failed else "completed",
        mutations=records, spent_usd="0.00"), indent=2) + "\n", encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
