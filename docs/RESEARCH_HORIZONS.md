# Research extensions after the October 2026 artifact

**Review date:** 9 October 2026. This is a targeted, primary-source-informed
research assessment, not a systematic review. It identifies feasible
extensions; none of the proposed methods below is present in the current
artifact. The current subjective novelty scores remain 5.5/10 overall and
5.5/10 for the applied method. A requested score of 8/10 is not supported by
the current result or by these unimplemented plans.

## What the updated literature changes

The nearest research areas now include more direct work than a general
“LLMs are stochastic and costly” framing suggests:

* PPDL is a peer-reviewed probabilistic language for multi-call LLM/tool flows
  that propagates uncertainty and supports inference scaling. Its evaluation
  compares strategies under total-token budgets, and its proof-repair example
  logs token usage. It is not a secret-conditioned usage-channel analysis,
  but this overlap narrows the candidate delta: a workflow trace distribution
  or budget alone is not new. [Mandel et al., ICML 2026](https://proceedings.mlr.press/v306/mandel26a.html).
* Point-to-point probabilistic leakage and symbolic quantitative information
  flow already include program locations, nontermination, entropy, KL
  divergence, and mutual information. Adding a generic TV or MI calculation
  would not be a new theory. [Chothia et al., IEEE CSF 2013](https://doi.org/10.1109/CSF.2013.20),
  [Schröer et al., 2024](https://doi.org/10.1007/978-3-031-75783-9_6).
* ProMCP measures token and latency costs across an MCP pipeline. It is
  execution profiling, not a source-level relational proof, but it means
  workflow cost observability already has a substantial current baseline.
  [Anjum et al., Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1967/).
* Provider-report integrity and hidden provider-side work are separate active
  topics. The ICML 2026 position paper describes hidden token/call inflation
  and model substitution; the IMMACULATE, Token Inflation, and PTIA papers
  study cryptographic or black-box audits of provider behavior. These are
  adjacent threat models, not source-level usage confidentiality. They make
  any claim that OrchLang audits invoices, verifies provider usage reports, or
  guarantees honest billing indefensible. [Sun et al., ICML 2026](https://proceedings.mlr.press/v306/sun26bd.html),
  [Guo et al., arXiv:2602.22700](https://arxiv.org/abs/2602.22700),
  [Hoque et al., arXiv:2605.30040](https://arxiv.org/abs/2605.30040),
  [Chen et al., arXiv:2609.20370](https://arxiv.org/abs/2609.20370).
* Multi-call retained context has direct billable-state and denial-of-wallet
  work. The interesting remaining boundary is confidentiality of a defined
  usage observer, not generic recursive cost growth. [Zhang et al.,
  arXiv:2609.28585](https://arxiv.org/abs/2609.28585).
* BPE and WordPiece tokenization already have finite-state transduction
  foundations. A possible cross-model request-bound feature would compose
  existing tokenizer and serialization semantics; it should not claim new
  tokenizer theory. [Cognetta & Okazaki, Computational Linguistics 2025](https://doi.org/10.1162/coli.a.23).

These sources leave a candidate integration gap: analyze a **defined
per-call usage trace as an observable channel of a probabilistic, multi-call
LLM workflow**, with the call's complete modeled request and outcome law
participating in control and composition. This is a candidate gap, not a
priority claim. A broader literature search and comparison with probabilistic
program analyses would be required before writing “first.”

## Ranked research directions

Scores below are comparative judgments for a possible implemented extension:
scientific novelty means likely contribution beyond the cited methods, not
acceptance odds; usefulness is potential user value; risk is implementation
and validation difficulty. They are not scores for current OrchLang.

| Rank | Direction | Novelty potential | Usefulness | Risk | Rationale |
|---|---|---:|---:|---|---|
| 1 | Finite probabilistic billing-channel analysis | 6/10 | 8/10 | High | The most direct extension of the security property; it measures leakage instead of only proving equality. QIF mathematics and probabilistic LLM-flow distributions are established, so the contribution must be the request/history-conditioned usage observer, composition theorem, and demonstrated precision. |
| 2 | Certified cross-tokenizer request bounds | 5.5/10 | 8/10 | Medium-high | Directly addresses incompatible units in multi-model chains and full-request cost. FST foundations exist; value is a reproducible, sound bridge between versioned tokenizer/decoder/serializer contracts. |
| 3 | Counterexample-guided refinement of conservative results | 4.5/10 | 7/10 | Medium | Helps users understand and resolve `unknown` or rejected cases. Product programs, symbolic execution, and QIF are established, so it is chiefly analysis precision and diagnostic quality. |
| 4 | Framework extraction and actual runtime execution | 4–5/10 | 8/10 | Medium | Strongest near-term software and accessibility value. The LangGraph integration is already implemented and evaluated, but it is an interoperability contribution, not a new relational method. |

### 1. Finite probabilistic billing-channel analysis

**Proposed semantics.** Add an explicit finite semantic contract
`Ω(c,k,Q,h)`, where `c` is a fully resolved model/options/price contract,
`k` is its call ordinal, `Q` is the exact request descriptor in the source
language's current abstraction, and `h` is the complete modeled prior history
needed to make the kernel conditional. For every key, the user supplies a
finite distribution with rational probabilities over complete modeled
outcomes (response text, reported usage, status, and any metadata used by
later control or requests). The model must include every state component
that affects the law; otherwise the result is conditional on an incomplete
kernel. The kernel is a declared mathematical input, not inferred from a
provider.

For a finite workflow horizon and finite supported public/secret domains,
enumerate reachable states and perform exact dynamic programming over
rational probability mass. For each secret assignment `s`, compute
`P(T=t | S=s)` over observable usage traces `T`. Define the trace observer
before analysis; a reasonable choice is ordered per-call resolved contract,
input/output usage, status, and stop/truncation marker. It excludes prompt and
response content. Compute pairwise total variation exactly as
`TV(P_s,P_s') = 1/2 Σ_t |P(T=t|s)-P(T=t|s')|`. With an explicit prior on
secrets, compute mutual information as a symbolic weighted-log expression or
provide a certified numerical interval. Charge rounding, unit prices, and
which status/termination fields are visible must be explicit. The analyzer
must reject unsupported or unbounded semantics instead of silently using an
ordinal-only or unconditional kernel.

**What would be new enough to investigate.** General quantitative QIF and
probabilistic leakage are established. The possible method contribution is
compositional construction of a request- and history-indexed observable
usage-channel for multi-call workflows, together with exact certificates and
the effect of response-dependent future requests. A finite deterministic
shared-oracle result is a limiting case with TV zero; the probabilistic
analyzer adds a distinct answer when secret arms issue different requests but
the resulting billed-trace distributions happen to match or approximately
match. It should also find cases where equal expected cost hides different
trace distributions.

**Minimum credible experiment.** Implement a small rational-kernel language
for the existing finite graph subset, with a hard call horizon and finite
response support. Independently implement a brute-force enumerator for tiny
fixtures. Compare both analyzers on: (a) identical requests and kernels,
(b) distinct requests with equal usage-trace distributions, which the current
request-equality rule conservatively rejects, (c) same expected bill but
different trace distributions, (d) response text that changes a later
request, (e) status, termination, or output-usage leakage, and (f) mutations
that yield known nonzero TV. Test exact rational mass conservation and compare
against brute force. Report reachable states, horizon, support size, time,
memory, exact TV, and any MI interval. Do not call sampled provider trials a
kernel proof. Do not assert privacy for request contents when the chosen
observer sees only usage.

**Publication test.** A paper would need a soundness theorem and a clear
complexity/result boundary in addition to the working code. Generic TV/MI,
probabilistic products, or a tool wrapper around an existing QIF package
would not justify a large novelty score. This is the only direction here with
a plausible research-method path beyond the current 5.5 score, but the amount
of work and competition from established QIF makes a score of 8 uncertain and
not currently justified.

### 2. Certified cross-tokenizer request bounds

**Problem.** The compiler cannot compare token units across unrelated model
contracts without a conversion premise. A scalar “bytes per token” estimate
does not by itself bound a full request: serialization, system/tool overhead,
normalization, Unicode decoding, special-token treatment, and token-boundary
effects also matter.

**Proposed certificate.** For each declared model contract, bind immutable
hashes and versions for the output token vocabulary/decoder, target tokenizer,
Unicode error policy, normalization and pre-tokenizer, special-token rules,
and full request serializer. Given source output cap `O`, compute a safe upper
bound on target request tokenization over every possible source token sequence
of length at most `O`, inserted into the declared template and serialized
according to the declared adapter. A conservative implementation can start
with maximum decoded byte weight per source token and a proven bound on
replacement/normalization expansion, then use target byte fallback to bound
token count. A more useful implementation can compose a source decoder and
target tokenizer transducer and solve a bounded max-plus path problem. The
FST certificate must include the exact converter tables and a separate
replayer must verify its bound. If the tokenizer has no documented byte
fallback, unknown normalization, unknown serializer, or provider-hidden
special-token behavior, fail closed.

**Evaluation.** Start with two version-pinned open tokenizers and a declared
local serializer, not a paid API. Exhaustively enumerate all source token
sequences up to a small cap and compare the certificate to actual target
tokenization; include malformed UTF-8, replacement sequences, byte boundaries,
special-token-looking text, control characters requiring serialization
escaping, and non-English Unicode. Then test longer randomized sequences and
verify every observed target request is below the certified bound. Report
tightness as well as soundness. A loose byte-count cap may prove safety but be
useless for program acceptance; measure the acceptance/precision tradeoff.

This is a practical compiler-analysis contribution, not new tokenization
theory. It must not claim actual provider request accounting unless the
provider's serialization and tokenizer contract are complete and verified.

### 3. Counterexample-guided refinement

Add a structured rejection result with one of three meanings: a static proof
obligation failed; a bounded execution found a concrete usage-trace witness;
or the analyzer hit an explicit unsupported/unknown case. For a witness,
include public/secret assignments, the complete modeled oracle table or
kernel seed, paired requests, and the first divergent event. A replay utility
should verify the witness without trusting the producer's “unsafe” label.

A subsequent refinement loop could split supported finite input or guard
partitions based on a witness and rerun the relational product. Refinement is
sound only if the partition is added to the declared semantics and the
abstraction map is checked; matching on a finite fixture alone cannot convert
a rejection into a proof. Compare rejection outcomes and precision on current
authored cases, bounded source projections, and deliberate mutations. Measure
which unknown cases become classified and how much cost/state growth results.

This would make the compiler substantially more useful, but diagnostics and
counterexample-producing symbolic execution are mature areas. Treat it as
artifact and precision improvement unless it yields a new verified refinement
algorithm or a surprising theorem.

### 4. Framework-facing execution

The optional LangGraph adapter now runs generated workflow graphs through the
actual pinned LangGraph package after certificate replay. Its backend report
covers 23 cases, 888 executions, 4,528 call events, and zero differences
against the graph producer's reference evaluator; 24 runs stop at the
configured call horizon. A separate bounded Python-AST frontend now exports a
small source subset and runs those source workflows through LangGraph: the
frozen source study records 30/30 accepted source/graph trace matches over 66
calls, 6/6 rejected-source value-probe matches, 12 equal accepted secret pairs,
and 3 differing pairs for the relationally rejected case. Frontend, backend,
certificate replayer, and runtime helper hashes are recorded in
[`langgraph_source_study.json`](../bench/results/langgraph_source_study.json).
These are authored finite fixtures, not an exhaustive Python translation
proof; the backend comparison uses the graph producer reference, and neither
study validates a model provider. The integration tests include mutation
after verification and recursion/call/byte caps. This strengthens executable
interoperability and software utility, but does not establish external
adoption or new relational theory. Further work should favor a proof or more
independent source semantics and external user evaluation over additional
synthetic execution counts.

## Recommendation and novelty threshold

Prioritize direction 1 only if the project is prepared to add a real formal
semantics and independent differential test harness. Direction 2 is a more
bounded practical extension if the intended use is cross-model token-budget
propagation. Direction 3 is worthwhile for product usability but should not be
sold as fundamental novelty. The completed framework integration strengthens
software-track utility and accessibility; it does not substitute for a new
scientific result.

The current method remains a sufficient pathwise-equality check under a
declared request-sensitive shared oracle. Existing work already supplies
relational cost analysis, resource-aware noninterference, probabilistic QIF,
LLM probabilistic flows, tokenizers as finite-state transducers, workflow
profilers, and provider-side billing audits. The defensible residual question
is a narrower composition problem at their intersection. A targeted audit
does not establish priority. I do not recommend scoring the present journal
novelty above 5.5/10. Reconsider only after implementing one of the first two
directions, proving the stated guarantee, and demonstrating an important
expressiveness or precision gain against relevant baselines.
