# Roadmap assessment and alternative approaches

Primary sources checked on 29 October 2026. Recommendations below distinguish
implemented changes from proposed experiments. A review's target accuracy or
overhead is not evidence that a technique will achieve it.

| Problem | Approach | Assessment for this revision |
|---|---|---|
| Admission after generated text | Compositional bounded-value certificate | Implemented in Lean. Bound every store slot in a common text-size unit, account for concatenation/escaping/trim, and require receiving-tokenizer, response, tool and context contracts. The certificate implies RunsIn for every tape; the concrete GGUF contracts remain unproved. |
| Admission after generated text | Same-tokenizer token-ID buffers | A useful alternative when an upstream result can remain in the receiving tokenizer's unit. Re-encoding strings, escaping and cross-model transport destroy the simple identity bound. This changes the interface and needs its own lowering proof. |
| Conservative byte envelopes exceed context | Explicit byte-bounded output type | Enforce a byte bound as part of both original and shaped semantics. This permits a conservative receiving-token bound, but adding truncation only to shaped executions would invalidate preservation. A new type/adapter needs evaluation of utility as well as resource bounds. |
| Overflows cannot be ruled out | Public envelope classes or predictive mitigation | Choose public classes before inference and model every observed class change. If secret-dependent overflow changes a schedule, exact noninterference is replaced by an explicit leakage budget; repeated observations also matter. |
| Isolated prefill exposes length | Accounting-only scope | Implemented in the paper. Treat two-pass prefill as an executed resource-envelope stress test. Report normalization is a useful lower-cost option for an exported-log observer. |
| Stronger serving interface | Fixed-length batched prefill with isolated attention | Worth a separate backend study, but one call of length T alone is insufficient. Sequence IDs, positions, masks, requested logits, cache updates and errors can reveal the real-token subset to a server-level observer. Define the observer before claiming a stronger guarantee. |
| Qwen grading collapses | Constrained categorical output | Prefer a separate ablation with an explicit yes/no JSON grammar over merely appending more prompt instructions. Grammar constraints establish syntax, not relevance accuracy or two-branch coverage. They also change the response kernel and must be bound into the model contract. |
| Timing leakage | Deadline release or predictive mitigation | A separate research extension. Must retain deadline misses, timeout/failure behavior, release jitter and repeated-query observations. Delaying a final response does not hide intermediate events from an observer that can see them. |
| Large loop overhead | Publicly selected loop envelopes | Potentially lower cover work if the envelope is public. Secret-dependent early envelope choice leaks unless explicitly analyzed. No claimed 60% improvement follows from the proposed schedule alone. |

## Why these alternatives follow from the literature

[Askarov, Zhang and Myers, CCS 2010](https://www.cs.cornell.edu/~zhangdf/pub/ccs10.pdf)
study wrappers that delay observable events to trade performance against bounded
timing leakage. This supports predictive mitigation as a distinct specification,
not the review's unmeasured promise of near-chance attack accuracy for OrchLang.
The relevant boundary is each observable release, not just workflow completion.

[LMQL, PLDI 2023](https://www.sri.inf.ethz.ch/publications/beurerkellner2023prompting)
combines control flow and output constraints in language-model programs. It is a
useful comparison for OrchLang's language design: constraining the generated
language and constraining the usage observation are separate goals. A categorical
grader can use both, but a new constraint must appear in the response contract.

The [llama.cpp grammar documentation](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
describes GBNF and JSON-schema conversion for constrained generation. This makes
a grammar-constrained grading ablation technically plausible. It does not justify
assuming a small model will classify retrieved documents correctly.

The [llama.cpp public API](https://github.com/ggml-org/llama.cpp/blob/master/include/llama.h)
exposes per-token positions, sequence membership and requested logits in addition
to batch length. My inference from this interface is that a masked batch can hide
length only from an observer denied the distinguishing metadata. The review's
claim that a single eval submission immediately establishes model-server
noninterference is therefore too strong. This inference is not an implementation
or a measured backend result.

[Barthe et al., POPL 2020](https://popl20.sigplan.org/details/POPL-2020-Research-Papers/9/Formal-Verification-of-a-Constant-Time-Preserving-C-Compiler)
verify constant-time preservation in a C compiler. This is the appropriate
comparison for the verification boundary: OrchLang validates a core translation
and keeps its parser and serving implementation trusted. It does not have an
equivalent verified lowering to hardware.

[Weiss et al., USENIX Security 2024](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss)
study token-length leakage in encrypted assistant responses. Their packet-based
observation is stronger and different from OrchLang's aggregate accounting
record, so the paper cites this motivation without claiming to defeat the attack.

## Decisions on the review's acceptance criteria

The new theorem and formal presentation are appropriate additions. The
accounting-only alternative is the defensible padding correction for the current
backend. Static weight sensitivity and a raw-output CRAG diagnosis are useful
and inexpensive; they are included. Timing mitigation, new decoding constraints
and attention-isolated serving should not be rushed into the same result without
their own models and measurements. A full homogeneous 1,684-pair campaign remains
different from the targeted final-release validation and must not be implied by
either regenerated tables or unchanged source-level shapes.

Human declarations, archival deposition and journal submission are handled by the
authors. This revision does not manufacture those facts or publish an artifact.
