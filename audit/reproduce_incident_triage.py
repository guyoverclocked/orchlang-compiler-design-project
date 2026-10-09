#!/usr/bin/env python3
"""Reproduce the separately scoped pinned-source incident-triage extension.

Run after installing integrations/incident_triage/requirements.lock in its
documented Python 3.14.6 environment. This command installs nothing. The clean
upstream checkout is reconstructed from the repository's local Git bundle;
the actual graph runners block network/process activity during executions.
The base compiler/evaluation reproduction remains audit/reproduce_final.py.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'integrations/incident_triage'
OUT = ROOT / 'audit/incident_triage'
PIN = 'c08f710acfeefe233329df613fe8358eaac5f350'
BUNDLE_SHA = 'deb487b425c49d95c39cd9ff2d689dc56401f66ffd44f7ae17fbe9a691849080'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory() -> dict[str, str]:
    files = {}
    excluded = {'.git', '.venv', '__pycache__', 'node_modules'}
    for folder in (CASE, ROOT / 'audit'):
        for directory, names, filenames in os.walk(folder):
            names[:] = sorted(name for name in names if name not in excluded)
            if OUT == Path(directory):
                names[:] = []
                continue
            for name in sorted(filenames):
                path = Path(directory) / name
                if folder == CASE or path.suffix == '.py':
                    files[str(path.relative_to(ROOT))] = sha(path)
    return dict(sorted(files.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integration-python', type=Path, required=True,
                        help='already installed exact pinned incident-triage environment')
    args = parser.parse_args(argv)
    runtime = args.integration_python.expanduser().absolute()
    OUT.mkdir(parents=True, exist_ok=True)
    initial = inventory()
    started = datetime.now(timezone.utc).isoformat()
    stages = []
    manifest_path = OUT / 'manifest.json'
    manifest_path.write_text(json.dumps({'format': 'orchlang-incident-extension-reproduction',
        'version': 1, 'status': 'running', 'started_utc': started}, indent=2) + '\n')

    def run(label: str, command: list, *, env=None):
        result = subprocess.run([str(item) for item in command], cwd=ROOT,
                                env=env, capture_output=True, text=True)
        log_path = OUT / (label + '.log')
        log_path.write_text(result.stdout + result.stderr, encoding='utf-8')
        stages.append({'stage': label, 'exit_code': result.returncode,
                       'log': str(log_path.relative_to(ROOT)),
                       'argv': [str(item) for item in command]})
        print(f'{label}: exit {result.returncode}', flush=True)
        if result.returncode:
            raise ValueError(f'{label} failed; read {log_path.relative_to(ROOT)}')
        return result

    def same(label: str, actual: Path, expected: Path):
        if actual.read_bytes() != expected.read_bytes():
            raise ValueError(f'{label}: fresh artifact differs from the recorded reference')

    try:
        if not runtime.is_file():
            raise ValueError('required interpreter does not exist')
        bundle = CASE / 'upstream_c08f710.bundle'
        if sha(bundle) != BUNDLE_SHA:
            raise ValueError('local upstream bundle differs from the audited source custody digest')
        run('source-bundle-verification', ['git', 'bundle', 'verify', bundle])
        with tempfile.TemporaryDirectory(prefix='orchlang-incident-reproduction-') as temp:
            checkout = Path(temp) / 'upstream'
            run('source-offline-clone', ['git', 'clone', '--quiet', '--no-checkout', bundle, checkout])
            run('source-pinned-checkout', ['git', '-C', checkout, 'checkout', '--quiet', '--detach', PIN])
            env = dict(os.environ, INCIDENT_TRIAGE_UPSTREAM=str(checkout))
            run('direct-source-tests', [runtime, '-m', 'unittest', 'discover', '-s', CASE,
                                        '-p', 'test_study.py', '-v'], env=env)
            fresh_study = OUT / 'source_study.json'
            run('direct-source-execution', [runtime, CASE / 'run_study.py', '--upstream', checkout,
                                            '--output', fresh_study], env=env)
            same('direct-source-byte-reproduction', fresh_study, CASE / 'results/source_study.json')
            run('independent-direct-source-replay', [sys.executable, CASE / 'verify_results.py', fresh_study])

            run('source-protocol-tests', [sys.executable, '-m', 'unittest',
                'integrations.incident_triage.source_analysis.test_source_analysis', '-v'])
            bridge_out = OUT / 'source_analysis'
            run('source-protocol-and-classifier-graph', [sys.executable, CASE / 'source_analysis/bridge.py',
                '--upstream', CASE / 'upstream_snapshot', '--study', fresh_study, '--output-dir', bridge_out])
            for path in sorted((CASE / 'source_analysis/artifacts').glob('*.json')):
                same('source-protocol-byte-reproduction:' + path.name, bridge_out / path.name, path)
            run('independent-source-protocol-replay', [sys.executable, CASE / 'source_analysis/replay_projection.py',
                bridge_out / 'source_analysis.json', CASE / 'upstream_snapshot', '--study', fresh_study,
                '--attestation', OUT / 'source_protocol.attestation.json'])

            run('concurrency-and-session-tests', [runtime, '-m', 'unittest', 'discover',
                '-s', CASE / 'concurrency', '-p', 'test_*.py', '-v'], env=env)
            fresh_race = OUT / 'concurrency_study.json'
            run('controlled-concurrent-source-execution', [runtime, CASE / 'concurrency/run_concurrency_study.py',
                '--upstream', checkout, '--output', fresh_race], env=env)
            same('concurrency-byte-reproduction', fresh_race, CASE / 'concurrency/results/concurrency_study.json')
            run('independent-concurrency-witness-replay', [sys.executable,
                CASE / 'concurrency/verify_concurrency_study.py', fresh_race, '--upstream', checkout])
            manager = run('isolated-session-manager-demo', [runtime,
                CASE / 'concurrency/demo_isolated_sessions.py'], env=env)
            manager_output = json.loads(manager.stdout)
            if manager_output.get('active_sessions_after_approval') != 0 \
                    or len(manager_output.get('starts', [])) != 2 \
                    or any(row.get('model_calls_before') != 2 or row.get('model_calls_after') != 2
                           or row.get('status') != 'approved' for row in manager_output.get('approvals', [])):
                raise ValueError('isolated session demo has an invalid continuation receipt')
            (OUT / 'isolated_session_demo.json').write_text(manager.stdout, encoding='utf-8')

            run('source-protocol-path-tests', [sys.executable, '-m', 'unittest', 'discover',
                '-s', CASE / 'protocol_paths', '-p', 'test_*.py', '-v'], env=env)
            fresh_paths = OUT / 'protocol_paths.json'
            run('source-protocol-path-execution', [runtime, CASE / 'protocol_paths/run_protocol_paths.py',
                '--upstream', checkout, '--output', fresh_paths], env=env)
            same('protocol-path-byte-reproduction', fresh_paths, CASE / 'protocol_paths/results/protocol_paths.json')
            run('independent-protocol-path-replay', [sys.executable,
                CASE / 'protocol_paths/verify_protocol_paths.py', fresh_paths, checkout,
                '--attestation', OUT / 'protocol_paths.attestation.json'])
            if subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain',
                                        '--untracked-files=all'], text=True).strip():
                raise ValueError('pinned upstream checkout changed during execution')

        final = inventory()
        if final != initial:
            changed = sorted(name for name in set(initial) | set(final) if initial.get(name) != final.get(name))
            raise ValueError('extension inputs changed during reproduction: ' + ', '.join(changed))
        result_files = sorted(OUT.rglob('*'))
        manifest = {
            'format': 'orchlang-incident-extension-reproduction', 'version': 1, 'status': 'passed',
            'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
            'python': platform.python_version(), 'platform': platform.platform(),
            'integration_interpreter': str(runtime), 'source_commit': PIN,
            'source_bundle_sha256': BUNDLE_SHA, 'inputs_unchanged_during_run': True,
            'input_sha256': final, 'stages': stages,
            'result_sha256': {str(path.relative_to(ROOT)): sha(path) for path in result_files
                              if path.is_file() and path != manifest_path},
            'byte_identical_reproductions': ['22-run direct source study', 'source AST protocol and classifier graph artifacts',
                                             'controlled concurrency witness', '12-run scripted source-path study'],
            'scope': [
                'one unchanged pinned MIT-licensed third-party workflow, with synthetic incidents and offline clients',
                'the full source dependency claim is conditional and source-specific, not a generic Python translator or mechanized Python proof',
                'the OrchGraph certificate covers only the first classifier request pair',
                'the race is one controlled schedule; the manager is a bounded pinned MockLLM utility',
                'scripted gpt-4o-mini name/nominal prices exercise source branches only; no provider execution or invoice measurements',
                'raw incident state/checkpoint privacy and external dispatch behavior are excluded',
                'independent replay checks source bytes, arithmetic and records; it is not a second LangGraph interpreter',
                'the separate base 44-stage compiler reproduction must also be run'],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (OUT / 'failed-run.json').unlink(missing_ok=True)
        print(f'Incident extension reproduction passed: {len(stages)} stages.', flush=True)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        failure = {'format': 'orchlang-incident-extension-reproduction', 'version': 1, 'status': 'failed',
            'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
            'error': str(error), 'stages': stages}
        manifest_path.write_text(json.dumps(failure, indent=2) + '\n', encoding='utf-8')
        (OUT / 'failed-run.json').write_text(json.dumps(failure, indent=2) + '\n', encoding='utf-8')
        print('Incident extension reproduction failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
