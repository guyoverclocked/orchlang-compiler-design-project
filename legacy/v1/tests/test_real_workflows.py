"""Dependency-free regression tests for real-workflow kernel/data admission."""
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.workflow_kernels import Kernel
from runtime.local_model import LocalModel, AdmissionError, render_messages
from runtime.workflow_tape import CapturedTape


class TextBackend:
    def __init__(self):
        self.requests = []

    def generate(self, *, prompt, schema, upstream_cap):
        self.requests.append(prompt)
        return "bound{" + str(len(self.requests)) + "}"


class RealWorkflowTests(unittest.TestCase):
    def test_actual_response_binding_and_one_pass_substitution(self):
        source = '''workflow W budget 1000 {
          input value: text max_tokens 20;
          model m = mock("deployment") max_tokens 10;
          prompt a(x: text) -> text = "first:{x}";
          prompt b(x: text) -> text = "next:{x}";
          let first: text = call a(value) using m;
          let last: text = call b(first) using m;
          output last;
        }'''
        backend = TextBackend()
        self.assertEqual(Kernel(source).run({"value":"{x}"}, backend), "bound{2}")
        self.assertEqual(backend.requests, ["first:{x}", "next:bound{1}"])

    def test_refine_kernel_uses_first_actual_response(self):
        kernel = Kernel((ROOT/"bench/corpus/faithful-local-v1/refine.orch").read_text())
        backend = TextBackend()
        kernel.run({"joke":"initial"}, backend)
        self.assertIn("adding wordplay: initial", backend.requests[0])
        self.assertIn("surprising twist to this joke: bound{1}", backend.requests[1])
        self.assertNotIn("surprising twist to this joke: initial", backend.requests[1])

    def test_malformed_and_unsupported_source_rejected(self):
        for body in ["if flag { }", 'input x: text max_tokens 1; output x; garbage',
                     'input x: text max_tokens 1; output x; @']:
            with self.assertRaises(ValueError):
                Kernel("workflow W budget 1 { " + body + " }")

    def test_explicit_chat_serialization(self):
        self.assertEqual(render_messages([{"role":"system","content":"S"},
                                         {"role":"user","content":"U"}]),
            "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nU<|im_end|>\n<|im_start|>assistant\n")

    def fake_model(self):
        model = LocalModel.__new__(LocalModel)
        class Tokenizer:
            def encode(self, text, add_special_tokens):
                return type("Encoding", (), {"ids":list(text.encode())})()
        model.tokenizer, model.lock, model.model = Tokenizer(), threading.RLock(), "fake"
        def forbidden(*args, **kwargs):
            raise AssertionError("admission must happen before model I/O")
        model.api = forbidden
        model.begin(input_cap=3, output_cap=2, max_calls=1, seed=1)
        return model

    def test_fully_constructed_request_admission_before_io(self):
        model = self.fake_model()
        with self.assertRaises(AdmissionError):
            model.generate(prompt="long")
        self.assertEqual(model.attempts, 0)

    def test_call_limit_admission_before_io(self):
        model = self.fake_model()
        model.attempts = 1
        with self.assertRaises(AdmissionError):
            model.generate(prompt="ok")

    def test_invalid_output_caps_never_dispatch(self):
        for value in (0,-1,0.5,False,True,"2"):
            model=self.fake_model()
            with self.subTest(value=value), self.assertRaises(ValueError):
                model.generate(prompt="ok",upstream_cap=value)
            self.assertEqual(model.attempts,0)

    def test_post_dispatch_transport_failure_has_unknown_usage(self):
        model=self.fake_model()
        def fail(*args):
            raise TimeoutError("simulated transport timeout")
        model.api=fail
        with self.assertRaises(TimeoutError):
            model.generate(prompt="ok")
        totals=model.totals()
        self.assertEqual(totals["calls"],1)
        self.assertFalse(totals["usage_complete"])
        self.assertIsNone(totals["input"])
        self.assertIsNone(totals["output"])
        self.assertEqual(totals["usage_unconfirmed_attempts"],1)

    def test_server_accounting_mismatch_rejected_and_recorded(self):
        model = self.fake_model()
        model.api = lambda *args: dict(response="x", prompt_eval_count=99, eval_count=1,
                                       done_reason="stop")
        with self.assertRaisesRegex(ValueError, "count disagreement"):
            model.generate(prompt="ok")
        self.assertEqual(model.trace[0]["status"], "error")
        self.assertEqual(model.attempts, 1)

    def test_generated_cap_violation_rejected_and_recorded(self):
        model = self.fake_model()
        model.api = lambda *args: dict(response="x", prompt_eval_count=2, eval_count=3,
                                       done_reason="length")
        with self.assertRaisesRegex(ValueError, "output cap violated"):
            model.generate(prompt="ok")
        self.assertEqual(model.trace[0]["status"], "error")

    def test_replay_checks_complete_request_and_consumption(self):
        event=dict(status="ok", rendered_request="exact", schema=None, output_cap=2,response="real")
        tape=CapturedTape([event],output_cap=2)
        with self.assertRaisesRegex(ValueError,"does not exactly match"):
            tape.generate(prompt="changed")
        with self.assertRaisesRegex(ValueError,"omitted"):
            tape.finish()
        self.assertEqual(tape.generate(prompt="exact"),"real")
        self.assertEqual(tape.finish()["actual_generation_calls"],0)

    def test_replay_checks_schema_and_effective_cap(self):
        event=dict(status="ok",rendered_request="exact",schema={"type":"object"},output_cap=2,response="{}")
        tape=CapturedTape([event],output_cap=2)
        with self.assertRaises(ValueError):
            tape.generate(prompt="exact",schema=None)
        with self.assertRaises(ValueError):
            tape.generate(prompt="exact",schema={"type":"object"},upstream_cap=1)

    def test_replay_is_ordered_except_explicit_parallel_declaration(self):
        events=[dict(status="ok",rendered_request=x,schema=None,output_cap=2,response=x)
                for x in ("first","second")]
        ordered=CapturedTape(events,output_cap=2)
        with self.assertRaises(ValueError):
            ordered.generate(prompt="second")
        parallel=CapturedTape(events,output_cap=2,allow_reorder=True)
        self.assertEqual(parallel.generate(prompt="second"),"second")
        self.assertEqual(parallel.generate(prompt="first"),"first")
        self.assertTrue(parallel.finish()["all_original_calls_consumed"])


if __name__ == "__main__":
    unittest.main()
