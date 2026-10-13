#!/usr/bin/env python3
"""Run the frozen solver study against the pre-optimization Git snapshot.

This helper extracts only the requested Git commit into a temporary directory
and asks ``solver_scaling.py`` to import its producer and replayer. The study
inputs remain the committed-by-the-study files in ``solver_inputs/`` and their
hashes are checked against the optimized run before and after measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "5aa4ebc669a3fbae72d9a605be250624fd0bcbf5"
STUDY = ROOT / "research/publication_upgrade/solver_scaling.py"


def _extract_git_archive(destination: Path, revision: str) -> None:
    archive = destination / "baseline.tar"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar",
                    "--output", str(archive), revision], check=True)
    root = destination / "source"
    root.mkdir()
    with tarfile.open(archive, "r:") as bundle:
        members = bundle.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts
                    or not (member.isdir() or member.isfile())):
                raise SystemExit(f"unsafe or unsupported Git archive entry: {member.name}")
        for member in members:
            target = root.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit(f"missing archive payload: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def _input_identity(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "kernel_sha256": document["inputs"]["kernel_sha256"],
        "graphs": [(row["calls_per_arm"], row["sha256"])
                   for row in document["inputs"]["graphs"]],
    }


def _check_frozen_inputs(path: Path, expected: dict[str, object]) -> None:
    actual = _input_identity(path)
    if actual != expected:
        raise SystemExit("solver input hashes differ from the optimized study")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimized-results", type=Path,
                        default=ROOT / "research/publication_upgrade/solver_scaling.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "research/publication_upgrade/solver_scaling_baseline.json")
    parser.add_argument("--sizes", default="2,8,16,32,64,128,256")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    if args.repetitions < 5:
        raise SystemExit("baseline comparison requires at least five repetitions")

    expected = _input_identity(args.optimized_results.resolve())
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orchlang-solver-baseline-") as temp_name:
        temp = Path(temp_name)
        _extract_git_archive(temp, BASELINE_REVISION)
        command = [
            sys.executable, str(STUDY), "--implementation-root", str(temp / "source"),
            "--implementation-name", f"baseline commit {BASELINE_REVISION}",
            "--sizes", args.sizes, "--repetitions", str(args.repetitions),
            "--warmups", str(args.warmups), "--timeout-seconds", str(args.timeout_seconds),
            "--input-dir", str(ROOT / "research/publication_upgrade/solver_inputs"),
            "--output", str(args.output.resolve()),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
    _check_frozen_inputs(args.output.resolve(), expected)
    print(f"baseline study written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
