"""Uniform-release validation and static diagnostics for the final revision.

Two length-extreme inputs per workflow are a targeted release check, never a
replacement for the historical full-corpus accuracy/attack study. All requests,
token IDs, local eval submissions and source identities are retained.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchlang import assurance as A, compiler as K, core as C, models as M, runtime as R
from experiments import run_workflow as runner
from experiments.referee_revision import InstrumentedBackend

KEEP = {"switch": "response,intention,llm_result", "routing": "answer,decision",
        "chaining": "final,gate,joke", "evaluator": "joke,stop", "email": "reply,route,cls",
        "orchestrator": "report,plan", "calculator": "out,done", "crag": "answer,search",
        "adaptive": "gen,src,have,done"}
PLAN = [(name, False) for name in KEEP] + [(name, True) for name in ("switch", "email", "crag")]


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def diagnostics(output, models):
    profiles = M.load_profiles(models)
    weights = [0.25, 1, 2, 4, 8, 16]
    sensitivity = []
    for name, replication in PLAN:
        source = ROOT / (f"workflows/replication/{name}_qwen.orch" if replication else f"workflows/{name}.orch")
        program, binding = A.source_binding(source.read_bytes(), profiles)
        tokenizers = {c.model: M.tokenizer_for(profiles[c.model].gguf) for c in C.calls(program.body)}
        naive = K.Shaper(program, profiles, tokenizers, "naive").run()
        variants = {str(weight): K.Shaper(program, profiles, tokenizers, "ours", K.Costs(w_out=weight)).run()
                    for weight in weights}
        _, _, verdicts = A.validate_candidates(source.read_bytes(), profiles, variants)
        for weight in weights:
            candidate = variants[str(weight)]
            assert verdicts[str(weight)]["accepted"]
            shape = C.shape(candidate)
            assert shape is not None
            cost = lambda sh: sum(e[2] + weight * e[3] for e in sh if e[0] == "llm")
            sensitivity.append(dict(workflow=name, replication=replication, output_weight=weight,
                                    accepted=True, shape=shape, cost=cost(shape),
                                    all_branches_cost=cost(C.shape(naive)),
                                    source_binding=binding["binding_sha256"]))
    grades = Counter()
    parsable = 0
    capped = 0
    for row in rows(ROOT / "publication/evidence/completion/replication/crag/orig.jsonl"):
        for event in row["execution_events"][:4]:
            text = event["visible_response"].strip()
            if text.startswith("```json") and text.endswith("```"):
                text = text[7:-3].strip()
            try:
                grade = json.loads(text).get("score")
                parsable += 1
            except (json.JSONDecodeError, AttributeError):
                grade = "unparsed"
            grades[str(grade)] += 1
            capped += len(event["generated_token_ids"]) == event["generation_cap"]
    dump(output / "diagnostics.json", dict(schema="orchlang-final-diagnostics-v1",
         implementation=A.implementation_hashes(ROOT), weights=weights, sensitivity=sensitivity,
         qwen_crag=dict(graded_documents=sum(grades.values()), parsed_json=parsable,
                        scores=dict(grades), reached_cap=capped,
                        route_counts=dict(Counter(row["store"]["search"] for row in rows(
                            ROOT / "publication/evidence/completion/replication/crag/orig.jsonl")))),
         interpretation="Recorded score vocabulary and cap diagnostic; no causal ablation or retuned primary data."))


def execute(output, models):
    cache = {}
    def backend(profile, **kwargs):
        key = profile.key
        if key not in cache:
            cache[key] = InstrumentedBackend(profile, **kwargs)
        return cache[key]
    R.LlamaBackend = backend
    summary = []
    for name, replication in PLAN:
        group = "qwen" if replication else "main"
        directory = output / group / name
        directory.mkdir(parents=True, exist_ok=False)
        data = rows(ROOT / f"experiments/data/{name}.jsonl")
        ordered = sorted(data, key=lambda row: (sum(len(v) for v in row["inputs"].values()), row["id"]))
        selected = [ordered[0], ordered[-1]]
        selections = output / "selected-data"
        selections.mkdir(exist_ok=True)
        data_path = selections / f"{group}-{name}.jsonl"
        data_path.write_text("".join(json.dumps(row) + "\n" for row in selected), encoding="utf-8")
        workflow = f"workflows/replication/{name}_qwen.orch" if replication else f"workflows/{name}.orch"
        before = {key: len(value.calls) for key, value in cache.items()}
        sys.argv = ["run_workflow", "--workflow", workflow, "--data", str(data_path),
                    "--out", str(directory), "--models", str(models), "--keep", KEEP[name]]
        if name in ("crag", "adaptive"):
            sys.argv += ["--corpus", f"experiments/data/{name}_corpus.jsonl",
                         "--web", f"experiments/data/{name}_web.jsonl"]
        runner.main()
        calls = [call for key, value in cache.items() for call in value.calls[before.get(key, 0):]]
        dump(directory / "local-calls.json", calls)
        original, shaped = rows(directory / "orig.jsonl"), rows(directory / "ours.jsonl")
        shape = json.loads((directory / "compile.json").read_text())["strategies"]["ours"]["lean"]["static_shape"]
        passed = (len(original) == len(shaped) == 2 and
                  all(a["id"] == b["id"] and a["store"] == b["store"] for a, b in zip(original, shaped)) and
                  all([[e[0], e[1], e[2], e[3]] if e[0] == "llm" else [e[0], e[1]] for e in row["trace"]] == shape for row in shaped) and
                  all(row["usage"]["usage_complete"] and not row["truncations"] for row in original + shaped))
        summary.append(dict(workflow=name, group=group, pairs=2, passed=passed, local_calls=len(calls)))
        dump(output / "progress.json", summary)
        assert passed, (name, group)
    dump(output / "summary.json", dict(schema="orchlang-uniform-release-validation-v1",
         selection="shortest and longest input by character length; two per workflow/model variant",
         inference_commit=runner.source_checkout_identity(ROOT),
         implementation=A.implementation_hashes(ROOT), driver_sha256=A.sha256(__file__),
         pairs=sum(r["pairs"] for r in summary), workflows=summary, passed=all(r["passed"] for r in summary),
         full_corpus_rerun=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("diagnostics", "execute"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    (diagnostics if args.mode == "diagnostics" else execute)(args.output.resolve(), args.models.resolve())
