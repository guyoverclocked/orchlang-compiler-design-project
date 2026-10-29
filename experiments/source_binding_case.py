"""End-to-end omission attack: self-declared policy vs source-bound validation."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchlang import assurance as A, compiler as K, models as M, validate

SOURCE = b'''workflow PrivateReply {
  input q: text secret max_tokens 8;
  model m = "m";
  prompt p(x) = user "Reply: {x}";
  let answer = call p(q) using m max_tokens 4;
  output answer;
}'''


def run():
    profiles = {"m": M.Profile("m", "unused", "qwen2")}
    program, binding = A.source_binding(SOURCE, profiles)
    weak = validate.lean_validate_batch([validate.payload([], program.body, program.body, [])])[0]
    repair = K.Shaper(program, profiles, {"m": M.CharTokenizer()}).run()
    _, _, verdicts = A.validate_candidates(SOURCE, profiles, {"unrepaired": program.body, "repair": repair})
    assert weak["accepted"] and not verdicts["unrepaired"]["accepted"] and verdicts["repair"]["accepted"]
    return dict(schema="orchlang-source-binding-omission-case-v1", source=SOURCE.decode(), source_binding=binding,
                candidate_declared_no_secrets=weak, source_bound=verdicts,
                interpretation="Core validation of a candidate-supplied empty secrecy policy accepts the natural call. "
                "Re-reading the actual secret declaration rejects that same unshaped call and accepts its repair.",
                unit="character-token sizing only; actual Lean checker, no model inference")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("candidate-policy: accepted; source-bound unshaped: rejected; source-bound repair: accepted")
