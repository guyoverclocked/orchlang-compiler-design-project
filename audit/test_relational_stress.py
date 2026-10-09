"""Unit tests for the independent relational stress reference model."""

from __future__ import annotations

import unittest

from relational_stress import (
    FAMILIES,
    Contract,
    Lit,
    Var,
    build_case,
    compare_secret_assignments,
    oracle_response,
    public_scenarios,
    run_reference,
    secret_assignments,
    substitute,
    utf8_bytes,
)


class RelationalStressReferenceTests(unittest.TestCase):
    def test_complete_template_substitution_uses_concrete_utf8_text(self) -> None:
        rendered = substitute("雪:{a}/{b}", ("a", "b"), ("é🙂", "line\nbreak"))
        self.assertEqual(rendered, "雪:é🙂/line\nbreak")
        self.assertEqual(utf8_bytes(rendered), len(rendered.encode("utf-8")))

    def test_oracle_is_deterministic_contract_ordinal_and_request_keyed(self) -> None:
        contract = Contract("mock", "full-text-test", 32)
        request = "prompt:雪🙂"
        output = oracle_response(contract, 3, request, 9)
        self.assertEqual(output, oracle_response(contract, 3, request, 9))
        self.assertLessEqual(utf8_bytes(output), contract.max_tokens)
        # Exercise the request dimension over a small fixed set; this guards
        # against accidentally regressing to the compiler's ordinal-only mock.
        outputs = {
            oracle_response(contract, 3, f"{request}:{suffix}", 9)
            for suffix in ("a", "b", "c", "d", "e", "f", "g", "h")
        }
        self.assertGreater(len(outputs), 1)
        self.assertNotEqual(output, oracle_response(contract, 4, request, 9))

    def test_balanced_and_nested_secret_shapes_have_equal_full_traces(self) -> None:
        for family in ("balanced_chain", "nested_secret_chain", "shadowed_public_chain"):
            with self.subTest(family=family):
                case = build_case(f"unit-{family}", 7331, family)
                result = compare_secret_assignments(
                    case.workflow,
                    public_scenarios(case.workflow)[:4],
                    seeds=(1, 7),
                    failure_percent=40,
                )
                self.assertEqual(result["request_mismatches"], 0)
                self.assertEqual(result["usage_mismatches"], 0)
                self.assertGreater(result["comparisons"], 0)

    def test_shared_aliases_advance_one_contract_ordinal(self) -> None:
        case = build_case("unit-aliases", 7331, "balanced_chain")
        run = run_reference(
            case.workflow,
            {"x": "public é", "y": "別の値", "route": False},
            {"s0": True},
            seed=17,
        )
        trace = run["request_trace"]
        self.assertGreaterEqual(len(trace), 2)
        ordinals = [entry["ordinal"] for entry in trace]
        self.assertEqual(ordinals, list(range(len(ordinals))))
        self.assertEqual(len({entry["contract"] for entry in trace}), 1)
        self.assertTrue(all("request" in entry for entry in trace))

    def test_nested_shadowing_binds_inner_result_for_following_call(self) -> None:
        case = build_case("unit-shadow", 7331, "shadowed_public_chain")
        run = run_reference(
            case.workflow,
            {"x": "root text", "y": "unused", "route": True},
            {"s0": True},
            seed=17,
        )
        requests = [entry["request"] for entry in run["request_trace"]]
        self.assertGreaterEqual(len(requests), 3)
        # The nested `current` shadows the outer `current`, and `tail` must
        # consume that inner result (the third request begins with its bytes).
        inner_response = oracle_response(
            case.workflow.model_map()["model_right"], 1, requests[1], 17
        )
        self.assertIn(inner_response, requests[2])
        self.assertEqual(run["accounting_checks"], len(requests))

    def test_retry_trace_is_shared_and_bounded(self) -> None:
        case = build_case("unit-retry", 7331, "bounded_retry_chain")
        result = compare_secret_assignments(
            case.workflow,
            public_scenarios(case.workflow)[:2],
            seeds=(1, 7, 19),
            failure_percent=70,
        )
        self.assertEqual(result["request_mismatches"], 0)
        self.assertEqual(result["usage_mismatches"], 0)
        self.assertGreater(result["retry_attempts"], 0)
        for secrets in secret_assignments(case.workflow):
            run = run_reference(
                case.workflow,
                {"x": "x", "y": "y", "route": False},
                secrets,
                seed=1,
                failure_percent=70,
            )
            self.assertTrue(all(1 <= attempts <= 4 for attempts in run["retry_attempts"]))

    def test_distinct_lexical_arguments_can_have_no_equal_value_witness(self) -> None:
        case = build_case("unit-equal-argument-values", 7331, "bounded_retry_chain", "argument")
        scenarios = [
            {"x": "same é text", "y": "same é text", "route": route}
            for route in (False, True)
        ]
        probe = compare_secret_assignments(
            case.workflow, scenarios, seeds=(1, 7, 19), failure_percent=40
        )
        self.assertGreater(probe["comparisons"], 0)
        self.assertEqual(probe["request_mismatches"], 0)
        self.assertEqual(probe["usage_mismatches"], 0)

    def test_generated_family_catalog_and_mutations_are_closed(self) -> None:
        self.assertEqual(
            FAMILIES,
            (
                "balanced_chain",
                "public_nested_chain",
                "bounded_retry_chain",
                "nested_secret_chain",
                "public_outer_secret",
                "shadowed_public_chain",
            ),
        )
        for family in FAMILIES:
            with self.subTest(family=family):
                case = build_case("unit-case", 991, family)
                self.assertIn("workflow Stress", case.source)
                self.assertIn("if s0", case.source)
                self.assertTrue(case.source.endswith("}\n"))


if __name__ == "__main__":
    unittest.main()
