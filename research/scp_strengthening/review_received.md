# OrchLang 0.5.0rc2 — Complete SCP Publication Review

Major revision recommended

Manuscript: OrchLang: Replayable Verification of Declared LLM Usage Observations Target journal: Elsevier's Science of Computer Programming Submission category: Original Software Publication (OSP) Reviewed: October 14, 2026

## 1. Updated verdict

Overall publication-readiness score

# 7.2/10

Up from approximately 6.5–7/10

My independent reviewer-style judgment, not an official journal rating or statistical acceptance probability.

The revised OrchLang manuscript is scientifically stronger than the previous version. The improvements are meaningful, technically defensible, and directly address problems identified during the earlier audit.

However, I still would not award it 9–10/10.

The primary obstacle has changed. Previously, I was concerned about software-revision inconsistencies, missing formal justification, weak scaling evidence, and insufficient external validation.

Three of those areas have materially improved. The new evaluation, however, exposes a significant usability limitation: zero out of 59 externally selected Python candidate files could be admitted by the existing frontend.

That result is honestly reported, which improves the scientific credibility of the paper. But it prevents me from concluding that OrchLang is ready for widespread research use with actual LLM-agent code.

## 2. Detailed scorecard

| Criterion                      | Previous assessment | Current |
| ------------------------------ | ------------------- | ------- |
| Relevance to SCP               | 9.0                 | 9.0     |
| Technical originality          | 6.5                 | 7.0     |
| Formal-methods rigor           | 6.5                 | 8.0     |
| Software engineering quality   | 7.5                 | 8.5     |
| Experimental rigor             | 6.0                 | 8.0     |
| Scalability evidence           | 5.0                 | 7.5     |
| Real-world applicability       | 5.0                 | 4.5     |
| Reproducibility infrastructure | 7.5                 | 9.0     |
| Scientific presentation        | 6.0                 | 8.0     |
| Submission completeness        | 4.0                 | 5.0     |

These scores are judgments based on the revised manuscript, the publication-upgrade repository documentation and implementation excerpts, and the earlier independent audit. I have not freshly executed the complete `0.5.0rc2` release in this review, so the new experimental counts remain reported results rather than independently reproduced ones.

## 3. What has genuinely improved?

Machine-checked refinement theorem

The paper now includes a theorem about agreement between node-entry snapshot semantics and lowered register execution for a normalized straight-line fragment.

I inspected `proofs/publication_upgrade/AtomicUpdates.v` in the publication-upgrade branch. It specifies a deterministic history/request oracle, tracks state-field reads, and proves agreement of request histories and local results under its `safe_after` premise.

This is substantive formalization, not merely a theorem stated in prose. However, the Python parser, final returned state and complete graph semantics remain outside that proof.

Measured optimization rather than unsupported performance claims

The new paper reports a paired scalability study against the earlier implementation, including five measured repetitions per workload size.

This directly addresses the previous unexplained resource limit.

Reproducibility and software provenance

The earlier paper-revision mismatch has been addressed through explicit source/evidence custody checks, a frozen software revision and a separate manuscript identity.

I confirmed that GitHub contains the declared `dd97af2ac714f8c0dbf5ddb63ac29cbdb4a2d0dc` revision, and the publication-upgrade guide documents the corresponding reproduction procedure.

More careful literature positioning

The paper now explicitly acknowledges relevant agent information-flow control research, token profiling, prompt-cache timing, and existing probabilistic-programming methods.

That is important because established tools such as Agentproof already support extraction from multiple agent frameworks, and their capability is an appropriate point of comparison.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://arxiv.org\&sz=32)

arxiv.org



### The most convincing quantitative improvement

Reported certificate replay performance, 64-call case

0 ms40 ms80 ms120 ms160 msPreviousCurrent

Lower is better. The manuscript reports paired measurements from a controlled workload.

Median replay-time reduction

## 36.8%

The previously inconclusive 128-call case now produces a replayed equality result under the default limits, while 256 calls still return `unknown`. This is a measured improvement, not proof of general scalability. The paper correctly distinguishes estimated internal work meters from actual memory measurements.

## 4. The central unresolved problem: external usability

Original external Python source admission

# 0 / 59

candidate files admitted

59 candidate files across 9 of the 12 selected repositories. All were rejected by the evaluated Python grammar.

The manuscript breaks the rejection causes into four categories.

09182736Unsupported importsTop-level import st…Annotation formsTop-level condition…

First reported rejection for each of the 59 external candidate files.

This is consequential for an SCP Original Software Publication. SCP's Software Track is intended to disseminate useful existing software, rather than treating the paper alone as the principal contribution.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://shop.elsevier.com\&sz=32)

Elsevier Shop



A reviewer may ask:

