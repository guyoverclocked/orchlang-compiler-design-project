# Related-work and novelty matrix

**Review date:** 9 October 2026. This is a targeted literature audit, not a
systematic review or a claim that every adjacent paper has been found. The
source inventory and claim boundaries are in
[`research/literature_sources.csv`](../research/literature_sources.csv).

## The property to compare

The property is relational: for two runs with the same public external values,
can changing secret state change the abstract per-contract usage trace? The
implementation tracks a content label for explicit data dependence, excluding
program-counter dependence; this is not a claim that branch-independent
contents are secret-independent. The sufficient rule compares ordered call
effects in secret-controlled alternatives under the same shared abstract
oracle Ω(c,k,Q), where `c` is the resolved model contract, `k` its call ordinal,
and `Q` the exact DSL template bytes plus ordered argument values. A prior-result
argument denotes the value from the aligned earlier call. The oracle contract
says equal keys produce equal abstract outcomes; equal ordinals with different
requests may have different outcomes.

This is not a provider-complete request identity: provider-added messages,
options, tool schemas, serialization, and actual response text are outside the
current abstraction. The cost theorem separately assumes per-call full abstract
request accounting `I <= ceil(UTF8_bytes(template)/d) + sum(argument bounds)`
in a common target-tokenizer unit, with no omitted overhead or serialization /
tokenizer-boundary interaction that exceeds the additive bound. This is not
implied by `d` alone. Nor is the property a unary worst-case token bound, an
expected resource bound, a quantitative leakage measure, prompt-injection
resistance, or timing/network-channel protection. The exact contract and
proof sketches are in [`FORMAL_CONTRACT.md`](FORMAL_CONTRACT.md).

## Matrix

