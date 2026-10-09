#!/usr/bin/env python3
"""Finite exact probabilistic bisimulation for ordered usage traces.

This experimental checker analyzes a *declared finite rational kernel* over
the request-graph semantics in :mod:`probabilistic_channels`. For one fixed
public store and 2--64 explicit, distinct secret stores it constructs the
reachable finite semantic transition system, then computes the coarsest
strong probabilistic bisimulation that preserves the visible call label
``(resolved contract, input_tokens, output_tokens)`` and terminality.

If every scenario's initial state lands in the same final block, the checker
reports a sufficient proof that the scenarios have equal ordered,
success-only usage-trace laws at every finite call horizon. Distinct blocks
mean only ``inconclusive``: probabilistic bisimulation is sufficient for
trace-law equality, not complete for it, so a split is not reported as a leak
witness.

State identity is the normalized next-call/stop PC, every initialized
concrete value, one call ordinal per resolved contract saturated at 33, and
the retained complete-event history (with each event ordinal saturated at
33). Kernel ordinal/history literals are bounded by 32, so all counts at
least 33 have identical rule-matching behavior. The kernel is ordered,
first-match with contract defaults, and uses exact rational probabilities.
Calls are successful outcomes only. A stop state is terminal and belongs to
a partition disjoint from call states.

The model excludes cumulative billing, trace-byte, work, and termination
budgets. Input documents, individual values/requests, serialized semantic
state keys, control steps, reachable-state count, transition expansion,
deterministic byte-work, and rational precision are bounded. The JSON size
meter preflights serialization and is a deterministic work estimate, not an
RSS or CPU-time bound. Exceeding an analysis resource cap returns UNKNOWN
without a partial system or proof. No provider probability model is validated,
and no claim is made about real-provider billing or failures.

API:: ``analyze(graph_document, kernel_document, public_store,
secret_scenarios, max_states=10000, max_work_bytes=64*1024*1024)``. Each
scenario is a JSON object assigning exactly the declared secret inputs;
priors are unnecessary because this is pairwise channel-law checking.

CLI:: ``python3 audit/stochastic_bisimulation.py GRAPH KERNEL --public-json
'{}' --scenarios-json '[{"secret":false},{"secret":true}]'``.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probabilistic_channels import (  # noqa: E402
    ChannelError,
    ChannelLimit,
    Kernel,
    MAX_RATIONAL_BITS,
    MAX_SOURCE_BYTES,
    MAX_VALUE_BYTES,
    advance_control,
    bounded_document,
    bounded_mass,
    canonical,
    normalized_store,
)
from orchgraph import Graph, InvalidGraph, natural, strict_json, utf8  # noqa: E402


FORMAT = 'orchlang-stochastic-bisimulation-certificate'
VERSION = 1
DEFAULT_MAX_STATES = 10_000
MAX_STATES = 1_000_000
DEFAULT_MAX_WORK_BYTES = 64 * 1024 * 1024
MAX_WORK_BYTES = 1024 * 1024 * 1024
MAX_SCENARIOS = 64
MAX_TRANSITIONS = 1_000_000
ORDINAL_SATURATION = 33
MAX_STATE_KEY_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class SemanticState:
    """A complete finite-state key; ``pc`` is normalized to call or stop."""

    pc: tuple[str, int]
    values: tuple[tuple[str, str | bool], ...]
    ordinals: tuple[int, ...]
    history: tuple[str, ...]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utf8_size(value: str, limit: int | None = None) -> int:
    """Count UTF-8 bytes without allocating an encoded copy."""
    if limit is not None and len(value) > limit:
        raise ChannelLimit('semantic-state byte cap reached')
    total = 0
    for char in value:
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise ChannelError('text contains a non-scalar Unicode surrogate')
        total += 1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        if limit is not None and total > limit:
            raise ChannelLimit('semantic-state byte cap reached')
    return total


def _json_string_size(value: str, limit: int | None = None) -> int:
    """Exact UTF-8 size of json.dumps(value, ensure_ascii=False)."""
    if limit is not None and len(value) + 2 > limit:
        raise ChannelLimit('document byte cap reached')
    total = 2  # surrounding quotes
    short_escapes = {'"', '\\', '\b', '\f', '\n', '\r', '\t'}
    for char in value:
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise ChannelError('text contains a non-scalar Unicode surrogate')
        if char in short_escapes:
            total += 2
        elif codepoint < 0x20:
            total += 6
        else:
            total += 1 if codepoint <= 0x7F else 2 if codepoint <= 0x7FF else 3 if codepoint <= 0xFFFF else 4
        if limit is not None and total > limit:
            raise ChannelLimit('document byte cap reached')
    return total


def _canonical_size(value: Any, limit: int, depth: int = 0,
                    active: set[int] | None = None) -> int:
    """Measure canonical JSON before serialization, stopping above ``limit``."""
    if depth > 256:
        raise ChannelError('JSON nesting limit reached')
    if active is None:
        active = set()
    if value is None:
        return 4
    if type(value) is bool:
        return 4 if value else 5
    if isinstance(value, str):
        return _json_string_size(value, limit)
    if type(value) is int:
        bit_length = abs(value).bit_length()
        if limit < 0 or (bit_length and ((bit_length - 1) * 30102) // 100000 + 1 > limit):
            raise ChannelLimit('document byte cap reached')
        try:
            digits = len(str(value))
        except ValueError as error:
            raise ChannelLimit('JSON integer digit cap reached') from error
        if digits > limit:
            raise ChannelLimit('document byte cap reached')
        return digits
    if type(value) is float:
        try:
            return len(json.dumps(value, allow_nan=False))
        except (ValueError, OverflowError) as error:
            raise ChannelError('nonfinite JSON number') from error
    if isinstance(value, (dict, list, tuple)):
        identity = id(value)
        if identity in active:
            raise ChannelError('cyclic value is not JSON')
        active.add(identity)
        try:
            if isinstance(value, dict):
                if any(not isinstance(key, str) for key in value):
                    raise ChannelError('JSON keys must be strings')
                total = 2
                if total > limit:
                    raise ChannelLimit('document byte cap reached')
                for index, (key, child) in enumerate(value.items()):
                    total += 1 if index else 0
                    total += _json_string_size(key, limit - total) + 1
                    if total > limit:
                        raise ChannelLimit('document byte cap reached')
                    total += _canonical_size(child, limit - total, depth + 1, active)
                    if total > limit:
                        raise ChannelLimit('document byte cap reached')
            else:
                total = 2
                if total > limit:
                    raise ChannelLimit('document byte cap reached')
                for index, child in enumerate(value):
                    total += (1 if index else 0)
                    total += _canonical_size(child, limit - total, depth + 1, active)
                    if total > limit:
                        raise ChannelLimit('document byte cap reached')
            return total
        finally:
            active.remove(identity)
    raise ChannelError('non-JSON value')


def _bounded_json(value: Any) -> Any:
    """Copy/validate API JSON values under the shared source-document cap."""
    try:
        _canonical_size(value, MAX_SOURCE_BYTES)
        normalized = bounded_document(value)
    except ChannelLimit:
        raise
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        raise ChannelError(str(error)) from error
    return normalized


def _canonical_limited(value: Any, limit: int, reason: str) -> str:
    try:
        _canonical_size(value, limit)
    except ChannelLimit as error:
        raise ChannelLimit(reason) from error
    return canonical(value)


def _state_document(state: SemanticState, identities: list[str]) -> dict[str, Any]:
    return {
        'pc': [state.pc[0], state.pc[1]],
        'values': {key: value for key, value in state.values},
        'ordinals': [
            {'contract': json.loads(identity), 'count': count}
            for identity, count in zip(identities, state.ordinals)
        ],
        'history': [json.loads(item) for item in state.history],
    }


def _state_key(state: SemanticState, identities: list[str]) -> str:
    size = _state_document_size(state, identities)
    if size > MAX_STATE_KEY_BYTES:
        raise ChannelLimit('serialized semantic-state byte cap reached')
    return canonical(_state_document(state, identities))


def _state_document_size(state: SemanticState, identities: list[str]) -> int:
    # Preflight the canonical state document without constructing it. Strings
    # from values are escaped by JSON; history and contract identities already
    # contain canonical JSON objects and can be counted directly.
    def add(current: int, amount: int) -> int:
        result = current + amount
        if result > MAX_STATE_KEY_BYTES:
            raise ChannelLimit('serialized semantic-state byte cap reached')
        return result

    state_name, index = state.pc
    size = len(b'{"history":[') + len(b'],"ordinals":[')
    if size > MAX_STATE_KEY_BYTES:
        raise ChannelLimit('serialized semantic-state byte cap reached')
    for item in state.history:
        size = add(size, _utf8_size(item, MAX_STATE_KEY_BYTES - size))
    size = add(size, max(0, len(state.history) - 1))
    for position, (identity, count) in enumerate(zip(identities, state.ordinals)):
        if position:
            size = add(size, 1)
        size = add(size, len(b'{"contract":'))
        size = add(size, _utf8_size(identity, MAX_STATE_KEY_BYTES - size))
        size = add(size, len(b',"count":') + len(str(count)) + 1)
    size = add(size, len(b'],"pc":['))
    size = add(size, _json_string_size(state_name, MAX_STATE_KEY_BYTES - size))
    size = add(size, 1 + len(str(index)) + len(b'],"values":{'))
    for position, (key, value) in enumerate(state.values):
        if position:
            size = add(size, 1)
        size = add(size, _json_string_size(key, MAX_STATE_KEY_BYTES - size) + 1)
        if isinstance(value, str):
            size = add(size, _json_string_size(value, MAX_STATE_KEY_BYTES - size))
        elif type(value) is bool:
            size = add(size, 4 if value else 5)
        else:
            raise ChannelError('semantic state contains a non-text/non-Boolean value')
    size = add(size, 2)
    return size


class _Work:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def charge(self, value: Any, overhead: int = 64) -> None:
        remaining = self.limit - self.used - overhead
        if remaining < 0:
            raise ChannelLimit('cumulative byte-work cap reached')
        try:
            measured = _canonical_size(value, remaining)
        except ChannelLimit as error:
            raise ChannelLimit('cumulative byte-work cap reached') from error
        self.used += measured + overhead
        if self.used > self.limit:
            raise ChannelLimit('cumulative byte-work cap reached')

    def charge_units(self, units: int) -> None:
        # Deterministic accounting for control traversal: 16 work bytes per
        # normalized control step. This is a cap meter, not an RSS estimate.
        self.used += units * 16
        if self.used > self.limit:
            raise ChannelLimit('cumulative byte-work cap reached')


def _combine_edges(rows: dict[tuple[str, str], Fraction]) -> list[tuple[str, str, Fraction]]:
    return [
        (label, target, probability)
        for (label, target), probability in sorted(rows.items())
    ]


def _build_closed_system(graph_document, kernel_document, public_store,
                         secret_scenarios, max_states: int,
                         max_work_bytes: int) -> dict[str, Any]:
    graph_document = _bounded_json(graph_document)
    kernel_document = _bounded_json(kernel_document)
    public_store = _bounded_json(public_store)
    secret_scenarios = _bounded_json(secret_scenarios)

    graph = Graph(graph_document)
    kernel = Kernel(graph, kernel_document)
    natural(max_states, upper=MAX_STATES, minimum=1)
    natural(max_work_bytes, upper=MAX_WORK_BYTES, minimum=1)

    public_names = {name for name, declaration in graph.inputs.items()
                    if declaration['label'] == 'public'}
    secret_names = set(graph.inputs) - public_names
    if not isinstance(public_store, dict) or set(public_store) != public_names:
        raise ChannelError('public store must contain exactly public inputs')
    if not isinstance(secret_scenarios, list) or not 2 <= len(secret_scenarios) <= MAX_SCENARIOS:
        raise ChannelError('bisimulation needs 2..64 explicit secret scenarios')

    public_size = len(utf8(canonical(public_store)))
    scenario_size = len(utf8(canonical(secret_scenarios)))
    if public_size + scenario_size > MAX_SOURCE_BYTES:
        raise ChannelLimit('public store and scenario document byte cap reached')

    stores_seen: set[str] = set()
    stores: list[dict[str, str | bool]] = []
    for scenario in secret_scenarios:
        if not isinstance(scenario, dict) or set(scenario) != secret_names:
            raise ChannelError('each scenario must assign exactly the secret inputs')
        full_store = {**public_store, **scenario}
        normalized = normalized_store(graph, full_store)
        scenario_key = _canonical_limited(
            {key: normalized[key] for key in sorted(secret_names)},
            MAX_SOURCE_BYTES, 'scenario store byte cap reached')
        if scenario_key in stores_seen:
            raise ChannelError('duplicate secret scenario')
        stores_seen.add(scenario_key)
        stores.append(normalized)

    identities = sorted(kernel.contracts)
    contracts = {identity: kernel.contracts[identity] for identity in identities}
    contract_positions = {identity: index for index, identity in enumerate(identities)}
    work = _Work(max_work_bytes)
    states: dict[str, SemanticState] = {}
    queue: deque[str] = deque()
    initial_keys: list[str] = []
    edge_rows: dict[str, list[tuple[str, str, Fraction]]] = {}
    expanded = 0
    transition_count = 0

    def intern(state: SemanticState) -> str:
        key = _state_key(state, identities)
        if key not in states:
            if len(states) >= max_states:
                raise ChannelLimit('reachable semantic-state cap reached')
            work.charge({'state': key})
            states[key] = state
            queue.append(key)
        return key

    def normalize(pc, values, ordinals, history):
        frozen_values = tuple(sorted(values.items()))
        checked_pc, kind, _event, steps = advance_control(graph, pc, dict(frozen_values))
        if kind not in ('call', 'stop'):
            raise ChannelError('control normalization did not reach call or stop')
        work.charge_units(steps)
        return SemanticState(checked_pc, frozen_values, tuple(ordinals), tuple(history))

    for store in stores:
        initial = normalize((graph.entry, 0), store, [0] * len(identities), ())
        initial_keys.append(intern(initial))

    while queue:
        source_key = queue.popleft()
        state = states[source_key]
        values = dict(state.values)
        kind, event = graph.event(state.pc)
        if kind not in ('call', 'stop'):
            raise ChannelError('internal error: semantic state PC is not normalized')
        if kind == 'stop':
            edge_rows[source_key] = []
            expanded += 1
            work.charge({'stop_state': source_key})
            continue

        alias = event['model']
        contract = graph.models[alias]
        identity = _canonical_limited(contract, MAX_SOURCE_BYTES,
                                      'resolved contract byte cap reached')
        ordinal_index = contract_positions[identity]
        ordinal = state.ordinals[ordinal_index]
        if any('value' in atom and atom['value'] not in values
               for atom in event['arguments']):
            raise ChannelError('request reads an uninitialized register')
        arguments = [atom['literal'] if 'literal' in atom else values[atom['value']]
                     for atom in event['arguments']]
        if any(not isinstance(argument, str) for argument in arguments):
            raise ChannelError('request argument is not text')
        request_bytes = len(utf8(event['template'])) + sum(len(utf8(arg)) for arg in arguments)
        if request_bytes > MAX_VALUE_BYTES:
            raise ChannelLimit('request byte cap reached')
        input_tokens = graph.estimate(event['template']) + sum(graph.estimate(arg) for arg in arguments)
        input_bound = graph.estimate(event['template']) + sum(
            graph.argument_bound(atom) for atom in event['arguments'])
        if input_tokens > input_bound:
            raise ChannelError('concrete request violates declared accounting bounds')

        outcomes = kernel.outcomes(identity, ordinal, event['template'], arguments,
                                   state.history)
        merged: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
        for response, output_tokens, probability in outcomes:
            transition_count += 1
            if transition_count > MAX_TRANSITIONS:
                raise ChannelLimit('call-transition expansion cap reached')
            updated_values = dict(values)
            updated_values[event['result']] = response
            updated_ordinals = list(state.ordinals)
            updated_ordinals[ordinal_index] = min(ORDINAL_SATURATION, ordinal + 1)
            complete_event = {
                'contract': contract,
                'ordinal': ordinal,
                'template': event['template'],
                'arguments': arguments,
                'response': response,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            }
            if kernel.window:
                event_key = _canonical_limited(complete_event, MAX_STATE_KEY_BYTES,
                                               'complete event byte cap reached')
                next_history = (state.history + (event_key,))[-kernel.window:]
            else:
                next_history = ()
            target_state = normalize((state.pc[0], state.pc[1] + 1), updated_values,
                                     updated_ordinals, next_history)
            target_key = intern(target_state)
            label = _canonical_limited({
                'kind': 'call',
                'contract': contract,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            }, MAX_STATE_KEY_BYTES, 'usage label byte cap reached')
            pair = (label, target_key)
            merged[pair] = bounded_mass(merged[pair] + probability)
            work.charge({
                'source': source_key,
                'label': label,
                'target': target_key,
                'probability': str(probability),
            })
        if exact_sum(merged.values()) != 1:
            raise ChannelError('call transition probabilities do not sum exactly to one')
        edge_rows[source_key] = _combine_edges(merged)
        expanded += 1

    if set(edge_rows) != set(states):
        raise ChannelError('internal error: transition closure is incomplete')
    return {
        'graph_document': graph_document,
        'kernel_document': kernel_document,
        'public_store': public_store,
        'secret_scenarios': secret_scenarios,
        'graph': graph,
        'kernel': kernel,
        'identities': identities,
        'contracts': contracts,
        'states': states,
        'initial_keys': initial_keys,
        'edge_rows': edge_rows,
        'expanded_states': expanded,
        'transition_count': transition_count,
        'work': work,
    }


def exact_sum(values) -> Fraction:
    total = Fraction(0)
    for value in values:
        total = bounded_mass(total + value)
    return total


def _initial_colors(states: dict[str, SemanticState], graph, work: _Work) -> dict[str, int]:
    groups: dict[tuple[str], list[str]] = defaultdict(list)
    for key, state in states.items():
        kind, _event = graph.event(state.pc)
        groups[('terminal' if kind == 'stop' else 'call',)].append(key)
    sorted_groups = sorted(groups.values(), key=lambda group: min(group))
    result: dict[str, int] = {}
    for color, group in enumerate(sorted_groups):
        for key in group:
            result[key] = color
    work.charge({'initial_partition': [sorted(group) for group in sorted_groups]})
    return result


def _refine_partition(system: dict[str, Any]) -> dict[str, Any]:
    states = system['states']
    identities = system['identities']
    graph = system['graph']
    edge_rows = system['edge_rows']
    work = system['work']
    colors = _initial_colors(states, graph, work)
    rounds = 0

    while True:
        by_signature: dict[str, list[str]] = defaultdict(list)
        for key, state in states.items():
            kind, _event = graph.event(state.pc)
            if kind == 'stop':
                signature_value = ('terminal', colors[key], ())
            else:
                distribution: dict[tuple[str, int], Fraction] = defaultdict(Fraction)
                for label, target, probability in edge_rows[key]:
                    pair = (label, colors[target])
                    distribution[pair] = bounded_mass(distribution[pair] + probability)
                ordered = tuple(
                    (label, target_color, str(probability))
                    for (label, target_color), probability in sorted(distribution.items())
                )
                signature_value = ('call', colors[key], ordered)
            signature_key = _canonical_limited(signature_value, MAX_STATE_KEY_BYTES,
                                               'partition signature byte cap reached')
            by_signature[signature_key].append(key)
            work.charge({'state': key, 'signature': signature_value})

        ordered_groups = sorted(by_signature.values(), key=lambda group: min(group))
        new_colors = {key: color for color, group in enumerate(ordered_groups) for key in group}
        rounds += 1
        work.charge({'refinement_round': rounds, 'blocks': [sorted(group) for group in ordered_groups]})
        if len(set(new_colors.values())) == len(set(colors.values())):
            colors = new_colors
            break
        colors = new_colors
        if rounds > len(states) + 1:
            raise ChannelError('partition refinement exceeded finite-state split bound')

    groups: dict[int, list[str]] = defaultdict(list)
    for key, color in colors.items():
        groups[color].append(key)
    stable_groups = sorted(groups.values(), key=lambda group: min(group))
    block_for_key = {
        key: f'B{block_index:06d}'
        for block_index, group in enumerate(stable_groups)
        for key in group
    }
    blocks = []
    for block_index, group in enumerate(stable_groups):
        sample_key = min(group)
        sample_state = states[sample_key]
        kind, _event = graph.event(sample_state.pc)
        terminal = kind == 'stop'
        aggregate: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
        if not terminal:
            for label, target, probability in edge_rows[sample_key]:
                pair = (label, block_for_key[target])
                aggregate[pair] = bounded_mass(aggregate[pair] + probability)
        signature = [
            {
                'label': json.loads(label),
                'target_block': target_block,
                'probability': str(probability),
            }
            for (label, target_block), probability in sorted(aggregate.items())
        ]
        block_id = f'B{block_index:06d}'
        blocks.append({
            'id': block_id,
            'kind': 'stop' if terminal else 'call',
            'states': [None for _ in group],
            'signature': signature,
        })
    return {
        'colors': colors,
        'block_for_key': block_for_key,
        'blocks': blocks,
        'rounds': rounds,
    }


def _certificate(system: dict[str, Any], partition: dict[str, Any],
                 raw_graph: bytes | None = None, raw_kernel: bytes | None = None) -> dict[str, Any]:
    identities = system['identities']
    state_keys = sorted(system['states'])
    state_ids = {key: f'S{index:06d}' for index, key in enumerate(state_keys)}
    block_for_key = partition['block_for_key']
    graph_document = system['graph_document']
    kernel_document = system['kernel_document']
    public_store = system['public_store']
    scenarios = system['secret_scenarios']
    graph_source = utf8(canonical(graph_document))
    kernel_source = utf8(canonical(kernel_document))
    scenario_source = utf8(canonical(scenarios))
    public_source = utf8(canonical(public_store))

    states_out = []
    transitions_out = []
    for key in state_keys:
        state = system['states'][key]
        kind, _event = system['graph'].event(state.pc)
        states_out.append({
            'id': state_ids[key],
            **_state_document(state, identities),
            'kind': 'stop' if kind == 'stop' else 'call',
            'block': block_for_key[key],
        })
        for label, target, probability in system['edge_rows'][key]:
            transitions_out.append({
                'from': state_ids[key],
                'label': json.loads(label),
                'to': state_ids[target],
                'probability': str(probability),
            })
    for block in partition['blocks']:
        block['states'] = sorted(
            state_ids[key] for key in state_keys if block_for_key[key] == block['id'])

    initial_ids = [state_ids[key] for key in system['initial_keys']]
    initial_blocks = [block_for_key[key] for key in system['initial_keys']]
    status = 'proved_equal' if len(set(initial_blocks)) == 1 else 'inconclusive'
    return {
        'format': FORMAT,
        'version': VERSION,
        'status': status,
        'claim': 'equal ordered success-only usage-trace laws at every finite call horizon',
        'scope': {
            'oracle': 'declared finite rational conditional kernel; exact request, saturated contract ordinal, and retained complete-event history determine its distribution',
            'kernel_rule_precedence': 'first matching rule in supplied order, otherwise resolved-contract default',
            'observer': 'ordered call labels contain normalized resolved contract, integer input usage, and integer output usage; stop is a terminal state class',
            'semantics': 'successful model outcomes only; each response updates its result register and complete event history',
            'ordinal_saturation': ORDINAL_SATURATION,
            'history_window': system['kernel'].window,
            'history_ordinal_saturation': ORDINAL_SATURATION,
            'saturation_justification': 'kernel ordinal and complete-history event ordinal literals are at most 32; all values >=33 match the same rules',
            'excluded': [
                'provider probability validity or provider behavior',
                'errors, retries, currency, cumulative cost or cumulative trace/work budgets',
                'termination probability or infinite-run trace law',
            ],
            'interpretation': 'same final block is sufficient for every finite-horizon trace-law equality; different blocks are inconclusive, not a trace-law counterexample',
        },
        'hashes': {
            'graph_sha256': _sha(raw_graph if raw_graph is not None else graph_source),
            'kernel_sha256': _sha(raw_kernel if raw_kernel is not None else kernel_source),
            'checker_sha256': _sha(Path(__file__).read_bytes()),
            'public_store_sha256': _sha(public_source),
            'secret_scenarios_sha256': _sha(scenario_source),
        },
        'inputs': {
            'public_store': public_store,
            'secret_scenarios': scenarios,
        },
        'closed_system': {
            'state_count': len(states_out),
            'transition_count': len(transitions_out),
            'initial_state_ids': initial_ids,
            'states': states_out,
            'transitions': transitions_out,
        },
        'partition_certificate': {
            'stable': True,
            'refinement_rounds': partition['rounds'],
            'block_count': len(partition['blocks']),
            'initial_scenario_blocks': initial_blocks,
            'all_initial_scenarios_equivalent': status == 'proved_equal',
            'blocks': partition['blocks'],
        },
        'analysis_stats': {
            'expanded_states': system['expanded_states'],
            'call_outcome_transitions_before_merge': system['transition_count'],
            'byte_work_estimate': system['work'].used,
            'max_states': system['max_states'],
            'max_work_bytes': system['work'].limit,
            'max_state_key_bytes': MAX_STATE_KEY_BYTES,
            'rational_precision_limit_bits': MAX_RATIONAL_BITS,
        },
    }


def analyze(graph_document, kernel_document, public_store, secret_scenarios,
            max_states: int = DEFAULT_MAX_STATES,
            max_work_bytes: int = DEFAULT_MAX_WORK_BYTES) -> dict[str, Any]:
    """Build and refine a closed finite system, returning proof or UNKNOWN.

    ``secret_scenarios`` is a list of 2--64 distinct JSON objects, each mapping
    exactly the graph's secret input names to concrete Boolean/text values.
    ``public_store`` maps exactly the public input names. No prior distribution
    is used; all scenario starts are compared pairwise.
    """
    natural(max_states, upper=MAX_STATES, minimum=1)
    natural(max_work_bytes, upper=MAX_WORK_BYTES, minimum=1)
    raw_graph = raw_kernel = raw_public = raw_scenarios = None
    try:
        graph_document = _bounded_json(graph_document)
        kernel_document = _bounded_json(kernel_document)
        public_store = _bounded_json(public_store)
        secret_scenarios = _bounded_json(secret_scenarios)
        raw_graph = utf8(canonical(graph_document))
        raw_kernel = utf8(canonical(kernel_document))
        raw_public = utf8(canonical(public_store))
        raw_scenarios = utf8(canonical(secret_scenarios))
        system = _build_closed_system(graph_document, kernel_document,
                                      public_store, secret_scenarios,
                                      max_states, max_work_bytes)
        system['max_states'] = max_states
        partition = _refine_partition(system)
        return _certificate(system, partition, raw_graph, raw_kernel)
    except ChannelLimit as error:
        return {
            'format': FORMAT,
            'version': VERSION,
            'status': 'unknown',
            'reason': str(error),
            'claim': None,
            'hashes': {
                'checker_sha256': _sha(Path(__file__).read_bytes()),
                **({'graph_sha256': _sha(raw_graph)} if raw_graph is not None else {}),
                **({'kernel_sha256': _sha(raw_kernel)} if raw_kernel is not None else {}),
                **({'public_store_sha256': _sha(raw_public)} if raw_public is not None else {}),
                **({'secret_scenarios_sha256': _sha(raw_scenarios)}
                   if raw_scenarios is not None else {}),
            },
            'closed_system': None,
            'partition_certificate': None,
            'scope': 'no partial closure or partition is treated as proof',
        }


def _read_bounded(path: Path) -> bytes:
    with path.open('rb') as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ChannelLimit('input document byte cap reached: ' + str(path))
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--public-json', required=True,
                        help='JSON object assigning exactly the public inputs')
    parser.add_argument('--scenarios-json', required=True,
                        help='JSON array of 2..64 distinct secret input objects')
    parser.add_argument('--max-states', type=int, default=DEFAULT_MAX_STATES)
    parser.add_argument('--max-work-bytes', type=int, default=DEFAULT_MAX_WORK_BYTES)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        raw_graph = _read_bounded(args.graph)
        raw_kernel = _read_bounded(args.kernel)
        if len(utf8(args.public_json)) + len(utf8(args.scenarios_json)) > MAX_SOURCE_BYTES:
            raise ChannelLimit('input scenario byte cap reached')
        graph_document = strict_json(raw_graph)
        kernel_document = strict_json(raw_kernel)
        public_store = strict_json(args.public_json)
        scenarios = strict_json(args.scenarios_json)
        report = analyze(graph_document, kernel_document, public_store, scenarios,
                         args.max_states, args.max_work_bytes)
        report['hashes']['graph_sha256'] = _sha(raw_graph)
        report['hashes']['kernel_sha256'] = _sha(raw_kernel)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True,
                             indent=2, allow_nan=False) + '\n'
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(encoded, encoding='utf-8')
        print(encoded, end='')
        return 0 if report['status'] == 'proved_equal' else 2 if report['status'] == 'inconclusive' else 3
    except (ChannelError, InvalidGraph, OSError, ValueError, TypeError,
            KeyError, OverflowError, RecursionError) as error:
        print('stochastic bisimulation failed closed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
