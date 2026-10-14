#!/usr/bin/env python3
"""Check that publication claims bind existing frozen source and evidence bytes.

This checks custody, not mathematical soundness or the truth of a result. A
source revision alone is insufficient if the manuscript names later files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

try:
    from .publication_run_integrity import (
        EVIDENCE_PATHS,
        OPTIONAL_EVIDENCE_IDS,
        REQUIRED_EVIDENCE_IDS,
        REQUIRED_SOURCE_PATHS,
        CLAIM_PROFILE,
        RUN_PATH,
        RunIntegrityError,
        frozen_source_inventory,
        parse_run_file,
    )
except ImportError:  # Script and unittest invocation from audit/.
    from publication_run_integrity import (
        EVIDENCE_PATHS,
        OPTIONAL_EVIDENCE_IDS,
        REQUIRED_EVIDENCE_IDS,
        REQUIRED_SOURCE_PATHS,
        CLAIM_PROFILE,
        RUN_PATH,
        RunIntegrityError,
        frozen_source_inventory,
        parse_run_file,
    )

FORMAT = "orchlang-publication-provenance"
SHA = re.compile(r"[0-9a-f]{64}\Z")
REV = re.compile(r"[0-9a-f]{40}\Z")


class ProvenanceError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def checked_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name:
        raise ProvenanceError("file name must be a nonempty relative POSIX path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name:
        raise ProvenanceError("noncanonical or escaping file path: " + name)
    candidate = root / name
    if candidate.is_symlink():
        raise ProvenanceError("symlinked artifact path is not accepted: " + name)
    resolved = candidate.resolve()
    if root.resolve() not in resolved.parents:
        raise ProvenanceError("file escapes the artifact root: " + name)
    return resolved


def read_manifest(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProvenanceError("duplicate JSON field: " + key)
            result[key] = value
        return result
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ProvenanceError("publication manifest exceeds 16 MiB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def verify(manifest: dict, root: Path, manuscript: Path | None = None) -> dict:
    required = {"format", "version", "source_revision", "source_files", "evidence", "claims", "limitations"}
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ProvenanceError("publication manifest fields differ from the version-1 schema")
    if manifest["format"] != FORMAT or type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ProvenanceError("unsupported publication manifest format/version")
    revision = manifest["source_revision"]
    if not isinstance(revision, str) or not REV.fullmatch(revision):
        raise ProvenanceError("source_revision must be a complete immutable Git SHA")
    try:
        actual = subprocess.check_output(["git", "rev-parse", revision + "^{commit}"], cwd=root, text=True).strip()
    except subprocess.CalledProcessError as error:
        raise ProvenanceError("frozen source commit is unavailable") from error
    if actual != revision:
        raise ProvenanceError("source revision does not resolve exactly")
    root = root.resolve()
    source = manifest["source_files"]
    evidence = manifest["evidence"]
    claims = manifest["claims"]
    if not isinstance(source, dict) or not source or not isinstance(evidence, dict) or not evidence:
        raise ProvenanceError("nonempty source and evidence inventories are required")
    if not REQUIRED_SOURCE_PATHS <= set(source):
        missing = sorted(REQUIRED_SOURCE_PATHS - set(source))
        raise ProvenanceError("fixed publication source profile is incomplete: " + ", ".join(missing))
    try:
        frozen_inventory = frozen_source_inventory(root, revision)
    except (RunIntegrityError, OSError, subprocess.CalledProcessError) as error:
        raise ProvenanceError(str(error)) from error
    if source != frozen_inventory:
        raise ProvenanceError("source inventory is incomplete or differs from all frozen publication inputs")

    expected_evidence_ids = REQUIRED_EVIDENCE_IDS | (set(evidence) & OPTIONAL_EVIDENCE_IDS)
    if set(evidence) != expected_evidence_ids:
        missing = sorted(REQUIRED_EVIDENCE_IDS - set(evidence))
        extra = sorted(set(evidence) - REQUIRED_EVIDENCE_IDS - OPTIONAL_EVIDENCE_IDS)
        raise ProvenanceError(
            "fixed publication evidence profile is incomplete or has unknown entries; missing="
            + ", ".join(missing) + "; extra=" + ", ".join(extra)
        )
    for name, expected in source.items():
        path = checked_path(root, name)
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ProvenanceError("invalid source digest: " + name)
        try:
            frozen = subprocess.check_output(["git", "show", revision + ":" + name], cwd=root, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as error:
            raise ProvenanceError("claimed source absent from frozen revision: " + name) from error
        if digest(frozen) != expected:
            raise ProvenanceError("frozen source digest differs: " + name)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ProvenanceError("working source differs from frozen revision: " + name)
    for key, item in evidence.items():
        if not isinstance(key, str) or not key or not isinstance(item, dict) or set(item) != {"path", "sha256", "scope"}:
            raise ProvenanceError("invalid evidence entry")
        path = checked_path(root, item["path"])
        if not isinstance(item["sha256"], str) or not SHA.fullmatch(item["sha256"]):
            raise ProvenanceError("invalid evidence digest: " + key)
        if not isinstance(item["scope"], str) or not item["scope"].strip():
            raise ProvenanceError("evidence scope must be explicit: " + key)
        if not path.is_file() or digest(path.read_bytes()) != item["sha256"]:
            raise ProvenanceError("missing or changed evidence: " + key)
        if key in EVIDENCE_PATHS and item["path"] != EVIDENCE_PATHS[key]:
            raise ProvenanceError("evidence path differs from the fixed publication profile: " + key)
    for key, path in EVIDENCE_PATHS.items():
        if evidence[key]["path"] != path:
            raise ProvenanceError("evidence path differs from the fixed publication profile: " + key)

    run_item = evidence["run"]
    try:
        run = parse_run_file(root, revision, frozen_inventory)
    except (RunIntegrityError, OSError, subprocess.CalledProcessError) as error:
        raise ProvenanceError(str(error)) from error
    if digest((root / RUN_PATH).read_bytes()) != run_item["sha256"]:
        raise ProvenanceError("run evidence digest does not match the fixed reproduction record")
    for evidence_id, relative in EVIDENCE_PATHS.items():
        if evidence_id in {"run"}:
            continue
        item = evidence[evidence_id]
        if run["outputs_sha256"].get(relative) != item["sha256"]:
            raise ProvenanceError("study evidence is not bound by the same successful run: " + evidence_id)

    if not isinstance(claims, list) or not claims:
        raise ProvenanceError("a nonempty claim-to-evidence map is required")
    seen = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"id", "statement", "source_paths", "evidence_ids"}:
            raise ProvenanceError("invalid claim entry")
        if not isinstance(claim["id"], str) or not claim["id"] or claim["id"] in seen:
            raise ProvenanceError("duplicate or empty claim identifier")
        seen.add(claim["id"])
        if not isinstance(claim["statement"], str) or not claim["statement"].strip():
            raise ProvenanceError("claim statement is empty")
        for field, inventory in (("source_paths", source), ("evidence_ids", evidence)):
            values = claim[field]
            if not isinstance(values, list) or not values or any(not isinstance(x, str) or x not in inventory for x in values):
                raise ProvenanceError("claim references absent " + field + ": " + claim["id"])
        profile = CLAIM_PROFILE.get(claim["id"])
        if profile is None:
            raise ProvenanceError("unknown publication claim: " + claim["id"])
        for field in ("source_paths", "evidence_ids"):
            values = claim[field]
            if len(values) != len(set(values)) or set(values) != profile[field]:
                raise ProvenanceError("claim differs from the fixed source/evidence profile: " + claim["id"])
    if seen != set(CLAIM_PROFILE):
        raise ProvenanceError("fixed publication claim profile is incomplete")
    if not isinstance(manifest["limitations"], list) or not manifest["limitations"] or any(
            not isinstance(x, str) or not x.strip() for x in manifest["limitations"]):
        raise ProvenanceError("explicit nonempty limitations are required")
    manuscript_item = evidence["manuscript"]
    if Path(manuscript_item["path"]).suffix.lower() != ".tex":
        raise ProvenanceError("manuscript evidence must be the standalone TeX source")
    manuscript_path = checked_path(root, manuscript_item["path"])
    if manuscript is not None:
        supplied = manuscript.resolve()
        if supplied != manuscript_path:
            raise ProvenanceError("requested manuscript differs from the manuscript bound by the manifest")
    try:
        manuscript_text = manuscript_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ProvenanceError("bound manuscript cannot be read") from error
    source_comments = re.findall(
        r"^% OrchLang-source-revision: ([0-9a-f]{40})$", manuscript_text, re.MULTILINE
    )
    if source_comments != [revision]:
        raise ProvenanceError("manuscript must declare the same frozen source revision exactly once")
    macro_values = re.findall(
        r"\\newcommand\s*\{\s*\\SourceRevision\s*\}\s*\{\s*([0-9a-f]{40})\s*\}",
        manuscript_text,
    )
    if macro_values != [revision]:
        raise ProvenanceError("manuscript must define one SourceRevision macro equal to the frozen source SHA")
    c2_rows = re.findall(r"(?ms)^\s*C2\s*&.*?\\\\\s*$", manuscript_text)
    if len(c2_rows) != 1:
        raise ProvenanceError("manuscript must contain exactly one C2 software-version row")
    c2 = c2_rows[0]
    immutable_target = (
        r"\\href{https://github.com/guyoverclocked/"
        r"orchlang-compiler-design-project/tree/\\SourceRevision}"
    )
    if not re.search(immutable_target, c2) or r"\texttt{\SourceRevision}" not in c2:
        raise ProvenanceError("C2 must link to the immutable SourceRevision tree and display that revision")

    pdf_item = evidence["manuscript_pdf"]
    if Path(pdf_item["path"]).suffix.lower() != ".pdf":
        raise ProvenanceError("compiled manuscript evidence must be a PDF")
    if pdf_item["path"] == manuscript_item["path"]:
        raise ProvenanceError("manuscript PDF evidence must be a separate file")
    return {"format": "orchlang-publication-provenance-attestation", "version": 1,
            "status": "verified", "source_revision": revision, "source_file_count": len(source),
            "evidence_count": len(evidence), "claim_count": len(claims),
            "scope": "source/evidence custody and claim references; no theorem or experiment truth validation"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manuscript", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(read_manifest(args.manifest), args.root, args.manuscript), indent=2))
    except (ProvenanceError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
