"""Construct explicitly lossy cost projections, not executions of upstream apps."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PF = "microsoft/promptflow"
LG = "langchain-ai/docs"


def workflow(name, declarations, statements, output="x"):
    return f"workflow {name} budget 100000 {{\n{declarations}\n{statements}\n  output {output};\n}}\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    upstream = json.loads((args.sources / "manifest.json").read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    census, included = [], []
    def record(case_id, repo, path, source=None, reason="", max_calls=0, changes="", added_caps=False):
        provenance = next(r for r in upstream if r["repo"] == repo and r["path"] == path)
        local = args.sources / repo.replace("/", "--") / path
        if hashlib.sha256(local.read_bytes()).hexdigest() != provenance["sha256"]:
            raise ValueError("upstream source mismatch")
        row = dict(id=case_id, source=provenance, status="adapted-cost-projection" if source else "excluded",
                   reason=reason, changes=changes, expected_max_calls=max_calls,
                   original_function_preserved=False, original_provider_behavior_validated=False,
                   original_workflow_executed=False, introduced_output_caps=added_caps,
                   policy="public data; web page untrusted where applicable; no secret bindings",
                   manual_adaptation_minutes=None)
        if source:
            name = case_id + ".orch"
            (args.output / name).write_text(source, encoding="utf-8", newline="\n")
            row.update(file=name, sha256=hashlib.sha256(source.encode()).hexdigest(),
                       nonempty_source_lines=sum(bool(l.strip()) for l in source.splitlines()),
                       input_bound_annotations=source.count("input "),
                       model_cap_annotations=source.count("model "))
            included.append(row)
        census.append(row)

    base = "examples/flows/standard/"
    common_loss = "Replaced provider with mock and prompts with authored summaries; imposed input bounds; omitted SDK retries, deployment/serialization and nonbilling helpers. Original end-to-end behavior is not certified."
    for name in ("basic", "basic-with-builtin-llm", "basic-with-connection"):
        source = workflow("PF" + name.replace("-", "_") ,
            '  input x: text max_tokens 256;\n  model m = mock("pf-basic") max_tokens 120;\n  prompt p(t: text) -> text = "Complete: {t}";',
            "  let answer: text = call p(x) using m;", "answer")
        record("pf-" + name, PF, base + name + "/flow.dag.yaml", source, max_calls=1,
               changes=common_loss + " The three basic variants share the same one-call graph and are not three unique structures.")
    source = workflow("PFIntent",
        '  input history: text max_tokens 256;\n  input info: text max_tokens 128;\n  model m = mock("pf-intent") max_tokens 256;\n  prompt p(h: text, i: text) -> text = "Extract intent: {h} Context: {i}";',
        "  let intent: text = call p(history, info) using m;", "intent")
    record("pf-customer-intent", PF, base + "customer-intent-extraction/flow.dag.yaml", source,
           max_calls=1, changes=common_loss + " Added output cap 256 absent from original model construction.", added_caps=True)
    source = workflow("PFNER",
        '  input document: text max_tokens 512;\n  input entity_type: text max_tokens 16;\n  model m = mock("pf-ner") max_tokens 64;\n  prompt p(t: text, e: text) -> text = "Extract {e} from {t}";',
        "  let entities: text = call p(document, entity_type) using m;", "entities")
    record("pf-ner", PF, base + "named-entity-recognition/flow.dag.yaml", source, max_calls=1, changes=common_loss)
    source = workflow("PFSwitch",
        '  input x: text max_tokens 256;\n  model m = mock("pf-switch") max_tokens 128;\n  prompt p(t: text) -> text = "Classify request: {t}";',
        "  let category: text = call p(x) using m;", "category")
    record("pf-switch", PF, base + "conditional-flow-for-switch/flow.dag.yaml", source, max_calls=1,
           changes=common_loss + " Source downstream order/product tools return fixed strings, not additional LLM calls.")
    source = workflow("PFIfElse", "  input x: text max_tokens 256;\n  input allowed: boolean max_tokens 1;",
                      "  if allowed { } else { }")
    record("pf-if-else-stubs", PF, base + "conditional-flow-for-if-else/flow.dag.yaml", source, max_calls=0,
           changes="Retained zero model-call cost. The source llm_result.py is a fixed-string stub. Omitted content-safety/helper computation and return-value construction; no LLM was added based on a tool name.")
    source = workflow("PFWeb",
        '  input page: text untrusted max_tokens 2000;\n  input url: text max_tokens 64;\n  model m = mock("pf-web-default") max_tokens 128;\n  prompt summarize(t: text) -> text = "Summarize page: {t}";\n  prompt classify(t: text, u: text) -> text = "Classify {u} using {t}";',
        "  let summary: text = call summarize(page) using m;\n  let category: text = call classify(summary, url) using m;", "category")
    record("pf-web-classification", PF, base + "web-classification/flow.dag.yaml", source, max_calls=2,
           changes=common_loss + " Default variant 0 only; fetched text supplied as bounded untrusted input, no HTTP executed; examples/JSON postprocessing omitted.")
    exclusions = {
        "autonomous-agent": "Dynamic agent/tool loop; no fixed supported call graph.",
        "describe-image": "Multimodal request/usage outside text-only source contract.",
        "flow-with-additional-includes": "Additional include environment is not represented by the supported standalone fragment.",
        "flow-with-symlinks": "Symlink/external tool environment not represented by the supported standalone fragment.",
        "gen-docstring": "Input-dependent division/fan-out, async processing and nested retry behavior.",
        "maths-to-code": "Executes generated arbitrary code; excluding it would remove a central task behavior.",
        "question-simulation": "Output cap is None and n is input-dependent; chat-history/conditional structured semantics unsupported without further changes."}
    for name, reason in exclusions.items():
        record("pf-" + name, PF, base + name + "/flow.dag.yaml", reason=reason)
    lgpath = "src/oss/langgraph/workflows-agents.mdx"
    declarations = '  input x: text max_tokens 256;\n  model m = mock("lg-bounded") max_tokens 64;'
    source = workflow("LGChain", declarations + '\n  input improve: boolean max_tokens 1;\n  prompt first(t: text) -> text = "Write a joke about {t}";\n  prompt improve_joke(t: text) -> text = "Improve this joke: {t}";\n  prompt polish(t: text) -> text = "Polish this joke: {t}";',
        '  let joke: text = call first(x) using m;\n  if improve {\n    let better: text = call improve_joke(joke) using m;\n    let final: text = call polish(better) using m;\n  }', "joke")
    record("lg-prompt-chaining", LG, lgpath, source, max_calls=3, added_caps=True,
           changes=common_loss + " Prompt-chaining section: added cap 64; response punctuation predicate abstracted to public improve flag; returns initial result rather than a branch-joined result. Only call/dependency cost shape is projected.")
    source = workflow("LGParallel", declarations + '\n  prompt joke(t: text) -> text = "Write a joke about {t}";\n  prompt story(t: text) -> text = "Write a story about {t}";\n  prompt poem(t: text) -> text = "Write a poem about {t}";',
        "  let a: text = call joke(x) using m;\n  let b: text = call story(x) using m;\n  let c: text = call poem(x) using m;", "a")
    record("lg-parallelization", LG, lgpath, source, max_calls=3, added_caps=True,
           changes=common_loss + " Parallelization section: serialized three independent calls; added cap 64; concatenating aggregator omitted. Aggregate call cost only, not timing/order equivalence.")
    source = workflow("LGRouting", declarations + '\n  input story_route: boolean max_tokens 1;\n  input joke_route: boolean max_tokens 1;\n  prompt router(t: text) -> text = "Route to story, joke or poem: {t}";\n  prompt respond(t: text) -> text = "{t}";',
        '  let decision: text = call router(x) using m;\n  if story_route { let a: text = call respond(x) using m; }\n  else { if joke_route { let b: text = call respond(x) using m; }\n         else { let c: text = call respond(x) using m; } }')
    record("lg-routing", LG, lgpath, source, max_calls=2, added_caps=True,
           changes=common_loss + " Routing section: added cap 64 and public branch flags; structured router decision/branch correlation and selected output removed. This is a cost overapproximation, not a functional translation.")
    for name, reason in {
        "orchestrator-worker": "Dynamic model-selected section count and worker fan-out; concurrency.",
        "evaluator-optimizer": "Unbounded response-dependent optimization loop; imposing a cap changes original behavior.",
        "agents": "Dynamic tool selection and cyclic agent execution outside the bounded fragment."}.items():
        record("lg-" + name, LG, lgpath, reason=reason)
    expected = {r["path"] for r in upstream if r["repo"] == PF and r["path"].endswith("flow.dag.yaml")}
    actual = {r["source"]["path"] for r in census if r["source"]["repo"] == PF}
    if actual != expected or len(census) != 21 or len(included) != 11:
        raise ValueError("census must account for every selected source")
    manifest = dict(schema_version="1", status="frozen-before-outcomes", source_records=upstream,
                    source_roots=2, census=census, cases=included, denominator=21,
                    original_workflow_executions=0, faithful_end_to_end_translations=0,
                    description="11 manually authored bounded cost projections, 10 exclusions; not original workflow task or provider results")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(census=len(census), projections=len(included), exclusions=len(census)-len(included))))


if __name__ == "__main__":
    main()
