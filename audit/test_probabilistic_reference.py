#!/usr/bin/env python3
"""Tests for the independent finite-outcome billing-channel enumerator."""
from __future__ import annotations

import copy
from fractions import Fraction
import itertools
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probabilistic_reference import ReferenceError, independent_histogram
from probabilistic_channels import producer_histogram


CONTRACT = {
    "provider": "offline", "model": "m1", "max_tokens": 8,
    "has_unit_price": False, "unit_price": 0.0,
}


def model(alias="m", **extra):
    return {"provider": "offline", "model": "m1", "max_tokens": 8, **extra}


def call(template, result="r", alias="m", arguments=None):
    return {"model": alias, "template": template,
            "arguments": [] if arguments is None else arguments, "result": result}


def graph(states, *, inputs=None, models=None, registers=None, entry="s", divisor=1):
    models = {"m": model()} if models is None else models
    registers = {"r": {"model": "m"}} if registers is None else registers
    return {
        "format": "orchlang-request-graph", "version": 1, "name": "probability_test",
        "chars_per_token": divisor, "inputs": {} if inputs is None else inputs,
        "registers": registers, "models": models, "states": states, "entry": entry,
    }


def stop():
    return {"kind": "stop"}


def distribution(*items):
    return [{"response": response, "output_tokens": usage, "probability": probability}
            for response, usage, probability in items]


def kernel(defaults=None, *, window=0, rules=None):
    if defaults is None:
        defaults = {"m": distribution(("z", 1, "1/1"))}
    elif isinstance(defaults, list):
        defaults = {"m": defaults}
    return {"format": "orchlang-finite-outcome-kernel", "version": 1,
            "history_window": window,
            "defaults": defaults,
            **({} if rules is None else {"rules": rules})}


def billing_contract(contract=CONTRACT, *, count, input_tokens, output_tokens):
    return {"contract": contract, "call_count": count,
            "input_tokens": input_tokens, "output_tokens": output_tokens}


def key(stopped, entries):
    return json.dumps({"stopped": stopped, "billing": entries}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))


