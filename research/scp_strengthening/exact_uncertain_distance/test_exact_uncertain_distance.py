from __future__ import annotations

import copy
import itertools
import json
import random
import tempfile
import unittest
from contextlib import redirect_stderr
from fractions import Fraction
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import exact_uncertain_distance as exact


STOP = exact.STOP


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


def _tv(left: dict[tuple[str, ...], Fraction], right: dict[tuple[str, ...], Fraction]) -> Fraction:
    return sum((abs(left.get(trace, Fraction(0)) - right.get(trace, Fraction(0))) for trace in left.keys() | right.keys()), Fraction(0)) / 2


def _all_deterministic_policy_laws(contract: exact.Contract, scenario: str) -> list[dict[tuple[str, ...], Fraction]]:
    """Brute-force whole row policies and their complete padded trace laws."""
    live_symbols = tuple(symbol for symbol in contract.alphabet if symbol != STOP)
    histories = [
        history
        for depth in range(contract.horizon)
        for history in itertools.product(live_symbols, repeat=depth)
    ]
    row_generators = [exact._row(contract, scenario, history) for history in histories]
    laws = []
    for choices in itertools.product(*(range(len(gens)) for gens in row_generators)):
        policy = dict(zip(histories, choices))
        law: dict[tuple[str, ...], Fraction] = {}

        def visit(history: tuple[str, ...], trace: tuple[str, ...], mass: Fraction) -> None:
            if len(trace) == contract.horizon:
                law[trace] = law.get(trace, Fraction(0)) + mass
                return
            generators = exact._row(contract, scenario, history)
            row = generators[policy[history]]
            for index, probability in enumerate(row):
                if probability == 0:
                    continue
                symbol = contract.alphabet[index]
                next_trace = trace + (symbol,)
                next_mass = mass * probability
                if symbol == STOP:
                    padded = next_trace + (STOP,) * (contract.horizon - len(next_trace))
                    law[padded] = law.get(padded, Fraction(0)) + next_mass
                else:
                    visit(history + (symbol,), next_trace, next_mass)

        visit((), (), Fraction(1))
        laws.append(law)
    return laws


def _exhaustive_worst_tv(raw: dict[str, object]) -> Fraction:
    """Independent reference: enumerate generator policies, then compare laws."""
    return _exhaustive_metrics(raw)["worst_tv"]


def _exhaustive_metrics(raw: dict[str, object]) -> dict[str, object]:
    """Return separately auditable brute-force law/pair counts and max TV."""
    contract = exact.parse_contract(raw)
    left_laws = _all_deterministic_policy_laws(contract, "left")
    right_laws = _all_deterministic_policy_laws(contract, "right")
    return {
        "worst_tv": max((_tv(left, right) for left in left_laws for right in right_laws), default=Fraction(0)),
        "left_policies": len(left_laws),
        "right_policies": len(right_laws),
        "compared_pairs": len(left_laws) * len(right_laws),
    }


def _pathwise_bound_for_degenerate_rows(raw: dict[str, object]) -> Fraction:
    """Tiny test-only transcription of the previous zero-radius survival bound."""
    contract = exact.parse_contract(raw)
    alphabet = contract.alphabet

    def survival(history: tuple[str, ...]) -> Fraction:
        if len(history) == contract.horizon:
            return Fraction(1)
        left = exact._row(contract, "left", history)
        right = exact._row(contract, "right", history)
        if len(left) != 1 or len(right) != 1:
            raise AssertionError("the old pathwise fixture uses singleton rows")
        left_row, right_row = left[0], right[0]
        tv = sum((abs(a - b) for a, b in zip(left_row, right_row)), Fraction(0)) / 2
        common = [
            symbol
            for symbol, a, b in zip(alphabet, left_row, right_row)
            if a > 0 and b > 0 and symbol != STOP
        ]
        if tv == 1:
            return Fraction(0)
        if not common:
            return Fraction(0)
        continuation = min(survival(history + (symbol,)) for symbol in common)
        return (1 - tv) * continuation

    return 1 - survival(())


def _compositions(total: int, width: int) -> list[tuple[int, ...]]:
    if width == 1:
        return [(total,)]
    result = []
    for first in range(total + 1):
        result.extend((first,) + tail for tail in _compositions(total - first, width - 1))
    return result


