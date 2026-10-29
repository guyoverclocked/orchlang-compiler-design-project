"""Run pinned upstream frameworks and explicit OrchLang local CPU ports.

Requires optional dependencies in real-workflows-requirements.txt, cached
upstream sources, the pinned tokenizer, and the pinned local Ollama model.
Every invocation in both arms performs actual inference; no results are replayed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.local_model import LocalModel
from runtime.workflow_originals import original_langgraph, original_promptflow, port


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trace_identity(trace):
    # Parallel independent calls may arrive in any order; compare their
    # complete messages/response multiset, including schema and token counts.
    return sorted(json.dumps(dict(request=e["rendered_request"], schema=e["schema"],
        response=e.get("response"), input=e.get("server_input_tokens"),
        output=e.get("generated_tokens"), status=e["status"]), sort_keys=True,
        ensure_ascii=False) for e in trace)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", required=True, type=Path)
    p.add_argument("--tokenizer", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--orchc", required=True, type=Path)
    p.add_argument("--protocol", type=Path, default=ROOT/"bench/protocols/real-workflows-local-v1.json")
    args = p.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    cp = ROOT/protocol["corpus"]
    corpus = json.loads(cp.read_text(encoding="utf-8"))
    if sha(cp) != protocol["corpus_sha256"]:
        raise ValueError("frozen corpus hash mismatch")
    for case in corpus["cases"]:
        if case["original_framework"] == "langgraph":
            for path_key, hash_key in [("snippet", "snippet_sha256"), ("executable", "executable_sha256")]:
                if sha(cp.parent/case[path_key]) != case[hash_key]:
                    raise ValueError("frozen upstream snippet mismatch")
        records = case.get("source_files", [case["source"]])
        for record in records:
            local = args.sources/record["repo"].replace("/", "--")/record["path"]
            if sha(local) != record["sha256"]:
                raise ValueError("pinned upstream source mismatch: " + record["path"])
    compiler_checks = []
    for kernel in corpus["kernels"]:
        path = cp.parent/kernel["file"]
        if sha(path) != kernel["sha256"]:
            raise ValueError("frozen kernel source mismatch")
        command = [str(args.orchc.resolve()), "check", str(path)]
        r = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        compiler_checks.append(dict(command=command, exit=r.returncode, stdout=r.stdout, stderr=r.stderr))
        if r.returncode:
            raise RuntimeError("executable port kernel rejected by production compiler")
    args.output.mkdir(parents=True, exist_ok=False)
    backend = LocalModel(args.tokenizer, protocol["model"]["tokenizer_sha256"])
    packages = sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())
    source_files = [ROOT/"runtime/local_model.py", ROOT/"runtime/workflow_kernels.py",
                    ROOT/"runtime/workflow_originals.py", Path(__file__)]
    manifest = dict(status="running", started_utc=datetime.now(timezone.utc).isoformat(),
        protocol_sha256=sha(args.protocol), corpus_sha256=sha(cp), compiler_sha256=sha(args.orchc),
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        dirty_tree=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        implementation_sha256={str(f.relative_to(ROOT)).replace("\\", "/"):sha(f) for f in source_files},
        python=sys.version, platform=platform.platform(), dependencies=packages,
        model=backend.identity, compiler_kernel_checks=compiler_checks,
        corpus_workflows=len(corpus["cases"]), unique_patterns=corpus["unique_upstream_patterns"],
        replay_generation_calls=0, cost_usd="0.00")
    results, failures = [], []
    def checkpoint():
        for name, data in [("manifest", manifest), ("results", results), ("failures", failures)]:
            (args.output/(name+".json")).write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    checkpoint()
    for case in corpus["cases"]:
        for output_cap in protocol["output_caps"]:
            for seed in protocol["seeds"]:
                for input_index, values in enumerate(protocol["inputs"][case["id"]]):
                    row = dict(id=case["id"], output_cap=output_cap, input_index=input_index,
                               seed=seed, inputs=values, translation=case["translation"], arms={})
                    for arm in ("original", "port"):
                        backend.begin(input_cap=protocol["input_cap"], output_cap=output_cap,
                                      max_calls=case["max_calls"], seed=seed)
                        start = time.perf_counter()
                        try:
                            if arm == "port":
                                output = port(case, values, cp.parent, backend)
                            elif case["original_framework"] == "langgraph":
                                output = original_langgraph(case, values, cp.parent, backend)
                            else:
                                output = original_promptflow(case, values, args.sources, backend)
                            observed = backend.totals()
                            violated = (observed["input"]+observed["output"] > observed["runtime_bound"] or
                                        observed["calls"] > case["max_calls"] or
                                        any(e["status"] != "ok" for e in backend.trace))
                            row["arms"][arm] = dict(status="ok", output=output, usage=observed,
                                violates_runtime_bound=violated, trace=backend.trace,
                                elapsed_seconds=time.perf_counter()-start)
                        except Exception as error:
                            row["arms"][arm] = dict(status="failed", error=repr(error),
                                traceback=traceback.format_exc(), trace=backend.trace,
                                usage=backend.totals(), elapsed_seconds=time.perf_counter()-start)
                            failures.append(dict(id=case["id"], arm=arm, cap=output_cap,
                                                 input_index=input_index, error=repr(error)))
                        print(json.dumps(dict(id=case["id"], cap=output_cap, input_index=input_index,
                            arm=arm, status=row["arms"][arm]["status"], calls=backend.attempts)), flush=True)
                        checkpoint()
                    a, b = row["arms"]["original"], row["arms"]["port"]
                    success = a["status"] == b["status"] == "ok"
                    row["outputs_equal"] = success and a["output"] == b["output"]
                    row["full_request_response_multisets_equal"] = success and trace_identity(a["trace"]) == trace_identity(b["trace"])
                    row["calls_equal"] = success and a["usage"]["calls"] == b["usage"]["calls"]
                    if not (row["outputs_equal"] and row["full_request_response_multisets_equal"] and row["calls_equal"]):
                        failures.append(dict(id=case["id"], cap=output_cap, input_index=input_index,
                                             error="differential workflow comparison failed"))
                    # The NER input suite has explicit expected answers. The
                    # other open-ended generation tasks have no quality label.
                    if case["id"] == "pf-ner":
                        expected = (["data scientist", "finance manager"] if input_index == 0 else ["(321) 654-0987"])
                        row["task_quality"] = dict(metric="exact entity set match; authored expected answers", expected=expected,
                            original_exact=success and sorted(a["output"].get("entities", [])) == sorted(expected),
                            port_exact=success and sorted(b["output"].get("entities", [])) == sorted(expected))
                    elif case["id"] == "lg-routing-graph":
                        expected = "joke" if input_index == 0 else "poem"
                        row["task_quality"] = dict(metric="requested route exact match", expected=expected,
                            original_exact=success and a["output"].get("decision") == expected,
                            port_exact=success and b["output"].get("decision") == expected)
                    else:
                        row["task_quality"] = dict(metric="unscored open-ended generation", rated=False)
                    results.append(row); checkpoint()
    summary = dict(comparison_rows=len(results), original_framework_executions=len(results),
        port_executions=len(results), corpus_workflows=6, distinct_upstream_patterns=5,
        direct_source_translation_workflows=1, hybrid_host_composition_workflows=5,
        direct_translation_comparisons=sum(r["translation"] == "direct-call-kernel" for r in results),
        hybrid_comparisons=sum(r["translation"] == "hybrid-host-composition" for r in results),
        outputs_equal=sum(r["outputs_equal"] for r in results),
        full_request_response_multisets_equal=sum(r["full_request_response_multisets_equal"] for r in results),
        actual_generation_calls=sum(a["usage"]["calls"] for r in results for a in r["arms"].values()),
        original_actual_generation_calls=sum(r["arms"]["original"]["usage"]["calls"] for r in results),
        port_actual_generation_calls=sum(r["arms"]["port"]["usage"]["calls"] for r in results),
        replay_generation_calls=0, infrastructure_or_differential_failures=len(failures),
        runtime_bound_violations=sum(a.get("violates_runtime_bound", False) for r in results for a in r["arms"].values()),
        source_scope="Runtime deployment experiment; one direct port plus five explicit hybrid host compositions; no all-input functional equivalence proof or production static tokenizer theorem.")
    (args.output/"summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    manifest.update(status="complete" if not failures else "completed-with-failures",
                    finished_utc=datetime.now(timezone.utc).isoformat(), summary=summary)
    checkpoint(); print(json.dumps(summary, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