> If none of the independently selected programs can pass the source frontend, how useful is this tool to researchers working with existing LLM-agent frameworks?

There is an important distinction: 0/59 is not the acceptance rate for OrchLang as a whole. The tool supports its own source language, direct request-graph inputs, and specific modeled workflows. The incident-triage study also provides separate, source-specific evidence.

Nevertheless, the external study establishes that the current general-purpose Python frontend has extremely limited applicability to the sampled real source files.

This is the single biggest remaining obstacle to a 9/10 assessment.

## 5. Detailed critical reviewer comments

### Major issue A — The formal theorem is narrower than the advertised workflow verification

The new theorem is valuable, but what does it establish?

It connects two representations of a straight-line sequence of calls under an important side condition: a later call must not read, from the original state, a field that was already updated by an earlier lowered call.

It does not establish:

- That the Python AST frontend always extracts the correct intermediate representation.
- That arbitrary LangGraph programs preserve their semantics after translation.
- That returned final states agree in every accepted program.
- That the entire request-equivalence or trace-law checker has been mechanized.
- That the provider's actual usage records satisfy the declared observation model.

I would want the manuscript to present the full reasoning chain explicitly:

Original Python / LangGraph program

AST extraction — partially validated, not proven

Normalized source intermediate representation

Machine-checked straight-line refinement, under premises

OrchLang request graph

Finite-model analysis and independent certificate replay

Verified declared observation-law property

Every arrow must state separately whether its guarantee is machine-checked, experimentally tested, or assumed.

A useful next formal-methods contribution would be to extend the current theorem to returned-state updates and compositional multi-node execution. That would close a meaningful gap between real LangGraph semantics and the model being verified.

### Major issue B — Model fidelity is still an assumption

Section 4.2 now reports local `tiktoken` comparisons across 90 paired call texts and additional authored controls.

That is useful engineering calibration. But comparing local BPE encodings with a character-based estimator does not demonstrate equivalence to actual provider-observed usage, which may depend on request envelopes, tool schemas, hidden formatting, caching and model-specific handling.

For publication, the paper should define at least three distinct observers:

| Observer                              | What can be claimed                                          |
| ------------------------------------- | ------------------------------------------------------------ |
| Declared abstract observer            | Mathematical claims within the specified model               |
| Locally calibrated tokenizer observer | Measured agreement or error against specified tokenizers     |
| Real API usage observer               | Empirical agreement or error against returned usage metadata |

Right now, the first is the strongest; the second has limited empirical support; the third remains unvalidated.

I would not require real provider integration for every theorem. But a modest, reproducible real-API experiment would strengthen the practical significance of the software—provided the manuscript clearly separates empirical observations from formal guarantees.

### Major issue C — The benchmark still lacks difficult natural programs that work

The current corpus is scientifically useful as a negative result. But it cannot show that the extracted models preserve requests, results and usage observations for naturally occurring external code because no candidate was admitted.

A stronger evaluation should contain both successful and unsuccessful external programs, selected using a documented protocol.

For every supported program, it should compare the original program and extracted graph using identical deterministic oracle histories, including positive and negative cases, rejected unsupported behavior, output records and request identity.

The critical standard is not achieving a particular admission percentage. It is demonstrating nontrivial faithful admission without silently broadening the assumptions or weakening the verifier.

### Major issue D — Some performance evidence remains too narrow

The seven-size benchmark is an improvement over the old version. Still, it measures a symmetric chain family.

A strong formal-methods software evaluation should also vary branch count, dependent request history, mutable registers, cycles, oracle support, observation alphabet and stochastic-model size.

Otherwise, an optimization can perform well on repeated certificate prefixes while still becoming impractical under other common state-space structures.

I would also clarify the phrase “11/22 pinned LangGraph backend/frontend tests” on page 4. Does this mean two suites containing 11 tests each, or 11 passes out of 22 attempts? The former is plausible from the context, but the written expression is ambiguous.

### Major issue E — The presentation still undersells the tool's actual operation

The manuscript is now six pages, includes an architecture figure, and is more focused. Visually, the paper is cleaner than the earlier draft.

However, the architecture figure on page 2 remains very small and abstract. It does not show a concrete user task.

For an OSP, I would substitute or supplement it with a compact end-to-end example that demonstrates an actual input, the selected observation contract, one checker invocation, and its certificate or counterexample.

The strongest version would let a reader understand the tool's value in under a minute.

## 6. Publication risks ranked by severity

