"""Generate revision tables from retained completed evidence, never invented counts."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("windows", "linux", "workflows", "replay", "repeatability", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    a = p.parse_args()
    selected = dict(
        precision=ROOT/"research/revision-2026-10-24/dataflow-precision-v2/manifest.json",
        aggregate=ROOT/"research/revision-2026-10-24/aggregate-reordering-v1/manifest.json",
        exact=ROOT/"research/readiness-2026-10-24/exact-accounting-v4/summary.json",
        windows=a.windows/"manifest.json", linux=a.linux/"manifest.json",
        workflows=a.workflows/"manifest.json", replay=a.replay/"conformance.json",
        repeatability=a.repeatability/"manifest.json")
    d = {k:read(v) for k,v in selected.items()}
    for k in ("precision", "aggregate", "exact", "windows", "linux"):
        if d[k]["status"] != "completed":
            raise ValueError("incomplete evidence: "+k)
    w,rows = read(a.workflows/"summary.json"),read(a.workflows/"results.json")
    pp = a.protocol.resolve()
    protocol = read(pp)
    corpus = read(ROOT/protocol["corpus"])
    if len(rows) != w["comparison_rows"] or len(rows) != 24:
        raise ValueError("incomplete workflow denominator")
    if d["workflows"]["protocol_sha256"] != sha(pp):
        raise ValueError("workflow protocol mismatch")
    replay,repeat = d["replay"]["summary"],d["repeatability"]["summary"]
    if d["replay"]["original_results_sha256"] != sha(a.workflows/"results.json"):
        raise ValueError("replay not bound to reported outcomes")
    commands = read(a.windows/"commands.json")
    cpp = next(re.search(r"Passed (\d+)/(\d+) tests",c["stdout"]) for c in commands
        if "orchlang_tests" in c["argv"][0] and len(c["argv"]) == 1)
    py = re.search(r"Ran (\d+) tests",next(c["stderr"] for c in commands if "unittest" in c["argv"]))
    if not cpp or cpp[1] != cpp[2] or not py:
        raise ValueError("missing test counts")
    counts,aggregate,exact = d["precision"]["counts"],d["aggregate"],d["exact"]
    metrics = dict(CppTests=int(cpp[1]),PythonTests=int(py[1]),
        ProofFiles=len(list((ROOT/"proof").glob("*.lean"))),
        PrecisionSourceCases=counts["source"]["cases"],
        PrecisionSourceAccepted=counts["source"]["accepted"],
        PrecisionSourceBaseline=counts["source"]["baseline_accepted"],
        PrecisionCoreCases=counts["core"]["cases"],
        PrecisionCoreAccepted=counts["core"]["accepted"],
        PrecisionCoreBaseline=counts["core"]["baseline_accepted"],
        PrecisionContexts=d["precision"]["execution_contexts"],
        AggregateCases=aggregate["source_cases"],AggregateAccepted=aggregate["aggregate_accepted"],
        AggregateBaseline=aggregate["ordered_baseline_accepted"],AggregateGains=aggregate["aggregate_gains"],
        AggregateContexts=aggregate["execution_contexts"],AggregatePaths=aggregate["weighted_paths"],
        TokenizerTexts=exact["text_observations"],TokenizerConcats=exact["concat_observations"],
        ExactSupported=exact["supported_static_configurations"],ExactPaths=exact["enumerated_paths"],
        ExactViolations=exact["static_bound_violations"])
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/"revision.tex").write_text("".join("\\newcommand{\\rev"+k+"}{"+str(v)+"}\n"
        for k,v in metrics.items()),encoding="utf-8",newline="\n")
    table = "\\begin{tabular}{lrrrr}\n\\hline\nGrammar/observer & Cases & Baseline & Revised & Gain \\\\\n\\hline\n"
    for label,case,old,new in [
        ("Ordered source",counts["source"]["cases"],counts["source"]["baseline_accepted"],counts["source"]["accepted"]),
        ("Ordered core",counts["core"]["cases"],counts["core"]["baseline_accepted"],counts["core"]["accepted"]),
        ("Aggregate closed",aggregate["source_cases"],aggregate["ordered_baseline_accepted"],aggregate["aggregate_accepted"])]:
        table += f"{label} & {case} & {old} & {new} & {new-old} "+r"\\"+"\n"
    table += "\\hline\n\\end{tabular}\n"
    (a.output/"precision.tex").write_text(table,encoding="utf-8",newline="\n")
    completed = sum(v["status"] == "ok" for r in rows for v in r["arms"].values())
    failed = 2*len(rows)-completed
    events = [e for r in rows for v in r["arms"].values() for e in v["trace"]]
    mismatches = sum(e.get("tokenizer_input_tokens") != e.get("server_input_tokens") for e in events)
    labels = dict(zip([c["id"] for c in corpus["cases"]],
        ["Chain graph","Chain functional","Parallel","Routing","Basic (direct)","NER (hybrid)"]))
    table = ("\\begin{table}[!ht]\n\\centering\\small\n\\begin{tabular}{lrrrr}\n\\hline\n"
        "Source variant & Pairs & Equal & Peak tokens & Bound range \\\\\n\\hline\n")
    workflow_table = []
    for c in corpus["cases"]:
        rr = [r for r in rows if r["id"] == c["id"]]
        usage = [v["usage"]["input"]+v["usage"]["output"] for r in rr for v in r["arms"].values()]
        bounds = [v["usage"]["runtime_bound"] for r in rr for v in r["arms"].values()]
        row = dict(id=c["id"],pairs=len(rr),equal=sum(r["outputs_equal"] for r in rr),
            peak_tokens=max(usage),minimum_bound=min(bounds),maximum_bound=max(bounds),translation=c["translation"])
        workflow_table.append(row)
        table += (labels[c["id"]]+f" & {len(rr)} & {row['equal']} & {max(usage)} & "+
            f"{min(bounds)}--{max(bounds)} "+r"\\"+"\n")
    table += ("\\hline\n\\end{tabular}\n"+
        "\\caption{Actual local generation: peak input-plus-generated-output usage across both arms and caps, versus guarded deployment bounds.}\n"+
        "\\label{tab:local}\n\\end{table}\n")
    paragraph = (
        f"The amended experiment compares {w['comparison_rows']} original/port pairs "
        f"({completed} completed executions; {failed} failed), with {w['actual_generation_calls']} "
        f"actual generations and no replay in either arm. Final outputs and complete request/response "
        f"multisets agree in {w['outputs_equal']} and {w['full_request_response_multisets_equal']} pairs. "
        f"There are {w['runtime_bound_violations']} recorded deployment-bound violations and "
        f"{mismatches} tokenizer/server input-count mismatches. The six source variants represent "
        f"five upstream patterns: one direct call-kernel port and five explicit host compositions. "
        r"Table~\ref{tab:local} reports observed costs and conservative bounds."+"\n\n"+
        f"Captured-response replay passes {replay['passed']}/{replay['comparisons']} comparisons "
        f"and matches {replay['exact_request_matches']} complete requests with zero new generations. "
        f"This tests port conformance under common actual outcomes. A post-hoc repeatability control "
        f"uses {repeat['actual_generation_calls']} actual generations in {repeat['pairs']} identical-request "
        f"pairs. Responses differ in {repeat['response_disagreements']} of the {repeat['pairs']} pairs. Earlier independent-generation differences "
        f"remain retained, so a matching rerun is not a seeded-determinism guarantee.\n\n")
    (a.output/"workflow-results.tex").write_text(paragraph+table,encoding="utf-8",newline="\n")
    summary = dict(metrics=metrics,workflows=w,workflow_table=workflow_table,
        completed_executions=completed,failed_executions=failed,tokenizer_server_mismatches=mismatches,
        replay=replay,repeatability=repeat,
        evidence={k:dict(path=str(v),sha256=sha(v)) for k,v in selected.items()})
    (a.output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(dict(output=str(a.output),metrics=metrics,workflows=w),indent=2))


if __name__ == "__main__":
    main()
