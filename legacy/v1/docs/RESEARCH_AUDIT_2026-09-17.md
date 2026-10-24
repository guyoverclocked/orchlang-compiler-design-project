# OrchLang research and branch audit

Date: 17 September 2026. Audited branch: `v2-static-certification`, commit `fd9d8bc`, against `main` at `077dd06`. Four branch commits; 125 changed files. Working tree was clean at the start. This audit adds evidence and this report; it does not repair or rewrite the compiler or existing paper.

## Verdict

**Do not submit the current manuscript as a soundness/certification research paper.** It is a substantial undergraduate compiler artifact and a useful research prototype, but the principal novelty claim overlooks directly relevant prior work, the cost-channel theorem is false as stated, and new programs contradict implementation-level cost guarantees.

This is a judgment of the current evidence, not a prediction that the project cannot become publishable. A corrected, carefully scoped tool/experience or workshop paper is a plausible near-term outcome. A credible journal letter needs one distinct, correct technical result. A strong full journal paper needs a new analysis or deployment result, proper semantics, and independent evaluation. A shorter format does not relax correctness or originality.

The most promising continuation is **relational token-resource analysis for bounded LLM workflows**, explicitly addressing opaque stochastic calls, tokenizer boundaries, and the observations exposed by usage accounting. Merely adding taint propagation to structural upper bounds is insufficient novelty.

## What was actually verified

Built the checked-out C++ sources afresh using GCC 16.1.0, C++17, `-Wall -Wextra -pedantic -O2`. The GCC 6.3 executable on the default PATH is too old; the newer installed toolchain was located using the repository's `.envrc`. No compiler warnings were emitted. GNU make was unavailable on PATH, so equivalent direct compiler invocations and example checks were used; this was not a literal `make check` run.

| Check | Fresh result |
|---|---|
| Existing regression executable | 83/83 passed |
| Valid/invalid/boundary example acceptance checks | 32/32 matched expectations |
| Valid example certificates emitted and JSON parsed | 8/8 |
| Existing cost suite | 23 workflows, 4,600 executions |
| Certified-total violations in that suite | 0 |
| Flat-baseline violations | 621/4,600 = 13.5%, on 8 workflows |
| Slack against sampled peak | Median 1.23x, range 1.02–3.01x |
| Existing security fixtures | 13 unsafe rejected; 13 safe accepted |
| Timing of 36 certifications | 0.31 s; 8.7 ms each, including startup |
| New audit probes | Accepted counterexamples described below |

Thus the recorded benchmark numbers are reproducible. Their interpretation as broad validation is not. The timing difference from approximately 6 ms is not itself a defect; neither measurement isolates analyzer time or establishes a scaling law.

Evidence is in `audit/2026-09-17/`: `tests.txt`, `benchmark/evaluation.txt`, `findings.json`, `probes.txt`, `paired.txt`, five `.orch` fixtures, `paired.cpp`, `reproduce.py`, and `build.ps1`. `reproduction.txt` preserves the initial full harness output; `probes.txt` and `findings.json` include the corrected output-component probe. Run `powershell -File audit/2026-09-17/build.ps1` from this checkout to rebuild and reproduce on this installed Windows toolchain. The Python harness can also be pointed at another fresh executable.

This was a targeted audit of the new analyses, runtime, certificates, claims, and evaluation, not an exhaustive proof of the compiler, a paid-provider experiment, or a patentability opinion. No absence-of-prior-work search can establish universal originality. Recent preprint descriptions below are author claims, not independently replicated results.

## Blocking findings

### 1. Equal upper bounds do not imply cost noninterference

**Priority P1.** `src/cost_analyzer.cpp:73` accepts secret branches whenever their total upper bounds agree. `docs/PAPER.md:452` claims equal actual resource usage under the same model choices. The premise does not imply the conclusion.

The accepted `equal_bounds.orch` chooses between `p(x)` and `p(y)` using a secret. Both public inputs have a bound of 100, but their actual lengths need not agree. Both branches have the same model and template and certify at 111 tokens.

The paired harness analyzes this source once, holds the seed and public inputs fixed, and varies only the secret token count between 0 and 1. It records **15 versus 53 total tokens**, with **zero output tokens in both calls**. These are identical model-level output choices. The secret selects public inputs of different actual lengths.

