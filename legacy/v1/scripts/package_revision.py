"""Package an exact committed source tree and checked manuscript for local review."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("review package must be outside the source checkout")
    if subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ROOT).returncode:
        raise ValueError("commit the reviewed source changes before packaging")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode("utf-8").split("\0")
    pending = [name for name in untracked if name and
               not name.startswith(("submission/", "publication/"))]
    if pending:
        raise ValueError("reviewed source/evidence must be committed: " + ", ".join(pending[:10]))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    out.mkdir(parents=True, exist_ok=False)
    source_zip = out / "orchlang-source-and-evidence.zip"
    subprocess.run(["git", "archive", "--format=zip", "--output", str(source_zip), commit],
                   cwd=ROOT, check=True)
    shutil.copyfile(args.pdf, out / "OrchLang-paper.pdf")
    with zipfile.ZipFile(source_zip) as source:
        if source.testzip() is not None:
            raise ValueError("source archive CRC failure")
        forbidden = ("submission/", "docs/AGENT_BRIEF.md", "docs/AGENT_START_HERE.md",
                     "docs/HISTORICAL_README.md", "publication/")
        if any(name.startswith(forbidden) for name in source.namelist()):
            raise ValueError("source export contains excluded historical material")
        if any(Path(name).suffix in {".exe",".o",".d",".pyc",".olean",".ilean"} or
               Path(name).name in {"orchc","orchlang_tests",".env",".envrc"}
               for name in source.namelist() if not name.endswith("/")):
            raise ValueError("source export contains a generated executable or local configuration")
        files = {item.filename:hashlib.sha256(source.read(item)).hexdigest()
                 for item in source.infolist() if not item.is_dir()}
        required = {"proof/AggregateReordering.lean", "runtime/token_accounting.py",
                    "runtime/local_model.py", "docs/manuscript/main.tex",
                    "docs/REVISION_STATUS.md", "scripts/report_revision.py"}
        if not required.issubset(files):
            raise ValueError("source export omits required revision files: " +
                             ", ".join(sorted(required - files.keys())))
        with zipfile.ZipFile(out / "manuscript-latex.zip", "x", zipfile.ZIP_DEFLATED) as latex:
            for name in source.namelist():
                if name.startswith("docs/manuscript/") and not name.endswith("/"):
                    latex.writestr(name.removeprefix("docs/manuscript/"), source.read(name))
        # A self-contained root snapshot lets a reviewer clone the exact export
        # without needing an unpublished branch or the repository's old history.
        with tempfile.TemporaryDirectory(prefix="orchlang-review-source-") as directory:
            tree=Path(directory)
            source.extractall(tree)
            def git(*argv):
                return subprocess.check_output(["git",*argv],cwd=tree,stderr=subprocess.STDOUT,
                                               text=True).strip()
            git("init","--quiet")
            git("config","core.autocrlf","false")
            git("config","user.name","OrchLang review snapshot builder")
            git("config","user.email","artifact-builder@localhost")
            git("add","--force","--all")
            git("commit","--quiet","-m","Self-contained source export of "+commit)
            snapshot_commit=git("rev-parse","HEAD")
            names=set(git("ls-files").splitlines())
            if names != set(files):
                raise ValueError("snapshot bundle differs from source export")
            git("bundle","create",str(out/"orchlang-source-snapshot.bundle"),"--all")
            git("bundle","verify",str(out/"orchlang-source-snapshot.bundle"))
    (out / "SOURCE_FILES.json").write_text(json.dumps(files, indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    (out / "README.txt").write_text(
        "OrchLang scientific revision: local supervisor-review package\n\n"
        "Read docs/REVISION_STATUS.md in the source archive for the findings and gaps.\n"
        "Clone the self-contained bundle to obtain an immediately usable Git tree:\n"
        "  git clone orchlang-source-snapshot.bundle orchlang-review\n"
        "Install documented optional dependencies and run checks with NEW output\n"
        "directories. The source ZIP has identical files but no Git metadata.\n"
        "Historical raw evidence is retained.\n"
        "Source export excludes course submissions, agent handoffs and older packages.\n"
        "No model weights, credentials, private literature or executables are included.\n"
        "This package does not assert author approval, public deposition or acceptance.\n"
        "Original local source commit: " + commit + "\n"
        "Self-contained export snapshot: " + snapshot_commit + "\n",
        encoding="utf-8", newline="\n")
    manifest = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), source_commit=commit,
                    source_snapshot_commit=snapshot_commit,
                    purpose="local-supervisor-review", source_files=len(files),
                    source_export="git archive with checked-in export-ignore attributes",
                    files={p.name:dict(sha256=sha(p), bytes=p.stat().st_size)
                           for p in out.iterdir() if p.is_file()})
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    archive = Path(str(out) + ".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(out.iterdir()):
            package.write(path, path.name)
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("review package CRC failure")
    print(json.dumps(dict(output=str(out), archive=str(archive), source_commit=commit,
                          source_files=len(files), archive_sha256=sha(archive))))


if __name__ == "__main__":
    main()
