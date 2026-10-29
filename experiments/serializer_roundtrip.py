"""Check the Python-to-Lean serialization boundary by exact round trip.

Python serializes core programs with ``core.stmt_json``; Lean parses them with
``decodeStmt`` and re-encodes them with ``encodeStmt``. Equality of the JSON
values means the program Lean checks is the program Python produced. Programs
come from the differential generator (with Unicode, escape and separator
literals) and, when model files are configured, from every application source
and its shaped candidates.
"""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orchlang import compiler as K, core as C  # noqa: E402
from experiments.differential import Gen, FakeProg, PROFILE, CharTok  # noqa: E402

SPECIAL = ["é", "漢字", "🚀", "\\", "\x1f", "\"quoted\"", "\n", " ", "<|eot_id|>"]


def literal_variants(stmt, rng):
    """Replace some literals by adversarial strings, preserving structure."""
    def expr(e):
        if isinstance(e, C.ELit):
            return C.ELit(e.value + rng.choice(SPECIAL)) if rng.random() < 0.5 else e
        if isinstance(e, C.EApp):
            return C.EApp(expr(e.a), expr(e.b))
        if isinstance(e, C.EEscape):
            return C.EEscape(expr(e.value))
        if isinstance(e, C.ETrim):
            return C.ETrim(expr(e.value))
        return e
    def go(s):
        if isinstance(s, C.Seq):
            return C.Seq(go(s.a), go(s.b))
        if isinstance(s, C.Call):
            return C.Call(s.site, s.x, s.model, expr(s.req), s.pad, s.max_tokens)
        if isinstance(s, C.Tool):
            return C.Tool(s.x, s.name, C.EEscape(expr(s.arg)) if rng.random() < 0.3 else expr(s.arg))
        if isinstance(s, C.Ite):
            return C.Ite(C.Guard(s.g.kind, s.g.x, s.g.value + rng.choice(SPECIAL)), go(s.a), go(s.b))
        if isinstance(s, C.Loop):
            return C.Loop(s.n, s.g, go(s.body), s.padded)
        return s
    return go(stmt)


def lean_roundtrip(items, lean, ascii_escaped=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "programs.json"
        path.write_text(json.dumps(items, ensure_ascii=ascii_escaped), encoding="utf-8")
        result = subprocess.run([lean, "--run", str(ROOT / "proof/ShapeCore.lean"), "roundtrip", str(path)],
                                capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout.rstrip("\r\n").rsplit("\n", 1)[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--programs", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--output", required=True)
    ap.add_argument("--ascii-escaped", action="store_true",
                    help="reproduce the pre-fix boundary (UTF-16 surrogate escapes)")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    items, origins = [], []
    for k in range(args.programs):
        nvars = rng.randint(2, 5)
        body = literal_variants(Gen(rng, nvars).stmt(rng.randint(1, 4)), rng)
        gamma = K.infer_labels(body, {x: (C.HIGH if rng.random() < 0.5 else C.LOW) for x in range(nvars)})
        fp = FakeProg(body, gamma, {x: 6 for x in range(nvars)})
        for name, program in [("original", body)] + [
                (s, K.Shaper(fp, {"m": PROFILE}, {"m": CharTok()}, s).run()) for s in ("ours", "padall")]:
            items.append(C.stmt_json(program)); origins.append(f"generated-{k}-{name}")
    workflows = 0
    if os.environ.get("ORCHLANG_MODELS"):
        from orchlang import assurance as A, admission as B, models as M
        profiles = M.load_profiles()
        sources = sorted((ROOT / "workflows").glob("*.orch")) + sorted((ROOT / "workflows/replication").glob("*.orch"))
        for source in sources:
            try:
                program, _ = A.source_binding(source.read_bytes(), profiles)
            except Exception:
                continue
            tokenizers = {c.model: M.tokenizer_for(profiles[c.model].gguf) for c in C.calls(program.body)}
            candidates = {"original": program.body, "ours": K.Shaper(program, profiles, tokenizers, "ours").run()}
            try:
                contract = B.byte_contract(program, response_bytes_per_token=128, context=21504)
                candidates["certified"] = B.certified_shaper(program, profiles, tokenizers, contract)
            except Exception:
                pass
            for name, body in candidates.items():
                items.append(C.stmt_json(body)); origins.append(f"{source.name}-{name}")
            workflows += 1
    returned = lean_roundtrip(items, os.environ.get("LEAN", "lean"), args.ascii_escaped)
    mismatches = [origins[i] for i, (a, b) in enumerate(zip(items, returned)) if a != b]
    result = dict(schema="orchlang-serializer-roundtrip-v1", programs=len(items),
                  generated_programs=args.programs, workflow_sources=workflows,
                  returned=len(returned), exact_roundtrips=len(items) - len(mismatches),
                  mismatches=mismatches[:20], all_equal=len(returned) == len(items) and not mismatches,
                  ascii_escaped=args.ascii_escaped,
                  scope="Python stmt_json -> Lean decodeStmt -> Lean encodeStmt -> JSON equality")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "mismatches"}))
    return 0 if result["all_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
