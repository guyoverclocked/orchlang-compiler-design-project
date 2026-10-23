# Candidate semantics and implemented scope

Status: 23 October 2026, implementer-reviewed scope. The author waived waiting
for unavailable faculty input. Independent human sign-off has not occurred.
The master plan controls conflicting historical descriptions. Do not infer an
end-to-end theorem from the source checker's acceptance message.

## Threat model and observations

The proposed adversary is an account observer, not the provider. The provider
sees requests and may observe contents outside this cost-only model. Public
inputs, declared caps and semantic contracts are fixed between the compared
worlds. Secret contents may differ. Released/declassified values must be fixed
by a separate release policy; the present core proofs have no declassification.

An ordered billing observation is a sequence of events:
`(semantic contract, unit, input usage, output usage, status)`.
An aggregate observation sums input/output usage, calls and failures by contract
and unit. It is a deterministic projection of the ordered trace. Reversing two
different calls can preserve the aggregate and change the trace. Timing, tool
side effects and returned contents are excluded from these two observations.
Content confidentiality remains a separate obligation: equal bills do not
permit public output of secret content. The finite reference's `private_output`
means retention by a trusted recipient, not the C++ language's public `output`.

Low-equivalence must fix actual public values, not their upper bounds. For
response-dependent public stores it also requires the inductively maintained
content relation. Pure equality of response lengths is insufficient.

## Primitive contracts and couplings

A proposed call kernel maps a fully serialized request and external state to a
distribution over response text, usage, status and successor state. To use an
identity coupling, require equal requests, equal semantic contracts, and related
external state that makes the kernels identical. The identity joint distribution
then has each required marginal. Two independent actual invocations need not
produce equal traces. Same seeds are not evidence of valid marginals.

For unequal requests, no equal-resource coupling is assumed. The permanent
finite example maps `yes` to output `x`, and `no!` to 100 copies of `x`.
Their input byte lengths agree and their output distributions differ. A
common sampled output-length tape would change one marginal in this example.

Semantic contracts need provider/model/tokenizer/serializer revisions, sampling,
cap interpretation, retry/error policy, usage accounting and external-state
assumptions. The finite reference requires these fields explicitly. Its
implemented serializers/tokenizers are only raw UTF-8 requests and synthetic
byte/codepoint counters. They are not production model tokenizer families.

The C++ grammar currently supports `mock(...)` only. Its canonical abstract
contract contains provider spelling, model revision spelling, cap and optional
price; version `orch-abstract-model-v1` fixes the remaining mock interpretation.
It is not a complete cloud contract. Unknown cloud fields cannot be verified
merely by placing a provider-like name inside `mock("...")`.

## Separate implemented semantics

