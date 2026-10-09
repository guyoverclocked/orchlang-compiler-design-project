#!/usr/bin/env python3
"""Export a whitelisted Python LangGraph StateGraph to request-graph JSON.

The exporter parses the exact source/contracts bytes, never imports or runs
the program, then invokes the request-graph checker and independent replayer.
An accepted report is evidence about the exported graph, not a source
translation proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

try:
    from .extract import FrontendError, extract_source, parse_contracts
except ImportError:  # direct script execution
    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from integrations.langgraph.source_frontend.extract import FrontendError, extract_source, parse_contracts


ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "audit"
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_CONTRACT_BYTES = 1 * 1024 * 1024


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    """Read at most maximum+1 bytes before rejecting an oversized input."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except OSError as error:
        raise FrontendError(f"cannot read {label}: {error}") from error
    if len(raw) > maximum:
        raise FrontendError(f"{label} exceeds {maximum} bytes")
    return raw


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _frontend_hash() -> tuple[str, list[dict[str, str]]]:
    source_dir = Path(__file__).resolve().parent
    files: list[dict[str, str]] = []
    for path in sorted(source_dir.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        raw = path.read_bytes()
        files.append({"path": path.name, "sha256": _sha(raw)})
    digest = hashlib.sha256(_canonical(files)).hexdigest()
    return digest, files


def _run_json_command(command: list[str], *, timeout: int = 60) -> tuple[int, dict[str, Any], str]:
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FrontendError(f"proof tool invocation failed: {error}") from error
    try:
        report = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as error:
        detail = (completed.stderr.strip() or completed.stdout.strip())[-2000:]
        raise FrontendError(f"proof tool did not return JSON: {detail}") from error
    if not isinstance(report, dict):
        raise FrontendError("proof tool JSON result must be an object")
    return completed.returncode, report, completed.stderr.strip()


def export_bytes(source_raw: bytes, contracts_raw: bytes, *, max_nodes: int = 50_000) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None
]:
    """Extract, graph-check and (only if accepted) independently replay bytes."""
    graph_doc, mapping = extract_source(source_raw, contracts_raw)
    graph_bytes = _canonical(graph_doc)
    graph_report: dict[str, Any]
    certificate_bytes: bytes
    attestation: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="orchlang-langgraph-export-") as temporary:
        temp = Path(temporary)
        graph_path = temp / "graph.json"
        certificate_path = temp / "certificate.json"
        replay_path = temp / "replay.json"
        graph_path.write_bytes(graph_bytes)
        status, graph_report, stderr = _run_json_command(
            [sys.executable, str(AUDIT / "orchgraph.py"), str(graph_path),
             "--max-nodes", str(max_nodes), "--report", str(certificate_path)]
        )
        if not certificate_path.exists():
            raise FrontendError(f"graph checker did not write a certificate: {stderr}")
        # Normalize the exact report bytes used by the independent replayer
        # and later emitted by the CLI, so every recorded hash names one file.
        certificate_bytes = _canonical(graph_report)
        certificate_path.write_bytes(certificate_bytes)
        if status not in (0, 1, 2) or graph_report.get("status") not in ("accepted", "rejected", "unknown"):
            raise FrontendError(f"graph checker failed closed: {stderr or graph_report}")
        if graph_report.get("source_sha256") != _sha(graph_bytes):
            raise FrontendError("graph checker report does not bind the emitted graph bytes")
        if graph_report["status"] == "accepted":
            replay_status, attestation, replay_stderr = _run_json_command(
                [sys.executable, str(AUDIT / "replay_graph_certificate.py"),
                 str(graph_path), str(certificate_path), "--attestation", str(replay_path)]
            )
            if replay_status != 0 or attestation.get("status") != "verified":
                raise FrontendError(f"independent certificate replay failed: {replay_stderr or attestation}")
            if not replay_path.exists():
                raise FrontendError("certificate replayer did not write its attestation")
            saved_attestation = json.loads(replay_path.read_bytes())
            if saved_attestation != attestation:
                raise FrontendError("replay output and attestation file disagree")

    frontend_digest, frontend_files = _frontend_hash()
    graph_checker_raw = (AUDIT / "orchgraph.py").read_bytes()
    replayer_raw = (AUDIT / "replay_graph_certificate.py").read_bytes()
    normalized_contracts = parse_contracts(contracts_raw)
    sidecar = {
        "format": "orchlang-langgraph-source-provenance",
        "version": 1,
        "source_sha256": _sha(source_raw),
        "contracts_sha256": _sha(contracts_raw),
        "graph_sha256": _sha(graph_bytes),
        "certificate_sha256": _sha(certificate_bytes),
        "attestation_sha256": _sha(_canonical(attestation)) if attestation is not None else None,
        "mapping_sha256": _sha(_canonical(mapping)),
        "frontend_sha256": frontend_digest,
        "frontend_files": frontend_files,
        "graph_checker_sha256": _sha(graph_checker_raw),
        "certificate_replayer_sha256": _sha(replayer_raw),
        "workflow": normalized_contracts["name"],
        "chars_per_token": normalized_contracts["chars_per_token"],
        "source_execution": "not_performed_by_exporter",
        "checks": {
            "extraction": "passed",
            "graph_check": graph_report.get("status"),
            "certificate_replay": "verified" if attestation is not None else "not_run_graph_not_accepted",
        },
        "graph_diagnostic": graph_report.get("diagnostic"),
        "graph_certificate": graph_report,
        "replay_attestation": attestation,
        "mapping": mapping,
        "assumptions": {
            "request_helper": "request(model=<literal alias>, template=<literal text>, arguments=[ordered text literals/state values/prior local results])",
            "token_helper": "tokens(text) is ceil(UTF-8 bytes / chars_per_token)",
            "state_updates": "each LangGraph node returns atomically; destination-field reads after its producing local call are rejected",
            "request_oracle": "shared Omega keyed by workflow name, seed, normalized model contract, per-contract ordinal, exact template, and ordered full-text arguments",
            "provider_scope": "offline helper only; no provider execution or guarantee",
        },
    }
    return graph_doc, sidecar, graph_report, attestation


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    graph = args.graph
    certificate = args.certificate or graph.with_name(graph.stem + ".certificate.json")
    sidecar = args.sidecar or graph.with_name(graph.stem + ".provenance.json")
    attestation = args.attestation or graph.with_name(graph.stem + ".attestation.json")
    paths = [graph, certificate, sidecar, attestation]
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise FrontendError("graph, certificate, sidecar, and attestation paths must be distinct")
    return tuple(paths)  # type: ignore[return-value]


