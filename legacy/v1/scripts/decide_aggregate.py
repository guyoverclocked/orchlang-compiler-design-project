"""Verified aggregate-only decision for two independent closed calls per arm."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.aggregate_gate import read_source


def run_checker(lean,cases,directory,record_prefix=None,private_results=False):
    version=subprocess.run([str(lean),'--version'],capture_output=True,text=True,timeout=30)
    if version.returncode or 'version 4.19.0,' not in version.stdout:
        raise ValueError('aggregate decision requires Lean 4.19.0')
    results,commands=[],[]
    with tempfile.TemporaryDirectory(prefix='aggregate-json-',dir=directory) as temp:
        for start in range(0,len(cases),32):
            chunk=cases[start:start+32]
            batch=Path(temp)/'batch.json'
            batch.write_text(json.dumps(chunk,ensure_ascii=False),encoding='utf-8',newline='\n')
            argv=[str(lean),'--run',str(ROOT/'proof/AggregateReordering.lean')]
            if private_results:
                argv.append('private')
            argv.append(str(batch))
            started=time.perf_counter()
            run=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=180)
            commands.append(dict(argv=argv,offset=start,cases=len(chunk),exit=run.returncode,
                                 seconds=time.perf_counter()-started,stdout=run.stdout,stderr=run.stderr,
                                 lean_version=version.stdout.strip()))
            if record_prefix:
                (Path(directory)/(record_prefix+'-commands.json')).write_text(
                    json.dumps(commands,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
            if run.returncode or 'sorryAx' in run.stdout or "uses 'sorry'" in run.stdout:
                raise ValueError('aggregate checker failed: '+run.stderr+run.stdout)
            output=json.loads(run.stdout.splitlines()[-1])
            if len(output)!=len(chunk):
                raise ValueError('incomplete aggregate checker response')
            results.extend(output)
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--lean',required=True,type=Path)
    p.add_argument('--finite-kernels',type=Path,help='Optional explicit normalized finite tables; no provider dispatch')
    p.add_argument('--private-results',type=Path,help='New archive path for full-action-indexed finite response multisets')
    args=p.parse_args()
    if bool(args.finite_kernels) != bool(args.private_results):
        p.error('--finite-kernels and --private-results must be supplied together')
    source=read_source(args.source.read_bytes())
    with tempfile.TemporaryDirectory(prefix='aggregate-decision-') as temp:
        if args.finite_kernels:
            kernels=json.loads(args.finite_kernels.read_text(encoding='utf-8'))
            case=dict(program=source['program'],kernels=kernels)
            result=run_checker(args.lean.resolve(),[case],temp,private_results=True)[0]
            archive=dict(source_sha256=source['source_sha256'],
                         semantics='trusted-caller archive; private_results are multisets, not public source output',
                         outcome=result)
            with args.private_results.open('x',encoding='utf-8',newline='\n') as output:
                json.dump(archive,output,ensure_ascii=False,indent=2)
                output.write('\n')
        else:
            result=run_checker(args.lean.resolve(),[dict(program=source['program'],execute=False)],temp)[0]
    print(json.dumps(dict(status='accepted' if result['checked'] else 'rejected',
                          source_sha256=source['source_sha256'],
                          judgment='per-contract UTF-8 input/output totals, call counts and failures',
                          assumptions='independent stateless full-action kernels; closed requests',
                          trusted_boundary='Python source reader; not ordered trace, content IFC or budget')))
    return int(not result['checked'])


if __name__=='__main__':
    raise SystemExit(main())