The mock has no supplied-store API, so the harness injects the two secret initial values by changing the secret declaration's runtime initializer after analysis. Both values satisfy the original declared bound of 1; neither the analyzer nor interpreter implementation is altered. This is audit instrumentation, not a claim that the ordinary CLI exposes paired secret stores.

Even without that instrumentation, a mathematical counterexample is immediate: fix public input lengths at 14 and 52, choose model output length 0 in both executions, and change the secret guard. Equal maxima coexist with unequal observations. The current rule is a heuristic for unequal declared maxima, not a security proof. Unequal maxima also do not establish a definite leak if differences concern unreachable paths or loose annotations.

**Repair:** withdraw Theorem 2-prime and the “balancing upper bounds fixes leakage” claim. Define an observation model and a relational analysis of two runs. Track exact symbolic cost relationships or require a proved constant-resource discipline; equality of intervals or interval endpoints is also insufficient. Decide whether the observer sees total tokens, input/output counts, model identities, prices, or the whole request trace. Equal token totals alone cannot protect model-specific monetary bills.

### 2. The guaranteed/estimated branch split is not a componentwise bound

**Priority P1.** `src/cost_analyzer.cpp:24` chooses the entire pair belonging to the arm with the larger total. That preserves a scalar total upper bound, but not upper bounds on each component.

In `split.orch`, one arm has `(output=1, input=201)` and the other `(output=100, input=1)`. The certificate reports guaranteed output 1, estimated input 201, total 202. Seed 2 executes the second arm and consumes **20 output tokens**, exceeding the alleged guaranteed component. The overall total remains below 202: this finding invalidates the split guarantee, not this example's total.

Changing the tokenization assumption can also change which arm wins and therefore change the reported guaranteed component. A straight-line regression asserting otherwise does not cover branch selection.

**Repair:** maintain componentwise maxima, or preserve path-indexed alternatives with a separately named total bound. State the tradeoff explicitly: the sum of independent maxima can be looser than the maximum total.

### 3. Literal accounting disagrees between analyzer and runtime

**Priority P1.** `src/semantic_analyzer.cpp:139` assigns Boolean literals one token; string literals use their unquoted value. `src/interpreter.cpp:136` estimates `expressionToString`, including string quotation marks and the spelling of Boolean literals.

At the default ratio, `literal.orch` certifies **2 tokens**, then consumes **3** at seed 1. `boolean.orch` certifies **3**, then consumes **4** at seed 1. Both certify successfully. These are implementation/specification consistency failures under the project's own accounting model; no hostile provider or real tokenizer is involved.

**Repair:** define canonical argument serialization, use it consistently, and test all expression kinds at tokenization boundaries. An independently implemented oracle is still necessary to catch shared mistakes.

### 4. Runtime scope disagrees with static scope

**Priority P1.** Static analysis uses nested scopes, but `src/interpreter.cpp:75` stores values, models, and prompts in flat maps. Entering and leaving a branch does not restore outer bindings.

In accepted `shadow.orch`, a branch locally shadows model `m` with a 1,000-token model. A later outer-scope call is statically charged against the original 1-token model. Seed 3 executes using the lingering inner model and consumes **348 total tokens against a certificate of 2**.

**Repair:** implement scoped environments or resolved binding IDs for every binding kind. Add shadowing and nested/repeated-block differential tests. This is a runtime refinement failure, not a mathematical failure of addition/max/multiplication for a correct reference semantics.

### 5. Security theorems and runtime observations are incomplete

Theorem 2 quantifies over two executions but does not constrain the randomness of their model calls. Even a public-only model call can return different values in two executions. A deterministic oracle, an appropriate coupling, or equality of output distributions must be specified. “Same model choices” is added only to Theorem 2-prime, and does not rescue finding 1.

The draft supplies a semantic judgment and proof sketches, rather than a complete operational semantics and all induction cases. The mock does not represent text values, records only tool names rather than tool argument values (`src/interpreter.cpp:198`), and ignores output statements (`:205`). It therefore cannot validate the claimed equality of effect arguments and returned outputs.

