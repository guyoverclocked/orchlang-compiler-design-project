#!/usr/bin/env python3
"""Independently replay every saved controlled finite-channel report.

The exact report, graph and kernel byte strings are supplied to the independent
DFS replayer. Two explicit resource configurations are recorded, including the
default configuration's legitimate UNKNOWN outcome. No provider calls occur.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from replay_probabilistic_report import replay_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPS = {'max_reference_paths': 100_000,
                'max_reference_steps': 1_000_000,
                'max_reference_work_bytes': 64 * 1024**2}
STUDY_CAPS = {'max_reference_paths': 1_000_000,
              'max_reference_steps': 10_000_000,
              'max_reference_work_bytes': 1024**3}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    study_path = ROOT / 'bench/results/probabilistic_channels.json'
    study_bytes = study_path.read_bytes()
    study = json.loads(study_bytes)
    if study.get('status') != 'passed':
        raise ValueError('channel corpus must pass before report replay')
    fixtures = {row['name']: row for row in study['fixtures']}
    out = ROOT / 'bench/results/probabilistic_replay'
    out.mkdir(parents=True, exist_ok=True)
    summary = {'reports': 0, 'study_verified': 0, 'study_unknown': 0,
               'study_rejected': 0, 'default_verified': 0,
               'default_unknown': 0, 'default_rejected': 0}
    result = {'format': 'orchlang-controlled-channel-report-replay', 'version': 1,
              'scope': 'independent reconstruction of finite exact usage histograms and exact metrics; approximate logarithms and producer counters excluded',
              'study_sha256': digest(study_bytes),
              'driver_sha256': digest(Path(__file__).read_bytes()),
              'replayer_sha256': digest((ROOT / 'audit/replay_probabilistic_report.py').read_bytes()),
              'reference_sha256': digest((ROOT / 'audit/probabilistic_reference.py').read_bytes()),
              'caps': {'default': DEFAULT_CAPS, 'study': STUDY_CAPS},
              'rows': [], 'failures': []}
    for row in study['rows']:
        fixture = fixtures[row['name']]
        report_path = ROOT / row['evidence']
        report_bytes = report_path.read_bytes()
        graph_bytes = (ROOT / fixture['graph']).read_bytes()
        kernel_bytes = (ROOT / fixture['kernel']).read_bytes()
        if digest(report_bytes) != row['evidence_sha256']:
            raise ValueError('stale report binding: ' + row['evidence'])
        if digest(graph_bytes) != fixture['source_sha256'] or digest(kernel_bytes) != fixture['kernel_sha256']:
            raise ValueError('stale graph/kernel binding: ' + row['name'])
        summary['reports'] += 1
        saved = {'name': row['name'], 'horizon': row['horizon'], 'observer': row['observer'],
                 'report': row['evidence'], 'report_sha256': digest(report_bytes),
                 'graph_sha256': digest(graph_bytes), 'kernel_sha256': digest(kernel_bytes)}
        for configuration, caps in (('default', DEFAULT_CAPS), ('study', STUDY_CAPS)):
            # Passing bytes prevents accidental path-dependent source substitution.
            attestation = replay_report(report_bytes, graph_bytes, kernel_bytes, **caps)
            status = attestation['status']
            if status not in ('verified', 'unknown', 'rejected'):
                raise ValueError('unexpected independent replay status')
            summary[configuration + '_' + status] += 1
            attestation_path = out / (report_path.stem + '.' + configuration + '.attestation.json')
            attestation_bytes = (json.dumps(attestation, ensure_ascii=False, indent=2) + '\n').encode()
            attestation_path.write_bytes(attestation_bytes)
            saved[configuration] = {'status': status,
                                    'attestation': str(attestation_path.relative_to(ROOT)),
                                    'attestation_sha256': digest(attestation_bytes)}
            if status == 'rejected' or configuration == 'study' and status != 'verified':
                result['failures'].append(row['evidence'] + ': ' + configuration + ' ' + status)
        result['rows'].append(saved)
    if summary['reports'] != study['summary']['channel_analyses']:
        result['failures'].append('replayed report count differs from producer corpus count')
    result['summary'] = summary
    result['status'] = 'passed' if not result['failures'] else 'failed'
    (ROOT / 'bench/results/probabilistic_replay.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'summary': summary, 'failures': result['failures']}, indent=2))
    return 0 if not result['failures'] else 1


if __name__ == '__main__':
    sys.exit(main())
