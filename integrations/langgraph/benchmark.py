"""Differentially execute admitted graph fixtures and exported source projections."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import platform
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

from orchgraph import Graph, reference_run  # noqa: E402  baseline only
from replay_graph_certificate import strict_json  # noqa: E402
from integrations.langgraph.backend import (  # noqa: E402
    MAX_PROBE_CALLS,
    OfflineOmegaOracle,
    execute_verified,
    prepare_graph,
)


SEEDS = (1, 17, 29)
TEXT_CANDIDATES = ("", "x", "public question", "é🙂 Unicode", 'quote " slash \\\nline')
PUBLIC_SAMPLE_INDICES = (0, 2, 3, 4)
DEFAULT_MAX_CALLS = 100
DEFAULT_OUTPUT = ROOT / "bench/results/langgraph_integration.json"
LANGGRAPH_PYPI_WHEEL_SHA256 = "e3f5f8ff4259f9281b73ff50fc9ef5cc3b025b8936b8283ecdca7cc0c4128690"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return _digest(encoded)


def _text_domain(graph: Graph, declaration: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in TEXT_CANDIDATES:
        if graph.estimate(value) <= declaration["max_tokens"] and value not in values:
            values.append(value)
    if not values:
        raise ValueError("text declaration has no fitting sample")
    return values


def _input_grid(graph: Graph) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public_flags = [name for name, item in graph.inputs.items()
                    if item["label"] == "public" and item["type"] == "boolean"]
    public_text = [name for name, item in graph.inputs.items()
                   if item["label"] == "public" and item["type"] == "text"]
    secret_names = [name for name, item in graph.inputs.items()
                    if item["label"] == "secret"]

    public_flag_rows = list(itertools.product((False, True), repeat=len(public_flags)))
    sample_count = 4 if public_text else 1
    public_stores: list[dict[str, Any]] = []
    for flags in public_flag_rows:
        for sample_index in range(sample_count):
            store = dict(zip(public_flags, flags))
            for input_index, name in enumerate(public_text):
                values = _text_domain(graph, graph.inputs[name])
                selected = [values[index] for index in PUBLIC_SAMPLE_INDICES
                            if index < len(values)] or values
                store[name] = selected[(sample_index + input_index) % len(selected)]
            public_stores.append(store)
    if not public_stores:
        public_stores = [{}]

    secret_domains: list[list[Any]] = []
    for name in secret_names:
        declaration = graph.inputs[name]
        if declaration["type"] == "boolean":
            secret_domains.append([False, True])
        else:
            secret_domains.append(_text_domain(graph, declaration))
    secret_stores = [dict(zip(secret_names, values))
                     for values in itertools.product(*secret_domains)]
    if not secret_stores:
        secret_stores = [{}]
    return public_stores, secret_stores


def _graph_cases() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    authored = ROOT / "examples/graphs/accepted"
    authored_certs = ROOT / "bench/results/graph_certificates"
    for graph_path in sorted(authored.glob("*.json")):
        cert_path = authored_certs / graph_path.name
        cases.append({
            "category": "authored_cyclic_graph_fixture",
            "graph": graph_path.relative_to(ROOT).as_posix(),
            "certificate": cert_path.relative_to(ROOT).as_posix(),
        })

    mapping_path = ROOT / "bench/results/source_graphs/corpus_mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    for item in mapping["files"]:
        if item.get("bridge_status") != "exported":
            continue
        artifacts = item["artifacts"]
        graph_path = ROOT / "bench/results/source_graphs" / artifacts["graph"]
        cert_path = ROOT / "bench/results/source_graphs" / artifacts["certificate"]
        category = "source_bridge_export:" + item["corpus_category"]
        cases.append({
            "category": category,
            "graph": graph_path.relative_to(ROOT).as_posix(),
            "certificate": cert_path.relative_to(ROOT).as_posix(),
        })
    return cases


def _run_case(case: dict[str, str], max_calls: int) -> dict[str, Any]:
    graph_path = ROOT / case["graph"]
    cert_path = ROOT / case["certificate"]
    raw_graph, raw_cert = graph_path.read_bytes(), cert_path.read_bytes()
    verified = prepare_graph(raw_graph, raw_cert)
    graph_doc = strict_json(raw_graph, "source graph")
    reference_graph = Graph(graph_doc)
    public_stores, secret_stores = _input_grid(reference_graph)
    oracle = OfflineOmegaOracle()
    rows: list[dict[str, Any]] = []
    compared_calls = truncated_runs = stopped_runs = different_runs = 0

    for public_index, public_values in enumerate(public_stores):
        for seed in SEEDS:
            for secret_values in secret_stores:
                store = {**public_values, **secret_values}
                baseline = reference_run(reference_graph, store, seed, max_calls)
                actual = execute_verified(
                    verified,
                    store,
                    seed,
                    oracle,
                    max_calls=max_calls,
                ).to_dict()
                projection = {
                    "trace": actual["trace"],
                    "stopped": actual["stopped"],
                }
                if "truncated_at_calls" in actual:
                    projection["truncated_at_calls"] = actual["truncated_at_calls"]
                expected = {
                    "trace": baseline["trace"],
                    "stopped": baseline["stopped"],
                }
                if "truncated_at_calls" in baseline:
                    expected["truncated_at_calls"] = baseline["truncated_at_calls"]
                equal = actual["status"] in ("stopped", "truncated") and projection == expected
                if not equal:
                    different_runs += 1
                    raise AssertionError(
                        f"LangGraph/reference_run mismatch for {case['graph']} "
                        f"at seed={seed}, public={public_values}, secret={secret_values}"
                    )
                if actual["status"] == "stopped":
                    stopped_runs += 1
                if actual["status"] == "truncated":
                    truncated_runs += 1
                compared_calls += actual["call_count"]
                rows.append({
                    "public_scenario": public_index,
                    "seed": seed,
                    "public_inputs": public_values,
                    "secret_inputs": secret_values,
                    "status": actual["status"],
                    "trace": actual["trace"],
                    "trace_sha256": _canonical_digest(actual["trace"]),
                    "stopped": actual["stopped"],
                    "truncated_at_calls": actual.get("truncated_at_calls"),
                    "control_steps": actual["control_steps"],
                    "trace_bytes": actual["trace_bytes"],
                    "reference_trace_sha256": _canonical_digest(baseline["trace"]),
                    "reference_equal": equal,
                })

    return {
        "category": case["category"],
        "graph": case["graph"],
        "certificate": case["certificate"],
        "graph_sha256": _digest(raw_graph),
        "certificate_sha256": _digest(raw_cert),
        "replay_attestation": verified.attestation,
        "public_scenario_count": len(public_stores),
        "secret_assignment_count": len(secret_stores),
        "seeds": list(SEEDS),
        "runs": len(rows),
        "trace_calls_compared": compared_calls,
        "stopped_runs": stopped_runs,
        "truncated_runs": truncated_runs,
        "different_runs": different_runs,
        "run_records": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if type(args.max_calls) is not int or not 1 <= args.max_calls <= MAX_PROBE_CALLS:
        parser.error(f"--max-calls must be in [1, {MAX_PROBE_CALLS}]")

    cases = _graph_cases()
    results = [_run_case(case, args.max_calls) for case in cases]
    grouped: dict[str, int] = {}
    for item in results:
        key = item["category"].split(":", 1)[0]
        grouped[key] = grouped.get(key, 0) + 1

    langgraph_meta = importlib.metadata.metadata("langgraph")
    requirements_lock = ROOT / "integrations/langgraph/requirements.lock"
    requirements_input = ROOT / "integrations/langgraph/requirements.in"
    backend_path = ROOT / "integrations/langgraph/backend.py"
    benchmark_path = ROOT / "integrations/langgraph/benchmark.py"
    tests_path = ROOT / "integrations/langgraph/test_backend.py"
    replayer_path = ROOT / "audit/replay_graph_certificate.py"
    producer_path = ROOT / "audit/orchgraph.py"
    source_bridge_path = ROOT / "audit/source_to_graph.py"
    corpus_mapping_path = ROOT / "bench/results/source_graphs/corpus_mapping.json"
    source_evaluation_path = ROOT / "bench/results/source_graphs/evaluation.json"
    document = {
        "format": "orchlang-langgraph-integration-evaluation",
        "version": 1,
        "experiment": "offline full-text differential execution on actual LangGraph StateGraph",
        "scope": {
            "authored_fixtures": "six accepted version-1 graph fixtures; includes productive cycles",
            "source_exports": "all seventeen graph exports already admitted by the bounded OrchLang source adapter",
            "attribution": "authored adapter/generated cases; not external user adoption or full ports of other workflow frameworks",
            "provider": "local deterministic full-text Ω test oracle; no network model provider or paid service",
            "comparison": "actual StateGraph execution trace versus audit/orchgraph.py reference_run on identical graph bytes, store, seed, and call horizon",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "langgraph": {
                "version": importlib.metadata.version("langgraph"),
                "license": langgraph_meta.get("License-Expression") or langgraph_meta.get("License"),
                "pypi_release_date": "2026-10-06",
                "pypi_wheel_sha256": LANGGRAPH_PYPI_WHEEL_SHA256,
            },
            "requirements_lock_sha256": _digest(requirements_lock.read_bytes()),
            "requirements_input_sha256": _digest(requirements_input.read_bytes()),
            "backend_sha256": _digest(backend_path.read_bytes()),
            "benchmark_script_sha256": _digest(benchmark_path.read_bytes()),
            "integration_tests_sha256": _digest(tests_path.read_bytes()),
            "independent_replayer_sha256": _digest(replayer_path.read_bytes()),
            "reference_producer_sha256": _digest(producer_path.read_bytes()),
            "source_bridge_sha256": _digest(source_bridge_path.read_bytes()),
            "source_graph_corpus_mapping_sha256": _digest(corpus_mapping_path.read_bytes()),
            "source_graph_evaluation_sha256": _digest(source_evaluation_path.read_bytes()),
        },
        "probe_grid": {
            "seeds": list(SEEDS),
            "public_text_candidates": list(TEXT_CANDIDATES),
            "public_sample_indices": list(PUBLIC_SAMPLE_INDICES),
            "public_boolean_assignments": "all combinations",
            "secret_assignments": "all combinations over false/true Boolean values and bounded fixed UTF-8 text candidates",
            "max_calls_per_run": args.max_calls,
            "trace_contents": "full ordered contract, ordinal, template, arguments, response text, input/output usage, stopped and truncated status are retained in run_records",
        },
        "totals": {
            "accepted_authored_graph_fixtures": sum(
                item["category"] == "authored_cyclic_graph_fixture" for item in results
            ),
            "admitted_source_bridge_exports": sum(
                item["category"].startswith("source_bridge_export:") for item in results
            ),
            "authored_fixture_executions": sum(
                item["runs"] for item in results
                if item["category"] == "authored_cyclic_graph_fixture"
            ),
            "source_export_executions": sum(
                item["runs"] for item in results
                if item["category"].startswith("source_bridge_export:")
            ),
            "executions": sum(item["runs"] for item in results),
            "trace_call_events_compared": sum(item["trace_calls_compared"] for item in results),
            "authored_fixture_trace_call_events": sum(
                item["trace_calls_compared"] for item in results
                if item["category"] == "authored_cyclic_graph_fixture"
            ),
            "source_export_trace_call_events": sum(
                item["trace_calls_compared"] for item in results
                if item["category"].startswith("source_bridge_export:")
            ),
            "stopped_executions": sum(item["stopped_runs"] for item in results),
            "truncated_executions": sum(item["truncated_runs"] for item in results),
            "different_executions": sum(item["different_runs"] for item in results),
        },
        "cases": results,
        "limitations": [
            "The graph source adapter is bounded and unaudited; source exports inherit its documented fidelity limits.",
            "The offline oracle is a reproducible fixture generator, not a real provider or tokenizer.",
            "The graph theorem remains conditional on compatible complete-request accounting and a shared cap-respecting outcome oracle.",
            "LangGraph execution demonstrates a runnable backend for these JSON graphs; it does not establish external adoption, production service behavior, termination, or finite total cost for productive cycles.",
            "Each StateGraph node executes one source graph state's calls in order, then its goto/guard/stop transition; the trace event cap counts each call and control event even within a node.",
        ],
    }
    encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8", newline="")
    print(json.dumps({"output": str(args.output), "totals": document["totals"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
