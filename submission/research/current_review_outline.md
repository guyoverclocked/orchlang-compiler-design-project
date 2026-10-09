# OrchLang software review deck: current story

**Working title:** “OrchLang: Replayable Contracts for Token Usage and Request-Equivalent LLM Workflows”  
**Status:** frozen on 9 October 2026 against the sanitized 44-stage reproduction manifest (SHA-256 `65c8d8fd312f4a004df9faf3a2ecf193e3023594c2a01029ca157d22049ba035`) and trace-equivalence report (SHA-256 `9dddb048e411960b07c070c7fff2b169361c1df84ce786cfdb73b524bb56c861`). The final 32-slide PPTX and 32-page PDF were rendered and visually inspected. No submission or acceptance claim appears in the deck.  
**Canvas and style:** match the local ArchiveGate deck: 16:9, warm cream and navy, coral for secret choices, teal for proved alignment, rust for rejection, editable native diagrams, concise evidence captions.

## Central claim

The presentation distinguishes three questions that are often collapsed:

1. Does a finite workflow stay below its declared unary token envelope?
2. Do two executions with the same public inputs produce the same modeled usage-event trace under a declared shared outcome relation?
3. What information does a selected finite usage observation reveal under an explicitly supplied probability kernel?

OrchLang answers a bounded version of the second question with a C++ compiler, and a separate experimental JSON graph checker applies a product construction to finite-control workflows with productive call cycles. A bounded source bridge and a restricted Python AST front end exercise the graph model on authored source examples. A pinned LangGraph backend provides an execution comparison under a deterministic offline oracle. A separate finite-kernel analyzer computes exact finite usage channels. These are connected artifacts with distinct contracts; they are not one end-to-end proof of a deployed LLM service.

The cyclic guarantee concerns every finite modeled usage-trace prefix, conditional on equal public-input identities, a faithful graph model, complete modeled requests, and shared \(\Omega(M,k,Q)\). It says nothing about termination or a finite total-cost bound for an unbounded cycle. The stochastic analyzer describes finite, user-specified kernels and fixed public stores; it does not estimate or certify a provider distribution.

## Main story (23 slides including cover)

