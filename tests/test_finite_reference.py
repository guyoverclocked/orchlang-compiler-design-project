import sys
from pathlib import Path
import unittest
from fractions import Fraction

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.finite_reference import Reference, Unsupported, canonical, distribution, tokens


def contract(**changes):
    value = dict(provider="finite", revision="test-v1", tokenizer="utf8-bytes-v1",
                 serializer="raw-utf8-v1", cap=100, sampling="explicit-table",
                 error_policy="status-in-outcome", accounting="all-attempts-input-and-output",
                 state="stateless")
    value.update(changes)
    return value


def outcome(text, p="1", status="ok"):
    return dict(text=text, p=p, status=status)


def call(request="yes", model="m", bind="answer"):
    return dict(kind="call", model=model, request=request, bind=bind)


class FiniteTests(unittest.TestCase):
    def setUp(self):
        self.c = contract()
        self.k = {canonical(self.c): {"yes": [outcome("x")], "no!": [outcome("x" * 100)]}}
        self.ref = Reference({"m": self.c, "alias": dict(self.c)}, self.k)

    def test_same_length_different_requests_invalid_coupling(self):
        left = self.ref.run([call("yes")], {})
        right = self.ref.run([call("no!")], {})
        self.assertEqual(left[0][0].trace[0].input, right[0][0].trace[0].input)
        self.assertNotEqual(distribution(left), distribution(right))
        self.assertEqual((left[0][0].trace[0].output, right[0][0].trace[0].output), (1, 100))

    def test_equivalent_aliases_share_semantic_contract(self):
        self.assertEqual(distribution(self.ref.run([call()], {})),
                         distribution(self.ref.run([call(model="alias")], {})))

    def test_shadowed_contracts_are_distinct(self):
        other = contract(cap=1)
        self.assertNotEqual(canonical(self.c), canonical(other))

    def test_retry_failed_attempts_remain_billed(self):
        ref = Reference({"m": self.c}, {canonical(self.c): {"*": [
            outcome("x", "1/2"), outcome("", "1/2", "error")]}})
        paths = ref.run([dict(kind="retry", bound=2, body=[call()])], {})
        by_calls = {}
        for state, p in paths:
            by_calls[len(state.trace)] = by_calls.get(len(state.trace), Fraction()) + p
        self.assertEqual(by_calls, {1: Fraction(1, 2), 2: Fraction(1, 2)})
        self.assertEqual(len(paths), 3)
        self.assertTrue(any(s.trace[0].status == "error" and len(s.trace) == 2 for s, _ in paths))

    def test_changed_error_contract_not_equal(self):
        self.assertNotEqual(canonical(self.c), canonical(contract(error_policy="no-errors")))
        with self.assertRaises(Unsupported):
            Reference({"m": contract(error_policy="no-errors")}, {})

    def test_tokenizer_units_not_interchangeable(self):
        self.assertEqual(tokens("é", "utf8-bytes-v1"), 2)
        self.assertEqual(tokens("é", "unicode-codepoints-v1"), 1)
        self.assertNotEqual(canonical(self.c), canonical(contract(tokenizer="unicode-codepoints-v1")))

    def test_public_control_secret_content_retained_privately(self):
        program = [{"kind": "if", "guard": "public", "then": [call()], "else": []},
                   dict(kind="private_output", value={"var": "secret"})]
        left = self.ref.run(program, dict(public=True, secret="private A"))
        right = self.ref.run(program, dict(public=True, secret="private B"))
        self.assertEqual(distribution(left), distribution(right))
        self.assertNotEqual(left[0][0].private_outputs, right[0][0].private_outputs)

    def test_aggregate_is_weaker_than_ordered(self):
        a = self.ref.run([call("yes"), call("no!")], {})
        b = self.ref.run([call("no!"), call("yes")], {})
        self.assertEqual(distribution(a, "aggregate"), distribution(b, "aggregate"))
        self.assertNotEqual(distribution(a), distribution(b))

    def test_response_text_drives_downstream_request(self):
        # No kernel entry for x: fail closed rather than substitute a length.
        with self.assertRaises(Unsupported):
            self.ref.run([call("yes", bind="x"), call({"var": "x"})], {})

    def test_invalid_kernel_mass_rejected(self):
        ref = Reference({"m": self.c}, {canonical(self.c): {"*": [outcome("x", "1/2")]}})
        with self.assertRaises(ValueError):
            ref.run([call()], {})

    def test_cap_violation_rejected(self):
        ref = Reference({"m": self.c}, {canonical(self.c): {"*": [outcome("x" * 101)]}})
        with self.assertRaises(ValueError):
            ref.run([call()], {})

    def test_unknown_features_fail_closed(self):
        with self.assertRaises(Unsupported):
            self.ref.run([dict(kind="network")], {})
        with self.assertRaises(Unsupported):
            self.ref.run([dict(kind="retry", bound=17, body=[])], {})


if __name__ == "__main__":
    unittest.main()
