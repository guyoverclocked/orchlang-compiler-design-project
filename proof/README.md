# Checked feasibility proofs

Use Lean **4.19.0**. No Mathlib, network fetch, `sorry`, custom axioms or admitted
lemmas are needed to check these files. They are separate small models; consult
`docs/SEMANTICS.md` before interpreting their scope.

```text
lean proof/BoundedCore.lean
lean proof/FiniteRelational.lean
lean proof/DataflowCore.lean
```

`#print axioms` reports standard Lean `propext` and `Quot.sound` where used;
it must not report `sorryAx`. The checker guards include a valid identical-request
plan, an invalid equal-length/different-content plan, and a wrong-plan certificate.

On the author's Windows machine the isolated executable is
`C:/Users/nambi/Documents/OrchLang Publication Work/tools/lean-4.19.0-windows/bin/lean.exe`.
It was downloaded from the official leanprover/lean4 v4.19.0 GitHub release.
Archive SHA256: `2c197a74b6d9c4d46363e34e06591165ed848237ba66de849f8b8d5539eb3895`.
The release API provided no publisher digest, so this is a locally measured
provenance checksum, not an independent signature verification.

`certificate_sound` covers typed `Program` and `Plan` values. The executable
JSON decoder has `decoded_certificate_sound` for successfully decoded values.
It accepts a JSON batch of `[program, plan]` pairs; constructors are arrays with
tags `skip`, `call`, `seq`, `branch` (program only), `repeat`, and `retry`.
`lean --run proof/FiniteRelational.lean batch.json` prints the checked Booleans.
Unknown tags/arity and over-limit depth/repetition fail closed. No certificate
is loaded as Lean source code. Retry stops when an attempt has no failed event;
all previous attempts remain in the observation.

`scripts/closed_certificate.py` independently reconstructs the restricted source
core and checks source digest/core agreement before invoking Lean. That Python
reader and binding are trusted; no verified source parser is claimed. This path
does not validate the C++ `certify` report. The finite result assumes a
shared kernel function of the full `Action` (contract **and request**).
For probability interpretation its finite weight tables must additionally be
normalized and nonnegative. No theorem verifies that a provider satisfies this.

## Text-valued dataflow core

`DataflowCore.lean` is a separate stronger model with a text store. Calls bind
actual response strings; later requests can use those bindings. Public text and
Boolean inputs are shared between executions, while secret Booleans affect
control. Normalization correctness is equality of complete state-transformer
semantics, so it composes through dataflow. Its relational and decoded-acceptance
theorems use the same standard axioms. Lexical retry restores the outer store
between attempts and retains every billed failure. This theorem is not a new
general relational logic or a mechanized implementation of the C++ IFC policy.

The executable JSON format uses case objects with `program`, `plan`, `execute`.
Programs contain `skip`, `call` with a response slot/contract/text expression,
`seq`, `public`, `secret` and `retry`; plans cannot contain `secret`. Text
expressions are `literal`, `var` and `append`. Optional execution contexts supply
public/secret Boolean arrays, a text store, explicit finite kernel rows and a
store-observation limit. The executable checks rational row masses, duplicate
keys, missing positive-probability requests and operational limits. These are
runtime checks, not a kernel-validity theorem. Error status is a returned value,
not an exception that aborts a body. The source reader remains trusted Python.
Full commands and boundaries: docs/DATAFLOW_CERTIFICATES.md.
