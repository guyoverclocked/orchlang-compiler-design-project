"""Reconstruct inspectable validation artifacts for the frozen revision sources.

This is explicitly an after-execution reconstruction of deterministic compiler
output. It does not relabel the execution or claim a verified lowering step.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchlang import assurance as A, compiler as K, core as C, models as M


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path)
    ap.add_argument("--models", required=True)
    args = ap.parse_args()
    plan = json.loads((args.directory / "protocol.json").read_text(encoding="utf-8"))
    # These files, rather than later packaging scripts, determine compilation.
    for name, expected in plan["implementation"].items():
        if name.startswith("orchlang/") or name.startswith("proof/"):
            if A.sha256(ROOT / name) != expected:
                raise ValueError("compiler/proof changed: " + name)
    profiles = M.load_profiles(args.models)
    target = args.directory / "reconstructed-validation"
    target.mkdir(exist_ok=False)
    for family, workflows in plan["workflow_selections"].items():
        for name in workflows:
            path = ROOT / (f"workflows/replication/{name}_qwen.orch" if family == "qwen1.5b" else f"workflows/{name}.orch")
            source = path.read_bytes()
            program, binding = A.source_binding(source, profiles)
            tokenizers = {family: M.tokenizer_for(profiles[family].gguf)}
            candidates = {strategy: K.Shaper(program, profiles, tokenizers, strategy).run() for strategy in ("ours", "naive", "uniform")}
            _, _, verdicts = A.validate_candidates(source, profiles, candidates)
            if not all(v["accepted"] for v in verdicts.values()):
                raise ValueError("reconstructed candidate rejected")
            artifact = dict(schema="orchlang-validation-artifact-v1", source_binding=binding,
                            model_contracts=A.model_contracts({family: profiles[family]}),
                            candidates={strategy: C.stmt_json(core) for strategy, core in candidates.items()})
            receipt = A.check_artifact(source, profiles, artifact)
            receipt["reconstructed_after_execution"] = True
            receipt["protocol_version"] = plan["version"]
            for suffix, value in (("artifact", artifact), ("receipt", receipt)):
                with (target / f"{family}-{name}-{suffix}.json").open("x", encoding="utf-8") as stream:
                    json.dump(value, stream, indent=2)
                    stream.write("\n")
            print(family, name, "source-bound accepted", flush=True)
