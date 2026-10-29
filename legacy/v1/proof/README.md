# Checked feasibility proofs

Use Lean **4.19.0**. No Mathlib, network fetch, `sorry`, custom axioms or admitted
lemmas are needed to check these files. They are separate small models; consult
`docs/SEMANTICS.md` before interpreting their scope.

```text
lean proof/BoundedCore.lean
lean proof/FiniteRelational.lean
lean proof/DataflowCore.lean
lean proof/AggregateReordering.lean
```

`#print axioms` reports standard Lean `propext`, `Quot.sound` and, in the
dataflow unit/arithmetic lemmas, `Classical.choice` where used. These are logical
dependencies, not a measure of implementation security. It must not report
`sorryAx`. The checker guards include a valid identical-request
plan, an invalid equal-length/different-content plan, and a wrong-plan certificate.

Use the `lean` executable from an isolated Lean 4.19.0 installation, or replace
`lean` in these commands with its absolute path. The historical Windows tool
archive was downloaded from the official leanprover/lean4 v4.19.0 GitHub release.
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

The primary interface is now a verified decision procedure: `checkProgram`
computes whether normalization succeeds, and `decoded_decision_sound` proves
the resulting relational guarantee for decoded programs. The executable accepts
`lean --run proof/DataflowCore.lean decide batch.json` with cases containing only
`program` and `execute`. The legacy saved-plan check recomputes normalization;
its plan is diagnostic output, not a proof-carrying witness or an efficiency gain.

New rewrites preserve complete state-transformer semantics: string-append
associativity, empty-string identities, adjacent literal folding, sequence units,
and elimination of public branches with equal normalized arms. The source reader
already folded adjacent template literals, so request-rewrite precision gains
are reported separately at core level. No observable call reordering occurs in
this ordered-trace procedure.

## Separate aggregate-only decision

`AggregateReordering.lean` supports exactly two independent closed calls in each
arm of one secret branch. It accepts equal action sequences and their reversal.
An action includes the full contract and serialized request. Its observer records
input bytes, output bytes, calls and failures for every contract; it discards
call order. This judgment does not override C++ IFC rejection.

`samples_comm` proves permutation of weighted aggregate outcomes after swapping
the calls. `mass_perm` and `independent_calls_aggregate` prove equality of the
exact histogram numerator for every Boolean predicate on the full observation,
and equality of the common probability denominator. This is a distributional
result modulo enumeration order, not equality of ordered traces. Each finite
kernel uses natural numerators and a common denominator; normalized rational
rows have this representation. The executable checks positive denominators and
unit row mass. The algebraic theorem itself does not require valid probabilities.

`decision_sound` and `decoded_decision_sound` cover the separate executable.
`scripts/decide_aggregate.py` binds it to a restricted, trusted Python source
reader. Response-dependent requests, secret text, mutable state, timing, retry,
tools, and branch/nonliteral outputs are rejected. Literal source outputs occur
only at workflow root. Budgets and provider conformance remain separate.

The additional `independent_calls_private_results` theorem strengthens the
aggregate result to the joint distribution of usage and a multiset of complete
responses/statuses indexed by full action. Duplicate draws retain multiplicity.
`decoded_private_results_sound` connects the same decision to this richer
observation. The separate `private` executable mode and optional
`--finite-kernels`/`--private-results` CLI arguments export enumerated finite
outcomes to a trusted caller; they do not introduce public source output or
model generation. The original aggregate JSON interface is unchanged.
