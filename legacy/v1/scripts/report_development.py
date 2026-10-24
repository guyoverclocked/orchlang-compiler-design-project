"""Derive development tables from successful immutable run records."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("offline", "generated", "tokenizers", "mutations", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    sources = {"offline": args.offline / "manifest.json", "generated": args.generated / "manifest.json",
               "tokenizers": args.tokenizers / "manifest.json", "mutations": args.mutations / "mutations.json"}
    manifests = {k: load(p) for k, p in sources.items()}
    if any(m["status"] != "completed" for m in manifests.values()):
        raise ValueError("cannot publish a successful summary from a failed/incomplete run")
    commands = load(args.offline / "commands.json")
    cpp = next(re.search(r"Passed (\d+)/(\d+) tests", c["stdout"]) for c in commands
               if "orchlang_tests" in c["argv"][0])
    py = next(re.search(r"Ran (\d+) tests", c["stderr"]) for c in commands
              if "unittest" in c["argv"])
    if cpp is None or py is None or cpp[1] != cpp[2]:
        raise ValueError("missing or unsuccessful test counts")
    costs = [r for r in load(args.offline / "results.json") if r["category"] == "historical-cost-development"]
    texts = load(args.tokenizers / "tokens.json")
    pairs = load(args.tokenizers / "concatenations.json")
    mutants = manifests["mutations"]["mutations"]
    g = manifests["generated"]
    rows = [
        ("C010", "C++ tests passed", int(cpp[1]), "tests; development suite"),
        ("C011", "Python tests passed", int(py[1]), "tests; independent reference and baseline"),
        ("C012", "Existing cost workflows", len(costs), "developer corpus; no external applications"),
        ("C012", "Mock executions checked", sum(len(c["runs"]) for c in costs), "five fixed seeds per workflow"),
        ("C013", "Generated programs checked", g["programs"], "exhaustive bounded grammar"),
        ("C013", "Unique call-count structures", g["unique_call_count_structures"], "structure count, distinct from programs"),
        ("C013", "Generated programs accepted", g["accepted"], "finite closed-request development fragment"),
        ("C013", "Accepted finite counterexamples", g["accepted_finite_counterexamples"], "exact supplied kernels; not a universal proof"),
        ("C013", "Trace-identity baseline disagreements", g["trace_identity_disagreements"], "no observed precision advantage over this floor"),
        ("C013", "Finite-equivalent programs rejected", g["finite_equivalent_rejected"], "kernel-specific equivalence, not universal safety"),
        ("C014", "Faults detected", sum(m["status"] == "detected" for m in mutants), f"of {len(mutants)} deliberately injected faults"),
        ("C015", "Token encodings exceeding byte/divisor estimate", sum(t["plain_exceeds_mock"] for t in texts), f"of {len(texts)} fixed boundary cases"),
        ("C015", "Non-additive concatenations", sum(not t["additive"] for t in pairs), f"of {len(pairs)} fixed pairs across two families"),
        ("C016", "External application workflows", 0, "not yet evaluated"),
        ("C008", "Paid API spending (USD)", "0.00", "no key or paid inference used"),
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    summary = dict(purpose="development-summary-not-final-publication-data",
                   sources={k: dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for k, p in sources.items()},
                   metrics=[dict(claim_id=c, metric=m, value=v, scope=s) for c, m, v, s in rows])
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    table = "# Development evidence (not final comparative data)\n\n"
    table += "| Claim | Metric | Value | Scope |\n|---|---|---:|---|\n"
    table += "".join(f"| {c} | {m} | {v} | {s} |\n" for c, m, v, s in rows)
    (args.output / "table.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
