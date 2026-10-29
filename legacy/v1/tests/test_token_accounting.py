"""Optional real-tokenizer integration tests (set ORCHLANG_TOKENIZER_DIR).

The stdlib-only suite reports a skip when the external pinned tokenizer artifacts
and tokenizers==0.21.4 are not available; it never substitutes another tokenizer.
"""
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from runtime.finite_reference import canonical, Unsupported
from runtime.replay_adapter import enumerate_replay
from runtime.token_accounting import (PinnedTokenizer, StaticAccounting, ExactReplay,
                                      replay_contract, utf8_size, analyze_source)

ARTIFACTS = os.environ.get("ORCHLANG_TOKENIZER_DIR")
AVAILABLE = bool(ARTIFACTS) and importlib.util.find_spec("tokenizers") is not None


class UTF8ContractTests(unittest.TestCase):
    def test_utf8_is_strict_and_counts_bytes(self):
        self.assertEqual(utf8_size("é🙂"),6)
        with self.assertRaises(UnicodeEncodeError):
            utf8_size("\ud800")
        with self.assertRaises(ValueError):
            utf8_size(True)


@unittest.skipUnless(AVAILABLE,"requires ORCHLANG_TOKENIZER_DIR and tokenizers==0.21.4")
class ExactAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(ARTIFACTS)
        cls.manifest = {e["id"]:e for e in json.loads((cls.directory/"manifest.json").read_text())}

    def tokenizer(self,family="gpt2-bpe",specials=False):
        record = self.manifest[family]
        return PinnedTokenizer.from_file(self.directory/record["file"],record["sha256"],
                                         add_special_tokens=specials)

    @staticmethod
    def call(request="hello",bind="a",model="m"):
        return dict(kind="call",request=request,bind=bind,model=model)

    def test_hash_version_and_contract_identity_are_enforced(self):
        path = self.directory/self.manifest["gpt2-bpe"]["file"]
        with self.assertRaises(Unsupported):
            PinnedTokenizer.from_file(path,"0"*64)
        with self.assertRaises(Unsupported):
            PinnedTokenizer.from_file(path,self.manifest["gpt2-bpe"]["sha256"],"0.0.0")
        t = self.tokenizer()
        c = replay_contract(t,"unit",8)
        c["tokenizer"] = "utf8-bytes-v1"
        with self.assertRaises(Unsupported):
            StaticAccounting(t,{"m":c})
        with self.assertRaises(Unsupported):
            ExactReplay(t,{"m":c},{})

    def test_plain_and_special_counts_bert(self):
        plain,special = self.tokenizer("bert-wordpiece"),self.tokenizer("bert-wordpiece",True)
        self.assertEqual(special.count(""),2)
        self.assertEqual(plain.count(""),0)
        self.assertEqual(special.count("hello"),plain.count("hello")+2)
        with self.assertRaises(Unsupported):
            plain.bound_utf8_bytes(10)
        with self.assertRaises(Unsupported):
            special.bound_utf8_bytes(10)

    def test_complete_concat_uses_exact_encoding(self):
        for family in ("gpt2-bpe","bert-wordpiece"):
            t = self.tokenizer(family)
            c = replay_contract(t,"unit",3)
            program = [self.call({"concat":["hel","lo"]})]
            bound = StaticAccounting(t,{"m":c}).analyze(program)
            self.assertEqual(bound.input_tokens,t.count("hello"))
            self.assertNotEqual(bound.input_tokens,t.count("hel")+t.count("lo"))
        # Summing pieces is not even an upper bound, for either family.
        for family,left,right in (("gpt2-bpe","hello","world"),
                                  ("bert-wordpiece","a","world")):
            t = self.tokenizer(family)
            self.assertGreater(t.count(left+right),t.count(left)+t.count(right))

    def test_dynamic_byte_contracts_bound_response_dependent_chain(self):
        t = self.tokenizer()
        c = replay_contract(t,"unit",4)
        program = [self.call({"concat":["Seed:",{"var":"x"}]},"first"),
                   self.call({"concat":["Next:",{"var":"first"}]},"second")]
        contracts,kernels = {"m":c},{canonical(c):{"*":[dict(text="é🙂",p="1",status="ok")]}}
        bound = StaticAccounting(t,contracts,{"x":8},{"m":6}).analyze(program)
        self.assertEqual(asdict(bound),dict(input_tokens=24,output_tokens=8,total_tokens=32,calls=2))
        adapter = ExactReplay(t,contracts,kernels,{"x":8},{"m":6},bound.total_tokens)
        result = adapter.run(program,{"x":"你好"},[0,0])
        self.assertEqual(result["requests"],("Seed:你好","Next:é🙂"))
        self.assertLessEqual(result["usage"]["total_tokens"],bound.total_tokens)
        with self.assertRaises(ValueError):
            adapter.run(program,{"x":"你"*3},[0,0])
        with self.assertRaises(Unsupported):
            StaticAccounting(t,contracts,{"x":8}).analyze(program)

    def test_token_cap_does_not_imply_a_byte_cap(self):
        t = self.tokenizer("bert-wordpiece")
        # BERT removes these control characters: zero encoded tokens can carry
        # arbitrarily many raw UTF-8 bytes. No cap->byte conversion is inferred.
        self.assertEqual(t.count("\x00"*4096),0)
        c = replay_contract(t,"unit",0)
        program = [self.call("hello","first"),self.call({"var":"first"})]
        with self.assertRaises(Unsupported):
            StaticAccounting(t,{"m":c}).analyze(program)

    def test_output_caps_cover_all_alternatives_including_errors(self):
        t = self.tokenizer()
        c = replay_contract(t,"unit",1)
        outcomes = [dict(text="x",p="1/2",status="ok"),dict(text="你好世界",p="1/2",status="error")]
        with self.assertRaises(ValueError):
            ExactReplay(t,{"m":c},{canonical(c):{"*":outcomes}})
        c = replay_contract(t,"unit",32)
        with self.assertRaises(ValueError):
            ExactReplay(t,{"m":c},{canonical(c):{"*":outcomes}},response_byte_caps={"m":1})

    def test_retry_all_attempts_and_branch_max(self):
        t = self.tokenizer()
        c = replay_contract(t,"unit",4)
        outcomes = [dict(text="x",p="1/2",status="ok"),dict(text="",p="1/2",status="error")]
        body = [self.call("hello")]
        program = [dict(kind="if",guard="g",then=[dict(kind="retry",bound=3,body=body)],
                        **{"else":[self.call("hello world")]})]
        bound = StaticAccounting(t,{"m":c}).analyze(program)
        self.assertEqual(bound.total_tokens,15)
        self.assertEqual(bound.calls,3)
        adapter = ExactReplay(t,{"m":c},{canonical(c):{"*":outcomes}},budget_tokens=15)
        paths = enumerate_replay(adapter,program,{"g":True})
        self.assertEqual(len(paths),4)
        self.assertEqual(max(p["usage"]["calls"] for p in paths),3)
        self.assertTrue(all(p["usage"]["total_tokens"] <= bound.total_tokens for p in paths))
        all_fail = next(p for p in paths if p["usage"]["output_tokens"] == 0)
        self.assertEqual(all_fail["usage"]["input_tokens"],3)

    def test_admission_precedes_dispatch_and_preserves_trace(self):
        t = self.tokenizer()
        c = replay_contract(t,"unit",4)
        kernels = {canonical(c):{"*":[dict(text="x",p="1",status="ok")]}}
        adapter = ExactReplay(t,{"m":c},kernels,budget_tokens=4)
        with self.assertRaises(ValueError):
            adapter.run([self.call("hello")],{},[0])
        self.assertEqual(adapter.trace,[])
        adapter = ExactReplay(t,{"m":c},kernels,max_request_tokens=0)
        with self.assertRaises(ValueError):
            adapter.run([self.call("hello")],{},[0])
        self.assertEqual(adapter.trace,[])

    def test_runtime_only_dynamic_bert_has_no_static_bound(self):
        from scripts.exact_tokenizer import execute_case
        t = self.tokenizer("bert-wordpiece")
        root = Path(__file__).resolve().parents[1]
        case = json.loads((root/"bench/exact/dynamic-chain.json").read_text(encoding="utf-8"))
        result = execute_case(case,t,runtime_only=True)
        self.assertIsNone(result["static_bound"])
        self.assertEqual(result["accounting_mode"],"runtime-admission")
        self.assertEqual(len(result["paths"]),4)
        with self.assertRaises(Unsupported):
            execute_case(case,t)
        case["budget_tokens"] = 0
        with self.assertRaises(ValueError):
            execute_case(case,t,runtime_only=True)
        case.pop("budget_tokens")
        with self.assertRaises(ValueError):
            execute_case(case,t,runtime_only=True)

    def test_truncation_and_padding_are_disabled(self):
        import tokenizers
        original = tokenizers.Tokenizer.from_file(str(self.directory/self.manifest["bert-wordpiece"]["file"]))
        original.enable_truncation(max_length=3)
        original.enable_padding(length=12)
        data = original.to_str().encode("utf-8")
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"policy.json"
            path.write_bytes(data)
            t = PinnedTokenizer.from_file(path,hashlib.sha256(data).hexdigest())
            self.assertFalse(t.provenance()["padding"])
            self.assertFalse(t.provenance()["truncation"])
            self.assertGreater(t.count("hello world "*100),3)

    def test_actual_source_counts_complete_substituted_requests(self):
        source = ('workflow W budget 11 { secret flag:boolean max_tokens 1; '
                  'model m=mock("x") max_tokens 8; '
                  'prompt p(a:text,b:text)->text="{a}{b}"; '
                  'if flag { let x:text=call p("hello","world") using m; } '
                  'else { let y:text=call p("hello"," world") using m; } output "done"; }').encode()
        t = self.tokenizer()
        result = analyze_source(source,t)
        self.assertEqual(result["static_bound"]["input_tokens"],3)
        self.assertEqual(result["static_bound"]["total_tokens"],11)
        self.assertTrue(result["within_budget"])
        self.assertEqual([c["exact_input_tokens"] for c in result["calls"]],[3,2])
        self.assertEqual(result["calls"][0]["source_contract"]["tokenizer"],"utf8-bytes-v1")
        self.assertNotEqual(result["tokenizer"]["identity"],"utf8-bytes-v1")
        self.assertFalse(analyze_source(source.replace(b"budget 11",b"budget 10"),t)["within_budget"])
        dynamic = source.replace(b'secret flag:boolean',b'input text_input:text max_tokens 8; secret flag:boolean')
        with self.assertRaisesRegex(Unsupported,"only closed requests"):
            analyze_source(dynamic,t)


if __name__ == "__main__":
    unittest.main()
