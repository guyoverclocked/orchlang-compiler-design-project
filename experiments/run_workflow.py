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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import compiler as K, core as C, models as M, runtime as R, syntax, tools as T, validate  # noqa: E402

STRATEGIES = ["ours", "naive", "uniform", "padall"]


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def compile_all(src_path, profiles):
    t0 = time.perf_counter()
    wf = syntax.parse(open(src_path, encoding="utf-8").read())
    prog = K.lower(wf, profiles)
    used = {c.model for c in C.calls(prog.body)}
    toks = {k: M.tokenizer_for(profiles[k].gguf) for k in used}
    findings = K.detect(prog)
    t_front = time.perf_counter() - t0
    shaped, t_shape = {}, {}
    for s in STRATEGIES:
        t1 = time.perf_counter()
        shaped[s] = K.Shaper(prog, profiles, toks, s).run()
        t_shape[s] = time.perf_counter() - t1
    high = prog.high_vars()
    payloads = [validate.payload(high, prog.body, prog.body)] + [validate.payload(high, prog.body, shaped[s]) for s in STRATEGIES]
    t2 = time.perf_counter()
    verdicts = validate.lean_validate_batch(payloads)
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
    }
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
    ap.add_argument("--corpus", default=None, help="JSONL passages for tool retrieve (top 4)")
    ap.add_argument("--web", default=None, help="JSONL passages for tool web_search (top 3)")
    ap.add_argument("--keep", default="", help="comma-separated variables to store")
    ap.add_argument("--compile-only", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    profiles = M.load_profiles(args.models)
    wf, prog, shaped, info = compile_all(args.workflow, profiles)
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
    backends = {k: R.LlamaBackend(profiles[k], n_ctx=4096, n_threads=args.threads, temperature=args.temperature)
                for k in used}
    rt = R.Runtime(backends, tools, caps)
    data = load_jsonl(args.data)
    if args.limit:
        data = data[: args.limit]
    keep = [v for v in args.keep.split(",") if v] or [wf.output]
    keep_slots = {v: prog.slots[v] for v in keep}
    progs = {"orig": prog.body, **shaped}
    for cond in args.conditions.split(","):
        path = os.path.join(args.out, f"{cond}.jsonl")
        done = {r["id"] for r in load_jsonl(path)} if os.path.exists(path) else set()
        with open(path, "a", encoding="utf-8") as f:
            for k, item in enumerate(data):
                if item["id"] in done:
                    continue
                store = {prog.slots[n]: v for n, v in item["inputs"].items()}
                t0 = time.perf_counter()
                r = rt.run(progs[cond], store, run_seed=k)
                rec = {"id": item["id"], "label": item.get("label"), "wall": time.perf_counter() - t0,
                       "store": {n: r.store.get(x, "") for n, x in keep_slots.items()},
                       "truncations": r.truncations,
                       "trace": [[e.kind, e.name, e.input_tokens, e.output_tokens, round(e.latency, 4),
                                  e.dummy, e.site, e.natural] for e in r.trace]}
                f.write(json.dumps(rec) + "\n")
                f.flush()
                print(cond, k, item["id"], f"{rec['wall']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
