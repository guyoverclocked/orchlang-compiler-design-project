import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchlang import assurance as A, compiler as K, core as C, runtime as R, syntax, validate
from orchlang.models import Profile, Template, TEMPLATES, CharTokenizer

TEMPLATES.setdefault("assurance-mock",Template("assurance-mock",None,"<{role}>{content}</>\n","<a>","<pad>","</>\n"))
PROFILE=Profile("m","","assurance-mock",filler=".")
PROFILES={"m":PROFILE}
SOURCE=b'''workflow W { input q: text secret max_tokens 4; model m = "m";
prompt p(x) = user "{x}"; let r = call p(q) using m max_tokens 12; output r; }'''


class Assurance(unittest.TestCase):
    def setUp(self):
        self.program,self.binding=A.source_binding(SOURCE,PROFILES)
        self.shaped=K.Shaper(self.program,PROFILES,{"m":CharTokenizer()}).run()

    def test_source_binding_owns_original_and_secrets(self):
        with patch.object(validate,"lean_validate_batch",return_value=[{"accepted":False}]) as checker:
            A.validate_candidates(SOURCE,PROFILES,{"forged":self.program.body})
            payload=checker.call_args.args[0][0]
            self.assertEqual(payload["secret_inputs"],[0])
            self.assertIn(0,payload["high"])
            self.assertEqual(payload["original"],C.stmt_json(self.program.body))
        changed=SOURCE.replace(b"max_tokens 4",b"max_tokens 5")
        self.assertNotEqual(A.source_binding(changed,PROFILES)[1]["binding_sha256"],self.binding["binding_sha256"])

    def test_resume_never_relabels_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest={"source":"one","model":"hash","data":"rows","temperature":0.0}
            A.open_run(directory,manifest)
            A.open_run(directory,manifest)
            Path(directory,"ours.jsonl").write_text('{"id":"a"}\n')
            with self.assertRaisesRegex(ValueError,"fingerprint"):
                A.open_run(directory,{**manifest,"model":"other"})
            self.assertEqual(A.checked_record_ids(Path(directory,"ours.jsonl"),{"a"}),{"a"})
            with Path(directory,"ours.jsonl").open("a") as stream: stream.write('{"id":"a"}\n')
            with self.assertRaisesRegex(ValueError,"duplicate"):
                A.checked_record_ids(Path(directory,"ours.jsonl"),{"a"})

    def test_unbound_old_records_cannot_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,"orig.jsonl").write_text('{"id":"a"}\n')
            with self.assertRaisesRegex(ValueError,"custody"):
                A.open_run(directory,{"source":"x"})

    def test_output_files_do_not_invalidate_their_own_resume_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest={'implementation_sha256':{'runtime.py':'one'},'git_dirty':False}
            A.open_run(directory,manifest)
            A.open_run(directory,{**manifest,'git_dirty':True})
            saved=json.loads(Path(directory,'run-manifest.json').read_text())
            self.assertFalse(saved['git_dirty'])
            with self.assertRaisesRegex(ValueError,'fingerprint'):
                A.open_run(directory,{'implementation_sha256':{'runtime.py':'two'},'git_dirty':True})

    def test_nonconforming_backend_is_detected_with_unknown_usage(self):
        class Broken(R.MockBackend):
            def generate(self,prompt,n,seed,forced,cap=None,pad_tokens=0):
                return [],"",self.count(prompt)+pad_tokens
        runtime=R.Runtime({"m":Broken(PROFILE)},{},{})
        with self.assertRaises(R.ContractViolation) as caught:
            runtime.run(self.shaped,{0:"a"})
        self.assertTrue(caught.exception.dispatched)
        self.assertFalse(caught.exception.usage_complete)

    def test_input_overflow_refuses_before_dispatch(self):
        backend=R.MockBackend(PROFILE)
        runtime=R.Runtime({"m":backend},{},{})
        with patch.object(backend,"generate",wraps=backend.generate) as generation:
            with self.assertRaises(R.ContractViolation) as caught:
                runtime.run(self.shaped,{0:"x"*1000})
            self.assertFalse(caught.exception.dispatched)
            generation.assert_not_called()

    def test_whole_shape_budget_refuses_before_secret_execution(self):
        backend=R.MockBackend(PROFILE)
        runtime=R.Runtime({"m":backend},{},{},budgets={"m":{"calls":0}})
        with patch.object(backend,"generate",wraps=backend.generate) as generation:
            with self.assertRaisesRegex(R.ContractViolation,"complete workflow shape") as caught:
                runtime.run(self.shaped,{0:"a"})
            self.assertFalse(caught.exception.dispatched)
            generation.assert_not_called()

    def test_model_specific_initial_admission(self):
        backend=R.MockBackend(PROFILE)
        runtime=R.Runtime({"m":backend},{},{},input_contracts={0:{"m":4}})
        with self.assertRaises(R.ContractViolation): runtime.run(self.shaped,{0:"abcde"})
        result=runtime.run(self.shaped,{0:"abcd"})
        self.assertEqual(result.truncations,0)

    def test_wrong_input_usage_and_transport_failure_are_not_zero(self):
        backend=R.MockBackend(PROFILE)
        runtime=R.Runtime({"m":backend},{},{})
        for response in (([1]*12,"x",999),RuntimeError("lost response")):
            with patch.object(backend,"generate",side_effect=response if isinstance(response,Exception) else None,
                              return_value=response):
                with self.assertRaises(R.ContractViolation) as caught: runtime.run(self.shaped,{0:"a"})
                self.assertFalse(caught.exception.usage_complete)

    def test_tool_arguments_preserve_delimiters_and_backslashes(self):
        source=SOURCE.replace(b"let r = call p(q) using m max_tokens 12;",b"tool echo(x) max_tokens 100; let r = tool echo(q);")
        program,_=A.source_binding(source,PROFILES)
        runtime=R.Runtime({"m":R.MockBackend(PROFILE)},{"echo":lambda x:x},{})
        for value in ("x\x1fy",r"a\s\b",r"a\\b",""):
            result=runtime.run(program.body,{0:value})
            self.assertEqual(result.store[program.output],value)

    def test_failure_evidence_retains_unknown_reservation_and_rejects_budget_typos(self):
        from experiments.run_workflow import failure_record
        backend=R.MockBackend(PROFILE)
        with self.assertRaisesRegex(ValueError,'budget names'):
            R.Runtime({'m':backend},{},{},budgets={'typo':{'calls':1}})
        runtime=R.Runtime({'m':backend},{},{})
        with patch.object(backend,'generate',side_effect=RuntimeError('lost response')):
            with self.assertRaises(R.ContractViolation) as caught:runtime.run(self.shaped,{0:'a'})
        failure=failure_record('id','ours',caught.exception,runtime)
        self.assertFalse(failure['usage_complete'])
        self.assertEqual(len(failure['usage']['unconfirmed']),1)
        self.assertGreater(failure['usage']['unconfirmed'][0]['reservation']['output'],0)

    def test_empty_artifact_cannot_claim_validation_success(self):
        artifact=dict(schema='orchlang-validation-artifact-v1',source_binding=self.binding,
                      model_contracts={},candidates={})
        with patch.object(A,'model_contracts',return_value={}):
            with self.assertRaisesRegex(ValueError,'nonempty'):
                A.check_artifact(SOURCE,PROFILES,artifact)


if __name__=="__main__": unittest.main()
