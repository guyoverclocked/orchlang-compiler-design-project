"""Fault injection: does the Lean validator catch compiler bugs?

Each mutation operator models a plausible shaping-compiler bug and is applied
at every applicable position of each workflow's validated program. Every mutant
is checked by Lean and, independently, by an empirical oracle: the mock runtime
executes the mutant under many secret inputs and reports whether observed
traces differ (a leak) or whether final stores differ from the original
program (a functional change). A sound validator must reject every mutant the
oracle shows to leak; mutants that change function must fail erasure checking.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import compiler as K, core as C, models as M, runtime as R, syntax, tools as T, validate  # noqa: E402


def positions(s, pred, path=()):
    """Paths (tuples of child indices) of statements satisfying pred."""
    out = [path] if pred(s) else []
    if isinstance(s, C.Seq):
        out += positions(s.a, pred, path + (0,)) + positions(s.b, pred, path + (1,))
    elif isinstance(s, C.Ite):
        out += positions(s.a, pred, path + (0,)) + positions(s.b, pred, path + (1,))
    elif isinstance(s, C.Loop):
        out += positions(s.body, pred, path + (0,))
    return out


def edit(s, path, f):
    if not path:
        return f(s)
    k, rest = path[0], path[1:]
    if isinstance(s, (C.Seq, C.Ite)):
        if k == 0:
            return replace(s, a=edit(s.a, rest, f))
        return replace(s, b=edit(s.b, rest, f))
    if isinstance(s, C.Loop):
        return replace(s, body=edit(s.body, rest, f))
    raise ValueError(path)


def lit_change(e):
    if isinstance(e, C.ELit):
        return C.ELit(e.value + " ")
    if isinstance(e, C.EApp):
        return C.EApp(lit_change(e.a), e.b)
    return C.EApp(e, C.ELit(" "))


OPERATORS = {
    "drop_pad": (lambda s: isinstance(s, C.Call) and s.pad, lambda s: replace(s, pad=None)),
    "shrink_input": (lambda s: isinstance(s, C.Call) and s.pad, lambda s: replace(s, pad=(s.pad[0] - 1, s.pad[1]))),
    "shrink_output": (lambda s: isinstance(s, C.Call) and s.pad and s.pad[1] > s.max_tokens,
                      lambda s: replace(s, pad=(s.pad[0], s.pad[1] - 1))),
    "undercut_cap": (lambda s: isinstance(s, C.Call) and s.pad, lambda s: replace(s, pad=(s.pad[0], s.max_tokens - 1))),
    "drop_dummy": (lambda s: isinstance(s, (C.Dummy, C.DummyTool)), lambda s: C.Skip()),
    "dummy_model": (lambda s: isinstance(s, C.Dummy), lambda s: replace(s, model=s.model + "-other")),
    "dummy_size": (lambda s: isinstance(s, C.Dummy), lambda s: replace(s, t=s.t + 1)),
    "unpad_loop": (lambda s: isinstance(s, C.Loop) and s.padded, lambda s: replace(s, padded=False)),
    "swap_seq": (lambda s: isinstance(s, C.Seq), lambda s: C.Seq(s.b, s.a)),
    "change_request": (lambda s: isinstance(s, C.Call), lambda s: replace(s, req=lit_change(s.req))),
    "site_clash": (lambda s: isinstance(s, C.Call) and s.site > 1, lambda s: replace(s, site=1)),
}


def oracle(prog, orig, secrets, backend_rt, high_inputs, runs=12):
    traces, changed = set(), False
    for k, sec in enumerate(secrets):
        store = {x: sec for x in high_inputs}
        r = backend_rt.run(prog, store, run_seed=0)
        traces.add(tuple(r.observed()))
        o = backend_rt.run(orig, store, run_seed=0)
        changed |= (o.store != r.store)
    return len(traces) > 1, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.environ.get("ORCHLANG_MODELS", "models.json"))
    ap.add_argument("--workflows", default="workflows")
    ap.add_argument("--output", required=True)
    ap.add_argument("--per-op", type=int, default=6, help="max positions per operator per workflow")
    args = ap.parse_args()
    profiles = M.load_profiles(args.models)
    rng = random.Random(5)
    secrets = ["", "yes", "no", "a" * 40, "story", "joke!", "web_search", "intent: billing\nurgency: critical",
               "grade: not funny\nfeedback: more", "FINAL: 3", "x?"] + [f"topic number {i} " * (i % 4 + 1) for i in range(30)]
    rows, payloads = [], []
    for fn in sorted(os.listdir(args.workflows)):
        if not fn.endswith(".orch"):
            continue
        wf = syntax.parse(open(os.path.join(args.workflows, fn), encoding="utf-8").read())
        prog = K.lower(wf, profiles)
        used = {c.model for c in C.calls(prog.body)}
        toks = {k: M.tokenizer_for(profiles[k].gguf) for k in used}
        shaped = K.Shaper(prog, profiles, toks, "ours").run()
        high_inputs = [prog.slots[i.name] for i in wf.inputs if i.secret]
        for op, (pred, f) in OPERATORS.items():
            ps = positions(shaped, pred)
            rng.shuffle(ps)
            for p in ps[: args.per_op]:
                mutant = edit(shaped, p, f)
                if mutant == shaped:
                    continue
                rows.append({"workflow": wf.name, "op": op, "path": list(p), "mutant": mutant, "prog": prog})
                payloads.append(validate.payload(prog.high_vars(), prog.body, mutant, prog.secret_inputs()))
        # forget_secret: the compiler drops a declared secret input from its labelling
        # and shapes consistently with the weaker labelling.
        for x in prog.secret_inputs():
            g0 = {y: (C.HIGH if y in prog.secret_inputs() and y != x else C.LOW) for y in prog.slots.values()}
            g1 = K.infer_labels(prog.body, g0)
            for y in prog.slots.values():
                g1.setdefault(y, C.LOW)
            weak = K.Program(prog.workflow, prog.slots, prog.body, g1, prog.site_lines, prog.site_caps,
                             prog.var_bounds, prog.output)
            mutant = K.Shaper(weak, profiles, toks, "ours").run()
            rows.append({"workflow": wf.name, "op": "forget_secret", "path": [x], "mutant": mutant, "prog": prog})
            payloads.append(validate.payload(weak.high_vars(), prog.body, mutant, prog.secret_inputs()))
    verdicts = validate.lean_validate_batch(payloads)
    # Mock responses draw words that drive the ported workflows' routing tests,
    # so that different secrets exercise different branches and loop counts.
    R.MockBackend.WORDS = [" yes", " no", " story", " joke", " poem", " web_search", " funny", " not funny",
                           " FINAL: 4", " CALL add 2 3", " order_search", " product_info", "?", "!",
                           "\nintent: billing", "\nintent: bug", "\nintent: question", "\nurgency: critical",
                           "\ngrade: not funny", "\nfeedback: shorter", "\nA :: b", " a", " b"]
    mock = {k: R.MockBackend(p, M.tokenizer_for(p.gguf)) for k, p in profiles.items() if os.path.exists(p.gguf)}
    mock.update({k + "-other": b for k, b in list(mock.items())})  # target of the dummy_model operator
    summary, details = {}, []
    for row, v in zip(rows, verdicts):
        # Oracle: mock generation with the real tokenizers and templates.
        rt = R.Runtime(mock, dict(T.BASE, retrieve=lambda q: q[:20], web_search=lambda q: q[-20:]), {})
        try:
            leak, changed = oracle(row["mutant"], row["prog"].body, secrets, rt, row["prog"].secret_inputs())
            err = None
        except Exception as e:  # mutants may violate runtime preconditions (e.g. unpadded high calls)
            leak, changed, err = None, None, type(e).__name__
        s = summary.setdefault(row["op"], {"mutants": 0, "rejected": 0, "oracle_leak": 0, "leak_accepted": 0,
                                           "accepted": 0})
        s["mutants"] += 1
        s["rejected"] += not v["accepted"]
        s["accepted"] += v["accepted"]
        s["oracle_leak"] += bool(leak)
        s["leak_accepted"] += bool(leak) and v["accepted"]
        details.append({"workflow": row["workflow"], "op": row["op"], "path": row["path"], "lean": {k: v[k] for k in v if k != "static_shape"},
                        "oracle_leak": leak, "oracle_changed": changed, "oracle_error": err})
    total = {k: sum(s[k] for s in summary.values()) for k in ["mutants", "rejected", "accepted", "oracle_leak", "leak_accepted"]}
    out = {"total": total, "by_operator": summary, "details": details}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({"total": total, "by_operator": summary}, indent=1))


if __name__ == "__main__":
    main()
