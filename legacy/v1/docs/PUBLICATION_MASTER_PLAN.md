# OrchLang: publication master plan and execution contract

**Prepared 23 October 2026. Audience: implementation/research agent, author, and faculty reviewer.**

This is the controlling plan for the next research iteration. It supersedes the research recommendations in `AGENT_BRIEF.md` and `SUBMISSION_PLAN.md` where they disagree. Those documents remain useful historical records. This document is a plan, not a report of completed experiments or a promise of journal acceptance. Proposed commands, directories, theorems, and acceptance targets below are explicitly future work unless labelled observed.

## 1. Decision and intended paper

**Do not submit the current research manuscript.** The repository is a useful prototype, but its central relational guarantee still has a concrete counterexample. Its comparison against prior resource analysis is too broad, its benchmark baselines do not establish competitive precision, and its mock execution does not establish real-provider resource privacy. A short paper does not remove these obligations.

The strongest feasible direction is a programming-languages paper about **the conditions under which resource observations of LLM workflows can actually be certified**, accompanied by a usable checker and a reproducible evaluation. The contribution should connect static relational reasoning to explicit model, request, tokenizer, retry, and observer contracts. It must distinguish a theorem about an abstract oracle from a guarantee about an implemented adapter.

Working title: **Contract-Checked Resource Privacy for LLM Workflows: From Relational Analysis to Reproducible Execution**. This is provisional. Use “privacy” only for the observation and threat model actually established. If the finished work proves only replay semantics, put that limitation in the title/abstract or choose “Resource Contracts for Bounded LLM Workflows.”

The intended contribution is not “LLMs need a new cost theory because they are stochastic,” “the first contracts for agents,” or “the first static workflow token bound.” Existing work substantially overlaps these claims. The candidate contribution is a sound, useful specialization with a precise trust boundary, an independently checkable result, and measured advantages over credible alternatives. This remains a hypothesis until the novelty gate in Section 5 passes.

The preferred venue is Elsevier's **Science of Computer Programming**, interpreted here as SCP. Its stated remit includes programming-language design, implementation, and evaluation, so this project can fit if it develops a defensible method and convincing evidence. The [publisher scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423) establishes fit, not acceptance probability.

## 2. Binding resource constraints and author decisions

The user has an RTX 5050 Laptop GPU with 8 GB VRAM; this audit observed 8,151 MiB and driver 610.74. Use a CPU-first formal/evaluation core and batch-one local inference. There is no requirement for training, fine-tuning, cloud GPUs, a paid judge model, or a large model. Local model experiments validate adapters and reveal limitations; model intelligence is not the scientific variable of interest.

The entire paid final-testing budget is **US$5**, across all providers and all attempts. Existing Claude Pro, ChatGPT Plus, and OpenCode Go subscriptions are available for the author's ordinary assistance, but are not assumed to grant programmatic inference credits. Do not automate subscription interfaces as an experimental API. Do not incur publication charges or buy papers under this budget.

The author has VIT Library Extension access and a strict faculty reviewer. Use that access for the short reading queue in Section 16. Never request passwords, session cookies, or API keys in a chat transcript. A future restricted key belongs in a local environment variable or secret store, excluded from logs and Git.

No submission deadline was supplied. Plan approximately 12–20 part-time weeks for one capable implementer, with substantial uncertainty around proof work and corpus construction. This is a planning estimate, not a delivery commitment. Reduce the scope honestly if a real deadline is shorter; do not replace missing evidence with claims.

Author decisions needed, without blocking offline work: submission deadline; available hours per week; RAM/disk availability; approved software license and contribution ownership; author list and faculty availability; whether external workflow adaptations may be redistributed. API access is needed only after the offline gates pass.

## 3. Refreshed repository audit: evidence versus inference

Audited repository: `orchlang-compiler-design-project`, branch **main**, commit **a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9**. Although the initial request referred to a new local branch, the current checkout is main and includes the relational work. Do not assume the old novelty branch is still the checked-out state. Record any subsequent implementation base independently.

The September audit is historical. Several intervening changes exist, including a relational analyzer, narrowed paper, tracked evaluation output, and a revised handoff. Do not repeat old defects as if their current status had been established.

### 3.1 Observed in this audit

The test suite was freshly rebuilt using the installed WinLibs GCC 16.1 toolchain with C++17, `-Wall -Wextra -pedantic -O2`. **All 95 tests passed.** The CLI was also freshly rebuilt. The default PATH toolchain is older; `.envrc` identifies the usable compiler location. The test log and new witness are in `research/2026-10-23/`. No production source was changed by this planning audit.

Despite those tests, the following workflow passes `check`:

```orch
workflow ShadowedContract budget 10000 {
 secret s: boolean max_tokens 1;
 input x: text max_tokens 0;
 prompt p(t: text) -> text = "{t}";
 if s {
  model m = mock("small") max_tokens 1;
  let a: text = call p(x) using m;
 } else {
  model m = mock("large") max_tokens 1000;
  let b: text = call p(x) using m;
 }
 output x;
}
```

With seed 1 and `s=true`, the mock reports input 1, output 1, total **2**. With the same seed and `s=false`, it reports input 1, output 986, total **987**. Both paths contain a model called `m`; the declarations have different contracts. In `src/relational.cpp`, the call signature compares `model` and `inputSize` at line 34 and stores `site.modelName` at line 144 at the audited commit. Lexical-name equality conflates distinct resolved declarations. This witness refutes the implemented acceptance rule's intended paired-execution resource claim; the reported unary maximum remains sufficient for this witness.

