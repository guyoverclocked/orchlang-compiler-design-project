import importlib.util
from pathlib import Path
import unittest


class Observer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('numpy') is None:
            raise unittest.SkipTest('analysis tier requires NumPy')
        path=Path(__file__).resolve().parents[1]/'experiments/analyze.py'
        spec=importlib.util.spec_from_file_location('shape_analysis',path)
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    def test_tool_identity_is_observable_but_analysis_fields_are_hidden(self):
        a=[['tool','first',0,0,0.1,False,0,0],['llm','m',10,4,0.2,False,1,2]]
        b=[['tool','upper',0,0,0.1,True,99,12],['llm','m',10,4,0.2,True,9,99]]
        self.assertNotEqual(self.module.observed(a),self.module.observed(b))
        b[0][1]='first'
        self.assertEqual(self.module.observed(a),self.module.observed(b))
        labels=['llm:m','tool:first']
        features=self.module.features(self.module.observed(a),2,labels)
        self.assertEqual(features[:4],[2,1,10,4])

    def test_weak_baselines_keep_tool_events(self):
        row={'trace':[['tool','first',0,0,0.1,False,0,0],['llm','m',10,4,0.2,False,1,2]]}
        self.assertEqual(self.module.derive_padonly(row,{'1':[20,8]})[0],row['trace'][0])
        self.assertEqual(self.module.derive_noforce(row)[0],row['trace'][0])


if __name__=='__main__':unittest.main()
