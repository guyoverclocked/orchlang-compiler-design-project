"""Audit-only probes. Run from any directory; uses the fresh audit executable.
Does not change compiler source or the checked-in benchmark results.
"""
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TC = Path(os.environ['LOCALAPPDATA']) / 'Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin'
os.environ['PATH'] = str(TC) + os.pathsep + os.environ['PATH']
EXE = HERE / 'orchc.exe'
cases = {
'literal': '''workflow Literal budget 100 {
 model m = mock("m") max_tokens 1;
 prompt p(x: text) -> text = "{x}";
 let y: text = call p("") using m;
 output y;
}''',
'boolean': '''workflow Boolean budget 100 {
 model m = mock("m") max_tokens 1;
 prompt p(x: boolean) -> text = "{x}";
 let y: text = call p(false) using m;
 output y;
}''',
'split': '''workflow Split budget 1000 {
 input flag: boolean max_tokens 1;
 input wide: text max_tokens 200;
 input narrow: text max_tokens 0;
 model small = mock("small") max_tokens 1;
 model large = mock("large") max_tokens 100;
 prompt p(x: text) -> text = "{x}";
 if flag {
   let a: text = call p(wide) using small;
 } else {
   let b: text = call p(narrow) using large;
 }
 output narrow;
}''',
'shadow': '''workflow Shadow budget 10000 {
 input flag: boolean max_tokens 1;
 input src: text max_tokens 0;
 model m = mock("outer") max_tokens 1;
 prompt p(x: text) -> text = "{x}";
 if flag {
   model m = mock("inner") max_tokens 1000;
 }
 let y: text = call p(src) using m;
 output y;
}''',
'equal_bounds': '''workflow EqualBounds budget 1000 {
 secret s: text max_tokens 1;
 input x: text max_tokens 100;
 input y: text max_tokens 100;
 model m = mock("m") max_tokens 10;
 prompt p(t: text) -> text = "{t}";
 if tokens(s) == 0 {
   let a: text = call p(x) using m;
 } else {
   let b: text = call p(y) using m;
 }
 output "done";
}'''
}

def run(*args):
    p = subprocess.run([str(EXE), *map(str,args)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

report = []
for name, source in cases.items():
    path = HERE / (name + '.orch')
    path.write_text(source+'\n', encoding='utf-8')
    code,out,err = run('certify', path)
    row = {'case':name, 'certify_exit':code, 'errors':err}
    if not code:
        bound = json.loads(out)['workflows'][0]['bound']
        row['bound'] = bound
        for seed in range(1,101):
            rc, trace, error = run('run',path,'--seed',seed)
            assert rc == 0, error
            counts = {}
            match = re.search(r'actual tokens\s+(\d+)\s+\(input (\d+) \+ output (\d+)\)', trace)
            if match:
                counts = {'actual':int(match[1]), 'output':int(match[3])}
            for line in trace.splitlines():
                fields = line.split()
                if len(fields)>2 and fields[:2] in [['actual','tokens'],['output','tokens']]:
                    counts[fields[0]] = int(fields[2])
            if counts.get('actual',0)>bound['total_tokens'] or counts.get('output',0)>bound['guaranteed_tokens']:
                row['first_violation'] = {'seed':seed, 'trace':trace}
                break
    report.append(row)

# Run the existing harness against our fresh build into an audit-only directory.
spec = importlib.util.spec_from_file_location('evaluation',ROOT/'bench/evaluate.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
evaluation.ORCHC = str(EXE)
evaluation.RESULTS = str(HERE/'benchmark')
if '--skip-benchmark' not in sys.argv:
    evaluation.main()

examples = []
valid = list((ROOT/'examples/valid').glob('*.orch'))
valid += [ROOT/'examples/boundary'/n for n in ['zero_budget.orch','long_identifier.orch','retry_one.orch','empty_branch.orch']]
invalid = list((ROOT/'examples/invalid').glob('*.orch')) + [ROOT/'examples/boundary/empty_workflow.orch']
for expected,paths in [(True,valid),(False,invalid)]:
    for path in paths:
        code,out,err=run('check',path)
        examples.append({'file':str(path.relative_to(ROOT)), 'expected_accept':expected, 'exit':code, 'match':(code==0)==expected})
report.append({'example_checks':examples})
(HERE/'findings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report[:-1],indent=2))
print('Example checks:',len(examples),'passed:',sum(r['match'] for r in examples))
