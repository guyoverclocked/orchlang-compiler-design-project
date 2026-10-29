"""Read-only source inventory and exact comparisons for the independent audit."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DISK = ROOT.parent / 'orchlang-compiler-design-project'

def git(path, *args):
    p = subprocess.run(['git', '-C', str(path), *args], capture_output=True, encoding='utf-8', errors='replace', check=True)
    return p.stdout

def inventory(path):
    tracked = git(path, 'ls-files', '-z').split('\0')
    untracked = git(path, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
    files = {}
    for name in sorted(set(tracked + untracked) - {''}):
        file = path / name
        if file.is_file():
            data = file.read_bytes()
            files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'untracked': name in untracked}
    return {'path': str(path), 'head': git(path, 'rev-parse', 'HEAD').strip(),
            'branch': git(path, 'branch', '--show-current').strip(),
            'status': git(path, 'status', '--porcelain=v1'),
            'refs': git(path, 'show-ref'), 'files': files,
            'timestamp_utc': datetime.now(timezone.utc).isoformat()}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['before', 'compare', 'after'])
    args = parser.parse_args()
    evidence = ROOT / 'evidence'
    if args.mode in ('before', 'after'):
        record = inventory(DISK)
        (evidence / f'disk-{args.mode}.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        if args.mode == 'after':
            before = json.loads((evidence / 'disk-before.json').read_text(encoding='utf-8'))
            differences = [key for key in ('head', 'branch', 'status', 'refs', 'files') if before[key] != record[key]]
            result = {'preserved': not differences, 'different_fields': differences, 'files_checked': len(record['files'])}
            (evidence / 'preservation.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result))
            if differences:
                raise SystemExit(1)
        else:
            print(json.dumps({'head': record['head'], 'files': len(record['files']), 'untracked': sum(x['untracked'] for x in record['files'].values())}))
    else:
        disk = json.loads((evidence / 'disk-before.json').read_text(encoding='utf-8'))
        remote = inventory(ROOT / 'remote')
        (evidence / 'remote-inventory.json').write_text(json.dumps(remote, indent=2) + '\n', encoding='utf-8')
        d, r = disk['files'], remote['files']
        names = sorted(set(d) | set(r))
        changes = [{'path': n, 'status': 'disk-only' if n not in r else 'remote-only' if n not in d else 'different',
                    'disk': d.get(n), 'remote': r.get(n)} for n in names if d.get(n, {}).get('sha256') != r.get(n, {}).get('sha256')]
        repo = ROOT / 'remote'
        history = {'merge_base': git(repo, 'merge-base', 'HEAD', disk['head']).strip(),
                   'ahead_behind': git(repo, 'rev-list', '--left-right', '--count', 'HEAD...' + disk['head']).strip(),
                   'remote_commits': git(repo, 'log', '--format=%H %aI %s', disk['head'] + '..HEAD'),
                   'disk_commits': git(repo, 'log', '--format=%H %aI %s', 'HEAD..' + disk['head']),
                   'diff_stat': git(repo, 'diff', '--stat', 'HEAD', disk['head']),
                   'diff_numstat': git(repo, 'diff', '--numstat', 'HEAD', disk['head'])}
        report = {'disk_head': disk['head'], 'remote_head': remote['head'], 'changes': changes, 'history': history}
        (evidence / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (evidence / 'remote-vs-disk.patch').write_text(git(repo, 'diff', 'HEAD', disk['head'], '--', 'src', 'include', 'runtime', 'proof', 'tests', 'scripts', 'bench', '.github'), encoding='utf-8')
        print(json.dumps({'disk_head': disk['head'], 'remote_head': remote['head'], 'changes': len(changes), 'history': history}, indent=2))

if __name__ == '__main__':
    main()
