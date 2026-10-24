"""Unit tests for the OrchLang v2 compiler and runtime (mock backend)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import compiler as K, core as C, runtime as R, syntax as S  # noqa: E402
from orchlang.models import Profile, Template, TEMPLATES  # noqa: E402

TEMPLATES.setdefault("mock", Template("mock", None, "<{role}>{content}</>\n", "<a>", "<pad>", "</>\n"))
PROFILES = {"m": Profile("m", "", "mock", filler="."), "big": Profile("big", "", "mock", filler=".")}


class CharTok:
    def count(self, s):
        return len(s)


TOKS = {"m": CharTok(), "big": CharTok()}

ROUTER = """
workflow Router {
  input q: text secret max_tokens 20;
  input mode: text public max_tokens 4;
  model small = "m";
  model large = "big";
  tool first_word(x) max_tokens 3;
  prompt route(x) = user "route {x}";
  prompt a(x) = user "A {x}";
  prompt b(x) = user "B {x}";
  prompt hello() = user "hello";
  let greet = call hello() using small max_tokens 5;
  let raw = call route(q) using small max_tokens 3;
  let lab = tool first_word(raw);
  if lab == "a" {
    let out = call a(q) using small max_tokens 8;
  } else {
    let tmp = call b(q) using large max_tokens 6;
    let out = call b(tmp) using small max_tokens 4;
  }
  repeat 2 until lab == "done" {
    let lab = tool first_word(out);
  }
  output out;
}
"""


def compile_router():
    prog = K.lower(S.parse(ROUTER), PROFILES)
    return prog


class Frontend(unittest.TestCase):
    def test_labels(self):
        prog = compile_router()
        names = {prog.names[x] for x in prog.high_vars()}
        self.assertEqual(names, {"q", "raw", "lab", "out", "tmp"})
        self.assertEqual(prog.gamma[prog.slots["greet"]], C.LOW)

    def test_detects_leaks(self):
        kinds = {f.kind for f in K.detect(compile_router())}
        self.assertIn("secret-dependent-branch", kinds)
        self.assertIn("secret-dependent-size", kinds)
        self.assertIn("secret-dependent-loop", kinds)

    def test_errors(self):
        bad = {
            "E202": 'workflow W { input q: text secret max_tokens 2; output z; }',
            "E222": 'workflow W { input q: text secret max_tokens 2; model m = "m"; prompt p(x) = user "{y}"; '
                    'let r = call p(q) using m max_tokens 1; output r; }',
            "E221": 'workflow W { input q: text secret max_tokens 2; model m = "m"; prompt p(x) = user "{x}"; '
                    'let r = call p() using m max_tokens 1; output r; }',
            "E241": 'workflow W { input q: text secret max_tokens 2; prompt p(x) = user "{x}"; '
                    'let r = call p(q) using m max_tokens 1; output r; }',
            "P001": 'workflow W { let }',
        }
        for code, src in bad.items():
            with self.assertRaises(S.OrchError) as cm:
                K.lower(S.parse(src), PROFILES)
            self.assertEqual(cm.exception.code, code, src)


class Shaping(unittest.TestCase):
    def test_all_strategies_satisfy_discipline(self):
        prog = compile_router()
        for s in ["ours", "naive", "uniform", "padall"]:
            shaped = K.Shaper(prog, PROFILES, TOKS, s).run()
            self.assertTrue(C.wt(prog.gamma, C.LOW, shaped), s)
            self.assertEqual(K.static_cost(C.Ite(C.Guard("eq", 0, ""), shaped, shaped)), K.static_cost(shaped))

    def test_ours_cheaper_than_naive(self):
        prog = compile_router()
        ours = K.Shaper(prog, PROFILES, TOKS, "ours").run()
        naive = K.Shaper(prog, PROFILES, TOKS, "naive").run()
        sub = lambda s: [c for c in C.flatten(s) if isinstance(c, C.Ite)][0]
        co, cn = K.static_cost(sub(ours)), K.static_cost(sub(naive))
        self.assertLess(co[0], cn[0])

    def test_models_never_merge(self):
        prog = compile_router()
        ours = K.Shaper(prog, PROFILES, TOKS, "ours").run()
        ite = [c for c in C.flatten(ours) if isinstance(c, C.Ite)][0]
        models = [e[1] for e in C.shape(ite) if e[0] == "llm"]
        self.assertEqual(models, ["big", "m"])  # small call merges with small call


class Runtime(unittest.TestCase):
    def setUp(self):
        self.rt = R.Runtime({k: R.MockBackend(p) for k, p in PROFILES.items()},
                            {"first_word": lambda x: x[:1]}, {"first_word": 3})

    def test_noninterference_and_preservation(self):
        prog = compile_router()
        ours = K.Shaper(prog, PROFILES, TOKS, "ours").run()
        traces = set()
        for secret in ["a", "b", "zzzz", "", "abcabcabcabcabc"]:
            r = self.rt.run(ours, {0: secret, 1: "x"}, run_seed=3)
            traces.add(tuple(r.observed()))
            o = self.rt.run(prog.body, {0: secret, 1: "x"}, run_seed=3)
            self.assertEqual(o.store, r.store)
        self.assertEqual(len(traces), 1)

    def test_original_leaks(self):
        prog = compile_router()
        traces = {tuple(self.rt.run(prog.body, {0: s, 1: "x"}, run_seed=3).observed()) for s in ["a", "b", "zz"]}
        self.assertGreater(len(traces), 1)

    def test_padder_exact(self):
        from dataclasses import replace
        req = PROFILES["m"].tmpl.render([("user", "x" * 30)])
        inband = R.Padder(R.MockBackend(replace(PROFILES["m"], pad_mode="inband")))
        for target in [20, 25, 40, 80]:
            out, iso, trunc = inband.pad(req, target)
            self.assertEqual((len(out), iso), (target, 0))
            self.assertEqual(trunc, len(req) + 10 > target)
        isolated = R.Padder(R.MockBackend(PROFILES["m"]))
        for target in [20, 25, 40, 80]:
            out, iso, trunc = isolated.pad(req, target)
            self.assertEqual(len(out) + iso, target)
            self.assertEqual(trunc, len(req) > target)
            if not trunc:
                self.assertEqual(out, req)


if __name__ == "__main__":
    unittest.main()


MODELS_JSON = os.environ.get("ORCHLANG_MODELS")


@unittest.skipUnless(MODELS_JSON and os.path.exists(MODELS_JSON), "model files not configured")
class RealTemplates(unittest.TestCase):
    """Chat rendering must match each GGUF's own Jinja template byte for byte."""

    def test_templates_match_gguf(self):
        import jinja2
        from llama_cpp import Llama
        from orchlang import models as M
        for key, prof in M.load_profiles(MODELS_JSON).items():
            if not os.path.exists(prof.gguf):
                continue
            m = Llama(model_path=prof.gguf, vocab_only=True, verbose=False)
            env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True).from_string(
                m.metadata["tokenizer.chat_template"])
            bos = "<|begin_of_text|>" if prof.template == "llama3" else ""
            for msgs in [[("system", "Be brief."), ("user", "  Hi\n ")], [("user", "x")], [("system", "S"), ("user", "a\nb")]]:
                ref = env.render(messages=[{"role": r, "content": c} for r, c in msgs],
                                 add_generation_prompt=True, bos_token=bos, eos_token="")
                self.assertEqual(ref, prof.tmpl.render(msgs), key)

    def test_padding_exact_with_real_tokenizer(self):
        from dataclasses import replace
        from orchlang import models as M
        for key, prof in M.load_profiles(MODELS_JSON).items():
            if not os.path.exists(prof.gguf):
                continue
            tok = M.tokenizer_for(prof.gguf)

            class B:
                profile = prof
                count = staticmethod(tok.count)
                encode_plain = staticmethod(tok.encode_plain)
                decode = staticmethod(tok.decode)
            req = prof.tmpl.render([("system", "Classify."), ("user", "Café résumé 你好 " * 20)])
            for mode in ("inband", "isolated"):
                B.profile = replace(prof, pad_mode=mode)
                pad = R.Padder(B())
                for target in [60, 100, 150, 400]:
                    out, iso, _ = pad.pad(req, target)
                    self.assertEqual(tok.count(out) + iso, target, (key, mode, target))
