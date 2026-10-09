#!/usr/bin/env python3
"""Regression checks for the independently implemented source/report auditor."""

import copy
import json
import pathlib
import tempfile
import unittest

from certificate_audit import SourceCost, bind, verify, ROOT


class SourceArithmeticTests(unittest.TestCase):
    def bound(self, body, divisor=4):
        source = 'workflow Test budget 100000 { ' + body + ' output "done"; }'
        return SourceCost(source, divisor).program()[0]['bound']

    def test_sequence(self):
        bound = self.bound('input x: text max_tokens 20; model m = mock("m") max_tokens 10; '
                           'prompt p(t: text) -> text = "{t}"; '
                           'let a: text = call p(x) using m; let b: text = call p(a) using m;')
        self.assertEqual(bound['total_tokens'], 52)

    def test_componentwise_branch(self):
        bound = self.bound('input x: text max_tokens 100; input flag: boolean; '
                           'model a = mock("a") max_tokens 1; model b = mock("b") max_tokens 20; '
                           'prompt p(t: text) -> text = "{t}"; '
                           'if flag { let r: text = call p(x) using a; } '
                           'else { let r: text = call p("") using b; }')
        self.assertEqual(bound, {'guaranteed_tokens': 20, 'estimated_tokens': 101,
                                'total_tokens': 102, 'component_sum_tokens': 121})

    def test_nested_retry_multiplies(self):
        bound = self.bound('model m = mock("m") max_tokens 10; prompt p() -> text = "abcd"; '
                           'retry 2 { retry 3 { let r: text = call p() using m; } }')
        self.assertEqual(bound['total_tokens'], 66)

    def test_model_shadowing_is_lexical(self):
        bound = self.bound('input flag: boolean; model m = mock("outer") max_tokens 20; '
                           'prompt p() -> text = ""; '
                           'if flag { model m = mock("inner") max_tokens 1; '
                           'let r: text = call p() using m; } '
                           'let after: text = call p() using m;')
        self.assertEqual(bound['guaranteed_tokens'], 21)

    def test_utf8_bytes(self):
        bound = self.bound('model m = mock("m") max_tokens 1; '
                           'prompt p(t: text) -> text = "{t}"; '
                           'let r: text = call p("é漢") using m;')
        self.assertEqual(bound['estimated_tokens'], 3)  # template 1, five-byte literal 2

    def test_literal_control_bytes_follow_dsl(self):
        bound = self.bound('model m = mock("m") max_tokens 1; '
                           'prompt p() -> text = "a\x01b"; let r: text = call p() using m;')
        self.assertEqual(bound["estimated_tokens"], 1)

    def test_unknown_argument_bound_fails(self):
        with self.assertRaises(ValueError):
            self.bound('input x: text; model m = mock("m") max_tokens 1; '
                       'prompt p(t: text) -> text = "{t}"; let r: text = call p(x) using m;')

    def test_boolean_needs_explicit_bound_if_prompted(self):
        with self.assertRaises(ValueError):
            self.bound('input x: boolean; model m = mock("m") max_tokens 1; '
                       'prompt p(t: boolean) -> text = "{t}"; let r: text = call p(x) using m;')

    def test_literal_expression_kinds_are_source_facts(self):
        parser = SourceCost(
            'workflow K budget 100 { model m = mock("m") max_tokens 1; '
            'prompt p(a: text, b: text, c: text, d: text) -> text = "{a}{b}{c}{d}"; '
            'let r: text = call p("7", 7, 7.0, true) using m; output "done"; }', 4)
        parser.program()
        arguments = parser.calls[0]['arguments']
        self.assertEqual([item['literal_expr_kind'] for item in arguments],
                         ['text', 'integer', 'decimal', 'boolean'])

    def test_reclassification_keeps_size(self):
        bound = self.bound('input x: text untrusted max_tokens 10; '
                           'endorse(x) as clean: text because "human checked"; '
                           'model m = mock("m") max_tokens 1; '
                           'prompt p(t: text) -> text = "{t}"; let r: text = call p(clean) using m;')
        self.assertEqual(bound['total_tokens'], 12)

    def test_saturation_rejected(self):
        with self.assertRaises(ValueError):
            self.bound('model m = mock("m") max_tokens 10; prompt p() -> text = ""; '
                       'retry 18446744073709551615 { let r: text = call p() using m; }')


class ReportIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='orchlang-auditor-test-')
        cls.source = pathlib.Path(cls.directory.name) / 'sample.orch'
        cls.source.write_text('workflow Demo budget 1000 {\n'
                              ' input x: text max_tokens 10;\n'
                              ' model m = mock("worker") max_tokens 20;\n'
                              ' prompt p(t: text) -> text = "{t}";\n'
                              ' retry 2 { let r: text = call p(x) using m; }\n'
                              ' output x;\n}\n')
        cls.envelope = bind(cls.source, ROOT / 'orchc')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_utf8_source_columns_roundtrip(self):
        source = pathlib.Path(self.directory.name) / 'utf8.orch'
        source.write_text('workflow UTF budget 100 { model m = mock("m") max_tokens 2; '
                          'prompt p() -> text = "é漢"; let r: text = call p() using m; output r; }')
        envelope = bind(source, ROOT / 'orchc')
        self.assertEqual(verify(source, envelope)['calls'], 1)

    def test_roundtrip(self):
        result = verify(self.source, self.envelope)
        self.assertEqual(result['calls'], 1)

    def reject_change(self, operation):
        changed = copy.deepcopy(self.envelope)
        operation(changed['certificate']['workflows'][0])
        with self.assertRaises(ValueError): verify(self.source, changed)

    def test_total_tamper(self):
        self.reject_change(lambda workflow: workflow['bound'].__setitem__('total_tokens', 1))

    def test_component_tamper(self):
        self.reject_change(lambda workflow: workflow['bound'].__setitem__('estimated_tokens', 0))

    def test_call_model_tamper(self):
        self.reject_change(lambda workflow: workflow['call_facts'][0]['model_contract'].__setitem__('model', 'other'))

    def test_template_tamper(self):
        self.reject_change(lambda workflow: workflow['call_facts'][0].__setitem__('template_text', 'xyz'))

    def test_argument_bound_tamper(self):
        self.reject_change(lambda workflow: workflow['call_facts'][0]['arguments'][0].__setitem__('token_bound', 1))

    def test_literal_kind_tamper(self):
        self.reject_change(lambda workflow: workflow['call_facts'][0]['arguments'][0].__setitem__('literal_expr_kind', 'text'))

    def test_derivation_tamper(self):
        self.reject_change(lambda workflow: workflow['derivation'][-1].__setitem__('total_tokens', 1))

    def test_source_digest_tamper(self):
        changed = copy.deepcopy(self.envelope)
        changed['source_sha256'] = '0' * 64
        with self.assertRaises(ValueError): verify(self.source, changed)


if __name__ == '__main__':
    unittest.main()
