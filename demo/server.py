#!/usr/bin/env python3
"""Bounded localhost demo runner for OrchLang research artifacts.

The HTTP API accepts only fixed fixture identifiers and small scalar controls.
Every subprocess uses a fixed argv assembled here, ``shell=False``, a timeout,
the repository root as its working directory, and fixed source/tool paths. No
provider, external service, arbitrary filesystem path, or user command is run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path(__file__).resolve().parent
COMPILER = ROOT / 'orchc'
MAX_BODY_BYTES = 16 * 1024
MAX_HTTP_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CHILD_OUTPUT_BYTES = 8 * 1024 * 1024
CHILD_TIMEOUT_SECONDS = 8
MAX_HORIZON = 8
MAX_GRAPH_CALLS = 8
MAX_CHANNEL_STATES = 10_000
MAX_CHANNEL_WORK = 16 * 1024 * 1024
MAX_BISIM_STATES = 5_000
MAX_BISIM_TRANSITIONS = 50_000
MAX_CONTROL_STEPS = 100_000

sys.path.insert(0, str(ROOT / 'audit'))
from orchgraph import Graph, reference_run, strict_json, utf8  # noqa: E402


FIXTURES: dict[str, dict[str, Any]] = {
    'budget-leak': {
        'title': 'Same budget. Different request usage.',
        'eyebrow': '01 / BOUNDED COMPILER',
        'kind': 'source',
        'path': 'bench/relational/reject/DifferentArgument.orch',
        'description': 'A secret flag selects between public inputs with different pinned lengths. Both arms fit the same declared caps, but their input usage differs.',
        'default': {'xLength': 37, 'yLength': 61},
    },
    'balanced-chain': {
        'title': 'Aligned calls can stay private.',
        'eyebrow': '02 / DEPENDENT CHAIN',
        'kind': 'source',
        'path': 'examples/research/accepted/chain_matched.orch',
        'description': 'Each private arm makes two calls. The second call consumes the first result; matching request identity and result correspondence keeps the ordered billing trace aligned.',
        'default': {'sourceLength': 8},
        'companion': 'equivalent_dependent_chain',
    },
    'productive-cycle': {
        'title': 'A productive cycle, replayed.',
        'eyebrow': '03 / FINITE-CONTROL GRAPH',
        'kind': 'graph',
        'path': 'examples/graphs/accepted/unbounded_productive_cycle.json',
        'description': 'A secret choice enters either side of a two-call loop. The product checker closes its finite relation; the sample traces are bounded probes, not a total-cost or termination proof.',
        'default': {'query': 'hello', 'horizon': 8},
    },
    'aggregate-order': {
        'title': 'Aggregation can hide order.',
        'eyebrow': '04 / EXACT FINITE CHANNEL',
        'kind': 'channel',
        'path': 'examples/channels/aggregate_hides_order.graph.json',
        'kernel': 'examples/channels/aggregate_hides_order.kernel.json',
        'description': 'The two alternatives use output sequences (1, 3) and (3, 1). Their aggregate total is the same; the ordered usage trace differs completely.',
        'default': {'horizon': 2},
    },
    'noisy-bit': {
        'title': 'A noisy usage bit.',
        'eyebrow': '05 / EXACT FINITE CHANNEL',
        'kind': 'channel',
        'path': 'examples/channels/noisy_usage_bit.graph.json',
        'kernel': 'examples/channels/noisy_usage_bit.kernel.json',
        'description': 'A finite rational kernel leaks partially through output usage. The exact total variation is 1/2; the all-horizon sufficient bisimulation check splits the roots and reports inconclusive.',
        'default': {'horizon': 1},
    },
    'same-mean': {
        'title': 'Same mean. Different laws.',
        'eyebrow': '06 / EXACT FINITE CHANNEL',
        'kind': 'channel',
        'path': 'examples/channels/same_mean_distinct_laws.graph.json',
        'kernel': 'examples/channels/same_mean_distinct_laws.kernel.json',
        'description': 'One alternative always uses two output tokens; the other uses one or three with equal probability. The expected usage matches, while total variation is one.',
        'default': {'horizon': 1},
    },
    'bisim-gap': {
        'title': 'Equal laws. Different hidden states.',
        'eyebrow': '07 / EXACT TRACE EQUIVALENCE',
        'kind': 'channel',
        'path': 'examples/channels/trace_equal_not_bisimilar.graph.json',
        'kernel': 'examples/channels/trace_equal_not_bisimilar.kernel.json',
        'description': 'Different hidden transition structures produce the same ordered usage law. Bisimulation is inconclusive; exact rational trace equivalence proves equality for every finite call horizon under this supplied model.',
        'default': {'horizon': 2},
    },
    'source-case': {
        'title': 'A real workflow needs an isolated meter.',
        'eyebrow': '08 / PINNED SOURCE AND INDEPENDENT REPLAY',
        'kind': 'source-case',
        'path': 'integrations/incident_triage/upstream_snapshot/src/triage/graph.py',
        'description': 'Check the source-specific request protocol, then replay a recorded concurrent execution: two incident IDs share one meter. Separate graph instances restore attribution in the tested control.',
        'default': {},
    },
}


class DemoError(Exception):
    """A bounded local demo operation failed closed."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _tool_sha(relative: str) -> str:
    return _sha((ROOT / relative).read_bytes())


def _fixed_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if ROOT not in path.parents or not path.is_file():
        raise DemoError('fixed demo fixture is missing or invalid')
    return path


