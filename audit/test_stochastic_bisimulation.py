#!/usr/bin/env python3
"""Regression tests for finite all-horizon stochastic bisimulation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchgraph import Graph  # noqa: E402
from probabilistic_channels import (  # noqa: E402
    bounded_document,
    canonical,
    producer_histogram,
)
from stochastic_bisimulation import (  # noqa: E402
    MAX_STATE_KEY_BYTES,
    ORDINAL_SATURATION,
    SemanticState,
    _canonical_size,
    _state_document_size,
    _state_key,
    analyze,
)


def graph_with(states, *, chars_per_token=1, inputs=None,
               models=None, registers=None, entry='choose'):
    graph = {
        'format': 'orchlang-request-graph',
        'version': 1,
        'name': 'finite_bisimulation',
        'chars_per_token': chars_per_token,
        'inputs': inputs or {'secret': {'type': 'boolean', 'label': 'secret'}},
        'models': models or {'m': {'provider': 'offline', 'model': 'finite', 'max_tokens': 4}},
        'registers': registers or {'r': {'model': 'm'}, 's': {'model': 'm'}},
        'entry': entry,
        'states': states,
    }
    return graph


def default_kernel(*, history_window=None, outcomes=None, rules=None):
    kernel = {
        'format': 'orchlang-finite-outcome-kernel',
        'version': 1,
        'defaults': {'m': outcomes or [
            {'response': 'x', 'output_tokens': 1, 'probability': '1'}]},
        'rules': rules or [],
    }
    if history_window is not None:
        kernel['history_window'] = history_window
    return kernel


def branch_states(left_calls, right_calls, *, left_next=None, right_next=None,
                  extra_states=None):
    states = {
        'choose': {
            'calls': [],
            'next': {'kind': 'secret', 'guard': {'value': 'secret'},
                     'then': 'left', 'else': 'right'},
        },
        'left': {'calls': left_calls, 'next': left_next or {'kind': 'stop'}},
        'right': {'calls': right_calls, 'next': right_next or {'kind': 'stop'}},
    }
    if extra_states:
        states.update(extra_states)
    return states


def call(template, result='r', arguments=None, model='m'):
    return {'model': model, 'template': template, 'arguments': arguments or [], 'result': result}


def scenarios():
    return [{'secret': False}, {'secret': True}]


def contract(graph_document):
    graph = Graph(bounded_document(graph_document))
    return next(iter(graph.models.values()))


def history_event(graph_document, template, response, *, ordinal=0,
                  arguments=None, input_tokens=None, output_tokens=1):
    model = contract(graph_document)
    arguments = arguments or []
    if input_tokens is None:
        input_tokens = len(template.encode('utf-8')) + sum(len(x.encode('utf-8')) for x in arguments)
    return {
        'contract': model,
        'ordinal': ordinal,
        'template': template,
        'arguments': arguments,
        'response': response,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
    }


def find_state(report, *, pc=None, values=None, history=None, ordinal=None):
    for state in report['closed_system']['states']:
        if pc is not None and state['pc'][0] != pc:
            continue
        if values is not None and any(state['values'].get(k) != v for k, v in values.items()):
            continue
        if history is not None and state['history'] != history:
            continue
        if ordinal is not None and not any(row['count'] == ordinal for row in state['ordinals']):
            continue
        return state
    raise AssertionError('matching semantic state was not found')


def edges_from(report, state_id):
    return [edge for edge in report['closed_system']['transitions'] if edge['from'] == state_id]


class StochasticBisimulationTests(unittest.TestCase):
    def test_preflight_json_size_matches_canonical_utf8_bytes(self):
        value = {
            'plain': ['text', True, False, None, 7, -13, 1.25],
            'escaped': '\x00\b\t\n\r\f"\\Ω雪',
            'object': {'β': 'value', 'a': [1, {'z': False}]},
            'tuple': (1, 'tuple-values serialize as arrays'),
        }
        encoded = canonical(value)
        self.assertEqual(_canonical_size(value, 10_000), len(encoded.encode('utf-8')))

        state = SemanticState(
            ('entry', 2),
            (('boolean', False), ('text', 'a\x00"Ω')),
            (7,),
            (canonical({'response': 'x\n', 'ordinal': 4}),),
        )
        identity = canonical({'model': 'finite', 'provider': 'offline'})
        state_key = _state_key(state, [identity])
        self.assertEqual(_state_document_size(state, [identity]), len(state_key.encode('utf-8')))

    def test_oversized_state_is_rejected_before_key_serialization(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        with patch('stochastic_bisimulation.MAX_STATE_KEY_BYTES', 64):
            report = analyze(graph, default_kernel(), {}, scenarios())
        self.assertEqual(report['status'], 'unknown')
        self.assertIn('semantic-state byte cap', report['reason'])
        self.assertIsNone(report['closed_system'])

    def test_oversized_api_document_returns_unknown_not_partial_proof(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        with patch('stochastic_bisimulation.MAX_SOURCE_BYTES', 64):
            report = analyze(graph, default_kernel(), {}, scenarios())
        self.assertEqual(report['status'], 'unknown')
        self.assertIn('document byte cap', report['reason'])
        self.assertIsNone(report['closed_system'])

    def test_request_content_can_differ_when_ordered_usage_laws_match(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        report = analyze(graph, default_kernel(), {}, scenarios())
        self.assertEqual(report['status'], 'proved_equal')
        self.assertEqual(report['partition_certificate']['initial_scenario_blocks'][0],
                         report['partition_certificate']['initial_scenario_blocks'][1])
        labels = [edge['label'] for edge in report['closed_system']['transitions']]
        self.assertEqual({label['input_tokens'] for label in labels}, {1})
        self.assertEqual({label['output_tokens'] for label in labels}, {1})
        self.assertEqual({label['contract']['model'] for label in labels}, {'finite'})

    def test_response_and_hidden_register_differences_can_be_quotiented(self):
        states = branch_states(
            [call('A')], [call('B')],
            left_next={'kind': 'goto', 'target': 'follow'},
            right_next={'kind': 'goto', 'target': 'follow'},
            extra_states={'follow': {
                'calls': [call('F', 's', [{'value': 'r'}])],
                'next': {'kind': 'stop'},
            }},
        )
        graph = graph_with(states)
        kernel = default_kernel(history_window=1, rules=[
            {'model': 'm', 'template': 'A', 'outcomes': [
                {'response': 'x', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'B', 'outcomes': [
                {'response': 'y', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'F', 'arguments': ['x'], 'outcomes': [
                {'response': 'u', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'F', 'arguments': ['y'], 'outcomes': [
                {'response': 'v', 'output_tokens': 1, 'probability': '1'}]},
        ])
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'proved_equal')
        follow_states = [s for s in report['closed_system']['states'] if s['pc'] == ['follow', 0]]
        self.assertEqual({s['values']['r'] for s in follow_states}, {'x', 'y'})
        self.assertEqual({s['history'][0]['template'] for s in follow_states}, {'A', 'B'})
        follow_edges = [edge for state in follow_states for edge in edges_from(report, state['id'])]
        self.assertEqual({edge['label']['input_tokens'] for edge in follow_edges}, {2})
        self.assertEqual({edge['label']['output_tokens'] for edge in follow_edges}, {1})
        self.assertEqual({edge['to'] and next(
            target['values'].get('s') for target in report['closed_system']['states']
            if target['id'] == edge['to']) for edge in follow_edges}, {'u', 'v'})

    def test_noisy_bit_is_inconclusive_not_reported_as_leak_witness(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        kernel = default_kernel(rules=[
            {'model': 'm', 'template': 'A', 'outcomes': [
                {'response': 'x', 'output_tokens': 1, 'probability': '3/4'},
                {'response': 'xx', 'output_tokens': 2, 'probability': '1/4'}]},
            {'model': 'm', 'template': 'B', 'outcomes': [
                {'response': 'x', 'output_tokens': 1, 'probability': '1/4'},
                {'response': 'xx', 'output_tokens': 2, 'probability': '3/4'}]},
        ])
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'inconclusive')
        self.assertFalse(report['partition_certificate']['all_initial_scenarios_equivalent'])
        self.assertIn('different blocks are inconclusive', report['scope']['interpretation'])

    def test_ordered_trace_detects_permutation_hidden_by_aggregate(self):
        states = branch_states(
            [call('A', 'r')], [call('BBBB', 'r')],
            left_next={'kind': 'goto', 'target': 'left2'},
            right_next={'kind': 'goto', 'target': 'right2'},
            extra_states={
                'left2': {'calls': [call('BBBB', 's')], 'next': {'kind': 'stop'}},
                'right2': {'calls': [call('A', 's')], 'next': {'kind': 'stop'}},
            },
        )
        graph = graph_with(states)
        kernel = default_kernel()
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'inconclusive')
        left_hist = producer_histogram(graph, kernel, {'secret': True}, 2, observer='aggregate')
        right_hist = producer_histogram(graph, kernel, {'secret': False}, 2, observer='aggregate')
        self.assertEqual(left_hist['histogram'], right_hist['histogram'])

    def test_productive_cycle_closes_without_a_horizon_bound(self):
        states = {
            'choose': {'calls': [], 'next': {'kind': 'secret', 'guard': {'value': 'secret'},
                                               'then': 'left', 'else': 'right'}},
            'left': {'calls': [call('A')], 'next': {'kind': 'goto', 'target': 'left'}},
            'right': {'calls': [call('B')], 'next': {'kind': 'goto', 'target': 'right'}},
        }
        graph = graph_with(states)
        report = analyze(graph, default_kernel(), {}, scenarios())
        self.assertEqual(report['status'], 'proved_equal')
        self.assertLess(report['closed_system']['state_count'], 100)
        self.assertTrue(report['partition_certificate']['stable'])
        self.assertLess(report['partition_certificate']['refinement_rounds'], 100)

    def test_complete_history_selects_distinct_kernel_rules_and_usage_labels(self):
        states = branch_states(
            [call('A')], [call('B')],
            left_next={'kind': 'goto', 'target': 'follow'},
            right_next={'kind': 'goto', 'target': 'follow'},
            extra_states={'follow': {
                'calls': [call('F', 's', [{'value': 'r'}])],
                'next': {'kind': 'stop'},
            }},
        )
        graph = graph_with(states)
        event_a = history_event(graph, 'A', 'x')
        event_b = history_event(graph, 'B', 'y')
        kernel = default_kernel(history_window=1, rules=[
            {'model': 'm', 'template': 'A', 'outcomes': [
                {'response': 'x', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'B', 'outcomes': [
                {'response': 'y', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'F', 'arguments': ['x'], 'history': [event_a], 'outcomes': [
                {'response': 'u', 'output_tokens': 1, 'probability': '1'}]},
            {'model': 'm', 'template': 'F', 'arguments': ['y'], 'history': [event_b], 'outcomes': [
                {'response': 'v', 'output_tokens': 2, 'probability': '1'}]},
        ])
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'inconclusive')
        follow_states = [s for s in report['closed_system']['states'] if s['pc'] == ['follow', 0]]
        self.assertEqual({s['history'][0]['template'] for s in follow_states}, {'A', 'B'})
        usages = {
            next(iter(edges_from(report, state['id'])))['label']['output_tokens']
            for state in follow_states
        }
        self.assertEqual(usages, {1, 2})

    def test_stop_and_call_states_are_in_distinct_initial_partitions(self):
        states = branch_states(
            [], [call('A')],
            left_next={'kind': 'stop'}, right_next={'kind': 'stop'},
        )
        report = analyze(graph_with(states), default_kernel(), {}, scenarios())
        self.assertEqual(report['status'], 'inconclusive')
        start_states = report['closed_system']['initial_state_ids']
        state_by_id = {s['id']: s for s in report['closed_system']['states']}
        self.assertEqual({state_by_id[sid]['kind'] for sid in start_states}, {'call', 'stop'})
        self.assertEqual({edge['label']['kind'] for edge in report['closed_system']['transitions']}, {'call'})

    def test_ordinal_and_history_saturation_closes_a_loop_after_32(self):
        states = {
            'choose': {'calls': [], 'next': {'kind': 'secret', 'guard': {'value': 'secret'},
                                               'then': 'left', 'else': 'right'}},
            'left': {'calls': [call('A')], 'next': {'kind': 'goto', 'target': 'left'}},
            'right': {'calls': [call('B')], 'next': {'kind': 'goto', 'target': 'right'}},
        }
        graph = graph_with(states)
        kernel = default_kernel(history_window=1, rules=[
            {'model': 'm', 'ordinal': 32, 'outcomes': [
                {'response': 'xx', 'output_tokens': 2, 'probability': '1'}]},
        ])
        report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'proved_equal')
        all_counts = {row['count'] for state in report['closed_system']['states'] for row in state['ordinals']}
        self.assertIn(32, all_counts)
        self.assertIn(ORDINAL_SATURATION, all_counts)
        all_history_ordinals = {
            event['ordinal'] for state in report['closed_system']['states'] for event in state['history']
        }
        self.assertIn(ORDINAL_SATURATION, all_history_ordinals)
        self.assertLess(report['closed_system']['state_count'], 100)

        horizon32_true = producer_histogram(graph, kernel, {'secret': True}, 32, observer='trace')
        horizon32_false = producer_histogram(graph, kernel, {'secret': False}, 32, observer='trace')
        self.assertEqual(horizon32_true['status'], 'complete')
        self.assertEqual(horizon32_true['histogram'], horizon32_false['histogram'])

    def test_history_literal_at_32_stops_matching_after_history_ordinal_saturates(self):
        states = {'loop': {'calls': [call('T')], 'next': {'kind': 'goto', 'target': 'loop'}}}
        graph = graph_with(states, entry='loop',
                           inputs={'secret': {'type': 'boolean', 'label': 'secret'}})
        event32 = history_event(graph, 'T', 'x', ordinal=32)
        kernel = default_kernel(history_window=1, rules=[
            {'model': 'm', 'history': [event32], 'outcomes': [
                {'response': 'xx', 'output_tokens': 2, 'probability': '1'}]},
        ])
        report = analyze(graph, kernel, {}, [{'secret': False}, {'secret': True}])
        self.assertEqual(report['status'], 'proved_equal')
        before = find_state(report, pc='loop', ordinal=33,
                            history=[event32])
        after_event33 = history_event(graph, 'T', 'xx', ordinal=33, output_tokens=2)
        after = find_state(report, pc='loop', ordinal=33,
                           history=[after_event33])
        before_usages = {edge['label']['output_tokens'] for edge in edges_from(report, before['id'])}
        after_usages = {edge['label']['output_tokens'] for edge in edges_from(report, after['id'])}
        self.assertEqual(before_usages, {2})
        self.assertEqual(after_usages, {1})

    def test_resource_caps_return_unknown_without_partial_certificate(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        kernel = default_kernel()
        state_limited = analyze(graph, kernel, {}, scenarios(), max_states=1)
        self.assertEqual(state_limited['status'], 'unknown')
        self.assertIsNone(state_limited['closed_system'])
        self.assertIsNone(state_limited['partition_certificate'])
        work_limited = analyze(graph, kernel, {}, scenarios(), max_work_bytes=1)
        self.assertEqual(work_limited['status'], 'unknown')
        self.assertIsNone(work_limited['closed_system'])

    def test_rational_precision_cap_returns_unknown(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        kernel = default_kernel(outcomes=[
            {'response': 'x', 'output_tokens': 1, 'probability': '1/2'},
            {'response': 'y', 'output_tokens': 1, 'probability': '1/2'},
        ])
        with patch('probabilistic_channels.MAX_RATIONAL_BITS', 1):
            report = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(report['status'], 'unknown')
        self.assertIn('precision cap', report['reason'])
        self.assertIsNone(report['closed_system'])

    def test_closed_certificate_is_deterministic_and_binds_all_semantic_inputs(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        kernel = default_kernel()
        first = analyze(graph, kernel, {}, scenarios())
        second = analyze(graph, kernel, {}, scenarios())
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'proved_equal')
        for field in ('graph_sha256', 'kernel_sha256', 'checker_sha256',
                      'public_store_sha256', 'secret_scenarios_sha256'):
            self.assertEqual(len(first['hashes'][field]), 64)
        self.assertEqual(first['closed_system']['state_count'], len(first['closed_system']['states']))
        self.assertEqual(first['closed_system']['transition_count'], len(first['closed_system']['transitions']))
        self.assertTrue(first['partition_certificate']['stable'])

    def test_invalid_scenario_and_empty_secret_space_are_rejected(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        with self.assertRaises(ValueError):
            analyze(graph, default_kernel(), {}, [{'secret': False}])
        with self.assertRaises(ValueError):
            analyze(graph, default_kernel(), {}, [{'secret': False}, {'other': True}])

    def test_cli_emits_closed_json_certificate(self):
        graph = graph_with(branch_states([call('A')], [call('B')]))
        kernel = default_kernel()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph_path = root / 'graph.json'
            kernel_path = root / 'kernel.json'
            output_path = root / 'certificate.json'
            graph_path.write_text(json.dumps(graph), encoding='utf-8')
            kernel_path.write_text(json.dumps(kernel), encoding='utf-8')
            command = [
                sys.executable, str(Path(__file__).with_name('stochastic_bisimulation.py')),
                str(graph_path), str(kernel_path), '--public-json', '{}',
                '--scenarios-json', '[{"secret":false},{"secret":true}]',
                '--report', str(output_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'proved_equal')
            self.assertEqual(json.loads(result.stdout), report)


if __name__ == '__main__':
    unittest.main()
