# Fifteen-minute review script

**Target:** about fifteen minutes including the final local demo. Slides 26–31 provide technical detail for questions. Tie displayed results to the refreshed trace-equivalence report and reproduction manifest; confirm the local demo server before presenting.

## Main story

### 0:00–0:15 · Slide 1 — OrchLang

I’ll separate a one-run resource bound, equality of usage traces across secret alternatives, and information in a finite usage distribution.

### 0:15–0:55 · Slide 2 — Equal means can hide different usage laws

The secret chooses between two one-call alternatives. For template A, output usage is one or three with probability one half each. For template B it is exactly two. Each call has one input token and the same model contract and cap, so expected output usage is two in both cases. Under this finite kernel the supports are disjoint: total variation is one. With the uniform prior, the secret is recoverable from this observation and the reported mutual information display is one bit. This is an exact fixture result, not a measured LLM distribution.

### 0:55–1:30 · Slide 3 — Aggregate totals can hide call order

The next fixture makes two calls in each branch. One produces output usage one then three; the other produces three then one. Both stop with two calls, input total two and output total four. Aggregate TV is zero; ordered usage-trace TV is one. The observation definition determines what the checker can distinguish.

### 1:30–1:55 · Slide 4 — Three questions: budget, trace and channel

A unary cost bound limits one run. A relational rule compares two runs that share public inputs and an outcome relation. A channel analysis computes the observation law under explicit probabilities. These are separate guarantees and data sources.

### 1:55–2:15 · Slide 5 — Four input paths keep claims separate

The bounded compiler accepts OrchLang source. A distinct Python checker consumes finite-control JSON graphs with productive call cycles. A bounded bridge and restricted Python AST front end connect selected sources to graph replay and offline execution. The finite-kernel path contains exact channel enumeration, strong bisimulation and exact trace equivalence. A pinned LangGraph runtime evaluates authored graphs under an offline response session. No component proves an arbitrary provider workflow end to end.

### 2:15–2:40 · Slide 6 — Equal caps still permit different realized usage

The rejected C++ example declares two public text inputs with the same maximum. A secret selects which input reaches the model. Their concrete lengths differ, so their realized input usage can differ despite equal static envelopes. The secret itself does not appear in the request.

### 2:40–3:10 · Slide 7 — The bounded compiler compares resolved requests

Each call retains resolved provider and model identity, output cap, optional price metadata, exact template bytes and ordered typed arguments. Public guards and earlier matched call results also have identities. The rule requires secret alternatives to keep a matched call signature. It accepts 15 of 15 balanced source-derived projections versus 8 of 15 in the preceding compiler. The study uses partial projections and authored variants, not full framework ports. The check is sufficient and incomplete.

### 3:10–3:35 · Slide 8 — The cyclic checker relates two control states

The graph checker builds product work items `(pcL,pcR,R)`. Equal public inputs seed `R`. Calls match on complete modeled request descriptors. The shared outcome assumption justifies relating returned values. This applies established product-program reasoning to model-call events.

### 3:35–3:55 · Slide 9 — Secret choices branch universally in the product

The product explores every pair of secret successors. Matching public predicates over related values synchronize. Calls require equal contract, template and ordered atoms. Stops must align. Any reachable mismatch rejects, and a product cap cannot yield acceptance.

### 3:55–4:20 · Slide 10 — Productive cycles establish usage-prefix equality

In the accepted cycle, both sides make matched calls and return to the same product state with the same relation. This closure supports every finite usage prefix under Ω. It does not establish termination or a finite cumulative token, price or call-count budget.

### 4:20–4:45 · Slide 11 — Overwriting a result erases its old pairing

The first result pair is `a↔x`. The next call overwrites `a` and writes `y`, so the live relation is now `a↔y`. A later request using `a` versus stale `x` has no justified match. The sample usage difference is one finite offline witness.

### 4:45–5:05 · Slide 12 — A separate replayer rebuilds the graph closure

The producer emits reachable product nodes and edges. The replayer strict-parses the original graph, reconstructs reachable source and product states, then verifies every relation, local rule and required successor. It checks the report under versioned graph rules, not a metatheory proof or source fidelity.

### 5:05–5:25 · Slide 13 — The source bridge admits a small OrchLang subset

The bridge tried 20 existing source programs; 17 exported and three retry examples were explicitly excluded. Across those exports, 720 source/graph runs and 360 secret trace pairs matched. The adapter uses its own narrow parser. Hashes bind the generated artifacts but do not prove the translation.

### 5:25–5:50 · Slide 14 — Source-level StateGraph examples reach LangGraph

