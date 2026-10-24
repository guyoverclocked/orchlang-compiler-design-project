# Faculty review packet: correctness, contribution and scope

Prepared 23 October 2026. Target date supplied by author: 30 October 2026.
This packet requests scholarly review, not authorization to spend money or submit.
No faculty sign-off has been recorded.

**Author steering:** the author waived waiting for unavailable faculty on
23 October. Implementation and offline evidence collection have continued.
Current manuscript: docs/manuscript/main.tex. Clean-snapshot evidence:
research/validated-2026-10-23/. The original questions below are retained for
eventual independent review; they do not imply the work is still waiting for
permission. MIT and author metadata are supplied; conflicts/final approvals and
independent human reproduction remain outstanding. Separate source-bound Lean
certificates and finite replay are now implemented within documented limits.

## What needs reviewing, in plain terms

The proposed claim is about what someone can learn from resource usage when a
secret changes. Equal maximum budgets do not establish equal actual usage. Equal
request lengths do not establish equal model-response distributions. The
conservative approach compares full request construction and semantic model
contracts, and states what must be trusted about the primitive/backend.

The immediate software repair is concrete: resolve declarations while scopes
are available, compare canonical contract fields rather than short model names,
preserve request content and argument order, and keep lexical scope information
through IR lowering. Equivalent model aliases remain admissible. These are
correctness/usability repairs, not claims that a new general logic was invented.

## Evidence the reviewer can inspect

1. Original checkout `a49fcdb`, `main`: fresh 95/95 passing tests, yet an accepted
   workflow bills 2 versus 987 mock units at seed 1. Original and fresh baseline
   logs are retained under `research/2026-10-23/` and
   `research/implementation-2026-10-23/baseline-*`.
2. Permanent developer examples: `research/separating-examples.md` and
   `bench/corpus/development/manifest.json`, including both acceptance and refusal.
3. Exact finite oracle: `runtime/finite_reference.py` and its tests. It does not
   import production analysis. The equal-length content example gives output
   counts 1 versus 100 under deterministic admissible request-dependent kernels.
4. Small Lean cores in `proof/`: compile with Lean 4.19.0. They prove only the
   judgments listed in `docs/SEMANTICS.md`; no proof verifies C++ or adapters.
5. Competent structural baseline, current development data, and isolated fault
   injection. See `docs/REPRODUCIBILITY.md` for commands and raw manifests.

## Closest existing capabilities and proposed route (G1)

Resource-aware IFC already exists (Ngo et al. 2017); relational cost analysis
already exists (RelCost); probabilistic AARA already exists (Raising Expectations).
eRHL provides quantitative relational probabilistic reasoning. PC2 already has
proof-carrying contracts and conditional real-world budget correspondence.
Hard-KLAIM already has typed interface trace safety, immutable identities, explicit
trusted adapters and Rocq mechanization. Detailed source/access notes are in
`research/literature.md` and `research/novelty-ledger.csv`.

No expressiveness separation from conventional IFC/trace identity or these logics
is established. The working route is therefore a software/reproducibility paper:
a useful bounded DSL checker, explicit failure taxonomy, scoped core proofs and
reproducible correctness evidence. Useful external application coverage is still
missing. A one-week deadline is not evidence of novelty or software maturity.

**G1 decisions requested:** Is this narrow tool contribution sufficient to pursue
an SCP Original Software Publication candidate? Which actual workflows would make
its usefulness credible? If a research route is preferred, identify one precise
delta beyond conventional IFC plus cost contracts, before adding extensions.

## Proposed semantic choices (G2)

- Adversary: an account observer; provider sees requests and is outside this
  confidentiality claim. Timing/content/tool effects require separate treatment.
- Compare states with equal actual public data and public contracts, not merely
  equal public lengths or caps. Declassification needs a separate release policy.
- Maintain two observers: ordered usage/status events and aggregate per-contract,
  per-unit usage/calls/failures. Aggregate equality does not imply trace equality.
- Use identity coupling only for the same fully serialized request and contract
  under related external state producing identical kernels. A probability
  coupling must have the actual marginals. Same seed is insufficient.
- Every failed-but-billed attempt counts. Early stopping, output content needed
  by later calls, model state and caching cannot be silently omitted.
- Treat the C++ mock's byte/divisor lengths as a synthetic unit. Different
  tokenizer counts require exact retokenization or an explicit justified bound.

**G2 decisions requested:** Are these assumptions useful and appropriate for the
intended observer? What fragment should be frozen for a one-week artifact?
Specifically review the missing connection between closed-request Lean semantics,
the text-valued finite interpreter, and the length-only C++ mock. The proposed
full-language distributional theorem is not yet proved. Do not sign off on it
based solely on compilation of the smaller proofs.

## Gates that remain

G3 requires source/IR checker correspondence and a matching independent semantic
oracle on the supported fragment. G4 requires an immutable final evaluation
protocol, fair baselines, external corpus census and human review before final
data. G5 requires another person to reproduce the release and trace claims.
License/ownership, author list, current SCP template and venue requirements need
author verification. The current software article is a working draft.

There is no request for an API key. Paid validation remains disabled; spend and
outstanding reservations are both USD 0. A scoped offline paper can omit paid
runs if it is otherwise defensible. Faculty review should prioritize soundness
and usefulness over adding a cloud experiment.

Record reviewer name, date, decisions, conditions and unresolved objections in
`research/PROGRESS.md`. Do not infer approval from silence or from this packet.
