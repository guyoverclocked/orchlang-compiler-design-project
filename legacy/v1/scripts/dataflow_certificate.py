"""Run the verified dataflow decision procedure (legacy saved-plan support)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.dataflow_gate import issue, bind_certificate, read_source


def run_checker(lean, cases, directory, record_prefix=None, decision=False):
    result, logs, commands = [], [], []
    version=subprocess.run([str(lean),'--version'],capture_output=True,text=True,timeout=30)
    if version.returncode or 'version 4.19.0,' not in version.stdout:
        raise ValueError('dataflow certificates require Lean 4.19.0')
    with tempfile.TemporaryDirectory(prefix='dataflow-json-', dir=directory) as temp:
        for start in range(0,len(cases),16):
            chunk=cases[start:start+16]
            batch = Path(temp)/f'batch-{start//16:03d}.json'
            batch.write_text(json.dumps(chunk, ensure_ascii=False),encoding='utf-8',newline='\n')
            argv=[str(lean),'--run',str(ROOT/'proof/DataflowCore.lean')]
            if decision:
                argv.append('decide')
            argv.append(str(batch))
            started=time.perf_counter()
            process = subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=180)
            commands.append(dict(argv=argv,case_offset=start,cases=len(chunk),exit=process.returncode,
                                 seconds=time.perf_counter()-started,lean_version=version.stdout.strip(),
                                 stdout=process.stdout,stderr=process.stderr))
            if record_prefix:
                (Path(directory)/(record_prefix+'-commands.json')).write_text(
                    json.dumps(commands,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
            if process.returncode or 'sorryAx' in process.stdout or "uses 'sorry'" in process.stdout:
                raise ValueError('dataflow checker failed: '+process.stderr+process.stdout)
            checked = json.loads(process.stdout.splitlines()[-1])
            if len(checked) != len(chunk):
                raise ValueError('malformed dataflow checker response')
            result.extend(checked)
            logs.extend(process.stdout.splitlines()[:-1])
        return result, '\n'.join(logs)+'\n'+json.dumps(result,ensure_ascii=False)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['decide','issue','check'])
    p.add_argument('source',type=Path)
    p.add_argument('certificate',type=Path,nargs='?')
    p.add_argument('--lean',required=True,type=Path)
    args=p.parse_args()
    data=args.source.read_bytes()
    if args.mode=='decide':
        if args.certificate is not None:
            p.error('decide takes a source and --lean, without a saved plan')
        source=read_source(data)
        with tempfile.TemporaryDirectory(prefix='dataflow-decision-') as temp:
            results,_=run_checker(args.lean.resolve(),[dict(program=source['program'],execute=[])],temp,decision=True)
        accepted=results[0]['checked']
        print(json.dumps(dict(status='accepted' if accepted else 'rejected',
                              source_sha256=source['source_sha256'],
                              judgment='shared-public text-dataflow resource-distribution independence',
                              trusted_boundary='Python source reader; not C++ IFC or source budget')))
        return int(not accepted)
    if args.certificate is None:
        p.error('legacy issue/check requires a saved-plan path')
    certificate=issue(data) if args.mode=='issue' else json.loads(args.certificate.read_text(encoding='utf-8'))
    case=bind_certificate(data,certificate)
    results,_=run_checker(args.lean.resolve(),[case],args.certificate.resolve().parent)
    if results != [dict(checked=True,executions=[])]:
        raise ValueError('Lean rejected dataflow certificate')
    if args.mode=='issue':
        with args.certificate.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(certificate,stream,indent=2,ensure_ascii=False)
            stream.write('\n')
    print(json.dumps(dict(status='checked',source_sha256=certificate['source_sha256'],
                         method='verified decision procedure; saved plan is diagnostic output',
                         scope='text-dataflow; shared public inputs; trusted source reader; no budget/provider guarantee')))


if __name__=='__main__':
    raise SystemExit(main())