The Python front end accepts a restricted static graph builder. Its finite study ran each original source 36 times. Thirty accepted source/backend trace comparisons and six expected-rejection value probes matched. The frontend has 20 tests. This does not validate unrestricted Python or every LangGraph construct.

### 5:50–6:15 · Slide 15 — The pinned backend found no trace differences on its grid

LangGraph 1.2.14 ran six authored fixtures and seventeen admitted source exports: 888 executions and 4,528 compared call events, with zero differences. Of those executions, 864 stopped and 24 hit the call horizon. The deterministic offline oracle does not represent live provider behavior; the truncated runs make no termination claim.

### 6:15–6:45 · Slide 16 — Full request text was checked in bounded compiler stress

There are 264 generated cases: 144 balanced positives and 120 controlled mutations. A separately implemented Python reference substitutes full request text. It ran 24,192 reference executions, compared 13,824 accepted secret assignments and checked 66,240 calls without a request or usage mismatch. It found witnesses for 117 rejected mutations. Three retry mutations had no finite witness and remain unknown. These are synthetic AST cases, not provider or full-language coverage.

### 6:45–7:10 · Slide 17 — The channel analyzer takes finite kernels as input

The exact channel tool receives a graph, finite rational outcomes, a fixed public store, explicit secret scenarios and priors, an observer and a call horizon. It models successful outcomes only. It does not fit a provider distribution.

### 7:10–7:35 · Slide 18 — Dynamic programming keeps exact probability mass

The DP state includes control, values, contract ordinals, accumulated usage, ordered trace, retained history and resource work. It merges only complete states that are equal in every future-relevant and observable field. Rational probability mass distributes across each finite kernel outcome. A separate no-merge DFS computes path probabilities as a differential check. State, precision and work caps return unknown.

### 7:35–8:05 · Slide 19 — Bisimulation is sufficient, not complete

The bisimulation checker constructs a finite semantic transducer for one fixed public store and explicit secret scenarios. It retains control, initialized values, contract ordinals saturated at 33, and bounded complete-event history. That saturation follows from this version's maximum kernel ordinal and history tests of 32. Exact partition refinement compares terminal status, visible usage labels and probability into successor blocks. A shared initial block proves equal ordered success-only usage laws at every finite call horizon. A split is inconclusive, which the next slide will address.

### 8:05–8:25 · Slide 20 — A separate replayer checks the stable partition

The checker and replayer are separate implementations. Replay reconstructs the finite transition system and independently checks the supplied stable partition. Across 11 fixtures, five prove equal laws and six are inconclusive; all 11 normal certificates replay. The five proved cases have 60 exact DP checks at six horizons and two observers, comparing 120 unit-mass scenario histograms. Eleven fresh state-cap probes returned UNKNOWN. The producer and replayer have 17 and 12 tests. The result excludes cumulative runtime monitors, provider validity, termination probabilities and infinite-run laws.

### 8:25–9:10 · Slide 21 — Exact trace equivalence resolves a split

The authored `trace_equal_not_bisimilar` fixture shows a split that strong bisimulation cannot resolve. In one secret path, the first response chooses the next request. In the other, the workflow uses the literal `pink`. Both produce ordered output-count words `(1,1)` and `(1,3)` with probability one half, so the H=2 ordered TV is zero. The strong-bisimulation split is a fresh analyzer comparison, not independently replayed in this study. The exact checker starts from the signed difference of the two scenario states and closes its rational span under every observed usage label. It compares stopped and still-live mass for each basis row. If all differences are zero, every finite word agrees for this supplied model. A nonzero residual returns a finite word witness. Resource caps return UNKNOWN without a partial claim. The independent replayer reconstructs the semantic closure and checks the span certificate. This specializes established weighted-automata equivalence, not a new general algorithm.

### 9:10–9:40 · Slide 22 — Prior work narrows the contribution

Resource-aware IFC and RelCost already handle resource observations relationally. PPDL models uncertain multi-call LLM/tool flows. QIF and finite trace analysis are established. Tzeng-style probabilistic-automata equivalence, rational weighted automata and APEX establish prior row-span methods for finite words. AgentFlow and Agentproof include static workflow verification. A recent author-reported Petri-net note covers unary cumulative LLM workflow costs. OrchLang applies these foundations to an ordered successful-call usage alphabet and adds a replayable certificate path. This is not new general theory.

### 9:40–10:05 · Slide 23 — Relational claims depend on request and oracle contracts

The relational result requires equal public identities, full modeled request equality, compatible accounting and a shared complete-outcome relation. The finite probability tools require that the supplied kernel captures relevant state. Hidden provider, account, cache, routing, serialization or tokenizer behavior would need to enter a deployment model. We have not established those facts for a provider.

