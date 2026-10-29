import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime.finite_reference import Unsupported
from runtime.dataflow_gate import (read_source, issue, bind_certificate, template_expression,
                                   reference_program, normalize_text, normalize, syntactic_normalize)

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/certificates/dataflow_certificate.orch'


class DataflowTests(unittest.TestCase):
    def test_monoid_request_rewrites_preserve_slot_order(self):
        term=['append',['append',['literal','Ne'],['literal','xt:']],
              ['append',['var',2],['literal','']]]
        self.assertEqual(normalize_text(term),['append',['literal','Next:'],['var',2]])
        self.assertNotEqual(normalize_text(['append',['var',2],['var',3]]),
                            normalize_text(['append',['var',3],['var',2]]))

    def test_semantically_equal_requests_gain_over_raw_tree_baseline(self):
        a=['call',1,'c',['append',['literal','A'],['append',['var',0],['literal','']]]]
        b=['call',1,'c',['append',['literal','A'],['var',0]]]
        program=['secret',0,a,b]
        self.assertIsNone(syntactic_normalize(program))
        self.assertEqual(normalize(program),b)

    def test_public_branch_and_sequence_units_gain_over_shape_baseline(self):
        call=['call',1,'c',['var',0]]
        program=['secret',0,['seq',['skip'],['public',0,call,call]],call]
        self.assertIsNone(syntactic_normalize(program))
        self.assertEqual(normalize(program),call)

    def test_observable_call_order_and_response_slot_still_distinct(self):
        a=['call',1,'c',['literal','A']]
        b=['call',2,'c',['literal','B']]
        self.assertIsNone(normalize(['secret',0,['seq',a,b],['seq',b,a]]))
        self.assertIsNone(normalize(['secret',0,a,['call',2,'c',['literal','A']]]))

    def test_unequal_public_branches_and_requests_are_retained(self):
        a=['call',1,'c',['literal','yes']]
        b=['call',1,'c',['literal','no!']]
        self.assertEqual(normalize(['public',0,a,b]),['public',0,a,b])
        self.assertIsNone(normalize(['secret',0,a,b]))

    def test_alpha_renamed_pipeline(self):
        parsed=read_source(EXAMPLE.read_bytes())
        cert=issue(EXAMPLE.read_bytes())
        self.assertEqual(parsed['slots'],4)  # input, two aligned responses, public-tail response
        self.assertEqual(len(parsed['public_inputs']),2)
        self.assertEqual(len(parsed['secret_guards']),1)
        self.assertEqual(cert['plan'][0],'seq')
        self.assertEqual(bind_certificate(EXAMPLE.read_bytes(),cert)['execute'],[])

    def test_downstream_response_replaced_by_literal_rejected(self):
        data=EXAMPLE.read_bytes().replace(b'next(response)',b'next("same-length")')
        with self.assertRaises(Unsupported):
            issue(data)

    def test_public_control_retained_without_equal_arms(self):
        parsed=read_source(EXAMPLE.read_bytes())
        cert=issue(EXAMPLE.read_bytes())
        self.assertEqual(cert['plan'][2][0],'public')
        self.assertNotEqual(cert['plan'][2][2],cert['plan'][2][3])

    def test_source_tamper(self):
        data=EXAMPLE.read_bytes()
        with self.assertRaises(Unsupported):
            bind_certificate(data+b'\n',issue(data))

    def test_lexical_branch_response_does_not_escape(self):
        data=EXAMPLE.read_bytes().replace(b'output "done";',b'let bad:text=call next(a) using m; output "done";')
        with self.assertRaises(Unsupported):
            read_source(data)

    def test_secret_guard_cannot_be_request_text(self):
        data=EXAMPLE.read_bytes().replace(b'first(topic)',b'first(s)')
        with self.assertRaises(Unsupported):
            read_source(data)

    def test_secret_text_and_branch_inputs_unsupported(self):
        for data in (EXAMPLE.read_bytes().replace(b'secret s: boolean max_tokens 1;',b'secret s:text max_tokens 1;'),
                     EXAMPLE.read_bytes().replace(b'if s {',b'if s { input local:text max_tokens 4;')):
            with self.assertRaises(Unsupported):
                read_source(data)

    def test_retries_and_nonliteral_outputs_fail_closed(self):
        for data in (EXAMPLE.read_bytes().replace(b'output "done";',b'output topic;'),
                     EXAMPLE.read_bytes().replace(b'output "done";',b'retry 2 {} output "done";')):
            with self.assertRaises(Unsupported):
                read_source(data)

    def test_branch_outputs_not_hidden_by_resource_projection(self):
        data=EXAMPLE.read_bytes().replace(b'if s {',b'if s { output "secret arm";')
        with self.assertRaises(Unsupported):
            read_source(data)

    def test_template_keeps_slot_identity_and_substitutes_once(self):
        result=template_expression('{a}|{b}|{a}',['a','b'],[['var',2],['literal','{a}']])
        self.assertEqual(result,['append',['var',2],['append',['literal','|{a}|'],['var',2]]])

    def test_unused_literal_argument_normalizes_by_request(self):
        # Content not used by a template cannot affect this raw serializer.
        self.assertEqual(template_expression('fixed',['a'],[['literal','yes']]),
                         template_expression('fixed',['a'],[['literal','no!']]))

    def test_unused_source_parameter_is_not_a_valid_prompt_declaration(self):
        with self.assertRaises(Unsupported):
            read_source(EXAMPLE.read_bytes().replace(b'"Start:{t}"',b'"fixed"'))

    def test_model_contract_shadowing(self):
        data=EXAMPLE.read_bytes().replace(b'mock("dataflow-demo-v1") max_tokens 64;\n        let response',
                                         b'mock("other") max_tokens 64;\n        let response')
        with self.assertRaises(Unsupported):
            issue(data)

    def test_root_inputs_and_response_slots_are_distinct(self):
        parsed=read_source(EXAMPLE.read_bytes())
        tree=reference_program(parsed['program'])
        left=tree[0]['then']
        self.assertEqual(left[0]['bind'],'v1')
        self.assertEqual(left[0]['request'],{'concat':['Start:',{'var':'v0'}]})
        self.assertEqual(left[1]['request'],{'concat':['Next:',{'var':'v1'}]})


if __name__=='__main__':
    unittest.main()
