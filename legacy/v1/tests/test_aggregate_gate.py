from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime.aggregate_gate import read_source,accepts
from runtime.finite_reference import Unsupported


SOURCE=b'''workflow Aggregate budget 1000 {
 secret s:boolean max_tokens 1;
 model m=mock("A") max_tokens 8;
 prompt p(t:text)->text="{t}";
 if s { let a:text=call p("yes") using m; let b:text=call p("no!") using m; }
 else { let b:text=call p("no!") using m; let a:text=call p("yes") using m; }
 output "done";
}'''


class AggregateTests(unittest.TestCase):
    def test_independent_closed_reordering_is_accepted(self):
        self.assertTrue(accepts(read_source(SOURCE)['program']))

    def test_different_request_multiset_is_rejected(self):
        changed=SOURCE.replace(b'else { let b:text=call p("no!")',b'else { let b:text=call p("bad")')
        self.assertFalse(accepts(read_source(changed)['program']))

    def test_response_dependency_fails_closed(self):
        with self.assertRaises(Unsupported):
            read_source(SOURCE.replace(b'p("no!")',b'p(a)',1))

    def test_public_outputs_cannot_be_erased_from_a_branch(self):
        with self.assertRaises(Unsupported):
            read_source(SOURCE.replace(b'if s {',b'if s { output "leak";'))

    def test_branch_count_retry_and_inputs_outside_fragment(self):
        for changed in (SOURCE.replace(b'output "done";',b'input x:text max_tokens 4; output "done";'),
                        SOURCE.replace(b'output "done";',b'retry 2 {} output "done";'),
                        SOURCE.replace(b'let b:text=call p("no!") using m;',b'',1)):
            with self.assertRaises(Unsupported):
                read_source(changed)


if __name__=='__main__':
    unittest.main()