### 10:05–10:20 · Slide 24 — The artifact makes its limits inspectable

The repository separates each tool, report and test suite. The independent replayers check specific certificates, and the reproduction manifest binds exact evidence. MIT licensing, source paths and reproduction commands are present. Reproducibility supports inspection; it does not guarantee correctness or imply a publication decision.

### 10:20–10:35 · Slide 25 — A narrow usage contract supports reviewable claims

The software checks bounded traces, extends prefix reasoning to a modeled cycle, and analyzes finite channels. The exact row-span result closes one concrete case that bisimulation leaves inconclusive. I’ll use the appendix for questions and close with the demo.

## Appendix prompts

### 10:35–11:00 · Slide 26 — Formal usage observation and coupling

An event is `(resolved contract,input usage,output usage)`. The aggregate observer groups counts and sums by contract plus a stop bit. The ordered observer preserves order and a stop or truncation bit. Static cycle reasoning uses pathwise Ω; channel analysis uses finite probabilities; bisimulation is sufficient, while exact row-span checks finite-word equality by comparing stop and live mass.

### 11:00–11:25 · Slide 27 — Graph schema and certificate replay

The graph schema has typed public and secret inputs, resolved contracts, result registers, ordered calls and finite control states. Call-free cycles reject. Product certificates contain the complete reachable closure. Independent replay checks that closure under the declared rules; it does not prove graph-source correspondence.

### 11:25–11:55 · Slide 28 — Source support and exclusions

The OrchLang adapter admits text inputs, mock models, text prompts and calls, selected guards, and a final public output. It rejects retries, tools, effects, releases and unsupported expressions. The Python extractor requires a static graph builder, synchronous call functions and bounded state, and rejects dynamic control, reducers, fan-out and effects. Source coverage remains narrow.

### 11:55–12:20 · Slide 29 — Evidence ledger and denominators

Source-derived compiler patterns, full-text stress, graph and LangGraph runs, finite-kernel channel analyses, bisimulation and exact trace-law studies have different denominators. They use separate inputs, oracles and observers. Read each count beside its report and never add study totals.

### 12:20–13:10 · Slide 30 — Likely examiner questions

**Is this a new general theory?** No. It applies established relational and probabilistic methods to a specific usage contract.  
**Do productive cycles prove a total budget?** No. They establish finite trace prefixes.  
**Does all-horizon bisimulation prove provider behavior?** No. It proves a sufficient equality for finite supplied stores and kernels.  
**What does a partition split mean?** Inconclusive by itself. Exact trace equivalence can prove some split cases equal or return a finite witness.  
**Is the row-span method new theory?** No. Tzeng and weighted-automata work established finite-word equivalence methods. OrchLang specializes the observer and replayable certificate.  
**Does the channel tool estimate LLM probabilities?** No. The user supplies finite exact kernels.  
**What does replay verify?** Reconstructed finite semantics and the certificate's exact span under versioned rules.  
**Why report aggregate and trace separately?** Aggregation can discard call order that a per-event observer retains.

### 13:10–13:35 · Slide 31 — Selected foundations and adjacent systems

The references include resource-aware IFC, RelCost, probabilistic resource analysis, PPDL, QIF, Tzeng's probabilistic automata algorithm, weighted automata and APEX. AgentFlow and Agentproof are preprints in the review snapshot. The Petri-net note is author-reported and unrefereed. Full links are in the slide notes and source register.

## 13:35–15:00 · Slide 32 — Live HTML demo

Run `python3 demo/server.py` from the repository root and open the loopback link. Select the aggregate-order fixture and keep the public store fixed. Run both secret scenarios. The aggregate observer gives the same totals; the ordered observer distinguishes `(1,3)` from `(3,1)`. Open the equal-mean fixture to show expected output usage two on each side with TV one. Finish on `trace_equal_not_bisimilar`: the strong-bisimulation panel shows an inconclusive analyzer comparison, H=2 ordered TV is zero, and exact row-span equivalence proves every finite ordered usage-word law for the supplied kernel. Show the independent replay status for the exact certificate. The interface calls only local analysis tools and offline fixtures.

## Untimed Q&A note — publication fit

The final independent review rates overall applied-project novelty 5.8/10, applied method 5.9/10, research-software quality 6.5/10, evidence 7.0/10, SCP OSP originality/significance 6.2/10, the equal-weight six-criterion candidate-quality proxy 7.4/10, target fit 8.5/10, and fundamental theory 3.0/10. These are internal review aids, not journal ratings or acceptance probabilities; a novelty score of 8 is not supported. Keep them in Q&A only, not on the main slides. See `docs/FINAL_PUBLICATION_REVIEW.md`.