| Work | What it establishes or implements | Overlap | Boundary that a paper must state |
|---|---|---|---|
| Ngo et al., *Verifying and Synthesizing Constant-Resource Implementations with Types*, IEEE S&P 2017, [DOI](https://doi.org/10.1109/SP.2017.53) ([author/open version](https://arxiv.org/abs/1801.01896)) | Combines automatic amortized resource analysis and information-flow typing; proves resource-aware noninterference for an explicit cost semantics. | Establishes that coupling IFC and resource security, and detecting resource side channels, are not new general ideas. | It analyzes program-defined costs. The OrchLang question is whether an invocation-level relation can be maintained when external outcome and usage are coupled by an explicit model/request oracle. That is an application delta, not a new NI principle. |
| Çiçek et al., *Relational Cost Analysis*, POPL 2017, [DOI](https://doi.org/10.1145/3009837.3009858) | Relational refinement analysis bounds differences between two execution costs. | Direct foundation for comparing resource use across paired runs. | It does not define a provider API request identity or an LLM billing trace. Numeric cost bounds remain valid where a sound cost contract exists. |
| Radiček et al., *Monadic Refinements for Relational Cost Analysis*, POPL 2018, [DOI](https://doi.org/10.1145/3158124) | Compositional refinement and cost-monad reasoning combines functional properties and cost relations. | Further limits any claim that compositional relational-cost reasoning is novel. | The contribution would need to be the invocation contract / sound abstraction for coupled external calls, not just syntax-tree signatures. |
| Barthe, D'Argenio & Rezk, *Secure Information Flow by Self-Composition*, IEEE CSFW 2004, [DOI](https://doi.org/10.1109/CSFW.2004.1310735); Barthe, Crespo & Kunz, *Product Programs and Relational Program Logics*, JLAMP 2016, [DOI](https://doi.org/10.1016/j.jlamp.2016.05.004) | Self-composition and product-program constructions reduce two-run properties such as noninterference to paired-program verification; the later comparison discusses loop synchronization and control-flow alignment. | Direct prior art for finite paired-control-state checking and loop alignment; the cyclic worklist is a concrete implementation of that established family. | A finite graph product reusing these constructions for resolved model requests and usage events is a tool/application delta, not a new relational verification or bisimulation theory. |
| Ngo et al., *Bounded Expectations*, PLDI 2018, [DOI](https://doi.org/10.1145/3192366.3192394) | Derives static upper bounds on expected resource consumption for probabilistic programs. | Proves stochasticity does not categorically rule out numeric resource analysis. | Expected cost is not pathwise equality of two usage traces. An LLM with no distribution or stable contract still prevents a useful numeric theorem, but this is a modeling limitation, not an impossibility result. |
| Dickerson, *Statically Bounding Resource Accumulation in LLM Agent Workflows: The Cost Case* (18 May 2026), [author-hosted paper](https://loom.technology/research/bounded-llm-cost/) | An author-hosted note states a Petri-net analysis for structural cumulative bounds on monotone resources, specializes it to token cost, and reports a live-model evaluation over 25 settings. No peer-reviewed venue or DOI was located in this targeted check. | Directly overlaps static unary cost bounds for LLM workflows. This makes it especially important not to sell an LLM token upper bound as the distinctive contribution. | It does not state a two-run confidentiality property or equal usage traces under a shared request-sensitive oracle. Its method/results are author-reported, not treated here as peer-reviewed or independently reproduced. |
| Mandel et al., *PPDL: LLM-Based Flows as Probabilistic Programs*, ICML 2026, [PMLR paper](https://proceedings.mlr.press/v306/mandel26a.html) | Peer-reviewed probabilistic language for multi-call LLM/tool flows; it explores trace/output distributions, compares strategies under a total-token budget, and logs token usage in its proof-repair case study. | The most important recent correction: probabilistic LLM workflow traces, token budgets, and usage logging are already adjacent. | PPDL does not claim a static, secret-conditioned usage-observer leakage guarantee or equal usage-trace distributions for secret alternatives. OrchLang must distinguish that property from PPDL's inference-scaling and output-uncertainty goals. |
| IBM Prompt Declaration Language, [official tutorial: `pdl_usage`](https://ibm.github.io/prompt-declaration-language/tutorial/) (unversioned documentation, checked 2026-10-09) | The runtime exposes accumulated model-call, prompt-token, and completion-token counters to a PDL workflow. | Usage collection is an existing workflow feature; token logging is not a new OrchLang contribution. | Runtime observability does not compute a secret-conditioned channel or prove source-level relational confidentiality. The tutorial describes a mutable framework runtime, not OrchLang's static byte-based request estimate. |
| Chothia et al., *Probabilistic Point-to-Point Information Leakage*, IEEE CSF 2013, [DOI](https://doi.org/10.1109/CSF.2013.20); Schröer et al., *Symbolic Quantitative Information Flow for Probabilistic Programs*, 2024, [DOI](https://doi.org/10.1007/978-3-031-75783-9_6) | The first defines quantitative leakage between arbitrary points in probabilistic programs, including nontermination and input. The second computes symbolic entropy, conditional entropy, KL divergence, and mutual information; it obtains exact symbolic expressions for discrete programs. | Both directly cover quantitative leakage measurement and symbolic probabilistic-program analysis. They rule out novelty claims for adding TV/MI or an arbitrary-point leakage observer in general. | OrchLang now implements a finite rational usage-channel analyzer and independent bounded DFS report replay. This is a workflow-specific integration, not a new QIF metric or general leakage model. |
| Larsen & Skou, *Bisimulation through Probabilistic Testing*, Information and Computation 94(1), 1991, [DOI](https://doi.org/10.1016/0890-5401(91)90030-6) | Foundational probabilistic transition-system bisimulation: states agree on labels and probability mass into each equivalence class. | Direct prior art for the exact strong probabilistic partition refinement used by the new all-horizon checker. | The contribution is the finite request/history/usage semantics and its executable sufficient test, not a new bisimulation theory. |
| Kamaleson, Parker & Rowe, *Finite-Horizon Bisimulation Minimisation for Probabilistic Systems*, SPIN 2016, [DOI](https://doi.org/10.1007/978-3-319-32582-8_10), [author-hosted paper](https://www.cs.ox.ac.uk/david.parker/papers/spin16fh.pdf) | Formalizes finite-horizon probabilistic bisimulation and gives partition-refinement and on-the-fly minimization algorithms for probabilistic systems. | Shows that finite-horizon bisimulation minimization is an established model-checking method; it reinforces that the all-horizon fixed-point extension is not a new algorithmic family. | OrchLang's all-horizon checker is an application to a finite usage-labelled LLM workflow model. It currently reports only a sufficient equivalence; a block split is inconclusive. |
| Anjum et al., *ProMCP: Profiling Token Flows and Latency Costs in Model Context Protocol–Based LLM Agents*, Findings of ACL 2026, [ACL Anthology](https://aclanthology.org/2026.findings-acl.1967/), [DOI](https://doi.org/10.18653/v1/2026.findings-acl.1967) | Profiles token and latency costs across a six-stage MCP communication pipeline, 20 servers, and 169 tools. | Directly adjacent to workflow token-cost observability and instrumentation. | It profiles actual runs; it does not prove source-level usage confidentiality. Its measured schema/planning overhead underscores why OrchLang's abstract request-cost premise must not be presented as provider-complete accounting. |
| Sun et al., *Position: Invisible Tokens, Visible Bills: The Urgent Need to Audit Hidden Operations in Opaque LLM Services*, ICML 2026, [PMLR paper](https://proceedings.mlr.press/v306/sun26bd.html) | Frames hidden token/call quantity inflation and model/tool quality downgrade in commercial opaque services and discusses audit strategies. | Establishes a timely accountability concern around provider-reported bills and hidden work. | It motivates a different observer and threat: provider execution/report integrity. OrchLang's abstract oracle and cost certificate do not attest hidden operations, reported token counts, or invoices. |
| Guo et al., *IMMACULATE: A Practical LLM Auditing Framework via Verifiable Computation*, [arXiv:2602.22700](https://arxiv.org/abs/2602.22700); Hoque et al., *Token Inflation: How Dishonest Providers Can Overcharge for Large Language Model Usage*, [arXiv:2605.30040](https://arxiv.org/abs/2605.30040); Chen et al., *The More It Says, the More You Pay: A Black-Box Audit of Provider-Side Token Inflation in LLM Services*, [arXiv:2609.20370](https://arxiv.org/abs/2609.20370) | These arXiv preprints address verifiable provider-execution audits, provider-side token-count inflation, and black-box detection of output-length inflation, respectively. | They are close enough that “LLM token usage auditing” is too broad as a description of OrchLang. They also highlight that trusted provider reports and actual billed units cannot be inferred from source-level analysis. | All three are cited as preprints as checked on 9 October 2026. Their reported findings are author claims, not independently validated here. Their focus differs: they audit provider/report behavior, whereas OrchLang checks a source-level relational property under a declared abstract oracle. |
| Zhang et al., *Persistent Billable State: Denial-of-Wallet Attacks and Defenses in Tool-Calling LLM Agents*, [arXiv:2609.28585](https://arxiv.org/abs/2609.28585) | Studies how retained tool returns can be re-ingested and billed across future calls, with host-side controls for prompt mass and cumulative spend. | Directly adjacent to multi-call state and recurring token cost in agent workflows. | This is a preprint and its target is host-side denial-of-wallet and billable-context management, not confidentiality of usage traces across secret states. Do not frame cost accumulation or agent state as an unaddressed problem. |
| Cognetta & Okazaki, *Tokenization as Finite-State Transduction*, Computational Linguistics 51(4), 2025, [ACL Anthology](https://aclanthology.org/2025.cl-4.2/), [DOI](https://doi.org/10.1162/coli.a.23) | Gives a finite-state transduction account of tokenization and shows BPE and WordPiece are efficiently representable as finite-state transducers. | Tokenizer conversion has formal foundations; a max-vocabulary-byte or tokenizer-transducer idea does not begin from an unstudied formalism. | A possible practical extension would compose version-pinned source decoding, exact request serialization, and target token counting to certify a cross-model request bound. That composition is only a candidate direction; it is not implemented or validated in OrchLang. |
| Köpf & Basin, *An Information-Theoretic Model for Adaptive Side-Channel Attacks*, CCS 2007, [DOI](https://doi.org/10.1145/1315245.1315282) | Quantifies an attacker's remaining uncertainty under adaptive side-channel observations. | Supports defining the observer and considering leakage magnitude rather than using “side channel” loosely. | Quantitative leakage and equality of billed traces are different properties; the latter is an all-pairs sufficient guarantee for a chosen observation. |
| LMQL, *Prompting Is Programming*, PLDI 2023, [DOI](https://doi.org/10.1145/3591300); APPL, ACL 2025, [paper](https://aclanthology.org/2025.acl-long.63/); IBM PDL, [preprint](https://arxiv.org/abs/2410.19135) | Prompt/query or workflow languages support constraints, Python integration, tools, control flow, and multi-call patterns. | A new DSL or structured prompt syntax is not itself novel; these are suitable workflow sources and comparisons. | None of these cited contributions is a static proof of equal modeled usage traces under a shared oracle. PDL is listed as a preprint in this audit; APPL and LMQL have peer-reviewed venue records. |
| CaMeL, [arXiv:2503.18813 v2](https://arxiv.org/abs/2503.18813); FIDES, [arXiv:2505.23643 v2](https://arxiv.org/abs/2505.23643) | Agent defenses use explicit control/data flow, capabilities, confidentiality/integrity labels, or dynamic taint/planner enforcement. | Strong neighbors for agent IFC and tool-flow security. They make “security for LLM agents is only prompt filtering” untenable. | Their focus is preventing unauthorized data/tool flows and prompt injection, not equal per-model billing traces. The cited versions are arXiv preprints, not treated here as peer-reviewed publications. |
| AgentFlow, [arXiv:2608.22868 v1](https://arxiv.org/abs/2608.22868); Agentproof, [arXiv:2603.20356 v1](https://arxiv.org/abs/2603.20356) | AgentFlow describes a policy language, runtime reference monitor, and bounded SMT verifier. Agentproof extracts graphs from four frameworks and checks structural/temporal policies statically and at runtime. | Directly refutes “no static workflow verification exists” and “agent security is runtime-only.” | The stated properties are policy/data-flow or graph/temporal properties, not request identity or billing noninterference. Both are cited as preprints as checked on the review date. Agentproof's 18 workflows are author-constructed, not a prevalence sample. |
| Ghost in the Agent, [arXiv:2604.23374](https://arxiv.org/abs/2604.23374); Token Budgets, [arXiv:2606.04056](https://arxiv.org/abs/2606.04056) | Adjacent proposals describe offline trace/provenance audits and affine/runtime token-budget accounting, respectively. | Show that agent flow audits and token budgeting are active, adjacent problems. | Offline audit is not static pre-execution proof; resource budgeting is not confidentiality noninterference. Both are cited as preprints, and author-reported catalogs/results must not be treated as independently replicated evidence. |
| Weiss et al., USENIX Security 2024, [paper](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss); Zhang et al., *Time Will Tell*, [arXiv:2412.15431](https://arxiv.org/abs/2412.15431) | Demonstrate prompt/token-length inference over encrypted traffic and timing/output-token correlations, respectively. | Establish that token-length-derived observations can matter for security. | Network traffic, latency, and provider invoices are distinct observers. *Time Will Tell* is cited as a preprint in this review; neither study establishes an OrchLang billing leak or guarantee. |

### Novelty and project assessment (not acceptance probabilities)

Scale: 0 means no incremental contribution in that dimension; 5 means a
focused contribution built largely from established ideas; 10 means a major
field-level advance. “Earlier” is this review's assessment of the prior draft;
“current” is the October 9 state after the implementation and evidence update.
The historical project self-rating is 4.5/10 overall; the current subjective
overall assessment is 5.5/10. That overall score is not the arithmetic mean
of the dimensions.

| Dimension | Earlier | Current | Why |
|---|---:|---:|---|
| Fundamental theory | 2.5/10 | 3/10 | The oracle and composition sketches specify a useful specialization, but resource-aware NI, relational cost, and probabilistic resource analysis are established. The argument is not mechanized. |
| Applied analysis method | 3.5/10 | 5.5/10 | Resolved model contracts, abstract request descriptors, ordinal alignment, and matched prior-result chains now support balanced secret arms that the baseline rejects. This is the principal gain. |
| Compiler/artifact | 4/10 | 6/10 | The compiler integrates resolved-contract and request-aware relational checks, certificates/reports, MIT licensing, citation metadata, pinned source manifests, and a separate source-cost auditor. An experimental cyclic graph frontend has an independently implemented certificate replayer and offline installable wheel; a bounded source bridge gates exact source/compiler snapshots. There is no provider adapter or independent full-source relational/IFC proof checker, and immutable public release is pending. |
| Evaluation | 2/10 | 5/10 | The two offline mock modes exercise 15 bounded projections with authored balanced/unbalanced variants and baseline comparisons. A separate generated-AST/full-text reference study covers 264 cases and 13,824 accepted paired comparisons. The cyclic grid checks 1,400 graph runs and 800 secret pairs; its 3,000-case property probe reuses the producer's reference evaluator. The source bridge exports 17 of 20 existing OrchLang files and has zero differences in 360 finite secret-trace comparisons. These are still synthetic, finite checks, not provider validation or independent application studies. |
| Research presentation | 2.5/10 | 5.5/10 | The claim is now bounded around abstract shared-oracle trace equality, while numeric/probabilistic and agent-verification neighbors are acknowledged. Deployment claims remain limited. |

In **each mode separately** (ordinal and request-sensitive), the frozen result
reports 1,500 base executions with zero component-bound violations, 2,250
balanced pairs with zero usage-observation mismatches, 2,250 unbalanced
extra-call pairs with all 2,250 mismatching, 30 source cost reports checked,
and 15 balanced accepts versus 8 for the baseline. All 15 unbalanced variants are rejected by
the new compiler. Do not aggregate these two deterministic mock grids as
independent trials. The separate Python source-cost auditor checks report consistency; it does
not verify relational or information-flow proofs. The final reproduction
record binds the results to compiler SHA-256
`5bae3be94e9b7d747728965e2562d06a9844d47b28f871c6fe44dcb6f0a7aa43`, and
records 111/111 optimized C++ tests, sanitizer success, 19/19 source-cost-
auditor tests, and 29 expected stages (`audit/final/manifest.json`; the auditor
log is `audit/final/auditor-tests.log`). The 15 cases are bounded authored
projections from three DSL frameworks, not production ports. The separate
catalog contains 17 candidate files from four repositories; that is not 17
executed ports.

## Defensible contribution statement

> We implement a deliberately incomplete static sufficient check for equality
> of per-contract usage traces across secret-controlled alternatives in a
> bounded workflow language. The check compares resolved model contracts and
> abstract request descriptors (exact template bytes plus ordered argument
> values), including references to aligned earlier results, under a shared
> oracle keyed by contract, call ordinal, and abstract request. The result is
> conditional on this abstraction and the cost assumptions; it is not a claim
> about provider wire requests, invoices, timing, or prompt-injection resistance.



## Stochastic-kernel corollary and prior art

The implementation's primary theorem uses one deterministic shared oracle, so
paired executions under that theorem share the same modeled outcomes. A
separate **conditional corollary** is available if a provider or runtime is
specified by a secret-independent conditional kernel over complete call
outcomes, keyed by the same resolved contract, ordinal, exact modeled request,
and complete relevant history. When the relational source argument keeps
those keys and histories aligned, couple each matched pair of calls by the
identity coupling. Each side retains the kernel's marginal law and the
coupled usage traces agree almost surely. Therefore independently sampled
runs have the same marginal usage-trace distribution; they need not have
identical sampled responses or random seeds.

This implication is ordinary probabilistic relational reasoning. Barthe et
al. define coupling witnesses with prescribed marginals and use them to derive
relations between probabilistic executions; Barthe and Hsu survey how these
proofs establish equivalence and other relational distribution properties.
[LPAR 2015](https://doi.org/10.1007/978-3-662-48899-7_27), [Cambridge 2020
chapter](https://doi.org/10.1017/9781108770750.006), and [POPL 2017 product
programs](https://doi.org/10.1145/3009837.3009896) are primary sources.
Their work supports the proof technique and makes clear that the corollary is
not new coupling theory.

The conditional statement requires equality of the **full** outcome kernel at
each matched history, including response contents, usage, errors/status, and
metadata that can influence later requests or control. It requires provider
state that affects the law to be included in the history and aligned, or else
the assumption fails. It assumes neither independent calls nor pathwise
equality between independently sampled runs; arbitrary call dependence may be
represented by the conditional history. A provider's real law, hidden state,
request serialization, and receipt visibility have not been measured here.
The compiler and graph checker do not encode or verify such kernels, so this
is a semantic consequence conditional on a provider contract, not evaluated
provider evidence or a new implementation feature. For unbounded productive
cycles the conclusion is finite-prefix distribution equality only, not a
finite whole-run cost bound.

Describe the result as an application/specialization of relational cost and
information-flow reasoning. The distinctive engineering question is whether
request identity and call alignment can be preserved compositionally across
secret alternatives in multi-call workflows when usage is controlled by an
external stochastic oracle. Do not claim the absence of numerical or
probabilistic alternatives.

## Reviewer objections to anticipate

1. **“This is just constant-resource typing with tokens.”** Agree about the
   lineage. Contrast only the external effect contract: an invocation is
   identified by a resolved model contract and abstract request descriptor,
   with outcomes related by a shared oracle. Show which call patterns this
   admits or rejects relative to a cost-annotated baseline.
2. **“The shared oracle makes the result tautological.”** Specify the key,
   coupling, equality notion, retries, and assumptions; prove that equal
   signatures imply matched keys at every matched call. Compare this property
   with distributional equality/approximate leakage and explain why the
   application needs this pathwise guarantee.
3. **“Request identity is not provider-complete.”** Agree. The implemented
   descriptor is exact only within the DSL abstraction: template bytes and
   ordered argument values. It omits provider serialization, tools/options, and
   real response text; the theorem must not imply otherwise.
4. **“Priors already cover stochastic LLMs.”** Cite PPDL precisely: it handles
   uncertainty propagation in LLM flows, which is important adjacent work, but
   does not claim equal usage traces under the coupling above. Do not dismiss
   probability as inapplicable.
5. **“The evaluation is synthetic.”** State that mock outcomes and source
   classifications are authored. The only executed security mutation appends
   one extra call in one secret-controlled arm per pattern. The source catalog
   samples public examples to test expressibility/shape coverage, not deployed
   applications or independent evaluations. A separate provider-backed study
   can measure realism without being confused with the theorem.
6. **“It does not defend an agent.”** Narrow the system claim to token-usage
   confidentiality. Compare with CaMeL/FIDES/AgentFlow/Agentproof and avoid
   calling the system prompt-injection resistant or a complete agent security
   solution.

## Importance and deployment relevance

The problem has **moderate importance** for workflows where secret-dependent
control or content can affect model choice, request size, call count/order, or
retries and an unauthorized observer can see per-run/per-contract usage. Token
length and timing attacks support the relevance of related observables, but do
not establish that ordinary invoices reveal one workflow's trace.

Current deployment relevance is **limited**. OrchLang is a static-method
prototype with an offline mock, no provider adapter, no real serialized-request
accounting, and no usage-receipt study. The theorem relies on its explicit
abstract oracle and the per-call cost premise; it does not certify provider
behavior, tariffs, caching, or billing records.