class IndependentProbabilisticReferenceTests(unittest.TestCase):
    def test_single_call_uses_exact_rational_mass_and_additive_usage(self):
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        outcomes = distribution(("a", 1, "1/3"), ("bb", 2, "2/3"))
        result = independent_histogram(document, kernel(outcomes), {}, 1)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["mass"], Fraction(1, 1))
        self.assertEqual(result["leaf_paths"], 2)
        self.assertEqual(result["call_transitions"], 2)
        expected = {
            key(True, [billing_contract(count=1, input_tokens=1, output_tokens=1)]): Fraction(1, 3),
            key(True, [billing_contract(count=1, input_tokens=1, output_tokens=2)]): Fraction(2, 3),
        }
        self.assertEqual(result["histogram"], expected)

    def test_request_usage_is_additive_utf8_byte_ceil_accounting(self):
        document = graph({"s": {"calls": [call("é", arguments=[{"literal": "a"}])],
                               "next": stop()}}, divisor=3)
        result = independent_histogram(document, kernel(distribution(("漢", 1, "1/1"))), {}, 1)
        decoded = json.loads(next(iter(result["histogram"])))
        # ceil(2 UTF-8 bytes / 3) + ceil(1 / 3) = 2, even though
        # ceil((2 + 1) / 3) would incorrectly be 1.
        self.assertEqual(decoded["billing"][0]["input_tokens"], 2)
        self.assertEqual(decoded["billing"][0]["output_tokens"], 1)

    def test_kernel_rules_are_first_match_ordered(self):
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        rules = [
            {"model": "m", "outcomes": distribution(("first", 5, "1/1"))},
            {"model": "m", "template": "t", "outcomes": distribution(("second", 6, "1/1"))},
        ]
        result = independent_histogram(document, kernel(distribution(("fallback", 8, "1/1")),
                                                         rules=rules), {}, 1)
        observation = json.loads(next(iter(result["histogram"])))
        self.assertEqual(observation["billing"][0]["output_tokens"], 5)

    def test_call_horizon_inspects_following_stop_but_truncates_at_next_call(self):
        deterministic = distribution(("x", 1, "1/1"))
        stop_graph = graph({"s": {"calls": [call("first")], "next": {"kind": "goto", "target": "end"}},
                            "end": {"calls": [], "next": stop()}})
        stopped = independent_histogram(stop_graph, kernel(deterministic), {}, 1)
        self.assertEqual(next(iter(stopped["histogram"])),
                         key(True, [billing_contract(count=1, input_tokens=5, output_tokens=1)]))

        extra_call_graph = graph({
            "s": {"calls": [call("first"), call("second")], "next": stop()},
        }, registers={"r": {"model": "m"}})
        truncated = independent_histogram(extra_call_graph, kernel(deterministic), {}, 1)
        self.assertEqual(next(iter(truncated["histogram"])),
                         key(False, [billing_contract(count=1, input_tokens=5, output_tokens=1)]))
        self.assertEqual(truncated["call_transitions"], 1)

    def test_secret_assignment_changes_observable_distribution_without_kernel_secret(self):
        document = graph({
            "s": {"calls": [], "next": {"kind": "secret", "guard": {"value": "route"},
                                                "then": "left", "else": "right"}},
            "left": {"calls": [call("left")], "next": stop()},
            "right": {"calls": [call("right")], "next": stop()},
        }, inputs={"route": {"type": "boolean", "label": "secret"}})
        rules = [
            {"model": "m", "template": "left", "outcomes": distribution(("L", 1, "1/1"))},
            {"model": "m", "template": "right", "outcomes": distribution(("RR", 2, "1/1"))},
        ]
        channel = kernel(distribution(("fallback", 8, "1/1")), rules=rules)
        left = independent_histogram(document, channel, {"route": True}, 1)
        right = independent_histogram(document, channel, {"route": False}, 1)
        self.assertNotEqual(left["histogram"], right["histogram"])
        self.assertIn('"output_tokens":1', next(iter(left["histogram"])))
        self.assertIn('"output_tokens":2', next(iter(right["histogram"])))

    def test_history_dependent_rule_matches_exact_complete_event(self):
        document = graph({
            "s": {"calls": [call("first")], "next": {"kind": "goto", "target": "second"}},
            "second": {"calls": [call("second")], "next": stop()},
        }, divisor=1)
        first_event = {"contract": CONTRACT, "ordinal": 0, "template": "first", "arguments": [],
                       "response": "a", "input_tokens": 5, "output_tokens": 1}
        rules = [
            {"model": "m", "template": "first",
             "outcomes": distribution(("a", 1, "1/2"), ("bb", 2, "1/2"))},
            {"model": "m", "template": "second", "history": [first_event],
             "outcomes": distribution(("hit", 3, "1/1"))},
        ]
        result = independent_histogram(document, kernel(distribution(("miss", 4, "1/1")),
                                                         window=1, rules=rules), {}, 2)
        self.assertEqual(result["mass"], Fraction(1, 1))
        self.assertEqual(result["leaf_paths"], 2)
        observations = {json.loads(observation)["billing"][0]["output_tokens"]: weight
                        for observation, weight in result["histogram"].items()}
        self.assertEqual(observations, {4: Fraction(1, 2), 6: Fraction(1, 2)})

    def test_productive_cycle_enumerates_paths_and_truncates_only_at_next_call(self):
        document = graph({
            "loop": {"calls": [call("t")], "next": {"kind": "public",
                "guard": {"value": "r", "op": "<=", "limit": 1},
                "then": "loop", "else": "done"}},
            "done": {"calls": [], "next": stop()},
        }, entry="loop")
        outcomes = distribution(("a", 1, "1/2"), ("bb", 2, "1/2"))
        result = independent_histogram(document, kernel(outcomes), {}, 2)
        self.assertEqual(result["leaf_paths"], 3)
        self.assertEqual(result["mass"], 1)
        masses = {}
        for observation, weight in result["histogram"].items():
            decoded = json.loads(observation)
            masses[(decoded["stopped"], decoded["billing"][0]["call_count"])] = weight
        self.assertEqual(masses, {
            (True, 1): Fraction(1, 2),
            (True, 2): Fraction(1, 4),
            (False, 2): Fraction(1, 4),
        })

    def test_trace_observer_contains_usage_only_and_preserves_call_order(self):
        document = graph({"s": {"calls": [call("alpha"), call("beta")], "next": stop()}})
        deterministic = distribution(("q", 1, "1/1"))
        result = independent_histogram(document, kernel(deterministic), {}, 2, observer="trace")
        observation = json.loads(next(iter(result["histogram"])))
        self.assertEqual(set(observation), {"stopped", "usage_trace"})
        self.assertTrue(observation["stopped"])
        self.assertEqual([item["input_tokens"] for item in observation["usage_trace"]], [5, 4])
        self.assertTrue(all(set(item) == {"contract", "input_tokens", "output_tokens"}
                            for item in observation["usage_trace"]))
        self.assertNotIn("response", next(iter(result["histogram"])))

    def test_independent_histograms_match_state_merging_producer(self):
        cases = []
        cycle = graph({
            "loop": {"calls": [call("t")], "next": {"kind": "public",
                "guard": {"value": "r", "op": "<=", "limit": 1},
                "then": "loop", "else": "done"}},
            "done": {"calls": [], "next": stop()},
        }, entry="loop")
        cycle_kernel = kernel(distribution(("a", 1, "1/2"), ("bb", 2, "1/2")))
        cases.append((cycle, cycle_kernel, {}, 3, "aggregate"))

        history_graph = graph({
            "s": {"calls": [call("first")], "next": {"kind": "goto", "target": "second"}},
            "second": {"calls": [call("second")], "next": stop()},
        })
        first_event = {"contract": CONTRACT, "ordinal": 0, "template": "first", "arguments": [],
                       "response": "a", "input_tokens": 5, "output_tokens": 1}
        history_kernel = kernel(distribution(("miss", 4, "1/1")), window=1, rules=[
            {"model": "m", "template": "first",
             "outcomes": distribution(("a", 1, "1/2"), ("bb", 2, "1/2"))},
            {"model": "m", "template": "second", "history": [first_event],
             "outcomes": distribution(("hit", 3, "1/1"))},
        ])
        cases.append((history_graph, history_kernel, {}, 2, "trace"))

        for document, channel, store, horizon, observer in cases:
            with self.subTest(name=document["name"], observer=observer):
                reference = independent_histogram(document, channel, store, horizon, observer=observer)
                producer = producer_histogram(document, channel, store, horizon, observer=observer)
                self.assertEqual(producer["status"], "complete")
                self.assertEqual(producer["histogram"], reference["histogram"])
                self.assertEqual(producer["mass"], reference["mass"])

    def test_independent_histograms_match_on_authored_accepted_graphs(self):
        fixture_dir = Path(__file__).resolve().parent.parent / "examples" / "graphs" / "accepted"
        for path in sorted(fixture_dir.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            channel = kernel({alias: distribution(("a", 1, "1/1"))
                              for alias in document["models"]})
            boolean_inputs = [name for name, decl in document["inputs"].items()
                              if decl["type"] == "boolean"]
            for choices in itertools.product((False, True), repeat=len(boolean_inputs)):
                store = {}
                for name, decl in document["inputs"].items():
                    store[name] = dict(zip(boolean_inputs, choices))[name] if decl["type"] == "boolean" else "question"
                for observer in ("aggregate", "trace"):
                    with self.subTest(graph=path.name, store=store, observer=observer):
                        reference = independent_histogram(document, channel, store, 3, observer=observer)
                        producer = producer_histogram(document, channel, store, 3, observer=observer)
                        self.assertEqual(producer["status"], "complete")
                        self.assertEqual(producer["histogram"], reference["histogram"])
                        self.assertEqual(producer["mass"], reference["mass"])

    def test_contract_alias_defaults_are_once_per_resolved_contract_and_must_agree(self):
        models = {"m": model(), "alias": model()}
        document = graph({"s": {"calls": [call("t", alias="alias")], "next": stop()}},
                         models=models, registers={"r": {"model": "m"}})
        accepted = kernel({"m": distribution(("x", 1, "1/1"))})
        self.assertEqual(independent_histogram(document, accepted, {}, 1)["status"], "complete")
        conflict = kernel({"m": distribution(("x", 1, "1/1")),
                           "alias": distribution(("y", 1, "1/1"))})
        with self.assertRaisesRegex(ReferenceError, "same-contract"):
            independent_histogram(document, conflict, {}, 1)

    def test_resource_exhaustion_is_unknown_without_partial_histogram(self):
        document = graph({
            "loop": {"calls": [call("t")], "next": {"kind": "public",
                "guard": {"value": "r", "op": "<=", "limit": 1},
                "then": "loop", "else": "done"}},
            "done": {"calls": [], "next": stop()},
        }, entry="loop")
        outcomes = distribution(("a", 1, "1/2"), ("bb", 2, "1/2"))
        result = independent_histogram(document, kernel(outcomes), {}, 8, max_paths=2)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["histogram"])
        self.assertIsNone(result["mass"])
        self.assertIn("path limit", result["diagnostic"])

    def test_cumulative_byte_work_cap_fails_closed_and_validates_bounds(self):
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        channel = kernel(distribution(("x", 1, "1/2"), ("y", 1, "1/2")))
        complete = independent_histogram(document, channel, {}, 1)
        self.assertEqual(complete["status"], "complete")
        self.assertGreater(complete["work_bytes"], 2)
        one_byte_short = independent_histogram(document, channel, {}, 1,
                                               max_work_bytes=complete["work_bytes"] - 1)
        self.assertEqual(one_byte_short["status"], "unknown")
        self.assertIsNone(one_byte_short["histogram"])
        self.assertIsNone(one_byte_short["mass"])

        result = independent_histogram(document, channel, {}, 1, max_work_bytes=1)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["histogram"])
        self.assertIsNone(result["mass"])
        self.assertEqual(result["work_bytes"], 2)
        self.assertIn("byte-work", result["diagnostic"])
        for invalid in (0, 1024 * 1024 * 1024 + 1):
            with self.subTest(max_work_bytes=invalid), self.assertRaises(ReferenceError):
                independent_histogram(document, channel, {}, 1, max_work_bytes=invalid)

    def test_strict_exact_probability_and_outcome_validation(self):
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        bad_kernels = [
            kernel(distribution(("a", 1, 0.5))),
            kernel(distribution(("a", 1, "01/2"), ("b", 1, "1/2"))),
            kernel(distribution(("a", 1, "1/3"))),
            kernel(distribution(("long", 1, "1/1"))),
            kernel(distribution(("a", 9, "1/1"))),
        ]
        for bad in bad_kernels:
            with self.subTest(kernel=bad), self.assertRaises(ReferenceError):
                independent_histogram(document, bad, {}, 1)

    def test_rule_history_rejects_noncomplete_or_secret_bearing_event(self):
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        event = {"contract": CONTRACT, "ordinal": 0, "template": "t", "arguments": [],
                 "response": "x", "input_tokens": 1, "output_tokens": 1, "secret": False}
        rules = [{"model": "m", "history": [event], "outcomes": distribution(("x", 1, "1/1"))}]
        with self.assertRaisesRegex(ReferenceError, "unknown"):
            independent_histogram(document, kernel(window=1, rules=rules), {}, 1)

    def test_input_and_graph_store_are_typed_and_bounded(self):
        document = graph({"s": {"calls": [], "next": stop()}},
                         inputs={"q": {"type": "text", "label": "public", "max_tokens": 1}},
                         registers={"r": {"model": "m"}})
        for store in ({}, {"q": "é"}, {"q": False}, {"q": "ab"}):
            with self.subTest(store=store), self.assertRaises(ReferenceError):
                independent_histogram(document, kernel(), store, 1)

    def test_duplicate_json_keys_and_unknown_schema_fields_are_rejected(self):
        duplicate_graph = ('{"format":"orchlang-request-graph","format":"wrong"}')
        with self.assertRaisesRegex(ReferenceError, "duplicate"):
            independent_histogram(duplicate_graph, kernel(), {}, 1)
        document = graph({"s": {"calls": [call("t")], "next": stop()}})
        malformed = copy.deepcopy(kernel())
        malformed["defaults"]["m"][0]["extra"] = "ignored?"
        with self.assertRaisesRegex(ReferenceError, "unknown"):
            independent_histogram(document, malformed, {}, 1)


if __name__ == "__main__":
    unittest.main()
