"""Actual cover-generation baseline comparison in an authored two-secret example.

This microbenchmark is separate from the application corpus and the 192-case
primitive matrix. Two traces are a falsification/illustration, not a statistical
security claim about random padding or a deployment population.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchlang import assurance as A, compiler as K, core as C, models as M
from experiments.referee_revision import InstrumentedBackend, dump, emit, execute
from experiments.run_workflow import source_checkout_identity

SOURCE = '''workflow TwoRoutes {
  input kind: text secret max_tokens 8;
  input q: text secret max_tokens 32;
  model m = "FAMILY";
  prompt p(x) = user "In one paragraph, explain: {x}";
  if kind == "short" {
    let answer = call p(q) using m max_tokens 4;
  } else {
    let answer = call p(q) using m max_tokens 16;
  }
  output answer;
}'''


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    profiles = M.load_profiles(args.models)
    sources = {family: SOURCE.replace("FAMILY", family) for family in ("llama1b", "qwen1.5b")}
    plan = dict(schema="orchlang-two-route-baselines-v1", source_identity=source_checkout_identity(ROOT), sources=sources,
                implementations={**A.implementation_hashes(ROOT), "experiments/referee_revision.py": A.sha256(ROOT / "experiments/referee_revision.py"),
                                 "experiments/revision_routing_baselines.py": A.sha256(Path(__file__))},
                contracts=A.model_contracts({k: profiles[k] for k in sources}), temperature=0.0, seed=17,
                inputs=[dict(kind=kind, q="the water cycle") for kind in ("short", "long")],
                conditions=["orig", "aligned", "all_branches", "uniform", "random_padding"], executions=20,
                normalization="Projection of original records only; changes the reporting contract.")
    dump(args.output / "protocol.json", plan)
    for family, source in sources.items():
        backend = InstrumentedBackend(profiles[family], temperature=0.0)
        program, binding = A.source_binding(source.encode(), profiles)
        candidates = {key: K.Shaper(program, profiles, {family: backend}, strategy).run()
                      for key, strategy in (("aligned", "ours"), ("all_branches", "naive"), ("uniform", "uniform"))}
        _, _, verdicts = A.validate_candidates(source.encode(), profiles, candidates)
        if not all(v["accepted"] for v in verdicts.values()):
            raise ValueError("candidate rejected")
        dump(args.output / (family + "-validation.json"), dict(source_binding=binding, verdicts=verdicts,
             candidates={key: C.stmt_json(body) for key, body in candidates.items()}))
        for inputs in plan["inputs"]:
            for condition, body in {"orig": program.body, **candidates, "random_padding": program.body}.items():
                result = execute(backend, body, inputs, program.slots, ["answer"], {}, {}, 17,
                                 random_pad=32 if condition == "random_padding" else 0)
                emit(args.output / "attempts.jsonl", dict(family=family, secret=inputs["kind"], condition=condition,
                     static_shape=C.shape(body), source_sha256=hashlib.sha256(source.encode()).hexdigest(), **result))
                print(family, inputs["kind"], condition, result["status"], flush=True)
        backend.m.close()
    if any(A.sha256(ROOT / name) != expected for name, expected in plan["implementations"].items()):
        raise ValueError("implementation changed during execution")
    dump(args.output / "execution-complete.json", dict(complete=True, implementation_unchanged=True))
