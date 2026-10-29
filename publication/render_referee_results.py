"""Generate manuscript tables directly from the reconciled revision summary."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("summary", type=Path)
    args = ap.parse_args()
    result = json.loads(args.summary.read_text(encoding="utf-8"))
    complete = result["completeness"]
    if not complete["execution_complete"] or complete["integrity_errors"] or result["local_observer"]["errors"]:
        raise ValueError("cannot render incomplete or unreconciled revision evidence")
    workflow = result["workflow"]
    matrix = result["transparency_matrix"]
    historical = workflow["historical_greedy_comparisons"]
    values = dict(revisionPairs=workflow["planned_pairs"], revisionCompleted=workflow["completed_pairs"],
                  revisionSavedEqual=workflow["saved_store_equal"], revisionFullEqual=workflow["all_store_equal"],
                  revisionShapes=workflow["shaped_trace_matches"], revisionTransparencyPairs=sum(r["attempted"] for r in matrix),
                  revisionTransparencyEqual=sum(r["equal"] for r in matrix),
                  revisionTransparencyConform=sum(r["conformant"] for r in matrix),
                  revisionLocalCalls=result["local_observer"]["calls_checked"],
                  revisionStops=result["local_observer"]["natural_stop_count_differences"],
                  revisionHistoricalCompared=len(historical), revisionHistoricalDiverged=sum(not r["equal"] for r in historical))
    generated = ROOT / "paper/generated"
    (generated / "unified-referee-results.tex").write_text("% Generated from the retained JSON summary; do not hand-edit.\n" +
        "\n".join("\\newcommand{\\" + key + "}{" + str(value) + "}" for key, value in values.items()) + "\n", encoding="utf-8")
    lines = []
    for row in matrix:
        family = "Llama" if row["family"] == "llama1b" else "Qwen"
        stop = "declared" if row["stop_variant"] == "declared" else "+ OK"
        lines.append(f"{family} & {stop} & {row['temperature']:.1f} & {row['attempted']} & {row['completed']} & {row['equal']} & {row['conformant']} & {row['stop_observed']} " + r"\\")
    (generated / "unified-referee-transparency-table.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    labels = {"orig": "Unshaped", "ours": "Aligned", "all_branches": "All branches", "uniform": "Uniform cells",
              "random_padding": "Random padding", "normalize-permitted-report-projection-only": "Normalize report*"}
    lines = []
    for row in result["baselines"]:
        family = "Llama" if row["family"] == "llama1b" else "Qwen"
        cost = row["weighted_logical_usage"] if row["weighted_logical_usage"] is not None else "--"
        equal = "yes" if row["saved_store_equal"] else "no"
        lines.append(f"{family} & {labels[row['condition']]} & {row['model_calls']} & {row['events']} & {cost} & {equal} " + r"\\")
    (generated / "unified-referee-baseline-table.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(values, indent=2))
