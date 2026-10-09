"""Tests for the fail-closed OrchLang source-to-request-graph bridge."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orchgraph import Graph, reference_run, strict_json
from relational_stress import FAMILIES, build_case, public_scenarios, secret_assignments
from source_to_graph import BridgeError, source_reference_run, translate_file, translate_text
import source_to_graph


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "orchc"


CHAIN = '''workflow BridgeChain budget 100000 {
  input query: text max_tokens 64;
  secret choose: boolean;
  model worker = mock("bridge-worker") max_tokens 12 cost_per_token 0.002;
  prompt process(value: text) -> text = "Process {value}";
  if choose {
    let first: text = call process(query) using worker;
    let second: text = call process(first) using worker;
  } else {
    let head: text = call process(query) using worker;
    let tail: text = call process(head) using worker;
  }
  output "fixed";
}
'''


SHADOWED_ALIAS = '''workflow ShadowAlias budget 100000 {
  input query: text max_tokens 64;
  secret route: boolean;
  prompt process(value: text) -> text = "R:{value}";
  if route {
    model m = mock("same-contract") max_tokens 9;
    let current: text = call process(query) using m;
    if tokens(current) <= 9 {
      let current: text = call process(current) using m;
    } else {
      let tail: text = call process(current) using m;
    }
  } else {
    model m = mock("same-contract") max_tokens 9;
    let current: text = call process(query) using m;
    if tokens(current) <= 9 {
      let tail: text = call process(current) using m;
    } else {
      let current: text = call process(current) using m;
    }
  }
  output "fixed";
}
'''


class SourceToGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not COMPILER.is_file():
            raise RuntimeError("build orchc before running bridge tests")

    def translate(self, source: str):
        directory = tempfile.TemporaryDirectory(prefix="orchlang-bridge-test-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        source_path = root / "input.orch"
        graph_path = root / "graph.json"
        sidecar_path = root / "graph.provenance.json"
        source_path.write_text(source, encoding="utf-8")
        graph, sidecar = translate_file(source_path, graph_path,
                                        sidecar_path=sidecar_path,
                                        compiler_path=COMPILER)
        return source_path, graph_path, sidecar_path, graph, sidecar

    @staticmethod
    def graph_store(sidecar: dict, source_store: dict):
        return {item["graph_name"]: source_store[item["source_name"]]
                for item in sidecar["mapping"]["inputs"]}

    def assert_differential(self, source: str, sidecar: dict, graph_doc: dict,
                            public_and_secret_stores: list[dict], seeds=(1, 17)) -> None:
        graph = Graph(graph_doc)
        for store in public_and_secret_stores:
            for seed in seeds:
                with self.subTest(store=store, seed=seed):
                    direct = source_reference_run(source, store, seed,
                                                  chars_per_token=graph.divisor)
                    lowered = reference_run(graph, self.graph_store(sidecar, store), seed)
                    self.assertEqual({key: direct[key] for key in ("trace", "stopped")},
                                     lowered)

    def test_balanced_dependent_chain_exports_strict_graph_and_bound_sidecar(self) -> None:
        source_path, graph_path, sidecar_path, graph, sidecar = self.translate(CHAIN)
        graph_raw = graph_path.read_bytes()
        source_raw = source_path.read_bytes()
        certificate_path = Path(str(graph_path) + ".certificate.json")
        certificate_raw = certificate_path.read_bytes()
        self.assertEqual(set(graph), {"format", "version", "name", "chars_per_token",
                                      "inputs", "registers", "models", "states", "entry"})
        self.assertEqual(sidecar["source_sha256"], hashlib.sha256(source_raw).hexdigest())
        self.assertEqual(sidecar["graph_sha256"], hashlib.sha256(graph_raw).hexdigest())
        self.assertEqual(sidecar["certificate_sha256"], hashlib.sha256(certificate_raw).hexdigest())
        self.assertEqual(sidecar["adapter_sha256"],
                         hashlib.sha256((ROOT / "audit/source_to_graph.py").read_bytes()).hexdigest())
        self.assertTrue(sidecar["source_cost_parser_sha256"])
        self.assertTrue(sidecar["compiler_sha256"])
        self.assertEqual(sidecar["semantic_gate"], "orchc check passed before export")
        self.assertEqual(sidecar["graph_checker"]["status"], "accepted")
        self.assertEqual(sidecar["independent_replay"]["status"], "verified")
        self.assertEqual(sidecar["omitted_output"]["text"], "fixed")
        self.assertEqual(sidecar["omitted_output"]["kind"], "literal")
        self.assertEqual(len({v["graph_register"] for v in sidecar["mapping"]["values"]}), 4)
        self.assert_differential(CHAIN, sidecar, graph, [
            {"query": "é🙂", "choose": False},
            {"query": "雪 and text", "choose": True},
            {"query": 'quote " slash \\', "choose": False},
        ])
        first = source_reference_run(CHAIN, {"query": "same public", "choose": False}, 9)
        second = source_reference_run(CHAIN, {"query": "same public", "choose": True}, 9)
        self.assertEqual(first["trace"], second["trace"])

    def test_shadowed_values_and_model_aliases_resolve_lexically(self) -> None:
        _, _, _, graph_doc, sidecar = self.translate(SHADOWED_ALIAS)
        aliases = sidecar["mapping"]["models"]
        self.assertEqual([item["source_name"] for item in aliases], ["m", "m"])
        self.assertNotEqual(aliases[0]["graph_alias"], aliases[1]["graph_alias"])
        self.assertEqual(aliases[0]["contract"], aliases[1]["contract"])
        values = sidecar["mapping"]["values"]
        current_bindings = [item for item in values if item["source_name"] == "current"]
        self.assertEqual(len(current_bindings), 4)
        self.assertEqual(len({item["graph_register"] for item in current_bindings}), 4)
        self.assert_differential(SHADOWED_ALIAS, sidecar, graph_doc, [
            {"query": "café", "route": True},
            {"query": "東京🙂", "route": False},
        ], seeds=(3, 19))

    def test_existing_independent_ast_families_match_full_text_source_and_graph_runs(self) -> None:
        # AST source families are generated independently of this parser and
        # lowering. Each is checked by orchc, the graph producer, and replayer;
        # the direct AST evaluator and graph probe then compare full requests,
        # response text, per-call usage, and stop status.
        for family in FAMILIES:
            if family == "bounded_retry_chain":
                continue  # retry attempt schedules are outside graph v1
            case = build_case(f"source-graph-{family}", 7331, family)
            with self.subTest(family=family):
                _, _, _, graph_doc, sidecar = self.translate(case.source)
                self.assertEqual(sidecar["graph_checker"]["status"], "accepted")
                stores: list[dict] = []
                scenarios = public_scenarios(case.workflow)
                # Empty, ASCII, and varied multi-byte/quoted/newline inputs.
                for scenario_index in (0, 4, 8, 10):
                    public = scenarios[scenario_index]
                    for secret in secret_assignments(case.workflow):
                        stores.append({**public, **secret})
                self.assert_differential(case.source, sidecar, graph_doc, stores,
                                         seeds=(1, 19))
                # Every secret valuation is compared under identical public
                # values and the same deterministic shared-oracle key.
                graph = Graph(graph_doc)
                public = scenarios[8]
                secret_runs = []
                for secret in secret_assignments(case.workflow):
                    store = {**public, **secret}
                    secret_runs.append(reference_run(
                        graph, self.graph_store(sidecar, store), 23))
                for run in secret_runs[1:]:
                    self.assertEqual(secret_runs[0]["trace"], run["trace"])

    def test_unsupported_constructs_fail_closed(self) -> None:
        prefix = '''workflow Refuse budget 1000 {
 input q: text max_tokens 8;
 model m = mock("m") max_tokens 4;
 prompt p(t: text) -> text = "{t}";
'''
        suffix = '\n output "fixed";\n}\n'
        unsupported = (
            " retry 2 { let r: text = call p(q) using m; }\n",
            ' declassify(q) as released: text because "reason";\n',
            " for i in 2 { let r: text = call p(q) using m; }\n",
            ' tool send(value: text); emit send(q);\n',
            " require tokens(q) <= 8;\n",
        )
        for construct in unsupported:
            with self.subTest(construct=construct):
                with self.assertRaises(BridgeError):
                    translate_text(prefix + construct + suffix)

    def test_public_input_output_is_recorded_and_omitted_from_billing_graph(self) -> None:
        source = CHAIN.replace('output "fixed";', "output query;")
        _, _, _, graph_doc, sidecar = self.translate(source)
        omitted = sidecar["omitted_output"]
        self.assertEqual(omitted["kind"], "identifier")
        self.assertEqual(omitted["source_name"], "query")
        self.assertEqual(omitted["type"], "text")
        self.assertEqual(omitted["confidentiality"], "public")
        self.assertEqual(omitted["graph_value_name"], "in_0")
        direct = source_reference_run(source, {"query": "public output", "choose": True}, 3)
        self.assertEqual(direct["output"], "public output")
        self.assert_differential(source, sidecar, graph_doc, [
            {"query": "public output", "choose": True},
            {"query": "é🙂", "choose": False},
        ])

    def test_public_call_result_output_is_recorded_separately(self) -> None:
        source = '''workflow ResultOutput budget 1000 {
  input query: text max_tokens 16;
  model m = mock("result-worker") max_tokens 4;
  prompt p(value: text) -> text = "P:{value}";
  let result: text = call p(query) using m;
  output result;
}
'''
        _, _, _, graph_doc, sidecar = self.translate(source)
        omitted = sidecar["omitted_output"]
        self.assertEqual(omitted["kind"], "identifier")
        self.assertEqual(omitted["source_name"], "result")
        self.assertEqual(omitted["value_kind"], "result")
        self.assertEqual(omitted["graph_value_name"],
                         sidecar["mapping"]["values"][0]["graph_register"])
        direct = source_reference_run(source, {"query": "question"}, 11)
        self.assertEqual(direct["output"], direct["trace"][0]["response"])
        self.assert_differential(source, sidecar, graph_doc,
                                 [{"query": "question"}, {"query": "é🙂"}])

    def test_private_unbound_and_nontext_outputs_are_rejected(self) -> None:
        private = CHAIN.replace('output "fixed";', "output choose;")
        with self.assertRaisesRegex(BridgeError, "must have text type"):
            translate_text(private)
        private_text = CHAIN.replace("secret choose: boolean;",
                                     "secret choose: text max_tokens 2;")
        private_text = private_text.replace("if choose {", "if tokens(choose) <= 1 {")
        private_text = private_text.replace('output "fixed";', "output choose;")
        with self.assertRaisesRegex(BridgeError, "is private"):
            translate_text(private_text)
        with self.assertRaisesRegex(BridgeError, "unbound or not a value"):
            translate_text(CHAIN.replace('output "fixed";', "output missing;") )

    def test_source_probe_enforces_input_request_response_trace_and_call_caps(self) -> None:
        source = '''workflow ProbeCaps budget 10000000 {
  input query: text max_tokens 1200000;
  model m = mock("probe") max_tokens 32;
  prompt p(value: text) -> text = "P:{value}";
  let first: text = call p(query) using m;
  let second: text = call p(query) using m;
  output "done";
}
'''
        oversized = "x" * (source_to_graph.MAX_UTF8_BYTES + 1)
        with self.assertRaisesRegex(BridgeError, "exceeds 1048576 UTF-8 bytes"):
            source_reference_run(source, {"query": oversized}, 1, chars_per_token=1)
        exact_value = "x" * source_to_graph.MAX_UTF8_BYTES
        with self.assertRaisesRegex(BridgeError, "complete request exceeds"):
            source_reference_run(source, {"query": exact_value}, 1, chars_per_token=1)
        with self.assertRaisesRegex(BridgeError, "call limit 1 reached"):
            source_reference_run(source, {"query": "short"}, 1, max_calls=1)

        old_trace_cap = source_to_graph.MAX_PROBE_TRACE_BYTES
        old_control_cap = source_to_graph.MAX_PROBE_CONTROL_STEPS
        try:
            source_to_graph.MAX_PROBE_TRACE_BYTES = 1
            with self.assertRaisesRegex(BridgeError, "reference trace exceeds"):
                source_reference_run(source, {"query": "short"}, 1)
            source_to_graph.MAX_PROBE_TRACE_BYTES = old_trace_cap
            source_to_graph.MAX_PROBE_CONTROL_STEPS = 1
            with self.assertRaisesRegex(BridgeError, "control-step limit"):
                source_reference_run(source, {"query": "short"}, 1)
        finally:
            source_to_graph.MAX_PROBE_TRACE_BYTES = old_trace_cap
            source_to_graph.MAX_PROBE_CONTROL_STEPS = old_control_cap

        response_limit_observed = False
        response_probe = source.replace("input query: text max_tokens 1200000;",
                                       "input query: text max_tokens 1;")
        for seed in range(1, 129):
            try:
                source_reference_run(response_probe, {"query": "x"}, seed,
                                     chars_per_token=40_000)
            except BridgeError as error:
                if "abstract response exceeds" in str(error):
                    response_limit_observed = True
                    break
        self.assertTrue(response_limit_observed,
                        "large divisors must fail before allocating an oversized response")

    def test_nontext_literal_and_unbounded_text_outputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(BridgeError, "final output must be text"):
            translate_text(CHAIN.replace('output "fixed";', "output true;"))
        with self.assertRaisesRegex(BridgeError, "unbounded text input"):
            translate_text(CHAIN.replace("input query: text max_tokens 64;",
                                          "input query: text;"))

    def test_type_erased_nontext_literals_are_rejected(self) -> None:
        source = '''workflow TypedLiteral budget 1000 {
  input query: text max_tokens 8;
  secret route: boolean;
  model m = mock("m") max_tokens 4;
  prompt p(v: text) -> text = "{v}";
  if route {
    let a: text = call p(true) using m;
  } else {
    let b: text = call p("true") using m;
  }
  output "fixed";
}
'''
        # The graph schema contains text atoms only. It cannot preserve the
        # expression-kind distinction used by the source mock for bool/string
        # literals that print as the same bytes.
        with self.assertRaisesRegex(BridgeError, "quoted text literals"):
            translate_text(source)

    def test_compiler_rejection_leaves_no_graph_or_sidecar(self) -> None:
        # Add a locally shadowed prompt in just the else arm.
        bad = CHAIN.replace('    let head: text = call process(query) using worker;',
                            '    prompt process(value: text) -> text = "Changed {value}";\n'
                            '    let head: text = call process(query) using worker;')
        with tempfile.TemporaryDirectory(prefix="orchlang-bridge-reject-") as directory:
            root = Path(directory)
            source_path = root / "bad.orch"
            graph_path = root / "bad.json"
            sidecar_path = root / "bad.provenance.json"
            certificate_path = Path(str(graph_path) + ".certificate.json")
            source_path.write_text(bad, encoding="utf-8")
            with self.assertRaisesRegex(BridgeError, "compiler check gate failed"):
                translate_file(source_path, graph_path, sidecar_path=sidecar_path,
                               compiler_path=COMPILER)
            self.assertFalse(graph_path.exists())
            self.assertFalse(certificate_path.exists())
            self.assertFalse(sidecar_path.exists())

    def test_compiler_gates_the_exact_parsed_source_snapshot(self) -> None:
        original = CHAIN.encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="orchlang-bridge-snapshot-") as directory:
            root = Path(directory)
            source_path = root / "snapshot.orch"
            graph_path = root / "snapshot.json"
            source_path.write_bytes(original)
            real_run = source_to_graph.subprocess.run
            mutated = False

            def change_original_before_compiler(command, *args, **kwargs):
                nonlocal mutated
                if not mutated and Path(command[0]).name == "orchc-snapshot":
                    mutated = True
                    source_path.write_text("this is not the parsed workflow", encoding="utf-8")
                return real_run(command, *args, **kwargs)

            with patch("source_to_graph.subprocess.run", side_effect=change_original_before_compiler):
                _, sidecar = translate_file(source_path, graph_path, compiler_path=COMPILER)
            self.assertTrue(mutated)
            self.assertNotEqual(source_path.read_bytes(), original)
            self.assertEqual(sidecar["source_sha256"], hashlib.sha256(original).hexdigest())
            self.assertTrue(graph_path.is_file())
            self.assertTrue(Path(str(graph_path) + ".certificate.json").is_file())

    def test_parser_rejects_non_utf8_and_source_graph_path_aliasing(self) -> None:
        with self.assertRaisesRegex(BridgeError, "not valid UTF-8"):
            from source_to_graph import parse_source
            parse_source(b"\xff")
        with tempfile.TemporaryDirectory(prefix="orchlang-bridge-paths-") as directory:
            source_path = Path(directory) / "same.orch"
            source_path.write_text(CHAIN, encoding="utf-8")
            with self.assertRaisesRegex(BridgeError, "distinct paths"):
                translate_file(source_path, source_path, compiler_path=COMPILER)


if __name__ == "__main__":
    unittest.main()
