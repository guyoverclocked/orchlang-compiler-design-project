import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchlang import assurance as A,compiler as K,models as M,validate
text=Path('paper/main.tex').read_text()
source=re.search(r'\\begin\{lstlisting\}\s*(workflow.*?)\\end\{lstlisting\}',text,re.S).group(1).encode()
profiles={'llama1b':M.Profile('llama1b','unused','llama3')}
program,binding=A.source_binding(source,profiles)
shaped=K.Shaper(program,profiles,{'llama1b':M.CharTokenizer()},'ours').run()
_,_,verdict=A.validate_candidates(source,profiles,{'ours':shaped})
assert verdict['ours']['accepted']
missing=validate.payload(program.high_vars(),program.body,shaped,program.secret_inputs())
del missing['secret_inputs']
try:validate.lean_validate_batch([missing])
except RuntimeError as error:rejected=True;reason=str(error).strip()
else:rejected=False;reason='unexpected acceptance'
assert rejected
out={'purpose':'manuscript example syntax/core check and mandatory-secret negative control',
     'example_accepted':True,'missing_secret_field_rejected':rejected,'rejection':reason,
     'binding_sha256':binding['binding_sha256'],'unit':'character-token audit only'}
Path('publication/evidence/core/manuscript-example-check.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
