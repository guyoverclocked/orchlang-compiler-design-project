# Six development examples for G1/G2

Executable source inventory: `bench/corpus/development/manifest.json`.
Independent finite semantics tests: `tests/test_finite_reference.py`.
All are developer-designed; external-workflow coverage is **zero** at this stage.

| Example | Conventional competent analysis / semantic oracle | Current repair | Interpretation |
|---|---|---|---|
| Shadowed contracts | Resolve declarations; distinct caps/kernels must not be conflated | `E236`; original audit source retained | Correctness repair, not a new general analysis principle |
| Equal length, different content | Content-dependent kernel gives outputs 1 vs 100 | `E236`; exact Python counterexample | Size equality cannot supply a valid coupling |
| Same request, different retry/error contract | Bounded self-composition includes every attempt/failure | Source retry mismatch rejected; reference keeps billed errors | C++/reference retry correspondence remains open |
| Cross-tokenizer composition | Retokenize exact text or keep separate units | Unsupported in source; reference byte/codepoint distinction | Synthetic unit example only, no real tokenizer-family validation yet |
| Equivalent aliases | Canonical semantic fields agree although declaration identities differ | Accepted; runtime bills by canonical contract | Avoid needless rejection caused by comparing fresh binding IDs alone |
| Public control, secret retained privately | Low-equivalent public routing permits differing branches; private content remains private | Source private store unused by public output; reference private-output example | Cost equivalence does not declassify content |

The correct conventional IFC/trace-identity baseline can express these judgments
with the same assumptions. No separating expressiveness result has been found.
The observer-order example is a useful scope distinction, not a novel theorem.
Current proposed value is a usable, auditable specialization with reproducible
failure cases. Faculty assessment and external usefulness evidence remain needed.
