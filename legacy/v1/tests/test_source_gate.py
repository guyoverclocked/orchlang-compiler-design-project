import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.finite_reference import Unsupported
from runtime.source_gate import issue, read_source, bind_certificate


PREFIX = ('workflow W budget 1000 { secret s: boolean max_tokens 1; '
          'prompt p(t: text) -> text = "{t}"; ')
CALL = 'let a: text = call p("yes") using m;'


def source(left=CALL, right=CALL):
    return (PREFIX + 'model m = mock("x") max_tokens 100; if s { ' + left +
            ' } else { ' + right + ' } output "done"; }').encode()


class SourceGateTests(unittest.TestCase):
    def test_nonlanguage_whitespace_rejected(self):
        for separator in ('\u00a0', '\v', '\f'):
            with self.subTest(separator=repr(separator)), self.assertRaises(Unsupported):
                read_source(source().replace(b'workflow W',('workflow'+separator+'W').encode()))

    def test_unused_prompt_parameter_rejected_like_frontend(self):
        with self.assertRaises(Unsupported):
            read_source(source().replace(b'"{t}"',b'"fixed"'))

    def test_aliases_and_scopes(self):
        data = source('model m = mock("x") max_tokens 100; ' + CALL,
                      'model other = mock("x") max_tokens 100; ' + CALL.replace('using m', 'using other'))
        cert = issue(data)
        self.assertEqual(bind_certificate(data, cert)[1][2], 'yes')

    def test_shadowed_contract_negative(self):
        with self.assertRaises(Unsupported):
            issue(source(right='model m = mock("big") max_tokens 100; ' + CALL))

    def test_same_length_different_request_negative(self):
        with self.assertRaises(Unsupported):
            issue(source(right=CALL.replace('yes', 'no!')))

    def test_bound_to_source_bytes(self):
        data = source()
        with self.assertRaises(Unsupported):
            bind_certificate(data + b'\n', issue(data))

    def test_changed_program_rejected_even_if_hash_updated(self):
        data = source()
        cert = issue(data)
        cert['program'][3][2] = 'attacker'
        with self.assertRaises(Unsupported):
            bind_certificate(data, cert)

    def test_plan_untrusted_until_lean_checks(self):
        data = source()
        cert = issue(data)
        cert['plan'] = ['skip']
        self.assertEqual(bind_certificate(data, cert)[1], ['skip'])

    def test_rejects_response_requests_retry_and_tools(self):
        for statement in ('let b: text = call p(a) using m;', 'retry 2 { ' + CALL + ' }',
                          'emit x("data");', 'input x: text max_tokens 4;'):
            with self.subTest(statement=statement), self.assertRaises(Unsupported):
                read_source(source(left=CALL + statement))

    def test_literal_substitution_single_pass_utf8_escapes(self):
        data = ('workflow W budget 999 { model m = mock("x") max_tokens 2; '
                'prompt p(a:text,b:text)->text="{a}|{b}|{a}"; '
                'let x:text=call p("{b}","é\\n") using m; output "ok"; }').encode()
        self.assertEqual(issue(data)['program'][2], '{b}|é\n|{b}')

    def test_malformed_template_and_escapes(self):
        for template in ('"{missing}"', '"{"', '"\\r"'):
            with self.subTest(template=template), self.assertRaises(Unsupported):
                issue(source().replace(b'"{t}"', template.encode()))

    def test_scope_escape_and_duplicate_declaration(self):
        for data in (source(left=CALL + CALL), source().replace(b'if s', b'if missing'),
                     source().replace(b'output "done";', b'let b:text=call p(a) using m;')):
            with self.assertRaises(Unsupported):
                read_source(data)


if __name__ == '__main__':
    unittest.main()
