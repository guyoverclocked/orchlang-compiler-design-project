import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.structural_baseline import structural_bound


def node(i, kind, region="root", **attrs):
    return dict(id=i, kind=kind, region=region, attributes=attrs)


class BaselineTests(unittest.TestCase):
    def test_nested_retry_and_branch_hand_calculation(self):
        # 3 * max(2+5, 7+1) = 24 total, independent maxima 21 in / 15 out.
        ir = dict(nodes=[node(1, "Retry", bound="3"),
                         node(2, "Branch", "root/retry@1#1"),
                         node(3, "Call", "root/retry@1#1/then@1#2", in_tokens="2", out_tokens="5"),
                         node(4, "Call", "root/retry@1#1/else@1#2", in_tokens="7", out_tokens="1")])
        self.assertEqual(structural_bound(ir), dict(input=21, output=15, total=24))

    def test_sibling_branches_on_same_line_keep_distinct_regions(self):
        ir = dict(nodes=[node(1, "Branch"),
                         node(2, "Call", "root/then@1#1", in_tokens="1", out_tokens="2"),
                         node(3, "Branch"),
                         node(4, "Call", "root/else@1#3", in_tokens="4", out_tokens="1")])
        self.assertEqual(structural_bound(ir)["total"], 8)

    def test_unknown_or_orphan_ir_is_infrastructure_error(self):
        with self.assertRaises(ValueError):
            structural_bound(dict(nodes=[node(1, "Call", "root/then@9#99", in_tokens="1", out_tokens="1")]))
        with self.assertRaises(ValueError):
            structural_bound(dict(nodes=[node(1, "NovelSyntax")]))


if __name__ == "__main__":
    unittest.main()