| Risk                                       | Severity | Why                                        |
| ------------------------------------------ | -------- | ------------------------------------------ |
| No externally admitted candidate files     | Critical | Limits demonstrated transferability        |
| Source-to-graph correctness incomplete     | High     | Creates an important assumption boundary   |
| No observed real-provider usage validation | High     | Limits practical accounting claims         |
| Benchmarks concentrated on authored inputs | High     | Limits generalization                      |
| Human author details/declarations missing  | High     | Prevents final submission                  |
| No persistent capsule identifier           | Medium   | Weakens long-term artifact accessibility   |
| Limited external human reproduction        | Medium   | Independent artifact usability unconfirmed |
| Presentation density                       | Medium   | Reduces accessibility to SCP reviewers     |

The revised manuscript explicitly acknowledges most of these limitations. That is a strength, but acknowledging a gap is different from resolving it.

## 7. What I would do next to reach 9/10

I would organize the remaining work into four release gates, in this order.

Gate 1 — Make the source frontend useful on independent programs

Implement safe handling for the common unsupported import patterns and annotations identified in the frozen corpus. Keep unsupported dynamic behavior as explicit rejection.

Freeze a fresh held-out corpus before making changes, then publish the number of admitted programs, rejection reasons and semantic-differential results.

Exit condition: Demonstrate several nontrivial, independently developed programs that are faithfully extracted and verified. Report all unsuccessful cases.

Gate 2 — Strengthen the source-level correctness argument

Extend the normalized-IR proof to final returned-state agreement and compositional execution where feasible.

Add adversarial differential tests for schema handling, Python name resolution, state updates, exceptions and branch behavior.

Exit condition: Every supported translation rule has a documented semantic obligation, with proof or independent differential evidence.

Gate 3 — Demonstrate practical and computational value

Add a second independent case study where OrchLang identifies a real request- or usage-observation property. Benchmark realistic graph structures and provide measurements for all success, inequality, inconclusive and resource-unknown outcomes.

Introduce optional real-provider usage calibration without changing the mathematical assumptions of the core checker.

Exit condition: Demonstrate an independently useful finding, reproducible baselines and documented computational limits.

Gate 4 — Complete the scholarly release

Have an independent researcher reproduce the installation, selected proofs, certificates and experiments from a clean checkout. Freeze the release, obtain a persistent archive identifier and finalize human-reviewed authorship and declarations.

Exit condition: One unambiguous archived version, complete provenance, independently reproduced evidence and a fully compliant manuscript.

## 8. Publication score projections

These are scenarios for future reviewer-readiness, not promises of acceptance.

0/102.5/105/107.5/1010/10Earlier draftCurrent rc2Faithful external extraction+ Strong case studies and proofs+ Independent release validation

Illustrative editorial-readiness judgments assuming the specified improvements are independently demonstrated.

I would not expect formatting improvements, additional synthetic tests, or a longer bibliography alone to produce those increases. The gains would need to come from demonstrable engineering and scientific results.

## 9. SCP-specific editorial judgment

The journal's scope includes programming languages, software verification, tools and experimental software technology. Its OSP track is a suitable home for research software such as OrchLang.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://shop.elsevier.com\&sz=32)

Elsevier Shop



I would distinguish three decisions:

| Editorial question                                                        | My judgment     |
| ------------------------------------------------------------------------- | --------------- |
| Is OrchLang in scope for SCP?                                             | Yes, strongly   |
| Does it contain a defensible research-software contribution?              | Yes             |
| Is the current manuscript ready for acceptance?                           | Not yet         |
| Would I recommend external review after submission details are finalized? | Yes, reasonable |
| What would I recommend as an external reviewer today?                     | Major revision  |

The current PDF still has explicit author-name, affiliation, correspondence, CRediT, funding and competing-interest placeholders. These are submission-completeness problems, distinct from technical merit. They must be completed by the responsible human author before submission.

The paper's reported proof, replay, benchmark and negative external-admission results are substantially more credible than broad claims that could not be reproduced or falsified. That makes this a stronger scientific paper even though it remains imperfect as a broadly usable software tool.

## 10. Final reviewer decision

Scientific maturity

## 8/10

Practical transferability

## 4.5/10

Overall publication readiness

## 7.2/10

Recommendation: Major revision

The current research candidate merits continued pursuit of SCP's Software Track. Its strongest contribution is an independently replayable verification pipeline for declared LLM usage observations. Its primary weakness is the limited demonstrated connection between that pipeline and naturally occurring external programs.

### My most important recommendation

Do not make the next release primarily about adding more mathematics or increasing test counts.

You now have credible formal reasoning, exact finite-model analysis, reproducibility infrastructure, a measurable optimization and a well-scoped software contribution.

What you still need is an exceptionally convincing answer to one question:

Can another researcher take an LLM workflow they did not design for OrchLang, use OrchLang to establish a meaningful property about it, and independently reproduce the result?

If the next release answers that question convincingly—without compromising semantic soundness—I would be prepared to reconsider the score in the 9/10 range.

That is where I would concentrate the next development cycle.