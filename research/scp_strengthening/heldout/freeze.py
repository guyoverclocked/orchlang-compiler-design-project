#!/usr/bin/env python3
"""Freeze disjoint source identities/bytes without invoking any frontend."""
from __future__ import annotations
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/scp_strengthening/heldout"
PROTOCOL = ROOT / "research/scp_strengthening/heldout/protocol.json"
EXTRACTOR = ROOT / "integrations/langgraph/source_frontend/extract.py"
ARCHIVE_CAP = 128 * 1024 * 1024
SOURCE_CAP = 2 * 1024 * 1024
EXCLUDED = {"test", "tests", "docs", "doc", "vendor", "vendored", "generated", ".venv", "site-packages"}

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

def gh(path: str) -> dict:
    for attempt in range(3):
        try:
            return json.loads(subprocess.check_output(["gh", "api", "--method", "GET", path], text=True, timeout=45))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")

def candidate(raw: bytes) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError) as error:
        return False, type(error).__name__ + ": " + str(error)
    names = {"StateGraph"}
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("langgraph.graph"):
            for alias in node.names:
                if alias.name == "StateGraph":
                    return True, None
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "langgraph.graph":
                    modules.add(alias.asname or "langgraph.graph")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in names:
            return True, None
        if isinstance(node.func, ast.Attribute) and node.func.attr == "StateGraph":
            base = ast.unparse(node.func.value)
            if base in modules:
                return True, None
    return False, None

def identities() -> None:
    target = OUT / "identities.json"
    if target.exists():
        raise ValueError("identities already frozen; do not resample")
    selection_path = OUT / "selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["protocol_sha256"] == sha(PROTOCOL.read_bytes())
    rows = []
    for selected in selection["selected_repositories"]:
        name = selected["full_name"]
        ref = gh("repos/" + name + "/git/ref/heads/" + quote(selected["default_branch"], safe=""))
        commit = gh("repos/" + name + "/git/commits/" + ref["object"]["sha"])
        metadata = OUT / "commits" / (name.replace("/", "__") + ".json")
        write(metadata, commit)
        rows.append(dict(selected, commit=commit["sha"], tree_sha=commit["tree"]["sha"],
                         commit_metadata_path=str(metadata.relative_to(ROOT)), commit_metadata_sha256=sha(metadata.read_bytes())))
    write(target, {"frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                   "protocol_sha256": sha(PROTOCOL.read_bytes()), "selection_sha256": sha(selection_path.read_bytes()),
                   "extractor_sha256_at_identity_freeze": sha(EXTRACTOR.read_bytes()), "repositories": rows})
    print("Frozen", len(rows), "immutable repository identities; no source extraction/evaluation")

def one(repo: dict) -> dict:
    name, commit = repo["full_name"], repo["commit"]
    row = {"repository": name, "commit": commit, "license_spdx": repo["license_spdx"],
           "python_path_count": 0, "candidates": [], "parse_errors": [], "oversize_files": [], "retained_license_paths": []}
    url = "https://codeload.github.com/" + name + "/zip/" + commit
    try:
        with urlopen(Request(url, headers={"User-Agent": "OrchLang-SCP-heldout-source-freeze/1"}), timeout=55) as response:
            chunks = []
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > ARCHIVE_CAP:
                    raise ValueError("repository archive exceeds preregistered 128MiB cap")
                chunks.append(block)
        archive = b"".join(chunks)
        row["archive_url"], row["archive_bytes"], row["archive_sha256"] = url, len(archive), sha(archive)
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            infos = sorted((x for x in bundle.infolist() if not x.is_dir()), key=lambda x: x.filename)
            for entry in infos:
                parts = PurePosixPath(entry.filename).parts
                if len(parts) < 2 or any(x in ("..", ".") for x in parts):
                    raise ValueError("unsafe archive member path")
                rel = PurePosixPath(*parts[1:]).as_posix()
                retained_license = bool(re.fullmatch(r"(?i)(licen[cs]e|copying)(\.[^/]*)?", parts[-1]))
                is_python = rel.endswith(".py") and not any(x.lower() in EXCLUDED for x in parts[1:])
                if not retained_license and not is_python:
                    continue
                if retained_license:
                    if entry.file_size > SOURCE_CAP:
                        raise ValueError("license exceeds2MiB cap")
                    raw = bundle.read(entry)
                    path = OUT / "sources" / name / commit / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    row["retained_license_paths"].append({"path": rel, "sha256": sha(raw)})
                if not is_python:
                    continue
                row["python_path_count"] += 1
                if entry.file_size > SOURCE_CAP:
                    row["oversize_files"].append({"path": rel, "bytes": entry.file_size})
                    continue
                raw = bundle.read(entry)
                is_candidate, error = candidate(raw)
                if error:
                    row["parse_errors"].append({"path": rel, "sha256": sha(raw), "error": error})
                if is_candidate:
                    path = OUT / "sources" / name / commit / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    row["candidates"].append({"repository": name, "commit": commit, "path": rel,
                                               "bytes": len(raw), "sha256": sha(raw),
                                               "source_snapshot": str(path.relative_to(ROOT)),
                                               "source_url": "https://github.com/" + name + "/blob/" + commit + "/" + rel})
        row["status"] = "frozen"
    except Exception as error:
        row["status"] = "retrieval_error"
        row["error"] = type(error).__name__ + ": " + str(error)
    return row

def sources() -> None:
    target = OUT / "source_freeze.json"
    if target.exists():
        raise ValueError("source cohort already frozen; do not refreeze")
    identity_path = OUT / "identities.json"
    identity = json.loads(identity_path.read_text())
    if sha(EXTRACTOR.read_bytes()) != identity["extractor_sha256_at_identity_freeze"]:
        raise ValueError("frontend changed before source freeze")
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, identity["repositories"]))
    record = {"frozen_at_utc": datetime.now(timezone.utc).isoformat(),
              "protocol_sha256": sha(PROTOCOL.read_bytes()), "identities_sha256": sha(identity_path.read_bytes()),
              "extractor_sha256_at_source_freeze": sha(EXTRACTOR.read_bytes()),
              "repository_count": len(rows), "python_path_count": sum(x["python_path_count"] for x in rows),
              "candidate_count": sum(len(x["candidates"]) for x in rows),
              "retrieval_errors": sum(x["status"] == "retrieval_error" for x in rows), "repositories": rows,
              "admission_evaluation_performed": False}
    write(target, record)
    print(json.dumps({k: record[k] for k in ("repository_count", "python_path_count", "candidate_count", "retrieval_errors", "admission_evaluation_performed")}, indent=2))

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("identities", "sources"))
    args = cli.parse_args()
    (identities if args.phase == "identities" else sources)()
