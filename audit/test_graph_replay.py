"""Semantic and adversarial tests for the independent graph-certificate replayer."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from replay_graph_certificate import ReplayError, replay


ROOT = Path(__file__).resolve().parents[1]
PRODUCER = ROOT / "audit" / "orchgraph.py"


def encode(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def base_graph() -> dict[str, object]:
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "ReplayBase",
        "chars_per_token": 1,
        "inputs": {
            "x": {"type": "text", "label": "public", "max_tokens": 20},
            "y": {"type": "text", "label": "public", "max_tokens": 20},
            "route": {"type": "boolean", "label": "public"},
            "secret": {"type": "boolean", "label": "secret"},
        },
        "registers": {
            "left_first": {"model": "m"},
            "right_first": {"model": "m_alias"},
            "left_next": {"model": "m"},
            "right_next": {"model": "m_alias"},
        },
        "models": {
            "m": {"provider": "mock", "model": "engine-A", "max_tokens": 4},
            "m_alias": {"provider": "mock", "model": "engine-A", "max_tokens": 4},
        },
        "states": {
            "entry": {
                "calls": [],
                "next": {
                    "kind": "secret",
                    "guard": {"value": "secret"},
                    "then": "left",
                    "else": "right",
                },
            },
            "left": {
                "calls": [
                    {"model": "m", "template": "lookup={x}!",
                     "arguments": [{"value": "x"}, {"literal": "!"}],
                     "result": "left_first"},
                    {"model": "m", "template": "follow={r}",
                     "arguments": [{"value": "left_first"}], "result": "left_next"},
                ],
                "next": {"kind": "stop"},
            },
            "right": {
                "calls": [
                    {"model": "m_alias", "template": "lookup={x}!",
                     "arguments": [{"value": "x"}, {"literal": "!"}],
                     "result": "right_first"},
                    {"model": "m_alias", "template": "follow={r}",
                     "arguments": [{"value": "right_first"}], "result": "right_next"},
                ],
                "next": {"kind": "stop"},
            },
        },
        "entry": "entry",
    }


def public_graph() -> dict[str, object]:
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "ReplayPublic",
        "inputs": {
            "x": {"type": "text", "label": "public", "max_tokens": 8},
            "y": {"type": "text", "label": "public", "max_tokens": 8},
            "secret": {"type": "boolean", "label": "secret"},
        },
        "registers": {},
        "models": {},
        "states": {
            "entry": {"calls": [], "next": {"kind": "secret", "guard": {"value": "secret"},
                                                   "then": "left", "else": "right"}},
            "left": {"calls": [], "next": {"kind": "public", "guard": {"value": "x", "op": "<=", "limit": 3},
                                               "then": "yes", "else": "no"}},
            "right": {"calls": [], "next": {"kind": "public", "guard": {"value": "x", "op": "<=", "limit": 3},
                                                "then": "yes", "else": "no"}},
            "yes": {"calls": [], "next": {"kind": "stop"}},
            "no": {"calls": [], "next": {"kind": "stop"}},
        },
        "entry": "entry",
    }


def overwrite_graph() -> dict[str, object]:
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "ReplayOverwrite",
        "inputs": {
            "x": {"type": "text", "label": "public", "max_tokens": 20},
            "secret": {"type": "boolean", "label": "secret"},
        },
        "registers": {
            "a": {"model": "m"}, "b": {"model": "m_alias"},
            "c": {"model": "m_alias"},
            "left_out": {"model": "m"}, "right_out": {"model": "m_alias"},
        },
        "models": {
            "m": {"provider": "mock", "model": "engine-A", "max_tokens": 3},
            "m_alias": {"provider": "mock", "model": "engine-A", "max_tokens": 3},
        },
        "states": {
            "entry": {"calls": [], "next": {"kind": "secret", "guard": {"value": "secret"},
                                               "then": "left1", "else": "right1"}},
            "left1": {"calls": [{"model": "m", "template": "first={x}",
                                  "arguments": [{"value": "x"}], "result": "a"}],
                      "next": {"kind": "goto", "target": "left2"}},
            "right1": {"calls": [{"model": "m_alias", "template": "first={x}",
                                   "arguments": [{"value": "x"}], "result": "b"}],
                       "next": {"kind": "goto", "target": "right2"}},
            "left2": {"calls": [
                {"model": "m", "template": "second={x}",
                 "arguments": [{"value": "x"}], "result": "a"},
                {"model": "m", "template": "consume={v}",
                 "arguments": [{"value": "a"}], "result": "left_out"},
            ], "next": {"kind": "stop"}},
            "right2": {"calls": [
                {"model": "m_alias", "template": "second={x}",
                 "arguments": [{"value": "x"}], "result": "c"},
                {"model": "m_alias", "template": "consume={v}",
                 "arguments": [{"value": "c"}], "result": "right_out"},
            ], "next": {"kind": "stop"}},
        },
        "entry": "entry",
    }


def cycle_graph() -> dict[str, object]:
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "ReplayCycle",
        "inputs": {"x": {"type": "text", "label": "public", "max_tokens": 8}},
        "registers": {"r": {"model": "m"}},
        "models": {"m": {"provider": "mock", "model": "engine-A", "max_tokens": 3}},
        "states": {
            "start": {"calls": [{"model": "m", "template": "seed={x}",
                                  "arguments": [{"value": "x"}], "result": "r"}],
                      "next": {"kind": "goto", "target": "loop"}},
            "loop": {"calls": [{"model": "m", "template": "again={r}",
                                 "arguments": [{"value": "r"}], "result": "r"}],
                     "next": {"kind": "goto", "target": "loop"}},
        },
        "entry": "start",
    }


def make_certificate(document: dict[str, object]) -> tuple[bytes, bytes, dict[str, object]]:
    graph_bytes = encode(document)
    with tempfile.TemporaryDirectory(prefix="graph-replay-test-") as temporary:
        directory = Path(temporary)
        graph_path = directory / "graph.json"
        cert_path = directory / "certificate.json"
        graph_path.write_bytes(graph_bytes)
        process = subprocess.run(
            [sys.executable, str(PRODUCER), str(graph_path), "--report", str(cert_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise AssertionError(f"graph fixture was not accepted: {process.stderr}\n{process.stdout}")
        certificate_bytes = cert_path.read_bytes()
    return graph_bytes, certificate_bytes, json.loads(certificate_bytes)


def refresh_source_digest(graph_bytes: bytes, certificate: dict[str, object]) -> bytes:
    certificate["source_sha256"] = hashlib.sha256(graph_bytes).hexdigest()
    return encode(certificate)


class GraphReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_bytes, cls.base_cert_bytes, cls.base_cert = make_certificate(base_graph())
        cls.public_bytes, cls.public_cert_bytes, cls.public_cert = make_certificate(public_graph())
        cls.overwrite_bytes, cls.overwrite_cert_bytes, cls.overwrite_cert = make_certificate(overwrite_graph())
        cls.cycle_bytes, cls.cycle_cert_bytes, cls.cycle_cert = make_certificate(cycle_graph())

    def assert_rejected(self, graph_bytes: bytes, certificate_bytes: bytes) -> None:
        with self.assertRaises(ReplayError):
            replay(graph_bytes, certificate_bytes)

    def test_replays_secret_choices_aliases_and_dependent_call_chain(self) -> None:
        attestation = replay(self.base_bytes, self.base_cert_bytes)
        self.assertEqual(attestation["status"], "verified")
        self.assertGreater(attestation["product_nodes_replayed"], 10)
        self.assertTrue(attestation["checks"]["complete_universal_successor_closure"])

    def test_replays_synchronized_public_guard(self) -> None:
        attestation = replay(self.public_bytes, self.public_cert_bytes)
        self.assertEqual(attestation["status"], "verified")

    def test_replays_productive_cycle_as_prefix_closure(self) -> None:
        attestation = replay(self.cycle_bytes, self.cycle_cert_bytes)
        self.assertEqual(attestation["status"], "verified")
        self.assertGreater(attestation["product_nodes_replayed"], 1)
        self.assertIn("no termination or finite total-cost", self.cycle_cert["semantics"]["cycles"])

    def test_overwrite_removes_stale_relation_before_adding_new_pair(self) -> None:
        attestation = replay(self.overwrite_bytes, self.overwrite_cert_bytes)
        self.assertEqual(attestation["status"], "verified")
        join_nodes = [node for node in self.overwrite_cert["nodes"]
                      if node["left"] == ["left2", 1] and node["right"] == ["right2", 1]]
        self.assertTrue(join_nodes)
        relation = {tuple(pair) for pair in join_nodes[0]["equal_values"]}
        self.assertIn(("a", "c"), relation)
        self.assertNotIn(("a", "b"), relation)

    def test_rejects_source_hash_mismatch(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["source_sha256"] = "0" * 64
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_nonaccepted_status(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["status"] = "unknown"
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_product_closure_larger_than_declared_resource_cap(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["max_nodes"] = 1
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_missing_secret_arm_successor(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["nodes"][0]["successors"].pop()
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_secret_identity_in_initial_relation(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        relation = cert["nodes"][0]["equal_values"]
        relation.append(["secret", "secret"])
        relation.sort()
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_missing_public_identity_in_initial_relation(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["nodes"][0]["equal_values"].remove(["x", "x"])
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_missing_matched_call_result_pair(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        node = next(n for n in cert["nodes"]
                    if ["left_first", "left_first"] in n["equal_values"])
        node["equal_values"] = [
            pair for pair in node["equal_values"]
            if pair[0] in {"route", "x", "y"} and pair[1] in {"route", "x", "y"}
        ]
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_missing_reachable_product_node(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["nodes"].pop()
        cert["product_nodes"] -= 1
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_unreachable_fake_product_node(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        fake = copy.deepcopy(cert["nodes"][-1])
        fake["id"] = len(cert["nodes"])
        cert["nodes"].append(fake)
        cert["product_nodes"] += 1
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_wrong_successor_id(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["nodes"][0]["successors"][0] = cert["nodes"][0]["successors"][1]
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_rule_tampering(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["nodes"][0]["rule"] = "stop"
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_resolved_model_contract_mismatch_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["models"]["m_alias"]["max_tokens"] = 5
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        cert["state_entry_bounds"]["right"]["output_tokens"] += 2
        cert["state_entry_bounds"]["right"]["total_tokens"] += 2
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_actual_model_id_mismatch_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["models"]["m_alias"]["model"] = "engine-B"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_template_mismatch_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["states"]["right"]["calls"][0]["template"] = "Lookup={x}!"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_argument_order_mismatch_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["states"]["right"]["calls"][0]["arguments"].reverse()
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_literal_argument_mismatch_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["states"]["right"]["calls"][0]["arguments"][1]["literal"] = "?"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_distinct_public_input_identity_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["states"]["right"]["calls"][0]["arguments"][0]["value"] = "y"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_changed_public_guard_subject_even_with_updated_hash(self) -> None:
        graph = public_graph()
        graph["states"]["right"]["next"]["guard"]["value"] = "y"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.public_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_public_guard_operator_mismatch_even_with_updated_hash(self) -> None:
        graph = public_graph()
        graph["states"]["right"]["next"]["guard"]["op"] = "<"
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.public_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_public_guard_limit_mismatch_even_with_updated_hash(self) -> None:
        graph = public_graph()
        graph["states"]["right"]["next"]["guard"]["limit"] = 4
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.public_cert)
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_call_stop_misalignment_even_with_updated_hash(self) -> None:
        graph = base_graph()
        graph["states"]["right"]["calls"] = []
        graph_bytes = encode(graph)
        cert = copy.deepcopy(self.base_cert)
        cert["state_entry_bounds"]["right"] = {
            "output_tokens": 0, "input_tokens": 0, "total_tokens": 0
        }
        self.assert_rejected(graph_bytes, refresh_source_digest(graph_bytes, cert))

    def test_rejects_invalid_untyped_graph(self) -> None:
        graph = base_graph()
        graph["inputs"]["secret"]["type"] = "integer"
        self.assert_rejected(encode(graph), self.base_cert_bytes)

    def test_rejects_call_free_cycle(self) -> None:
        graph = {
            "format": "orchlang-request-graph", "version": 1, "name": "SilentLoop",
            "inputs": {}, "registers": {}, "models": {},
            "states": {
                "entry": {"calls": [], "next": {"kind": "goto", "target": "loop"}},
                "loop": {"calls": [], "next": {"kind": "goto", "target": "loop"}},
            },
            "entry": "entry",
        }
        with self.assertRaises(ReplayError):
            replay(encode(graph), self.base_cert_bytes)

    def test_rejects_duplicate_json_keys(self) -> None:
        duplicate_graph = self.base_bytes.replace(
            b'"format":"orchlang-request-graph"',
            b'"format":"orchlang-request-graph","format":"orchlang-request-graph"',
            1,
        )
        with self.assertRaisesRegex(ReplayError, "duplicate JSON object key"):
            replay(duplicate_graph, self.base_cert_bytes)

    def test_rejects_duplicate_certificate_json_keys(self) -> None:
        duplicate_cert = self.base_cert_bytes.replace(
            b'"status": "accepted"',
            b'"status": "accepted", "status": "accepted"',
            1,
        )
        with self.assertRaisesRegex(ReplayError, "duplicate JSON object key"):
            replay(self.base_bytes, duplicate_cert)

    def test_rejects_unknown_certificate_fields(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["trust_me"] = True
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_rejects_state_cost_summary_tampering(self) -> None:
        cert = copy.deepcopy(self.base_cert)
        cert["state_entry_bounds"]["left"]["total_tokens"] += 1
        self.assert_rejected(self.base_bytes, encode(cert))

    def test_attestation_binds_graph_and_replayer_hashes(self) -> None:
        attestation = replay(self.base_bytes, self.base_cert_bytes)
        self.assertEqual(attestation["source_sha256"], hashlib.sha256(self.base_bytes).hexdigest())
        self.assertEqual(len(attestation["replayer_sha256"]), 64)
        self.assertFalse(attestation["producer_checker_hash_verified"])

    def test_cli_emits_machine_readable_attestation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graph-replay-cli-test-") as temporary:
            directory = Path(temporary)
            graph_path = directory / "graph.json"
            cert_path = directory / "certificate.json"
            attestation_path = directory / "attestation.json"
            graph_path.write_bytes(self.base_bytes)
            cert_path.write_bytes(self.base_cert_bytes)
            process = subprocess.run(
                [sys.executable, str(ROOT / "audit" / "replay_graph_certificate.py"),
                 str(graph_path), str(cert_path), "--attestation", str(attestation_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)["status"], "verified")
            self.assertEqual(json.loads(attestation_path.read_text())["source_sha256"],
                             hashlib.sha256(self.base_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