| Artifact | Precisely established coverage | Exclusions/gap |
|---|---|---|
| C++ semantic/relational analyzer | Scoped resolution facts; canonical abstract contracts; ordered typed argument identities and literal content; raw template/substitution-map equality; public guard binding identities; bounded branch/retry signatures | No mechanized implementation soundness, complete serialized-request IR, typed provider-token conversion, or adapter proof |
| C++ mock interpreter | Seeded synthetic lengths, lexical environments, bounded retry sampling, contract-indexed bills; explicit invalid-pin errors | No text generation; declarations and retries consume a shared RNG; no general same-seed pathwise theorem; no faithful realization of arbitrary reference kernels |
| `runtime/finite_reference.py` | Independent hand-authored text IR, exact rational finite enumeration, response-dependent requests, lexical branch/retry stores, failed-but-billed attempts, ordered/aggregate observers | No automatic C++ lowering; no real tokenizer; no mutable provider state; limit 16 retry attempts and 100,000 enumerated paths; over-limit is unsupported, not unsafe |
| `proof/BoundedCore.lean` | Scalar unary cap theorem for nondeterministic calls/sequence/branches and up-to-n repetition; identity-branch trace equivalence; observer projection | One synthetic resource unit; primitive bounds are execution premises; no stores, request text, probabilistic semantics or C++ connection |
| `proof/FiniteRelational.lean` | Normalizer correctness, equal weighted trace lists for all secret Boolean stores, observer projection, typed and decoded-JSON certificate soundness; fixed repetition and bounded early-stop retry, all failures billed | Closed requests only; shared stateless finite kernel; no response-dependent requests, kernel-validity theorem or verified source/C++ connection |
| `runtime/source_gate.py` and `scripts/closed_certificate.py` | Independently reparse restricted source, resolve lexical declarations, substitute literal arguments, bind source SHA256/core to an untrusted plan and invoke Lean | Trusted Python reader/serialization/hash binding; excludes inputs, response-dependent requests, retries, tools, prices and reclassification; no C++ mock budget check |
| `runtime/replay_adapter.py` | Separate finite-table text executor; choice tapes, exact weights, usage units and failed-attempt billing; fixed-case exhaustive reference conformance | No inference/provider; execution correspondence tested, not proved |
| `proof/DataflowCore.lean` | Store-transformer normalization, response-dependent requests, shared public text/Boolean inputs, secret Boolean branches, lexical bounded retry and decoded certificate soundness | Shared stateless finite kernels; UTF-8 byte observations; secret text, tools, output events and C++ correspondence excluded; probability interpretation needs valid kernels |
| `runtime/dataflow_gate.py` and `scripts/dataflow_certificate.py` | Separate source reader/checker path for public inputs and downstream call bindings; symbolic requests and aligned lexical slots; root literal outputs only | Trusted Python reader/slot allocation/serialization; source retries and reclassification rejected; no C++ budget check or override of C++ confidentiality policy |

The Lean finite relational theorem is algebraic: it holds for arbitrary kernel
tables, even invalid probability tables, because both sides compute the same
weighted trace list. Its probabilistic interpretation additionally requires
nonnegative normalized finite kernels. Python checks these conditions for its
own tables; there is no verified bridge between the two implementations.
The dataflow core now also has an executable text evaluator for direct
cross-implementation checks; its source-reader correctness is still unproved.
See DATAFLOW_CERTIFICATES.md for the added scope and distinct policy judgment.

## Resource arithmetic and attempts

Do not add heterogeneous tokenizer counts. Proposed resource vectors are indexed
by contract and unit. The C++ runtime uses the homogeneous `mock-length-v1` unit;
its historical `chars_per_token` option actually divides raw string byte length.
It adds template estimates and argument lengths, including template placeholder
syntax. This is deliberately not tokenization of fully substituted text.
An input serialized under another tokenizer needs retokenization or a proved
bound, which the production source language does not implement.

Static arithmetic saturates and rejects a saturated total bound (`E266`). Ceil
division no longer forms an overflowing numerator. Currency figures in the
legacy report are floating-point estimates, not spending authorization. A paid
runner would require exact integer/decimal reservations and provider cap
assumptions. No paid runner or key has been enabled.

The Python reference defines an attempt as successful iff every call in that
attempt succeeds. It bills errors, stops on success, and caps attempts. The
C++ mock samples retry failure independently after a body. These semantics differ;
they must not be described as equivalent. Both Lean cores now permit bounded
early stopping. The finite proof follows the reference rule for closed requests,
using `retryDistribution`; a guard checks exact 1/2, 1/4, 1/4 weights. The source
gate rejects retry syntax because the C++ interpretation differs.

## Remaining theorem and implementation obligations

1. Independent human review/reproduction remain unavailable.
2. Stores and downstream content are covered in the separate dataflow core under
   shared public values and secret-Boolean-only control; secret text inputs,
   stateful providers and full source semantics remain outside its theorem.
3. Prove the independent source reader or relate the complete C++ implementation
   to formal semantics. The trusted boundary is reduced rather than removed.
4. Closed-request certificates now reconstruct source and check plans with Lean.
   The C++ `certify` JSON remains an analysis report.
5. Replay conformance and tokenizer probes do not validate an inference/provider
   adapter. Do not silently transfer mock units to real tokens.
6. Validate a corpus independently; no accepted-counterexample-free finite test
   campaign can substitute for a general proof.

Until these are discharged, report the repaired regressions and limited core
theorems, not general cloud privacy or full-language verification.
