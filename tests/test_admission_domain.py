import unittest
from experiments.admission_domain import observe, study
from orchlang import core as C, models as M, runtime as R


class AdmissionDomain(unittest.TestCase):
    def test_chained_overflow_exposes_a_confirmed_prefix(self):
        class VariableResponse(R.MockBackend):
            def generate(self, prompt, max_tokens, seed, forced, cap=None, pad_tokens=0):
                visible = ("a" if prompt.startswith("a") else "bbbb")[:cap or max_tokens]
                ids = self.encode(visible)
                if forced:
                    ids += [0] * (max_tokens - len(ids))
                return ids, visible, self.count(prompt) + pad_tokens
        backend = VariableResponse(M.Profile("m", "unused", "qwen2"))
        runtime = R.Runtime({"m": backend}, {}, {})
        header = backend.profile.tmpl.generation
        request = lambda slot: C.concat([C.EVar(slot), C.ELit(header)])
        program = C.seq([C.Call(0, 1, "m", request(0), (len(header) + 8, 4), 4),
                         C.Call(1, 2, "m", request(1), (len(header) + 3, 4), 4)])
        completed = observe(runtime, program, {0: "a"}, 0)
        failed = observe(runtime, program, {0: "b"}, 0)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(completed["trace"]), 2)
        self.assertEqual(len(failed["trace"]), 1)
        self.assertEqual(completed["trace"][0], failed["trace"][0])
        self.assertTrue(failed["usage"]["usage_complete"])

    def test_refusal_channel_and_exhaustive_finite_domain(self):
        result = study()
        self.assertEqual([r["status"] for r in result["counterexample"]], ["completed", "refused"])
        self.assertEqual(result["finite_cases"], 45)
        self.assertTrue(result["all_completed_with_static_shape"])
        self.assertEqual(result["counterexample"][1]["usage"]["confirmed"], {})

    def test_unknown_dispatch_is_visible_with_reservation_retained(self):
        class Broken(R.MockBackend):
            def generate(self, *args, **kwargs):
                raise OSError("transport lost after submission")
        backend = Broken(M.Profile("m", "unused", "qwen2"))
        runtime = R.Runtime({"m": backend}, {}, {})
        program = C.Call(0, 1, "m", C.ELit("request"), None, 4)
        result = observe(runtime, program, {}, 0)
        self.assertEqual(result["status"], "unknown_dispatch")
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertTrue(result["usage"]["unconfirmed"])


if __name__ == "__main__":
    unittest.main()
