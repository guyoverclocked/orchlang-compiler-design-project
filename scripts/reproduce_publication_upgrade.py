#!/usr/bin/env python3
"""Run the publication studies against one frozen source revision.

Install the two existing locked optional environments first. Corpus selection
is never repeated here: evaluate the preregistered, frozen original sources.
No provider credentials, paid calls, submission or release upload is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/publication_upgrade"
sys.path.insert(0, str(ROOT / "audit"))
from publication_provenance import digest  # noqa: E402
from publication_run_integrity import (  # noqa: E402
    REQUIRED_STAGES,
    RunIntegrityError,
    capture_run_outputs,
    frozen_source_inventory,
    validate_run_record,
)


def frozen_sources(revision: str) -> dict[str, str]:
    return frozen_source_inventory(ROOT, revision)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-revision", default="HEAD")
    cli.add_argument("--integration-python", type=Path, default=ROOT / ".venv/bin/python")
    cli.add_argument("--incident-python", type=Path, default=ROOT / "integrations/incident_triage/.venv/bin/python")
    cli.add_argument("--coqc", default="coqc")
    cli.add_argument("--repetitions", type=int, default=5)
    args = cli.parse_args()
    if args.repetitions < 5:
        cli.error("the publication scaling study requires at least five repetitions")
    revision = subprocess.check_output(["git", "rev-parse", args.source_revision + "^{commit}"], cwd=ROOT, text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD^{commit}"], cwd=ROOT, text=True).strip()
    if head != revision:
        print(
            "Refusing to run: the requested source revision must be HEAD so the core reproduction's "
            "base_revision identifies the exact source tree (requested " + revision + ", HEAD " + head + ").",
            file=sys.stderr,
        )
        return 2
    inventory = frozen_sources(revision)
    OUT.mkdir(parents=True, exist_ok=True)
    logs = OUT / "reproduction"
    logs.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    state = {"format": "orchlang-publication-upgrade-reproduction", "version": 2,
             "source_revision": revision, "status": "running", "started_utc": started,
             "source_files_sha256": inventory,
             "platform": platform.platform(), "python": platform.python_version(), "stages": []}
    run_path = logs / "run.json"
    run_path.write_text(json.dumps(state, indent=2) + "\n")

    def run(label, command):
        stage_started = datetime.now(timezone.utc).isoformat()
        command = [str(x) for x in command]
        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        path = logs / (label + ".log")
        path.write_text(completed.stdout, encoding="utf-8")
        stage_completed = datetime.now(timezone.utc).isoformat()
        relative_log = str(path.relative_to(ROOT))
        state["stages"].append({"name": label, "exit_code": completed.returncode,
                                "started_utc": stage_started, "completed_utc": stage_completed,
                                "log": relative_log, "log_sha256": digest(path.read_bytes()),
                                "argv": command})
        run_path.write_text(json.dumps(state, indent=2) + "\n")
        print(label + ": exit " + str(completed.returncode), flush=True)
        if completed.returncode:
            raise RuntimeError("stage failed; read " + str(path.relative_to(ROOT)))
        return completed.stdout

    try:
        run("core-and-langgraph", [sys.executable, "audit/reproduce_final.py", "--sanitize", "--package",
                                  "--integration-python", args.integration_python])
        run("observer-ablation", [sys.executable, "research/publication_upgrade/observer_ablation.py",
                                  "--output", "output/publication_upgrade/observer_ablation.json"])
        run("incident-original-source", [sys.executable, "audit/reproduce_incident_triage.py",
                                         "--integration-python", args.incident_python])
        run("external-original-source-corpus", [sys.executable, "scripts/publication_upgrade_corpus.py", "--evaluate"])
        run("local-tokenizer-calibration", [args.integration_python,
                                           "research/publication_upgrade/tokenizer_calibration.py"])
        run("solver-scaling", [sys.executable, "research/publication_upgrade/solver_scaling.py",
                               "--repetitions", args.repetitions, "--sizes", "2,8,16,32,64,128,256",
                               "--output", "research/publication_upgrade/solver_scaling.json",
                               "--input-dir", "research/publication_upgrade/solver_inputs"])
        run("solver-paired-baseline", [sys.executable, "research/publication_upgrade/run_solver_baseline.py",
                                       "--repetitions", args.repetitions, "--warmups", 1,
                                       "--sizes", "2,8,16,32,64,128,256",
                                       "--output", "research/publication_upgrade/solver_scaling_baseline.json"])
        run("solver-plot", [sys.executable, "research/publication_upgrade/plot_solver_scaling.py",
                            "research/publication_upgrade/solver_scaling.json",
                            "research/publication_upgrade/solver_scaling",
                            "--baseline", "research/publication_upgrade/solver_scaling_baseline.json"])
        # Proof compilation is required rather than silently replaced by a text inspection.
        proof = ROOT / "proofs/publication_upgrade"
        for name in ("AtomicUpdates.v", "Assumptions.v"):
            if not (proof / name).is_file():
                raise ValueError("missing current-semantics proof: " + str(proof / name))
            output = run("proof-" + Path(name).stem, [args.coqc, "-Q", str(proof), "PublicationUpgrade", str(proof / name)])
            if name == "Assumptions.v" and output.count("Closed under the global context") != 2:
                raise ValueError("current-semantics theorems have unexpected global assumptions")
        if frozen_sources(revision) != inventory:
            raise ValueError("source inputs changed during the publication run")
        # Freeze all generated evidence and logs before marking this run as passed.
        state["outputs_sha256"] = capture_run_outputs(ROOT)
        state["completed_utc"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "passed"
        validate_run_record(state, ROOT, revision, inventory)
        run_path.write_text(json.dumps(state, indent=2) + "\n")
        print("Publication studies passed at " + revision)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, RunIntegrityError) as error:
        state.update(status="failed", error=str(error), completed_utc=datetime.now(timezone.utc).isoformat())
        run_path.write_text(json.dumps(state, indent=2) + "\n")
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
