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

## Admission-domain extension

`AdmissionDomain.lean` imports the unchanged core and proves `shape_exec_on`,
`admitted_noninterference` and `certified_domain_noninterference` using
`World.ConformsOn` instead of global conformance. Only reached model calls and
cover calls must lie in the specified request domain. A separate same-admission
premise is necessary when refusal is visible. `DomainCertificate` states the
required invariant over all advertised inputs and tapes; the runtime does not
automatically construct it. Failed and unknown-dispatch observations are explicit
constructors but their physical behavior is not proved by the ideal admission
adapter. In particular, this adapter is noncomputable specification code, not
a proposed preflight algorithm that can inspect future model results for free.

```bash
lean -o proof/ShapeCore.olean proof/ShapeCore.lean
LEAN_PATH=proof lean proof/AdmissionDomain.lean
python experiments/admission_domain.py --output out/admission-domain.json
```

PowerShell: `$env:LEAN_PATH=(Resolve-Path proof).Path` before the second command.
The finite Python example checks 15 strings and three seeds under a character
mock backend and retains a short/oversized-input refusal counterexample.

## Round-3 restricted-domain theory (current headline results)

The global premises `World.Conforms` and `World.Transparent` quantify over every
padding target, including targets smaller than the request, so no non-truncating
padder satisfies them. The current results use only restricted premises:

- `Utf8Envelope.lean` proves the three structural conjuncts of `Envelope.Sound`
  for `String.utf8ByteSize` (`utf8_append`, `utf8_escape`, `utf8_trim`) and
  `utf8_envelope_sound`, which reduces soundness to the tokenizer, response and
  tool bounds.
- `RestrictedDomain.lean` proves `noninterference_on`, `erase_correct_on` and
  `shape_budget_sound_on` under `ConformsOn`/`TransparentOn` plus `RunsIn`, and
  the certified end-to-end theorems `certified_noninterference`,
  `certified_secret_inputs_sound`, `certified_preservation`,
  `certified_budget_sound` and `certified_shape_exact`. Their only run-time
  premise is the input guard `boundedStore`. `padWorld_*` shows the restricted
  premises are satisfiable by a non-truncating padder that violates global
  conformance.
- `VocabularyEnvelope.lean` adds `segmentation_count_le` and
  `tokenizer_alpha_one`: a tokenization into nonempty pieces that concatenate to
  the input has at most one token per byte. The byte-bounded runtime checks
  both premises before every dispatch.

`ShapeCore.lean` also exposes `roundtrip` (`lean --run proof/ShapeCore.lean
roundtrip programs.json`), which decodes and re-encodes programs to check the
Python serializer.

Check everything, in dependency order, with an axiom audit:

```bash
python publication/check_proofs.py --output out/proof-receipt.json
```

Expected: 7 files, 2,312 lines, 78 theorems, no `sorryAx`; certified theorems use
only `propext` and `Quot.sound`.
