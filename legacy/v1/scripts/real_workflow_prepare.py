"""Prepare hashed upstream code, executable call kernels, and a frozen protocol."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.workflow_kernels import Kernel
TOKENIZER_SHA = "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qwen(template, system=None):
    prefix = "" if system is None else "<|im_start|>system\n" + system + "<|im_end|>\n"
    return prefix + "<|im_start|>user\n" + template + "<|im_end|>\n<|im_start|>assistant\n"


def kernel(name, parameters, template, cap=64):
    inputs = "".join(f"  input {p}: text max_tokens 512;\n" for p in parameters)
    params = ", ".join(p + ": text" for p in parameters)
    return (f"workflow {name} budget 100000 {{\n" + inputs +
            f'  model local = mock("deployment-override-qwen2.5-3b") max_tokens {cap};\n' +
            f"  prompt renderedPrompt({params}) -> text = {json.dumps(template, ensure_ascii=False)};\n" +
            f"  let response: text = call renderedPrompt({', '.join(parameters)}) using local;\n" +
            "  output response;\n}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path,
                   help="New corpus folder; frozen repository corpora are never overwritten")
    p.add_argument("--protocol-output", required=True, type=Path)
    args = p.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.sources / "manifest.json").read_text())
    lg = args.sources / "langchain-ai--docs/src/oss/langgraph/workflows-agents.mdx"
    doc = lg.read_text(encoding="utf-8")
    lg_record = next(r for r in manifest if r["repo"] == "langchain-ai/docs" and
                     r["path"].endswith("workflows-agents.mdx"))
    if sha(lg.read_bytes()) != lg_record["sha256"]:
        raise ValueError("LangGraph pinned source mismatch")
    cases = []
    for section, variant, case_id, max_calls in [
        ("Prompt chaining", "Graph API", "lg-chain-graph", 3),
        ("Prompt chaining", "Functional API", "lg-chain-functional", 3),
        ("Parallelization", "Graph API", "lg-parallel-graph", 3),
        ("Routing", "Graph API", "lg-routing-graph", 2),
    ]:
        content = doc.split("## " + section + "\n", 1)[1].split("\n## ", 1)[0]
        snippet = re.search(r"```python " + re.escape(variant) + r"\n(.*?)\n```", content, re.S)[1]
        fn = case_id + ".upstream.py"
        (dest / fn).write_text(snippet + "\n", encoding="utf-8", newline="\n")
        cutoff = next((marker for marker in ("# Show workflow", "# Show the workflow", "# Invoke")
                       if marker in snippet), None)
        if cutoff is None:
            raise ValueError("unknown upstream setup/invocation boundary")
        executable = snippet.split(cutoff, 1)[0]
        # Only the optional image-display import is removed; all graph/task,
        # predicates, prompts, bindings and aggregators remain byte-identical.
        executable = executable.replace("from IPython.display import Image, display\n", "")
        exfn = case_id + ".execute.py"
        (dest / exfn).write_text(executable, encoding="utf-8", newline="\n")
        cases.append(dict(id=case_id, source=lg_record, snippet=fn,
                          snippet_sha256=sha((snippet+"\n").encode()), executable=exfn,
                          executable_sha256=sha(executable.encode()), max_calls=max_calls,
                          translation="hybrid-host-composition", whole_source_faithful=False,
                          original_framework="langgraph", unique_pattern=section,
                          original_nonempty_lines=sum(bool(x.strip()) for x in executable.splitlines())))
    for flow, case_id, translation in [("basic", "pf-basic", "direct-call-kernel"),
                                       ("named-entity-recognition", "pf-ner", "hybrid-host-composition")]:
        prefix = f"examples/flows/standard/{flow}/"
        records = [r for r in manifest if r["repo"] == "microsoft/promptflow" and
                   r["path"].startswith(prefix)]
        for r in records:
            source = args.sources / "microsoft--promptflow" / r["path"]
            if sha(source.read_bytes()) != r["sha256"]:
                raise ValueError("Prompt Flow source mismatch")
        cases.append(dict(id=case_id, source=next(r for r in records if r["path"].endswith("flow.dag.yaml")),
                          source_files=records, max_calls=1, original_framework="promptflow",
                          translation=translation, whole_source_faithful=case_id == "pf-basic",
                          unique_pattern=flow,
                          original_nonempty_lines=sum(sum(bool(x.strip()) for x in
                              (args.sources/"microsoft--promptflow"/r["path"]).read_text(encoding="utf-8").splitlines())
                              for r in records if Path(r["path"]).name in
                              ({"flow.dag.yaml","hello.py","hello.jinja2"} if case_id=="pf-basic" else
                               {"flow.dag.yaml","cleansing.py","NER_LLM.jinja2"}))))
    kernels = {
        "first": kernel("First", ["topic"], qwen("Write a short joke about {topic}")),
        "improve": kernel("Improve", ["joke"], qwen("Make this joke funnier by adding wordplay: {joke}")),
        "polish": kernel("Polish", ["joke"], qwen("Add a surprising twist to this joke: {joke}")),
        "joke": kernel("Joke", ["topic"], qwen("Write a joke about {topic}")),
        "story": kernel("Story", ["topic"], qwen("Write a story about {topic}")),
        "poem": kernel("Poem", ["topic"], qwen("Write a poem about {topic}")),
        "route": kernel("Route", ["request"], qwen("{request}",
                      "Route the input to story, joke, or poem based on the user's request.")),
        "respond": kernel("Respond", ["request"], qwen("{request}")),
        "basic": kernel("Basic", ["language"],
                    "Write a simple {language} program that displays the greeting message.", 120),
        "ner": kernel("NER", ["entity_type", "document"], qwen(
            "Entity type: {entity_type}\nText content: {document}\nEntities:",
            "Your task is to find entities of certain type from the given text content.\n"
            "If there're multiple entities, please return them all with comma separated, e.g. \"entity1, entity2, entity3\".\n"
            "You should only return the entity list, nothing else.\n"
            "If there's no such entity, please return \"None\".")),
    }
    # Preserve a genuine model-response dependency within OrchLang itself.
    kernels["refine"] = (
        "workflow Refine budget 100000 {\n"
        "  input joke: text max_tokens 512;\n"
        '  model local = mock("deployment-override-qwen2.5-3b") max_tokens 64;\n'
        "  prompt improve(value: text) -> text = " + json.dumps(qwen(
            "Make this joke funnier by adding wordplay: {value}")) + ";\n"
        "  prompt polish(value: text) -> text = " + json.dumps(qwen(
            "Add a surprising twist to this joke: {value}")) + ";\n"
        "  let better: text = call improve(joke) using local;\n"
        "  let final: text = call polish(better) using local;\n"
        "  output final;\n}\n")
    kernel_records = []
    for name, source in kernels.items():
        path = dest / (name+".orch")
        path.write_text(source, encoding="utf-8", newline="\n")
        parsed=Kernel(source)
        kernel_records.append(dict(name=name, file=path.name, sha256=sha(source.encode()),
            nonempty_lines=sum(bool(x.strip()) for x in source.splitlines()),
            input_bound_annotations=len(parsed.inputs), model_cap_annotations=len(parsed.models)))
    corpus = dict(schema_version=1, cases=cases, kernels=kernel_records,
        denominator=6, unique_upstream_patterns=5, direct_translations=1, hybrid_compositions=5,
        note="Both upstream Python prompt-chaining APIs are retained separately: their punctuation gates differ.",
        unsupported_full_translation_features=["response text predicates", "structured JSON guards", "branch joins",
            "parallel scheduling", "list-valued outputs", "pure aggregation/postprocessing"],
        host_operations="Explicit in runtime/workflow_originals.py; never claimed to be OrchLang or proved.")
    (dest/"manifest.json").write_text(json.dumps(corpus, indent=2)+"\n", encoding="utf-8")
    protocol = dict(schema_version=1, status="frozen-before-full-comparison-outcomes",
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        development_disclosure="Fresh regenerated development corpus. Existing v1-v4 experiments and amendments remain retained; this is not untouched preregistration or a replacement for their frozen files.",
        corpus=str(dest/"manifest.json"), corpus_sha256=sha((dest/"manifest.json").read_bytes()),
        output_caps=[24, 64], input_cap=512, seeds=[1], repeats=1,
        inputs={"lg-chain-graph":[{"topic":"cats"},{"topic":"compiler errors"}],
                "lg-chain-functional":[{"topic":"cats"},{"topic":"compiler errors"}],
                "lg-parallel-graph":[{"topic":"cats"},{"topic":"compiler errors"}],
                "lg-routing-graph":[{"input":"Write me a joke about cats"},{"input":"Write a short poem about compilers"}],
                "pf-basic":[{"text":"Python"},{"text":"JavaScript"}],
                "pf-ner":[{"entity_type":"job title", "text":"Maxime is a data scientist at Auto Dataset, and his wife is a finance manager in the same company."},
                          {"entity_type":"phone number", "text":"The phone number (321) 654-0987 is no longer in service"}]},
        primary_endpoints=["exact final-output equality", "exact full request/response multiset equality",
                           "actual node/branch agreement", "runtime admission bound violations"],
        comparison="Two actual generations per matched invocation, original then port; no replay or memoization. Independent stateless temperature-zero calls; parallel call order ignored, dependencies retained.",
        amendments="Retain all failures; any fixture fix requires dated amendment and a fresh output directory.",
        budget="maximum admitted calls * (full request input ceiling + generated output cap); dynamic deployment guard, not production compiler or Lean static theorem",
        model=dict(name="qwen2.5:3b", manifest_sha256="357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b",
                   gguf_sha256="5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6",
                   tokenizer_repo="Qwen/Qwen2.5-3B-Instruct", tokenizer_revision="aa8e72537993ba99e69dfaafa59ed015b17504d1",
                   tokenizer_sha256=TOKENIZER_SHA, tokenizers_version="0.21.4", temperature=0, device="CPU"),
        quality="Report bounded-model task failures separately. Trace equality establishes adapter fidelity on these inputs, not task quality or all-input equivalence.",
        cost_usd="0.00")
    path=args.protocol_output.resolve()
    if path.exists():
        raise ValueError("protocol output must be a new file")
    path.write_text(json.dumps(protocol, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(protocol_sha256=sha(path.read_bytes()), workflows=len(cases), kernels=len(kernels))))


if __name__ == "__main__":
    main()
