import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchlang import admission as B, assurance as A, compiler as K, core as C, runtime as R
from orchlang.models import Profile, Template, TEMPLATES, CharTokenizer

TEMPLATES.setdefault("round3-mock", Template("round3-mock", None, "<{role}>{content}</>\n", "<a>", "<pad>", "</>\n"))
PROFILE = Profile("m", "", "round3-mock", filler=".")
PROFILES = {"m": PROFILE}
SOURCE = b'''workflow W { input q: text secret max_tokens 4; model m = "m";
prompt p(x) = user "{x}"; let r = call p(q) using m max_tokens 3; output r; }'''
ROOT = Path(__file__).resolve().parents[1]
LEAN = os.environ.get("LEAN") or shutil.which("lean")


class LossyBackend(R.MockBackend):
    """A tokenizer that drops its last character violates segmentation."""
    def encode(self, text):
        return [ord(c) for c in text[:-1]]


class Round3(unittest.TestCase):
    def setUp(self):
        self.program, _ = A.source_binding(SOURCE, PROFILES)
        self.contract = B.byte_contract(self.program, response_bytes_per_token=4, context=4096)
        self.candidate = B.certified_shaper(self.program, PROFILES, {"m": CharTokenizer()}, self.contract)

    def test_segmentation_receipt_on_character_tokenizer(self):
        receipt = B.segmentation_receipt(R.MockBackend(PROFILE), "<user>é漢🚀</>\n<a>")
        self.assertTrue(receipt["segmented"])
        self.assertTrue(receipt["bound_holds"])
        self.assertLess(receipt["tokens"], receipt["bytes"])

    def test_segmentation_violation_refuses_before_dispatch(self):
        runtime = B.ByteBoundedRuntime({"m": LossyBackend(PROFILE)}, {}, {}, byte_contract=self.contract)
        with self.assertRaisesRegex(R.ContractViolation, "segmentation"):
            runtime.run(self.candidate, {self.program.slots["q"]: "ab"}, 0)
        self.assertEqual(runtime.ledger.snapshot()["confirmed"], {})

    def test_bounded_execution_records_segmentation(self):
        runtime = B.ByteBoundedRuntime({"m": R.MockBackend(PROFILE)}, {}, {}, byte_contract=self.contract)
        result = runtime.run(self.candidate, {self.program.slots["q"]: "ab"}, 0)
        audits = [event.audit for event in result.trace if event.kind == "llm"]
        self.assertTrue(audits and all(a["segmentation"]["segmented"] for a in audits))

    def test_python_escape_matches_lean_character_definition(self):
        def lean_escape(text):
            return "".join("\\\\" if c == "\\" else "\\s" if c == "\x1f" else c for c in text)
        for text in ["", "plain", "a\\b", "\x1f\\\x1f", "é\\ü\x1f€", "🚀\\"]:
            self.assertEqual(C.escape_tool_arg(text), lean_escape(text))

    @unittest.skipUnless(LEAN, "Lean executable not configured")
    def test_astral_literals_cross_the_lean_boundary(self):
        program = C.Call(1, 0, "m", C.EApp(C.ELit("rocket 🚀 "), C.EVar(0)), (64, 4), 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "programs.json"
            path.write_text(json.dumps([C.stmt_json(program)], ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([LEAN, "--run", str(ROOT / "proof/ShapeCore.lean"), "roundtrip", str(path)],
                                    capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), [C.stmt_json(program)])


if __name__ == "__main__":
    unittest.main()
