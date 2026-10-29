import json
import tempfile
from pathlib import Path
import unittest
from orchlang.models import load_profiles


class Contracts(unittest.TestCase):
    def test_pinned_aliases_share_identity_but_semantic_fields_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory,'models.json')
            base=dict(gguf='same.gguf',template='qwen2',sha256='a'*64,stop=['eos'])
            path.write_text(json.dumps({'b':base,'a':base,'different_stop':{**base,'stop':['other']},
                                        'grammar':{**base,'decoding_grammar':'root ::= "yes"'},
                                        'unverified':{k:v for k,v in base.items() if k!='sha256'}}))
            profiles=load_profiles(str(path))
            self.assertEqual(profiles['a'].key,profiles['b'].key)
            self.assertNotEqual(profiles['a'].key,profiles['different_stop'].key)
            self.assertNotEqual(profiles['a'].key,profiles['grammar'].key)
            self.assertEqual(profiles['unverified'].key,'unverified')


if __name__=='__main__':unittest.main()
