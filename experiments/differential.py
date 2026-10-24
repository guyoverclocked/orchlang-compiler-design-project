"""Randomized differential validation of the untrusted compiler and runtime.

For random core programs and random secret labellings it checks that
 1. every shaping strategy's output is accepted by the Lean validator;
 2. Python's mirror of the discipline agrees with Lean on original programs;
 3. the Python runtime (mock backend) emits identical observed traces for
    shaped programs under different secret inputs and equal public inputs,
    and that each trace equals the Lean-reported static shape when defined;
 4. shaped and original programs compute the same final stores under the
    mock backend's transparent forced decoding.
Writes a JSON summary to the given output path.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import compiler as K, core as C, runtime as R, validate  # noqa: E402
from orchlang.models import Profile, Template, TEMPLATES  # noqa: E402

TEMPLATES["mock"] = Template("mock", None, "<{role}>{content}</>\n", "<a>", "<pad>", "</>\n")
PROFILE = Profile("m", "", "mock", filler=".")
TOOLS = {"upper": lambda x: x.upper()[:6], "first": lambda x: x[:1], "const": lambda v: v}


class CharTok:
    def count(self, s): return len(s)


def rand_expr(rng, nvars):
    parts = [C.ELit("<user>")]
    for _ in range(rng.randint(0, 2)):
        parts.append(C.EVar(rng.randrange(nvars)) if rng.random() < 0.7 else C.ELit(rng.choice(["a", "bc", "x:"])))
    parts.append(C.ELit("</>\n<a>"))
    return C.concat(parts)


class Gen:
    def __init__(self, rng, nvars):
        self.rng, self.nvars, self.site = rng, nvars, 0

    def stmt(self, depth):
        r = self.rng.random()
        if depth <= 0 or r < 0.45:
            if self.rng.random() < 0.75:
                self.site += 1
                return C.Call(self.site, self.rng.randrange(self.nvars), "m", rand_expr(self.rng, self.nvars),
                              None, self.rng.randint(1, 6))
            return C.Tool(self.rng.randrange(self.nvars), self.rng.choice(["upper", "first"]),
                          C.EVar(self.rng.randrange(self.nvars)))
        if r < 0.7:
            return C.Seq(self.stmt(depth - 1), self.stmt(depth - 1))
        g = C.Guard(self.rng.choice(["eq", "prefix"]), self.rng.randrange(self.nvars),
                    self.rng.choice(["a", "b", "c", ""]))
        if r < 0.9:
            return C.Ite(g, self.stmt(depth - 1), self.stmt(depth - 1) if self.rng.random() < 0.8 else C.Skip())
        return C.Loop(self.rng.randint(1, 3), g, self.stmt(depth - 1), False)


class FakeProg:
    def __init__(self, body, gamma, bounds):
        self.body, self.gamma, self.var_bounds = body, gamma, bounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--programs", type=int, default=500)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    strategies = ["ours", "naive", "uniform", "padall"]
    cases, payloads = [], []
    for k in range(args.programs):
        nvars = rng.randint(2, 5)
        body = Gen(rng, nvars).stmt(rng.randint(1, 4))
        nin = rng.randint(1, nvars)
        secret = {x for x in range(nin) if rng.random() < 0.5}
        gamma0 = {x: (C.HIGH if x in secret else C.LOW) for x in range(nvars)}
        gamma = K.infer_labels(body, gamma0)
        bounds = {x: 6 for x in range(nvars)}
        fp = FakeProg(body, gamma, bounds)
        high = sorted(x for x, l in gamma.items() if l == C.HIGH)
        shaped = {s: K.Shaper(fp, {"m": PROFILE}, {"m": CharTok()}, s).run() for s in strategies}
        cases.append(dict(body=body, gamma=gamma, nin=nin, secret=secret, shaped=shaped, high=high,
                          leaky=bool(K.detect_core(fp))))
        payloads.append(validate.payload(high, body, body))
        for s in strategies:
            payloads.append(validate.payload(high, body, shaped[s]))
    t0 = time.time()
    verdicts = validate.lean_validate_batch(payloads)
    lean_seconds = time.time() - t0

    summary = {s: {"accepted": 0, "trace_equal_pairs": 0, "pairs": 0, "static_shape_matches": 0,
                   "static_shape_runs": 0, "store_equal_runs": 0, "runs": 0} for s in strategies}
    orig_agree, orig_accepted, detect_agree = 0, 0, 0
    backend = R.MockBackend(PROFILE)
    rt = R.Runtime({"m": backend}, TOOLS, {})
    per = 1 + len(strategies)
    for k, case in enumerate(cases):
        v0 = verdicts[k * per]
        py0 = C.wt(case["gamma"], C.LOW, case["body"]) and v0["randomness_sites"]
        orig_agree += (v0["accepted"] == py0)
        orig_accepted += v0["accepted"]
        detect_agree += (v0["accepted"] == (not case["leaky"]))
        for j, s in enumerate(strategies):
            v = verdicts[k * per + 1 + j]
            summary[s]["accepted"] += v["accepted"]
            prog = case["shaped"][s]
            static = v["static_shape"]
            for run in range(args.runs):
                low = {x: rng.choice(["a", "b", "ab", ""]) for x in range(case["nin"]) if x not in case["secret"]}
                s1 = {**low, **{x: rng.choice(["a", "b", "c", "abc", ""]) for x in case["secret"]}}
                s2 = {**low, **{x: rng.choice(["a", "b", "c", "abc", ""]) for x in case["secret"]}}
                r1, r2 = rt.run(prog, s1, run), rt.run(prog, s2, run)
                summary[s]["pairs"] += 1
                summary[s]["trace_equal_pairs"] += (r1.observed() == r2.observed())
                if static is not None:
                    summary[s]["static_shape_runs"] += 1
                    summary[s]["static_shape_matches"] += ([list(e) for e in r1.observed()] == static)
                ro = rt.run(case["body"], s1, run)
                summary[s]["runs"] += 1
                summary[s]["store_equal_runs"] += (ro.store == r1.store)
    # Execution cost per strategy on identical inputs (input + 4 * output units),
    # over programs that contain both public and secret calls.
    crng = random.Random(args.seed + 1)
    savings = {"padall": [], "naive": [], "uniform": []}
    mixed = 0
    for case in cases:
        labs = {C.join(C.LOW, C.expr_label(case["gamma"], c.req)) for c in C.calls(case["body"])}
        stores = []
        for _ in range(4):
            st = {x: crng.choice(["a", "b", "ab", ""]) for x in range(case["nin"])}
            stores.append(st)
        cost = {}
        for s in strategies:
            tot = 0
            for k, st in enumerate(stores):
                r = rt.run(case["shaped"][s], st, k)
                tot += sum(e.input_tokens + 4 * e.output_tokens for e in r.trace if e.kind == "llm")
            cost[s] = tot
        if cost["ours"] == 0:
            continue
        has_low = any(C.join(C.LOW, C.expr_label(case["gamma"], c.req)) == C.LOW for c in C.calls(case["body"]))
        has_high = bool(case["high"]) and any(c.pad for c in C.calls(case["shaped"]["ours"]))
        if has_low and has_high:
            mixed += 1
            for b in savings:
                if cost[b] > 0:
                    savings[b].append(1 - cost["ours"] / cost[b])
    import statistics
    padded_budget = {"mixed_programs": mixed,
                     "saving_median": statistics.median(savings["padall"]) if savings["padall"] else None,
                     "saving_vs": {b: {"median": statistics.median(v) if v else None,
                                       "mean": sum(v) / len(v) if v else None,
                                       "max": max(v) if v else None} for b, v in savings.items()}}
    result = {"padded_budget": padded_budget, "programs": args.programs, "seed": args.seed, "lean_checks": len(payloads),
              "lean_seconds": round(lean_seconds, 2), "original_accepted": orig_accepted,
              "original_python_lean_agreement": orig_agree, "detector_lean_agreement": detect_agree,
              "strategies": summary}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