class ExactUncertainDistanceTests(unittest.TestCase):
    def test_json_depth_limit_is_interpreter_independent(self) -> None:
        value = 0
        for _ in range(exact.MAX_JSON_DEPTH):
            value = [value]
        with self.assertRaises(exact.ContractError):
            exact._validate_json_tree(value, "depth probe")
        with self.assertRaises(exact.ContractError):
            exact.parse_json_bytes(json.dumps(value).encode())

    def test_state_cap_reserves_unfinished_ancestor(self) -> None:
        raw = _contract(["A", STOP], 1, [
            _row(scenario, [], {"A": 1, STOP: 0}) for scenario in ("left", "right")])
        with patch.object(exact, "MAX_DP_STATES", 1):
            with self.assertRaises(exact.UnverifiableContract):
                exact.certify(raw)
        with patch.object(exact, "MAX_DP_STATES", 2):
            certificate = exact.certify(raw)
            self.assertEqual(len(certificate["states"]), 2)
            self.assertTrue(exact.verify(raw, certificate)["verified"])

    def test_generated_rationals_use_bounded_certificate_domain(self) -> None:
        d1, d2 = 10**46 + 33, 10**46 + 79
        rows = []
        for scenario in ("left", "right"):
            rows.extend([
                _row(scenario, [], {"A": f"1/{d1}", STOP: f"{d1-1}/{d1}"}),
                _row(scenario, ["A"], {"A": f"1/{d2}", STOP: f"{d2-1}/{d2}"}),
                _row(scenario, ["A", "A"], {"A": 0, STOP: 1}),
            ])
        raw = _contract(["A", STOP], 3, rows, require_stop=True)
        certificate = exact.certify(raw)
        state = next(item for item in certificate["states"] if item["history"] == ["A", "A"])
        self.assertGreater(len(state["left_mass"].split("/")[1]), exact.MAX_RATIONAL_DIGITS)
        decoded = exact.parse_json_bytes(exact._certificate_bytes(certificate) + b"\n")
        self.assertEqual(exact.verify(raw, decoded)["worst_case_tv"], "0")

    def test_certificate_item_cap_applies_to_all_interfaces(self) -> None:
        rows = []
        for scenario, denominator in (("left", 17), ("right", 19)):
            rows.append(_row(scenario, [], *[
                {"A": f"{numerator}/{denominator}", STOP: f"{denominator-numerator}/{denominator}"}
                for numerator in range(1, 17)]))
        raw = _contract(["A", STOP], 1, rows)
        certificate = exact.certify(raw)
        self.assertEqual(len(certificate["states"]), 257)
        with patch.object(exact, "MAX_JSON_ITEMS", 1000):
            exact.parse_contract(raw)
            with self.assertRaises(exact.UnverifiableContract):
                exact.certify(raw)
            with self.assertRaises(exact.UnverifiableContract):
                exact.verify(raw, certificate)
            with self.assertRaises(exact.ContractError):
                exact.parse_json_bytes(json.dumps(certificate).encode())

    def test_unequal_prefix_mass_is_preserved(self) -> None:
        alphabet = ["A", "B", "C", STOP]
        raw = _contract(
            alphabet,
            2,
            [
                _row("left", [], _distribution(tuple(alphabet), A="2/3", B="1/3")),
                _row("right", [], _distribution(tuple(alphabet), A="1/3", B="2/3")),
                _row("left", ["A"], _distribution(tuple(alphabet), C=1)),
                _row("right", ["A"], _distribution(tuple(alphabet), C=1)),
                _row("left", ["B"], _distribution(tuple(alphabet), C=1)),
                _row("right", ["B"], _distribution(tuple(alphabet), C=1)),
            ],
        )
        certificate = exact.certify(raw)
        self.assertEqual(certificate["worst_case_tv"], "1/3")
        self.assertEqual(exact.verify(raw, certificate)["worst_case_tv"], "1/3")
        prefix_states = [state for state in certificate["states"] if state["history"] == ["A"]]
        self.assertEqual(len(prefix_states), 1)
        self.assertEqual(prefix_states[0]["left_mass"], "2/3")
        self.assertEqual(prefix_states[0]["right_mass"], "1/3")

    def test_decisive_exact_bound_beats_old_pathwise_bound(self) -> None:
        example = Path(__file__).parent / "examples" / "unequal_prefix_mass.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        certificate = exact.certify(raw)
        self.assertEqual(certificate["worst_case_tv"], "1/2")
        self.assertEqual(_exhaustive_worst_tv(raw), Fraction(1, 2))
        self.assertEqual(_pathwise_bound_for_degenerate_rows(raw), Fraction(1))
        self.assertEqual(exact.verify(raw, certificate)["worst_case_tv"], "1/2")

    def test_rectangular_claim_excludes_a_shared_global_parameter(self) -> None:
        alphabet = ("A", "B", STOP)
        tied_projection = [
            _row(
                "left",
                [],
                _distribution(alphabet, A=1),
                _distribution(alphabet, B=1),
            ),
            _row(
                "right",
                [],
                _distribution(alphabet, A=1),
                _distribution(alphabet, B=1),
            ),
        ]
        raw = _contract(list(alphabet), 1, tied_projection)
        # The checker interprets the row sets as independent convex hulls and
        # can pair left=delta_A with right=delta_B, hence exact robust TV=1.
        self.assertEqual(exact.certify(raw)["worst_case_tv"], "1")
        # Under a shared latent theta, only (delta_A,delta_A) and
        # (delta_B,delta_B) are legal pairs; their true paired TV is always 0.
        linked_pair_laws = [
            ({("A",): Fraction(1)}, {("A",): Fraction(1)}),
            ({("B",): Fraction(1)}, {("B",): Fraction(1)}),
        ]
        self.assertEqual(max(_tv(left, right) for left, right in linked_pair_laws), 0)

    def test_uncertainty_set_monotonicity_and_generator_order(self) -> None:
        alphabet = ("A", "B", STOP)
        delta_a = _distribution(alphabet, A=1)
        delta_b = _distribution(alphabet, B=1)
        base = _contract(
            list(alphabet),
            1,
            [_row("left", [], delta_a), _row("right", [], delta_a)],
        )
        expanded = _contract(
            list(alphabet),
            1,
            [_row("left", [], delta_a, delta_b), _row("right", [], delta_a)],
        )
        base_value = Fraction(exact.certify(base)["worst_case_tv"])
        expanded_value = Fraction(exact.certify(expanded)["worst_case_tv"])
        self.assertEqual(base_value, 0)
        self.assertEqual(expanded_value, 1)
        self.assertGreaterEqual(expanded_value, base_value)

        reordered = _contract(
            list(alphabet),
            1,
            [_row("left", [], delta_b, delta_a), _row("right", [], delta_a)],
        )
        self.assertEqual(Fraction(exact.certify(reordered)["worst_case_tv"]), expanded_value)

    def test_one_step_projection_obeys_total_variation_data_processing(self) -> None:
        original_alphabet = ("A", "B", "C", STOP)
        original = _contract(
            list(original_alphabet),
            1,
            [
                _row("left", [], _distribution(original_alphabet, A=1)),
                _row("right", [], _distribution(original_alphabet, B=1)),
            ],
        )
        original_value = Fraction(exact.certify(original)["worst_case_tv"])
        projection = {"A": "X", "B": "X", "C": "C", STOP: STOP}
        projected_alphabet = ("X", "C", STOP)
        projected_rows = []
        for row in original["rows"]:
            gen = row["generators"][0]
            projected = {symbol: Fraction(0) for symbol in projected_alphabet}
            for symbol, probability in gen.items():
                projected[projection[symbol]] += Fraction(probability)
            projected_rows.append(
                _row(
                    row["scenario"],
                    [],
                    {symbol: exact._rational_text(prob) for symbol, prob in projected.items()},
                )
            )
        projected = _contract(list(projected_alphabet), 1, projected_rows)
        projected_value = Fraction(exact.certify(projected)["worst_case_tv"])
        self.assertEqual(original_value, 1)
        self.assertEqual(projected_value, 0)
        self.assertLessEqual(projected_value, original_value)

    def test_stop_padding_and_error_as_an_ordinary_visible_symbol(self) -> None:
        alphabet = ["ERROR", "RECOVERED", STOP]
        raw = _contract(
            alphabet,
            3,
            [
                _row("left", [], _distribution(tuple(alphabet), ERROR=1)),
                _row("right", [], _distribution(tuple(alphabet), ERROR=1)),
                _row("left", ["ERROR"], _distribution(tuple(alphabet), RECOVERED=1)),
                _row("right", ["ERROR"], _distribution(tuple(alphabet), **{STOP: 1})),
                _row("left", ["ERROR", "RECOVERED"], _distribution(tuple(alphabet), **{STOP: 1})),
            ],
            require_stop=True,
        )
        certificate = exact.certify(raw)
        self.assertEqual(certificate["worst_case_tv"], "1")
        self.assertEqual(exact.verify(raw, certificate)["worst_case_tv"], "1")
        self.assertTrue(all(STOP not in state["history"] for state in certificate["states"]))

    def test_missing_live_rows_are_full_simplex(self) -> None:
        alphabet = ["A", "B", STOP]
        raw = _contract(alphabet, 1, [])
        certificate = exact.certify(raw)
        # Both scenario rows are independently unconstrained, so they may
        # choose different alphabet symbols and have disjoint laws.
        self.assertEqual(certificate["worst_case_tv"], "1")
        self.assertTrue(exact.verify(raw, certificate)["verified"])

    def test_small_random_contracts_match_exhaustive_whole_law_oracle(self) -> None:
        rng = random.Random(20261014)
        alphabet = ("A", "B", STOP)
        distributions = [
            tuple(Fraction(part, 2) for part in composition)
            for composition in _compositions(2, len(alphabet))
        ]
        for _ in range(18):
            rows: list[dict[str, object]] = []
            histories = [(), ("A",), ("B",)]
            for scenario in ("left", "right"):
                for history in histories:
                    if rng.random() < 0.15:
                        continue  # exercise conservative full-simplex fallback
                    chosen = rng.sample(distributions, rng.randint(1, 2))
                    rows.append(
                        _row(
                            scenario,
                            list(history),
                            *[
                                {symbol: exact._rational_text(prob) for symbol, prob in zip(alphabet, distribution)}
                                for distribution in chosen
                            ],
                        )
                    )
            raw = _contract(list(alphabet), 2, rows)
            certificate = exact.certify(raw)
            expected = _exhaustive_worst_tv(raw)
            self.assertEqual(Fraction(certificate["worst_case_tv"]), expected)
            self.assertEqual(exact.verify(raw, certificate)["worst_case_tv"], certificate["worst_case_tv"])

    def test_certificate_tampering_and_contract_binding_fail(self) -> None:
        alphabet = ["A", "B", STOP]
        raw = _contract(alphabet, 1, [])
        certificate = exact.certify(raw)
        tampered = copy.deepcopy(certificate)
        tampered["worst_case_tv"] = "0"
        with self.assertRaises(exact.ContractError):
            exact.verify(raw, tampered)
        changed = copy.deepcopy(raw)
        changed["horizon"] = 2
        with self.assertRaises(exact.ContractError):
            exact.verify(changed, certificate)

        # Python considers True equal to 1, so certificate integer indexes
        # must use exact type checks before ordinary value comparisons.
        bool_index = copy.deepcopy(certificate)
        bool_index["states"][0]["selected_pair"] = [True, 0]
        with self.assertRaises(exact.ContractError):
            exact.verify(raw, bool_index)
        bool_mass = copy.deepcopy(certificate)
        bool_mass["states"][0]["left_mass"] = True
        with self.assertRaises(exact.ContractError):
            exact.verify(raw, bool_mass)
        bool_overlap = copy.deepcopy(certificate)
        bool_overlap["states"][0]["overlap"] = True
        with self.assertRaises(exact.ContractError):
            exact.verify(raw, bool_overlap)

    def test_strict_json_types_duplicates_unicode_and_rationals(self) -> None:
        malformed = [
            b'{"x":1,"x":2}',
            b'{"x":"a","\\u0078":"b"}',
            b'{"x":0.5}',
            b'{"x":1e-3}',
            b'{"x":"\\ud800"}',
            b"\xff",
        ]
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(exact.ContractError):
                exact.parse_json_bytes(data)
        alphabet = ["A", STOP]
        raw = _contract(alphabet, True, [])  # bool is not a horizon integer
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(raw)
        bad_probability = _contract(
            alphabet,
            1,
            [_row("left", [], _distribution(tuple(alphabet), A=False, **{STOP: 1}))],
        )
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(bad_probability)
        bad_rational = _contract(
            alphabet,
            1,
            [_row("left", [], {"A": "2/0", STOP: 0})],
        )
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(bad_rational)

    def test_duplicate_rows_and_generators_fail(self) -> None:
        alphabet = ["A", STOP]
        point = _distribution(tuple(alphabet), A=1)
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(_contract(alphabet, 1, [_row("left", [], point), _row("left", [], point)]))
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(_contract(alphabet, 1, [_row("left", [], point, point)]))
        equivalent_point = _distribution(tuple(alphabet), A="2/2", **{STOP: 0})
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(_contract(alphabet, 1, [_row("left", [], point, equivalent_point)]))

    def test_fail_closed_work_cap_does_not_replace_existing_output(self) -> None:
        example = Path(__file__).parent / "examples" / "unequal_prefix_mass.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "contract.json"
            output_path = Path(directory) / "certificate.json"
            contract_path.write_text(json.dumps(raw), encoding="utf-8")
            output_path.write_bytes(b"previous-complete-certificate\n")
            with patch.object(exact, "MAX_EVALUATIONS", 1), redirect_stderr(StringIO()):
                status = exact.main(["certify", str(contract_path), "--out", str(output_path)])
            self.assertEqual(status, 2)
            self.assertEqual(output_path.read_bytes(), b"previous-complete-certificate\n")

    def test_state_rational_generator_and_byte_caps_fail_closed(self) -> None:
        alphabet = ["A", STOP]
        singleton = _contract(
            alphabet,
            1,
            [
                _row("left", [], _distribution(tuple(alphabet), A="1/2", **{STOP: "1/2"})),
                _row("right", [], _distribution(tuple(alphabet), A="1/2", **{STOP: "1/2"})),
            ],
        )
        with patch.object(exact, "MAX_DP_STATES", 0):
            with self.assertRaises(exact.UnverifiableContract):
                exact.certify(singleton)
        with patch.object(exact, "MAX_ARITHMETIC_BITS", 1):
            with self.assertRaises(exact.UnverifiableContract):
                exact.parse_contract(singleton)
        two_vertices = _contract(
            alphabet,
            1,
            [_row("left", [], _distribution(tuple(alphabet), A=1), _distribution(tuple(alphabet), **{STOP: 1}))],
        )
        with patch.object(exact, "MAX_GENERATORS_PER_ROW", 1):
            with self.assertRaises(exact.ContractError):
                exact.parse_contract(two_vertices)
        with patch.object(exact, "MAX_INPUT_BYTES", 4):
            with self.assertRaises(exact.ContractError):
                exact.parse_json_bytes(b"12345")

    def test_output_byte_cap_does_not_replace_existing_output(self) -> None:
        alphabet = ["A", STOP]
        raw = _contract(alphabet, 1, [])
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "contract.json"
            output_path = Path(directory) / "certificate.json"
            contract_path.write_text(json.dumps(raw), encoding="utf-8")
            output_path.write_bytes(b"previous-complete-certificate\n")
            with patch.object(exact, "MAX_OUTPUT_BYTES", 16), redirect_stderr(StringIO()):
                status = exact.main(["certify", str(contract_path), "--out", str(output_path)])
            self.assertEqual(status, 2)
            self.assertEqual(output_path.read_bytes(), b"previous-complete-certificate\n")

    def test_produced_certificate_round_trips_through_bounded_input_parser(self) -> None:
        example = Path(__file__).parent / "examples" / "unequal_prefix_mass.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        certificate = exact.certify(raw)
        encoded = exact._certificate_bytes(certificate)
        self.assertLessEqual(len(encoded) + 1, exact.MAX_INPUT_BYTES)
        parsed = exact.parse_json_bytes(encoded + b"\n", "generated certificate")
        self.assertTrue(exact.verify(raw, parsed)["verified"])

    def test_maximum_supported_horizon_uses_bounded_recursion(self) -> None:
        alphabet = ("A", STOP)
        rows = []
        for depth in range(10):
            history = ["A"] * depth
            next_symbol = STOP if depth == 9 else "A"
            rows.append(_row("left", history, _distribution(alphabet, **{next_symbol: 1})))
            rows.append(_row("right", history, _distribution(alphabet, **{next_symbol: 1})))
        raw = _contract(list(alphabet), 10, rows, require_stop=True)
        certificate = exact.certify(raw)
        self.assertEqual(certificate["worst_case_tv"], "0")
        self.assertTrue(exact.verify(raw, certificate)["verified"])

    def test_direct_api_cyclic_json_graph_is_rejected(self) -> None:
        raw = _contract(["A", STOP], 1, [])
        raw["cycle"] = raw
        with self.assertRaises(exact.ContractError):
            exact.parse_contract(raw)


if __name__ == "__main__":
    unittest.main()
