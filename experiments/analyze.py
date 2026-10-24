"""Leakage, overhead and functional-preservation analysis for workflow runs.

Observer model: per-event usage records (model, input tokens, output tokens,
latency; tool name) with all content hidden. Dummy flags, call sites and
natural lengths are analysis-only fields and never enter observer features.

Observation conditions:
  orig        recorded undefended runs
  ours        recorded shaped runs (Lean-validated program)
  padonly     derived from orig: every call padded to its static (T, N) but
              no dummy calls or loop padding (padding without shape alignment)
  noforce     derived from ours: shapes aligned and inputs padded, outputs not
              forced (deployments whose API cannot force output length)
  randpad     derived from orig: uniform random input/output padding whose
              mean equals ours' mean per-run padding overhead
Leakage of the static strategies (naive/uniform/padall) is zero by the same
validated theorem; only their static cost is reported.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import Counter, defaultdict
from typing import Dict, List

import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict
except ImportError:  # pragma: no cover
    RandomForestClassifier = None


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# ---------------------------------------------------------------- observations

def observed(trace, use_latency=False):
    out = []
    for kind, name, i, o, lat, dummy, site, nat in trace:
        if kind == "llm":
            out.append(("llm", name, i, o) + ((lat,) if use_latency else ()))
    return out


def derive_padonly(rec, pads):
    tr = []
    for kind, name, i, o, lat, dummy, site, nat in rec["trace"]:
        if kind == "llm":
            t, n = pads.get(str(site)) or (i, o)
            tr.append([kind, name, t, n, lat, dummy, site, nat])
    return tr


def derive_noforce(rec):
    tr = []
    for kind, name, i, o, lat, dummy, site, nat in rec["trace"]:
        if kind == "llm":
            tr.append([kind, name, i, min(nat, o), lat, dummy, site, nat])
    return tr


def derive_randpad(rec, mean_in, mean_out, n_calls, rng):
    tr = []
    for kind, name, i, o, lat, dummy, site, nat in rec["trace"]:
        if kind == "llm":
            ai = rng.randint(0, max(0, int(round(2 * mean_in / max(1, n_calls)))))
            ao = rng.randint(0, max(0, int(round(2 * mean_out / max(1, n_calls)))))
            tr.append([kind, name, i + ai, o + ao, lat, dummy, site, nat])
    return tr


def features(obs, max_calls, models):
    """Fixed-length vector: count, per-position (model id, in, out), totals."""
    v = [len(obs), sum(e[2] for e in obs), sum(e[3] for e in obs)]
    for k in range(max_calls):
        if k < len(obs):
            e = obs[k]
            v += [models.index(e[1]) + 1, e[2], e[3]] + ([e[4]] if len(e) > 4 else [])
        else:
            v += [0, -1, -1] + ([-1] if obs and len(obs[0]) > 4 else [])
    if obs and len(obs[0]) > 4:
        v.append(sum(e[4] for e in obs))
    return v


# ---------------------------------------------------------------- leakage measures

def mutual_information(labels, traces):
    """Plug-in I(label; trace) in bits with Miller-Madow bias correction."""
    n = len(labels)
    if n == 0:
        return 0.0
    def H(counts):
        h = -sum(c / n * math.log2(c / n) for c in counts.values() if c)
        return h + (len([c for c in counts.values() if c]) - 1) / (2 * n * math.log(2))
    hl = H(Counter(labels))
    ht = H(Counter(traces))
    hj = H(Counter(zip(labels, traces)))
    return max(0.0, hl + ht - hj)


def attack(X, y, seed=0, trees=200):
    y = np.asarray(y)
    classes, counts = np.unique(y, return_counts=True)
    majority = counts.max() / counts.sum()
    if len(classes) < 2:
        return {"accuracy": 1.0, "balanced": 1.0, "majority": 1.0, "chance_balanced": 1.0, "n": int(len(y))}
    if RandomForestClassifier is None:
        return {"accuracy": None, "balanced": None, "majority": float(majority),
                "chance_balanced": 1.0 / len(classes), "n": int(len(y))}
    # Stratified 5-fold CV when every class has five members, else shuffled 5-fold CV.
    cv = (StratifiedKFold(5, shuffle=True, random_state=seed) if counts.min() >= 5
          else KFold(5, shuffle=True, random_state=seed))
    clf = RandomForestClassifier(n_estimators=trees, random_state=seed, min_samples_leaf=1,
                                 class_weight="balanced_subsample")
    pred = cross_val_predict(clf, np.asarray(X, dtype=float), y, cv=cv)
    acc = float((pred == y).mean())
    bal = float(np.mean([(pred[y == c] == c).mean() for c in classes]))
    return {"accuracy": acc, "balanced": bal, "majority": float(majority),
            "chance_balanced": 1.0 / len(classes), "n": int(len(y)),
            "mi_pred_bits": mutual_information(list(y), list(pred))}


def permutation_p(X, y, observed_bal, rounds=0, seed=0, trees=50):
    """One-sided permutation test of the attacker's balanced accuracy: the
    fraction of label permutations whose balanced accuracy reaches the observed
    one (same features, same classifier with `trees` trees)."""
    if not rounds or observed_bal is None:
        return None
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(rounds):
        yp = rng.permutation(np.asarray(y, dtype=object))
        b = attack(X, yp, seed, trees)["balanced"]
        if b is not None and b >= observed_bal:
            hits += 1
    return (hits + 1) / (rounds + 1)


# ---------------------------------------------------------------- costs

def run_cost(trace, include_dummy=True):
    calls = inp = out = 0
    lat = 0.0
    for kind, name, i, o, l, dummy, site, nat in trace:
        if kind == "llm":
            calls += 1; inp += i; out += o; lat += l
    return calls, inp, out, lat


def summarize_costs(recs):
    a = np.array([run_cost(r["trace"]) for r in recs], dtype=float)
    return {"calls": a[:, 0].mean(), "input": a[:, 1].mean(), "output": a[:, 2].mean(),
            "latency": a[:, 3].mean(), "latency_sd": a[:, 3].std(), "n": len(recs)}


def mcnemar(a: List[bool], b: List[bool]):
    """Exact two-sided McNemar test on paired correctness."""
    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n01 + n10
    if n == 0:
        return {"orig_only": 0, "ours_only": 0, "p": 1.0}
    k = min(n01, n10)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n * 2
    return {"orig_only": n01, "ours_only": n10, "p": min(1.0, p)}


# ---------------------------------------------------------------- main

def analyze(run_dir, scorer=None, decision=None, perm_rounds=0, seed=0):
    info = json.load(open(os.path.join(run_dir, "compile.json")))
    orig = {r["id"]: r for r in load(os.path.join(run_dir, "orig.jsonl"))}
    ours = {r["id"]: r for r in load(os.path.join(run_dir, "ours.jsonl"))}
    ids = sorted(set(orig) & set(ours), key=str)
    orig_l = [orig[i] for i in ids]
    ours_l = [ours[i] for i in ids]
    pads = info["pads"]
    oc, sc = summarize_costs(orig_l), summarize_costs(ours_l)
    mean_in, mean_out = sc["input"] - oc["input"], sc["output"] - oc["output"]
    rng = random.Random(seed)
    conds = {
        "orig": [r["trace"] for r in orig_l],
        "ours": [r["trace"] for r in ours_l],
        "padonly": [derive_padonly(r, pads) for r in orig_l],
        "noforce": [derive_noforce(r) for r in ours_l],
        "randpad": [derive_randpad(r, mean_in, mean_out, max(1, oc["calls"]), rng) for r in orig_l],
    }
    models = sorted({e[1] for trs in conds.values() for tr in trs for e in tr if e[0] == "llm"})
    max_calls = max(len(observed(tr)) for trs in conds.values() for tr in trs)
    targets = {"label": [r["label"] for r in orig_l]}
    if decision:
        targets["decision"] = [str(r["store"].get(decision, "")) for r in orig_l]
    out = {"workflow": info["workflow"], "n": len(ids), "leakage": {}, "costs": {}, "static": {}}
    for cname, trs in conds.items():
        for lat in ([False, True] if cname in ("orig", "ours") else [False]):
            obs = [observed(tr, lat) for tr in trs]
            X = [features(o, max_calls, models) for o in obs]
            key = cname + ("+latency" if lat else "")
            res = {"distinct_traces": len(set(map(tuple, ([tuple(e[:4]) for e in o] for o in obs))))}
            for tname, y in targets.items():
                a = attack(X, y, seed)
                a["mi_bits"] = mutual_information(y, [tuple(tuple(e[:4]) for e in o) for o in obs])
                a["perm_p"] = permutation_p(np.asarray(X, float), np.asarray(y), a["accuracy"], perm_rounds, seed)
                res[tname] = a
            out["leakage"][key] = res
    out["costs"] = {"orig": oc, "ours": sc}
    for s, v in info["strategies"].items():
        out["static"][s] = v["static_cost"]
    if scorer:
        items = {}
        co = [bool(scorer(orig[i])) for i in ids]
        cs = [bool(scorer(ours[i])) for i in ids]
        out["function"] = {"orig_correct": sum(co) / len(ids), "ours_correct": sum(cs) / len(ids),
                           "agreement": sum(1 for i in ids if orig[i]["store"] == ours[i]["store"]) / len(ids),
                           "mcnemar": mcnemar(co, cs)}
    if decision:
        out["decision_agreement"] = sum(1 for i in ids if orig[i]["store"].get(decision) == ours[i]["store"].get(decision)) / len(ids)
    out["truncations"] = sum(r["truncations"] for r in ours_l)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--decision", default=None)
    ap.add_argument("--perm", type=int, default=0)
    args = ap.parse_args()
    print(json.dumps(analyze(args.run_dir, decision=args.decision, perm_rounds=args.perm), indent=1, default=float))