Model calls are observable external interactions in a deployment, although the paper treats `emit` as the only outward effect. Secret-controlled call existence, chosen provider, and prompt selection need either an explicit exclusion from the attacker model or enforcement. Trusted-input provenance also does not prove that a model produces safe or truthful content. Written endorsement reasons are trusted assertions, not executed validators.

The saturation proof needs correction: a finite machine maximum does not dominate arbitrary mathematical costs. Rejecting saturated bounds with E266 is the useful implementation safeguard; formulate the theorem for successfully certified, nonsaturated programs.

### 6. Token bounds are not portable across model tokenizers

`inspectCall` assigns each result its producing model's output token cap, then reuses that count directly as a later model's input bound. Token counts are relative to a tokenizer. A string with at most N tokens under model A need not have at most N tokens under model B. The DSL permits different models, but has no conversion contracts or tokenizer identity. This is a deployment-contract gap, not something the mock tests.

Likewise, `std::string::size()` measures bytes, although the option and prose say characters. Serialized request wrappers, tool schemas, escaping, and tokenizer behavior at concatenation boundaries require a precise accounting contract. A1/A2 can make an abstract theorem conditional, but they do not implement those obligations. Avoid “unconditionally sound” in deployment claims.

## Evaluation and certificate audit

**Branch coverage is weaker than claimed.** The generated outer branch guards use `tokens(head) <= 150`, while `head` comes from a model capped at 150. The else arms are unreachable under the mock contract. More seeds cannot exercise them. The expensive unreachable arms inflate slack and make “branches are loose because we charge the expensive arm” an incomplete explanation. Add reachable guards, forced decisions, endpoint outputs, and measured branch coverage.

The paper specifically says `branch_in_retry` is unsound for the flat baseline in principle but not observed in 200 seeds. For the checked-in program this is false: the reachable worst case is `278 + 3*278 = 1112`, below the flat bound 1284. The larger 2462 certificate includes an infeasible expensive arm. Correct the sentence rather than merely increasing seeds.

**The baseline is described incorrectly.** `bench/evaluate.py:53` actually sums both IR `out_tokens` and `in_tokens`, although the text repeatedly calls it the sum of `max_tokens`. Relabel it “flat sum of per-call input and output upper bounds.” It is a useful regression baseline for the old compiler, but a deliberately retry-unaware sum is not competitive state of the art. Add a simple control-flow-aware baseline and an exhaustive bounded oracle. Compare tools only on properties and inputs they support.

**Security classification is policy conformance, not injection robustness.** Handwritten labels plus a one-line trusted endorsement often explain the difference between “unsafe” and “safe.” That demonstrates enforcement of the declared policy; it does not show that the endorsement is justified or that an application resists adversarial text. Preserve the fixture results but describe them as such. Measure how many independently sourced useful workflows are expressible, rejected, or require trusted escapes.

**The evaluation harness can hide failures.** It skips failed certification/runs, counts any nonzero exit as an unsafe rejection (`:153`), and returns success even when bound violations occur (`:266`). Missing files, crashes, or unrelated parse errors must not count as security successes. Require exact run counts, expected diagnostic families, and nonzero exit on failed experiment assertions.

**Certificates are structured reports, not independently checked proofs.** The emitter writes JSON and textual derivations. No independent certificate checker, source/IR binding hash, formal proof term, or runtime consumer is implemented. A JSON parser checks syntax, not truth. Call this an “analysis certificate/report” until there is a small trusted checker that rejects forged, stale, or incomplete evidence. `orchc run` also returns before the cost pass (`src/main.cpp:184`), so execution does not require cost certification.

“Zero runtime analysis overhead” is reasonable for an erased static pass inside the restricted semantics. “Zero runtime cost” or superiority to runtime monitors is too broad: enforcing input contracts and integrating real providers remains work. Runtime monitors commonly check *before* a forbidden effect, not only after it has fired.

## Prior-work findings

