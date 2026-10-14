#!/usr/bin/env python3
"""Fresh tiny-policy oracle for the exact uncertain-distance artifact.

This test-only script does not call the subject module's parser, row lookup,
certificate verifier, Bellman recurrence, or experiment-test oracle when
constructing laws. It imports the subject certifier solely to compare its
claimed result and uses its output backpointers to recover a witness policy.
All generated contracts are synthetic; no workflow/source/provider is run.
"""

from __future__ import annotations

import copy
import itertools
import random
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUBJECT = HERE.parent / "exact_uncertain_distance"
sys.path.insert(0, str(SUBJECT))
import exact_uncertain_distance as subject  # noqa: E402

STOP = "__STOP__"
ALPHABET = ("A", "B", STOP)
SEED = 0xA70D14
CONTRACTS = 120


def compositions(total: int, width: int) -> list[tuple[int, ...]]:
    if width == 1:
        return [(total,)]
    return [
        (first,) + tail
        for first in range(total + 1)
        for tail in compositions(total - first, width - 1)
    ]


def distribution(alphabet: tuple[str, ...], rng: random.Random) -> dict[str, Fraction]:
    denominator = rng.randint(1, 5)
    parts = rng.choice(compositions(denominator, len(alphabet)))
    return {symbol: Fraction(value, denominator) for symbol, value in zip(alphabet, parts)}


def text_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def policy_options(
    alphabet: tuple[str, ...], horizon: int, rows: list[dict[str, Any]], scenario: str
) -> tuple[list[tuple[str, ...]], list[list[dict[str, Fraction]]]]:
    live_symbols = tuple(symbol for symbol in alphabet if symbol != STOP)
    histories = [
        history
        for depth in range(horizon)
        for history in itertools.product(live_symbols, repeat=depth)
    ]
    row_lookup = {(row["scenario"], tuple(row["history"])): row for row in rows}
    options = []
    for history in histories:
        row = row_lookup.get((scenario, history))
        if row is None:
            options.append(
                [
                    {symbol: Fraction(int(symbol == selected)) for symbol in alphabet}
                    for selected in alphabet
                ]
            )
        else:
            options.append(
                [
                    {symbol: Fraction(generator[symbol]) for symbol in alphabet}
                    for generator in row["generators"]
                ]
            )
    return histories, options


def evaluate_law(
    alphabet: tuple[str, ...],
    horizon: int,
    histories: list[tuple[str, ...]],
    selected_rows: dict[tuple[str, ...], dict[str, Fraction]],
) -> dict[tuple[str, ...], Fraction]:
    """Enumerate one selected deterministic vertex policy's padded law."""
    del histories  # It constrains policy construction; traversal follows the tree.
    law: dict[tuple[str, ...], Fraction] = {}

    def visit(history: tuple[str, ...], trace: tuple[str, ...], mass: Fraction) -> None:
        if len(trace) == horizon:
            law[trace] = law.get(trace, Fraction(0)) + mass
            return
        row = selected_rows[history]
        for symbol in alphabet:
            probability = row[symbol]
            if probability == 0:
                continue
            next_trace = trace + (symbol,)
            next_mass = mass * probability
            if symbol == STOP:
                padded = next_trace + (STOP,) * (horizon - len(next_trace))
                law[padded] = law.get(padded, Fraction(0)) + next_mass
            else:
                visit(history + (symbol,), next_trace, next_mass)

    visit((), (), Fraction(1))
    return law


def all_policy_laws(
    alphabet: tuple[str, ...], horizon: int, rows: list[dict[str, Any]], scenario: str
) -> tuple[list[dict[tuple[str, ...], Fraction]], list[tuple[str, ...]], list[list[dict[str, Fraction]]]]:
    histories, options = policy_options(alphabet, horizon, rows, scenario)
    laws = []
    for choices in itertools.product(*(range(len(values)) for values in options)):
        selected = {history: options[i][choice] for i, (history, choice) in enumerate(zip(histories, choices))}
        laws.append(evaluate_law(alphabet, horizon, histories, selected))
    return laws, histories, options


def total_variation(
    left: dict[tuple[str, ...], Fraction], right: dict[tuple[str, ...], Fraction]
) -> Fraction:
    return sum(
        (abs(left.get(trace, Fraction(0)) - right.get(trace, Fraction(0))) for trace in left.keys() | right.keys()),
        Fraction(0),
    ) / 2


def contract_for(rng: random.Random, index: int) -> dict[str, Any]:
    horizon = 1 if index % 5 == 0 else (2 if index % 3 else 3)
    alphabet = list(ALPHABET)
    rng.shuffle(alphabet)  # STOP need not be in the last coordinate.
    rows = []
    if horizon == 1:
        histories: list[tuple[str, ...]] = [()]
    elif horizon == 2:
        histories = [(), ("A",), ("B",)]
    else:
        histories = [
            (),
            ("A",),
            ("B",),
            ("A", "A"),
            ("A", "B"),
            ("B", "A"),
            ("B", "B"),
        ]

    for scenario in ("left", "right"):
        for history in histories:
            # Missing H=2 rows exercise full-simplex fallback.
            if horizon == 2 and history and rng.random() < 0.22:
                continue
            # All depth-(H-1) rows stop, keeping H=3 enumeration compact while
            # the earlier rows exercise multi-step, history-sensitive laws.
            if horizon == 3 and len(history) == 2:
                generators = [{symbol: Fraction(int(symbol == STOP)) for symbol in alphabet}]
            else:
                count = rng.randint(1, 3 if horizon == 1 else 2)
                generators = []
                while len(generators) < count:
                    candidate = distribution(tuple(alphabet), rng)
                    if candidate not in generators:
                        generators.append(candidate)
            rows.append(
                {
                    "scenario": scenario,
                    "history": list(history),
                    "generators": [
                        {symbol: text_fraction(generator[symbol]) for symbol in alphabet}
                        for generator in generators
                    ],
                }
            )

    return {
        "schema": subject.SCHEMA,
        "alphabet": alphabet,
        "horizon": horizon,
        "require_stop_by_horizon": horizon == 3,
        "rows": rows,
    }


