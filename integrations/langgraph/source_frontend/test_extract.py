"""Regression tests for the fail-closed LangGraph source AST subset."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "audit"))

from orchgraph import Graph, check  # noqa: E402
from integrations.langgraph.source_frontend.extract import (  # noqa: E402
    FrontendError,
    extract_source,
    parse_contracts,
)
from integrations.langgraph.source_frontend.export import (  # noqa: E402
    _canonical,
    _read_bounded,
    _write_atomic,
    export_bytes,
)
import hashlib  # noqa: E402
from integrations.langgraph.source_frontend import study as source_study  # noqa: E402


HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"


def _read_fixture(name: str) -> tuple[bytes, bytes]:
    return ((EXAMPLES / f"{name}.py").read_bytes(),
            (EXAMPLES / f"{name}.contracts.json").read_bytes())


def _document(source: str, contracts: dict | None = None) -> tuple[bytes, bytes]:
    if contracts is None:
        contracts = {
            "format": "orchlang-langgraph-contracts",
            "version": 1,
            "name": "small_case",
            "inputs": {"query": {"type": "text", "label": "public", "max_tokens": 64}},
            "models": {"m": {"provider": "mock", "model": "canonical", "max_tokens": 8}},
        }
    return source.encode("utf-8"), json.dumps(contracts, ensure_ascii=False).encode("utf-8")


PRELUDE = '''from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from integrations.langgraph.source_frontend.runtime import request, tokens
'''


class SourceFrontendTests(unittest.TestCase):
    def test_secret_branch_dependent_chain_extracts_to_accepted_graph(self) -> None:
        source, contracts = _read_fixture("secret_dependent_chain")
        graph, mapping = extract_source(source, contracts)
        result = check(Graph(graph))
        self.assertEqual(result["status"], "accepted", result.get("diagnostic"))
        self.assertEqual(len(mapping["routers"]), 2)
        self.assertEqual({item["guard_source_field"] for item in mapping["routers"]},
                         {"private_route", "public_mode"})
        calls = [call for state in graph["states"].values() for call in state["calls"]]
        self.assertEqual(len(calls), 4)
        final_calls = [call for call in calls if call["template"] == "answer-v2"]
        self.assertEqual(len(final_calls), 2)
        self.assertEqual(final_calls[0]["arguments"][0], final_calls[1]["arguments"][0])
        self.assertEqual(final_calls[0]["arguments"][1], {"literal": "suffix"})

    def test_productive_cycle_extracts_and_checks(self) -> None:
        source, contracts = _read_fixture("productive_cycle")
        graph, mapping = extract_source(source, contracts)
        result = check(Graph(graph))
        self.assertEqual(result["status"], "accepted", result.get("diagnostic"))
        state = graph["states"][graph["entry"]]
        self.assertEqual(state["next"]["kind"], "public")
        self.assertEqual(state["next"]["then"], graph["entry"])
        self.assertEqual(mapping["nodes"][0]["source_node"], "generate")

    def test_secret_argument_is_rejected_before_graph_generation(self) -> None:
        source, contracts = _read_fixture("rejected_secret_argument")
        with self.assertRaisesRegex(FrontendError, "direct secret input"):
            extract_source(source, contracts)

    def test_atomic_state_update_hazard_is_rejected(self) -> None:
        source, contracts = _read_fixture("rejected_atomic_update")
        with self.assertRaisesRegex(FrontendError, "applies returned state updates atomically"):
            extract_source(source, contracts)

    def test_result_read_before_any_writer_is_rejected(self) -> None:
        source = PRELUDE + '''
class State(TypedDict):
    query: str
    result: str
def choose(state):
    return {}
def generate(state):
    answer = request(model="m", template="go", arguments=[state["query"]])
    return {"result": answer}
def route(state):
    if tokens(state["result"]) > 3:
        return "yes"
    return "no"
builder = StateGraph(State)
builder.add_node("choose", choose)
builder.add_node("generate", generate)
builder.add_edge(START, "choose")
builder.add_conditional_edges("choose", route, {"yes": "generate", "no": "generate"})
builder.add_edge("generate", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "before a writer"):
            extract_source(*_document(source))

    def test_atomic_result_register_write_is_visible_only_to_local_result(self) -> None:
        source = PRELUDE + '''
class State(TypedDict):
    query: str
    draft: str
    answer: str
def run(state):
    draft = request(model="m", template="draft", arguments=[state["query"]])
    answer = request(model="m", template="answer", arguments=[draft])
    return {"draft": draft, "answer": answer}
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_edge(START, "run")
builder.add_edge("run", END)
app = builder.compile()
'''
        graph, _ = extract_source(*_document(source))
        body = graph["states"][graph["entry"]]
        self.assertEqual(body["calls"][0]["result"], body["calls"][1]["arguments"][0]["value"])

    def test_same_result_slot_rejects_different_model_units(self) -> None:
        contracts = {
            "format": "orchlang-langgraph-contracts", "version": 1,
            "name": "unit_conflict",
            "inputs": {"flag": {"type": "boolean", "label": "secret"}},
            "models": {
                "a": {"provider": "mock", "model": "one", "max_tokens": 8},
                "b": {"provider": "mock", "model": "two", "max_tokens": 8},
            },
        }
        source = PRELUDE + '''
class State(TypedDict):
    flag: bool
    result: str
def yes(state):
    result = request(model="a", template="same", arguments=["x"])
    return {"result": result}
def no(state):
    result = request(model="b", template="same", arguments=["x"])
    return {"result": result}
def route(state):
    if state["flag"]:
        return "yes"
    return "no"
def begin(state):
    return {}
builder = StateGraph(State)
builder.add_node("begin", begin)
builder.add_node("yes", yes)
builder.add_node("no", no)
builder.add_edge(START, "begin")
builder.add_conditional_edges("begin", route, {"yes": "yes", "no": "no"})
builder.add_edge("yes", END)
builder.add_edge("no", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "different provider/model token units"):
            extract_source(*_document(source, contracts))

    def test_cross_cap_writers_choose_maximum_register_bound(self) -> None:
        contracts = {
            "format": "orchlang-langgraph-contracts", "version": 1,
            "name": "cap_writers",
            "inputs": {"flag": {"type": "boolean", "label": "secret"}},
            "models": {
                "small": {"provider": "mock", "model": "same", "max_tokens": 4},
                "large": {"provider": "mock", "model": "same", "max_tokens": 12},
            },
        }
        source = PRELUDE + '''
class State(TypedDict):
    flag: bool
    result: str
def left(state):
    value = request(model="small", template="same", arguments=["x"])
    return {"result": value}
def right(state):
    value = request(model="large", template="same", arguments=["x"])
    return {"result": value}
def route(state):
    if state["flag"]:
        return "left"
    return "right"
def begin(state):
    return {}
builder = StateGraph(State)
builder.add_node("begin", begin)
builder.add_node("left", left)
builder.add_node("right", right)
builder.add_edge(START, "begin")
builder.add_conditional_edges("begin", route, {"left": "left", "right": "right"})
builder.add_edge("left", END)
builder.add_edge("right", END)
app = builder.compile()
'''
        graph, mapping = extract_source(*_document(source, contracts))
        slot = mapping["result_slots"][0]
        self.assertEqual(slot["max_writer_cap"], 12)
        self.assertEqual(check(Graph(graph))["status"], "rejected")

    def test_secret_branch_template_difference_stays_a_relational_rejection(self) -> None:
        contracts = {
            "format": "orchlang-langgraph-contracts", "version": 1,
            "name": "different_secret_request",
            "inputs": {"private": {"type": "boolean", "label": "secret"}},
            "models": {"m": {"provider": "mock", "model": "same", "max_tokens": 8}},
        }
        source = PRELUDE + '''
class State(TypedDict):
    private: bool
    result: str
def begin(state):
    return {}
def left(state):
    result = request(model="m", template="left", arguments=["same"])
    return {"result": result}
def right(state):
    result = request(model="m", template="right", arguments=["same"])
    return {"result": result}
def route(state):
    if state["private"]:
        return "left"
    return "right"
builder = StateGraph(State)
builder.add_node("begin", begin)
builder.add_node("left", left)
builder.add_node("right", right)
builder.add_edge(START, "begin")
builder.add_conditional_edges("begin", route, {"left": "left", "right": "right"})
builder.add_edge("left", END)
builder.add_edge("right", END)
app = builder.compile()
'''
        graph, _ = extract_source(*_document(source, contracts))
        result = check(Graph(graph))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("templates", result["diagnostic"])

    def test_route_comparison_normalizes_reversed_operands(self) -> None:
        source = PRELUDE + '''
class State(TypedDict):
    query: str
    result: str
def run(state):
    result = request(model="m", template="go", arguments=[state["query"]])
    return {"result": result}
def route(state):
    if 5 < tokens(state["result"]):
        return "large"
    return "small"
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_conditional_edges("run", route, {"large": END, "small": END})
builder.add_edge(START, "run")
app = builder.compile()
'''
        graph, _ = extract_source(*_document(source))
        self.assertEqual(graph["states"][graph["entry"]]["next"]["guard"]["op"], ">")

    def test_unrecognized_statements_and_imports_fail_closed(self) -> None:
        source = PRELUDE + '''
import os
class State(TypedDict):
    query: str
def run(state):
    return {}
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_edge(START, "run")
builder.add_edge("run", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "unsupported top-level statement Import"):
            extract_source(*_document(source))

    def test_nonliteral_request_components_and_argument_types_fail_closed(self) -> None:
        base = PRELUDE + '''
class State(TypedDict):
    query: str
def run(state):
    response = request(model=MODEL, template="go", arguments=[state["query"]])
    return {}
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_edge(START, "run")
builder.add_edge("run", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "literal string"):
            extract_source(*_document(base))

        boolean_arg = base.replace('model=MODEL', 'model="m"').replace('arguments=[state["query"]]', 'arguments=[True]')
        with self.assertRaisesRegex(FrontendError, "request arguments"):
            extract_source(*_document(boolean_arg))

    def test_model_alias_price_and_duplicate_json_validation(self) -> None:
        for bad in (
            b'{"format":"orchlang-langgraph-contracts","version":1,"version":1,"name":"x","inputs":{},"models":{}}',
            b'{"format":"orchlang-langgraph-contracts","version":1,"name":"x","inputs":{},"models":{"m":{"provider":"p","model":"m","max_tokens":1,"unit_price":1e999}}}',
        ):
            with self.subTest(bad=bad), self.assertRaises(FrontendError):
                parse_contracts(bad)

    def test_export_binds_exact_source_contract_graph_certificate_and_replay(self) -> None:
        source, contracts = _read_fixture("secret_dependent_chain")
        graph, sidecar, report, attestation = export_bytes(source, contracts)
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        self.assertEqual(sidecar["source_sha256"], digest(source))
        self.assertEqual(sidecar["contracts_sha256"], digest(contracts))
        self.assertEqual(sidecar["graph_sha256"], digest(_canonical(graph)))
        self.assertEqual(sidecar["certificate_sha256"], digest(_canonical(report)))
        self.assertEqual(sidecar["attestation_sha256"], digest(_canonical(attestation)))
        self.assertEqual(sidecar["checks"]["graph_check"], "accepted")
        self.assertEqual(sidecar["checks"]["certificate_replay"], "verified")
        self.assertEqual(sidecar["source_execution"], "not_performed_by_exporter")

    def test_reused_output_paths_remove_stale_attestation_for_rejected_graph(self) -> None:
        accepted_source, accepted_contracts = _read_fixture("secret_dependent_chain")
        accepted = export_bytes(accepted_source, accepted_contracts)
        rejected_source, rejected_contracts = _read_fixture("rejected_secret_request_difference")
        rejected = export_bytes(rejected_source, rejected_contracts)
        self.assertEqual(accepted[2]["status"], "accepted")
        self.assertIsNotNone(accepted[3])
        self.assertEqual(rejected[2]["status"], "rejected")
        self.assertIsNone(rejected[3])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph_path = root / "flow.graph.json"
            certificate_path = root / "flow.certificate.json"
            sidecar_path = root / "flow.provenance.json"
            attestation_path = root / "flow.attestation.json"

            def outputs(exported):
                graph, sidecar, report, attestation = exported
                return [
                    (graph_path, _canonical(graph)),
                    (certificate_path, _canonical(report)),
                    (sidecar_path, _canonical(sidecar)),
                    (attestation_path, _canonical(attestation) if attestation is not None else None),
                ]

            _write_atomic(outputs(accepted))
            self.assertTrue(attestation_path.exists())
            _write_atomic(outputs(rejected))
            self.assertFalse(attestation_path.exists())
            self.assertEqual(json.loads(sidecar_path.read_bytes())["attestation_sha256"], None)
            self.assertEqual(json.loads(certificate_path.read_bytes())["status"], "rejected")

    def test_study_artifact_reuse_invalidates_old_attestation_before_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (patch.object(source_study, "ARTIFACTS", root),
                  patch.object(source_study, "ROOT", root)):
                source_study._save_artifacts(
                    "reused", {"graph": "accepted"}, {"attestation_sha256": "old"},
                    {"status": "accepted"}, {"status": "verified"},
                )
                attestation_path = root / "reused.attestation.json"
                self.assertTrue(attestation_path.exists())
                source_study._save_artifacts(
                    "reused", {"graph": "rejected"}, {"attestation_sha256": None},
                    {"status": "rejected"}, None,
                )
                self.assertFalse(attestation_path.exists())
                self.assertEqual(json.loads((root / "reused.provenance.json").read_bytes())
                                 ["attestation_sha256"], None)

    def test_exporter_rejects_oversized_files_after_bounded_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.py"
            path.write_bytes(b"12345")
            self.assertEqual(_read_bounded(path, 5, "source"), b"12345")
            with self.assertRaisesRegex(FrontendError, "exceeds 4 bytes"):
                _read_bounded(path, 4, "source")

    def test_contract_caps_and_static_request_bytes_fit_runtime_probe_limits(self) -> None:
        contracts = {
            "format": "orchlang-langgraph-contracts", "version": 1,
            "name": "oversized", "chars_per_token": 4,
            "inputs": {"query": {"type": "text", "label": "public", "max_tokens": 2**64 - 2}},
            "models": {"m": {"provider": "mock", "model": "m", "max_tokens": 8}},
        }
        with self.assertRaisesRegex(FrontendError, "offline value-byte limit"):
            parse_contracts(json.dumps(contracts).encode())

    def test_contract_inputs_match_typed_dict_fields_exactly(self) -> None:
        source = PRELUDE + '''
class State(TypedDict):
    query: bool
def run(state):
    return {}
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_edge(START, "run")
builder.add_edge("run", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "TypedDict type"):
            extract_source(*_document(source))

    def test_builder_requires_all_functions_and_reachable_static_nodes(self) -> None:
        source = PRELUDE + '''
class State(TypedDict):
    query: str
def run(state):
    return {}
def unused(state):
    return {}
builder = StateGraph(State)
builder.add_node("run", run)
builder.add_node("unused", unused)
builder.add_edge(START, "run")
builder.add_edge("run", END)
builder.add_edge("unused", END)
app = builder.compile()
'''
        with self.assertRaisesRegex(FrontendError, "unreachable StateGraph nodes"):
            extract_source(*_document(source))


if __name__ == "__main__":
    unittest.main()