The key missing reference is [Ngo, Dehesa-Azuara, Fredrikson and Hoffmann, IEEE S&P 2017](https://www.ieee-security.org/TC/SP2017/papers/408.pdf), *Verifying and Synthesizing Constant-Resource Implementations with Types*. It already integrates information-flow typing with resource analysis, formalizes resource-aware noninterference, and addresses resource side channels. Consequently, combining these two analyses and discovering secret-dependent resource usage is not a new general idea. OrchLang would need an LLM-specific technical advance beyond that foundation.

[Time Will Tell](https://arxiv.org/abs/2412.15431) already studies sensitive-information leakage through LLM output token counts and timing. [USENIX Security 2024 token-length attacks](https://www.usenix.org/system/files/usenixsecurity24-weiss.pdf) and [USENIX Security 2026 merged-output attacks](https://www.usenix.org/conference/usenixsecurity26/presentation/li-sijia) address related observations. These differ from workflow-level billing, but rule out presenting all token/resource leakage as a new defect class.

The following distinctions matter for fair positioning:

| Work | What it establishes for positioning |
|---|---|
| [CaMeL](https://arxiv.org/abs/2503.18813) | Data/control separation and capability-based defenses are not merely runtime string scanning. The README's universal string-scanning claim is false. |
| [FIDES](https://arxiv.org/abs/2505.23643) | Missing close comparator for confidentiality, integrity, and controlled release in AI agents. Include its security model and useful-task tradeoffs. |
| [AgentFlow](https://arxiv.org/abs/2608.22868) | Runtime enforcement plus a bounded SMT verifier; calling everything purely dynamic loses a relevant distinction. |
| [NeuroTaint](https://arxiv.org/abs/2604.23374) | The abstract explicitly describes offline auditing of execution traces. The draft misclassifies it as a runtime mechanism. Offline trace analysis and pre-execution source analysis are different. |
| [GIF](https://arxiv.org/abs/2606.23277) | Local geometric/semantic information-flow reasoning; a different guarantee and model-access requirement from source-label propagation. |
| [Agentproof](https://arxiv.org/abs/2603.20356) | Static workflow verification already exists; compare checked properties and extraction coverage, not just “static versus runtime.” |
| [Token Budgets](https://arxiv.org/html/2606.04056v1) | Affine bookkeeping integrity plus conditional runtime spend caps. Its 4–6x reservation slack is not directly comparable with OrchLang's bound/sample-maximum ratio on another corpus. |
| [Budget-conserving multi-agent routing](https://arxiv.org/abs/2605.05657) | Resource accounting/conservation is an existing adjacent direction. |
| [Proof-carrying LLM certificates](https://arxiv.org/abs/2605.16407) | Merely emitting a certificate is not an uncontested new contribution. Specify precisely what a checker trusts. |
| [llm-cost](https://github.com/rul1an/llm-cost/) | Non-peer-reviewed engineering prior art for offline/static cost estimation and CI budget checks. Its README is not evidence of a formal workflow bound. |
| [Beyond Max Tokens](https://arxiv.org/abs/2601.10955) | Tool-chain resource amplification is already an attack research topic. A defense needs more than identifying that attacks can increase spend. |

I did not find, in this targeted search, an exact duplicate of the proposed restricted DSL with both analyses and its report format. **That is insufficient to support “first”: combining existing ideas in a narrow new language can be useful without being a substantial research contribution.**

### Existing bibliography cross-check

The cited recent arXiv identifiers resolve to the named papers; they are not obviously invented citations. Existence is not verification of their experimental claims or peer-review status. Relevant metadata and claim corrections:

| Draft references | Check |
|---|---|
| [1] [LMQL](https://arxiv.org/abs/2212.06094) | Title and 26–85% reported cost savings confirmed on primary abstract. Savings are not universal static bounds. |
| [2] [SGLang](https://arxiv.org/abs/2312.07104), [3] [DSPy](https://arxiv.org/abs/2310.03714), [4] [APPL](https://arxiv.org/abs/2406.13161), [5] [PDL](https://arxiv.org/abs/2410.19135) | Title/identifier matches confirmed. This is not an exhaustive audit of each system's current implementation. |
| [6]–[13], [21] | Primary pages verified; see distinctions above and [f-secure](https://arxiv.org/abs/2409.19091). Pin versions and supply complete author metadata. |
| [14] [Denning & Denning](https://faculty.nps.edu/dedennin/publications/CertificationProgramsSecureInfoFlow.pdf) | Classical static IFC foundation; fits the cited role. |
| [15] [Volpano, Smith, Irvine](https://course.ece.cmu.edu/~ece732/s24/readings/secure-types.pdf) | Paper verified; correct author order from its title page is Volpano, Smith, Irvine. Draft reverses the last two. |
| [16] [JFlow](https://www.cs.cornell.edu/andru/papers/popl99/popl99.pdf), [17] [IFC survey](https://www.cs.cornell.edu/andru/papers/jsac/sm-jsac03.pdf) | Primary texts located; support established static flow analysis. |
| [18] [Multivariate AARA](https://www.cs.cmu.edu/~janh/assets/pdf/aamulti_journal.pdf), [19] [Exponential AARA](https://link.springer.com/chapter/10.1007/978-3-030-45231-5_19) | Primary records located. OrchLang does not currently implement amortized potential inference. |
| [20] [Declassification](https://www.cse.chalmers.se/~dave/papers/sabelfeld-sands-CSFW05.pdf) | Primary text located. A justification string does not implement all semantic release principles. |
| [22] [OWASP project](https://owasp.org/projects/top-10-for-large-language-model-applications) | Real project. Pin the cited 2025 edition rather than relying on a changing landing page. |

Remove “every taint checker accepts this,” “every published defence scans strings,” “only a unified compiler can see it,” and “genuinely new defect class.” Separate modules can share facts; the C++ implementation itself does so. The scientific question is whether the combined reasoning provides a sound and useful property, not whether it happens in one executable.

## How to turn this into stronger research

These are proposed research directions, not completed features or proven-original claims. Choose one main contribution; do not inflate scope with unrelated additions.

### Recommended: relational token-resource contracts

Possible title: **Beyond Equal Caps: Relational Resource Contracts for LLM Workflows**.

Research question: *When can a compiler prove that changing secret data does not change an explicitly defined resource observation, despite opaque model calls and bounded retries?*

Start with a small language and a coupled oracle semantics. Separate two properties: unary worst-case budget safety and relational resource independence. Represent input lengths symbolically, give each call an explicit tokenizer/model contract, and preserve relations across the two executions. Handle secret-independent schedules first; introduce secret branches only when the relational obligations can be discharged. A useful result would accept nontrivial safe workflows rejected by a ban on all secret branching, while rejecting equal-cap counterexamples that the current rule accepts.

The potential advance over classical constant-resource typing must be specific: opaque stochastic calls, tokenizer conversion, provider-visible resource vectors, or composition of such contracts. If the implementation only instantiates the 2017 method with tokens as a resource metric, position it as an application/tool paper rather than new theory.

**Minimum convincing evidence:** full rules and soundness argument; ideally a mechanized small core; a separate certificate checker; executable counterexamples to tempting weaker rules; exhaustive paired executions of small programs; and independently sourced workflow case studies. Demonstrate why ordinary max-bound analysis and a straightforward constant-resource baseline cannot obtain the same precision or utility.

Do not claim that equal max-output settings or local dummy padding equalize a provider's actual bill. Early stopping, input lengths, differing model prices, retry outcomes, and request observability remain relevant. Padding must have a defined deployment semantics and be included in both the cost and privacy proof.

**Publication shape:** a focused letter is plausible if it delivers one nontrivial compositional theorem and an implemented checker, with clear improvement over the classical baseline. A full article needs stronger expressiveness, usefulness, and empirical evidence. Acceptance cannot be inferred from the topic alone.

### Alternative: portable bounds across heterogeneous tokenizers

Possible title: **Compositional Token Bounds Across Heterogeneous LLM Pipelines**.

Research question: *Can a workflow bound remain valid when outputs are reserialized and retokenized for different models?*

Attach units to resource facts: token counts under tokenizer A, UTF-8 byte bounds, serialized request bounds, and counts under tokenizer B. Derive and validate conversion contracts; reject unsupported conversions. Include template wrappers, escaping, and bounded retries. Use exact finite-vocabulary facts where possible, conservative byte-based fallbacks otherwise, and explicitly model special-token and request overhead.

Evaluate multilingual text, code, JSON, unusual Unicode, empty inputs, long strings, mixed-model chains, and actual serialized requests. Compare the four-character heuristic, one-token-per-byte assumptions under stated tokenizer conditions, exact tokenization where content is known, and the proposed compositional method. Report both violations and reservation slack on the same workloads.

**Why it might work:** it addresses a concrete compositional gap hidden by the mock. **Why it might fail as a paper:** a simple byte conversion plus tokenizer calls may be routine engineering. It needs a useful new bound, demonstrably better precision, or a substantial empirical finding. Related static estimators, AARA, and tokenizer literature must be searched further before claiming originality.

### Alternative: quantify attacker-controlled spending

Possible title: **Bounding Attacker-Controlled Resource Amplification in LLM Workflows**.

Instead of W237 warning that untrusted data selects different maxima, estimate an upper bound on the change in cost caused by varying untrusted inputs while fixing trusted state and specifying how model randomness is coupled. Distinguish an absolute budget cap from an influence bound. Ratios are unstable when baseline spend can be zero; start with an additive bound.

Useful contributions could include provenance of spend increases, sound treatment of correlated branches/retries, and identification of minimal policy changes that reduce exposure without disabling useful work. Evaluate external attack scenarios and useful-task completion, rather than just whether an endorsement was added.

**Risk:** resource amplification attacks and budget enforcement already exist. A coarse interval difference is a baseline, not sufficient novelty. This direction needs a sharper relational analysis or a strong deployment study.

## An evidence-driven execution plan

1. **Correctness gate.** Fix findings 1–4, define literal/scoping semantics, and add the supplied counterexamples to regression tests. Withdraw unsupported theorems immediately; retain E236 only with accurately limited wording until replaced. Define tokenizer and model-oracle assumptions.
2. **Choose the research property.** Write the observer, allowed programs, adversary, theorem, and closest-prior-work delta on one page. Have a PL/security supervisor challenge that delta before substantial implementation.
3. **Build independent evidence.** Create a small reference interpreter with explicit input stores and model outcomes; compare it to the C++ implementation. Generate bounded programs and exhaustively enumerate small cases, including both branch directions and all retry counts. Test certificate tampering and source mismatch. Keep the existing 23 workflows as regressions.
4. **Build an external corpus.** Predefine selection criteria and adapt independent workflow/agent-security examples. Keep an exclusion log for features the DSL cannot represent. For a pilot, 20–30 diverse workflows is a useful engineering target, not a publication threshold. Separate development fixtures from held-out evaluation; ask another reviewer to validate labels and adaptations.
5. **Use meaningful baselines.** Compare flat sum, control-flow upper bounds, path-sensitive interval bounds, a classical constant-resource discipline, and the new relational method on the same admissible fragment. Runtime IFC systems belong in a separate utility/security comparison with their different scope made explicit.
6. **Measure the right outcomes.** Soundness counterexamples; proof obligations discharged; false rejections; trusted-escape frequency; supported-case coverage; bound slack against exact reachable maxima where available; compiler/checker scaling; and real request accounting where deployment claims are made. If attack resistance is claimed, measure attack success and legitimate-task utility.
7. **Write after the result stabilizes.** Report negative results and unsupported features. Do not replace lack of novelty with more plots, more seeds, or stronger adjectives.

## Publication recommendation

| Form | Current readiness | What changes the assessment |
|---|---|---|
| Undergraduate project / demonstration | Substantial artifact, with important defects to disclose | Correct core claims and supplied failures |
| Student research or program-analysis workshop paper | Plausible after repair and honest positioning | Clear scoped question, useful artifact, external cases, fair baseline |
| Journal letter / short research paper | Not ready | One distinct and correct result, concise proof, focused validation |
| Full research journal article | Weak in present form | New method or substantial empirical contribution; independent evidence and complete semantics |
| Selective PL/security research venue | Not currently competitive | Significant advance over classical resource-aware IFC, with rigorous and realistic evaluation |

[SOAP's official 2026 call](https://pldi26.sigplan.org/home/SOAP-2026) explicitly included integration/idea papers about program analyses, making that *kind* of workshop a sensible fit after correction. The 2026 event is past; this is a scope comparison, not an open-deadline recommendation. The official Information Processing Letters scope page could not be retrieved in this audit, so no current page-limit, fee, deadline, or acceptance-rate claim is made. Venue selection should follow the completed contribution.

The existing submission plan's advice to post the draft immediately should not be followed with the current claims. First correct the soundness failures and prior-work positioning. The project's value is its working compiler and a tractable platform for studying resource-aware security; the next paper should earn its claim through one precise new result.
