import unittest
from orchlang.ledger import UsageLedger,AdmissionRefused


class Ledger(unittest.TestCase):
    def test_reserve_confirm_and_refuse_before_dispatch(self):
        ledger=UsageLedger({'m':{'input':10,'output':8,'calls':2}})
        first=ledger.reserve('m',5,4);ledger.confirm(first,5,2)
        second=ledger.reserve('m',5,4)
        with self.assertRaises(AdmissionRefused):ledger.reserve('m',1,1)
        ledger.confirm(second,5,4)
        state=ledger.snapshot()
        self.assertTrue(state['usage_complete'])
        self.assertEqual(state['confirmed']['m'],{'input':10,'output':6,'calls':2})

    def test_unconfirmed_attempt_retains_reservation(self):
        ledger=UsageLedger({'m':{'output':8}})
        ledger.reserve('m',5,8)
        self.assertFalse(ledger.snapshot()['usage_complete'])
        with self.assertRaises(AdmissionRefused):ledger.reserve('m',1,1)
        self.assertEqual(ledger.snapshot()['confirmed']['m']['output'],0)
        self.assertEqual(ledger.snapshot()['unconfirmed'][0]['reservation']['output'],8)

    def test_model_units_are_separate_and_invalid_values_fail(self):
        ledger=UsageLedger({'a':{'output':1},'b':{'output':100}})
        first=ledger.reserve('a',0,1);ledger.confirm(first,0,1)
        with self.assertRaises(AdmissionRefused):ledger.reserve('a',0,1)
        second=ledger.reserve('b',0,100);ledger.confirm(second,0,100)
        self.assertEqual(set(ledger.snapshot()['confirmed']),{'a','b'})
        for value in (True,1.5,-1):
            with self.assertRaises(ValueError):UsageLedger({'m':{'output':value}})


if __name__=='__main__':unittest.main()
