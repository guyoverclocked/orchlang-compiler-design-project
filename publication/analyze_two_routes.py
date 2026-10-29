"""JSON-only reconciliation of actual two-route cover-generation baselines."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from analyze_referee_revision import local_checks, read_rows, usage

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads((args.directory / "protocol.json").read_text())
    raw = read_rows(args.directory / "attempts.jsonl")
    expected = {(family, secret, condition) for family in plan["sources"] for secret in ("short", "long") for condition in plan["conditions"]}
    actual = [(r["family"], r["secret"], r["condition"]) for r in raw]
    if len(actual) != len(expected) or set(actual) != expected or not (args.directory / "execution-complete.json").is_file():
        raise ValueError("incomplete, duplicate or foreign attempts")
    originals = {(r["family"], r["secret"]): r for r in raw if r["condition"] == "orig"}
    groups, errors = defaultdict(list), []
    for row in raw:
        groups[row["family"], row["condition"]].append(row)
        for local in row["local_observations"]:
            if local_checks(local):
                errors.append(dict(family=row["family"], secret=row["secret"], condition=row["condition"], errors=local_checks(local)))
        if row["status"] == "completed" and row["static_shape"] is not None and row["trace"] != row["static_shape"]:
            errors.append(dict(family=row["family"], condition=row["condition"], errors=["shape-mismatch"]))
    results = []
    for (family, condition), rows in sorted(groups.items()):
        complete = [r for r in rows if r["status"] == "completed"]
        results.append(dict(family=family, condition=condition, attempted=len(rows), completed=len(complete),
                            distinct_traces=len({json.dumps(r["trace"]) for r in complete}),
                            mean_usage=sum(usage(r) for r in complete) / len(complete) if complete else None,
                            mean_calls=sum(len(r["local_observations"]) for r in complete) / len(complete) if complete else None,
                            saved_equal=sum(r["store"] == originals[family, r["secret"]].get("store") for r in complete)))
    for family in plan["sources"]:
        orig = next(r for r in results if r["family"] == family and r["condition"] == "orig")
        results.append(dict(orig, condition="normalize-report-projection-only", distinct_traces=1,
                            limitation="Free report rewriting, not faithful usage; no extra execution."))
    summary = dict(schema="orchlang-two-route-summary-v1", executions=len(raw), results=results, audit_errors=errors,
                   local_calls=sum(len(r["local_observations"]) for r in raw),
                   failed_attempts=[{k: r.get(k) for k in ("family", "secret", "condition", "error")} for r in raw if r["status"] != "completed"],
                   scope="Authored microbenchmark; two secret values per family. No population/random-padding distribution claim.")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    if errors:
        raise ValueError(errors)
    names = {"orig": "Unshaped", "aligned": "Aligned", "all_branches": "All branches", "uniform": "Uniform cells",
             "random_padding": "Random padding", "normalize-report-projection-only": "Normalize report*"}
    order = ["orig", "aligned", "all_branches", "uniform", "random_padding", "normalize-report-projection-only"]
    lines = []
    for family in plan["sources"]:
        for condition in order:
            row = next(r for r in results if r["family"] == family and r["condition"] == condition)
            model = "Llama" if family == "llama1b" else "Qwen"
            cost = f"{row['mean_usage']:.0f}" if row["mean_usage"] is not None else "--"
            calls = f"{row['mean_calls']:.0f}" if row["mean_calls"] is not None else "--"
            lines.append(f"{model} & {names[condition]} & {calls} & {row['distinct_traces']} & {cost} & {row['saved_equal']}/2 " + r"\\")
    (ROOT / "paper/generated/unified-referee-route-table.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
