"""Retain finite reference/replay conformance observations, with exact weights."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.finite_reference import Reference
from runtime.replay_adapter import Replay, enumerate_replay
from tests.test_replay_adapter import conformance_cases, reference_observations, replay_observations


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows, failures = [], []
    for name, contracts, kernels, program, env in conformance_cases():
        reference = Reference(contracts,kernels).run(program,env)
        replay = enumerate_replay(Replay(contracts,kernels),program,env)
        equal = reference_observations(reference) == replay_observations(replay)
        if not equal:
            failures.append(name)
        rows.append(dict(case=name, contracts=contracts, kernels=kernels, program=program, env=env,
                         reference_paths=len(reference), replay_paths=len(replay), exact_equal=equal,
                         observations=[dict(trace=r['trace'],requests=r['requests'],
                                            private_outputs=r['private_outputs'],weight=str(r['weight'])) for r in replay]))
    files = ['runtime/finite_reference.py','runtime/replay_adapter.py','tests/test_replay_adapter.py','scripts/check_replay.py']
    manifest = dict(status='failed' if failures else 'completed',
                    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    dirty_tree=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    files={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                    cases=len(rows), replay_paths=sum(r['replay_paths'] for r in rows), failures=failures,
                    scope='finite-text-table-replay; no-provider-inference',spent_usd='0.00')
    for name, value in [('manifest.json',manifest),('observations.json',rows)]:
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(manifest,indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
