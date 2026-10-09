#!/usr/bin/env python3
"""Run authored Python StateGraph fixtures against exported graph probes.

The exporter is static. This study executes only the AST-validated authored
fixtures under the pinned offline LangGraph runtime and compares their
full-text request traces with the independently replay-gated graph backend.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit.orchgraph import Graph, reference_run  # noqa: E402
from integrations.langgraph.backend import (  # noqa: E402
    BackendError,
    OfflineRequestSession,
    execute_verified,
    prepare_graph,
)
from integrations.langgraph.source_frontend.extract import (  # noqa: E402
    FrontendError,
    extract_source,
    parse_contracts,
)
from integrations.langgraph.source_frontend.export import (  # noqa: E402
    _canonical,
    export_bytes,
)
from integrations.langgraph.source_frontend.runtime import bind_session  # noqa: E402


HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"
ARTIFACTS = HERE / "artifacts"
DEFAULT_OUTPUT = ROOT / "bench/results/langgraph_source_study.json"
SEEDS = (1, 17, 29)
MAX_CALLS = 3
MAX_CONTROL_STEPS = 100_000
TEXT_STORES = ("public question é🙂", "second input, with punctuation?")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8"))


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="." + path.name + ".", dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    temporary.replace(path)


def _save_artifacts(name: str, graph: dict[str, Any], sidecar: dict[str, Any],
                    report: dict[str, Any], attestation: dict[str, Any] | None) -> dict[str, str]:
    base = ARTIFACTS / name
    attestation_path = base.with_suffix(".attestation.json")
    graph_bytes = _canonical(graph)
    report_bytes = _canonical(report)
    sidecar = dict(sidecar)
    sidecar["study_artifacts"] = {
        "graph": base.name + ".graph.json",
        "certificate_or_report": base.name + ".certificate.json",
        "provenance": base.name + ".provenance.json",
        "attestation": base.name + ".attestation.json" if attestation is not None else None,
    }
    paths = {
        "graph": base.with_suffix(".graph.json"),
        "certificate": base.with_suffix(".certificate.json"),
        "provenance": base.with_suffix(".provenance.json"),
    }
    # Remove any earlier attestation before replacing the snapshots. If a
    # later write fails, no stale proof can appear to certify the new graph.
    attestation_path.unlink(missing_ok=True)
    _write(paths["graph"], graph_bytes)
    _write(paths["certificate"], report_bytes)
    _write(paths["provenance"], _canonical(sidecar))
    if attestation is not None:
        paths["attestation"] = attestation_path
        _write(paths["attestation"], _canonical(attestation))
    return {key: path.relative_to(ROOT).as_posix() for key, path in paths.items()}


def _source_app(source_raw: bytes, compiled_variable: str, filename: str) -> Any:
    # This helper is called only after extract_source accepts the exact bytes.
    # The AST gate permits only imports, TypedDict declarations, simple node
    # functions, static StateGraph builders, and one compile assignment.
    decoded = source_raw.decode("utf-8")
    syntax = ast.parse(decoded, filename=filename, mode="exec")
    namespace: dict[str, Any] = {"__name__": "orchlang_langgraph_source_fixture",
                                 "__file__": filename}
    exec(compile(syntax, filename, "exec"), namespace, namespace)
    app = namespace.get(compiled_variable)
    if not callable(getattr(app, "invoke", None)):
        raise RuntimeError("validated source did not produce a LangGraph compiled app")
    return app


def _run_source(app: Any, contracts: dict[str, Any], source_store: dict[str, Any],
                seed: int, max_calls: int) -> dict[str, Any]:
    session = OfflineRequestSession(
        contracts["name"], seed, contracts["models"], contracts["chars_per_token"],
        max_calls=max_calls,
    )
    status = "stopped"
    final_state: dict[str, Any] | None = None
    failure: dict[str, str] | None = None
    try:
        with bind_session(session):
            final_state = app.invoke(source_store, config={"recursion_limit": 256})
    except Exception as error:
        message = str(error)
        if isinstance(error, BackendError) and "offline request-session call cap" in message:
            status = "truncated"
        else:
            status = "runtime_error"
            failure = {"type": type(error).__name__, "message": message[:1000]}
    return {"status": status, "trace": session.trace,
            "stopped": status == "stopped", "failure": failure,
            "final_state": final_state}


def _graph_store(mapping: dict[str, Any], source_store: dict[str, Any]) -> dict[str, Any]:
    return {item["graph_name"]: source_store[item["source_key"]]
            for item in mapping["inputs"]}


def _paired_run(graph_doc: dict[str, Any], graph_report: dict[str, Any],
                mapping: dict[str, Any], contracts: dict[str, Any], source_raw: bytes,
                source_path: Path, source_store: dict[str, Any], seed: int,
                max_calls: int) -> dict[str, Any]:
    graph_raw = _canonical(graph_doc)
    certificate_raw = _canonical(graph_report)
    verified = prepare_graph(graph_raw, certificate_raw)
    source_app = _source_app(source_raw, mapping["compiled_variable"], str(source_path))
    source_run = _run_source(source_app, contracts, source_store, seed, max_calls)
    graph_run = execute_verified(
        verified,
        _graph_store(mapping, source_store),
        seed,
        max_calls=max_calls,
        max_control_steps=MAX_CONTROL_STEPS,
        recursion_limit=256,
    ).to_dict()
    if source_run["failure"] is not None:
        raise RuntimeError(f"actual source LangGraph failed: {source_run['failure']}")
    source_status = source_run["status"]
    graph_status = graph_run["status"]
    same = (source_run["trace"] == graph_run["trace"]
            and source_status == graph_status
            and source_run["stopped"] == graph_run["stopped"])
    if not same:
        raise RuntimeError(
            f"source/graph differential mismatch for {source_path.name}: "
            f"source={source_status}/{_digest(source_run['trace'])}, "
            f"graph={graph_status}/{_digest(graph_run['trace'])}"
        )
    return {
        "seed": seed,
        "inputs": source_store,
        "status": source_status,
        "stopped": source_run["stopped"],
        "trace_equal": same,
        "trace_sha256": _digest(source_run["trace"]),
        "call_count": len(source_run["trace"]),
        "trace": source_run["trace"],
    }


def _graph_probe_pair(graph_doc: dict[str, Any], mapping: dict[str, Any],
                      source_store: dict[str, Any], seed: int,
                      max_calls: int) -> dict[str, Any]:
    graph = Graph(graph_doc)
    source_run = reference_run(graph, _graph_store(mapping, source_store), seed, max_calls)
    return source_run


def run_study(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    try:
        from importlib.metadata import version
        langgraph_version = version("langgraph")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError("run the LangGraph source study with integrations/langgraph/.venv/bin/python") from error

    result: dict[str, Any] = {
        "format": "orchlang-langgraph-source-study",
        "version": 1,
        "purpose": "finite execution cross-check of actual LangGraph Python source and its static request-graph projection",
        "selection": "three authored fixtures cover dependent calls after a secret branch, two-way public routing, and a productive cycle; three rejected fixtures cover direct secret request input, atomic state-update mismatch, and secret-dependent template divergence",
        "environment": {"python": sys.version, "langgraph": langgraph_version},
        "oracle_contract": {
            "key": "Omega(workflow name, seed, normalized model contract, per-contract ordinal, exact template, ordered full-text arguments)",
            "implementation": "integrations.langgraph.backend.OfflineOmegaOracle",
            "response": "deterministic UTF-8 text with output usage within declared max_tokens",
            "scope": "offline declared model only; no deployed provider guarantee",
        },
        "limits": {"seeds": list(SEEDS), "cycle_max_calls": MAX_CALLS,
                   "max_control_steps": MAX_CONTROL_STEPS},
        "cases": [],
        "totals": {"source_execution_runs": 0, "source_graph_pairs": 0,
                   "source_graph_equal": 0, "call_events": 0,
                   "secret_assignment_pairs": 0, "secret_trace_equal": 0,
                   "secret_trace_different_pairs": 0,
                   "source_value_probe_pairs": 0, "source_value_probe_equal": 0,
                   "expected_relational_rejections": 0,
                   "expected_frontend_rejections": 0},
        "criteria": {
            "accepted": "every source run must complete or truncate at the configured call horizon exactly like the replay-gated graph backend, with byte-for-byte equal ordered request/response/usage trace",
            "relational_rejection": "the secret-template-divergence graph must be rejected by the graph checker; the actual source and independent value probe must agree per run, and at least one paired secret assignment must have a different trace",
            "frontend_rejection": "direct secret request arguments and same-node post-call reads of returned fields must fail closed during AST extraction",
        },
        "nonclaims": [
            "this authored finite study is not an exhaustive Python/LangGraph grammar test or source-translation proof",
            "the offline oracle does not establish actual model-provider behavior",
            "graph acceptance does not establish termination or a finite total budget for cycles",
            "only the declared state/contract assumptions and exported graph property are checked",
        ],
    }

    accepted_runs_by_case: dict[str, list[dict[str, Any]]] = {}
    contract_docs: dict[str, dict[str, Any]] = {}
    source_docs: dict[str, bytes] = {}
    graph_docs: dict[str, dict[str, Any]] = {}
    mappings: dict[str, dict[str, Any]] = {}

    for name in ("secret_dependent_chain", "productive_cycle", "rejected_secret_request_difference",
                 "rejected_secret_argument", "rejected_atomic_update"):
        source_path = EXAMPLES / f"{name}.py"
        contract_path = EXAMPLES / f"{name}.contracts.json"
        source_raw = source_path.read_bytes()
        contracts_raw = contract_path.read_bytes()
        case: dict[str, Any] = {
            "name": name,
            "source_path": source_path.relative_to(ROOT).as_posix(),
            "contracts_path": contract_path.relative_to(ROOT).as_posix(),
            "source_sha256": _sha(source_raw),
            "contracts_sha256": _sha(contracts_raw),
        }
        try:
            graph_doc, sidecar, graph_report, attestation = export_bytes(source_raw, contracts_raw)
        except FrontendError as error:
            case.update(frontend="rejected", diagnostic=str(error),
                        graph_check="not_run", replay="not_run", runs=[])
            if name not in {"rejected_secret_argument", "rejected_atomic_update"}:
                raise RuntimeError(f"unexpected AST frontend rejection for {name}: {error}") from error
            result["totals"]["expected_frontend_rejections"] += 1
            result["cases"].append(case)
            continue

        graph_raw = _canonical(graph_doc)
        certificate_raw = _canonical(graph_report)
        case.update(frontend="accepted", graph_check=graph_report["status"],
                    diagnostic=graph_report.get("diagnostic"),
                    replay=sidecar["checks"]["certificate_replay"],
                    graph_sha256=_sha(graph_raw), certificate_sha256=_sha(certificate_raw),
                    attestation_sha256=_sha(_canonical(attestation)) if attestation is not None else None)
        artifacts = _save_artifacts(name, graph_doc, sidecar, graph_report, attestation)
        case["artifacts"] = artifacts
        graph_docs[name] = graph_doc
        mappings[name] = sidecar["mapping"]
        contract_docs[name] = parse_contracts(contracts_raw)
        source_docs[name] = source_raw

        if name in ("secret_dependent_chain", "productive_cycle"):
            if graph_report["status"] != "accepted" or attestation is None:
                raise RuntimeError(f"expected graph/replay acceptance for {name}")
            source_app = _source_app(source_raw, sidecar["mapping"]["compiled_variable"], str(source_path))
            runs: list[dict[str, Any]] = []
            if name == "secret_dependent_chain":
                input_rows = []
                for question in TEXT_STORES:
                    for public_mode in (False, True):
                        input_rows.append((question, public_mode))
                for question, public_mode in input_rows:
                    secret_pair: list[dict[str, Any]] = []
                    for seed in SEEDS:
                        for private_route in (False, True):
                            store = {"question": question, "private_route": private_route,
                                     "public_mode": public_mode}
                            run = _paired_run(
                                graph_doc, graph_report, sidecar["mapping"], contract_docs[name],
                                source_raw, source_path, store, seed, MAX_CALLS,
                            )
                            runs.append(run)
                            secret_pair.append(run)
                            result["totals"]["source_graph_pairs"] += 1
                            result["totals"]["source_execution_runs"] += 1
                            result["totals"]["source_graph_equal"] += int(run["trace_equal"])
                            result["totals"]["call_events"] += run["call_count"]
                    # Group adjacent false/true assignments for each fixed
                    # public store and seed, then record their billing traces.
                    for offset in range(0, len(secret_pair), 2):
                        left, right = secret_pair[offset:offset + 2]
                        result["totals"]["secret_assignment_pairs"] += 1
                        equal = (left["trace"] == right["trace"]
                                 and left["status"] == right["status"])
                        if not equal:
                            raise RuntimeError("accepted secret_dependent_chain changed trace under its secret route")
                        result["totals"]["secret_trace_equal"] += int(equal)
            else:
                for repeat in (False, True):
                    for seed in SEEDS:
                        store = {"question": "loop question é", "repeat": repeat}
                        run = _paired_run(
                            graph_doc, graph_report, sidecar["mapping"], contract_docs[name],
                            source_raw, source_path, store, seed, MAX_CALLS,
                        )
                        expected_status = "truncated" if repeat else "stopped"
                        if run["status"] != expected_status:
                            raise RuntimeError(f"cycle expected {expected_status}, got {run['status']}")
                        runs.append(run)
                        result["totals"]["source_graph_pairs"] += 1
                        result["totals"]["source_execution_runs"] += 1
                        result["totals"]["source_graph_equal"] += int(run["trace_equal"])
                        result["totals"]["call_events"] += run["call_count"]
            case["runs"] = runs
            accepted_runs_by_case[name] = runs
        elif name == "rejected_secret_request_difference":
            if graph_report["status"] != "rejected" or attestation is not None:
                raise RuntimeError("secret request divergence was not rejected by the relational graph check")
            from audit.orchgraph import Graph as ProducerGraph
            producer_graph = ProducerGraph(graph_doc)
            source_app = _source_app(source_raw, sidecar["mapping"]["compiled_variable"], str(source_path))
            runs = []
            secret_traces: dict[tuple[int, bool], list[dict[str, Any]]] = {}
            for secret in (False, True):
                for seed in SEEDS:
                    store = {"private_route": secret}
                    source_run = _run_source(source_app, contract_docs[name], store, seed, MAX_CALLS)
                    graph_run = reference_run(
                        producer_graph,
                        _graph_store(sidecar["mapping"], store),
                        seed,
                        MAX_CALLS,
                    )
                    same = source_run["trace"] == graph_run["trace"] and source_run["stopped"] == graph_run["stopped"]
                    if not same or source_run["status"] != "stopped":
                        raise RuntimeError("actual rejected-source trace disagrees with the graph value probe")
                    secret_traces[(seed, secret)] = source_run["trace"]
                    runs.append({"seed": seed, "inputs": store, "status": source_run["status"],
                                 "stopped": source_run["stopped"], "source_graph_probe_equal": same,
                                 "trace_sha256": _digest(source_run["trace"]),
                                 "trace": source_run["trace"]})
                    result["totals"]["source_execution_runs"] += 1
                    result["totals"]["source_value_probe_pairs"] += 1
                    result["totals"]["source_value_probe_equal"] += int(same)
                    result["totals"]["call_events"] += len(source_run["trace"])
            differing = 0
            for seed in SEEDS:
                result["totals"]["secret_assignment_pairs"] += 1
                if secret_traces[(seed, False)] != secret_traces[(seed, True)]:
                    differing += 1
            if differing != len(SEEDS):
                raise RuntimeError("secret request difference fixture did not produce its expected per-seed witness")
            result["totals"]["secret_trace_different_pairs"] += differing
            case["secret_trace_comparison"] = {
                "pairs": len(SEEDS), "different_pairs": differing,
                "expected_property": "different exact templates under secret assignments; graph checker rejects",
            }
            case["runs"] = runs
            result["totals"]["expected_relational_rejections"] += 1
        else:
            raise AssertionError(name)
        result["cases"].append(case)

    result["source_frontend_sha256"] = _sha((HERE / "extract.py").read_bytes())
    result["exporter_sha256"] = _sha((HERE / "export.py").read_bytes())
    result["study_sha256"] = _sha(Path(__file__).read_bytes())
    result["runtime_helper_sha256"] = _sha((HERE / "runtime.py").read_bytes())
    result["langgraph_backend_sha256"] = _sha((ROOT / "integrations/langgraph/backend.py").read_bytes())
    result["checker_sha256"] = _sha((ROOT / "audit/orchgraph.py").read_bytes())
    result["replayer_sha256"] = _sha((ROOT / "audit/replay_graph_certificate.py").read_bytes())
    if result["totals"]["source_graph_pairs"] != result["totals"]["source_graph_equal"]:
        raise RuntimeError("one or more accepted source/graph trace comparisons failed")
    if result["totals"]["source_value_probe_pairs"] != result["totals"]["source_value_probe_equal"]:
        raise RuntimeError("one or more rejected-source/value-probe trace comparisons failed")
    _write(output_path, _canonical(result))
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = run_study(args.output)
    except Exception as error:
        print(f"LangGraph source study failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "output": str(args.output),
                      "totals": report["totals"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