| # | Slide title | Purpose and visual evidence | Speaker-note claim boundary |
|---:|---|---|---|
| 1 | OrchLang | Minimal title slide. One compact usage-trace motif connects secret alternatives to an observer. | Introduce the software review and name the bounded compiler plus separate experimental graph/checking tools. |
| 2 | Equal means can hide different usage laws | Two one-call secret alternatives. Branch A emits 1 or 3 output tokens with probability 1/2 each; branch B emits 2. Both means are 2. With a uniform prior, TV=1 and mutual information=1 bit in this fixture. | Exact result for the supplied finite kernel and one-call horizon. This is not a measured LLM distribution. |
| 3 | Aggregate totals can hide call order | At horizon 2, the modeled traces are `(1,3)` and `(3,1)`. Aggregate `(calls,input,output)` laws match (TV=0); ordered usage-trace TV=1. | Exact result for the authored kernel. This shows why the observer definition matters. |
| 4 | Three questions: budget, trace and channel | One-run ceiling, paired-run equality and distributional leakage sit on separate axes. | A unary maximum, pathwise relational claim, and finite probabilistic channel analysis are distinct results. |
| 5 | Four input paths keep claims separate | Architecture: bounded C++ AST compiler; JSON request-graph checker; bounded source bridge / restricted Python AST front end; finite-kernel tools for channels, bisimulation and exact trace laws. | Preserve separate formats and claims. The bridge is not a verified compiler; the JSON graph is an explicit model. |
| 6 | Equal caps still permit different realized usage | Editable counterexample: a secret selects public `x` or `y`; both have the same cap but different concrete lengths. | Static envelopes alone do not prove trace equality. The secret need not enter the prompt directly. |
| 7 | The bounded compiler compares resolved requests | Show resolved model contract, exact template bytes, ordered atoms, public guard identity and matched earlier call results. Include 15/15 balanced source-derived projections versus 8/15 on the frozen preceding version. | The source-derived set contains partial projections and authored bounded variants, not full framework ports. The relational rule is sufficient and incomplete. |
| 8 | The cyclic checker relates two control states | Editable product node `(pcL, pcR, R)`; public inputs seed `R`, and a matched call can add a result pair. | Product programs and relational reasoning are established foundations. The graph front end is separate from the C++ language. |
| 9 | Secret choices branch universally in the product | Show synchronized public tests, all secret successor pairs, exact matched call descriptors and aligned stops. | The rule rejects on any uncovered successor or mismatch; resource caps fail closed. |
| 10 | Productive cycles establish prefix equality | Two matched call chains return to the same product state/relation. | Coinductive closure gives equality of every finite usage prefix under \(\Omega\), not termination or a finite total-token/price/call bound. |
| 11 | Overwriting a result erases its old pairing | Timeline: first results `a↔x`; second call overwrites to `a↔y`; a later request using `a` vs `x` fails to match. Add the concrete single-grid usage witness. | The witness is one finite offline run. The method rule, not the sample, motivates killing stale relations. |
| 12 | A separate replayer rebuilds the graph closure | Source hash → certificate → independent product reconstruction; label what replay checks and what it trusts. | Replay checks closure under versioned graph rules. It does not mechanize the theorem or establish source/provider fidelity. |
| 13 | The source bridge admits a small OrchLang subset | 20 existing source candidates, 17 exported and 3 excluded for retry syntax; show explicit source→graph→replay path. | The source front end is experimental and fail-closed. Its provenance hashes do not prove translation correctness. |
| 14 | Source-level StateGraph examples reach LangGraph | Show Python AST extractor and the pinned runtime. Evidence: 20 front-end tests; 36 original-source runs; 30 accepted trace comparisons plus 6 expected-rejection value probes matched. | Authored restricted Python only. The source and frontend study is finite and does not establish general Python extraction. |
| 15 | The pinned backend found no trace differences on its grid | LangGraph 1.2.14: 888 offline runs, 4,528 call-event pairs, zero differences; 864 runs stopped and 24 hit the finite call horizon. | Deterministic offline oracle; not live provider behavior. Truncated executions do not establish termination. |
| 16 | Full request text was checked in bounded compiler stress | 264 synthetic C++ cases (144 accepted, 120 mutations rejected); 13,824 accepted secret comparisons; 0 request/usage mismatches; 66,240 per-call accounting checks; 117 mutation witnesses and 3 unknown. | The separate Python evaluator substitutes complete request text. Three finite no-witness cases remain unknown. This is not exhaustive language or provider validation. |
| 17 | The channel analyzer takes finite kernels as input | Show a finite exact outcome table, conditioning fields, fixed public store, explicit secret scenarios/prior, and finite call horizon. | It does not infer kernel probabilities from model calls, and it models only declared usage observations. |
| 18 | Dynamic programming keeps exact probability mass | Diagram call-depth states: control, values, contract ordinals, usage/trace, retained history; merge only identical complete semantic/resource states. Compare with no-merge DFS. | Exact rational arithmetic within explicit resource caps; an implementation proof sketch plus differential testing, not mechanized metatheory. |
| 19 | Bisimulation is sufficient, not complete | Finite transducer, bounded history, ordinal saturation at 33, exact partition refinement and visible usage labels. | A shared initial block proves ordered success-only usage-law equality at every finite horizon. A split is inconclusive. |
| 20 | A separate replayer checks the stable partition | 11 authored fixtures: 5 proved equal and 6 inconclusive; all 11 normal certificates replayed. 60 exact DP checks compared 120 scenario histograms; 11 fresh cap probes returned UNKNOWN. | Finite explicit state/kernel stores only. No cumulative runtime monitors, provider validity, termination or infinite-run law. Producer/replayer have 17/12 tests. |
| 21 | Exact trace equivalence resolves a split | One finite fixture: strong bisimulation splits successor states, but H=2 ordered TV is 0. Exact rational row-span closure proves all finite words, with a separate STOP/LIVE check. | A nonzero residual yields a finite distinguishing word. A cap returns UNKNOWN without a partial claim. This specializes established weighted-automata equivalence. |
| 22 | Prior work narrows the contribution | Editable comparison table: resource-aware IFC; RelCost; expected-resource and LLM-flow analysis; QIF; probabilistic trace equivalence and weighted automata; agent workflow checks; unary LLM workflow cost. | Attribute the row-span method to established automata equivalence. The applied delta is the finite LLM usage observer and independently replayed certificate, not a new general algorithm. |
| 23 | Relational claims depend on request and oracle contracts | Lay out public-store equality, request descriptors, complete modeled input accounting, finite kernels and shared outcome relation. | For real deployments, hidden request fields/state and provider serialization would need modeling. |
| 24 | The artifact makes its limits inspectable | Evidence-to-artifact map: reports, independent replay, tests, pinned backend, docs, MIT license; list omitted provider and source-fidelity claims. | Reproducibility artifacts support inspection; the manifest and tests are not a proof of all components. No venue decision is implied. |
| 25 | A narrow usage contract supports reviewable claims | Close the main story with static relations, productive-cycle prefixes, finite channels and exact all-finite-word equality for one split case. | Recap separate input models and assumptions, then transition to questions. |

