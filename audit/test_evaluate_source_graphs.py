"""Tests for the finite existing-source graph evaluation grid."""
from __future__ import annotations

import unittest

from evaluate_source_graphs import billing_projection, input_scenarios
from source_to_graph import parse_source


class SourceGraphEvaluationGridTests(unittest.TestCase):
    def test_grid_covers_public_booleans_and_bounded_text_and_secret_values(self) -> None:
        workflow = parse_source(b'''workflow Grid budget 100 {
  input public_a: boolean;
  input public_b: boolean;
  input question: text max_tokens 16;
  secret route: boolean;
  secret hidden: text max_tokens 2;
  output "fixed";
}
''')
        public, secrets, secret_names = input_scenarios(workflow)
        self.assertEqual(len(public), 16)  # four public-flag combinations x four text samples
        self.assertEqual({(row["public_a"], row["public_b"]) for row in public},
                         {(False, False), (False, True), (True, False), (True, True)})
        self.assertEqual(secret_names, ["route", "hidden"])
        self.assertEqual(len(secrets), 4)  # both flags x empty or bounded UTF-8 text
        self.assertEqual({row["route"] for row in secrets}, {False, True})
        self.assertTrue(all(len(row["hidden"].encode("utf-8")) <= 8 for row in secrets))
        self.assertTrue(any(value.startswith("é🙂") for row in public
                            for value in row.values() if isinstance(value, str)))
        self.assertTrue(any("\n" in value for row in public for value in row.values()
                            if isinstance(value, str)))

    def test_output_is_outside_billing_projection(self) -> None:
        left = {"trace": [{"input_tokens": 1}], "stopped": True, "output": "left"}
        right = {"trace": [{"input_tokens": 1}], "stopped": True, "output": "right"}
        self.assertEqual(billing_projection(left), billing_projection(right))


if __name__ == "__main__":
    unittest.main()