def maximizing_policy_from_certificate(
    raw: dict[str, Any], certificate: dict[str, Any]
) -> tuple[dict[tuple[str, ...], dict[str, Fraction]], dict[tuple[str, ...], dict[str, Fraction]]]:
    """Follow selected local vertex pairs from the root to reconstruct a witness."""
    alphabet = tuple(raw["alphabet"])
    horizon = raw["horizon"]
    left_histories, left_options = policy_options(alphabet, horizon, raw["rows"], "left")
    right_histories, right_options = policy_options(alphabet, horizon, raw["rows"], "right")
    left_policy = {h: options[0] for h, options in zip(left_histories, left_options)}
    right_policy = {h: options[0] for h, options in zip(right_histories, right_options)}
    states = {
        (
            tuple(item["history"]),
            Fraction(item["left_mass"]),
            Fraction(item["right_mass"]),
        ): item
        for item in certificate["states"]
    }

    def follow(history: tuple[str, ...], left_mass: Fraction, right_mass: Fraction) -> None:
        record = states[(history, left_mass, right_mass)]
        if len(history) == horizon:
            return
        left_index, right_index = record["selected_pair"]
        left_row = left_options[left_histories.index(history)][left_index]
        right_row = right_options[right_histories.index(history)][right_index]
        left_policy[history] = left_row
        right_policy[history] = right_row
        for symbol in alphabet:
            if symbol == STOP:
                continue
            next_left = left_mass * left_row[symbol]
            next_right = right_mass * right_row[symbol]
            if next_left > 0 and next_right > 0:
                follow(history + (symbol,), next_left, next_right)

    follow((), Fraction(1), Fraction(1))
    return left_policy, right_policy


def main() -> None:
    rng = random.Random(SEED)
    compared_pairs = 0
    reconstructed_witnesses = 0
    for index in range(CONTRACTS):
        raw = contract_for(rng, index)
        alphabet = tuple(raw["alphabet"])
        horizon = raw["horizon"]
        certificate = subject.certify(raw)

        left_laws, _, _ = all_policy_laws(alphabet, horizon, raw["rows"], "left")
        right_laws, _, _ = all_policy_laws(alphabet, horizon, raw["rows"], "right")
        worst = max(total_variation(left, right) for left in left_laws for right in right_laws)
        compared_pairs += len(left_laws) * len(right_laws)
        if worst != Fraction(certificate["worst_case_tv"]):
            raise AssertionError(f"case {index}: certificate {certificate['worst_case_tv']} != direct {worst}")

        left_policy, right_policy = maximizing_policy_from_certificate(raw, certificate)
        left_witness = evaluate_law(alphabet, horizon, [], left_policy)
        right_witness = evaluate_law(alphabet, horizon, [], right_policy)
        witness_tv = total_variation(left_witness, right_witness)
        if witness_tv != worst:
            raise AssertionError(f"case {index}: selected generator backpointers realize {witness_tv}, expected {worst}")
        if subject.verify(raw, certificate)["worst_case_tv"] != certificate["worst_case_tv"]:
            raise AssertionError(f"case {index}: replay disagrees")
        reconstructed_witnesses += 1

    # Tamper beyond the existing root-value test: omit a reachable closure
    # state, add an unreachable mass state, and corrupt a Bellman argmin/value.
    attack = {
        "schema": subject.SCHEMA,
        "alphabet": ["A", "B", STOP],
        "horizon": 2,
        "require_stop_by_horizon": False,
        "rows": [],
    }
    cert = subject.certify(attack)
    mutations = [
        lambda value: value["states"].pop(),
        lambda value: value["states"].append(
            {"history": ["A"], "left_mass": "1/2", "right_mass": "1", "overlap": "0", "selected_pair": [0, 0]}
        ),
        lambda value: value["states"][0].update(selected_pair=[999, 0]),
        lambda value: value["states"][-1].update(overlap="0"),
    ]
    for attack_index, mutate in enumerate(mutations):
        tampered = copy.deepcopy(cert)
        mutate(tampered)
        try:
            subject.verify(attack, tampered)
        except subject.ContractError:
            continue
        raise AssertionError(f"certificate tamper case {attack_index} was accepted")

    print(
        f"fresh_contracts={CONTRACTS}; policy_pairs={compared_pairs}; "
        f"matching_witnesses={reconstructed_witnesses}; rejected_certificate_tampers={len(mutations)}"
    )


if __name__ == "__main__":
    main()
