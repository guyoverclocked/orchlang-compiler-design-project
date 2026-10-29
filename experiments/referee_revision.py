"""Predeclared, version-bound referee revision experiments (local GGUF only).

All attempts, including errors and mismatches, are retained. Existing output
directories cannot be reused. This is a bounded falsification study, not an
independent human replication, authoritative gateway, or universal model proof.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchlang import assurance as A, compiler as K, core as C, models as M, runtime as R, tools as T
from experiments.run_workflow import source_checkout_identity

KEEP = {"switch": ["response", "intention", "llm_result"], "email": ["reply", "route", "cls"],
        "crag": ["answer", "search"]}
PROMPTS = ["", "Reply with exactly OK.", "Summarize in one word: " + "café 漢字 a b c. " * 32]


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def emit(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class InstrumentedBackend(R.LlamaBackend):
    """Independent *local API* observations below Runtime._llm's usage report.

    Records tokens supplied to llama-cpp-python eval and yielded by generate.
    This is trusted client instrumentation, not a remote bill/network observer.
    An eval submission can contain multiple native batches; it is not a count
    of physical GPU/CPU operations or billable requests.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []
        self.active = None
        self.phase = "generation"
        original_eval = self.m.eval
        original_generate = self.m.generate

        def eval_tokens(tokens):
            if self.active is not None:
                self.active["eval_submissions"].append(dict(phase=self.phase, token_ids=list(tokens)))
            return original_eval(tokens)

        def generate_tokens(*args, **kwargs):
            for token in original_generate(*args, **kwargs):
                if self.active is not None:
                    self.active["yielded_token_ids"].append(token)
                yield token

        self.m.eval = eval_tokens
        self.m.generate = generate_tokens

    def isolated_prefill(self, n):
        self.phase = "isolated_prefill"
        try:
            return super().isolated_prefill(n)
        finally:
            self.phase = "generation"

    def generate(self, prompt, max_tokens, seed, forced, cap=None, pad_tokens=0):
        record = dict(request_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                      request_token_ids=self.encode(prompt), max_tokens=max_tokens, seed=seed,
                      forced=forced, cap=cap, isolated_pad_tokens=pad_tokens,
                      eval_submissions=[], yielded_token_ids=[])
        self.calls.append(record)
        self.active = record
        try:
            result = super().generate(prompt, max_tokens, seed, forced, cap, pad_tokens)
            record.update(returned_ids=result[0], visible=result[1], reported_input=result[2], status="completed")
            return result
        except Exception as error:
            record.update(status="failed", error=repr(error))
            raise
        finally:
            self.active = None


def select_inputs(name, family):
    data = jsonl(ROOT / f"experiments/data/{name}.jsonl")
    historical = (ROOT / f"publication/evidence/completion/replication/{name}/orig.jsonl" if family == "qwen1.5b"
                  else ROOT / (f"publication/evidence/completion/main/{name}/orig.jsonl" if name == "crag"
                               else f"experiments/results/runs/{name}/orig.jsonl"))
    old = {r["id"]: r for r in jsonl(historical)}
    size = lambda row: sum(len(value) for value in row["inputs"].values())
    first, last = min(data, key=size), max(data, key=size)
    key = {"switch": "intention", "email": "route", "crag": "search"}[name]
    first_branch = old.get(first["id"], {}).get("store", {}).get(key)
    other = next((row for row in data if row["id"] not in (first["id"], last["id"])
                  and old.get(row["id"], {}).get("store", {}).get(key) != first_branch), None)
    if other is None:
        other = next(row for row in data if row["id"] not in (first["id"], last["id"]))
    rows = [dict(row, selection=selection, historical_store=old.get(row["id"], {}).get("store"))
            for row, selection in ((first, "shortest"), (last, "longest"), (other, "alternate-historical-branch-or-first-unused"))]
    variant = dict(first, id=first["id"] + "-whitespace-boundary", selection="controlled-boundary-variant",
                   inputs={key: " \t\u2003" + value + "\u2003\t " for key, value in first["inputs"].items()},
                   historical_store=None)
    return [*rows, variant]


def execute(backend, program, inputs, slots, keep, tools, caps, seed, random_pad=0):
    backend.calls = []
    runtime = R.Runtime({backend.profile.key: backend}, tools, caps, random_pad=random_pad)
    start = time.perf_counter()
    try:
        result = runtime.run(program, {slots[k]: v for k, v in inputs.items()}, seed)
        return dict(status="completed", store={key: result.store.get(slots[key], "") for key in keep},
                    all_store={str(k): v for k, v in result.store.items()},
                    trace=result.observed(), truncations=result.truncations, usage=result.usage,
                    execution_events=[e.audit for e in result.trace if e.kind == "llm"],
                    local_observations=backend.calls, seconds=time.perf_counter() - start)
    except Exception as error:
        return dict(status="failed", error=repr(error), dispatched=getattr(error, "dispatched", None),
                    prefix=[e.observed() for e in runtime.trace], usage=runtime.ledger.snapshot(),
                    local_observations=backend.calls, seconds=time.perf_counter() - start)


