"""Differential source binding + executable Lean certificate checks; immutable output."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.finite_reference import Unsupported
from runtime.source_gate import read_source, issue, bind_certificate
from scripts.closed_certificate import check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--programs', required=True, type=Path)
    p.add_argument('--lean', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = json.loads(args.programs.read_text(encoding='utf-8'))
    pairs, expected, outcomes, failures, certificates = [], [], [], [], []
    for row in rows:
        data = row['source'].encode('utf-8')
        parsed = read_source(data)
        # Use the left arm as an untrusted plan candidate even on unsafe programs.
        plan = parsed['program'][2]
        pairs.append([parsed['program'], plan])
        expected.append(row['trace_identity_accepts'])
        if row['accepted']:
            cert = issue(data)
            certificates.append(dict(id=row['id'], certificate=cert))
            pairs.append(bind_certificate(data, cert)); expected.append(True)
            tampered = dict(cert, plan=['skip'])
            pairs.append(bind_certificate(data, tampered)); expected.append(False)
            for changed in (data + b'\n', data.replace(b'max_tokens ', b'max_tokens 9', 1)):
                try:
                    bind_certificate(changed, cert)
                    failures.append(f"source tamper accepted: {row['id']}")
                except Unsupported:
                    pass
    result, stdout = check(args.lean.resolve(), pairs, args.output.resolve())
    for i, (got, want) in enumerate(zip(result, expected)):
        outcomes.append(dict(id=i, checked=got, expected=want))
        if got != want:
            failures.append(f'Lean disagreement {i}')
    # Parser fail-closed checks, kept distinct from semantic rejection.
    malformed = [[], [['unknown'], ['skip']], [['skip', 0], ['skip']],
                 [['skip'], ['branch', 0, ['skip'], ['skip']]]]
    for i, item in enumerate(malformed):
        try:
            check(args.lean.resolve(), [item], args.output.resolve())
            failures.append(f'malformed JSON core accepted: {i}')
        except ValueError:
            pass
    manifest = dict(status='failed' if failures else 'completed',
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    dirty_tree=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)),
                    programs_sha256=hashlib.sha256(args.programs.read_bytes()).hexdigest(),
                    source_programs=len(rows), lean_checks=len(pairs), certificates_issued=len(certificates),
                    source_tampers_rejected=2*len(certificates), malformed_batches_rejected=len(malformed),
                    failures=failures, scope='closed-source-reader-trusted; decoded-core-theorem', spent_usd='0.00')
    for name, content in [('manifest.json', manifest), ('outcomes.json', outcomes), ('certificates.json', certificates)]:
        (args.output/name).write_text(json.dumps(content, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    (args.output/'lean.txt').write_text(stdout, encoding='utf-8', newline='\n')
    print(json.dumps(manifest, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
