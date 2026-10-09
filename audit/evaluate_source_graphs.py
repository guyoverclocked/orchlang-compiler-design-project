#!/usr/bin/env python3
"""Attempt a fixed source corpus through the experimental graph bridge.

This study does not rewrite source files. It records compiler acceptance,
bridge-subset exclusions, emitted graph/certificate/provenance artifacts,
independent replay, and finite direct-source/graph full-text trace comparisons.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

try:
    from orchgraph import Graph, reference_run
    from source_to_graph import (BridgeError, InputDecl, SourceReferenceInterpreter,
                                 check_compiler_snapshot, parse_source, translate_file)
except ImportError:  # pragma: no cover - package import path
    from .orchgraph import Graph, reference_run
    from .source_to_graph import (BridgeError, InputDecl, SourceReferenceInterpreter,
                                  check_compiler_snapshot, parse_source, translate_file)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "bench/results/source_graphs"
DIVISOR = 4
SEEDS = (1, 17, 29)
TEXT_CANDIDATES = ("", "x", "public question", "é🙂 Unicode", 'quote " slash \\\nline')
PUBLIC_SAMPLE_INDICES = (0, 2, 3, 4)
MAX_PUBLIC_SCENARIOS = 512
MAX_SECRET_ASSIGNMENTS = 4096
MAX_RUNS_PER_SOURCE = 100_000
MAX_CALLS = 10_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return digest(encoded)


def _text_values(declaration: InputDecl, limit: int) -> list[str]:
    values: list[str] = []
    for value in TEXT_CANDIDATES:
        encoded = value.encode("utf-8")
        estimate = (len(encoded) + DIVISOR - 1) // DIVISOR
        if estimate <= limit and value not in values:
            values.append(value)
    if not values:
        raise BridgeError(f"no test value fits text input {declaration.name!r}")
    return values


def input_scenarios(workflow) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    declarations = [item for item in workflow.body if isinstance(item, InputDecl)]
    public = [item for item in declarations if item.confidential == "public"]
    secrets = [item for item in declarations if item.confidential == "secret"]
    public_flags = [item for item in public if item.type_name == "boolean"]
    public_text = [item for item in public if item.type_name == "text"]
    secret_domains: list[list[Any]] = []
    for item in secrets:
        if item.type_name == "boolean":
            secret_domains.append([False, True])
        else:
            secret_domains.append(_text_values(item, item.max_tokens or 0))
    secret_count = 1
    for domain in secret_domains:
        secret_count *= len(domain)
    if secret_count > MAX_SECRET_ASSIGNMENTS:
        raise BridgeError(f"secret assignment grid exceeds {MAX_SECRET_ASSIGNMENTS}")
    secret_stores = [dict(zip((item.name for item in secrets), values))
                     for values in itertools.product(*secret_domains)]

    flag_assignments = list(itertools.product((False, True), repeat=len(public_flags)))
    scenario_count = len(flag_assignments) * (4 if public_text else 1)
    if scenario_count > MAX_PUBLIC_SCENARIOS:
        raise BridgeError(f"public input grid exceeds {MAX_PUBLIC_SCENARIOS}")
    public_stores: list[dict[str, Any]] = []
    for flags in flag_assignments:
        for sample_index in range(4 if public_text else 1):
            store: dict[str, Any] = dict(zip((item.name for item in public_flags), flags))
            for index, item in enumerate(public_text):
                values = _text_values(item, item.max_tokens or 0)
                selected = [values[value_index] for value_index in PUBLIC_SAMPLE_INDICES
                            if value_index < len(values)] or values
                store[item.name] = selected[(sample_index + index) % len(selected)]
            public_stores.append(store)
    if not public_stores:
        public_stores = [{}]
    return public_stores, secret_stores, [item.name for item in secrets]


def graph_store(mapping: dict[str, Any], source_store: dict[str, Any]) -> dict[str, Any]:
    return {entry["graph_name"]: source_store[entry["source_name"]]
            for entry in mapping["inputs"]}


def billing_projection(run: dict[str, Any]) -> dict[str, Any]:
    """The graph observer includes ordered calls/usages and stop, not output text."""
    return {"trace": run["trace"], "stopped": run["stopped"]}


def _run_replay(graph_path: Path, certificate_path: Path,
                attestation_path: Path) -> dict[str, Any]:
    replayer = ROOT / "audit/replay_graph_certificate.py"
    try:
        completed = subprocess.run(
            [sys.executable, str(replayer), str(graph_path), str(certificate_path),
             "--attestation", str(attestation_path)],
            capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BridgeError(f"independent replay could not complete: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BridgeError(f"independent replay failed: {detail[-2000:]}")
    report = json.loads(completed.stdout)
    if not isinstance(report, dict) or report.get("status") != "verified":
        raise BridgeError("independent replay did not return verified status")
    return report


def _run_case(source_path: Path, category: str, compiler: Path,
              root_out: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relative = source_path.relative_to(ROOT).as_posix()
    raw = source_path.read_bytes()
    source_hash = digest(raw)
    case_name = source_path.stem
    base = root_out / "exports" / category / case_name
    graph_path = base.with_suffix(".graph.json")
    certificate_path = base.with_suffix(".certificate.json")
    sidecar_path = base.with_suffix(".provenance.json")
    attestation_path = base.with_suffix(".attestation.json")
    row: dict[str, Any] = {
        "source_path": relative,
        "source_sha256": source_hash,
        "corpus_category": category,
        "compiler_check": None,
        "bridge_status": None,
        "diagnostic": None,
        "artifacts": None,
        "differential": None,
    }
    probes: list[dict[str, Any]] = []

    check, compiler_hash = check_compiler_snapshot(raw, compiler, DIVISOR)
    diagnostic = (check.stderr.strip() or check.stdout.strip())[-2000:]
    row["compiler_check"] = {
        "status": "accepted" if check.returncode == 0 else "rejected",
        "exit_code": check.returncode,
        "compiler_sha256": compiler_hash,
        "diagnostic": diagnostic or None,
    }
    if check.returncode != 0:
        row["bridge_status"] = "compiler_rejected"
        row["diagnostic"] = diagnostic
        return row, probes

    try:
        graph_doc, sidecar = translate_file(
            source_path, graph_path, sidecar_path=sidecar_path,
            certificate_path=certificate_path, compiler_path=compiler,
            chars_per_token=DIVISOR)
    except BridgeError as error:
        message = str(error)
        row["bridge_status"] = "unsupported_subset"
        row["diagnostic"] = message
        if "compiler check gate failed" in message:
            row["bridge_status"] = "compiler_rejected"
        elif "request-graph check" in message or "replay" in message:
            row["bridge_status"] = "pipeline_error"
        return row, probes
    if sidecar["source_sha256"] != source_hash:
        raise BridgeError("source bytes changed between corpus snapshot and bridge translation")
    if sidecar["compiler_sha256"] != compiler_hash:
        raise BridgeError("compiler bytes changed between corpus gate and bridge translation")

    replay = _run_replay(graph_path, certificate_path, attestation_path)
    graph = Graph(graph_doc)
    workflow = parse_source(raw)
    public_stores, secret_stores, _ = input_scenarios(workflow)
    expected_runs = len(public_stores) * len(secret_stores) * len(SEEDS)
    if expected_runs > MAX_RUNS_PER_SOURCE:
        raise BridgeError(f"source differential grid would require {expected_runs} runs; limit is {MAX_RUNS_PER_SOURCE}")
    direct_graph_runs = 0
    invariant_secret_pairs = 0
    differing_secret_pairs = 0
    compared_calls = 0
    first_difference: dict[str, Any] | None = None

    for public_index, public_values in enumerate(public_stores):
        for seed in SEEDS:
            paired: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
            for secret_values in secret_stores:
                store = {**public_values, **secret_values}
                direct = SourceReferenceInterpreter(workflow, store, seed,
                                                    DIVISOR, MAX_CALLS).run()
                lowered = reference_run(graph, graph_store(sidecar["mapping"], store),
                                        seed, MAX_CALLS)
                same = billing_projection(direct) == billing_projection(lowered)
                direct_graph_runs += 1
                compared_calls += max(len(direct["trace"]), len(lowered["trace"]))
                probe = {
                    "public_scenario": public_index,
                    "seed": seed,
                    "public_inputs": public_values,
                    "secret_inputs": secret_values,
                    "source_graph_equal": same,
                    "source_trace_sha256": canonical_digest(direct["trace"]),
                    "graph_trace_sha256": canonical_digest(lowered["trace"]),
                    "source_trace": direct["trace"],
                    "graph_trace": lowered["trace"],
                    "source_stopped": direct["stopped"],
                    "graph_stopped": lowered["stopped"],
                    "source_output_value_outside_billing_observer": direct["output"],
                }
                probes.append(probe)
                if not same and first_difference is None:
                    first_difference = {
                        "public_scenario": public_index,
                        "seed": seed,
                        "public_inputs": public_values,
                        "secret_inputs": secret_values,
                        "source_trace_sha256": probe["source_trace_sha256"],
                        "graph_trace_sha256": probe["graph_trace_sha256"],
                    }
                paired.append((secret_values, direct, lowered))
            if paired:
                source_reference, graph_reference = paired[0][1], paired[0][2]
                for secret_values, direct, lowered in paired[1:]:
                    source_same = billing_projection(direct) == billing_projection(source_reference)
                    graph_same = billing_projection(lowered) == billing_projection(graph_reference)
                    direct_same = source_same and graph_same
                    invariant_secret_pairs += int(direct_same)
                    differing_secret_pairs += int(not direct_same)
                    if not direct_same and first_difference is None:
                        first_difference = {
                            "public_scenario": public_index,
                            "seed": seed,
                            "reference_secret_inputs": paired[0][0],
                            "other_secret_inputs": secret_values,
                            "source_secret_invariant": source_same,
                            "graph_secret_invariant": graph_same,
                        }

    probe_path = root_out / "probes" / category / f"{case_name}.jsonl"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    with probe_path.open("w", encoding="utf-8", newline="\n") as output:
        for probe in probes:
            output.write(json.dumps(probe, ensure_ascii=False, sort_keys=True) + "\n")
    row["bridge_status"] = "exported"
    row["artifacts"] = {
        "graph": graph_path.relative_to(root_out).as_posix(),
        "graph_sha256": digest(graph_path.read_bytes()),
        "certificate": certificate_path.relative_to(root_out).as_posix(),
        "certificate_sha256": digest(certificate_path.read_bytes()),
        "provenance": sidecar_path.relative_to(root_out).as_posix(),
        "provenance_sha256": digest(sidecar_path.read_bytes()),
        "independent_replay": attestation_path.relative_to(root_out).as_posix(),
        "replay_status": replay["status"],
        "replay_sha256": digest(attestation_path.read_bytes()),
        "probe_file": probe_path.relative_to(root_out).as_posix(),
        "probe_sha256": digest(probe_path.read_bytes()),
    }
    row["differential"] = {
        "public_scenarios": len(public_stores),
        "secret_assignments_per_scenario": len(secret_stores),
        "seeds": list(SEEDS),
        "source_graph_run_pairs": direct_graph_runs,
        "secret_trace_pairs": invariant_secret_pairs + differing_secret_pairs,
        "secret_trace_pairs_equal": invariant_secret_pairs,
        "secret_trace_pairs_different": differing_secret_pairs,
        "call_events_compared": compared_calls,
        "first_difference": first_difference,
        "probes_sha256": row["artifacts"]["probe_sha256"],
    }
    return row, probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=ROOT / "orchc")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args(argv)
    compiler = args.compiler.resolve()
    output_root = args.output.resolve()
    initial_compiler_hash = digest(compiler.read_bytes()) if compiler.is_file() else None
    research = sorted((ROOT / "examples/research/accepted").glob("*.orch"))
    balanced = sorted((ROOT / "bench/sourced/balanced").glob("*.orch"))
    initial_source_hashes = {path.resolve(): digest(path.read_bytes())
                             for path in research + balanced}
    failures: list[str] = []
    if len(research) != 5:
        failures.append(f"expected 5 accepted research examples, found {len(research)}")
    if len(balanced) != 15:
        failures.append(f"expected 15 balanced sourced examples, found {len(balanced)}")

    rows: list[dict[str, Any]] = []
    for category, paths in (("research_accepted", research), ("sourced_balanced", balanced)):
        for source_path in paths:
            try:
                row, _ = _run_case(source_path, category, compiler, output_root)
            except (BridgeError, OSError, ValueError, TypeError, KeyError, IndexError) as error:
                row = {
                    "source_path": source_path.relative_to(ROOT).as_posix(),
                    "source_sha256": digest(source_path.read_bytes()) if source_path.exists() else None,
                    "corpus_category": category,
                    "compiler_check": None,
                    "bridge_status": "evaluation_error",
                    "diagnostic": str(error),
                    "artifacts": None,
                    "differential": None,
                }
                failures.append(f"{row['source_path']}: {error}")
            if row["bridge_status"] == "compiler_rejected":
                failures.append(f"{row['source_path']}: selected source failed compiler check")
            elif row["bridge_status"] == "pipeline_error":
                failures.append(f"{row['source_path']}: graph proof/replay failed: {row['diagnostic']}")
            elif row["bridge_status"] == "exported":
                diff = row["differential"]
                if diff["first_difference"] is not None:
                    failures.append(f"{row['source_path']}: differential mismatch")
            rows.append(row)

    for path, expected_hash in initial_source_hashes.items():
        if not path.is_file() or digest(path.read_bytes()) != expected_hash:
            failures.append(f"source changed during study: {path.relative_to(ROOT).as_posix()}")
    if not compiler.is_file() or digest(compiler.read_bytes()) != initial_compiler_hash:
        failures.append("compiler executable changed during study")

    statuses = {status: sum(row["bridge_status"] == status for row in rows)
                for status in ("exported", "unsupported_subset", "compiler_rejected",
                               "pipeline_error", "evaluation_error")}
    totals = {
        "attempted_sources": len(rows),
        "compiler_accepted_sources": sum(row.get("compiler_check", {}).get("status") == "accepted"
                                          for row in rows if row.get("compiler_check")),
        "bridge_status_counts": statuses,
        "source_graph_run_pairs": sum((row.get("differential") or {}).get("source_graph_run_pairs", 0)
                                       for row in rows),
        "secret_trace_pairs": sum((row.get("differential") or {}).get("secret_trace_pairs", 0)
                                  for row in rows),
        "secret_trace_pairs_different": sum((row.get("differential") or {}).get("secret_trace_pairs_different", 0)
                                             for row in rows),
        "call_events_compared": sum((row.get("differential") or {}).get("call_events_compared", 0)
                                    for row in rows),
    }
    result = {
        "experiment": "finite source-to-request-graph translation and full-text trace cross-check",
        "scope": "5 existing accepted research examples plus 15 existing balanced sourced projections; files are read-only and unsupported adapter-subset cases are reported separately",
        "selection": {
            "research_accepted": [p.relative_to(ROOT).as_posix() for p in research],
            "sourced_balanced": [p.relative_to(ROOT).as_posix() for p in balanced],
            "no_prompt_or_output_rewrites": True,
        },
        "probe_grid": {
            "chars_per_token": DIVISOR,
            "seeds": list(SEEDS),
            "public_text_samples": list(TEXT_CANDIDATES),
            "public_boolean_assignments": "all combinations",
            "secret_assignments": "all combinations over false/true for Boolean secrets and bounded empty/short/UTF-8 text samples for text secrets",
            "source_and_graph_traces": "complete ordered modeled requests, full abstract responses, per-call token usage, and stop status",
            "max_calls_per_run": MAX_CALLS,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "compiler_sha256": initial_compiler_hash,
            "adapter_sha256": digest((ROOT / "audit/source_to_graph.py").read_bytes()),
            "source_cost_parser_sha256": digest((ROOT / "audit/certificate_audit.py").read_bytes()),
            "graph_checker_sha256": digest((ROOT / "audit/orchgraph.py").read_bytes()),
            "replayer_sha256": digest((ROOT / "audit/replay_graph_certificate.py").read_bytes()),
            "evaluator_sha256": digest(Path(__file__).read_bytes()),
        },
        "totals": totals,
        "files": rows,
        "failures": failures,
        "limits": [
            "the source adapter is not a verified translation and only handles its explicit acyclic subset",
            "the AST reference interpreter and graph probe are separate evaluators but implement the same declared finite mock-oracle contract",
            "finite trace agreement is evidence for this corpus and grid, not a source-translation proof or mechanized metatheory",
            "the output oracle is a reproducible test generator; it is not a deployed provider or a claim about real request serialization",
            "unsupported rows are selection outcomes, not compiler rejections unless the separate compiler gate says so",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (output_root / "evaluation.json").write_bytes(encoded)
    mapping = {
        "format": "orchlang-source-graph-corpus-map",
        "version": 1,
        "evaluation_sha256": digest(encoded),
        "files": [{"source_path": row["source_path"],
                   "source_sha256": row["source_sha256"],
                   "corpus_category": row["corpus_category"],
                   "bridge_status": row["bridge_status"],
                   "artifacts": row["artifacts"],
                   "diagnostic": row["diagnostic"]} for row in rows],
    }
    (output_root / "corpus_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"totals": totals, "failures": failures,
                      "result": str(output_root / "evaluation.json")}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
