import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import robust_usage as ru
from robust_usage import (
    ContractError,
    STOP,
    UnverifiableContract,
    certify,
    parse_contract,
    replay,
)


ALPHABET = ["a", "b", STOP]
EXAMPLE = Path(__file__).parent / "examples" / "sharp_history_contract.json"


def distribution(**probabilities):
    return {symbol: str(Fraction(probabilities.get(symbol, 0))) for symbol in ALPHABET}


def row(center, radius="0"):
    return {"center": center, "radius": radius}


def paired(history, left_center, right_center, left_radius="0", right_radius="0"):
    return {
        "history": history,
        "left": row(left_center, left_radius),
        "right": row(right_center, right_radius),
    }


def contract(horizon, rows, require_stop=False):
    return {
        "schema": "orchlang.robust-usage/v1",
        "horizon": horizon,
        "alphabet": ALPHABET,
        "require_stop_by_horizon": require_stop,
        "rows": rows,
    }


def center_law(raw, side):
    parsed = parse_contract(raw)
    side_index = 0 if side == "left" else 1
    law = {(): Fraction(1)}
    for _ in range(parsed.horizon):
        next_law = {}
        for history, mass in law.items():
            if STOP in history:
                probabilities = {STOP: Fraction(1)}
            else:
                row_value = parsed.rows[history][side_index]
                if row_value is None:
                    raise AssertionError(f"missing row at {history!r}")
                probabilities = row_value.center
            for symbol, probability in probabilities.items():
                if probability:
                    output = history + (symbol,)
                    next_law[output] = next_law.get(output, Fraction(0)) + mass * probability
        law = next_law
    return law


def law_tv(left_law, right_law):
    support = set(left_law) | set(right_law)
    return sum((abs(left_law.get(trace, 0) - right_law.get(trace, 0)) for trace in support), Fraction(0)) / 2


def marginals(law, horizon):
    result = []
    for position in range(horizon):
        marginal = {}
        for trace, probability in law.items():
            marginal[trace[position]] = marginal.get(trace[position], Fraction(0)) + probability
        result.append(marginal)
    return result