def workflow_study(args, profiles, selections):
    path = args.output / "workflow-attempts.jsonl"
    for family in ("llama1b", "qwen1.5b"):
        for temperature in (0.0, 0.8):
            backend = InstrumentedBackend(profiles[family], n_threads=args.threads, temperature=temperature)
            for name in KEEP:
                source_path = ROOT / (f"workflows/replication/{name}_qwen.orch" if family == "qwen1.5b" else f"workflows/{name}.orch")
                source = source_path.read_bytes()
                program, binding = A.source_binding(source, profiles)
                tokenizers = {family: backend}
                candidates = {strategy: K.Shaper(program, profiles, tokenizers, strategy).run()
                              for strategy in ("ours", "naive", "uniform")}
                _, _, verdicts = A.validate_candidates(source, profiles, candidates)
                if not all(v["accepted"] for v in verdicts.values()):
                    raise ValueError("candidate failed Lean acceptance")
                tools = dict(T.BASE)
                if name == "crag":
                    tools["retrieve"] = T.Retriever([r["text"] for r in jsonl(ROOT / "experiments/data/crag_corpus.jsonl")], k=4)
                    tools["web_search"] = T.Retriever([r["text"] for r in jsonl(ROOT / "experiments/data/crag_web.jsonl")], k=3)
                caps = {tool.name: tool.max_tokens for tool in program.workflow.tools}
                for index, item in enumerate(selections[family][name]):
                    seed = (0, 17, 0, 17)[index]
                    variants = {"orig": program.body, "ours": candidates["ours"]}
                    # Same real backend and observation alphabet. Costly baselines
                    # use the shortest switch case only, under greedy decoding.
                    if name == "switch" and index == 0 and temperature == 0.0:
                        variants.update(all_branches=candidates["naive"], uniform=candidates["uniform"], random_padding=program.body)
                    for condition, core in variants.items():
                        result = execute(backend, core, item["inputs"], program.slots, KEEP[name], tools, caps, seed,
                                         random_pad=32 if condition == "random_padding" else 0)
                        row = dict(family=family, workflow=name, temperature=temperature, seed=seed,
                                   id=item["id"], selection=item["selection"], condition=condition,
                                   source_sha256=A.sha256(source_path), source_binding_sha256=binding["binding_sha256"],
                                   static_shape=C.shape(core), historical_store=item["historical_store"], **result)
                        emit(path, row)
                        print("workflow", family, name, temperature, item["id"], condition, result["status"], flush=True)
            backend.m.close()
            del backend
            gc.collect()


def transparency_study(args, profiles):
    path = args.output / "transparency-attempts.jsonl"
    for family in ("llama1b", "qwen1.5b"):
        for stop_variant, temperature in itertools.product(("declared", "extra-stop-OK"), (0.0, 0.8)):
            profile = profiles[family]
            if stop_variant != "declared":
                profile = replace(profile, stop=[*profile.stop, "OK"])
            backend = InstrumentedBackend(profile, n_threads=args.threads, temperature=temperature)
            for index, (prompt_index, cap, gap, seed) in enumerate(itertools.product(range(3), (4, 16), (0, 8), (0, 17))):
                request = profile.tmpl.render([("user", PROMPTS[prompt_index])])
                target = backend.count(request) + (0, 16, 64)[index % 3]
                attempt = dict(family=family, stop_variant=stop_variant, temperature=temperature, seed=seed,
                               prompt_class=("empty", "stop-seeking", "long-multilingual")[prompt_index],
                               request=request, request_tokens=backend.count(request), cap=cap, forced=cap + gap,
                               target=target, stop_ids=sorted(backend.stop_ids), stop_strings=profile.stop)
                backend.calls = []
                try:
                    padded, isolated, truncation = R.Padder(backend).pad(request, target)
                    natural = backend.generate(request, cap, seed, False)
                    forced = backend.generate(padded, cap + gap, seed, True, cap, isolated)
                    attempt.update(status="completed", natural_ids=natural[0], forced_ids=forced[0],
                                   natural_visible=natural[1], forced_visible=forced[1], visible_equal=natural[1] == forced[1],
                                   conformance=forced[2] == target and len(forced[0]) == cap + gap,
                                   truncations=int(truncation), local_observations=backend.calls)
                except Exception as error:
                    attempt.update(status="failed", error=repr(error), local_observations=backend.calls)
                emit(path, attempt)
                print("transparency", family, stop_variant, temperature, index, attempt["status"],
                      attempt.get("visible_equal"), flush=True)
            backend.m.close()
            del backend
            gc.collect()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    if args.output.exists():
        raise ValueError("use a new output directory, even after a failed run")
    args.output.mkdir(parents=True)
    profiles = M.load_profiles(args.models)
    selections = {family: {name: select_inputs(name, family) for name in KEEP} for family in ("llama1b", "qwen1.5b")}
    implementation = {**A.implementation_hashes(ROOT), "proof/AdmissionDomain.lean": A.sha256(ROOT / "proof/AdmissionDomain.lean"),
                      "experiments/referee_revision.py": A.sha256(Path(__file__))}
    identity = source_checkout_identity(ROOT)
    plan = dict(schema="orchlang-referee-revision-protocol-v1", version=identity["git_commit"], source_identity=identity,
                implementation=implementation, model_contracts=A.model_contracts({k: profiles[k] for k in selections}),
                python=sys.version, platform=platform.platform(), threads=args.threads, temperature=[0.0, 0.8], seeds=[0, 17],
                workflow_selections=selections, workflow_pairs=48, baseline_extra_executions=6, transparency_pairs=192,
                transparency_prompts=PROMPTS, transparency_caps=[4, 16], forced_gaps=[0, 8], input_slack=[0, 16, 64],
                stop_profiles=["declared", "declared plus single-token OK when tokenizer supports it"],
                interpretation="Historical-branch-stratified falsification, not preregistered independent research or quality estimation; no failures omitted.",
                observer="logical usage plus separate trusted local llama-cpp-python eval/generate instrumentation, not gateway/invoice authority")
    dump(args.output / "protocol.json", plan)
    workflow_study(args, profiles, selections)
    transparency_study(args, profiles)
    if implementation != {name: A.sha256(ROOT / name) for name in implementation}:
        raise ValueError("implementation changed during execution")
    dump(args.output / "execution-complete.json", dict(complete=True, implementation_unchanged=True))


if __name__ == "__main__":
    main()
