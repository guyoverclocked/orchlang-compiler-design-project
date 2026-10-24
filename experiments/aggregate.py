"""Aggregate run directories into paper tables and LaTeX macros.

Usage: python experiments/aggregate.py RUNS_DIR OUT_DIR [--extra JSON ...]
Writes OUT_DIR/results.json, OUT_DIR/results.tex (macros) and table files.
Every number in the paper's evaluation is produced here from raw records.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402

WORKFLOWS = ["routing", "chaining", "evaluator", "orchestrator", "switch", "email", "crag", "calculator", "adaptive"]
NAMES = {"routing": "Routing", "chaining": "Prompt chaining", "evaluator": "Evaluator--optimizer",
         "orchestrator": "Orchestrator--worker", "switch": "PF switch", "email": "Email agent",
         "crag": "Corrective RAG", "calculator": "Calculator agent", "adaptive": "Adaptive RAG"}
DECISION_VARS = {"routing": ["decision"], "chaining": ["gate"], "switch": ["intention"], "email": ["route"],
                 "crag": ["search"], "adaptive": ["src"]}
PRICE_IN, PRICE_OUT = 1.0, 4.0  # relative price per token (output 4x input)


def path(trace):
    return tuple(e[6] for e in trace if e[0] == "llm" and not e[5])


def decision(rec, wf):
    vals = tuple(str(rec["store"].get(v, "")) for v in DECISION_VARS.get(wf, []))
    return str((path(rec["trace"]), vals))


def norm(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def scorer(wf, item):
    if wf == "switch":
        return lambda r: r["store"].get("intention") == item["label"]
    if wf == "routing":
        return lambda r: r["store"].get("decision") == item["gold"]
    if wf == "crag":
        return lambda r: any(norm(a) in norm(r["store"].get("answer", "")) for a in item["answers"])
    if wf == "calculator":
        def ok(r):
            m = re.findall(r"-?\d[\d,]*\.?\d*", r["store"].get("out", "").split("FINAL:")[-1])
            try:
                return bool(m) and abs(float(m[0].replace(",", "").rstrip(".")) - float(item["gold"])) < 1e-6
            except ValueError:
                return False
        return ok
    if wf == "adaptive":
        if item["answers"]:
            return lambda r: any(norm(a) in norm(r["store"].get("gen", "")) for a in item["answers"])
        return lambda r: any(k in norm(r["store"].get("gen", "")) for k in
                             ["don't know", "do not know", "not provide", "no information", "not mention",
                              "doesn't mention", "does not mention", "not available", "cannot", "can't", "unable"])
    return None


def load_items(data_dir, wf):
    return {r["id"]: r for r in A.load(os.path.join(data_dir, f"{wf}.jsonl"))}


def cost(trace):
    c, i, o, lat = A.run_cost(trace)
    return c, i, o, PRICE_IN * i + PRICE_OUT * o, lat


def fmt(x, nd=1):
    return f"{x:.{nd}f}"


def analyze_workflow(run_dir, data_dir, wf, seed=0, perm=0):
    info = json.load(open(os.path.join(run_dir, "compile.json")))
    orig = {r["id"]: r for r in A.load(os.path.join(run_dir, "orig.jsonl"))}
    ours = {r["id"]: r for r in A.load(os.path.join(run_dir, "ours.jsonl"))}
    items = load_items(data_dir, wf)
    ids = [i for i in orig if i in ours]
    O = [orig[i] for i in ids]
    S = [ours[i] for i in ids]
    pads = info["pads"]
    # conformance: every shaped run's observed trace equals the Lean static shape
    static = [tuple(e) for e in info["strategies"]["ours"]["lean"]["static_shape"]] \
        if info["strategies"]["ours"]["lean"]["static_shape"] is not None else None
    conform = sum(1 for r in S if static is not None and
                  [tuple(["llm", e[1], e[2], e[3]]) if e[0] == "llm" else ("tool", e[1]) for e in r["trace"]] ==
                  [tuple(x) for x in static])
    oc = np.array([cost(r["trace"]) for r in O])
    sc = np.array([cost(r["trace"]) for r in S])
    import random
    rng = random.Random(seed)
    mean_in, mean_out = sc[:, 1].mean() - oc[:, 1].mean(), sc[:, 2].mean() - oc[:, 2].mean()
    conds = {
        "orig": [r["trace"] for r in O],
        "ours": [r["trace"] for r in S],
        "padonly": [A.derive_padonly(r, pads) for r in O],
        "noforce": [A.derive_noforce(r) for r in S],
        "randpad": [A.derive_randpad(r, mean_in, mean_out, max(1.0, oc[:, 0].mean()), rng) for r in O],
    }
    models = sorted({e[1] for trs in conds.values() for tr in trs for e in tr if e[0] == "llm"})
    max_calls = max(len(A.observed(tr)) for trs in conds.values() for tr in trs)
    targets = {"decision": {"orig": [decision(r, wf) for r in O], "ours": [decision(r, wf) for r in S]},
               "label": {"orig": [r["label"] for r in O], "ours": [r["label"] for r in S]}}
    leak = {}
    for cname, trs in conds.items():
        src = "ours" if cname in ("ours", "noforce") else "orig"
        for lat in ([False, True] if cname in ("orig", "ours") else [False]):
            obs = [A.observed(tr, lat) for tr in trs]
            X = [A.features(o, max_calls, models) for o in obs]
            key = cname + ("+lat" if lat else "")
            res = {"distinct": len({tuple(tuple(e[:4]) for e in o) for o in obs})}
            for t, ys in targets.items():
                y = ys[src]
                a = A.attack(X, y, seed)
                a["mi_bits"] = A.mutual_information(y, [tuple(tuple(e[:4]) for e in o) for o in obs])
                a["classes"] = len(set(y))
                if perm and key in ("orig", "ours+lat", "orig+lat"):
                    fast = A.attack(X, y, seed, trees=50)["balanced"]
                    a["perm_p"] = A.permutation_p(np.asarray(X, float), y, fast, perm, seed)
                res[t] = a
            leak[key] = res
    func = {}
    agree_dec = sum(1 for i in ids if decision(orig[i], wf).split("), (")[-1] == decision(ours[i], wf).split("), (")[-1]
                    and path(orig[i]["trace"]) == path(ours[i]["trace"])) / len(ids)
    func["decision_agreement"] = agree_dec
    out_var = info.get("output_var")
    func["output_equal"] = sum(1 for i in ids if orig[i]["store"] == ours[i]["store"]) / len(ids)
    sc_fn = None
    if wf in ("switch", "routing", "crag", "calculator", "adaptive"):
        co = [bool(scorer(wf, items[i])(orig[i])) for i in ids]
        cs = [bool(scorer(wf, items[i])(ours[i])) for i in ids]
        func.update(orig_acc=sum(co) / len(ids), ours_acc=sum(cs) / len(ids), mcnemar=A.mcnemar(co, cs))
    static_costs = {}
    for s, v in info["strategies"].items():
        c = v["static_cost"]
        static_costs[s] = {"calls": c[0], "input": c[1], "output": c[2], "price": PRICE_IN * c[1] + PRICE_OUT * c[2]}
    lat_o, lat_s = oc[:, 4], sc[:, 4]
    return {
        "workflow": wf, "n": len(ids), "findings": len(info["findings"]), "sites": info["calls"],
        "source_lines": info["source_lines"], "lean_seconds": info["lean_seconds_batch"],
        "frontend_seconds": info["frontend_seconds"],
        "shape_seconds": info["strategies"]["ours"]["shape_seconds"],
        "conformant_runs": conform, "static_shape_defined": static is not None,
        "truncations": int(sum(r["truncations"] for r in S)),
        "orig_cost": {"calls": oc[:, 0].mean(), "input": oc[:, 1].mean(), "output": oc[:, 2].mean(),
                      "price": oc[:, 3].mean(), "calls_min": oc[:, 0].min(), "calls_max": oc[:, 0].max()},
        "ours_cost": {"calls": sc[:, 0].mean(), "input": sc[:, 1].mean(), "output": sc[:, 2].mean(), "price": sc[:, 3].mean()},
        "static": static_costs,
        "latency": {"orig_mean": lat_o.mean(), "orig_sd": lat_o.std(), "ours_mean": lat_s.mean(), "ours_sd": lat_s.std(),
                    "orig_cv": lat_o.std() / lat_o.mean(), "ours_cv": lat_s.std() / lat_s.mean()},
        "leak": leak, "function": func,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("out")
    ap.add_argument("--data", default="experiments/data")
    ap.add_argument("--mutation", default=None)
    ap.add_argument("--differential", default=None)
    ap.add_argument("--transparency", default=None)
    ap.add_argument("--perm", type=int, default=0, help="permutation rounds for p-values (e.g. 200)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    res = {}
    for wf in WORKFLOWS:
        d = os.path.join(args.runs, wf)
        if os.path.exists(os.path.join(d, "ours.jsonl")) and os.path.getsize(os.path.join(d, "ours.jsonl")) > 0:
            res[wf] = analyze_workflow(d, args.data, wf, perm=args.perm)
    extra = {}
    for k in ("mutation", "differential", "transparency"):
        p = getattr(args, k)
        if p and os.path.exists(p):
            extra[k] = json.load(open(p))
    json.dump({"workflows": res, "extra": {k: (v.get("summary") or v.get("total") or v) if k != "differential" else v
                                           for k, v in extra.items()}},
              open(os.path.join(args.out, "results.json"), "w"), indent=1, default=float)
    write_tex(res, extra, args.out)
    print(json.dumps({wf: {"n": r["n"], "dec_orig": r["leak"]["orig"]["decision"]["balanced"],
                           "dec_ours": r["leak"]["ours"]["decision"]["balanced"],
                           "overhead": r["ours_cost"]["price"] / r["orig_cost"]["price"]} for wf, r in res.items()},
                     indent=1, default=float))


def pct(x):
    return "--" if x is None else f"{100 * x:.0f}"


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def write_tex(res, extra, out):
    M = {}
    wfs = [w for w in WORKFLOWS if w in res]
    dec_orig = [res[w]["leak"]["orig"]["decision"]["balanced"] for w in wfs]
    chance = [res[w]["leak"]["orig"]["decision"]["chance_balanced"] for w in wfs
              if res[w]["leak"]["orig"]["decision"].get("chance_balanced")]
    lab_orig = [res[w]["leak"]["orig"]["label"]["balanced"] for w in wfs]
    over = [res[w]["ours_cost"]["price"] / res[w]["orig_cost"]["price"] for w in wfs]
    over_tok = [(res[w]["ours_cost"]["input"] + res[w]["ours_cost"]["output"]) /
                (res[w]["orig_cost"]["input"] + res[w]["orig_cost"]["output"]) for w in wfs]
    naive_save = [1 - res[w]["static"]["ours"]["price"] / res[w]["static"]["naive"]["price"] for w in wfs]
    unif_save = [1 - res[w]["static"]["ours"]["price"] / res[w]["static"]["uniform"]["price"] for w in wfs]
    drops = [100 * (res[w]["function"]["orig_acc"] - res[w]["function"]["ours_acc"]) for w in wfs
             if "orig_acc" in res[w]["function"]]
    M["resWorkflows"] = str(len(wfs))
    M["resRuns"] = str(sum(2 * res[w]["n"] for w in wfs))
    M["resInputs"] = str(sum(res[w]["n"] for w in wfs))
    M["resDecisionMedian"] = pct(med(dec_orig))
    M["resDecisionMin"] = pct(min([x for x in dec_orig if x is not None], default=None))
    M["resDecisionChanceMedian"] = pct(med(chance)) if chance else "--"
    M["resLabelMedian"] = pct(med(lab_orig))
    M["resOverheadMedian"] = fmt(med(over) or 0)
    M["resOverheadMin"] = fmt(min(over))
    M["resOverheadMax"] = fmt(max(over))
    M["resTokenOverheadMedian"] = fmt(med(over_tok) or 0)
    M["resNaiveSavingMedian"] = pct(med(naive_save))
    M["resNaiveSavingMax"] = pct(max(naive_save))
    M["resUniformSavingMedian"] = pct(med(unif_save))
    M["resUniformSavingMax"] = pct(max(unif_save))
    M["resFuncMaxDrop"] = fmt(max(drops) if drops else 0.0)
    M["resConformant"] = str(sum(res[w]["conformant_runs"] for w in wfs))
    M["resShapedRuns"] = str(sum(res[w]["n"] for w in wfs))
    M["resDistinctOurs"] = str(max(res[w]["leak"]["ours"]["distinct"] for w in wfs))
    M["resTruncations"] = str(sum(res[w]["truncations"] for w in wfs))
    for k in ("padonly", "noforce", "randpad"):
        v = [res[w]["leak"][k]["decision"]["balanced"] for w in wfs]
        M[f"res{k.capitalize()}Median"] = pct(med(v))
        M[f"res{k.capitalize()}Leaky"] = str(sum(1 for w in wfs if (res[w]["leak"][k]["decision"]["balanced"] or 0) >
                                                  (res[w]["leak"][k]["decision"].get("chance_balanced") or 1) + 0.05))
    M["resLatCVOrig"] = fmt(med([res[w]["latency"]["orig_cv"] for w in wfs]) or 0, 2)
    M["resLatCVOurs"] = fmt(med([res[w]["latency"]["ours_cv"] for w in wfs]) or 0, 2)
    M["resLeanSeconds"] = fmt(med([res[w]["lean_seconds"] for w in wfs]) or 0)
    lat = [res[w]["leak"]["ours+lat"]["decision"]["balanced"] for w in wfs]
    M["resLatencyOursMedian"] = pct(med(lat))
    M["resLatencyOursMax"] = pct(max([x for x in lat if x is not None], default=None))
    M["resLatencyOrigMedian"] = pct(med([res[w]["leak"]["orig+lat"]["decision"]["balanced"] for w in wfs]))
    ps = [(w, res[w]["leak"]["ours+lat"][t].get("perm_p")) for w in wfs for t in ("decision", "label")]
    ps = [(w, p) for w, p in ps if p is not None]
    if ps:
        M["resLatPermTests"] = str(len(ps))
        M["resLatPermSignificant"] = str(sum(1 for _, p in ps if p < 0.05))
        M["resLatPermMin"] = f"{min(p for _, p in ps):.3f}"
    if "mutation" in extra:
        t = extra["mutation"]["total"]
        M.update(mutTotal=str(t["mutants"]), mutLeak=str(t["oracle_leak"]), mutAcceptedLeak=str(t["leak_accepted"]),
                 mutAccepted=str(t["accepted"]), mutRejected=str(t["rejected"]),
                 mutOps=str(len(extra["mutation"]["by_operator"])))
    if "differential" in extra:
        d = extra["differential"]
        M.update(diffPrograms=str(d["programs"]), diffLeanChecks=str(d["lean_checks"]),
                 diffPairs=str(sum(v["pairs"] for v in d["strategies"].values())),
                 diffOrigAccepted=str(d["original_accepted"]),
                 diffAllAccepted="yes" if all(v["accepted"] == d["programs"] for v in d["strategies"].values()) else "no",
                 diffTraceEqual=str(sum(v["trace_equal_pairs"] for v in d["strategies"].values())),
                 diffStoreEqual=str(sum(v["store_equal_runs"] for v in d["strategies"].values())),
                 diffRuns=str(sum(v["runs"] for v in d["strategies"].values())))
        if "padded_budget" in d:
            pb = d["padded_budget"]
            M["diffMixedPrograms"] = str(pb["mixed_programs"])
            M["diffTaintSavingMean"] = pct(pb["saving_vs"]["padall"]["mean"])
            M["diffTaintSavingMax"] = pct(pb["saving_vs"]["padall"]["max"])
        M["resDiffLeanSeconds"] = fmt(d["lean_seconds"])
    if "transparency" in extra:
        s = extra["transparency"]["summary"]
        M.update(trGreedyCases=str(s["0.0"]["cases"]), trGreedyEqual=str(s["0.0"]["visible_equal"]),
                 trSampleCases=str(s["0.8"]["cases"]), trSampleEqual=str(s["0.8"]["visible_equal"]),
                 trExactIn=str(s["0.0"]["exact_input"] + s["0.8"]["exact_input"]),
                 trExactOut=str(s["0.0"]["exact_output"] + s["0.8"]["exact_output"]))
    with open(os.path.join(out, "results.tex"), "w") as f:
        for k, v in sorted(M.items()):
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    # Table: workflows
    with open(os.path.join(out, "tab_workflows.tex"), "w") as f:
        for w in wfs:
            r = res[w]
            f.write(f"{NAMES[w]} & {r['sites']} & {r['source_lines']} & {r['findings']} & {r['n']} & "
                    f"{fmt(r['orig_cost']['calls'])} ({int(r['orig_cost']['calls_min'])}--{int(r['orig_cost']['calls_max'])}) & "
                    f"{r['static']['ours']['calls']} \\\\\n")
    # Table: leakage
    with open(os.path.join(out, "tab_leak.tex"), "w") as f:
        for w in wfs:
            L = res[w]["leak"]
            def b(c, t="decision"):
                return pct(L[c][t]["balanced"])
            f.write(f"{NAMES[w]} & {L['orig']['decision']['classes']} & {pct(L['orig']['decision']['chance_balanced'])} & "
                    f"{b('orig')} & {fmt(L['orig']['decision']['mi_pred_bits'], 2)} & {b('padonly')} & {b('randpad')} & "
                    f"{b('noforce')} & {b('ours')} & {fmt(L['ours']['decision']['mi_bits'], 2)} & "
                    f"{b('orig', 'label')} & {b('ours', 'label')} \\\\\n")
    # Table: overhead
    with open(os.path.join(out, "tab_overhead.tex"), "w") as f:
        for w in wfs:
            r = res[w]
            o, s, st = r["orig_cost"], r["ours_cost"], r["static"]
            f.write(f"{NAMES[w]} & {fmt(o['calls'])} & {fmt(o['input'], 0)} & {fmt(o['output'], 0)} & "
                    f"{s['calls']:.0f} & {s['input']:.0f} & {s['output']:.0f} & {fmt(s['price'] / o['price'])} & "
                    f"{fmt(st['naive']['price'] / o['price'])} & {fmt(st['uniform']['price'] / o['price'])} & "
                    f"{fmt(r['latency']['orig_mean'])} & {fmt(r['latency']['ours_mean'])} \\\\\n")
    # Table: function
    with open(os.path.join(out, "tab_function.tex"), "w") as f:
        for w in wfs:
            fn = res[w]["function"]
            acc = (f"{pct(fn['orig_acc'])} & {pct(fn['ours_acc'])} & {fn['mcnemar']['p']:.2f}"
                   if "orig_acc" in fn else "-- & -- & --")
            f.write(f"{NAMES[w]} & {acc} & {pct(fn['decision_agreement'])} & {pct(fn['output_equal'])} & "
                    f"{res[w]['truncations']} \\\\\n")


if __name__ == "__main__":
    main()
