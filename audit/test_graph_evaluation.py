#!/usr/bin/env python3
"""Keep request witnesses distinct from usage-observer witnesses."""
import copy
import unittest
from evaluate_graphs import billing_vector, requests


class ObservationTests(unittest.TestCase):
    def example(self):
        contract={'provider':'mock','model':'m','max_tokens':8,'has_unit_price':False,'unit_price':0.0}
        event={'contract':contract,'ordinal':0,'template':'Process','arguments':['x'],
               'response':'abcd','input_tokens':3,'output_tokens':1}
        return {'trace':[event],'stopped':True}

    def test_request_difference_does_not_imply_billing_difference(self):
        left=self.example();right=copy.deepcopy(left)
        right['trace'][0]['arguments']=['y'];right['trace'][0]['response']='wxyz'
        self.assertNotEqual(requests(left),requests(right))
        self.assertEqual(billing_vector(left),billing_vector(right))

    def test_billing_groups_by_resolved_contract(self):
        run=self.example();second=copy.deepcopy(run['trace'][0]);second['ordinal']=1
        run['trace'].append(second)
        vector=billing_vector(run)
        self.assertEqual(len(vector),1)
        self.assertEqual((vector[0]['call_count'],vector[0]['input_tokens'],vector[0]['output_tokens']),(2,6,2))


if __name__=='__main__':unittest.main()