def _command(argv: list[str], *, timeout: int = CHILD_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run one fixed local command without a shell and bound time/output."""
    try:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            shell=False,
            env={**os.environ, 'PYTHONNOUSERSITE': '1'},
        )
    except subprocess.TimeoutExpired as error:
        raise DemoError('local analysis exceeded its 8-second subprocess limit') from error
    except OSError as error:
        raise DemoError('could not start a fixed local analysis command') from error
    if len(result.stdout) + len(result.stderr) > MAX_CHILD_OUTPUT_BYTES:
        raise DemoError('local analysis output exceeded its 8 MiB limit')
    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'digest': _sha(
            b'exit=' + str(result.returncode).encode('ascii') + b'\nstdout\0' +
            result.stdout + b'\nstderr\0' + result.stderr
        ),
    }


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DemoError(f'{label} did not produce valid JSON') from error


def _output_text(raw: bytes) -> str:
    return raw.decode('utf-8', errors='replace')[:20_000]


def _artifact(label: str, digest: str, kind: str) -> dict[str, str]:
    return {'label': label, 'sha256': digest, 'kind': kind}


def _base_result(fixture_id: str, source_raw: bytes) -> dict[str, Any]:
    meta = FIXTURES[fixture_id]
    return {
        'fixture': fixture_id,
        'title': meta['title'],
        'eyebrow': meta['eyebrow'],
        'description': meta['description'],
        'execution': 'live',
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': {
            'path': meta['path'],
            'sha256': _sha(source_raw),
            'text': source_raw.decode('utf-8'),
        },
        'compiler_sha256': _sha(COMPILER.read_bytes()) if COMPILER.is_file() else None,
        'artifacts': [_artifact(meta['path'], _sha(source_raw), 'source')],
        'assumptions': [
            'All model behavior is offline and synthetic; the server never calls a provider.',
            'UTF-8 byte and declared token bounds are abstract contracts, not real provider tokenizer guarantees.',
        ],
    }


def _source_check(path: Path) -> dict[str, Any]:
    result = _command([str(COMPILER), 'check', str(path)])
    diagnostic_text = _output_text(result['stderr'] + result['stdout'])
    diagnostic_codes = sorted(set(re.findall(r'\bE\d{3}\b', diagnostic_text)))
    return {
        'status': 'accepted' if result['returncode'] == 0 else 'rejected',
        'returncode': result['returncode'],
        'diagnostics': diagnostic_text.strip(),
        'diagnostic_codes': diagnostic_codes,
        'sha256': result['digest'],
        'tool': 'orchc check',
    }


def _source_run(path: Path, pins: list[str], *, unsafe: bool = False,
                request_sensitive: bool = False) -> tuple[dict[str, Any], bytes]:
    argv = [str(COMPILER), 'run', str(path), '--seed', '3']
    if unsafe:
        argv.append('--audit-unsafe')
    if request_sensitive:
        argv.append('--request-sensitive-oracle')
    for pin in pins:
        argv.extend(['--pin', pin])
    argv.append('--json')
    result = _command(argv)
    if result['returncode'] != 0:
        raise DemoError('fixed offline compiler witness run failed: ' + _output_text(result['stderr']))
    parsed = _decode_json(result['stdout'], 'orchc run')
    if not isinstance(parsed, dict) or not isinstance(parsed.get('workflows'), list):
        raise DemoError('orchc run returned an unexpected JSON structure')
    return {'workflows': parsed['workflows'], 'sha256': result['digest']}, result['stdout']


def _request_plan_from_certificate(report: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for workflow in report.get('workflows', []):
        for fact in workflow.get('call_facts', []):
            contract = fact.get('model_contract', {})
            plan.append({
                'location': fact.get('location'),
                'result': fact.get('result'),
                'contract': {
                    'provider': contract.get('provider'),
                    'model': contract.get('model'),
                    'max_tokens': contract.get('max_tokens'),
                    'stable_key': contract.get('stable_key'),
                },
                'template': fact.get('template_text'),
                'arguments': [
                    {
                        'position': atom.get('position'),
                        'kind': atom.get('kind'),
                        'expression_kind': atom.get('literal_expr_kind'),
                        'binding': atom.get('name'),
                        'binding_id': atom.get('binding_id'),
                        'value_id': atom.get('value_id'),
                        'literal': atom.get('literal_text'),
                    }
                    for atom in fact.get('arguments', [])
                ],
            })
    return plan


def _source_evaluate(fixture_id: str, options: dict[str, Any]) -> dict[str, Any]:
    meta = FIXTURES[fixture_id]
    source_path = _fixed_path(meta['path'])
    source_raw = source_path.read_bytes()
    response = _base_result(fixture_id, source_raw)
    response['source']['path'] = meta['path']
    response['checks'] = [_source_check(source_path)]
    response['traces'] = []

    artifacts = response['artifacts']
    artifacts.append(_artifact('orchc check', response['checks'][0]['sha256'], 'compiler'))
    if fixture_id == 'budget-leak':
        x_length = options.get('xLength', meta['default']['xLength'])
        y_length = options.get('yLength', meta['default']['yLength'])
        for flag in (False, True):
            run, _ = _source_run(
                source_path,
                [f'x={x_length}', f'y={y_length}', 's=0', f'flag={str(flag).lower()}'],
                unsafe=True,
            )
            workflow = run['workflows'][0]
            response['traces'].append({
                'scenario': 'flag=true selects x' if flag else 'flag=false selects y',
                'secret': flag,
                'bypass': '--audit-unsafe · offline witness only',
                'workflow': workflow,
                'sha256': run['sha256'],
            })
            artifacts.append(_artifact('offline witness run ' + str(flag).lower(), run['sha256'], 'run'))
        response['request_plan'] = [
            {
                'scenario': 'flag=true', 'contract': 'mock:offline-m / cap 60',
                'template': 'Process this payload: {payload}',
                'argument': f'outer(x), pinned length {x_length}',
            },
            {
                'scenario': 'flag=false', 'contract': 'mock:offline-m / cap 60',
                'template': 'Process this payload: {payload}',
                'argument': f'outer(y), pinned length {y_length}',
            },
        ]
        response['selected_inputs'] = {'x_length': x_length, 'y_length': y_length}
        response['cost_bound'] = 'Both arms use the same declared cap; the concrete outer input lengths differ.'
        response['security_result'] = 'E236 · the normal execution gate rejects mismatched requests.'
        return response

    # The independent auditor's bind operation invokes `orchc certify`, binds
    # the exact source/compiler hashes, and returns the source-derived cost audit.
    with tempfile.TemporaryDirectory(prefix='orchlang-demo-source-') as temp:
        report_path = Path(temp) / 'certificate.json'
        audit = _command([
            sys.executable, str(ROOT / 'audit' / 'certificate_audit.py'),
            '--compiler', str(COMPILER), 'bind', str(source_path), str(report_path),
        ])
        envelope_raw = report_path.read_bytes()
    envelope = _decode_json(envelope_raw, 'source-bound compiler certificate')
    cert_report = envelope.get('certificate')
    if not isinstance(cert_report, dict):
        raise DemoError('source-cost auditor omitted the compiler certificate')
    response['certificate'] = cert_report
    response['request_plan'] = _request_plan_from_certificate(cert_report)
    artifacts.append(_artifact('source-bound compiler certificate', _sha(envelope_raw), 'certificate'))
    audit_result = _decode_json(audit['stdout'], 'independent source-cost auditor')
    response['cost_replay'] = audit_result
    artifacts.append(_artifact('independent source-cost audit', audit['digest'], 'replay'))
    if audit['returncode'] != 0 or not audit_result.get('verified'):
        raise DemoError('independent source-cost audit did not verify the compiler report')

    source_length = options.get('sourceLength', meta['default']['sourceLength'])
    for choose in (False, True):
        run, _ = _source_run(
            source_path,
            [f'source={source_length}', f'choose={str(choose).lower()}'],
            request_sensitive=True,
        )
        workflow = run['workflows'][0]
        response['traces'].append({
            'scenario': 'choose=true' if choose else 'choose=false',
            'secret': choose,
            'workflow': workflow,
            'sha256': run['sha256'],
        })
        artifacts.append(_artifact('request-sensitive run ' + str(choose).lower(), run['sha256'], 'run'))
    response['selected_inputs'] = {'source_length': source_length}
    response['security_result'] = 'Compiler check/certificate accepted; independent cost derivation verified.'
    if meta.get('companion'):
        response['companion'] = _channel_analysis(meta['companion'], options.get('horizon', 2))
        artifacts.extend(response['companion']['artifacts'])
    return response


def _graph_evaluate(fixture_id: str, options: dict[str, Any]) -> dict[str, Any]:
    meta = FIXTURES[fixture_id]
    graph_path = _fixed_path(meta['path'])
    raw_graph = graph_path.read_bytes()
    graph_response = _base_result(fixture_id, raw_graph)
    graph_response['source'] = {
        'path': meta['path'], 'sha256': _sha(raw_graph), 'text': raw_graph.decode('utf-8')
    }
    with tempfile.TemporaryDirectory(prefix='orchlang-demo-graph-') as temp:
        certificate_path = Path(temp) / 'graph-certificate.json'
        checked = _command([
            sys.executable, str(ROOT / 'audit' / 'orchgraph.py'), str(graph_path),
            '--max-nodes', '50000', '--report', str(certificate_path),
        ])
        report = _decode_json(checked['stdout'], 'request-graph checker')
        graph_response['graph_check'] = {
            'status': report.get('status'),
            'report': report,
            'sha256': checked['digest'],
        }
        graph_response['artifacts'].append(_artifact('request-graph certificate', checked['digest'], 'certificate'))
        graph_response['graph_replay'] = None
        if report.get('status') == 'accepted' and checked['returncode'] == 0:
            replay = _command([
                sys.executable, str(ROOT / 'audit' / 'replay_graph_certificate.py'),
                str(graph_path), str(certificate_path),
            ])
            attestation = _decode_json(replay['stdout'], 'independent graph replayer')
            graph_response['graph_replay'] = {
                'status': attestation.get('status'),
                'attestation': attestation,
                'sha256': replay['digest'],
            }
            graph_response['artifacts'].append(_artifact('independent graph replay', replay['digest'], 'replay'))
            if replay['returncode'] != 0 or attestation.get('status') != 'verified':
                raise DemoError('independent graph certificate replay did not verify')
        elif checked['returncode'] not in (0, 1, 2):
            raise DemoError('request-graph checker failed unexpectedly')

    parsed_graph = Graph(strict_json(raw_graph))
    query = options.get('query', 'hello')
    if not isinstance(query, str):
        raise DemoError('query must be text')
    try:
        query_bytes = utf8(query)
    except UnicodeEncodeError as error:
        raise DemoError('query must contain valid Unicode scalar values') from error
    if len(query_bytes) > 128:
        raise DemoError('query must be at most 128 UTF-8 bytes')
    if parsed_graph.estimate(query) > parsed_graph.inputs['query']['max_tokens']:
        raise DemoError('query exceeds the fixture’s declared public-input token bound')
    horizon = options.get('horizon', MAX_GRAPH_CALLS)
    traces = []
    for route in (False, True):
        run = reference_run(
            parsed_graph,
            {'query': query, 'route': route},
            seed=3,
            max_calls=horizon,
        )
        traces.append(_shape_graph_trace('route=true' if route else 'route=false', route, run))
    graph_response['traces'] = traces
    graph_response['selected_inputs'] = {'query': query, 'horizon': horizon, 'seed': 3}
    graph_response['security_result'] = (
        'Graph certificate accepted and independently replayed. Sampled traces are bounded probes; '
        'productive cycles have no finite total-cost or termination claim.'
    )
    graph_response['assumptions'] += [
        'The offline reference oracle is deterministic and keyed by graph, seed, resolved contract, ordinal, template, and ordered arguments.',
        'The displayed trace stops after at most eight calls; it is not a proof that the cycle terminates.',
    ]
    return graph_response


def _shape_graph_trace(label: str, route: bool, run: dict[str, Any]) -> dict[str, Any]:
    rows = run.get('trace', [])
    calls = []
    totals: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, 1):
        contract = row['contract']
        key = f"{contract['provider']}:{contract['model']}"
        calls.append({
            'index': index,
            'contract': {'provider': contract['provider'], 'model': contract['model'],
                         'max_tokens': contract['max_tokens']},
            'ordinal': row['ordinal'],
            'template': row['template'],
            'arguments': row['arguments'],
            'input_tokens': row['input_tokens'],
            'output_tokens': row['output_tokens'],
            'response': row['response'],
        })
        bill = totals.setdefault(key, {
            'contract': {'provider': contract['provider'], 'model': contract['model']},
            'calls': 0, 'input_tokens': 0, 'output_tokens': 0,
        })
        bill['calls'] += 1
        bill['input_tokens'] += row['input_tokens']
        bill['output_tokens'] += row['output_tokens']
    return {
        'scenario': label,
        'secret': route,
        'calls': calls,
        'ordered_usage': [
            {'call': row['index'], 'input_tokens': row['input_tokens'],
             'output_tokens': row['output_tokens']} for row in calls
        ],
        'aggregate_billing': list(totals.values()),
        'stopped': run.get('stopped'),
        'truncated_at_calls': run.get('truncated_at_calls'),
    }


def _channel_analysis(name: str, horizon: int) -> dict[str, Any]:
    graph_relative = f'examples/channels/{name}.graph.json'
    kernel_relative = f'examples/channels/{name}.kernel.json'
    graph_path, kernel_path = _fixed_path(graph_relative), _fixed_path(kernel_relative)
    raw_graph, raw_kernel = graph_path.read_bytes(), kernel_path.read_bytes()
    scenarios = '[{"values":{"secret":false},"prior":"1/2"},{"values":{"secret":true},"prior":"1/2"}]'
    report_rows: dict[str, Any] = {}
    artifacts = [
        _artifact(graph_relative, _sha(raw_graph), 'source'),
        _artifact(kernel_relative, _sha(raw_kernel), 'source'),
    ]
    for observer in ('aggregate', 'trace'):
        with tempfile.TemporaryDirectory(prefix='orchlang-demo-channel-') as temp:
            report_path = Path(temp) / 'channel-report.json'
            analyzed = _command([
                sys.executable, str(ROOT / 'audit' / 'probabilistic_channels.py'),
                str(graph_path), str(kernel_path), '--public-json', '{}',
                '--scenarios-json', scenarios, '--horizon', str(horizon),
                '--max-states', str(MAX_CHANNEL_STATES), '--max-work-bytes', str(MAX_CHANNEL_WORK),
                '--observer', observer, '--report', str(report_path),
            ])
            if analyzed['returncode'] not in (0, 2):
                raise DemoError('finite channel analysis failed: ' + _output_text(analyzed['stderr']))
            report = _decode_json(analyzed['stdout'], 'finite channel analyzer')
            replayed = _command([
                sys.executable, str(ROOT / 'audit' / 'replay_probabilistic_report.py'),
                str(report_path), str(graph_path), str(kernel_path),
                '--max-reference-paths', '10000', '--max-reference-steps', '100000',
                '--max-reference-work-bytes', str(MAX_CHANNEL_WORK),
            ])
            if replayed['returncode'] not in (0, 1, 2):
                raise DemoError('finite channel replay failed unexpectedly')
            attestation = _decode_json(replayed['stdout'], 'finite channel replayer')
            if report.get('status') == 'complete' and attestation.get('status') != 'verified':
                raise DemoError('independent finite channel replay did not verify')
            report_rows[observer] = {
                'status': report.get('status'),
                'observer': observer,
                'horizon': horizon,
                'rows': report.get('rows'),
                'metrics': report.get('metrics'),
                'replay': {
                    'status': attestation.get('status'),
                    'attestation': attestation,
                    'sha256': replayed['digest'],
                },
                'report_sha256': analyzed['digest'],
                'report': report,
            }
            artifacts.append(_artifact(f'{observer} channel report h={horizon}', analyzed['digest'], 'analysis'))
            artifacts.append(_artifact(f'{observer} channel replay h={horizon}', replayed['digest'], 'replay'))

    secret_scenarios = '[{"secret":false},{"secret":true}]'
    with tempfile.TemporaryDirectory(prefix='orchlang-demo-bisim-') as temp:
        report_path = Path(temp) / 'bisimulation.json'
        analyzed = _command([
            sys.executable, str(ROOT / 'audit' / 'stochastic_bisimulation.py'),
            str(graph_path), str(kernel_path), '--public-json', '{}',
            '--scenarios-json', secret_scenarios,
            '--max-states', str(MAX_BISIM_STATES), '--max-work-bytes', str(MAX_CHANNEL_WORK),
            '--report', str(report_path),
        ])
        if analyzed['returncode'] not in (0, 2, 3):
            raise DemoError('all-horizon bisimulation failed: ' + _output_text(analyzed['stderr']))
        report = _decode_json(analyzed['stdout'], 'stochastic bisimulation checker')
        replayed = _command([
            sys.executable, str(ROOT / 'audit' / 'replay_stochastic_certificate.py'),
            str(report_path), str(graph_path), str(kernel_path),
            '--public-json', '{}', '--scenarios-json', secret_scenarios,
            '--max-states', str(MAX_BISIM_STATES), '--max-transitions', str(MAX_BISIM_TRANSITIONS),
            '--max-work-bytes', str(MAX_CHANNEL_WORK), '--max-control-steps', str(MAX_CONTROL_STEPS),
        ]) if report.get('status') in ('proved_equal', 'inconclusive') else None
        attestation = _decode_json(replayed['stdout'], 'stochastic certificate replayer') if replayed else None
        if replayed and (replayed['returncode'] not in (0, 1, 2) or attestation.get('status') != 'verified'):
            raise DemoError('independent stochastic certificate replay did not verify')
        bisimulation = {
            'status': report.get('status'),
            'claim': report.get('claim'),
            'state_count': report.get('closed_system', {}).get('state_count') if report.get('closed_system') else None,
            'root_blocks': report.get('partition_certificate', {}).get('initial_scenario_blocks') if report.get('partition_certificate') else None,
            'replay': {'status': attestation.get('status'), 'attestation': attestation,
                       'sha256': replayed['digest']} if replayed else None,
            'report_sha256': analyzed['digest'],
            'report': report,
        }
        artifacts.append(_artifact('all-horizon bisimulation certificate', analyzed['digest'], 'analysis'))
        if replayed:
            artifacts.append(_artifact('independent bisimulation replay', replayed['digest'], 'replay'))

    with tempfile.TemporaryDirectory(prefix='orchlang-demo-trace-law-') as temp:
        report_path = Path(temp) / 'trace-equivalence.json'
        analyzed = _command([
            sys.executable, str(ROOT / 'audit' / 'trace_equivalence.py'),
            str(graph_path), str(kernel_path), '--public-json', '{}',
            '--scenarios-json', secret_scenarios,
            '--max-states', str(MAX_BISIM_STATES), '--max-work-bytes', str(MAX_CHANNEL_WORK),
            '--max-matrix-entries', '1000000', '--report', str(report_path),
        ])
        if analyzed['returncode'] not in (0, 1, 3):
            raise DemoError('exact trace-law analysis failed: ' + _output_text(analyzed['stderr']))
        exact_report = _decode_json(analyzed['stdout'], 'exact trace-law checker')
        replayed = _command([
            sys.executable, str(ROOT / 'audit' / 'replay_trace_equivalence.py'),
            str(report_path), str(graph_path), str(kernel_path),
            '--public-json', '{}', '--scenarios-json', secret_scenarios,
            '--max-states', str(MAX_BISIM_STATES), '--max-transitions', str(MAX_BISIM_TRANSITIONS),
            '--max-work-bytes', str(MAX_CHANNEL_WORK), '--max-matrix-entries', '1000000',
            '--max-control-steps', str(MAX_CONTROL_STEPS),
        ]) if exact_report.get('status') in ('proved_equal', 'unequal') else None
        attestation = _decode_json(replayed['stdout'], 'exact trace-law replayer') if replayed else None
        if replayed and (replayed['returncode'] != 0 or attestation.get('status') != 'verified'):
            raise DemoError('independent exact trace-law replay did not verify')
        trace_equivalence = {
            'status': exact_report.get('status'), 'claim': exact_report.get('claim'),
            'state_count': exact_report.get('closed_system', {}).get('state_count') if exact_report.get('closed_system') else None,
            'report': exact_report, 'report_sha256': analyzed['digest'],
            'replay': {'status': attestation.get('status'), 'attestation': attestation,
                       'sha256': replayed['digest']} if replayed else None,
        }
        artifacts.append(_artifact('exact all-finite-horizon trace-law report', analyzed['digest'], 'analysis'))
        if replayed:
            artifacts.append(_artifact('independent exact trace-law replay', replayed['digest'], 'replay'))

    return {
        'name': name,
        'graph': {'path': graph_relative, 'sha256': _sha(raw_graph), 'text': raw_graph.decode('utf-8')},
        'kernel': {'path': kernel_relative, 'sha256': _sha(raw_kernel), 'text': raw_kernel.decode('utf-8')},
        'horizon': horizon,
        'observers': report_rows,
        'bisimulation': bisimulation,
        'trace_equivalence': trace_equivalence,
        'artifacts': artifacts,
        'limits': {
            'horizon_max': MAX_HORIZON,
            'channel_states': MAX_CHANNEL_STATES,
            'channel_work_bytes': MAX_CHANNEL_WORK,
            'bisimulation_states': MAX_BISIM_STATES,
            'bisimulation_transitions': MAX_BISIM_TRANSITIONS,
            'trace_matrix_entries': 1_000_000,
        },
    }


def _channel_fixture(fixture_id: str, options: dict[str, Any]) -> dict[str, Any]:
    meta = FIXTURES[fixture_id]
    source_raw = _fixed_path(meta['path']).read_bytes()
    response = _base_result(fixture_id, source_raw)
    response['source']['text'] = source_raw.decode('utf-8')
    analysis = _channel_analysis(Path(meta['path']).stem.replace('.graph', ''), options.get('horizon', meta['default']['horizon']))
    response['analysis'] = analysis
    response['artifacts'].extend(analysis['artifacts'])
    response['security_result'] = _channel_message(fixture_id, analysis)
    response['assumptions'] += [
        'The finite channel uses the fixture’s exact rational success-only kernel and uniform prior over two fixed secret assignments.',
        'The all-horizon checker is sufficient but incomplete: a root split means inconclusive, not a counterexample.',
        'Exact trace equivalence compares stopped and live ordered-word masses for the supplied finite model; an unequal result has a finite independently replayed witness.',
        'All reported probabilities concern the supplied offline model, not a provider distribution.',
    ]
    return response


def _channel_message(fixture_id: str, analysis: dict[str, Any]) -> str:
    aggregate = analysis['observers']['aggregate']['metrics']
    trace = analysis['observers']['trace']['metrics']
    tv_agg = aggregate['pairwise'][0]['total_variation'] if aggregate else 'n/a'
    tv_trace = trace['pairwise'][0]['total_variation'] if trace else 'n/a'
    bisim = analysis['bisimulation']['status']
    if fixture_id == 'bisim-gap':
        exact = analysis['trace_equivalence']['status']
        return f'Ordered-trace TV={tv_trace}; bisimulation={bisim}; exact all-finite-horizon trace equivalence={exact}.'
    if fixture_id == 'aggregate-order':
        return f'Aggregate TV={tv_agg}; ordered-trace TV={tv_trace}. The aggregate observer loses call order.'
    if fixture_id == 'noisy-bit':
        return f'Exact ordered-trace TV={tv_trace}; bisimulation status={bisim} (a split is inconclusive).'
    return f'Exact ordered-trace TV={tv_trace}; the supplied alternatives have equal expected output usage but different laws.'


def _source_case_evaluate() -> dict[str, Any]:
    """Freshly check source contracts and a saved, actual-source race witness.

    This does not execute LangGraph. The source execution is recorded; both
    independent verifiers run now. The temporary Git checkout comes only from
    the fixed local bundle, whose digest is bound in the reproduction record.
    """
    fixture_id = 'source-case'
    meta = FIXTURES[fixture_id]
    response = _base_result(fixture_id, _fixed_path(meta['path']).read_bytes())
    relative = 'integrations/incident_triage/'
    analysis_path = _fixed_path(relative + 'source_analysis/artifacts/source_analysis.json')
    study_path = _fixed_path(relative + 'results/source_study.json')
    witness_path = _fixed_path(relative + 'concurrency/results/concurrency_study.json')
    path_study_path = _fixed_path(relative + 'protocol_paths/results/protocol_paths.json')
    bundle_path = _fixed_path(relative + 'upstream_c08f710.bundle')
    reproduction = _decode_json(
        _fixed_path(relative + 'concurrency/results/root_reproduction.json').read_bytes(),
        'source witness reproduction record',
    )
    if _sha(bundle_path.read_bytes()) != reproduction.get('bundle_sha256'):
        raise DemoError('fixed upstream bundle digest differs from its reproduction record')

    with tempfile.TemporaryDirectory(prefix='orchlang-demo-protocol-') as temp:
        attestation_path = Path(temp) / 'fresh_attestation.json'
        protocol = _command([
            sys.executable,
            str(_fixed_path(relative + 'source_analysis/replay_projection.py')),
            str(analysis_path),
            str(ROOT / relative / 'upstream_snapshot'),
            '--study', str(study_path), '--attestation', str(attestation_path),
        ])
        if protocol['returncode'] != 0 or not attestation_path.is_file():
            raise DemoError('independent source-protocol replay did not verify')
        protocol_attestation = _decode_json(
            attestation_path.read_bytes(), 'independent source-protocol replay',
        )
    expected_checks = [
        'pinned upstream selected file bytes and source manifest identity',
        'independent AST re-extraction of request, helper, schema, control, cost and gate dependencies',
        'serialized theorem claim, classifier-only lowering scope, and exclusions',
        'typed summary, repair, exact source estimator/budget, draft, and human gate obligations',
        '22 finite source runs and 11 exact-redaction pair projections',
        'authored raw-text classifier, repair, and draft mutations rejected',
        'independent replay of the source-bound classifier OrchGraph certificate',
    ]
    expected_scope = ('conditional source-specific pre-dispatch request/usage/route dependency argument; '
                      'not generic source translation or a mechanized proof of Python semantics')
    if (protocol['returncode'] != 0 or protocol_attestation.get('status') != 'verified'
            or protocol_attestation.get('checks') != expected_checks
            or protocol_attestation.get('claim_kind') !=
               'independent pinned-source AST contract re-extraction plus classifier graph certificate replay'
            or protocol_attestation.get('attestation_scope') != expected_scope
            or protocol_attestation.get('report_sha256') != _sha(analysis_path.read_bytes())
            or protocol_attestation.get('source_study_sha256') != _sha(study_path.read_bytes())
            or protocol_attestation.get('source', {}).get('commit') !=
               'c08f710acfeefe233329df613fe8358eaac5f350'
            or protocol_attestation.get('graph', {}).get('graph_replay_status') != 'verified'):
        raise DemoError('independent source-protocol replay did not verify')

    with tempfile.TemporaryDirectory(prefix='orchlang-demo-upstream-') as temp:
        checkout = Path(temp) / 'source'
        cloned = _command(['git', 'clone', '--quiet', '--no-checkout', str(bundle_path), str(checkout)])
        if cloned['returncode'] != 0:
            raise DemoError('could not reconstruct the fixed local upstream checkout')
        checked_out = _command([
            'git', '-C', str(checkout), 'checkout', '--quiet', '--detach',
            'c08f710acfeefe233329df613fe8358eaac5f350',
        ])
        if checked_out['returncode'] != 0:
            raise DemoError('the fixed upstream revision is unavailable in the local bundle')
        replay = _command([
            sys.executable,
            str(_fixed_path(relative + 'concurrency/verify_concurrency_study.py')),
            str(witness_path), '--upstream', str(checkout),
        ])
        path_attestation_path = Path(temp) / 'paths.attestation.json'
        paths_replay = _command([
            sys.executable,
            str(_fixed_path(relative + 'protocol_paths/verify_protocol_paths.py')),
            str(path_study_path), str(checkout), '--attestation', str(path_attestation_path),
        ])
        if paths_replay['returncode'] != 0 or not path_attestation_path.is_file():
            raise DemoError('independent recorded source-path replay did not verify')
        path_attestation = _decode_json(
            path_attestation_path.read_bytes(), 'independent recorded source-path replay',
        )
    witness_attestation = _decode_json(replay['stdout'], 'independent concurrency witness replay')
    if replay['returncode'] != 0 or witness_attestation.get('status') != 'verified':
        raise DemoError('independent recorded concurrency witness replay did not verify')
    if (path_attestation.get('status') != 'verified'
            or path_attestation.get('report_sha256') != _sha(path_study_path.read_bytes())
            or path_attestation.get('source_commit') != 'c08f710acfeefe233329df613fe8358eaac5f350'
            or path_attestation.get('claim_kind') !=
               'independent fixed-fixture reconstruction of selected unchanged-source paths'
            or path_attestation.get('path_count') != 6 or path_attestation.get('pair_count') != 6
            or path_attestation.get('run_count') != 12 or path_attestation.get('call_count') != 24
            or len(path_attestation.get('checks', [])) != 9):
        raise DemoError('independent recorded source-path replay did not verify')

    analysis = _decode_json(analysis_path.read_bytes(), 'source analysis')
    study = _decode_json(study_path.read_bytes(), 'recorded source study')
    witness = _decode_json(witness_path.read_bytes(), 'recorded concurrency study')
    path_study = _decode_json(path_study_path.read_bytes(), 'recorded source path study')
    response['source_case'] = {
        'source_commit': 'c08f710acfeefe233329df613fe8358eaac5f350',
        'protocol_replay': protocol_attestation,
        'concurrency_replay': witness_attestation,
        'paths_replay': path_attestation,
        'path_specs': path_study['path_specs'],
        'conditional_claim': analysis.get('claim'),
        'dependency_protocol': analysis.get('source_ast_contract', {}).get('dependency_protocol'),
        'mutations': analysis.get('authored_mutation_probes', []),
        'projection': analysis.get('source_study_projection', {}),
        'recorded_source_run_count': len(study.get('runs', [])),
        'shared_rows': witness['shared_graph']['runs'],
        'isolated_rows': witness['isolated_per_invocation_graphs']['runs'],
        'approvals': witness['isolated_per_invocation_graphs']['approvals'],
        'execution_notice': 'The original LangGraph executions are recorded. This button freshly runs independent source/profile and witness checks; it does not rerun LangGraph.',
    }
    response['request_plan'] = [
        {'scenario': 'classify', 'template': 'exact CLASSIFY_SYSTEM',
         'argument': 'INCIDENT REPORT: + exact redact_pii(text)'},
        {'scenario': 'repair', 'template': 'source validation/repair helper',
         'argument': 'same request + same schema error under the shared outcome premise'},
        {'scenario': 'draft', 'template': 'exact ACTIONS_SYSTEM',
         'argument': 'classification category + priority level + complete summary'},
    ]
    for label, path, kind in [
        ('source dependency report', analysis_path, 'analysis'),
        ('recorded direct source executions', study_path, 'recorded execution'),
        ('recorded concurrent source execution', witness_path, 'recorded execution'),
        ('recorded source path executions', path_study_path, 'recorded execution'),
        ('pinned upstream Git bundle', bundle_path, 'source'),
    ]:
        response['artifacts'].append(_artifact(label, _sha(path.read_bytes()), kind))
    response['artifacts'] += [
        _artifact('source-protocol replayer executable', _tool_sha(relative + 'source_analysis/replay_projection.py'), 'tool'),
        _artifact('concurrency witness verifier executable', _tool_sha(relative + 'concurrency/verify_concurrency_study.py'), 'tool'),
        _artifact('source-path verifier executable', _tool_sha(relative + 'protocol_paths/verify_protocol_paths.py'), 'tool'),
        _artifact('fresh independent source-protocol replay', protocol['digest'], 'replay'),
        _artifact('fresh independent concurrency witness replay', replay['digest'], 'replay'),
        _artifact('fresh independent source-path replay', paths_replay['digest'], 'replay'),
    ]
    response['assumptions'] = [
        'The source-specific claim requires equal valid metadata and exact redacted text, fixed configuration, fresh isolated apps, and a shared complete-outcome oracle.',
        'The protocol is an exact-source recognizer with inspected helper contracts; it is not a general Python translator.',
        'Only the first classifier request slice is exported to the existing OrchGraph checker. The full protocol has a separate source-specific independent checker.',
        'The race is one controlled schedule on unchanged upstream source. Its mitigation is a tested isolated-app control, not a proof of every concurrent schedule.',
        'Usage uses the source character-count estimate. Mock prices are zero; no provider charge or budget violation is measured.',
        'Six authored paired source paths use fixed outcomes. The oversized-response budget probe uses nominal prices only; no invoice or realistic provider likelihood is inferred.',
        'Original incident text remains in state/checkpoints. That storage privacy is outside the selected observation.',
        'The local Git clone reads a bundled source archive and makes no external network request.',
    ]
    response['security_result'] = 'Conditional source protocol and recorded shared-meter witness independently verified; isolated source apps restore their own rows.'
    response['live_notice'] = 'Fresh independent replay over recorded source executions. No LangGraph execution, provider call, or external network request occurs in this button.'
    return response


def evaluate(fixture_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if fixture_id not in FIXTURES:
        raise DemoError('unknown fixed fixture identifier')
    payload = payload or {}
    if not isinstance(payload, dict):
        raise DemoError('request body must be a JSON object')
    meta = FIXTURES[fixture_id]
    allowed = {
        'budget-leak': {'xLength', 'yLength'},
        'balanced-chain': {'sourceLength', 'horizon'},
        'productive-cycle': {'query', 'horizon'},
        'aggregate-order': {'horizon'},
        'noisy-bit': {'horizon'},
        'same-mean': {'horizon'},
        'bisim-gap': {'horizon'},
        'source-case': set(),
    }[fixture_id]
    if set(payload) - allowed:
        raise DemoError('request contains unknown controls')
    if fixture_id == 'source-case':
        return _source_case_evaluate()
    if fixture_id == 'budget-leak':
        for field in ('xLength', 'yLength'):
            value = payload.get(field, meta['default'][field])
            if type(value) is not int or not 1 <= value <= 100:
                raise DemoError(f'{field} must be an integer from 1 to 100')
        return _source_evaluate(fixture_id, payload)
    if fixture_id == 'balanced-chain':
        value = payload.get('sourceLength', meta['default']['sourceLength'])
        if type(value) is not int or not 0 <= value <= 32:
            raise DemoError('sourceLength must be an integer from 0 to 32')
        if 'horizon' in payload:
            _validate_horizon(payload['horizon'])
        return _source_evaluate(fixture_id, payload)
    if fixture_id == 'productive-cycle':
        horizon = payload.get('horizon', meta['default']['horizon'])
        _validate_horizon(horizon)
        return _graph_evaluate(fixture_id, {**payload, 'horizon': horizon})
    horizon = payload.get('horizon', meta['default']['horizon'])
    _validate_horizon(horizon)
    return _channel_fixture(fixture_id, {**payload, 'horizon': horizon})


def _validate_horizon(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= MAX_HORIZON:
        raise DemoError('horizon must be an integer from 1 to 8')
    return value


def build_offline_evidence() -> dict[str, Any]:
    """Create the recorded fallback bundle from the current local tools."""
    results = {}
    for fixture_id, meta in FIXTURES.items():
        results[fixture_id] = evaluate(fixture_id, dict(meta['default']))
        results[fixture_id]['execution'] = 'static evidence snapshot'
        results[fixture_id]['generated_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        results[fixture_id]['offline_provenance'] = {
            'compiler_sha256': results[fixture_id].get('compiler_sha256'),
            'compiler_source': 'repository-local orchc binary; offline mock only',
            'network_calls': 0,
            'model_provider_calls': 0,
            'source_sha256': results[fixture_id]['source']['sha256'],
            'report_digests': [item for item in results[fixture_id]['artifacts'] if item['kind'] in ('analysis', 'certificate', 'replay', 'compiler', 'run')],
        }
        if fixture_id == 'source-case':
            results[fixture_id]['offline_provenance']['compiler_source'] = 'This fixture runs independent source/profile, concurrency and path replayers; it does not execute orchc or LangGraph.'
    return {
        'format': 'orchlang-demo-offline-evidence',
        'version': 1,
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'provenance': {
            'method': 'Generated by demo/server.py from fixed local fixtures and offline repository tools.',
            'network_calls': 0,
            'provider_calls': 0,
            'compiler_sha256': _sha(COMPILER.read_bytes()),
            'tools': {
                'orchgraph.py': _tool_sha('audit/orchgraph.py'),
                'replay_graph_certificate.py': _tool_sha('audit/replay_graph_certificate.py'),
                'probabilistic_channels.py': _tool_sha('audit/probabilistic_channels.py'),
                'replay_probabilistic_report.py': _tool_sha('audit/replay_probabilistic_report.py'),
                'stochastic_bisimulation.py': _tool_sha('audit/stochastic_bisimulation.py'),
                'replay_stochastic_certificate.py': _tool_sha('audit/replay_stochastic_certificate.py'),
                'trace_equivalence.py': _tool_sha('audit/trace_equivalence.py'),
                'replay_trace_equivalence.py': _tool_sha('audit/replay_trace_equivalence.py'),
                'certificate_audit.py': _tool_sha('audit/certificate_audit.py'),
            },
            'scope': 'Recorded fixture runs and reports. The standalone file does not invoke or identify a current compiler run.',
        },
        'fixtures': results,
    }


def write_offline_evidence() -> None:
    evidence = build_offline_evidence()
    encoded = json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    evidence_path = DEMO / 'offline_evidence.json'
    evidence_path.write_text(encoded, encoding='utf-8')
    html_path = DEMO / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    opening = '  <script id="offline-evidence" type="application/json">\n'
    closing = '\n  </script>'
    if html.count(opening) != 1:
        raise DemoError('offline evidence HTML marker is missing or ambiguous')
    start = html.index(opening) + len(opening)
    end = html.find(closing, start)
    if end < 0:
        raise DemoError('offline evidence HTML marker is incomplete')
    inline = json.dumps(evidence, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    inline = inline.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html_path.write_text(html[:start] + inline + html[end:], encoding='utf-8')


class DemoHandler(BaseHTTPRequestHandler):
    server_version = 'OrchLangLocalDemo/1.0'
    sys_version = ''

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write('[demo] ' + (fmt % args) + '\n')

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        if len(body) > MAX_HTTP_RESPONSE_BYTES:
            status = 500
            body = b'{"error":"response exceeds the demo size limit"}'
            content_type = 'application/json; charset=utf-8'
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self._send(status, body, 'application/json; charset=utf-8')

    def _host_allowed(self) -> bool:
        host = self.headers.get('Host', '').split(':', 1)[0].lower()
        if host not in ('127.0.0.1', 'localhost'):
            return False
        origin = self.headers.get('Origin')
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._json(403, {'error': 'localhost origin required'})
            return
        path = urlsplit(self.path).path
        if path in ('/', '/index.html'):
            target, content_type = DEMO / 'index.html', 'text/html; charset=utf-8'
        elif path == '/README.md':
            target, content_type = DEMO / 'README.md', 'text/markdown; charset=utf-8'
        elif path == '/api/fixtures':
            self._json(200, {'fixtures': [
                {key: value for key, value in meta.items() if key in ('title', 'eyebrow', 'kind', 'description')}
                | {'id': fixture_id}
                for fixture_id, meta in FIXTURES.items()
            ], 'limits': {'request_bytes': MAX_BODY_BYTES, 'horizon': MAX_HORIZON,
                          'subprocess_seconds': CHILD_TIMEOUT_SECONDS}})
            return
        else:
            self._json(404, {'error': 'not found'})
            return
        try:
            data = target.read_bytes()
        except OSError:
            self._json(404, {'error': 'demo file not found'})
            return
        self._send(200, data, content_type)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._json(403, {'error': 'localhost origin required'})
            return
        if urlsplit(self.path).path != '/api/evaluate':
            self._json(404, {'error': 'not found'})
            return
        if self.headers.get_content_type() != 'application/json':
            self._json(415, {'error': 'application/json required'})
            return
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            self._json(400, {'error': 'valid Content-Length required'})
            return
        if not 0 <= length <= MAX_BODY_BYTES:
            self._json(413, {'error': 'request body exceeds 16 KiB'})
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode('utf-8'))
            if not isinstance(payload, dict) or set(payload) - {'fixture', 'options'}:
                raise DemoError('request must contain only fixture and options')
            fixture_id = payload.get('fixture')
            options = payload.get('options', {})
            result = evaluate(fixture_id, options)
            result['execution'] = 'live localhost run'
            result.setdefault('live_notice', 'Fresh report from the repository-local compiler/checkers. No provider or external network call was made.')
            self._json(200, result)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._json(400, {'error': 'invalid UTF-8 JSON request'})
        except DemoError as error:
            self._json(400, {'error': str(error)})
        except Exception as error:  # fail closed; detailed internals remain in local stderr
            self.log_error('demo evaluation failed: %s', error)
            self._json(500, {'error': 'fixed local analysis failed closed'})


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(port: int = 8765) -> DemoServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('port must be between 0 and 65535')
    return DemoServer(('127.0.0.1', port), DemoHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--refresh-evidence', action='store_true',
                        help='recompute and embed the standalone offline evidence snapshot')
    args = parser.parse_args(argv)
    try:
        if args.refresh_evidence:
            write_offline_evidence()
            print('Updated demo/index.html and demo/offline_evidence.json from local offline tools.')
            return 0
        server = make_server(args.port)
    except (ValueError, OSError, DemoError) as error:
        print('OrchLang demo could not start: ' + str(error), file=sys.stderr)
        return 1
    print(f'OrchLang demo listening at http://127.0.0.1:{server.server_port}/')
    print('Offline only: no provider calls or outbound network requests are made.')
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print('\nStopping local demo.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
