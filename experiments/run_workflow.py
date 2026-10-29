"""Compile, validate and execute one OrchLang workflow over a dataset.

Writes into --out:
  compile.json         findings, labels, static shapes/costs per strategy,
                       Lean verdicts and timings
  <condition>.jsonl    one record per input: store values, observed trace with
                       analysis-only fields (dummy, site, natural length)
Execution conditions: orig (no defense) and ours (shaped). Other strategies are
static: their traces are constant and determined by the validated shape.
Resumable: records already present are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import hashlib
import platform
import importlib.metadata
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import assurance as A, compiler as K, core as C, models as M, runtime as R, syntax, tools as T, validate, admission as B  # noqa: E402

STRATEGIES = ["ours", "naive", "uniform", "padall"]


def source_checkout_identity(root):
    """A source ZIP has no Git commit; never inherit an unrelated parent repo.

    Actual execution identity remains the exact implementation/source hashes.
    The exported manifest identifies custody without pretending it is Git HEAD.
    """
    root = Path(root).resolve()
    try:
        top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root,
                                          stderr=subprocess.DEVNULL, text=True).strip()).resolve()
        if top != root:
            raise ValueError("enclosing repository is not this source tree")
        return dict(git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                    git_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()))
    except (OSError, subprocess.CalledProcessError, ValueError):
        manifest = root / "publication/FILE_MANIFEST.json"
        return dict(git_commit=None, git_dirty=None, source_export=True,
                    export_manifest_sha256=A.sha256(manifest) if manifest.is_file() else None)


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def failure_record(item_id, condition, error, runtime):
    """Preserve known prefix usage and unconfirmed reservations on failure."""
    usage=runtime.ledger.snapshot() if hasattr(runtime,'ledger') else None
    return dict(id=item_id,condition=condition,error=repr(error),
                dispatched_current_call=getattr(error,'dispatched',None),
                usage_complete=usage['usage_complete'] if usage is not None else False,
                usage=usage,successful_prefix_events=len(getattr(runtime,'trace',[])),
                status='failed-not-a-completed-execution')


def compile_all(src_path, profiles, byte_bounded=False, context=4096, response_bytes=16):
    t0 = time.perf_counter()
    source = open(src_path, "rb").read()
    prog, binding = A.source_binding(source, profiles)
    wf = prog.workflow
    used = {c.model for c in C.calls(prog.body)}
    toks = {k: M.tokenizer_for(profiles[k].gguf) for k in used}
    findings = K.detect(prog)
    t_front = time.perf_counter() - t0
    shaped, t_shape = {}, {}
    byte_contract = (B.byte_contract(prog, context=context, response_bytes_per_token=response_bytes)
                     if byte_bounded else None)
    for s in STRATEGIES:
        t1 = time.perf_counter()
        shaped[s] = (B.certified_shaper(prog, profiles, toks, byte_contract, s) if byte_bounded
                     else K.Shaper(prog, profiles, toks, s).run())
        t_shape[s] = time.perf_counter() - t1
    high = prog.high_vars()
    t2 = time.perf_counter()
    _, checked_binding, checked = A.validate_candidates(source, profiles, {"original":prog.body, **shaped})
    if binding != checked_binding:
        raise ValueError("source binding changed during validation")
    verdicts = [checked["original"], *[checked[s] for s in STRATEGIES]]
    t_lean = time.perf_counter() - t2
    info = {
        "workflow": wf.name, "source": src_path,
        "source_lines": sum(1 for l in open(src_path, encoding="utf-8") if l.strip() and not l.strip().startswith("//")),
        "slots": prog.slots, "high": [prog.names[x] for x in high],
        "findings": [f.__dict__ for f in findings],
        "calls": len(C.calls(prog.body)),
        "original_lean": verdicts[0],
        "strategies": {s: {"lean": v, "static_cost": K.static_cost(shaped[s]), "shape_seconds": t_shape[s]}
                       for s, v in zip(STRATEGIES, verdicts[1:])},
        "frontend_seconds": t_front, "lean_seconds_batch": t_lean,
        "pads": {str(c.site): c.pad for c in C.calls(shaped["ours"])},
        "caps": {str(c.site): c.max_tokens for c in C.calls(prog.body)},
        "site_lines": {str(k): v for k, v in prog.site_lines.items()},
        "source_binding": binding,
        "request_targets": "heuristic execution envelopes; complete requests are admitted exactly before dispatch",
    }
    if byte_bounded:
        info["byte_contract"] = byte_contract
        certificate = B.check_certificate(shaped["ours"], byte_contract, toks)
        if not certificate["verdict"]["accepted"]:
            raise ValueError("Lean rejected the executable byte admission certificate")
        info["static_admission_certificate"] = certificate
        info["request_targets"] = "compositional UTF-8-byte envelope checked by Lean; explicit bounded-value interface"
    return wf, prog, shaped, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=os.environ.get("ORCHLANG_MODELS", "models.json"))
    ap.add_argument("--conditions", default="orig,ours")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--context", type=int, default=4096)
    ap.add_argument("--byte-bounded", action="store_true",
                    help="use the explicit byte-bounded original/shaped interface and Lean admission certificate")
    ap.add_argument("--response-bytes", type=int, default=16,
                    help="byte-bounded mode: visible-response UTF-8 bytes per visible token")
    ap.add_argument("--corpus", default=None, help="JSONL passages for tool retrieve (top 4)")
    ap.add_argument("--web", default=None, help="JSONL passages for tool web_search (top 3)")
    ap.add_argument("--keep", default="", help="comma-separated variables to store")
    ap.add_argument("--compile-only", action="store_true")
    ap.add_argument("--budgets",help="JSON per-model input/output/call limits, enforced before each dispatch")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    profiles = M.load_profiles(args.models)
    data = load_jsonl(args.data)
    if args.limit:
        data = data[: args.limit]
    if len({r["id"] for r in data}) != len(data):
        raise ValueError("duplicate dataset IDs")
    declared_models = {m.key for m in syntax.parse(open(args.workflow, encoding="utf-8").read()).models}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest = dict(schema="orchlang-execution-custody-v1", source_sha256=A.sha256(args.workflow),
                    data_sha256=A.sha256(args.data), selected_ids=[r["id"] for r in data],
                    model_contracts=A.model_contracts({k:profiles[k] for k in declared_models}),
                    implementation_sha256=A.implementation_hashes(root),
                    python=sys.version, platform=platform.platform(),
                    dependencies={name:importlib.metadata.version(name) for name in ("llama-cpp-python",)},
                    temperature=args.temperature, threads=args.threads,
                    context=args.context, byte_bounded=args.byte_bounded,
                    response_bytes_per_token=args.response_bytes if args.byte_bounded else None,
                    gpu_layers=os.environ.get("ORCHLANG_GPU_LAYERS","0"),
                    batch=int(os.environ.get("ORCHLANG_BATCH","128")),
                    kept_variables=args.keep, conditions=args.conditions.split(","),
                    corpus_sha256=A.sha256(args.corpus) if args.corpus else None,
                    web_sha256=A.sha256(args.web) if args.web else None,
                    spent_api_usd="0.00", observer="ordered-logical-model-usage-and-tool-names")
    budgets=json.loads(Path(args.budgets).read_text(encoding="utf-8")) if args.budgets else None
    manifest["budgets"]=budgets
    manifest.update(source_checkout_identity(root))
    backend_dir = os.environ.get("ORCHLANG_GGML_BACKENDS")
    manifest["backend_libraries"] = ({p.name:A.sha256(p) for p in sorted(Path(backend_dir).glob("*.dll"))}
                                     if backend_dir else {"source":"pinned llama-cpp-python wheel"})
    A.open_run(args.out, manifest)
    wf, prog, shaped, info = compile_all(args.workflow, profiles, args.byte_bounded, args.context,
                                         args.response_bytes)
    artifact=dict(schema='orchlang-validation-artifact-v1',source_binding=info['source_binding'],
                  model_contracts=manifest['model_contracts'],
                  candidates={name:C.stmt_json(body) for name,body in shaped.items()})
    Path(args.out,'validation-artifact.json').write_text(json.dumps(artifact,indent=2)+'\n',encoding='utf-8')
    with open(os.path.join(args.out, "compile.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(json.dumps({k: info[k] for k in ("workflow", "calls", "high")}), flush=True)
    for s in STRATEGIES:
        assert info["strategies"][s]["lean"]["accepted"], f"Lean rejected strategy {s}"
    if args.compile_only:
        return
    tools = dict(T.BASE)
    if args.corpus:
        tools["retrieve"] = T.Retriever([p["text"] for p in load_jsonl(args.corpus)], k=4)
    if args.web:
        tools["web_search"] = T.Retriever([p["text"] for p in load_jsonl(args.web)], k=3)
    caps = {t.name: t.max_tokens for t in wf.tools}
    used = sorted({c.model for c in C.calls(prog.body)})
    backends = {k: R.LlamaBackend(profiles[k], n_ctx=args.context, n_threads=args.threads, temperature=args.temperature)
                for k in used}
    rt = (B.ByteBoundedRuntime(backends, tools, caps, budgets=budgets, byte_contract=info["byte_contract"])
          if args.byte_bounded else R.Runtime(backends, tools, caps, budgets=budgets))
    keep = [v for v in args.keep.split(",") if v] or [wf.output]
    keep_slots = {v: prog.slots[v] for v in keep}
    progs = {"orig": prog.body, **shaped}
    refused = set()
    if args.byte_bounded:
        # The entry guard is a public admission decision taken before any dispatch.
        # Refused inputs are recorded once and excluded from both arms alike.
        bounds = info["byte_contract"]["value_bounds"]
        refusal_path = os.path.join(args.out, "guard-refusals.jsonl")
        prior = {json.loads(l)["id"] for l in open(refusal_path, encoding="utf-8")} if os.path.exists(refusal_path) else set()
        with open(refusal_path, "a", encoding="utf-8") as log:
            for item in data:
                sizes = {n: len(v.encode("utf-8")) for n, v in item["inputs"].items()}
                if any(size > bounds.get(prog.slots[n], 0) for n, size in sizes.items()):
                    refused.add(item["id"])
                    if item["id"] not in prior:
                        log.write(json.dumps(dict(id=item["id"], input_bytes=sizes,
                            bounds={n: bounds.get(prog.slots[n], 0) for n in sizes},
                            status="refused-by-entry-guard-before-dispatch")) + "\n")
    for cond in args.conditions.split(","):
        path = os.path.join(args.out, f"{cond}.jsonl")
        done = A.checked_record_ids(path,{r["id"] for r in data})
        with open(path, "a", encoding="utf-8") as f:
            for k, item in enumerate(data):
                if item["id"] in done or item["id"] in refused:
                    continue
                store = {prog.slots[n]: v for n, v in item["inputs"].items()}
                t0 = time.perf_counter()
                try:
                    r = rt.run(progs[cond], store, run_seed=k)
                except Exception as error:
                    failure = failure_record(item['id'],cond,error,rt)
                    with open(os.path.join(args.out,"failures.jsonl"),"a",encoding="utf-8") as log:
                        log.write(json.dumps(failure)+"\n")
                    raise
                rec = {"id": item["id"], "label": item.get("label"), "wall": time.perf_counter() - t0,
                       "store": {n: r.store.get(x, "") for n, x in keep_slots.items()},
                       "truncations": r.truncations, "usage":r.usage,
                       "source_binding_sha256":info["source_binding"]["binding_sha256"],
                       "execution_events": [e.audit for e in r.trace if e.kind=="llm"],
                       "byte_clips": getattr(rt, "byte_clips", []),
                       "trace": [[e.kind, e.name, e.input_tokens, e.output_tokens, round(e.latency, 4),
                                  e.dummy, e.site, e.natural] for e in r.trace]}
                f.write(json.dumps(rec) + "\n")
                f.flush()
                print(cond, k, item["id"], f"{rec['wall']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
