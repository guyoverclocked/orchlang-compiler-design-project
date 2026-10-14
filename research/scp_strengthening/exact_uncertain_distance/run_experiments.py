#!/usr/bin/env python3
"""Reproduce the finite exact-distance fixtures and exhaustive tiny oracles."""

from __future__ import annotations

import json
import random
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exact_uncertain_distance as exact
import test_exact_uncertain_distance as reference


def _distribution(alphabet: tuple[str, ...], **values: object) -> dict[str, object]:
    return {symbol: values.get(symbol, 0) for symbol in alphabet}


def _contract(
    alphabet: list[str],
    horizon: int,
    rows: list[dict[str, object]],
    *,
    require_stop: bool = False,
) -> dict[str, object]:
    return {
        "schema": exact.SCHEMA,
        "alphabet": alphabet,
        "horizon": horizon,
        "require_stop_by_horizon": require_stop,
        "rows": rows,
    }


def _row(scenario: str, history: list[str], *generators: dict[str, object]) -> dict[str, object]:
    return {"scenario": scenario, "history": history, "generators": list(generators)}


def _case(name: str, raw: dict[str, object]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    result: dict[str, Any] = {"name": name}
    try:
        certificate = exact.certify(raw)
        replay = exact.verify(raw, certificate)
        exhaustive = reference._exhaustive_metrics(raw)
        claimed = Fraction(certificate["worst_case_tv"])
        oracle_tv = exhaustive["worst_tv"]
        if claimed != oracle_tv:
            failures.append({"case": name, "check": "exhaustive_tv", "detail": f"certificate={claimed}, oracle={oracle_tv}"})
        if not replay["verified"] or replay["worst_case_tv"] != certificate["worst_case_tv"]:
            failures.append({"case": name, "check": "certificate_replay", "detail": "replay result differs"})
        result.update(
            {
                "exact_overlap": certificate["overlap"],
                "exact_worst_case_tv": certificate["worst_case_tv"],
                "certificate_replay": {
                    "verified": replay["verified"],
                    "states": replay["states"],
                },
                "exhaustive_oracle": {
                    "left_policy_laws": exhaustive["left_policies"],
                    "right_policy_laws": exhaustive["right_policies"],
                    "compared_law_pairs": exhaustive["compared_pairs"],
                    "worst_case_tv": str(oracle_tv),
                },
            }
        )
    except Exception as exc:  # Keep experiment failures machine-readable.
        failures.append({"case": name, "check": "execution", "detail": f"{type(exc).__name__}: {exc}"})
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result, failures


def _compositions(total: int, width: int) -> list[tuple[int, ...]]:
    if width == 1:
        return [(total,)]
    values: list[tuple[int, ...]] = []
    for first in range(total + 1):
        values.extend((first,) + tail for tail in _compositions(total - first, width - 1))
    return values


def run() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    def add(name: str, raw: dict[str, object]) -> dict[str, Any]:
        result, case_failures = _case(name, raw)
        cases.append(result)
        failures.extend(case_failures)
        return result

    decisive_path = HERE / "examples" / "unequal_prefix_mass.json"
    decisive_raw = json.loads(decisive_path.read_text(encoding="utf-8"))
    decisive = add("unequal_prefix_mass_decisive", decisive_raw)
    try:
        old_bound = reference._pathwise_bound_for_degenerate_rows(decisive_raw)
        decisive["previous_pathwise_bound"] = str(old_bound)
        if decisive.get("exact_worst_case_tv") != "1/2" or old_bound != 1:
            failures.append({"case": "unequal_prefix_mass_decisive", "check": "strict_improvement", "detail": "expected exact=1/2 and old bound=1"})
    except Exception as exc:
        failures.append({"case": "unequal_prefix_mass_decisive", "check": "previous_bound", "detail": f"{type(exc).__name__}: {exc}"})

    symbols = ("A", "B", exact.STOP)
    delta_a = _distribution(symbols, A=1)
    delta_b = _distribution(symbols, B=1)
    base = _contract(
        list(symbols),
        1,
        [_row("left", [], delta_a), _row("right", [], delta_a)],
    )
    expanded = _contract(
        list(symbols),
        1,
        [_row("left", [], delta_a, delta_b), _row("right", [], delta_a)],
    )
    reordered = _contract(
        list(symbols),
        1,
        [_row("left", [], delta_b, delta_a), _row("right", [], delta_a)],
    )
    base_result = add("uncertainty_monotonicity_base", base)
    expanded_result = add("uncertainty_monotonicity_expanded", expanded)
    reordered_result = add("generator_order_permutation", reordered)
    if not (
        base_result.get("exact_worst_case_tv") == "0"
        and expanded_result.get("exact_worst_case_tv") == "1"
        and reordered_result.get("exact_worst_case_tv") == "1"
    ):
        failures.append({"case": "uncertainty_monotonicity", "check": "set_expansion_and_order", "detail": "expected values 0, 1, 1"})

    original_symbols = ("A", "B", "C", exact.STOP)
    original = _contract(
        list(original_symbols),
        1,
        [
            _row("left", [], _distribution(original_symbols, A=1)),
            _row("right", [], _distribution(original_symbols, B=1)),
        ],
    )
    projection = {"A": "X", "B": "X", "C": "C", exact.STOP: exact.STOP}
    projected_symbols = ("X", "C", exact.STOP)
    projected_rows = []
    for row in original["rows"]:
        source = row["generators"][0]
        target = {symbol: Fraction(0) for symbol in projected_symbols}
        for symbol, mass in source.items():
            target[projection[symbol]] += Fraction(mass)
        projected_rows.append(
            _row(
                row["scenario"],
                [],
                {symbol: exact._rational_text(mass) for symbol, mass in target.items()},
            )
        )
    projected = _contract(list(projected_symbols), 1, projected_rows)
    original_result = add("data_processing_before_projection", original)
    projected_result = add("data_processing_after_projection", projected)
    if not (
        original_result.get("exact_worst_case_tv") == "1"
        and projected_result.get("exact_worst_case_tv") == "0"
    ):
        failures.append({"case": "data_processing", "check": "projection_contracts_tv", "detail": "expected values 1 then 0"})

    global_theta_projection = _contract(
        list(symbols),
        1,
        [
            _row("left", [], delta_a, delta_b),
            _row("right", [], delta_a, delta_b),
        ],
    )
    global_projection_result = add("shared_parameter_rectangular_projection", global_theta_projection)
    rectangular_tv = global_projection_result.get("exact_worst_case_tv")
    if rectangular_tv != "1":
        failures.append({"case": "shared_parameter_rectangular_projection", "check": "expected_value", "detail": f"expected TV=1, got {rectangular_tv}"})

    linked = [
        ({("A",): Fraction(1)}, {("A",): Fraction(1)}),
        ({("B",): Fraction(1)}, {("B",): Fraction(1)}),
    ]
    linked_values = [reference._tv(left, right) for left, right in linked]
    linked_max = max(linked_values)
    shared_theta = {
        "paired_global_parameter_choices": len(linked),
        "compared_paired_laws": len(linked_values),
        "worst_case_tv": str(linked_max),
        "rectangular_projection_tv": rectangular_tv,
        "interpretation": "The independent row-product permits left=delta_A/right=delta_B; the tied global-parameter model does not.",
    }
    if linked_max != 0:
        failures.append({"case": "shared_global_parameter", "check": "paired_parameter", "detail": f"expected 0, got {linked_max}"})

    stop_symbols = ("ERROR", "RECOVERED", exact.STOP)
    stop_error = _contract(
        list(stop_symbols),
        3,
        [
            _row("left", [], _distribution(stop_symbols, ERROR=1)),
            _row("right", [], _distribution(stop_symbols, ERROR=1)),
            _row("left", ["ERROR"], _distribution(stop_symbols, RECOVERED=1)),
            _row("right", ["ERROR"], _distribution(stop_symbols, **{exact.STOP: 1})),
            _row("left", ["ERROR", "RECOVERED"], _distribution(stop_symbols, **{exact.STOP: 1})),
        ],
        require_stop=True,
    )
    stop_result = add("stop_padding_and_visible_error", stop_error)
    if stop_result.get("exact_worst_case_tv") != "1":
        failures.append({"case": "stop_padding_and_visible_error", "check": "expected_value", "detail": "expected TV=1"})

    seed = 20261014
    rng = random.Random(seed)
    random_symbols = ("A", "B", exact.STOP)
    distributions = [
        tuple(Fraction(part, 2) for part in composition)
        for composition in _compositions(2, len(random_symbols))
    ]
    random_case_count = 18
    for case_index in range(random_case_count):
        rows: list[dict[str, object]] = []
        for scenario in ("left", "right"):
            for history in ((), ("A",), ("B",)):
                if rng.random() < 0.15:
                    continue
                selected = rng.sample(distributions, rng.randint(1, 2))
                rows.append(
                    _row(
                        scenario,
                        list(history),
                        *[
                            {symbol: exact._rational_text(probability) for symbol, probability in zip(random_symbols, dist)}
                            for dist in selected
                        ],
                    )
                )
        add(f"random_tiny_{case_index:02d}", _contract(list(random_symbols), 2, rows))

    oracle_rows = [item["exhaustive_oracle"] for item in cases if "exhaustive_oracle" in item]
    aggregate_oracle = {
        "fixture_contracts_checked": len(oracle_rows),
        "left_policy_laws_enumerated_sum": sum(item["left_policy_laws"] for item in oracle_rows),
        "right_policy_laws_enumerated_sum": sum(item["right_policy_laws"] for item in oracle_rows),
        "cross_scenario_law_pairs_compared_sum": sum(item["compared_law_pairs"] for item in oracle_rows),
        "exact_vs_exhaustive_mismatches": sum(
            1
            for item in cases
            if "exhaustive_oracle" in item
            and item.get("exact_worst_case_tv") != item["exhaustive_oracle"]["worst_case_tv"]
        ),
        "oracle_method": "Independently enumerates complete deterministic row-generator policies, constructs full padded trace laws, and compares every left/right policy-law pair by direct finite-alphabet L1/2. It shares the production contract parser but not its Bellman recurrence or certificate replay.",
    }

    return {
        "schema": "orchlang.exact-uncertain-distance-experiment/v1",
        "scope": "Development fixtures only; no held-out cohort inputs or outputs are read by this runner.",
        "model": {
            "horizon": "finite; tested through H=3, plus bounded H=10 unit test",
            "row_semantics": "Each scenario/history row is any distribution in the convex hull of its explicit rational generator list; missing live rows are the full simplex.",
            "rectangularity": "All scenario/history rows are independently selectable. Shared global parameters or cross-row/cross-scenario couplings are excluded.",
            "stop": "First __STOP__ ends the visible trace and is padded through the horizon; require_stop_by_horizon checks every supported path when true.",
        },
        "fixtures": cases,
        "sanity_properties": {
            "uncertainty_set_expansion": {
                "base_tv": base_result.get("exact_worst_case_tv"),
                "expanded_tv": expanded_result.get("exact_worst_case_tv"),
                "monotone": Fraction(expanded_result.get("exact_worst_case_tv", "0")) >= Fraction(base_result.get("exact_worst_case_tv", "0")),
            },
            "generator_order_invariance": {
                "original_order_tv": expanded_result.get("exact_worst_case_tv"),
                "permuted_order_tv": reordered_result.get("exact_worst_case_tv"),
                "invariant": expanded_result.get("exact_worst_case_tv") == reordered_result.get("exact_worst_case_tv"),
            },
            "data_processing": {
                "before_projection_tv": original_result.get("exact_worst_case_tv"),
                "after_projection_tv": projected_result.get("exact_worst_case_tv"),
                "nonincreasing": Fraction(projected_result.get("exact_worst_case_tv", "0")) <= Fraction(original_result.get("exact_worst_case_tv", "0")),
            },
            "shared_parameter_excluded_premise": shared_theta,
        },
        "exhaustive_oracle_totals": aggregate_oracle,
        "prior_art_check": {
            "discovery": "OpenAlex search_works query: total variation ambiguity dynamic programming robust probability distributions Tzortzis Charalambous.",
            "primary_pages_checked_with_web": [
                {
                    "title": "Dynamic Programming Subject to Total Variation Distance Ambiguity",
                    "url": "https://arxiv.org/abs/1402.1009",
                    "relevance": "Dynamic programming under conditional-distribution TV ambiguity; related setup, different objective/model.",
                },
                {
                    "title": "Imprecise Markov chains and their limit behaviour",
                    "url": "https://arxiv.org/abs/0801.0980",
                    "relevance": "Credal transition rows and lower/upper expectations for imprecise Markov chains.",
                },
                {
                    "title": "Imprecise probability trees: Bridging two theories of imprecise probability",
                    "url": "https://arxiv.org/abs/0801.1196",
                    "relevance": "Imprecise probability trees and local uncertainty models.",
                },
                {
                    "title": "Coefficients of Ergodicity for Imprecise Markov Chains",
                    "url": "https://leo.ugr.es/sipta/isipta09/proceedings/papers/p039skulj_poster.pdf",
                    "relevance": "Primary ISIPTA proceedings paper on ergodicity coefficients for imprecise chains; adjacent distance literature.",
                },
                {
                    "title": "On the Total Variation Distance of Labelled Markov Chains",
                    "url": "https://arxiv.org/abs/1405.2852",
                    "relevance": "Trace TV for precise labelled Markov chains, not this uncertain-row model.",
                },
                {
                    "title": "On the Relationship between Bisimulation and Trace Equivalence in an Approximate Probabilistic Context",
                    "url": "https://arxiv.org/abs/1701.04547",
                    "relevance": "Finite-horizon trace-TV approximation bounds via approximate probabilistic bisimulation.",
                },
            ],
            "boundary": "Discovery and primary-page spot checks are not a systematic literature review; no novelty or first-result claim is made.",
        },
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }


def main() -> int:
    result = run()
    output = HERE / "experiment_results.json"
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    output.write_text(payload, encoding="utf-8")
    print(output)
    print(f"status={result['status']} failures={len(result['failures'])} cases={len(result['fixtures'])}")
    return 0 if not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
