import unittest
from orchlang import admission as A, core as C, models as M, runtime as R


class ByteAdmission(unittest.TestCase):
    def test_utf8_clipping_never_splits_a_codepoint_or_exceeds_cap(self):
        for cap in range(20):
            value = A.clip_utf8("漢字🙂a" * 3, cap)
            self.assertLessEqual(len(value.encode("utf-8")), cap)
            self.assertTrue(("漢字🙂a" * 3).startswith(value))

    def test_expression_envelope_handles_trim_and_escaping(self):
        expression = C.EApp(C.ELit("漢"), C.EEscape(C.ETrim(C.EVar(0))))
        values = ("", "a", "\\\x1f", "  漢字 ")
        for value in values:
            bound = A.expression_bytes(expression, {0: len(value.encode("utf-8"))})
            self.assertLessEqual(len(C.eval_expr({0: value}, expression).encode("utf-8")), bound)

    def test_entry_guard_refuses_before_any_model_dispatch(self):
        backend = R.MockBackend(M.Profile("m", "unused", "qwen2"))
        contract = dict(value_bounds={0: 1}, tool_bytes={}, response_bytes_per_token=16, dummy_request=".")
        runtime = A.ByteBoundedRuntime({"m": backend}, {}, {}, byte_contract=contract)
        with self.assertRaisesRegex(R.ContractViolation, "entry store"):
            runtime.run(C.Dummy("m", 1, 4), {0: "漢"})
        self.assertEqual(runtime.trace, [])

    def test_isolated_padder_accepts_canonical_raw_dummy(self):
        backend = R.MockBackend(M.Profile("m", "unused", "qwen2"))
        self.assertEqual(R.Padder(backend).pad(".", 4), (".", 3, False))