Repair requires two separate concepts: **binding identity** for correct name resolution and **canonical semantic contract equality** for permitted equivalences. Comparing only names is unsound; comparing only fresh binding IDs would reject semantically identical aliases unnecessarily. Test both distinct shadowed contracts and equivalent aliases. Preserve the witness permanently.

### 3.2 Recorded results, not freshly rerun here

The repository's existing evaluation records report 0/4,600 componentwise bound violations, flat-baseline violations 636/4,600, control-flow-baseline violations 644/4,600, median slack 1.11, and 0/2,975 accepted secret-pair differences, with seven rejected witnesses. These are tracked historical experiment outputs, not new confirmations by this turn. The 95-test result above is fresh. Never merge these provenance categories in a paper.

The current `control_flow_baseline` in `bench/evaluate.py` omits retry multiplication. A baseline that already mishandles supported language constructs cannot establish superiority to a competent resource analyzer. The flat baseline may accidentally compensate by overcounting branches. Preserve these only as explicitly broken negative controls.

### 3.3 Further semantic gaps to investigate

Current signatures represent sizes, model names, and selected syntactic structure. A size signature is not a full model request. Equal prompt lengths do not imply equal response distributions. For example, two equally long requests may induce deterministic output lengths 1 and 100 under an admissible request-dependent model kernel. A common random-length tape does not become a valid coupling merely because the two programs use the same seed.

The current mock's random-stream behavior, declarations, retry sampling, and token-count values require a line-by-line correspondence review against the paper's oracle. Audit branch-local state in the relational builder, including `localCalls_` and `callIndex_`, nested branches, scope exit, and call alignment. These are investigation targets, not additional confirmed defects.

Inspect UTF-8 handling, character/token conversions, concatenation, model-specific retokenization, chat serialization overhead, cap semantics, failed-but-billed calls, hidden reasoning usage, and overflow. A “four characters per token” estimate must never silently become a provider-token theorem. Inspect content confidentiality separately from cost equality: a resource-equivalent secret branch must not automatically declassify its output content.

## 4. Literature map and claim corrections

This is a focused, refreshed primary-source survey, not an exhaustive systematic review. Sources were checked on 23 October 2026. Full proof comparison remains implementation work. “Abstract inspected” does not mean “theorem audited.” Track versions and access status in the evidence ledger.

