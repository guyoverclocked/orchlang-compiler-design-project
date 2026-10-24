"""Assemble and hash an offline author-review archive; no publication or upload."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--tested-v3',required=True,type=Path)
    p.add_argument('--tested-v4',required=True,type=Path)
    p.add_argument('--tested-current',type=Path,help='Latest complete core validation when new models were added')
    p.add_argument('--pdf',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    source=args.source.resolve()
    if subprocess.check_output(['git','status','--porcelain'],cwd=source,text=True).strip():
        raise ValueError('review source must be clean')
    # No compiler/runtime/proof/test changes may be hidden by a docs-only release.
    core_files=[path for name in ('src','include','runtime','proof','tests')
                for path in (source/name).rglob('*') if path.is_file() and
                path.suffix in {'.cpp','.hpp','.py','.lean'}]
    core_files += [source/'bench/structural_baseline.py']
    for path in core_files:
        relative=path.relative_to(source)
        for tested in ([args.tested_current] if args.tested_current else [args.tested_v3,args.tested_v4]):
            if sha(path)!=sha(tested/relative):
                raise ValueError('untested core differs: '+str(relative))
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.pdf,out/'OrchLang-software-paper-review.pdf')
    shutil.copyfile(source/'docs/manuscript/highlights.txt',out/'highlights.txt')
    shutil.copyfile(source/'docs/AUTHOR_REVIEW.md',out/'AUTHOR_REVIEW.md')
    def zip_paths(destination, paths, root):
        with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(paths):
                archive.write(path,path.relative_to(root).as_posix())
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None:
                raise ValueError('corrupt archive')
    paths=[p for p in source.rglob('*') if p.is_file() and '.git' not in p.relative_to(source).parts]
    if any(p.suffix in {'.exe','.pdf','.docx','.png','.pyc'} or p.name in {'.env','.envrc'} for p in paths):
        raise ValueError('unexpected binary/private input in source package')
    zip_paths(out/'orchlang-source-and-evidence.zip',paths,source)
    manuscript=source/'docs/manuscript'
    zip_paths(out/'manuscript-latex-source.zip',[p for p in manuscript.rglob('*') if p.is_file()],manuscript)
    bundles=out/'tested-source'
    bundles.mkdir()
    bundle_sources=[('source-v3',args.tested_v3),('source-v4',args.tested_v4),('review-source',source)]
    if args.tested_current:
        bundle_sources.append(('source-dataflow',args.tested_current))
    for name,tree in bundle_sources:
        bundle=bundles/(name+'.bundle')
        subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=tree,check=True,capture_output=True)
        subprocess.run(['git','bundle','verify',str(bundle)],cwd=tree,check=True,capture_output=True)
    note=('OrchLang publication author-review artifact\n\n'
          'Not submitted or publicly released. Read AUTHOR_REVIEW.md first.\n'
          'Source/evidence ZIP contains code, tests, proofs, raw observations and ledgers.\n'
          'LaTeX ZIP is a self-contained project. Compile main.tex twice with elsarticle.\n'
          'Tested-source bundles preserve exact local Git revisions. For example:\n'
          'git clone tested-source/source-v3.bundle reconstructed-v3\n'
          'Run the documented offline checks with new output directories outside the clone.\n'
          'The review revision changes documentation/evidence tooling; core byte identity\n'
          'against the current tested revision was checked during assembly.\n'
          'No runtime binaries, keys, private library papers or model weights are included.\n'
          'Formal claims are closed-core and conditional; no provider privacy is established.\n'
          'API spend/reservations USD 0; approved total cap USD 5.\n')
    (out/'README.txt').write_text(note,encoding='utf-8',newline='\n')
    manifest=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),purpose='local-author-review-not-submission',
                  review_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
                  unchanged_tested_core_files=len(core_files),spent_usd='0.00',
                  core_validation_commit=subprocess.check_output(['git','rev-parse','HEAD'],
                      cwd=args.tested_current or args.tested_v3,text=True).strip(),
                  files={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
                         for p in out.rglob('*') if p.is_file()})
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    zip_paths(out.parent/(out.name+'.zip'),[p for p in out.rglob('*') if p.is_file()],out)
    print(json.dumps(dict(output=str(out),commit=manifest['review_commit'],
                         tested_core_files=len(core_files),archive=str(out.parent/(out.name+'.zip')))))


if __name__=='__main__':
    main()
