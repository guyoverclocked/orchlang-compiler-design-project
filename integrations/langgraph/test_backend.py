"""Executable conformance checks for the optional actual-LangGraph backend."""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "audit"))

from orchgraph import Graph, check, reference_run  # noqa: E402
from replay_graph_certificate import ReplayError, strict_json  # noqa: E402
from integrations.langgraph.backend import (  # noqa: E402
    BackendError,
    MAX_PROBE_VALUE_BYTES,
    OfflineRequestSession,
    OfflineOmegaOracle,
    OracleOutcome,
    execute_graph,
    execute_verified,
    prepare_graph,
)


ACCEPTED = ROOT / "examples/graphs/accepted"
CERTIFICATES = ROOT / "bench/results/graph_certificates"


def _store(graph: Graph, secret_bool: bool = False,
           public_bool: bool = False) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, declaration in graph.inputs.items():
        if declaration["type"] == "text":
            result[name] = "é🙂 Unicode"
        elif declaration["label"] == "secret":
            result[name] = secret_bool
        else:
            result[name] = public_bool
    return result


def _projection(result: dict[str, object]) -> dict[str, object]:
    keys = ("trace", "stopped", "truncated_at_calls")
    return {key: result[key] for key in keys if key in result}


class LangGraphBackendTests(unittest.TestCase):
    def _fixture(self, name: str):
        graph_path = ACCEPTED / name
        certificate_path = CERTIFICATES / name
        raw_graph = graph_path.read_bytes()
        raw_certificate = certificate_path.read_bytes()
        graph = Graph(strict_json(raw_graph, "source graph"))
        verified = prepare_graph(raw_graph, raw_certificate)
        return graph, verified, raw_graph, raw_certificate

    def test_all_six_authored_accepted_graphs_match_reference(self) -> None:
        paths = sorted(ACCEPTED.glob("*.json"))
        self.assertEqual(len(paths), 6)
        for graph_path in paths:
            with self.subTest(graph=graph_path.name):
                graph, verified, _, _ = self._fixture(graph_path.name)
                stores = [_store(graph, secret_bool=value) for value in (False, True)]
                if any(
                    name in graph.inputs
                    and graph.inputs[name]["label"] == "secret"
                    and graph.inputs[name]["type"] == "boolean"
                    for name in graph.inputs
                ):
                    # Exercise every Boolean secret assignment, including
                    # nested independent choices when the graph has two bits.
                    secret_names = [name for name, item in graph.inputs.items()
                                    if item["label"] == "secret" and item["type"] == "boolean"]
                    stores = []
                    for flags in itertools.product((False, True), repeat=len(secret_names)):
                        store = _store(graph)
                        store.update(dict(zip(secret_names, flags)))
                        stores.append(store)
                for store in stores:
                    for seed in (1, 17, 29):
                        expected = reference_run(graph, store, seed, 24)
                        actual = execute_verified(
                            verified, store, seed, OfflineOmegaOracle(), max_calls=24
                        ).to_dict()
                        self.assertEqual(actual["status"],
                                         "truncated" if "truncated_at_calls" in expected else "stopped")
                        self.assertEqual(_projection(actual), _projection(expected))

    def test_call_horizon_checks_control_after_last_allowed_call(self) -> None:
        graph, verified, _, _ = self._fixture("finite_private_chain.json")
        store = _store(graph, secret_bool=True)
        expected = reference_run(graph, store, 17, 2)
        actual = execute_verified(verified, store, 17, max_calls=2).to_dict()
        self.assertEqual(actual["status"], "stopped")
        self.assertTrue(actual["stopped"])
        self.assertEqual(actual["call_count"], 2)
        self.assertEqual(_projection(actual), _projection(expected))
        self.assertEqual(actual["version"], 2)
        self.assertEqual({key: actual["final_values"][key] for key in store}, store)
        self.assertEqual(actual["final_values"]["a"], actual["trace"][0]["response"])
        self.assertEqual(actual["final_values"]["b"], actual["trace"][1]["response"])
        self.assertNotIn("x", actual["final_values"])

        expected_prefix = reference_run(graph, store, 17, 1)
        actual_prefix = execute_verified(verified, store, 17, max_calls=1).to_dict()
        self.assertEqual(actual_prefix["status"], "truncated")
        self.assertEqual(actual_prefix["truncated_at_calls"], 1)
        self.assertEqual(_projection(actual_prefix), _projection(expected_prefix))
        self.assertIsNone(actual_prefix["final_values"])

    def test_real_langgraph_recursion_limit_fails_closed(self) -> None:
        graph, verified, _, _ = self._fixture("unbounded_productive_cycle.json")
        actual = execute_verified(
            verified,
            _store(graph, secret_bool=True),
            17,
            max_calls=10_000,
            recursion_limit=5,
        ).to_dict()
        self.assertEqual(actual["status"], "resource_limited")
        self.assertFalse(actual["stopped"])
        self.assertIsNone(actual["final_values"])
        self.assertNotIn("truncated_at_calls", actual)
        self.assertEqual(actual["failure"]["type"], "langgraph_recursion_limit")

    def test_graph_control_limit_fails_closed(self) -> None:
        graph, verified, _, _ = self._fixture("finite_private_chain.json")
        actual = execute_verified(
            verified,
            _store(graph, secret_bool=True),
            17,
            max_calls=10,
            max_control_steps=1,
        ).to_dict()
        self.assertEqual(actual["status"], "resource_limited")
        self.assertFalse(actual["stopped"])
        self.assertIsNone(actual["final_values"])
        self.assertIsNotNone(actual["failure"])

    def test_bad_certificate_and_stale_relation_never_build_stategraph(self) -> None:
        graph_path = ACCEPTED / "finite_private_chain.json"
        cert_path = CERTIFICATES / graph_path.name
        graph_bytes = graph_path.read_bytes()
        certificate = cert_path.read_bytes()
        stale_path = ROOT / "examples/graphs/rejected/overwritten_result_relation.json"
        stale_bytes = stale_path.read_bytes()
        stale_doc = Graph(strict_json(stale_bytes, "stale relation graph"))
        stale_certificate = json.dumps(
            check(stale_doc), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        with patch("integrations.langgraph.backend._compile_state_graph") as compile_graph:
            with self.assertRaises(ReplayError):
                execute_graph(graph_bytes + b" ", certificate, {"query": "x", "route": True}, 1)
            with self.assertRaises(ReplayError):
                execute_graph(stale_bytes, stale_certificate, {"query": "x", "route": True}, 1)
            compile_graph.assert_not_called()

    def test_input_validation_precedes_stategraph_construction(self) -> None:
        graph, verified, _, _ = self._fixture("finite_private_chain.json")
        store = _store(graph, secret_bool=True)
        store["query"] = "x" * 200
        with patch("integrations.langgraph.backend._compile_state_graph") as compile_graph:
            with self.assertRaises(BackendError):
                execute_verified(verified, store, 1)
            compile_graph.assert_not_called()

    def test_mutating_a_normalized_read_view_cannot_change_verified_execution(self) -> None:
        graph, verified, _, _ = self._fixture("matched_cyclic_chain.json")
        mutable_view = verified.graph
        mutable_view.states[graph.entry] = {"calls": [], "next": {"kind": "stop"}}
        mutable_attestation = verified.attestation
        mutable_attestation["status"] = "tampered"
        with self.assertRaises(AttributeError):
            verified.raw_graph = b"tampered"  # type: ignore[misc]

        store = _store(graph, secret_bool=True)
        expected = reference_run(graph, store, 17, 8)
        actual = execute_verified(verified, store, 17, max_calls=8).to_dict()
        self.assertEqual(actual["replay_attestation"]["status"], "verified")
        self.assertEqual(_projection(actual), _projection(expected))

    def test_oracle_output_usage_must_bound_full_response(self) -> None:
        graph, verified, _, _ = self._fixture("finite_private_chain.json")

        def unsafe_oracle(_request):
            return OracleOutcome("too long for one token", 1)

        actual = execute_verified(
            verified,
            _store(graph, secret_bool=True),
            17,
            unsafe_oracle,
            max_calls=5,
        ).to_dict()
        self.assertEqual(actual["status"], "runtime_error")
        self.assertFalse(actual["stopped"])
        self.assertEqual(actual["call_count"], 0)

    def test_source_request_session_matches_full_value_oracle(self) -> None:
        graph, _, _, _ = self._fixture("finite_private_chain.json")
        store = _store(graph, secret_bool=True)
        expected = reference_run(graph, store, 17, 2)
        session = OfflineRequestSession(
            graph.name, 17, graph.models, chars_per_token=graph.divisor
        )
        values = dict(store)
        for call in graph.states["left"]["calls"]:
            arguments = [
                atom["literal"] if "literal" in atom else values[atom["value"]]
                for atom in call["arguments"]
            ]
            values[call["result"]] = session.request(
                call["model"], call["template"], arguments
            )
        self.assertEqual(session.trace, expected["trace"])
        self.assertEqual(session.tokens("é🙂 Unicode"), graph.estimate("é🙂 Unicode"))

    def test_session_preserves_optional_price_identity_and_call_cap(self) -> None:
        contracts = {
            "plain": {"provider": "mock", "model": "unit-test", "max_tokens": 8},
            "zero_price": {"provider": "mock", "model": "unit-test",
                            "max_tokens": 8, "unit_price": 0},
        }
        session = OfflineRequestSession(
            "helper_probe", 17, contracts, max_calls=2
        )
        session.request("plain", "prompt", ["x"])
        session.request("zero_price", "prompt", ["x"])
        self.assertEqual([event["ordinal"] for event in session.trace], [0, 0])
        self.assertEqual([event["contract"]["has_unit_price"] for event in session.trace],
                         [False, True])
        with self.assertRaises(BackendError):
            session.request("plain", "prompt", ["x"])
        with self.assertRaises(BackendError):
            session.tokens("\ud800")

    def test_request_and_response_byte_limits_fail_closed(self) -> None:
        counter = {"calls": 0}

        def counting_oracle(request):
            counter["calls"] += 1
            return OfflineOmegaOracle()(request)

        contract = {"provider": "mock", "model": "unit-test", "max_tokens": 8}
        session = OfflineRequestSession(
            "byte_probe", 1, {"m": contract}, oracle=counting_oracle
        )
        with self.assertRaises(BackendError):
            session.request("m", "p" * (MAX_PROBE_VALUE_BYTES + 1), [])
        self.assertEqual(counter["calls"], 0)

        graph, verified, _, _ = self._fixture("finite_private_chain.json")

        def oversized_oracle(_request):
            return OracleOutcome("x" * (MAX_PROBE_VALUE_BYTES + 1), 8)

        result = execute_verified(
            verified,
            _store(graph, secret_bool=True),
            1,
            oversized_oracle,
        ).to_dict()
        self.assertEqual(result["status"], "resource_limited")
        self.assertFalse(result["stopped"])
        self.assertEqual(result["call_count"], 0)


if __name__ == "__main__":
    unittest.main()
