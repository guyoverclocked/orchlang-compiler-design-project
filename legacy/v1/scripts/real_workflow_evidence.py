"""Derive diagnoses, usage, quality, and source/glue counts from retained runs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.workflow_kernels import Kernel
KERNELS={"lg-chain-graph":["first","refine"],
         "lg-chain-functional":["first","refine"],
         "lg-parallel-graph":["joke","story","poem"],
         "lg-routing-graph":["route","respond"],
         "pf-basic":["basic"],"pf-ner":["ner"]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(row):
    a,b=row["arms"]["original"],row["arms"]["port"]
    if a["status"]!="ok" or b["status"]!="ok":
        return dict(classification="infrastructure-or-execution-failure")
    if row["outputs_equal"] and row["full_request_response_multisets_equal"]:
        return dict(classification="independent-generation-exact-match")
    aa,bb=a["trace"],b["trace"]
    if row["id"]=="lg-parallel-graph":
        # Only independent parallel calls can be matched by their full request.
        pairs=[]
        for x in aa:
            matches=[y for y in bb if y["rendered_request"]==x["rendered_request"] and
                     y["schema"]==x["schema"] and y["output_cap"]==x["output_cap"]]
            if len(matches)!=1:
                return dict(classification="translation-request-or-call-mismatch")
            pairs.append((x,matches[0]))
    else:
        pairs=list(zip(aa,bb))
    for index,(x,y) in enumerate(pairs):
        request_equal=(x["rendered_request"]==y["rendered_request"] and
                       x["schema"]==y["schema"] and x["output_cap"]==y["output_cap"])
        if not request_equal:
            return dict(classification="translation-request-or-call-mismatch", first_difference_call=index+1,
                        original_request=x["rendered_request"],port_request=y["rendered_request"])
        if x["response"]!=y["response"]:
            later=[j+index+2 for j,(left,right) in enumerate(pairs[index+1:]) if
                   left["rendered_request"]!=right["rendered_request"]]
            return dict(classification="first-equal-request-divergent-model-response",
                        first_difference_call=index+1, complete_request=x["rendered_request"],
                        original_response=x["response"],port_response=y["response"],
                        consequent_later_prompt_differences=later,
                        cause="undetermined; caching/numerical effects are hypotheses, not established")
    return dict(classification="call-count-or-aggregation-output-mismatch")


def nonempty(text):
    return sum(bool(line.strip()) for line in text.splitlines())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--protocol",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--sources",type=Path,
                   default=ROOT/"research/real-workflows-2026-10-24/upstream")
    args=p.parse_args()
    protocol=json.loads(args.protocol.read_text())
    corpus=json.loads((ROOT/protocol["corpus"]).read_text())
    rows=json.loads((args.run/"results.json").read_text())
    manifest=json.loads((args.run/"manifest.json").read_text())
    if sha(args.protocol)!=manifest["protocol_sha256"]:
        raise ValueError("source run/protocol mismatch")
    diagnoses=[]
    for row in rows:
        item={key:row[key] for key in ("id","output_cap","input_index","seed")}
        item.update(diagnose(row)); diagnoses.append(item)
    source=(ROOT/"runtime/workflow_originals.py").read_text()
    port_node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=="port")
    segments=[]
    for node in port_node.body:
        if isinstance(node,ast.If):
            text=ast.get_source_segment(source,node)
            segments.append((ast.get_source_segment(source,node.test),nonempty(text)))
    glue={}
    for key in KERNELS:
        glue[key]=next(count for test,count in segments if key in test)
    kernel_records={k["name"]:k for k in corpus["kernels"]}
    workflow_metrics=[]
    for case in corpus["cases"]:
        rr=[r for r in rows if r["id"]==case["id"]]
        events=[e for r in rr for arm in r["arms"].values() for e in arm["trace"]]
        successful=[a for r in rr for a in r["arms"].values() if a["status"]=="ok"]
        k=[kernel_records[name] for name in KERNELS[case["id"]]]
        kernel_source=[(ROOT/protocol["corpus"]).parent.joinpath(x["file"]).read_text(encoding="utf-8") for x in k]
        parsed_kernels=[Kernel(source) for source in kernel_source]
        if case["original_framework"]=="langgraph":
            original_source=(ROOT/protocol["corpus"]).parent/case["executable"]
            original_loc=nonempty(original_source.read_text(encoding="utf-8"))
            original_count_files=[case["executable"]]
        else:
            active={"pf-basic":{"flow.dag.yaml","hello.py","hello.jinja2"},
                    "pf-ner":{"flow.dag.yaml","cleansing.py","NER_LLM.jinja2"}}[case["id"]]
            records=[r for r in case["source_files"] if Path(r["path"]).name in active]
            if len(records)!=3:
                raise ValueError("unexpected active upstream source files")
            original_loc=0
            original_count_files=[]
            for record in records:
                path=args.sources/record["repo"].replace("/","--")/record["path"]
                if sha(path)!=record["sha256"]:
                    raise ValueError("active upstream source hash mismatch")
                original_loc+=nonempty(path.read_text(encoding="utf-8"))
                original_count_files.append(record["path"])
        usage=[a["usage"]["input"]+a["usage"]["output"] for a in successful]
        bounds=[a["usage"]["runtime_bound"] for a in successful]
        workflow_metrics.append(dict(id=case["id"],translation=case["translation"],
            original_nonempty_source_lines=original_loc,
            original_count_files=original_count_files,
            port_kernel_files=[x["file"] for x in k],
            port_kernel_nonempty_lines=sum(nonempty(source) for source in kernel_source),
            port_kernel_bytes=sum((ROOT/protocol["corpus"]).parent.joinpath(x["file"]).stat().st_size for x in k),
            source_input_annotations=sum(len(kernel.inputs) for kernel in parsed_kernels),
            source_model_cap_annotations=sum(len(kernel.models) for kernel in parsed_kernels),
            host_case_nonempty_lines=glue[case["id"]], comparisons=len(rr),
            independently_equal=sum(r["outputs_equal"] for r in rr),
            actual_generation_calls=len(events), complete_executions=len(successful),
            observed_token_range=[min(usage),max(usage)] if usage else None,
            guarded_bound_range=[min(bounds),max(bounds)] if bounds else None,
            length_terminated_generation_calls=sum(e.get("done_reason")=="length" for e in events),
            tokenizer_server_mismatches=sum(e.get("tokenizer_input_tokens")!=e.get("server_input_tokens") for e in events),
            scored_quality=[r["task_quality"] for r in rr if r["task_quality"].get("metric")!="unscored open-ended generation"]))
    counts={label:sum(d["classification"]==label for d in diagnoses) for label in sorted(set(d["classification"] for d in diagnoses))}
    data=dict(protocol_sha256=sha(args.protocol),results_sha256=sha(args.run/"results.json"),
        diagnoses=diagnoses,diagnosis_counts=counts,workflow_metrics=workflow_metrics,
        source_count_policy="Nonempty source lines include comments. Upstream snippets exclude visualization and invocation; shared notebook setup imports are supplied by the framework driver. PF source includes YAML/prompts/tools, excludes tests. Host case LOC are AST branch spans; shared drivers/adapters are reported separately. LOC is descriptive, not a time/effort or maintainability study.",
        shared_port_function_nonempty_lines=nonempty(ast.get_source_segment(source,port_node)),
        shared_driver_nonempty_lines=nonempty(source),
        shared_kernel_interpreter_nonempty_lines=nonempty((ROOT/"runtime/workflow_kernels.py").read_text()),
        annotation_scope="Source input/model annotations use the compiler's abstract contract. Actual Qwen token admission is a separate runtime guard on the complete constructed request; annotations do not become a tokenizer theorem.")
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/"analysis.json").write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    annotation=dict(policy=data["source_count_policy"], annotation_scope=data["annotation_scope"],
                    shared_port_function_nonempty_lines=data["shared_port_function_nonempty_lines"],
                    shared_driver_nonempty_lines=data["shared_driver_nonempty_lines"],
                    shared_kernel_interpreter_nonempty_lines=data["shared_kernel_interpreter_nonempty_lines"],
                    rows=[{key:row[key] for key in ("id","translation","original_nonempty_source_lines","original_count_files",
                        "port_kernel_files","port_kernel_nonempty_lines","port_kernel_bytes",
                        "source_input_annotations","source_model_cap_annotations","host_case_nonempty_lines")}
                        for row in workflow_metrics])
    (args.output/"annotation-counts.json").write_text(json.dumps(annotation,indent=2)+"\n",encoding="utf-8")
    labels=dict(zip(KERNELS,["Chain graph","Chain functional","Parallel graph","Routing graph","Basic","NER"]))
    md="| Source variant | Original LOC | Kernel LOC | Input / cap annotations | Host case LOC |\n|---|---:|---:|---:|---:|\n"
    tex="\\begin{tabular}{lrrrr}\n\\hline\nSource variant & Original & Kernels & Input/cap & Host case \\\\\n\\hline\n"
    for row in workflow_metrics:
        label=labels[row["id"]]
        values=(row["original_nonempty_source_lines"],row["port_kernel_nonempty_lines"],
                f"{row['source_input_annotations']}/{row['source_model_cap_annotations']}",
                row["host_case_nonempty_lines"])
        md+=f"| {label} | "+" | ".join(map(str,values))+" |\n"
        tex+=label+" & "+" & ".join(map(str,values))+r" \\"+"\n"
    tex+="\\hline\n\\end{tabular}\n"
    (args.output/"annotation-counts.md").write_text(md+"\n"+data["source_count_policy"]+"\n",encoding="utf-8")
    (args.output/"annotation-counts.tex").write_text(tex,encoding="utf-8")
    print(json.dumps(counts,indent=2))


if __name__=="__main__":
    main()
