#!/usr/bin/env python3
"""Package a frozen source revision, validated study outputs, and the final paper.

The source archive comes from the declared immutable Git commit. The evidence
archive includes the fresh run and standalone manuscript. This creates local
review artifacts; it does not submit to a journal or claim acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/publication_upgrade"
sys.path.insert(0, str(ROOT / "audit"))
sys.path.insert(0, str(ROOT / "scripts"))
from publication_provenance import ProvenanceError, digest, verify  # noqa: E402
from publication_run_integrity import (  # noqa: E402
    CLAIM_PROFILE,
    EVIDENCE_PATHS,
    RunIntegrityError,
    frozen_source_inventory,
    parse_run_file,
)


CLAIM_STATEMENTS = {
    "software-checks": (
        "The recorded native, Python, sanitizer, package, and pinned LangGraph checks pass."
    ),
    "source-boundary": (
        "The bounded original-source sample admits no candidate to the current frontend, delimiting its supported source boundary."
    ),
    "prefix-replay": (
        "Prefix sharing reduces verifier recomputation and resolves the previous cap in the recorded controlled family."
    ),
    "atomic-ir": (
        "A machine-checked theorem establishes request-history and local-result agreement for the stated normalized-IR fragment."
    ),
    "source-specific-study": (
        "The pinned offline incident-triage source study and bounded concurrency extension freshly reproduce."
    ),
    "measurement-boundary": (
        "The offline local BPE calibration measures the stated source-call and control texts without provider accounting."
    ),
    "observer-sensitivity": (
        "On twelve authored fixtures, the recorded checker comparison separates request equality, stochastic bisimulation, and exact usage-trace outcomes."
    ),
    "manuscript-provenance": (
        "The manuscript's displayed source revision and immutable C2 link are checked against this evidence manifest."
    ),
}

EVIDENCE_SCOPES = {
    "core": "fresh native, Python, sanitizer, package, and pinned LangGraph reproduction",
    "incident": "fresh pinned unmodified offline incident-triage source run and source-specific replay",
    "corpus": "bounded frozen external-source admission sample; all unsupported outcomes retained",
    "selection": "frozen candidate selection audit and cohort-invariance evidence",
    "solver": "five worker repetitions at each of seven controlled synthetic sizes",
    "solver_baseline": "paired prior implementation using identical frozen inputs and measurement boundary",
    "tokenizer": "local tokenizer calibration with frozen vocabulary payloads; no provider accounting",
    "observer": "twelve authored fixtures with fresh checker execution and independent exact-trace replay",
    "proof": "global assumptions reported for the normalized straight-line request/local-result refinement",
    "run": "ordered successful publication reproduction with source, output, and log digests",
}


def relative_file(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(label + " must be stored inside the repository") from error
    if path.expanduser().is_symlink() or not resolved.is_file():
        raise ValueError(label + " must be a regular file inside the repository")
    return relative.as_posix()


def _claim_rows() -> list[dict]:
    rows = []
    for claim_id, profile in CLAIM_PROFILE.items():
        rows.append({
            "id": claim_id,
            "statement": CLAIM_STATEMENTS[claim_id],
            "source_paths": sorted(profile["source_paths"]),
            "evidence_ids": sorted(profile["evidence_ids"]),
        })
    return rows


def _evidence_files() -> set[Path]:
    folders = (
        ROOT / "audit/final", ROOT / "audit/incident_triage", ROOT / "bench/results",
        ROOT / "output/release", OUT / "reproduction", OUT / "corpus",
        OUT / "tokenizer_cache", ROOT / "proofs/publication_upgrade",
    )
    files: set[Path] = set()
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            if path.is_symlink():
                raise ValueError("evidence archive cannot contain symlinked files: " + str(path))
            if path.is_file():
                files.add(path)
    fixed = (
        OUT / "tokenizer_calibration.json", OUT / "observer_ablation.json",
        ROOT / "research/publication_upgrade/solver_scaling.json",
        ROOT / "research/publication_upgrade/solver_scaling_baseline.json",
        ROOT / "research/publication_upgrade/solver_scaling_plot_metadata.json",
        ROOT / "research/publication_upgrade/solver_scaling.svg",
        ROOT / "research/publication_upgrade/solver_scaling.pdf",
    )
    for path in fixed:
        if not path.is_file() or path.is_symlink():
            raise ValueError("required evidence file is missing or symlinked: " + str(path.relative_to(ROOT)))
        files.add(path)
    run = json.loads((OUT / "reproduction/run.json").read_text(encoding="utf-8"))
    output_inventory = run.get("outputs_sha256")
    if not isinstance(output_inventory, dict) or not output_inventory:
        raise ValueError("passing run lacks its final output digest inventory")
    for relative in output_inventory:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("captured run output is missing or symlinked: " + relative)
        files.add(path)
    return files


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-revision", required=True,
                     help="complete frozen code/source revision used for the passing run")
    cli.add_argument("--manuscript", type=Path, required=True,
                     help="standalone final LaTeX source with the matching SourceRevision C2 link")
    cli.add_argument("--pdf", type=Path, required=True,
                     help="compiled standalone manuscript PDF to include and bind as evidence")
    args = cli.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", args.source_revision + "^{commit}"], cwd=ROOT, text=True
    ).strip()
    sources = frozen_source_inventory(ROOT, revision)
    manuscript_rel = relative_file(args.manuscript, "manuscript")
    pdf_rel = relative_file(args.pdf, "PDF")
    run = parse_run_file(ROOT, revision, sources)
    if run.get("status") != "passed":
        raise RunIntegrityError("a fresh successful reproduction at the frozen source revision is required")

    named = {
        key: (path, EVIDENCE_SCOPES[key]) for key, path in EVIDENCE_PATHS.items()
        if key != "run"
    }
    named["run"] = (EVIDENCE_PATHS["run"], EVIDENCE_SCOPES["run"])
    evidence = {
        key: {"path": path, "sha256": digest((ROOT / path).read_bytes()), "scope": scope}
        for key, (path, scope) in named.items()
    }
    evidence["manuscript"] = {
        "path": manuscript_rel,
        "sha256": digest((ROOT / manuscript_rel).read_bytes()),
        "scope": "standalone LaTeX source with checked immutable code revision and C2 row",
    }
    evidence["manuscript_pdf"] = {
        "path": pdf_rel,
        "sha256": digest((ROOT / pdf_rel).read_bytes()),
        "scope": "compiled manuscript PDF supplied with the checked LaTeX source",
    }

    manifest = {
        "format": "orchlang-publication-provenance",
        "version": 1,
        "source_revision": revision,
        "source_files": sources,
        "evidence": evidence,
        "claims": _claim_rows(),
        "limitations": [
            "This package records a candidate for review; it is not a journal submission, peer review, or acceptance.",
            "Author identity and affiliation fields remain placeholders for the author to complete.",
            "No provider measurements, probabilities, or invoices are validated; transport timing and privacy are outside scope.",
            "The machine proof covers a normalized straight-line fragment, not AST extraction, final states, or full toolchain correctness.",
            "The 12-repository source sample and controlled synthetic scaling family do not support population-wide generalization.",
            "Agent-assisted checks and same-host replays are not an independent human artifact evaluation.",
        ],
    }
    manifest_path = OUT / "publication_manifest.json"
    attestation_path = OUT / "provenance_attestation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    attestation = verify(manifest, ROOT, ROOT / manuscript_rel)
    attestation_path.write_text(json.dumps(attestation, indent=2) + "\n", encoding="utf-8")

    source_zip = OUT / "OrchLang_0.5.0rc2_source.zip"
    evidence_zip = OUT / "OrchLang_0.5.0rc2_publication_evidence.zip"
    with tempfile.TemporaryDirectory(prefix="orchlang-publication-package-") as temp:
        source_temp = Path(temp) / source_zip.name
        evidence_temp = Path(temp) / evidence_zip.name
        subprocess.run(
            ["git", "archive", "--format=zip", "--prefix=orchlang/",
             "--output", str(source_temp), revision], cwd=ROOT, check=True,
        )
        files = _evidence_files()
        files.update({manifest_path, attestation_path, ROOT / manuscript_rel})
        files.add(ROOT / pdf_rel)
        with zipfile.ZipFile(evidence_temp, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(files):
                bundle.write(path, path.relative_to(ROOT).as_posix())

        # Check both source and run output custody after reading all package
        # inputs, immediately before the archives become visible.
        verify(manifest, ROOT, ROOT / manuscript_rel)
        parse_run_file(ROOT, revision, sources)
        source_zip.write_bytes(source_temp.read_bytes())
        evidence_zip.write_bytes(evidence_temp.read_bytes())

    assets = {
        path.name: {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
        for path in (source_zip, evidence_zip)
    }
    checksums = OUT / "archive_checksums.json"
    checksums.write_text(json.dumps({
        "source_revision": revision,
        "publication_manifest_sha256": digest(manifest_path.read_bytes()),
        "attestation_sha256": digest(attestation_path.read_bytes()),
        "assets": assets,
        "status": "local_candidate_packaged",
        "submission_ready": False,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "packaged",
        "source_revision": revision,
        "manuscript": manuscript_rel,
        "submission_ready": False,
        "assets": assets,
        "attestation": attestation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProvenanceError, RunIntegrityError, OSError, ValueError,
            subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
