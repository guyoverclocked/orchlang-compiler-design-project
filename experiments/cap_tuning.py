"""Cost/fidelity trade-off of choosing output caps from profiling data.

For each workflow, inputs are split into calibration and test halves by a hash of
their id. Each call site's cap is set to a quantile q of the natural output lengths
observed at that site in undefended calibration runs (sites never reached keep their
declared cap). The workflow is recompiled and reshaped with the tuned caps, which also
tightens downstream input bounds, and validated in Lean. Reported per q: the shaped
program's static price relative to the mean undefended price on the test half, and
the fraction of test runs in which some call's natural output would exceed its tuned
cap (and therefore be truncated). Security is unaffected by the choice of caps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import compiler as K, core as C, models as M, syntax, validate  # noqa: E402

PRICE_OUT = 4.0


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def split(i):
    return int(hashlib.sha256(i.encode()).hexdigest(), 16) % 2


def quantile(xs, q):
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[k]


def recap(s, caps):
    if isinstance(s, C.Seq):
        return C.Seq(recap(s.a, caps), recap(s.b, caps))
    if isinstance(s, C.Call):
        return replace(s, max_tokens=caps.get(s.site, s.max_tokens))
    if isinstance(s, C.Ite):
        return C.Ite(s.g, recap(s.a, caps), recap(s.b, caps))
    if isinstance(s, C.Loop):
        return C.Loop(s.n, s.g, recap(s.body, caps), s.padded)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--models", default=os.environ.get("ORCHLANG_MODELS", "models.json"))
    ap.add_argument("--output", required=True)
    ap.add_argument("--quantiles", default="0.5,0.75,0.9,0.95,1.0")
    args = ap.parse_args()
    profiles = M.load_profiles(args.models)
    qs = [float(q) for q in args.quantiles.split(",")]
    out = {}
    payloads, keys = [], []
    for wf in sorted(os.listdir(args.runs)):
        d = os.path.join(args.runs, wf)
        if not os.path.exists(os.path.join(d, "orig.jsonl")) or not os.path.exists(f"workflows/{wf}.orch"):
            continue
        recs = load(os.path.join(d, "orig.jsonl"))
        if len(recs) < 10:
            continue
        cal = [r for r in recs if split(r["id"]) == 0]
        test = [r for r in recs if split(r["id"]) == 1]
        wfo = syntax.parse(open(f"workflows/{wf}.orch", encoding="utf-8").read())
        prog = K.lower(wfo, profiles)
        toks = {k: M.tokenizer_for(profiles[k].gguf) for k in {c.model for c in C.calls(prog.body)}}
        declared = {c.site: c.max_tokens for c in C.calls(prog.body)}
        nat = {}
        for r in cal:
            for e in r["trace"]:
                if e[0] == "llm":
                    nat.setdefault(e[6], []).append(e[3])
        test_price = sum(sum(e[2] + PRICE_OUT * e[3] for e in r["trace"] if e[0] == "llm") for r in test) / len(test)
        rows = []
        for q in qs:
            caps = {s: max(1, min(declared[s], quantile(v, q))) for s, v in nat.items()}
            body = recap(prog.body, caps)
            p2 = K.Program(prog.workflow, prog.slots, body, prog.gamma, prog.site_lines, caps, output=prog.output)
            lw = K.Lowerer(wfo, profiles)
            p2.var_bounds = K.var_bounds(p2, lw)
            shaped = K.Shaper(p2, profiles, toks, "ours").run()
            sc = K.static_cost(shaped)
            price = sc[1] + PRICE_OUT * sc[2]
            trunc_runs = sum(1 for r in test if any(e[0] == "llm" and e[3] > caps.get(e[6], declared[e[6]])
                                                    for e in r["trace"]))
            calls = [e for r in test for e in r["trace"] if e[0] == "llm"]
            trunc_calls = sum(1 for e in calls if e[3] > caps.get(e[6], declared[e[6]]))
            rows.append({"q": q, "price_ratio": price / test_price, "truncated_runs": trunc_runs / len(test),
                         "truncated_calls": trunc_calls / max(1, len(calls)), "calls": sc[0], "input": sc[1],
                         "output": sc[2]})
            payloads.append(validate.payload(p2.high_vars(), body, shaped))
            keys.append((wf, q))
        out[wf] = {"calibration": len(cal), "test": len(test), "test_price": test_price, "rows": rows}
    verdicts = validate.lean_validate_batch(payloads) if payloads else []
    for (wf, q), v in zip(keys, verdicts):
        for row in out[wf]["rows"]:
            if row["q"] == q:
                row["lean_accepted"] = v["accepted"]
    with open(args.output, "w") as f:
        json.dump(out, f, indent=1)
    for wf, v in out.items():
        print(wf, [(r["q"], round(r["price_ratio"], 2), round(r["truncated_runs"], 2), r.get("lean_accepted")) for r in v["rows"]])


if __name__ == "__main__":
    main()
