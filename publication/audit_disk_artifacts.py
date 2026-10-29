"""Inventory additional disk snapshots and bind the review archive, read only."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EXTRA=Path(r'C:\Users\nambi\Documents\OrchLang Publication Work')
FOLDERS=['dataflow-freeze-v1','dataflow-freeze-v2','dataflow-freeze-v3','dataflow-freeze-v4','dataflow-freeze-v5',
         'scientific-core-clean-v1','github-publication-check-v1','release-candidate-v4']

def hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ('src','include','runtime','proof','scripts','tests') for p in (root/name).rglob('*')
            if p.is_file() and p.suffix in {'.cpp','.hpp','.py','.lean'} and '__pycache__' not in p.parts}

def main():
    baseline=hashes(ROOT/'disk-snapshot')
    result={}
    for name in FOLDERS:
        directory=EXTRA/name
        if not directory.exists(): continue
        h=hashes(directory)
        p=subprocess.run(['git','-C',str(directory),'rev-parse','HEAD'],capture_output=True,text=True)
        result[name]={'head':p.stdout.strip() if p.returncode==0 else None,'code_files':len(h),
                      'different_or_missing_from_current':[n for n in sorted(set(h)|set(baseline)) if h.get(n)!=baseline.get(n)],
                      'hashes':h}
    archive=EXTRA/'deliverables/OrchLang-scientific-review-2026-10-24-validated.zip'
    validation=json.loads((ROOT/'disk-snapshot/publication/SCIENTIFIC_REVISION_VALIDATION.json').read_text())
    result['review_archive']={'path':str(archive),'bytes':archive.stat().st_size,
                             'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                             'matches_repository_receipt':hashlib.sha256(archive.read_bytes()).hexdigest()==validation['sha256']}
    lit=EXTRA/'private-literature/HARD-KLAIM.txt'
    result['hard_klaim']={'path':str(lit),'sha256':hashlib.sha256(lit.read_bytes()).hexdigest(),
                          'scope':'Existing locally supplied full-text extraction, pages 1-3 and theorem sections inspected; not redistributed.'}
    (ROOT/'evidence/additional-disk-artifacts.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({n:{k:v for k,v in d.items() if k!='hashes'} for n,d in result.items()},indent=2))

if __name__=='__main__':main()
