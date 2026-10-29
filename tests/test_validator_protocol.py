"""Reject vacuous/malformed receipts and preserve Unicode inside JSON records."""
import json
import subprocess
import unittest
from unittest.mock import patch
from orchlang import validate


class Protocol(unittest.TestCase):
    def test_unicode_line_separators_are_data(self):
        expected=[dict(accepted=True,static_shape=[['tool','x\u0085\u2028\u2029y']])]
        output='proof diagnostics\n'+json.dumps(expected,ensure_ascii=False)+'\n'
        process=subprocess.CompletedProcess([],0,output,'')
        with patch.object(validate.subprocess,'run',return_value=process):
            self.assertEqual(validate.lean_validate_batch([{}]),expected)

    def test_wrong_denominators_types_and_exit_status_cannot_be_receipts(self):
        for status,verdict in ((0,[]),(0,[{'accepted':1}]),(0,[{'accepted':False}]),(1,[{'accepted':True}])):
            process=subprocess.CompletedProcess([],status,json.dumps(verdict)+'\n','')
            with self.subTest(status=status,verdict=verdict),patch.object(validate.subprocess,'run',return_value=process):
                with self.assertRaises(RuntimeError):validate.lean_validate_batch([{}])


if __name__=='__main__':unittest.main()
