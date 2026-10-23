"""Verify published artifact and raw-evidence checksums without network access.

These checks establish byte integrity against committed manifests, not scientific
correctness, author approval, signatures, or independent reproduction.
"""
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def checked_path(root, relative):
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("manifest path must remain inside its directory")
    return path


def verify_hashes(root, entries):
    for relative, expected in entries.items():
        data = checked_path(root, relative).read_bytes()
        digest = expected if isinstance(expected, str) else expected['sha256']
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("checksum mismatch: " + str(root.relative_to(ROOT) / relative))
        if isinstance(expected, dict) and len(data) != expected['bytes']:
            raise ValueError("size mismatch: " + relative)
    return len(entries)


def main():
    publication = ROOT / 'publication'
    manifest = json.loads((publication / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1:
        raise ValueError("unsupported artifact manifest")
    artifact_count = verify_hashes(publication, manifest['files'])
    bundles = {
        'source-v3.bundle': manifest['source_v3_commit'],
        'source-v4.bundle': manifest['source_v4_commit'],
        'source-dataflow.bundle': manifest['core_validation_commit'],
        'review-source.bundle': manifest['source_review_commit'],
    }
    for name, expected_commit in bundles.items():
        path = publication / 'tested-source' / name
        subprocess.run(['git', 'bundle', 'verify', str(path)], cwd=ROOT,
                       check=True, capture_output=True, text=True)
        heads = subprocess.check_output(['git', 'bundle', 'list-heads', str(path)],
                                        cwd=ROOT, text=True)
        if not any(line.split() == [expected_commit, 'HEAD'] for line in heads.splitlines()):
            raise ValueError("bundle HEAD differs from manifest: " + name)
    raw_count = 0
    for date in ('2026-10-23', '2026-10-24'):
        directory = ROOT / 'research' / ('validated-' + date)
        entries = json.loads((directory / 'files.json').read_text(encoding='utf-8'))
        raw_count += verify_hashes(directory, entries)
    validation = ROOT / 'research' / 'github-validation-2026-10-24'
    validation_entries = json.loads((validation / 'files.json').read_text(encoding='utf-8'))
    validation_count = verify_hashes(validation, validation_entries)
    print(json.dumps(dict(status='verified', publication_files=artifact_count,
                          bundles=len(bundles), raw_evidence_files=raw_count,
                          github_validation_files=validation_count,
                          scope='byte integrity and Git bundle validity; not a scientific proof'),
                     indent=2))


if __name__ == '__main__':
    main()