def _write_atomic(outputs: list[tuple[Path, bytes | None]]) -> None:
    """Replace output snapshots and invalidate destinations passed as None.

    In particular, a rejected export must remove an older replay attestation
    at the reused path before replacing the graph and its other sidecars.
    """
    pending: list[tuple[Path, Path]] = []
    invalidations: list[Path] = []
    try:
        for destination, data in outputs:
            if data is None:
                invalidations.append(destination)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix="." + destination.name + ".", dir=destination.parent)
            temp_path = Path(temp_name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            pending.append((temp_path, destination))
        # Invalidate stale proof artifacts before replacing any new snapshot.
        # If a later replace fails, the mixed output set cannot retain an old
        # attestation that appears to certify the newly written graph.
        for destination in invalidations:
            destination.unlink(missing_ok=True)
        for temporary, destination in pending:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in pending:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Python source using the documented StateGraph subset")
    parser.add_argument("contracts", type=Path, help="strict JSON state/model contracts")
    parser.add_argument("graph", type=Path, help="output version-1 request graph JSON")
    parser.add_argument("--certificate", type=Path, help="producer graph-check report path")
    parser.add_argument("--sidecar", type=Path, help="source/contract/mapping provenance path")
    parser.add_argument("--attestation", type=Path, help="independent replay attestation path")
    parser.add_argument("--max-nodes", type=int, default=50_000)
    parser.add_argument("--require-accepted", action="store_true",
                        help="exit nonzero if graph checker rejects or cannot decide")
    args = parser.parse_args(argv)
    try:
        graph_path, certificate_path, sidecar_path, attestation_path = _paths(args)
        output_paths = {path.resolve() for path in (graph_path, certificate_path, sidecar_path, attestation_path)}
        if args.source.resolve() in output_paths or args.contracts.resolve() in output_paths:
            raise FrontendError("output paths must not overwrite the source or contracts snapshot")
        source_raw = _read_bounded(args.source, MAX_SOURCE_BYTES, "Python source")
        contracts_raw = _read_bounded(args.contracts, MAX_CONTRACT_BYTES, "contracts")
        graph_doc, sidecar, graph_report, attestation = export_bytes(
            source_raw, contracts_raw, max_nodes=args.max_nodes)
        graph_bytes = _canonical(graph_doc)
        certificate_bytes = _canonical(graph_report)
        sidecar_bytes = _canonical(sidecar)
        attestation_bytes = _canonical(attestation) if attestation is not None else None
        _write_atomic([(graph_path, graph_bytes),
                       (certificate_path, certificate_bytes),
                       (sidecar_path, sidecar_bytes),
                       (attestation_path, attestation_bytes)])
        summary = {"status": graph_report["status"],
                   "graph_sha256": sidecar["graph_sha256"],
                   "source_sha256": sidecar["source_sha256"],
                   "contracts_sha256": sidecar["contracts_sha256"],
                   "certificate_sha256": sidecar["certificate_sha256"],
                   "replay": sidecar["checks"]["certificate_replay"],
                   "graph": str(graph_path),
                   "certificate": str(certificate_path),
                   "sidecar": str(sidecar_path)}
        if attestation is not None:
            summary["attestation"] = str(attestation_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.require_accepted and graph_report["status"] != "accepted":
            return 2 if graph_report["status"] == "unknown" else 1
        return 0
    except (FrontendError, OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        print(f"LangGraph source export failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