class RobustUsageTests(unittest.TestCase):
    def test_produced_certificate_obeys_reader_item_cap(self):
        center = distribution(a="1/2", b="1/2")
        raw = contract(22, [paired(["a"] * k, center, center) for k in range(20)])
        certificate = certify(raw)
        def count(value):
            pending, total = [value], 0
            while pending:
                item = pending.pop()
                total += 1
                if isinstance(item, dict):
                    pending.extend(item.values())
                elif isinstance(item, list):
                    pending.extend(item)
            return total
        limit = count(raw) + 1
        self.assertGreater(count(certificate), limit)
        with patch.object(ru, "MAX_JSON_ITEMS", limit):
            parse_contract(raw)
            with self.assertRaises(UnverifiableContract):
                certify(raw)
            accepted, report = replay(raw, certificate)
            self.assertFalse(accepted)
            self.assertIn("item limit", str(report))

    def test_json_depth_limit_is_interpreter_independent(self):
        value = 0
        for _ in range(ru.MAX_JSON_DEPTH):
            value = [value]
        with self.assertRaises(ContractError):
            ru._validate_json_tree(value)
        with self.assertRaises(ContractError):
            ru._loads_json_bytes(json.dumps(value).encode(), "depth probe")

    def test_equal_exact_rows_prove_zero_and_stop_padding(self):
        stop = distribution(**{STOP: 1})
        raw = contract(3, [paired([], stop, stop)], require_stop=True)
        result = certify(raw)
        self.assertEqual(result["tv_upper_bound"], "0")
        self.assertEqual(result["scope"], "complete_trace_through_horizon")
        self.assertTrue(result["termination_proved_by_contract"])
        self.assertEqual(result["worst_shared_prefix"], [STOP, STOP, STOP])

    def test_tv_radii_compose_with_center_distance_and_are_exact(self):
        common = distribution(a="1/2", b="1/2")
        raw = contract(1, [paired([], common, common, "1/4", "1/4")])
        result = certify(raw)
        self.assertEqual(law_tv(center_law(raw, "left"), center_law(raw, "right")), Fraction(0))
        self.assertEqual(result["rows"][0]["local_tv_bound"], "1/2")
        self.assertEqual(result["tv_upper_bound"], "1/2")
        # Opposite shifts attain the sum of the two radii.
        concrete_left = {"a": Fraction(3, 4), "b": Fraction(1, 4), STOP: Fraction(0)}
        concrete_right = {"a": Fraction(1, 4), "b": Fraction(3, 4), STOP: Fraction(0)}
        common_fraction = {symbol: Fraction(probability) for symbol, probability in common.items()}
        self.assertEqual(sum(abs(concrete_left[x] - common_fraction[x]) for x in ALPHABET) / 2, Fraction(1, 4))
        self.assertEqual(sum(abs(concrete_right[x] - common_fraction[x]) for x in ALPHABET) / 2, Fraction(1, 4))
        self.assertEqual(sum(abs(concrete_left[x] - concrete_right[x]) for x in ALPHABET) / 2, Fraction(1, 2))

    def test_equal_slot_marginals_can_have_singular_joint_traces(self):
        fair = distribution(a="1/2", b="1/2")
        raw = contract(
            2,
            [
                paired([], fair, fair),
                paired(["a"], distribution(a=1), distribution(b=1)),
                paired(["b"], distribution(b=1), distribution(a=1)),
            ],
        )
        left_law = center_law(raw, "left")
        right_law = center_law(raw, "right")
        self.assertEqual(marginals(left_law, 2), marginals(right_law, 2))
        self.assertEqual(law_tv(left_law, right_law), Fraction(1))
        self.assertEqual(certify(raw)["tv_upper_bound"], "1")

    def test_visible_stop_position_is_in_the_observer_trace(self):
        stop = distribution(**{STOP: 1})
        event = distribution(a=1)
        raw = contract(
            2,
            [paired([], stop, event), paired(["a"], stop, stop)],
            require_stop=True,
        )
        result = certify(raw)
        self.assertEqual(result["tv_upper_bound"], "1")
        self.assertEqual(result["scope"], "complete_trace_through_horizon")
        self.assertEqual(law_tv(center_law(raw, "left"), center_law(raw, "right")), Fraction(1))

    def test_history_path_bound_is_sharp_and_beats_per_level_maxima(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        result = certify(raw)
        exact_center_tv = law_tv(center_law(raw, "left"), center_law(raw, "right"))
        self.assertEqual(exact_center_tv, Fraction(91, 100))
        self.assertEqual(result["tv_upper_bound"], "91/100")
        self.assertEqual(result["per_level_product_upper_bound"], "99/100")
        self.assertLess(Fraction(result["tv_upper_bound"]), Fraction(result["per_level_product_upper_bound"]))

    def test_missing_shared_prefix_row_becomes_unit_bound(self):
        same = distribution(a=1)
        raw = contract(2, [paired([], same, same)])
        result = certify(raw)
        self.assertEqual(result["tv_upper_bound"], "1")
        missing = next(entry for entry in result["rows"] if entry["history"] == ["a"])
        self.assertTrue(missing["missing_row"])
        self.assertEqual(missing["local_tv_bound"], "1")

    def test_complete_trace_request_rejects_possible_nontermination(self):
        event = distribution(a=1)
        raw = contract(1, [paired([], event, event)], require_stop=True)
        with self.assertRaises(UnverifiableContract):
            certify(raw)

    def test_malformed_stop_padding_is_rejected(self):
        stop = distribution(**{STOP: 1})
        event = distribution(a=1)
        raw = contract(2, [paired([], stop, stop), paired([STOP], event, event)])
        with self.assertRaises(ContractError):
            certify(raw)

    def test_invalid_probability_or_radius_is_rejected(self):
        invalid_sum = {"a": "1/2", "b": "1/3", STOP: "0"}
        raw = contract(1, [paired([], invalid_sum, invalid_sum)])
        with self.assertRaises(ContractError):
            certify(raw)
        too_large = distribution(a=1)
        raw = contract(1, [paired([], too_large, too_large, "3/2", "0")])
        with self.assertRaises(ContractError):
            certify(raw)

    def test_certificate_replay_detects_tampering(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        certificate = certify(raw)
        valid, _ = replay(raw, certificate)
        self.assertTrue(valid)
        tampered = copy.deepcopy(certificate)
        tampered["tv_upper_bound"] = "0"
        valid, _ = replay(raw, tampered)
        self.assertFalse(valid)

    def test_replay_checks_local_obligations_without_calling_producer(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        certificate = certify(raw)
        with patch.object(ru, "certify", side_effect=AssertionError("producer must not run")):
            valid, report = replay(raw, certificate)
        self.assertTrue(valid)
        self.assertIn("necessary continuation coverage", report["checks"])

    def test_replay_rejects_bool_integer_fraction_and_metadata_type_confusion(self):
        stop = distribution(**{STOP: 1})
        raw = contract(1, [paired([], stop, stop)])
        original = certify(raw)

        attacks = []
        changed = copy.deepcopy(original)
        changed["horizon"] = True  # bool compares equal to integer 1 in Python.
        attacks.append(changed)
        changed = copy.deepcopy(original)
        changed["shared_prefix_nodes"] = True
        attacks.append(changed)
        changed = copy.deepcopy(original)
        changed["tv_upper_bound"] = 0.0
        attacks.append(changed)
        changed = copy.deepcopy(original)
        changed["rows"][0]["local_tv_bound"] = "1e-999999999999"
        attacks.append(changed)
        changed = copy.deepcopy(original)
        changed["per_level_maxima"][0]["depth"] = True
        attacks.append(changed)

        for malformed in attacks:
            with self.subTest(certificate=malformed):
                valid, _ = replay(raw, malformed)
                self.assertFalse(valid)

    def test_replay_requires_every_continuation_and_checks_root_and_stop_proof(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        certificate = certify(raw)
        missing = copy.deepcopy(certificate)
        missing["rows"].pop()
        self.assertFalse(replay(raw, missing)[0])

        bad_root = copy.deepcopy(certificate)
        bad_root["survival_lower_bound"] = "0"
        self.assertFalse(replay(raw, bad_root)[0])

        stop = distribution(**{STOP: 1})
        stopped = contract(2, [paired([], stop, stop)], require_stop=True)
        stop_certificate = certify(stopped)
        tampered_stop = copy.deepcopy(stop_certificate)
        tampered_stop["stop_coverage_nodes"] += 1
        self.assertFalse(replay(stopped, tampered_stop)[0])

    def test_duplicate_keys_and_escaped_surrogates_are_rejected(self):
        duplicate = Path(__file__).parents[1] / "adversarial_review" / "duplicate_keys_contract.json"
        with self.assertRaises(ContractError):
            ru._load_json(str(duplicate))
        with self.assertRaises(ContractError):
            ru._loads_json_bytes(b'{"symbol":"\\ud800"}', "surrogate test")
        with self.assertRaises(ContractError):
            ru._loads_json_bytes(b'{"symbol":"\xff"}', "UTF-8 test")

    def test_horizon_and_exact_rational_input_have_hard_bounds(self):
        no_rows = contract(2_000_000, [])
        with self.assertRaises(ContractError):
            certify(no_rows, max_nodes=1)
        with self.assertRaises(ContractError):
            ru._fraction("1e999999999999", "attack")
        with self.assertRaises(ContractError):
            ru._fraction("1/" + "9" * (ru.MAX_RATIONAL_DIGITS + 1), "attack")
        with self.assertRaises(ContractError):
            ru._loads_json_bytes(b"1" + b"0" * (ru.MAX_INTEGER_DIGITS + 1), "integer bomb")
        with self.assertRaises(ContractError):
            ru._fraction(1 << (ru.MAX_NUMERIC_BITS + 1), "integer bomb")

    def test_intermediate_rational_growth_fails_closed(self):
        horizon = 100
        left = distribution(a=1)
        right = distribution(a="1/2", **{STOP: "1/2"})
        rows = [paired(["a"] * depth, left, right) for depth in range(horizon)]
        raw = contract(horizon, rows)
        # Production permits up to MAX_ARITHMETIC_BITS. Lowering only this
        # limit in the test makes a long exact product hit it quickly.
        with patch.object(ru, "MAX_ARITHMETIC_BITS", 64):
            with self.assertRaises(UnverifiableContract):
                certify(raw, max_nodes=1_000)

    def test_file_reader_caps_bytes_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            oversized = Path(directory) / "large.json"
            oversized.write_bytes(b"{" + b" " * 20 + b"}")
            with patch.object(ru, "MAX_INPUT_BYTES", 8):
                with self.assertRaises(ContractError):
                    ru._load_json(str(oversized))

    def test_valid_horizon_1100_uses_bounded_iterative_traversals(self):
        horizon = 1_100
        event = distribution(a=1)
        stop = distribution(**{STOP: 1})
        rows = [
            paired(["a"] * depth, event if depth < horizon - 1 else stop,
                   event if depth < horizon - 1 else stop)
            for depth in range(horizon)
        ]
        raw = contract(horizon, rows, require_stop=True)
        certificate = certify(raw, max_nodes=3_000)
        self.assertEqual(certificate["tv_upper_bound"], "0")
        self.assertEqual(certificate["shared_prefix_nodes"], horizon)
        valid, _ = replay(raw, certificate, max_nodes=3_000)
        self.assertTrue(valid)

    def test_node_limit_cli_does_not_emit_partial_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = ru.main(["certify", str(path), "--max-nodes", "1", "--out", "-"])
            self.assertEqual(status, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("unknown/rejected:", stderr.getvalue())

    def test_cli_certificate_file_round_trip_uses_local_obligation_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "contract.json"
            certificate_path = Path(directory) / "certificate.json"
            contract_path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            status = ru.main(["certify", str(contract_path), "--out", str(certificate_path)])
            self.assertEqual(status, 0)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = ru.main(["replay", str(contract_path), str(certificate_path)])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(stdout.getvalue())["replay"], "ok")

    def test_node_limit_returns_unknown(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        with self.assertRaises(UnverifiableContract):
            certify(raw, max_nodes=1)


if __name__ == "__main__":
    unittest.main()
