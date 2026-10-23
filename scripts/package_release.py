"""Create a separate clean source snapshot without altering the user's Git tree."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("clean snapshot must be outside the working repository")
    out.mkdir(parents=True, exist_ok=False)
    selected = []
    for name in ("src", "include", "tests", "runtime", "scripts", "proof", "examples", "bench", "docs", "research", "audit"):
        for path in (ROOT / name).rglob("*"):
            if not path.is_file() or any(x in path.parts for x in ("__pycache__", ".lake")):
                continue
            if path.suffix.lower() in {".exe", ".o", ".d", ".pyc", ".olean", ".ilean", ".docx", ".pptx", ".pdf", ".png", ".aux", ".log", ".out", ".gz"}:
                continue
            selected.append(path)
    selected += [ROOT / n for n in ("README.md", "Makefile", "LICENSE", "THIRD_PARTY_NOTICES.md", ".gitignore", ".gitattributes")]
    hashes = {}
    for path in selected:
        relative = path.relative_to(ROOT)
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if relative.parts[0] not in {"research", "audit"} and (path.suffix.lower() in {
                ".cpp", ".hpp", ".py", ".json", ".orch", ".md", ".lean", ".ps1", ".sh"} or
                path.name in {"Makefile", "LICENSE", ".gitignore", ".gitattributes", "lean-toolchain"}):
            target.write_text(target.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    upstream = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    provenance = dict(upstream_base_commit=upstream, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      purpose="clean-local-artifact-snapshot-not-a-public-release",
                      source_working_tree_was_dirty=True, files=hashes)
    (out / "SOURCE_PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8", newline="\n")
    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=out, text=True, stderr=subprocess.STDOUT).strip()
    git("init", "--quiet")
    for key, fallback in (("user.name", "OrchLang artifact builder"), ("user.email", "artifact-builder@localhost")):
        result = subprocess.run(["git", "config", key], cwd=ROOT, capture_output=True, text=True)
        git("config", key, result.stdout.strip() or fallback)
    git("add", "--all")
    git("commit", "--quiet", "-m", "Freeze source and offline external-projection protocol")
    commit = git("rev-parse", "HEAD")
    for relative, expected in hashes.items():
        committed = subprocess.check_output(["git", "show", commit + ":" + relative], cwd=out)
        if hashlib.sha256(committed).hexdigest() != expected:
            raise ValueError("committed bytes differ from provenance: " + relative)
    if git("status", "--porcelain"):
        raise AssertionError("snapshot must start clean")
    print(json.dumps(dict(path=str(out), commit=commit, copied_files=len(hashes), dirty_tree=False)))


if __name__ == "__main__":
    main()
