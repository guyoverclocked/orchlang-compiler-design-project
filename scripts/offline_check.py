"""Fresh CPU development validation with immutable output/provenance.

Usage: python scripts/offline_check.py --cxx /absolute/path/to/g++ --output DIR
This is a development validation run, not a frozen final comparative experiment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.structural_baseline import structural_bound


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "c++"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lean", help="Pinned Lean executable; include proof checks when supplied")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)  # Never overwrite raw evidence.
    commands = []
    failures = []

    def run(argv, expected=0):
        started = time.perf_counter()
        try:
            process = subprocess.run([str(a) for a in argv], cwd=ROOT, capture_output=True,
                                     encoding="utf-8", errors="replace", timeout=300)
        except (OSError, subprocess.TimeoutExpired) as error:
            process = subprocess.CompletedProcess(argv, 127, "", str(error))
        name = f"{len(commands):03d}"
        commands.append(dict(argv=[str(a) for a in argv], exit=process.returncode,
                             seconds=time.perf_counter() - started, stdout=process.stdout,
                             stderr=process.stderr))
        if process.returncode != expected:
            failures.append(f"command {name}: expected {expected}, got {process.returncode}")
        return process

    source_commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = run(["git", "status", "--porcelain=v1"]).stdout
    (out / "working-tree.patch").write_text(run(["git", "diff", "--binary", "HEAD"]).stdout,
                                           encoding="utf-8")
    inputs = sorted(set(p for folder in ("src", "include", "tests", "scripts", "runtime", "proof",
                                         "bench/cost", "bench/corpus", "bench/protocols")
                        for p in (ROOT / folder).rglob("*")
                        if p.is_file() and "__pycache__" not in p.parts and
                        p.suffix in {".cpp", ".hpp", ".py", ".json", ".orch", ".lean", ".md"}))
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in inputs}
    hashes["bench/structural_baseline.py"] = digest(ROOT / "bench/structural_baseline.py")
    hashes["proof/lean-toolchain"] = digest(ROOT / "proof/lean-toolchain")
    (out / "source-files.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    # A source snapshot digest supplements the base commit when the tree is dirty.
    snapshot_hash = digest(out / "source-files.json")
    toolenv = os.environ.copy()
    compiler_dir = str(Path(args.cxx).resolve().parent)
    if Path(args.cxx).is_absolute():
        os.environ["PATH"] = compiler_dir + os.pathsep + toolenv.get("PATH", "")
    version = run([args.cxx, "--version"]).stdout
    executable_suffix = ".exe" if os.name == "nt" else ""
    test_binary = out / ("orchlang_tests" + executable_suffix)
    cli = out / ("orchc" + executable_suffix)
    core = sorted(p for p in (ROOT / "src").glob("*.cpp") if p.name != "main.cpp")
    flags = ["-std=c++17", "-Wall", "-Wextra", "-pedantic", "-O2", "-Iinclude"]
    run([args.cxx, *flags, *core, ROOT / "tests/tests.cpp", "-o", test_binary])
    run([args.cxx, *flags, *core, ROOT / "src/main.cpp", "-o", cli])
    rows = []
    if not failures:
        run([test_binary])
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
        smoke_source = "bench/corpus/development/public-control.orch"
        for malformed_flags in (["--seed", "-1"], ["--seed", "18446744073709551616"],
                      ["--chars-per-token", "1x"], ["--retry-failure", "oops"],
                      ["--pin", "x=2garbage"], ["--pin", "=1"], ["--pin", "x=-1"]):
            run([cli, "run", smoke_source, *malformed_flags], 2)
        for pin, diagnostic in (("x=11", "R002"), ("typo=true", "R003"), ("x=true", "R003")):
            result = run([cli, "run", smoke_source, "--pin", pin], 1)
            if f"[{diagnostic}]" not in result.stderr:
                failures.append("invalid pin lacks required runtime diagnostic: " + pin)
        if args.lean:
            version_result = run([args.lean, "--version"])
            if "version 4.19.0," not in version_result.stdout:
                failures.append("proof toolchain must be Lean 4.19.0")
            for proof in sorted((ROOT / "proof").glob("*.lean")):
                result = run([args.lean, proof])
                if "sorryAx" in result.stdout or "uses 'sorry'" in result.stdout:
                    failures.append(proof.name + ": incomplete proof")
        corpus = json.loads((ROOT / "bench/corpus/development/manifest.json").read_text())
        for case in corpus["cases"]:
            if case["path"] is None:
                rows.append(dict(id=case["id"], category=case["category"], status="unsupported"))
                continue
            result = run([cli, "check", case["path"]], case["exit"])
            if case.get("diagnostic") and f'[{case["diagnostic"]}]' not in result.stderr:
                failures.append(case["id"] + ": wrong/missing diagnostic; not a successful rejection")
            rows.append(dict(id=case["id"], category=case["category"], exit=result.returncode))
        for path in sorted((ROOT / "bench/cost").glob("*.orch")):
            report = run([cli, "certify", path])
            ir = run([cli, "ir-json", path])
            if report.returncode or ir.returncode:
                continue  # Already recorded as failure, never a successful case.
            bound = json.loads(report.stdout)["workflows"][0]["bound"]
            base = structural_bound(json.loads(ir.stdout)["workflows"][0])
            if (bound["estimated_tokens"], bound["guaranteed_tokens"], bound["total_tokens"]) != (
                    base["input"], base["output"], base["total"]):
                failures.append(path.name + ": production and structural baseline disagree")
            row = dict(id=path.stem, category="historical-cost-development",
                       structural=base, production=bound, runs=[])
            for seed in range(1, 6):
                executed = run([cli, "run", path, "--seed", str(seed)])
                match = re.search(r"actual tokens\s+(\d+)\s+\(input (\d+) \+ output (\d+)\)", executed.stdout)
                if match is None:
                    failures.append(path.name + ": malformed runtime observation")
                    continue
                total, i, o = map(int, match.groups())
                if total > base["total"] or i > base["input"] or o > base["output"]:
                    failures.append(path.name + ": bound violation")
                row["runs"].append(dict(seed=seed, input=i, output=o, total=total))
            rows.append(row)
        positives = sorted((ROOT / "examples/valid").glob("*.orch"))
        positives += [ROOT / "examples/boundary" / f"{n}.orch" for n in
                      ("zero_budget", "long_identifier", "retry_one", "empty_branch")]
        for path in positives:
            run([cli, "check", path])
        for path in sorted((ROOT / "examples/invalid").glob("*.orch")):
            p = run([cli, "check", path], 1)
            if not re.search(r"error \[[A-Z]\d+\]", p.stderr):
                failures.append(path.name + ": failure lacks a source diagnostic")
    manifest = dict(schema_version="1", status="failed" if failures else "completed",
                    purpose="development-validation-not-final-experiment", source_commit=source_commit,
                    dirty_tree=bool(dirty), source_snapshot_sha256=snapshot_hash,
                    corpus_manifest_sha256=digest(ROOT / "bench/corpus/development/manifest.json"),
                    observer="aggregate-abstract-contract-usage", backend="mock-and-finite-development",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
                    platform=platform.platform(), compiler=version, flags=flags,
                    seeds=list(range(1, 6)), external_workflows=0,
                    proof_checked=bool(args.lean),
                    budget_usd_cap="5.00", spent_usd="0.00", outstanding_reserved_usd="0.00",
                    failures=failures)
    (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=manifest["status"], output=str(out), failures=failures), indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
