"""Source-message interpolation must precede the template's nonlinear trim."""
import re
import unittest
from pathlib import Path
from orchlang import compiler as K,core as C,models as M,syntax


def literal(value):
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')+'"'


class Templates(unittest.TestCase):
    def test_lowered_requests_match_value_level_templates(self):
        cases=[[('user','{x}')],[('system','  {x}  '),('user','\n {y}\n')],
               [('user','prefix {x} suffix')],[('user','{x}{y}{x}')],
               [('user','left\0literal {x} \0tail')]]
        spaces=[chr(i) for i in range(0x110000) if chr(i).isspace()]
        values=['','x','  x  ','\n\tx\u00a0','\0x\0','x\\y','\u200bx\u200b']+[c+'x'+c for c in spaces]
        for family in ('llama3','qwen2'):
            profile=M.Profile('m','unused',family)
            for messages in cases:
                names=sorted(set(re.findall(r'\{(\w+)\}',''.join(v for _,v in messages))))
                source='workflow W { '+''.join(f'input {n}: text secret max_tokens 64; ' for n in names)
                source+='model m = "m"; prompt p('+','.join(names)+') = '
                source+=' '.join(role+' '+literal(text) for role,text in messages)+'; '
                source+='let out = call p('+','.join(names)+') using m max_tokens 6; output out; }'
                program=K.lower(syntax.parse(source),{'m':profile})
                call=C.calls(program.body)[0]
                for value in values:
                    args={name:value if i==0 else value[::-1] for i,name in enumerate(names)}
                    store={program.slots[name]:text for name,text in args.items()}
                    actual=C.eval_expr(store,call.req)
                    concrete=[(role,re.sub(r'\{(\w+)\}',lambda m:args[m[1]],text)) for role,text in messages]
                    with self.subTest(family=family,messages=messages,value=repr(value)):
                        self.assertEqual(actual,profile.tmpl.render(concrete))

    def test_lean_whitespace_classification_matches_python_exhaustively(self):
        source=(Path(__file__).resolve().parents[1]/'proof/ShapeCore.lean').read_text(encoding='utf-8')
        group=re.search(r'def templateWhitespace.*?\(\[(.*?)\] : List Nat\)',source,re.S).group(1)
        actual={int(x) for x in group.replace('\n','').split(',')}
        expected={i for i in range(0x110000) if chr(i).isspace()}
        self.assertEqual(actual,expected)
        self.assertEqual(len(actual),29)


if __name__=='__main__':unittest.main()
