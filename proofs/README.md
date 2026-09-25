# Coq development

`OrchLang.v` mechanises four results of `docs/FORMAL_MODEL.md` for the core
calculus of its §1. It is about 1,100 lines, builds with Coq 8.18 in a few
seconds, and uses no axioms:

```
make proofs
```

compiles it and then `Assumptions.v`, which runs `Print Assumptions` on every
main theorem. Each must print `Closed under the global context`. No `Admitted`,
`admit` or `Axiom` appears in the development.

## What is proved

| Coq name | Paper result | Statement |
|---|---|---|
| `equiv_sound` | Lemma 2 | Two programs related by the request-equivalence judgment `bequiv`, from stores related on its variable relation, produce the same history on every tape and leave related stores. |
| `resolve_exact` | §5, resolution | Inlining the arm that a store's outcome vector selects, for every secret guard, does not change the execution, provided no statement assigns a secret. |
| `request_trace_noninterference` | Theorem 1 | If the resolutions of a program under two stores' outcome vectors are related by the judgment, starting from the identity on the public variables where the stores agree, the two executions produce the same history on every tape. |
| `observers_agree` | Theorem 1 | So every function of the history — trace, per-provider view, bill under any tokenizer and any envelope, spend — agrees. |
| `unary_bound`, `guaranteed_bound` | Theorem 5 | Output tokens ≤ the analysis's output figure and billed input ≤ its guaranteed input figure, for every execution. |
| `size_blind` | Theorem 6 | A μ-indexed analysis that is sound for total output tokens rejects every program with a feasible secret branch whose then-arm calls a model with a positive cap on a request containing a text constant that has a fresh twin, whatever the else-arm is. |

The provider `Pi`, validator `V`, keying schemes `key_call` and `key_retry`,
the tape, and the guard predicates are section variables. Theorems 1 and 5
hold for all of them; the global, per-model and per-request keying schemes of
the paper are all functions of the history and the request, which is the only
shape the development assumes. Theorem 6 quantifies over analyses, and its
soundness hypothesis quantifies over deterministic providers, which is the
weakest form of the hypothesis.

## Hypotheses of Theorem 5

`unary_bound` assumes, as section hypotheses, exactly what the certificate's
guaranteed figures assume:

* `Pi_cap`: the provider reports at most `cap m` output tokens.
* `Pi_bytes`: a response is at most `rbytes m` bytes. The implementation takes
  `rbytes m` to be `λ × cap m` for the model's tokenizer, or the client byte
  cap. That decoding `o` generated tokens yields at most `λ × o` bytes is
  argued in `docs/FORMAL_MODEL.md` §7 and checked empirically by
  `bench/tokenizers/measure.py`; it is *assumed* here.
* `bin_contract`: billed input — tokenizer plus envelope — is at most
  `κ × bytes + σ + overhead`. The per-tokenizer `(κ, σ)` are the measured
  contracts in `src/tokenizer_contracts.cpp`; that a contract holds for every
  string is argued structurally, not proved.
* `wf_block`: every binding's byte bound covers the responses it can receive
  (`rbytes m ≤ vb x` for a call binding `x`), and the initial store respects
  the declared byte bounds.

## Modelling choices

* **Strings are Coq strings**, sequences of 8-bit characters, so
  `String.length` is a byte length. The proofs never inspect the characters
  except in Theorem 6, whose fresh twin must contain a character absent from
  every text constant of the program.
* **The store is flat.** OrchLang's block scoping appears as freshness side
  conditions in the call rule of the judgment: a call may bind only a variable
  not already in the relation. The implementation meets them by giving every
  declaration a unique binding identity.
* **Static text is merged** before comparison, as in the implementation;
  `merge_eval` proves merging preserves the request.
* **The judgment is a relation.** The implementation computes, per outcome
  vector, a signature and compares signatures for equality. That equal
  signatures yield a derivation of `bequiv` is argued on paper.
* **Resolution requires that nothing assigns a secret.** In the flat store a
  variable is a binding identity. The implementation gives every declaration
  its own identity and declares secrets only at top level (`E203`), so no call
  rebinds a secret, even one that reuses its name.

## What is not mechanised

* Lemma 1 (coupling validity): that under a fresh keying scheme a tape-driven
  execution has the distribution of independent sampling. The development
  proves *pointwise* noninterference for every tape; turning that into
  equality of distributions is Lemma 1.
* Theorem 2 (the `log2 k` leakage bound), Theorem 3 (provider and bill normal
  forms), Theorem 4 (relative completeness), Proposition 7.
* The tokenizer contracts and the λ decoding bound, which are hypotheses.
* The C++ implementation, which is connected to this model only by the
  differential tests in `tests/tests.cpp` and the harness in
  `bench/evaluate.py`.
