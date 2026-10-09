#!/usr/bin/env python3
"""Reproduce the current artifact from local source and a pinned local baseline.

Core, auditor and evaluation need only make/C++17/Python3. No provider/network
requests are made. Presentation/PDF builds are separate optional artifacts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9'
OUT = ROOT / 'audit/final'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(folders, suffixes):
    """Inventory project sources without traversing optional runtime environments."""
    paths = []
    excluded = {'.git', '.venv', 'node_modules', '__pycache__', '.build', 'dist'}
    for folder in folders:
        for directory, names, filenames in os.walk(ROOT / folder):
            names[:] = sorted(name for name in names if name not in excluded)
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.suffix in suffixes:
                    paths.append(path)
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--baseline', default=BASELINE,
                     help='locally available baseline revision; default is the audited preceding version')
    cli.add_argument('--quick', action='store_true', help='skip the long experiment grids and baseline build')
    cli.add_argument('--sanitize', action='store_true', help='run ASan/UBSan then rebuild optimized')
    cli.add_argument('--package', action='store_true', help='also build and isolated-test analysis/replay wheel (needs pip/setuptools/wheel)')
    cli.add_argument('--integration-python', type=Path,
                     help='optional interpreter from the pinned LangGraph environment; never installs packages')
    args = cli.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    started = datetime.now(timezone.utc).isoformat()
    def executable_inputs():
        inventory = source_inventory(
            ('src', 'include', 'tests', 'audit', 'bench', 'examples', 'scripts', 'integrations', 'demo'),
            {'.cpp', '.hpp', '.py', '.orch', '.html', '.js', '.in', '.lock'})
        for folder in ('examples/graphs', 'examples/channels'):
            inventory.update(source_inventory((folder,), {'.json'}))
        for name in ('Makefile', 'pyproject.toml', 'README.md', 'LICENSE', 'demo/offline_evidence.json'):
            inventory[name] = sha(ROOT / name)
        return inventory
    initial_inputs = executable_inputs()
    # A failed new run must not leave a previous PASSED manifest in its place.
    (OUT / 'manifest.json').write_text(json.dumps({'format': 'orchlang-final-reproduction',
        'version': 3, 'started_utc': started, 'status': 'running'}, indent=2) + '\n')

    def run(label, argv, cwd=ROOT, display=None, expected=0):
        result = subprocess.run([str(x) for x in argv], cwd=cwd,
                                capture_output=True, text=True)
        (OUT / (label + '.log')).write_text(result.stdout + result.stderr)
        entries.append({'stage': label, 'argv': display or [str(x) for x in argv],
                        'exit_code': result.returncode, 'expected_exit_code': expected,
                        'log': 'audit/final/' + label + '.log'})
        print('%s: exit %d' % (label, result.returncode), flush=True)
        if result.returncode != expected:
            raise RuntimeError('%s failed; read %s' % (label, OUT / (label + '.log')))
        return result

    try:
        if args.sanitize:
            run('sanitizer', ['make', 'sanitize'])
            run('optimized-clean', ['make', 'clean'])
        run('optimized-check', ['make', 'check'])
        run('python-tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'audit',
                              '-p', 'test_*.py', '-v'],
            display=['python3', '-m', 'unittest', 'discover', '-s', 'audit', '-p',
                     'test_*.py', '-v'])
        run('demo-http-tests', [sys.executable, '-m', 'unittest', 'demo.test_server', '-v'],
            display=['python3', '-m', 'unittest', 'demo.test_server', '-v'])
        for path in sorted((ROOT / 'examples/research/accepted').glob('*.orch')):
            label = 'accept-' + path.stem
            run(label, ['./orchc', 'check', str(path.relative_to(ROOT))])
            for command in ('certify', 'ir-json'):
                output = run(label + '-' + command,
                             ['./orchc', command, str(path.relative_to(ROOT))])
                json.loads(output.stdout)
        for path in sorted((ROOT / 'examples/research/rejected').glob('*.orch')):
            result = subprocess.run(['./orchc', 'check', str(path.relative_to(ROOT))],
                                    cwd=ROOT, capture_output=True, text=True)
            label = 'reject-' + path.stem
            (OUT / (label + '.log')).write_text(result.stdout + result.stderr)
            codes = re.findall(r'\[([ELP]\d{3})\]', result.stderr)
            expected = 'E267' if path.stem == 'cross_model_chain' else 'E236'
            entries.append({'stage': label, 'exit_code': result.returncode,
                            'diagnostics': codes, 'expected': expected,
                            'log': 'audit/final/' + label + '.log'})
            if result.returncode == 0 or expected not in codes:
                raise RuntimeError('%s did not produce %s' % (path.name, expected))
        if not args.quick:
            run('generated-evaluation', [sys.executable, 'bench/evaluate.py'],
                display=['python3', 'bench/evaluate.py'])
            revision = subprocess.check_output(['git', 'rev-parse', args.baseline + '^{commit}'],
                                                cwd=ROOT, text=True).strip()
            if revision != BASELINE:
                raise ValueError('comparison requires audited baseline ' + BASELINE)
            archived = subprocess.check_output(['git', 'archive', revision], cwd=ROOT)
            with tempfile.TemporaryDirectory(prefix='orchlang-reproduce-baseline-') as directory:
                baseline_root = Path(directory)
                with tarfile.open(fileobj=io.BytesIO(archived)) as archive:
                    # git archive contains the repository's own revision, no external tar input.
                    for member in archive.getmembers():
                        destination = (baseline_root / member.name).resolve()
                        if baseline_root.resolve() not in destination.parents:
                            raise ValueError('archive path escapes baseline checkout')
                    if hasattr(tarfile, 'data_filter'):
                        archive.extractall(baseline_root, filter='data')
                    else:  # Older Python 3.10: checked local git archive only.
                        archive.extractall(baseline_root)
                run('baseline-build', ['make'], cwd=baseline_root, display=['make', '(baseline)'])
                for label, mode in [('sourced-ordinal', []),
                                    ('sourced-request-sensitive', ['--request-sensitive-oracle'])]:
                    run(label, [sys.executable, 'bench/evaluate_sourced.py', '--baseline',
                                str(baseline_root / 'orchc')] + mode,
                        display=['python3', 'bench/evaluate_sourced.py', '--baseline', '$BASELINE/orchc'] + mode)
            for name in ('sourced.json', 'sourced_request_sensitive.json'):
                evidence = json.loads((ROOT / 'bench/results' / name).read_text())
                if evidence['failures'] or evidence['environment']['compiler_sha256'] != sha(ROOT / 'orchc'):
                    raise ValueError('failed or stale source study: ' + name)
            for label, script in [('relational-fulltext-stress', 'audit/relational_stress.py'),
                                  ('cyclic-graph-grid', 'audit/evaluate_graphs.py'),
                                  ('cyclic-graph-property-probe', 'audit/graph_adversarial.py'),
                                  ('source-graph-bridge-study', 'audit/evaluate_source_graphs.py'),
                                  ('finite-probabilistic-channels', 'audit/evaluate_probabilistic_channels.py'),
                                  ('independent-channel-report-replay', 'audit/evaluate_probabilistic_replay.py'),
                                  ('all-finite-horizon-bisimulation', 'audit/evaluate_stochastic_bisimulation.py'),
                                  ('exact-all-finite-horizon-trace-equivalence', 'audit/evaluate_trace_equivalence.py')]:
                run(label, [sys.executable, script], display=['python3', script])
        if args.integration_python:
            integration_python = args.integration_python.expanduser().absolute()
            if not integration_python.is_file():
                raise ValueError('optional integration interpreter does not exist: ' + str(integration_python))
            run('langgraph-backend-tests', [integration_python, '-m', 'unittest', '-v',
                'integrations.langgraph.test_backend'],
                display=['$LANGGRAPH_PYTHON', '-m', 'unittest', '-v', 'integrations.langgraph.test_backend'])
            run('langgraph-source-frontend-tests', [integration_python, '-m', 'unittest', '-v',
                'integrations.langgraph.source_frontend.test_extract'],
                display=['$LANGGRAPH_PYTHON', '-m', 'unittest', '-v', 'integrations.langgraph.source_frontend.test_extract'])
            if not args.quick:
                run('actual-langgraph-backend-study', [integration_python, '-m', 'integrations.langgraph.benchmark'],
                    display=['$LANGGRAPH_PYTHON', '-m', 'integrations.langgraph.benchmark'])
                run('actual-langgraph-source-study', [integration_python, '-m', 'integrations.langgraph.source_frontend.study'],
                    display=['$LANGGRAPH_PYTHON', '-m', 'integrations.langgraph.source_frontend.study'])
        if args.package:
            run('installed-wheel-validation', [sys.executable, 'scripts/package_graph_tools.py'],
                display=['python3', 'scripts/package_graph_tools.py'])
        final_inputs = executable_inputs()
        if final_inputs != initial_inputs:
            changed = sorted(name for name in set(initial_inputs) | set(final_inputs)
                             if initial_inputs.get(name) != final_inputs.get(name))
            raise ValueError('executable inputs changed during reproduction; rerun after freezing: ' + ', '.join(changed))
        files = sorted((ROOT / 'bench/results').rglob('*'))
        manifest = {'format': 'orchlang-final-reproduction', 'version': 3,
                    'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
                    'platform': platform.platform(), 'python': platform.python_version(),
                    'base_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                             cwd=ROOT, text=True).strip(),
                    'working_source': 'release-candidate edits are bound by the file inventory; base_revision alone is not their identity',
                    'baseline_revision': BASELINE, 'quick': args.quick, 'sanitizer_requested': args.sanitize,
                    'packaging_requested': args.package,
                    'optional_langgraph_requested': bool(args.integration_python),
                    'integration_interpreter': str(args.integration_python.expanduser().absolute()) if args.integration_python else None,
                    'compiler_sha256': sha(ROOT / 'orchc'), 'stages': entries,
                    'inputs_unchanged_during_run': True,
                    'executable_input_sha256': final_inputs,
                    'results_sha256': {str(p.relative_to(ROOT)): sha(p) for p in files if p.is_file()},
                    'core_source_sha256': source_inventory(
                        ('src', 'include', 'tests', 'audit', 'bench', 'examples', 'scripts', 'integrations', 'demo'),
                        {'.cpp', '.hpp', '.py', '.orch', '.html', '.js'}),
                    'graph_fixture_sha256': {str(p.relative_to(ROOT)): sha(p)
                        for p in sorted((ROOT / 'examples/graphs').rglob('*.json'))},
                    'channel_fixture_sha256': {str(p.relative_to(ROOT)): sha(p)
                        for p in sorted((ROOT / 'examples/channels').rglob('*.json'))},
                    'integration_source_sha256': source_inventory(('integrations',), {'.py', '.in', '.lock'}),
                    'integration_artifact_sha256': {str(p.relative_to(ROOT)): sha(p)
                        for p in sorted((ROOT / 'integrations/langgraph/source_frontend').rglob('*.json'))},
                    'demo_snapshot_sha256': {'demo/offline_evidence.json': sha(ROOT / 'demo/offline_evidence.json')},
                    'package_source_sha256': {'pyproject.toml': sha(ROOT / 'pyproject.toml')},
                    'package_result_sha256': {str(p.relative_to(ROOT)): sha(p)
                        for p in sorted((ROOT / 'output/release').rglob('*'))
                        if p.is_file() and p.suffix in ('.whl', '.json')},
                    'status': 'passed',
                    'limits': ['offline mocks; no paid/provider measurements',
                               'cost report auditor does not verify IFC/relational proof',
                               'source-pattern abstractions are author-created after language design',
                               'cyclic graph theorem is conditional; no termination or finite whole-cycle budget',
                               'graph value/property probes share producer schema; independent replay checks closure',
                               'source bridge and Python AST frontend cover explicit subsets, not arbitrary framework extraction',
                               'finite channel replay verifies exact facts; approximate logarithms and producer counters excluded',
                               'stochastic bisimulation is sufficient for all finite horizons under supplied finite models; split blocks inconclusive',
                               'exact trace equivalence is a known weighted-automaton method over the same supplied finite model; finite witnesses and independent replay do not validate provider premises',
                               'cumulative runtime resource monitors and provider probability validity excluded from the all finite horizon theorem',
                               'optional LangGraph execution remains offline and supports no claim of external adoption',
                               'demo has fixed fixtures, bounded localhost execution and explicitly labeled saved evidence']}
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (OUT / 'failed-run.json').unlink(missing_ok=True)
        print('Reproduction passed; audit/final/manifest.json records hashes and logs.')
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        failure = {'format': 'orchlang-final-reproduction', 'version': 3, 'status': 'failed',
                   'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
                   'error': str(error), 'stages': entries}
        (OUT / 'failed-run.json').write_text(json.dumps(failure, indent=2) + '\n')
        (OUT / 'manifest.json').write_text(json.dumps(failure, indent=2) + '\n')
        print('Reproduction failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
