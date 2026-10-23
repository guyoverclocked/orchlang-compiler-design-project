"""Derive the dataflow manuscript supplement from successful retained runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--cpu',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    m,cpu=read(args.run/'manifest.json'),read(args.cpu/'manifest.json')
    if m['status']!='completed' or cpu['status']!='completed' or m['failures'] or cpu['failures']:
        raise ValueError('cannot derive a successful table from failed or incomplete runs')
    commands=read(args.cpu/'commands.json')
    cpp=next(re.search(r'Passed (\d+)/(\d+) tests',c['stdout']) for c in commands if 'orchlang_tests' in c['argv'][0])
    py=next(re.search(r'Ran (\d+) tests',c['stderr']) for c in commands if 'unittest' in c['argv'])
    if cpp is None or py is None or cpp[1]!=cpp[2] or not cpu['proof_checked']:
        raise ValueError('missing tests or proofs')
    metrics={k:m[k] for k in ('source_programs','accepted','execution_contexts','accepted_finite_counterexamples',
              'source_reconstruction_disagreements','lean_normalization_disagreements',
              'lean_reference_disagreements','lean_replay_disagreements','cpp_accepted','cpp_e230_cases',
              'boundary_cases','boundary_paths','source_tampers_rejected','altered_plans_rejected',
              'invalid_evaluator_inputs_rejected')}
    proof_count=sum(len(c['argv'])==2 and str(c['argv'][1]).endswith('.lean') for c in commands)
    metrics.update(cpp_tests=int(cpp[1]),python_tests=int(py[1]),proof_files=proof_count)
    evidence={}
    for group,directory in [('dataflow',args.run),('cpu',args.cpu)]:
        for file in sorted(directory.glob('*.json')):
            evidence[group+'/'+file.name]=dict(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),path=str(file))
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'summary.json').write_text(json.dumps(dict(metrics=metrics,evidence=evidence),indent=2)+'\n',encoding='utf-8',newline='\n')
    def macro_name(key):
        if key=='cpp_e230_cases':
            return 'CppSecretArgumentCases'  # TeX control sequence names contain letters only.
        return ''.join(x.title() for x in key.split('_'))
    macros=''.join('\\newcommand{\\evDataflow'+macro_name(k)+'}{'+str(v)+'}\n' for k,v in metrics.items())
    (args.output/'dataflow-metrics.tex').write_text(macros,encoding='utf-8',newline='\n')
    table='| Endpoint | Value |\n|---|---:|\n'+''.join('| '+k+' | '+str(v)+' |\n' for k,v in metrics.items())
    (args.output/'table.md').write_text(table,encoding='utf-8',newline='\n')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':
    main()
