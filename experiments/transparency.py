"""Empirical check of World.Transparent and World.Conforms.

For requests drawn from the evaluation datasets, natural generation on the
original request, capped at `cap` tokens, is compared with the shaped call:
the request padded to T tokens (isolated padding) and decoding forced to
N > cap tokens, whose visible part is cut at the first stop token and at
`cap`. Both use the same randomness cell (seed), under greedy decoding and
under sampling. Equality is exactly the Transparency hypothesis. Also records
that every padded call reported exactly T input and N output tokens
(Conformance). With --mode inband, the natural generation is run on the
in-band padded request instead, which tests only the forced-decoding half.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchlang import models as M, runtime as R  # noqa: E402

PROMPTS = {
    "routing": ("Route the input to story, joke, or poem based on the user's request.", "user_input"),
    "chaining": (None, "topic"),
    "switch": ("Classify the user's shopping intention.", "query"),
    "email": (None, "email_content"),
    "calculator": ("You are a helpful assistant tasked with performing arithmetic on a set of inputs.", "question"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.environ.get("ORCHLANG_MODELS", "models.json"))
    ap.add_argument("--model", default="llama1b")
    ap.add_argument("--per", type=int, default=12)
    ap.add_argument("--output", required=True)
    ap.add_argument("--mode", default="isolated", choices=["isolated", "inband"])
    args = ap.parse_args()
    from dataclasses import replace
    prof = replace(M.load_profiles(args.models)[args.model], pad_mode=args.mode)
    rng = random.Random(3)
    out = {"model": args.model, "mode": args.mode, "cases": []}
    for temp in (0.0, 0.8):
        b = R.LlamaBackend(prof, n_ctx=2048, temperature=temp)
        pad = R.Padder(b)
        for name, (system, key) in PROMPTS.items():
            rows = [json.loads(l) for l in open(f"experiments/data/{name}.jsonl", encoding="utf-8")]
            for r in rng.sample(rows, args.per):
                msgs = ([("system", system)] if system else []) + [("user", r["inputs"][key])]
                req = prof.tmpl.render(msgs)
                cap = rng.choice([16, 48, 96])
                n = cap + rng.choice([1, 32, 96])
                target = b.count(req) + rng.choice([10, 100, 300])
                padded, iso, trunc = pad.pad(req, target)
                seed = rng.randrange(1 << 30)
                natural_prompt = req if args.mode == "isolated" else padded
                ids_n, vis_n, pt_n = b.generate(natural_prompt, cap, seed, False)
                ids_f, vis_f, pt_f = b.generate(padded, n, seed, True, cap=cap, pad_tokens=iso)
                out["cases"].append({"workflow": name, "temperature": temp, "cap": cap, "forced": n,
                                     "target": target, "prompt_tokens": pt_f, "generated": len(ids_f),
                                     "natural_tokens": len(ids_n), "visible_equal": vis_n == vis_f,
                                     "truncated": trunc})
        del b
    cs = out["cases"]
    out["summary"] = {
        str(t): {"cases": sum(1 for c in cs if c["temperature"] == t),
                 "visible_equal": sum(c["visible_equal"] for c in cs if c["temperature"] == t),
                 "exact_input": sum(c["prompt_tokens"] == c["target"] for c in cs if c["temperature"] == t),
                 "exact_output": sum(c["generated"] == c["forced"] for c in cs if c["temperature"] == t)}
        for t in (0.0, 0.8)}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
