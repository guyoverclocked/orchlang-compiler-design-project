"""Round-3 statistics and certified-mode analysis from raw execution records.

Inputs are immutable run directories. Nothing here re-executes a model.

* Primary (heuristic) study: per-workflow original-trace attack with its
  cross-validated predictions, a 95% bootstrap interval for balanced accuracy,
  a label-permutation p-value, Wilson intervals for inherited task accuracy and
  cost-ratio medians with and without the calculator stress test.
* Certified (byte-bounded) study: completion, refusal, output and shape
  equality, tokenizer-segmentation receipts, byte clips, certified cost relative
  to the original and to the heuristic shaped arm, and agreement of bounded
  originals with primary originals for the same dataset IDs and seeds.
* Categorical CRAG ablation: exact two-sided McNemar test.
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import aggregate as G  # noqa: E402
import analyze as A  # noqa: E402

PLAN = [("main", w) for w in ("routing", "chaining", "evaluator", "orchestrator", "switch", "email",
                              "crag", "calculator", "adaptive")] + \
       [("replication", w) for w in ("switch", "email", "crag")]
NAMES = {"routing": "Routing", "chaining": "Chaining", "evaluator": "Evaluator", "orchestrator": "Orchestrator",
         "switch": "PF switch", "email": "Email", "crag": "Corrective RAG", "calculator": "Calculator",
         "adaptive": "Adaptive RAG"}
DATA = ROOT / "experiments/data"


def label(group, workflow):
    return NAMES[workflow] + (" (Q)" if group == "replication" else "")


def records(path):
    if not path.exists():
        return {}
    return {r["id"]: r for r in (json.loads(l) for l in path.open(encoding="utf-8") if l.strip())}


def wilson(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def mcnemar_exact(improved, regressed):
    n = improved + regressed
    k = min(improved, regressed)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def balanced(pred, y, classes):
    return float(np.mean([(pred[y == c] == c).mean() for c in classes if (y == c).any()]))


def attack_with_ci(X, y, seed=0, boots=2000, perms=200):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedKFold, KFold, cross_val_predict
    y = np.asarray(y)
    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        return None
    def run(labels, trees=200):
        cv = (StratifiedKFold(5, shuffle=True, random_state=seed) if np.unique(labels, return_counts=True)[1].min() >= 5
              else KFold(5, shuffle=True, random_state=seed))
        clf = RandomForestClassifier(n_estimators=trees, random_state=seed, class_weight="balanced_subsample")
        return cross_val_predict(clf, np.asarray(X, float), labels, cv=cv)
    pred = run(y)
    observed = balanced(pred, y, classes)
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(boots):
        idx = rng.integers(0, len(y), len(y))
        present = np.unique(y[idx])
        if len(present) >= 2:
            samples.append(balanced(pred[idx], y[idx], present))
    lo, hi = np.percentile(samples, [2.5, 97.5])
    fast = balanced(run(y, 50), y, classes)
    hits = sum(balanced(run(perm, 50), perm, classes) >= fast
               for perm in (rng.permutation(y) for _ in range(perms)))
    return dict(balanced=observed, ci=[float(lo), float(hi)], chance=1 / len(classes),
                permutation_p=(hits + 1) / (perms + 1), permutations=perms, bootstrap=boots)


def primary(study, perms):
    rows = []
    for group, workflow in PLAN:
        run = study / group / workflow
        orig, ours = records(run / "orig.jsonl"), records(run / "ours.jsonl")
        ids = [i for i in orig if i in ours]
        O, S = [orig[i] for i in ids], [ours[i] for i in ids]
        obs = [A.observed(r["trace"], False) for r in O]
        models = sorted({e[0] + ":" + e[1] for r in O + S for e in r["trace"]})
        max_calls = max(len(A.observed(r["trace"])) for r in O + S)
        X = [A.features(o, max_calls, models) for o in obs]
        y = [G.decision(r, workflow) for r in O]
        attack = attack_with_ci(X, y, perms=perms)
        items = G.load_items(str(DATA), workflow)
        score = G.scorer(workflow, items[ids[0]]) if workflow in ("switch", "routing", "crag", "calculator", "adaptive") else None
        task = None
        if score is not None:
            correct = sum(bool(G.scorer(workflow, items[i])(orig[i])) for i in ids)
            task = dict(correct=correct, n=len(ids), rate=correct / len(ids), wilson=wilson(correct, len(ids)))
        oc = [G.cost(r["trace"])[3] for r in O]
        sc = [G.cost(r["trace"])[3] for r in S]
        rows.append(dict(group=group, workflow=workflow, label=label(group, workflow), pairs=len(ids),
                         classes=len(set(y)), attack=attack, task=task,
                         cost_ratio=float(np.mean(sc) / np.mean(oc)),
                         shaped_traces=len({json.dumps(A.observed(r["trace"])) for r in S})))
    main = [r["cost_ratio"] for r in rows if r["group"] == "main"]
    without = [r["cost_ratio"] for r in rows if r["group"] == "main" and r["workflow"] != "calculator"]
    return dict(workflows=rows, median_cost=statistics.median(main),
                median_cost_without_calculator=statistics.median(without),
                range_cost=[min(main), max(main)])


def certified(study, heuristic):
    rows = []
    for group, workflow in PLAN:
        run = study / group / workflow
        if not (run / "compile.json").exists():
            continue
        info = json.loads((run / "compile.json").read_text(encoding="utf-8"))
        static = info["strategies"]["ours"]["lean"]["static_shape"]
        orig, ours = records(run / "orig.jsonl"), records(run / "ours.jsonl")
        refused = records(run / "guard-refusals.jsonl")
        ids = [i for i in orig if i in ours]
        saved_equal = sum(orig[i]["store"] == ours[i]["store"] for i in ids)
        shape_equal = sum([list(e[:4]) if e[0] == "llm" else e[:2] for e in ours[i]["trace"]] ==
                          [e if e[0] == "llm" else e[:2] for e in static] for i in ids)
        events = [e for i in ids for r in (orig[i], ours[i]) for e in r["execution_events"]]
        segmented = sum(e.get("segmentation", {}).get("segmented", False) for e in events)
        clips = [c for i in ids for r in (orig[i], ours[i]) for c in r.get("byte_clips", [])]
        clipped_pairs = sum(bool(orig[i].get("byte_clips") or ours[i].get("byte_clips")) for i in ids)
        oc = [G.cost(orig[i]["trace"])[3] for i in ids]
        sc = [G.cost(ours[i]["trace"])[3] for i in ids]
        h_orig = records(heuristic / group / workflow / "orig.jsonl")
        h_ours = records(heuristic / group / workflow / "ours.jsonl")
        shared = [i for i in ids if i in h_orig and i in h_ours]
        hc = [G.cost(h_ours[i]["trace"])[3] for i in shared]
        same_original = sum(orig[i]["store"] == h_orig[i]["store"] for i in shared)
        task = None
        if workflow in ("switch", "routing", "crag", "calculator", "adaptive"):
            items = G.load_items(str(DATA), workflow)
            correct = sum(bool(G.scorer(workflow, items[i])(orig[i])) for i in ids)
            primary_correct = sum(bool(G.scorer(workflow, items[i])(h_orig[i])) for i in shared)
            task = dict(correct=correct, n=len(ids), primary_correct_same_ids=primary_correct, shared=len(shared))
        bounds = info.get("byte_contract", {})
        max_tn = max((e[2] + e[3] for e in static if e[0] == "llm"), default=0)
        rows.append(dict(group=group, workflow=workflow, label=label(group, workflow),
                         planned=len(ids) + len(refused), refused=len(refused), pairs=len(ids),
                         saved_equal=saved_equal, shape_equal=shape_equal,
                         certificate_accepted=info.get("static_admission_certificate", {}).get("verdict", {}).get("accepted"),
                         llm_events=len(events), segmented_events=segmented,
                         clip_events=dict(llm=sum(c["kind"] == "llm" for c in clips),
                                          tool=sum(c["kind"] == "tool" for c in clips)),
                         clipped_pairs=clipped_pairs, max_t_plus_n=max_tn,
                         cost_ratio=float(np.mean(sc) / np.mean(oc)),
                         certified_over_heuristic=(float(np.mean(sc) / np.mean(hc)) if hc else None),
                         bounded_original_equals_primary=same_original, shared_with_primary=len(shared),
                         task=task, context=bounds.get("context"),
                         response_bytes_per_token=bounds.get("response_bytes_per_token")))
    main = [r["cost_ratio"] for r in rows if r["group"] == "main"]
    over = [r["certified_over_heuristic"] for r in rows if r["certified_over_heuristic"]]
    return dict(workflows=rows,
                totals=dict(planned=sum(r["planned"] for r in rows), refused=sum(r["refused"] for r in rows),
                            pairs=sum(r["pairs"] for r in rows), saved_equal=sum(r["saved_equal"] for r in rows),
                            shape_equal=sum(r["shape_equal"] for r in rows),
                            llm_events=sum(r["llm_events"] for r in rows),
                            segmented_events=sum(r["segmented_events"] for r in rows),
                            clipped_pairs=sum(r["clipped_pairs"] for r in rows),
                            llm_clips=sum(r["clip_events"]["llm"] for r in rows),
                            tool_clips=sum(r["clip_events"]["tool"] for r in rows),
                            bounded_original_equals_primary=sum(r["bounded_original_equals_primary"] for r in rows),
                            shared_with_primary=sum(r["shared_with_primary"] for r in rows)),
                median_cost=statistics.median(main) if main else None,
                median_certified_over_heuristic=statistics.median(over) if over else None)


def pct(x):
    return f"{100 * x:.1f}"


def tex(primary_result, certified_result, categorical):
    macros = {}
    out = []
    for r in primary_result["workflows"]:
        a, t = r["attack"], r["task"]
        ba = (f"{pct(a['balanced'])} [{pct(a['ci'][0])}, {pct(a['ci'][1])}]" if a else "--")
        p = ("--" if not a else ("$<$0.005" if a["permutation_p"] < 0.005 else f"{a['permutation_p']:.2f}"))
        task = (f"{pct(t['rate'])} [{pct(t['wilson'][0])}, {pct(t['wilson'][1])}]" if t else "--")
        sep = "\\midrule\n" if r["group"] == "replication" and r["workflow"] == "switch" else ""
        out.append(f"{sep}{r['label']} & {r['pairs']} & {r['classes']} & {ba} & {p} & {r['shaped_traces']} & "
                   f"{r['cost_ratio']:.2f} & {task} \\\\")
    Path_out = "\n".join(out) + "\n"
    cert = []
    for r in certified_result["workflows"]:
        sep = "\\midrule\n" if r["group"] == "replication" and r["workflow"] == "switch" else ""
        over = "--" if r["certified_over_heuristic"] is None else f"{r['certified_over_heuristic']:.2f}"
        cert.append(f"{sep}{r['label']} & {r['pairs']}/{r['planned']} & {r['saved_equal']}/{r['pairs']} & "
                    f"{r['shape_equal']}/{r['pairs']} & {r['segmented_events']:,}/{r['llm_events']:,} & "
                    f"{r['clipped_pairs']} & {r['bounded_original_equals_primary']}/{r['shared_with_primary']} & "
                    f"{r['max_t_plus_n']:,} & {r['cost_ratio']:.2f} & {over} \\\\")
    T = certified_result["totals"]
    macros.update(
        rThreeMedianCost=f"{primary_result['median_cost']:.2f}",
        rThreeMedianCostNoCalc=f"{primary_result['median_cost_without_calculator']:.2f}",
        rThreeCertPlanned=f"{T['planned']:,}", rThreeCertRefused=str(T["refused"]),
        rThreeCertPairs=f"{T['pairs']:,}", rThreeCertSaved=f"{T['saved_equal']:,}",
        rThreeCertShape=f"{T['shape_equal']:,}", rThreeCertCalls=f"{T['llm_events']:,}",
        rThreeCertSegmented=f"{T['segmented_events']:,}", rThreeCertClippedPairs=str(T["clipped_pairs"]),
        rThreeCertLlmClips=f"{T['llm_clips']:,}", rThreeCertToolClips=f"{T['tool_clips']:,}",
        rThreeCertSameOrig=f"{T['bounded_original_equals_primary']:,}",
        rThreeCertShared=f"{T['shared_with_primary']:,}",
        rThreeCertMedianCost=("--" if certified_result["median_cost"] is None else f"{certified_result['median_cost']:.2f}"),
        rThreeCertOverHeuristic=("--" if certified_result["median_certified_over_heuristic"] is None
                                 else f"{certified_result['median_certified_over_heuristic']:.2f}"),
        rThreeMcNemarP=f"{categorical['mcnemar_p']:.1e}".replace("e-0", "\\times10^{-").replace("e-", "\\times10^{-") + "}",
    )
    lines = "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in macros.items())
    return lines, Path_out, "\n".join(cert) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--primary", type=Path, default=ROOT / "publication/evidence/round2-homogeneous")
    ap.add_argument("--certified", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--permutations", type=int, default=200)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    p = primary(args.primary, args.permutations)
    c = certified(args.certified, args.primary)
    categorical = dict(improved=28, regressed=1, mcnemar_p=mcnemar_exact(28, 1),
                       source="publication/evidence/round2-analysis-v2/summary.json")
    result = dict(schema="orchlang-round3-analysis-v1", primary=p, certified=c, categorical=categorical)
    (args.output / "round3-analysis.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    macros, primary_rows, certified_rows = tex(p, c, categorical)
    (args.output / "round3-macros.tex").write_text(macros, encoding="utf-8")
    (args.output / "round3-primary.tex").write_text(primary_rows, encoding="utf-8")
    (args.output / "round3-certified.tex").write_text(certified_rows, encoding="utf-8")
    print(json.dumps(dict(primary_median=p["median_cost"], certified=c["totals"],
                          mcnemar=categorical["mcnemar_p"]), indent=1))


if __name__ == "__main__":
    main()