## Appendix (6 slides, then the live demo)

| # | Title | Material |
|---:|---|---|
| 26 | Formal usage observation and coupling | Define event `(resolved contract,input usage,output usage)`, ordered trace, aggregate vector, and \(\Omega(M,k,Q)\); state the productive-cycle prefix result and exact STOP/LIVE word check. |
| 27 | Graph schema and certificate replay | Versioned graph fields, product node, worklist closure, successful replay and exact scope of independent verification. |
| 28 | Source support and exclusions | Source bridge and Python `StateGraph` subset, accepted/rejected syntax, final output/effect exclusions, and no verified translation theorem. |
| 29 | Evidence ledger and denominators | Keep source projections, full-text stress, cyclic graphs/LangGraph, finite probability kernels, stable-partition bisimulation and exact trace-law checks in separate rows. Bind final counts to their own reports. |
| 30 | Likely examiner questions | Honest concise answers on prior art, provider fidelity, cycles, strong-bisimulation incompleteness, exact trace equivalence, probability models and replay. |
| 31 | Selected references and related systems | Include Tzeng, weighted automata, APEX and labelled trace probability as established prior art. Label preprints and the author-reported Petri-net note clearly. |
| 32 | Live HTML demo | Last slide in the deck. Clickable `http://127.0.0.1:8765/`, local launch command, compare aggregate/ordered channels, then show the hidden-state fixture whose equal finite trace laws exceed strong bisimulation. |

## Main visual rules

- Keep ArchiveGate's editorial rhythm: cream/navy alternation, coral secret path, teal matched path, rust rejected path; simple titles and large evidence objects.
- Slides 2 and 3 are the paired opening hook. No abstract claims before those concrete finite examples.
- Distinguish exact rational results from approximate logarithm displays. The two hook slides use exact TV and equal/unequal observation laws; “1 bit” is the reported approximate display for the exact fixture.
- For all execution grids, label the oracle as offline and identify stopped versus truncated runs. Keep each denominator beside its claim.
- Put citations and source paths in each slide's speaker notes. Keep primary citations visible on the related-work slide.
- Keep slides 13–16, 19–21, and 24 separate; do not pool counts across studies. Slide 21 demonstrates one exact trace-law case while the appendix carries the extension's corpus totals.
- Explain that strong probabilistic bisimulation is sufficient but incomplete for this trace-law property. The rational row-span algorithm follows established probabilistic/weighted-automata equivalence methods; credit Tzeng, Kiefer et al. and APEX.
- End with the interactive demo. The examiner-question appendix comes before it so the live demo remains the final slide.

## Freeze gate

1. The final title, related-work framing, refreshed full reproduction manifest and all displayed evidence are frozen.
2. The strict builder passed against the manifest-bound reports. The editable PPTX has 32 slides, speaker notes and no package or layout findings.
3. All 32 slide renders and the PDF montage were visually inspected. The 32-page raster PDF has a working clickable link on the last slide; see `README.md` for why this host used the raster fallback.
4. The loopback demo URL and `python3 demo/server.py` command were verified by the demo owner.

## Independent publication assessment

`docs/FINAL_PUBLICATION_REVIEW.md` records the final independent assessment:
overall applied-project novelty 5.8/10 (4.5/10 initially), applied method
5.9/10 (3.5/10 initially), research-software quality 6.5/10 (4.0/10
initially), evidence 7.0/10 (2.0/10 initially), SCP OSP
originality/significance 6.2/10, equal-weight six-criterion candidate quality
7.4/10, target fit 8.5/10, and fundamental theory 3.0/10. These are internal
review aids, not journal ratings or acceptance probabilities. A novelty score
of 8 is not supported. Numeric assessment is for optional examiner Q&A; the
main deck intentionally stays score-free.
