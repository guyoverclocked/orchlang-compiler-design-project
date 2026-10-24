"""Static facts for the paper: census statistics from census.csv and code
statistics of the artifact. Writes paper/generated/static.tex."""
from __future__ import annotations

import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def census():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "experiments/census/census.csv"), encoding="utf-8")))
    apps = [r for r in rows if r["notes"].startswith("tier=A;")]
    dep = lambda r: any(r[k].startswith("yes") for k in ("branching", "loop", "fanout"))
    is_pf = lambda r: r["source"] == "promptflow"
    out = {"censusRows": len(rows), "censusApps": len(apps)}

    def block(prefix, rs):
        d = [r for r in rs if dep(r)]
        out[prefix] = len(rs)
        out[prefix + "Dep"] = len(d)
        out[prefix + "Pct"] = round(100 * len(d) / len(rs))
        out[prefix + "Branch"] = sum(r["branching"].startswith("yes") for r in rs)
        out[prefix + "Loop"] = sum(r["loop"].startswith("yes") for r in rs)
        out[prefix + "Fan"] = sum(r["fanout"].startswith("yes") for r in rs)
        return d

    d = block("censusAll", apps)
    out["censusDependent"] = out["censusAllDep"]
    out["censusPct"] = out["censusAllPct"]
    out["censusBranching"] = out["censusAllBranch"]
    out["censusLoopsDep"] = out["censusAllLoop"]
    out["censusFanout"] = out["censusAllFan"]
    out["censusUserDriven"] = sum(r["decision_on_user_content"] == "yes" for r in d)
    loops = [r for r in apps if r["loop"].startswith("yes")]
    out["censusLoops"] = len(loops)
    # lg-storm's bound (max_num_turns = 5, libs/cli/examples/graphs/storm.py:356) is recorded in census.md
    # rather than in its notes field.
    bounded = lambda r: re.search(r"(?<!un)bounded \(", r["notes"]) or r["id"] == "lg-storm"
    out["censusUnbounded"] = sum(1 for r in loops if not bounded(r))
    block("censusLangGraph", [r for r in apps if not is_pf(r)])
    block("censusPF", [r for r in apps if is_pf(r)])
    return out


def code():
    def lines(paths):
        n = 0
        for p in paths:
            for l in open(p, encoding="utf-8"):
                s = l.strip()
                if s and not s.startswith("#"):
                    n += 1
        return n
    py = [os.path.join(ROOT, "orchlang", f) for f in os.listdir(os.path.join(ROOT, "orchlang")) if f.endswith(".py")]
    lean = os.path.join(ROOT, "proof", "ShapeCore.lean")
    text = open(lean, encoding="utf-8").read()
    return {"pyLines": lines(py), "leanLines": len(text.splitlines()),
            "leanTheorems": len(re.findall(r"^theorem ", text, re.M)),
            "leanGuards": len(re.findall(r"^#guard ", text, re.M)),
            "orchLines": sum(1 for f in os.listdir(os.path.join(ROOT, "workflows")) if f.endswith(".orch")
                             for l in open(os.path.join(ROOT, "workflows", f), encoding="utf-8")
                             if l.strip() and not l.strip().startswith("//"))}


def main():
    vals = {**census(), **code()}
    # census figures stated in the text that are coded qualitatively in census.md
    vals.update(censusConstantCalls=5, censusMultiModel=7)
    out = os.path.join(ROOT, "paper", "generated", "static.tex")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        for k, v in sorted(vals.items()):
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    print(vals)


if __name__ == "__main__":
    main()
