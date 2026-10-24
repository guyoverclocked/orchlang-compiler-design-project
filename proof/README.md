# Lean development

`ShapeCore.lean` (Lean 4.19.0, core library only) contains:

- the core workflow language, its semantics over an abstract `World`
  (tokenizers, models, padder, tools) and a per-site randomness tape;
- the static shape of a statement and the padding discipline `wt`, the
  randomness-site check `sitesOK` and the cap check `capsOK`;
- `noninterference` / `trace_noninterference` / `distribution_noninterference`:
  under `World.Conforms`, programs satisfying the discipline emit identical usage
  traces from stores that agree on public variables, for every tape;
- `erase_correct` and `clean_data`: under `World.Transparent`, a shaped program
  computes the same store as its erasure;
- `validateProgram` and `validateProgram_sound`: the executable translation
  validator and its soundness;
- `checkJson` / `main`: the JSON entry point used by `orchlang/validate.py`;
- `#guard` regression tests evaluated at every check.

Check the proofs with `lean proof/ShapeCore.lean`. Validate a batch of programs with
`lean --run proof/ShapeCore.lean batch.json`, where each item is
`{"high": [vars], "original": stmt, "padded": stmt}`.

Earlier cores (bounded cost, finite relational and dataflow certificates) are in
`legacy/v1/proof/`.