| Work and source | Relevant overlap | Required comparison / current access status |
|---|---|---|
| [Ngo et al., IEEE S&P 2017](https://www.ieee-security.org/TC/SP2017/papers/408.pdf) | Resource analysis and information-flow security already interact in prior work. | Open paper available. Compare constant-resource conditions, synthesis, and leakage interpretation; do not claim the combination itself. |
| [RelCost, POPL 2017](https://people.mpi-sws.org/~dg/papers/popl17.pdf) | Relational cost reasoning predates this project. | Open paper; map our judgment, assumptions, and automation to its expressiveness. |
| [Monadic refinements for relational cost analysis, POPL 2018](https://www.radicek.com/papers/popl18.pdf) | General frameworks connect relational and unary cost analyses. | Open paper; inspect primitive specifications and how our fragment could be encoded. |
| [Raising Expectations, ICFP 2020](https://www.cs.cmu.edu/~janh/assets/pdf/WangKH20.pdf) | Probabilistic automatic amortized resource analysis exists. | Open paper/abstract inspected. It defeats blanket assertions that randomness makes potential-based resource analysis impossible. |
| [Relational reasoning via probabilistic coupling](https://arxiv.org/abs/1509.03476) | Coupling is a standard proof technique with marginal obligations. | Open source; identify exactly which coupling rule we specialize. |
| [eRHL](https://arxiv.org/abs/2407.17127), version 2, January 2025 | Quantitative relational probabilistic reasoning already covers rich properties. | Abstract inspected; full relevant rules must be read before claiming a new quantitative logic. |
| [Köpf and Basin, adaptive side-channel attacks](https://people.inf.ethz.ch/basin/pubs/ccs07.pdf) | Observation choice, priors, and repeated attacks matter for leakage. | Open source; mandatory before any claim measured in bits. |
| [Time Will Tell](https://arxiv.org/abs/2412.15431) | LLM timing/token observations are already a security topic. | Motivation and threat-model comparison; it is not a compiler baseline. |
| [CaMeL](https://arxiv.org/abs/2503.18813) and [FIDES](https://arxiv.org/abs/2505.23643) | Agent security through controlled execution and information flow. | Open papers; compare security goal and restrictions, not incomparable headline accuracy. |
| [AgentDojo](https://arxiv.org/abs/2406.13352), [artifact](https://github.com/ethz-spylab/agentdojo) | External agent-workflow evaluation source. | A bounded static adaptation is a new corpus, not the original benchmark result. Record all exclusions. |
| [Statically Bounding Resource Accumulation in LLM Agent Workflows: The Cost Case](https://loom.technology/research/bounded-llm-cost/), May 2026 | Author-hosted report proposes structural workflow cost bounds. | Relevant text inspected; peer-review status is not established here. Compare fragment and retry/accounting assumptions, and reproduce applicable artifact results if available. |
| [Proof-Carrying Contracts: Commitments AI Agents Cannot Break](https://arxiv.org/abs/2610.28484), submitted 20 October 2026 | PC2 checks proofs before agent operations and addresses preservation of constraints. | Abstract and relevant HTML sections inspected, not a complete 70-page proof audit. Generic “proof-carrying agent contracts” is not our novelty. Read budget modules and real-world correspondence carefully. |
| [Hard-KLAIM: Hardening MCP-Enabled Agentic Workflows with a Locality-Aware Type-and-Effect System for Trace Safety](https://www.sciencedirect.com/science/article/pii/S2352220826000830), October 2026 | Very recent type-and-effect work on agentic workflows. | Publisher metadata/search excerpt available; full text blocked in this environment. VIT access is needed before claiming separation. |

Explicitly withdraw the old proposed impossibility argument that a stochastic LLM call cannot have a numeric potential or resource specification. A cap can support a conservative worst-case specification, and probabilistic analyses can reason about expected cost under suitable assumptions. The interesting question is the precision and validity of the specification, not whether a number can exist.

Do not treat lack of a phrase in a search result as evidence that a paper lacks a feature. Do not assert priority from this table. Retrieve bibliographic metadata from the primary records and manually verify author names, publication status, version, DOI, and theorem references before producing the final bibliography.

## 5. Novelty gate before major implementation

Spend the first research iteration on a falsifiable comparison. Create `research/novelty-ledger.csv` with one row per proposed claim and columns: claim ID, exact statement, closest source/version/section, existing capability, proposed delta, witness example, assumptions, implementation artifact, evidence status, faculty decision. Each claim must survive the strongest applicable prior work, not merely the nearest LLM-branded system.

Candidate research questions:

1. Can a small compositional checker separate request equality, token-length equality, and provider-kernel assumptions sufficiently to certify useful workflows without silently trusting an invalid coupling?
2. Does tracking tokenizer units and resolved request contracts prevent practically occurring false certifications at acceptable precision and annotation cost?
3. Can certificates make analysis results independently auditable without reproducing the entire analyzer, and what remains trusted between source, IR, adapter, and provider?
4. On external bounded workflows, which resource-privacy guarantees are useful and which are too restrictive? Can principled transformations recover utility?

These are candidate questions, not claims of novelty. Build six small separating examples before a large implementation: shadowed contracts; equal length/different request; equal request with different retry/error contract; cross-tokenizer composition; equivalent aliases; safe public-control composition with secret data retained privately. For each, compare a correct conventional implementation and the proposed rule. Include examples our rule must reject.

**Proceed with the SCP research narrative only if** there is an explicit method or semantic insight beyond conventional IFC plus cost annotation, a useful class of programs admitted, and a credible argument for why existing generic tools require materially different assumptions or effort. A specialized decidable checker with demonstrable precision/usability can be a contribution; mere renaming cannot.

If this fails, do not invent a separation theorem. Choose the tool/reproducibility narrative in Section 15, or select one bounded extension from Section 13 with faculty agreement. Record negative novelty findings. Avoid building five speculative extensions simultaneously.

## 6. Formal model: freeze this before implementation grows

Define a sequential, terminating core with literals, bounded inputs, lexical bindings, prompts, bounded model calls, conditionals, bounded retries, and output events. Exclude unbounded recursion, arbitrary dynamic tool graphs, concurrency, streaming timing, and uncontrolled network actions from the first theorem. If implementation accepts syntax outside the proven fragment, label it unsupported for certification.

### 6.1 Values, contracts, and units

Represent content, confidentiality label, integrity label, and size information separately. A public length is not public content. Let a resolved model contract contain at least:

```text
M = (provider, model revision, tokenizer revision, serializer revision,
     sampling parameters, output-cap interpretation, error/retry policy,
     usage-accounting policy, external-state assumptions)
```

Canonicalize semantic fields, not declaration spelling. Missing or unverifiable fields produce an explicit assumption or refusal. Distinguish UTF-8 bytes, Unicode code points, tokenizer-specific input/output tokens, call counts, and money. Addition across tokenizer units requires an explicit conversion or a vector indexed by model/contract. Do not assume tokenization is additive across concatenation. Prefer exact tokenization of fully serialized known requests and sound, stated upper bounds for symbolic content.

The runtime state includes environments, public/secret stores, bounded remaining attempts, accumulated observations, and relevant provider/session state. State precisely whether models are stateless, how caches behave, and what a model revision fixes. A shared provider name cannot establish these properties.

### 6.2 Observers

Define at least two explicit observers: aggregate usage vector and ordered billing trace. The first may see per-contract input/output counts and call counts; the second also sees order, request category, failures, or retry events as specified. A money-only observer depends on a fixed tariff; token equality is not automatically equality of all provider charges. Timing and output contents are out of scope unless separately treated.

State who the adversary is. An account observer is different from the provider, which sees requests. Declare what public inputs, caps, model choices, errors, and invocation counts reveal. Define low-equivalence of initial states relative to that observer. Termination is bounded in the core, but early failure is still observable and must be modelled.

### 6.3 Calls and valid coupling

Represent a call by a kernel `K_M(request, state)` over response text, usage, status, and next state. A relational primitive contract supplies a coupling whose marginals are exactly the two call kernels and whose outcomes satisfy the declared relation. Same seed, same output cap, and equal request length do not establish this condition.

The conservative default rule requires equal fully serialized requests, equal semantic contracts, and appropriately related external state. Under an explicit same-kernel assumption, identity coupling is valid. For unequal requests, reject a privacy certificate unless a stronger primitive relation is justified. Local replay may supply a finite explicit kernel; do not generalize its certificate to an unknown cloud service.

Equality coupling proves equality in distribution, not that two independent real invocations return identical traces. Tests must respect this distinction. A fixed deterministic replay can test pathwise interpreter correspondence; independent local/remote samples test empirical behavior only.

Downstream calls require relations on response content sufficient to justify the next request relation. Length equality alone cannot propagate through arbitrary prompt construction or semantic predicates. Preserve these dependencies explicitly.

### 6.4 Theorem obligations

Target the following statements, with assumptions printed alongside each theorem:

1. **Unary resource soundness:** every admitted execution has nonnegative resource vector `C <= B` componentwise, conditional on primitive usage contracts. Include every bounded attempt, serialization charge, and supported failure event. State separately any conversion to currency.
2. **Relational observation soundness:** for low-equivalent states and valid primitive relational contracts, an accepted program induces equal distributions under the named observer. Prove via a valid execution coupling; do not substitute equality of upper bounds.
3. **Composition:** sequential composition and supported branch/retry rules preserve their preconditions, state relations, and resource guarantees. Address termination and exceptions explicitly.
4. **Observer projection:** equality for a stronger observation implies equality for its deterministic projection. This supports weaker aggregate guarantees without pretending they imply trace equality.
5. **Certificate checker soundness:** acceptance of a well-formed certificate implies the semantic judgment for the checked IR. State what connects that IR to the executed program.

Mechanize the bounded core in **one** proof assistant, Lean or Rocq, chosen for implementer/faculty competence after a small feasibility spike. Do not start both. Remove admitted lemmas from the release proof. Distinguish axioms representing external primitives from unfinished proofs. A mechanized abstract theorem is not verification of the whole C++ implementation.

## 7. Implementation architecture and work packages

The following paths are proposed and may be adapted after inspecting repository conventions. Preserve stable user-facing behavior where possible; document intentional rejection changes. Do not add a large framework solely to sound impressive.

| Package | Dependencies | Concrete work and deliverable | Acceptance condition |
|---|---|---|---|
| W0: evidence freeze | None | Capture commit, dirty state, compiler, tests, historic-result provenance; retain witness and reproducible commands. | Fresh baseline reproduces both the passing suite and failing relational witness. |
| W1: novelty and semantics | W0 | Literature ledger, comparison examples, `docs/SEMANTICS.md`, threat model, faculty discussion. | Claims are scoped; no unexamined coupling assumption or blanket AARA impossibility remains. |
| W2: resolution and typed IR | W0 | Resolve model/prompt/value bindings; introduce semantic contract IDs and typed resource units. | Shadowing, alias, nested-scope, serialization, and overflow regressions behave correctly. |
| W3: reference semantics | W1–W2 | Small independent interpreter with explicit stores, text values, outcome tapes/kernels, and structured events. | Hand-enumerated examples match; it does not call the production analyzer to generate expected answers. |
| W4: analysis and certificates | W1–W3 | Request/content/size relations; observer-indexed rules; certificates with explicit assumptions; readable rejection reasons. | Positive and adversarial cases agree with the reference semantics; unsupported inputs fail closed. |
| W5: proof and checker | W1, alongside W3–W4 | Mechanized core, independent certificate checker, trust-boundary document. | Proof builds from clean checkout; malformed/mismatched certificates are rejected. |
| W6: runtime adapters | W2–W4 | Local text runtime, tokenizer/serializer adapters, bounded retries, usage ledger, deterministic replay. | Contract violations are surfaced; replay traces reproduce; unknown billing is never treated as zero. |
| W7: fair evaluation | W3–W6 | Strong baselines, external corpus, mutation/generative tests, preregistered protocol, raw data. | Tables regenerate; exclusions/failures remain visible; no result is selected by favorable seed. |
| W8: paid validation | Offline gates, faculty review | Restricted-key provider smoke/pilot/frozen final runs. | Total reserved plus spent stays within $5; requests and usage are attributable without leaking secrets. |
| W9: manuscript/release | W5–W8 or disclosed narrower scope | Paper, appendices, archive, license, reproducibility guide, reviewer packet. | Independent person reproduces core results and verifies every principal claim. |

For W2, retain source spans through lowering, use checked arithmetic for size/budget calculations, and make canonicalization stable across serialization. Test renamed variables, duplicate model names, semantically identical aliases, differing caps, differing tokenizer revisions, and changing temperatures. Do not define equivalence by a hash without specifying the hashed canonical structure.

For W3, make the reference semantics simpler than the production tool. Implement finite kernels with exact rational probabilities for tiny examples. Exhaustively enumerate executions up to explicit depth/size bounds. This provides an independent falsification oracle, not a proof for arbitrary programs.

For W4/W5, certificates should identify schema version, source digest, IR digest, contract definitions, observer, initial relations, rule tree, bound vector, and assumptions. A source digest only binds bytes; it does not prove correct lowering. Either validate source-to-IR translation or disclose the front end as trusted. Do not describe a Python checker as verified merely because its rules resemble the Lean/Rocq development. Prefer an executable checker tied to the mechanized definition when feasible; otherwise report the remaining implementation gap.

For W6, log each attempted request, preflight reservation, returned usage/status, response digest, and settlement. Provider failure after transmission may still cost money. Unknown outcomes retain their reservation until reconciled. Bound retry counts and prohibit hidden SDK retries. A runtime detector after an oversized response cannot retroactively prove the bill stayed within its reservation; only a valid provider cap contract or conservatively reserved maximum supports that statement.

Proposed future CLI interfaces are `orchc certify`, `orchc verify-certificate`, and `orchc run --backend replay|local|remote`. These do not exist merely because they appear here. Implement them or revise the release instructions before publication.

## 8. Adversarial test inventory

Create permanent regressions for the new shadowed-model witness and every earlier audit issue still reproducible at the new base. Record fixed historical failures with their fixing commit; do not silently remove them.

The required matrix includes: equivalent aliases; different providers sharing a short name; same lengths/different literals; content-dependent kernels; nested secret/public guards; branch-local variables reused after joins; unused declarations consuming randomness; zero calls; zero caps; maximum supported integers; Unicode and empty strings; repeated placeholders; multiple tokenizer units; retries with success/failure on each attempt; failed-but-billed requests; cap changes; malformed usage; wrong certificate/source pair; unknown certificate rule; unsupported language syntax; and output-content leakage despite equal resource traces.

Generate small well-typed programs independently of the analyzer's acceptance rule. Compare accepted programs to finite-kernel exhaustive semantics; compare interpreter traces to the production runtime. Use metamorphic tests for alpha-renaming, equivalent aliases, harmless grouping, and observer projection. Keep failing seeds and shrink counterexamples. Mutate rules deliberately—remove retry multiplication, confuse binding IDs, erase request content, or drop a failure event—and verify the suite detects those mutants. Report surviving mutants instead of hiding them.

Separate categories: implementation bug, violated external assumption, unsupported fragment, conservative rejection, malformed program, and experiment infrastructure failure. They must not all become “unsafe.”

## 9. Evaluation protocol and credible baselines

Freeze a versioned protocol before collecting final comparative outcomes. Development cases can guide implementation; held-out external cases must not be repeatedly redesigned to improve acceptance. Register a dated local protocol commit; public preregistration is optional, but immutable provenance is not.

### 9.1 Corpus

Use three explicitly separate strata:

1. Adversarial microbenchmarks targeting semantic obligations, including all published audit witnesses.
2. Generated bounded programs with declared grammar, size/depth limits, seeds, and finite kernels. Count programs and unique structures separately from repeated runs.
3. External workflows drawn from at least two independently maintained sources or applications, with frozen source revisions and an inclusion/exclusion census. Aim initially for 30–50 distinct bounded workflows across summarization, extraction, retrieval composition, validation/retry, and routing. This is a workload target, not a number already obtained or a required favorable outcome.

An AgentDojo adaptation may contribute cases, but record original task ID, original behavior, removed dynamic features, translation effort, preserved observations, and exclusion reason. Include difficult exclusions in the coverage denominator. If few real workflows satisfy the supported fragment, that is a research finding and a signal to narrow the claim or revise the method.

Each workflow needs an independently reviewed expected policy judgment or a small semantic oracle. Keep developer-designed examples separate from external tasks. Report annotation effort, source size, model-call structure, retry bounds, secret/public assignments, and required assumptions. Do not label a program “safe” solely because our tool accepted it.

### 9.2 Baselines

| Baseline | Purpose and fair implementation |
|---|---|
| Structural max/multiply bound | Sum sequential costs, maximum branch cost, bounded retry multiplication, the same primitive caps and serialization assumptions. This is the minimum competent unary baseline. |
| Interval/refinement variant | Track useful size intervals and reachable guards with comparable resource assumptions. Measure whether extra relational machinery actually improves results. |
| Conservative IFC/trace identity | Reject secret-dependent observable actions unless paired requests/contracts are identical. Establish a sound, easy-to-understand relational floor. |
| Bounded self-composition | Encode two executions in a finite reference checker or solver; include timeout/size limits. This is a strong small-fragment oracle, not claimed scalable verification. |
| Audited v3 implementation | Preserve the current tool as a historical comparator with known unsound cases clearly marked. Do not call its acceptance rate precision. |
| Closest external method | Reproduce a suitable prior artifact if compatible, or provide a carefully scoped encoding comparison. Explain missing executable comparisons and incompatible semantics. |

All baselines use the same front-end inputs, primitive contracts, and observer whenever possible. If their domains differ, compare the intersection and separately report coverage. A general logic need not have an LLM-specific executable to invalidate a novelty claim. Broken flat/retry-omitting baselines belong only in a negative-control appendix.

### 9.3 Questions, metrics, and analyses

RQ-A: Does the implementation agree with the formal core and finite oracle? Report violations by class, mutation detection, and independent-checker discrepancies. Zero observed failures is not proof; the proof and tests answer different questions.

RQ-B: What soundness/precision/coverage tradeoff does the new analysis achieve? Report accepted safe cases, rejected unsafe witnesses, conservative rejections, unsupported cases, and unresolved oracle cases. For bounds, report absolute slack and ratios only where the denominator is positive. Give median, distribution, worst cases, and per-workflow values. Do not hide zero-usage cases.

RQ-C: Is certification useful at reasonable effort? Report annotations per workflow, translation effort, analysis/checking time, certificate size, memory, and explanation quality against predetermined tasks. A small structured faculty walkthrough can document usability issues, but is not a human-subject study with population-level conclusions.

RQ-D: Where do real adapters violate abstract assumptions? Compare exact tokenizer/replay/local observations to specified contracts; catalogue mismatch causes. Provider validation is a small external-validity check, not proof of distributional privacy or broad deployment safety.

For runtime performance, warm up separately, repeat fixed workloads, record hardware/tool versions and thermal/power conditions, and aggregate at the workflow level. For uncertainty, use workflow-clustered bootstrap intervals where justified and show raw paired differences. Thousands of seeds on one workflow are not thousands of independent applications. Predeclare primary endpoints and treat extra analyses as exploratory. Do not use a nonsignificant distribution test as evidence of equality.

If equal-distribution claims are tested empirically, explicitly acknowledge finite samples cannot establish exact equality. A quantitative approximate guarantee needs a specified metric, estimand, confidence procedure, and assumptions; a dollar or token difference is not “bits leaked.”

### 9.4 Ablations

Remove one feature at a time: contract canonicalization, request-content relation, tokenizer-unit tracking, retry/failure accounting, observer distinction, and independent checking. Some ablations are deliberately unsound; label them as fault injection rather than competitive alternatives. For precision features, keep soundness assumptions unchanged and measure the incremental benefit. If a component adds complexity without measurable or theoretical benefit, remove it from the principal contribution.

## 10. Local inference plan for 8 GB VRAM

Start with synthetic kernels and exact tokenizers; these require no GPU and are sufficient for proof and semantic testing. Then use a pinned small open model as a text-producing adapter. [Qwen3-4B's model card](https://huggingface.co/Qwen/Qwen3-4B) is one candidate, not a mandatory choice. A four-bit quantization is a feasibility starting point; weight size alone does not establish VRAM fit because context/KV cache and runtime overhead also matter.

Run batch size 1 with short contexts and bounded outputs. Measure peak GPU memory, wall time, and disk use before the corpus run. Fall back to a 1–3B model if needed. Freeze model repository revision, weight checksums, quantization recipe/file, tokenizer files, chat template, runtime commit/version, sampling parameters, and thinking-mode settings. Prefer explicit fixed caps and disable optional reasoning modes when their accounting cannot be specified.

Test at least two tokenizer families for portability, even if only one model is run. A second small local model, executed sequentially, is optional if time/disk permit. Do not spend the research budget chasing frontier-model performance: the scientific task concerns resource semantics and trust boundaries.

Have two reproducibility tiers: CPU-only replay for all principal static results; optional GPU regeneration for real-text adapter observations. Store lawful raw responses or sanitized fixtures plus hashes when redistribution permits. Replaying captured responses is reproducibility of those observations, not a claim that future model sampling is deterministic.

## 11. Hard $5 remote-validation protocol

Use OpenRouter if its available endpoint provides adequate model/provider and usage provenance; otherwise inspect CodeCraft's actual API documentation before using it. Do not assume CodeCraft routing, model IDs, tokenizer behavior, or billing equals another service. The [OpenRouter authentication documentation](https://openrouter.ai/docs/api_reference/authentication) describes key-based access and controls; the [model documentation](https://openrouter.ai/docs/guides/overview/models) is the starting point for current endpoint metadata. Recheck prices and limits at execution time.

Budget envelopes: $0.25 API/schema smoke test, $0.75 pilot, $3.00 frozen final experiment, $1.00 contingency. These are ceilings, not spending targets. Set a separate provider-side key limit of at most $5 where supported, with no automatic replenishment. The harness independently caps cumulative spend and outstanding reservations. No other task may use this key.

Before each request, calculate a conservative maximum charge from serialized input, output cap, all billable categories, and permitted attempts using the saved current tariff. Dispatch only if `settled + outstanding + new reservation <= remaining authorized cap`. Count retries and uncertain failures; do not release reservations merely because a timeout occurred. If any billable category lacks a defensible bound, stop paid execution rather than guessing. Sequential requests simplify accounting. Reconcile provider totals after each stage.

The pilot checks schema, provider identity, cap enforcement, usage fields, and failures. It does not select the most flattering model. Prefer a fixed low-cost endpoint with fallbacks disabled when supported; record actual routing. If the endpoint cannot be pinned, disclose this as a limitation and retain replay evidence.

A possible final design is 12 preselected workflows × 2 secret variants × 5 repetitions = 120 workflow executions, with each execution's bounded call count priced separately. This is only a candidate ceiling: the pilot's request sizes and current prices determine the affordable predeclared sample. Reduce the design before final data collection if needed. Do not stop or extend based on significance. A $5 study cannot justify broad multi-provider security claims.

Store run IDs, timestamps, endpoint/model/provider metadata, redacted request configuration, response/usage hashes, errors, retries, and spend. Never store authorization headers. No paid experiment was run during this audit. Do not ask for a key until the offline package, faculty checkpoint, and cost manifest are ready.

## 12. Artifact and data contract

Create a machine-readable manifest per experiment. Minimum fields:

```json
{
  "schema_version": "1",
  "status": "planned",
  "source_commit": "REQUIRED_AT_RUN_TIME",
  "dirty_tree": false,
  "protocol_commit": "REQUIRED_AT_RUN_TIME",
  "corpus_manifest_sha256": "REQUIRED_AT_RUN_TIME",
  "observer": "aggregate_usage_or_ordered_trace",
  "backend": "finite_kernel_or_replay_or_local_or_remote",
  "model_contract_digest": "REQUIRED_IF_APPLICABLE",
  "seeds": [],
  "planned_workflows": 0,
  "completed_workflows": 0,
  "excluded_workflows": 0,
  "budget_usd_cap": 5.0,
  "spent_usd": 0.0,
  "outstanding_reserved_usd": 0.0
}
```

This example is a design template, not an actual run record. The runner must refuse `REQUIRED_AT_RUN_TIME` values and record complete environment and command metadata in linked files. Use a decimal representation or integer micro-units for money; do not rely on binary floating-point comparisons at the spending boundary.

Suggested layout: `proof/`, `certificates/`, `runtime/`, `bench/corpus/`, `bench/protocols/`, `bench/raw/`, `bench/analysis/`, `research/claims.csv`, and `docs/REPRODUCIBILITY.md`. Keep raw observations immutable; derived tables must name their source manifests. Provide a quick CPU reproduction command and a full offline reproduction command. A failed dependency download must not silently switch model or data versions.

Every manuscript number should trace to a machine-readable table, generating script, raw run manifest, and exact code revision. Every theorem should trace to a formal statement, proof artifact, assumptions, and implementation coverage. Add a table that explicitly lists unverified components: parser/lowering if applicable, tokenizer library, inference backend, provider cap/accounting contract, operating system, and hardware.

Before release, resolve the currently missing top-level license with the author, audit dependency/model/dataset licenses, update third-party notices, and exclude credentials and copyrighted library PDFs. Archive a versioned code/data release with a persistent identifier if available. Do not promise redistribution of provider responses or adapted benchmarks until permissions are checked.

## 13. Open research headroom with stopping criteria

The implementation agent may investigate these directions, but must preserve the main soundness work and choose at most one substantial extension before the first complete evaluation.

| Direction | Research question and first experiment | Continue only if | Stop or narrow if |
|---|---|---|---|
| Observer-sensitive certification | Can aggregate-usage certificates admit useful programs rejected by ordered-trace certification? Construct explicit separating workflows and prove projection. | The distinction reflects a plausible account observer and appears in external cases. | Benefit depends on hiding information the actual observer receives. |
| Minimal resource padding | Can constrained padding equalize declared observations with a proved transformation and measured overhead? Start with finite deterministic kernels. | Transformation preserves required functional behavior and has a clear optimality or approximation statement. | It changes tasks, hides billed retries, or is merely familiar padding without a new useful result. |
| Contract inference with validation | Can request/size invariants be inferred and then independently checked? Start with simple template/dataflow constraints. | Inference reduces annotation burden while the checker remains sound. | Learned heuristics become trusted proof premises. |
| Quantitative resource distance | Can a compositional bound on expected or worst-case observation difference help when exact equality is too restrictive? First encode examples in eRHL/RelCost. | There is a genuine automation/fragment advantage and the metric is useful. | It is sold as information leakage without an information-theoretic theorem. |
| Adapter conformance | Can generated boundary tests expose tokenizer, cap, and retry mismatches across local/adapted backends? | The resulting taxonomy and artifact generalize beyond OrchLang and independently reproduce failures. | Only intentionally broken mocks fail, or tests are described as universal proof. |
| Verified lowering | Can a translation validator shrink the trusted source-to-IR boundary? Prototype a small syntax-directed validator. | It closes a meaningful gap with manageable proof effort. | It consumes the whole project while the basic semantic claim remains unsound. |

Research questions to leave open explicitly: How does stateful provider behavior affect coupling? Which request equivalences beyond byte equality can be justified? Can caching and retries be modelled without unrealistic independence? Which observer best matches actual billing access? How much external workflow coverage is lost by boundedness? Can richer secret-dependent workflows retain utility without exposing resource patterns? These are not claims the first paper must solve.

## 14. Faculty checkpoints and execution gates

G0, baseline: independently reproduce the new witness and build. No guarantee claim proceeds while it is accepted.

G1, novelty: faculty receives a two-page comparison, six separating examples, source-access status, and proposed contribution. The key question is “what remains new under the closest prior formulation?” If no persuasive answer exists, change narrative before major proof engineering.

G2, semantics: faculty reviews observer, low-equivalence, kernels, coupling marginals, primitive assumptions, retry/failure behavior, and theorem statements. Include a deliberately invalid same-length coupling and explain why the system rejects it.

G3, implementation: corrected checker, independent semantics, regressions, and proof skeleton agree. An accepted counterexample blocks the claim immediately. Do not bury it as a threat to validity.

G4, experiment freeze: faculty approves corpus inclusion, strong baselines, primary endpoints, analysis scripts, and the $5 cost manifest before final data. The model choice must not depend on favorable final results.

G5, release: a person other than the primary implementer follows clean-machine instructions, reproduces main tables, checks proof compilation, and traces manuscript claims to artifacts. Record failures and corrections.

Suggested effort allocation: 1–2 weeks audit/novelty; 2–4 semantics/reference core; 3–6 checker/proof with overlap; 2–4 adapters/corpus; 1–2 final experiments; 2–3 writing/review. These overlap and may expand. Do not treat the estimate as permission to skip failed gates.

## 15. Publication routes and manuscript construction

**Route A: SCP research paper.** Choose this if the method has a specific defensible contribution, the formal result is correct, useful cases survive the conservative contracts, and evaluation withstands credible comparisons. The paper should explain the semantic gap, present the method and its limits, and show why the implementation is useful. More features alone will not make it stronger.

**Route B: SCP Original Software Publication.** Choose this if the strongest contribution becomes a reusable, rigorously engineered analysis/checking tool with a compelling demonstration rather than a new theory. The [EAPLS software-track call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/) describes a short software article, code/documentation, and review of software merit. Its approximate length guidance is not a verified current submission limit. Obtain the current [SCP author guide](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors), which was access-blocked here. OSP is not automatic acceptance or a loophole around correctness.

For genre calibration, inspect the open manuscript of [Fossil 2.0 in SCP](https://pure.tudelft.nl/ws/portalfiles/portal/248039296/1-s2.0-S0167642325000930-main.pdf). It is a software-publication example, not a scientific baseline for our method. Also retrieve the current SCP software examples in Section 16 through the library.

**Route C: another appropriate venue.** [STTT's scope](https://link.springer.com/journal/10009/aims-and-scope) is relevant if semantics-based verification tooling and realistic evaluation become central. [JOSS submission requirements](https://joss.readthedocs.io/en/latest/submitting.html) are relevant for mature, openly licensed research software; this is a software-publication route, not a substitute for proving a novel research claim. An institutional technical report or preprint can archive complete work but is not itself a peer-reviewed journal publication. Do not assume an arbitrary journal offers a “letter” category without checking its current guide.

Do not submit overlapping manuscripts simultaneously. If a later software paper and research paper have distinct contributions, disclose and cite the overlap and obtain the applicable editorial guidance. Do not reuse the earlier brief's blanket assumption that parallel routes are necessarily safe.

Recommended research-paper structure: (1) motivating counterexample and threat model; (2) exact contribution and prior-art distinction; (3) language and contracts; (4) analysis/checker and theorems; (5) implementation and trusted boundary; (6) evaluation protocol and results; (7) limitations; (8) related work and conclusion. Adjust ordering for readability after results exist.

Required figures/tables: observer/contract architecture; proof and implementation trust boundary; worked valid and invalid coupling; corpus census; baseline assumptions; soundness/precision/coverage results; overhead distributions; adapter mismatches; limitations matrix. Generate scientific figures from data, not illustrative invented numbers.

Write the abstract last. Each contribution sentence must have a claim ID and completed evidence. Avoid “secure,” “verified,” “first,” “zero leakage,” and “real-world guarantee” without their exact qualification. A theorem conditional on a provider contract must say so in the abstract if that condition is central.

Follow the current [Elsevier generative-AI policy](https://www.elsevier.com/en-gb/about/policies-and-standards/generative-ai-policies-for-journals): authors remain accountable and must make the applicable disclosure. Verify the submission-day policy and required wording. AI systems are not authors; every citation, result, and proof must receive human review.

## 16. Access requests for the author

Use VIT access to obtain lawful personal research copies of:

1. **Hard-KLAIM**, [publisher record](https://www.sciencedirect.com/science/article/pii/S2352220826000830). Highest priority: its full semantics, effect rules, guarantees, evaluation, and related work are necessary for the novelty gate.
2. The current [SCP Guide for Authors](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors), including research/OSP article types, software requirements, current template, data/code policies, charges/options, and any length guidance. Save the date retrieved.
3. **CAN-Verify**, [SCP publisher record](https://www.sciencedirect.com/science/article/pii/S0167642324001564), for agent-tool software-publication expectations. This is a genre comparison, not necessarily a directly comparable algorithm.

Place private copies outside publicly committed artifacts, and provide local paths to the next agent. Do not redistribute subscription PDFs. Most foundational papers in Section 4 already have open primary copies; do not spend time or money acquiring duplicate paywalled versions unnecessarily.

Ask the faculty reviewer for an early semantics meeting and a later preregistration review rather than waiting until a polished draft exists. Ask the author for a restricted API key only at G4, plus permission to consume the already specified cap with the concrete cost manifest. That request must identify provider, maximum total charge, sample design, and retained data. The user has authorized a $5 testing budget; do not repeatedly ask about the same budget once the execution details are settled.

## 17. Definition of done and next-agent operating rules

The deliverable is a **submission-ready package**, not a fabricated guarantee of publication. It consists of a correct and scoped manuscript; complete proof/assumption inventory; audited code; meaningful tests; strong baselines; frozen corpus and raw data; regenerated figures/tables; license and notices; clean-machine reproduction; faculty sign-off; and a verified venue checklist. Paid live validation can be omitted only if the final paper honestly scopes itself to offline/local/replay evidence and the chosen venue narrative remains defensible.

The next agent should first read this file, the current source, `research/2026-10-23/README.md`, and the prior audit. Then inspect the actual Git state; preserve user changes; reproduce the witness; create the claim/novelty ledger; and begin W1/W2. Do not spend the first week rewriting introductions. Do not implement the old AARA impossibility proposal. Do not assume a broad theoretical separation can be obtained merely by adding stochastic primitives.

Work autonomously on reversible offline implementation. Escalate only decisions requiring author ownership, unavailable literature, secrets, paid-resource changes, or actual submission. Keep a research decision log with rejected directions and counterexamples. If evidence contradicts the intended narrative, revise the narrative and keep the evidence. If the strongest contribution is a careful negative result about unsafe assumptions and an effective checker, publish that honest result rather than stretching the claim.

At each milestone report: completed artifacts, changed claims, current counterexamples, proof obligations remaining, corpus coverage, resource consumption, and the next gate. The project is ready to submit only when its most skeptical reader can reconstruct why the guarantees hold and where they stop.
