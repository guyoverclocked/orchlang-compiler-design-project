#!/usr/bin/env python3
"""Re-execute authored state studies without overwriting frozen observations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.scp_strengthening.source_differential import run as primary
from research.scp_strengthening.completed_state_review import truth_table_run as truth

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    frozen = ROOT / "output/scp_strengthening/source_differential"
    if destination == frozen or frozen in destination.parents:
        raise RuntimeError("replication must not replace the frozen primary record")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("replication destination is populated; choose a fresh directory")
    destination.mkdir(parents=True, exist_ok=True)
    primary.OUT = destination
    shutil.copyfile(frozen / "protocol.json", destination / "protocol.json")
    # Run the original hash-bound harness unchanged, with only its output
    # destination redirected. It still validates every source/tool digest.
    sys.argv = [str(primary.__file__)]
    code = primary.main()
    if code:
        return code
    protocol = json.loads(truth.PROTOCOL_PATH.read_bytes())
    result = truth.run_experiment(protocol)
    truth._save(destination / "truth_table_replication.json", result)
    if result["failures"]:
        print(json.dumps(result["failures"]))
        return 1
    print("Truth-table fresh replication: 18 runs, no failures")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
