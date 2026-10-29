# OrchLang: independent SCP referee audit — 25 October 2026

**Manuscript:** *Source-Bound Validation and Contract-Indexed Accounting for Constant-Shape LLM Workflows* (18-page author-review PDF).  
**Artifact:** `orchlang-scp-supplementary-material.zip` (1,958 archive entries, ~685 MiB expanded).  
**Journal target:** Elsevier *Science of Computer Programming* (SCP).  
**Role:** adversarial, simulated referee and artifact evaluator, not an official journal decision.  
**Overall assessment:** **7.8/10** for research-paper publication readiness; **major revision before submission**. Scientific/engineering substance is stronger than this number; release and external-validity limits are substantive. A 9–10/10 score is not warranted on the evidence available today.

## Executive judgment

OrchLang has evolved from a compiler/token-accounting study into a bounded language with **repair of secret-dependent logical usage**, independently source-bound validation of candidate repairs, conditional Lean theorems for a core language, model-indexed accounting and a documented experimental artifact. The rewrite is not cosmetic. The artifact includes hard-to-fake negative results: timing leakage persists, poor task accuracy is preserved rather than disguised, some accounting configurations are unsupported, real deployments are not claimed to be covered, and later frontend repairs are *not* retroactively attributed to historical inference runs.

The main claim is **validly framed as conditional**: when the mathematical `World.Conforms` hypothesis holds, an accepted core has equal *ordered logical* usage traces for public-equal stores and a coupled tape. Under the separate `World.Transparent` hypothesis, the shaped core agrees in final store with erasure/original (relative to assumed extraction correctness). This is **not** a proof that physical inference servers, gateways, or API invoices reveal equal observations, nor that aborts and failures are secret-independent. The paper generally acknowledges these exclusions; they nonetheless determine both real-world significance and the claims an editor can approve.

### Reviewer scorecard (subjective)

| Criterion | /10 | Basis |
|---|---:|---|
| Journal relevance and scope | 9.0 | Programming language design, formal methods, compiler, research software and experimental validation |
| Method/software novelty | 7.2 | Distinct specialized integration; balancing, translation validation, constant resource and padding are established |
| Formal rigor *within the specified core* | 8.3 | Significant named Lean results and explicit hypotheses; toolchain-to-world refinement open |
| Experimental evidence and integrity | 8.8 | Raw source/shape/output records, version separation, negative results, strict completeness, audit scripts |
| Correctness/reproducibility engineering | 8.3 | Hash-checked package, source-custody tests, separate interpreter, audit/protocol negatives; external assets unavailable here |
| External/deployment validity | 5.6 | Nine authored bounded adaptations; no authoritative billing/gateway observer; abort/timing not covered |
| Manuscript clarity and scientific restraint | 8.1 | Clear assumptions, accurate negative results; contribution and use-case could be more immediate |
| Submission/archival readiness | 4.8 | Combined code local not publicly archived; author permission/declarations and stable identifier pending |

The composite **7.8/10** is an editorial judgment, **not** a measured acceptance probability or an arithmetic average that can be gamed by adding tests. The journal track remains to be explicitly selected. An 18-page proof-plus-evaluation manuscript is more naturally assessed in SCP's **Research Papers / Experimental Software Technology or Formal Techniques** area. The **Original Software Publication** route has specific presentation and accessibility requirements: it cannot be assumed that an 18-page research manuscript is an OSP-ready submission.

## Exactly what I independently checked

### Source package, inventory, and PDF identity

- Unpacked and inspected the ZIP, including `orchlang/`, `proof/`, `tests/`, `reference/`, `publication/`, `experiments/`, `paper/`, `legacy/v1/`, manifests and evidence directories.
- The stand-alone submitted PDF is byte-identical to **both** `paper/main.pdf` and `output/pdf/orchlang-scp-author-review.pdf` in the archive (SHA-256 `90f79a416c2a69567623ea915c35f3e1815fcce93482293819681d2ed4a13e6f`).
- Ran `python publication/verify_package.py`: **verified, 1,957 files checked, zero failures**. This checks that the retained bytes match the manifest, not that the research claims are true.
- Ran `python publication/build_evidence.py --require-complete`: successful; reports **1,172 main + 512 replication + 21 fresh conformance** paired runs, no pending completion failures.
- Ran `python -m unittest discover -s tests -v` under Python 3.13.5: **33 tests run; 31 passed, two skipped** because the required GGUF files are not configured. The manuscript's recorded configured run says all 33 passed with pinned models. My local results do not independently repeat the two model-template/tokenizer tests.
- Inspected `proof/ShapeCore.lean`, including `World.Conforms`, `World.Transparent`, `shape`, `exec`, `wt`, `sitesOK`, `validate`, `validate_sound`, `validateProgram_sound`, `secret_inputs_sound`, `shape_usage_exact`, `shape_budget_sound`, and JSON decoding. The code contains formal derivations for the named propositions and reports axiom dependencies; I did not have Lean 4.19.0 available to recompile the proof or verify its saved axiom report independently.
- Inspected representative real runtime, ledger, source-binding and validator paths: `orchlang/runtime.py`, `ledger.py`, `assurance.py`, `compiler.py`, `syntax.py`, `validate.py` and tests. This was a **targeted code audit**, not proof of absence of all defects in every line of this 685-MiB package.

### Independent raw-record reconciliation

I wrote a separate small parser to load **all** raw `orig.jsonl` and `ours.jsonl` records from the four declared study groupings and compare IDs, saved stores, shaped logical `(event type, model/tool name, input, output)` observations, and truncations. This program did **not** import OrchLang, the paper's table generator, or its manuscript numbers.

| Group | Distinct paired IDs | Saved stores equal | Distinct shaped logical traces per workflow | Recorded truncations |
|---|---:|---:|---:|---:|
| Historical, seven workflows | 962 | 962 | 1 each | 0 |
| Main completion (corrective/adaptive RAG) | 210 | 210 | 1 each | 0 |
| Qwen cross-family replication (three workflows) | 512 | 512 | 1 each | 0 |
| Fresh conformance (seven workflows) | 21 | 21 | 1 each | 0 |
| **Total** | **1,705** | **1,705** | each shaped workflow constant | **0** |

The **1,684 planned study+replication pairs** exclude the 21 separate conformance pairs. This agrees with the manuscript's denominator handling; never write 1,705 as the primary study sample size. Historical records do not carry the new `usage_complete` fields. For all 743 new pairs, **1,486 original/shaped execution records** are available; counting `execution_events` independently gives **5,831** model calls, and the count agrees with model events in the trace array for every new record.

These records substantiate that the declared saved-store and logical-shape outputs are present. They do **not** establish counterfactual response quality, independent full-state preservation, real billing, true tokenization without the external model files, absence of unrecorded failures, or correct reporting by an adversarial physical host.

### Deliberate non-claims

- I did **not** rerun the full model campaigns. GGUF weights and the source-history Git bundle described in `publication/README.md` were not supplied as a separately usable bundle, and `llama-cpp-python`/Lean 4.19.0 are not configured in my test runtime.
- I did **not** verify live-model usage against provider invoices or internet-hosted inference APIs.
- I did **not** execute `legacy/v1`'s separate C++ and four-Lean-file reproduction locally. I inspected the packaged records and claim ledger about those checks.
- I did **not** prove the trusted Python frontend/backend correct. The authors do not assert such a proof.
- Therefore, positive manuscript evidence is *corroborated by raw retained records*, not independently replicated as a complete end-to-end experiment from weight download through inference.

## Manuscript claim-by-claim verdict

| Claim/location | Judgment | Why/qualification |
|---|---|---|
| Abstract: hidden contents can still leak usage | Correct motivation | Real prior art exists on output-count and routing metadata leakage; must continue to cite it |
| Abstract: shaping compiler, executable Lean validator | Substantiated as packaged code | Core representation, validator, compiler, Lean file and source-checking path are present |
| Theorem 1: core usage-trace noninterference | Well-scoped *conditional* result | Assumes `World.Conforms`, accepted core, well-formed labels/sites, same public store and coupled tape; not physical deployment proof |
| Theorem 2: functional preservation | Conditional | Requires global `World.Transparent`, correct erasure/source binding and cap discipline; task correctness does not follow |
| Theorem 3: model-indexed shape budgets | Natural valid corollary within model | Exact triple follows fixed shape; physical request admission is partial and unproved as Lean-to-Python refinement |
| 6,320 cross-implementation finite runs | Plausibly documented and tightly versioned | Saved research manifests and scripts are present; Lean reexecution not performed here; finite char-world, not provider execution |
| 962 original retained pairs and shaped constant traces | **Independently raw-record corroborated** | Exact ID/store/trace/truncation counts; old observations lack new request/ID evidence |
| 210 main completion + 512 Qwen replication | **Independently raw-record corroborated** | Strict completeness and exact pair IDs; separate cohorts/implementations rightly maintained |
| 1,486 records / 5,831 model events | **Independently counted** | Event record counts match trace model events |
| 1.83x historical median overhead | Reported, source table and analysis included | Weighted logical input + 4 output, **not** time/currency/provider cost; some studies substantially more expensive |
| Saved outputs equal | **Raw-record corroborated** | Only saved fields, not a theorem about quality or all intermediate state |
| 100% maximum shaped latency attack | Important candid negative result | Contradicts any generalized timing-security interpretation |
| Original task scores (some very poor) | Disclosed accurately in manuscript | Calculator 1%; cannot claim utility improvement or robust application task performance |
| Two implementation branches retained | Documented separation | Companion `legacy/v1` is not shown formally translating into shaping language |
| Source-bound checker derives original and secrets | Present in Python source | Reader/lowering, binding and serialization are trusted, not machine verified; annotations define the declared secrecy policy |
| Public, stable released artifact | **Not satisfied** | Manuscript expressly states combined revision local; no persistent archive DOI, source-history bundle not separately provided |

## Major referee objections, ranked

### M1 — The conformance and operational domain are not linked by a sufficiently strong theorem

In `proof/ShapeCore.lean`, `World.Conforms` is globally quantified:

```
forall model target request,
  tok(model, padReq(model,target,request)) = target
forall model request randomness count,
  outTok(model, forced(...,count)) = count
```

The **concrete** `Padder.pad` rejects if the complete request already exceeds the padding target; the runtime also refuses requests before dispatch when a contract cannot be met. That is sensible fail-closed engineering, but it means the global abstract conformance premise is **stronger than what the physical backend offers**. For a realistic nontruncating padder, arbitrary targets smaller than a request cannot be satisfied. The paper admits a partial runtime and an unproved total refinement (pp. 3 and 7), so this is **not proof of an invalid Lean theorem**; it is a genuine gap in applying the theorem to real accepted programs. A reviewer should ask for a theorem over the **admitted domain** or for a clearly stated, invariant-restricted conformance premise with a proof that all purportedly protected executions stay in that domain.

**Minimal challenge case:** two public-equal inputs with different secret string lengths; a fixed target admits one and refuses the other. If the observer sees whether dispatch occurred, the exit/absence pattern is a leakage channel. Current theoretical traces exclude refusal/failure. A future result could model refusals as visible events and prove either both runs refuse identically or neither refuses across all admitted secrets. Without such a result, say plainly that pre-dispatch checks enforce resource safety **but not failure-observation noninterference**.

### M2 — The observer is a logical host interface; a physically authoritative observer is absent

The event alphabet includes `llm(model,input,output)` and `tool(name)`. A `dummyTool` emits a logical event without calling an external tool; a model dummy may perform real local generation. Isolated padding counts local prefill plus the original request, and natural/forced counts follow OrchLang's own token-ID conventions. These do not necessarily match provider bills, gateway-visible request envelopes, server timers, real external tool execution or network telemetry.

The paper *does* warn readers. Nevertheless, this boundary is load-bearing: if the app controls what it reports, it may simply normalize/redact the report, avoiding expensive dummy inference. The paper says the observer is entitled to **faithful logical usage records**, but provides no real authoritative gateway adapter establishing that threat model. Make the genuinely relevant deployment setting concrete (an accounting interface beyond app control, with fixed semantics and measured agreement) or frame the contribution first and foremost as an **offline programming/assurance tool** under a declared reporting contract.

### M3 — Transparency is a demanding, empirically fragile primitive premise

`World.Transparent` requires padded/forced output after visible prefix extraction to equal natural unpadded output for **all** relevant prompts, targets, lengths and randomness cells. The paper reports isolated-padding checks with 60 greedy and 60 sampled cases, plus other real-model pairs; these are encouraging *finite observations*. They do not establish a general provider/model guarantee, particularly across EOS rules, prompt-cache interactions, stochastic decoding, seeding and backend version changes. If transparency fails, the noninterference result can still apply to logical usage while **functionality may change**.

The distinction between logical isolated prefill and actual backend input usage should be emphasized earlier, next to the abstract's overhead numbers. Add a systematic falsification matrix for model families, cap combinations, temperature, seeds, stop tokens and prompt lengths with failure rates and limitations, while retaining the theorem as conditional.

### M4 — Application validity is bounded by authored adaptations, incomplete utility, and release-version separation

The nine workflow adaptations reimplement/modify tutorials and examples: their sources, model, retrieval datasets and loops differ from deployed original agents. A representative workflow is not an untouched independent system. Some task scorers are weak: routing ~64.7%, switch ~35.2%, calculator 1%; completed RAG cohorts have 28.7%, 51.7%, 37.3% task accuracy. Preserving a poor result is still useful for equivalence checking, **not** evidence of useful task execution.

The main new inference campaigns used freeze `6a24fe8`; the later frontend correction `913530b` has targeted tests and three real-model boundary pairs, with three Qwen adaptations receiving core-identity evidence. The authors accurately avoid relabeling earlier runs; a strong final acceptance package should additionally rerun a stratified subset or the full practical study on the **released** binary/source and report divergence, with matched original/shaped requests and visible results.

### M5 — The central integration and novel scientific delta need sharper articulation

Agat, Ngo et al., FaCT, Pnueli/Necula, website-fingerprinting supersequence defenses and Pacer supply prior art for shaping, constant-resource programming, translation validation and cover events. More recent papers cover LLM output-count leakage, routing metadata and privacy-aware agent communication. The paper credits these. Its original *engineering* synthesis is source-bound, model-indexed, executable and separately replayable. It needs a **one-page contribution matrix** explaining the specific unsupported use case in prior methods, why source-derived secret/contract binding makes a measurable difference, and one substantive end-to-end scenario showing a prior erroneous acceptance turned into a correct rejection or faithful repair.

Do not characterize the fixed-shape budget corollary as a new logic. Do not imply the combined C++ legacy artifact and Python shaping language share a mechanically established semantics. The draft currently respects both points.

### M6 — Reproduction can be integrity-checked locally, but not independently rerun from the public record

Hash custody is good: `verify_package.py` passed. However the manuscript says the **combined revision is local and not publicly deposited**; model weights are not included (which is reasonable if pinned), and a separate source-history bundle is mentioned but was not part of the submitted ZIP. A serious SCP software submission should have stable publicly accessible source/evidence revision, cited archive identifiers, signed/tagged release, a fresh-machine reproduction from public artifacts, and explicitly recorded optional heavyweight dependencies. Have a separate human reviewer verify at least proof check, source-bound validation, benchmark/plot regeneration and a minimal GGUF-backed run.

### M7 — Reviewer/editor-facing manuscript preparation

The 18-page PDF is appropriate in shape for a **research paper** but should not be presented automatically as a short Original Software Publication. Choose a track based on the accepted contribution. If OSP, follow that track's separate length, code-metadata and availability requirements; if research, foreground the assurance question and mechanized/evaluation reasoning more prominently.

`[16]` is visibly rendered as `Journal of Logical and Algebraic Methods in ProgrammingJournal pre-proof`; clean the reference punctuation. Verify whether all recent arXiv items are still preprints when submitting; don't imply peer review for repository-only/author-hosted work. A concise command/result example would make the software easier to assess than the high-level architecture diagram alone. Add succinct threat-model and confidence/limits figure; avoid a pseudo-quantitative accuracy claim from underpowered single-class or weak task datasets.

Author names/email are present, but the manuscript clearly says **consent, CRediT, funding/conflicts, permissions and final author accountability are still pending**. Those require genuine human confirmation. Elsevier's current generative-AI policy requires human verification and a specific preparation disclosure (tool, purpose, oversight, responsibility), plus research-method disclosure for AI-assisted code and evaluation. These are not box-ticking changes the agent may autonomously assert.

## Reference cross-check — main provenance and novelty risks

### Independently checked against external records

- **[1] Zhang, Saileshwar, Lie, `2412.15431`**: arXiv title/authors and 2024 provenance match; output-token timing attack established: https://arxiv.org/abs/2412.15431.
- **[2] Teng-Ruei Chen, `2610.09981`**: October 7, 2026 arXiv item exists and discusses content-dependent routing metadata: https://arxiv.org/abs/2610.09981.
- **[6]/[7] Translation validation**: Necula PLDI 2000 DOI and pages confirmed independently by DBLP: https://dblp.org/rec/conf/pldi/Necula00.html; Pnueli et al. TACAS cited as older foundational work.
- **[8] FaCT**: PLDI 2019 paper/DOI are real; its role as a timing-sensitive DSL is an appropriate comparator: https://doi.org/10.1145/3314221.3314605.
- **[10] eRHL**: authors, title and 2025 proceedings status corroborated by one author's academic page: https://www-sop.inria.fr/members/Martin.Avanzini/publications/ABDG:POPL:25.html. The bibliography cites an arXiv v2; consider using the final POPL journal/conference entry if appropriate.
- **[12] SICC, `2609.26076`**: externally indexed paper exists on privacy-aware multi-agent workflow communication: https://arxiv.org/abs/2609.26076.
- **[13] Dangol, `2606.07150`**: externally indexed paper exists: https://arxiv.org/abs/2606.07150.
- **[16] Hard-KLAIM**: Elsevier journal record confirms `10.1016/j.jlamp.2026.101191`, online October 9, 2026, journal pre-proof, and authors; citation is substantively grounded but final journal/pre-proof formatting is defective: https://www.sciencedirect.com/science/article/pii/S2352220826000830.
- **[17] Proof-Carrying Contracts, `2610.28484`**: released October 20, 2026, correct authors; it is an arXiv preprint, not an established SCP paper: https://arxiv.org/abs/2610.28484.
- **[18] Token Budgets, `2606.04056`**: arXiv work exists, but remains a preprint/author project: https://arxiv.org/abs/2606.04056.

### Bibliographic cleanup / limitations

- Other old foundational entries ([3] Agat, [4] Ngo et al., [5] Wang et al., [9] RelCost, [11] Pacer) are well-known compatible precedents as described. Their precise metadata was not exhaustively DOI-revalidated in this pass; compare final BibTeX to publisher records before submission.
- [14] CaMeL and [15] FIDES should remain distinguished from the exact logical-usage observer, not counted as direct-equivalent attacks or verified work on OrchLang's same property.
- [19] author-hosted resource-cost report, [20] Costwright repository, [21] Typed Resources repository should be labeled **non-peer-reviewed artifacts** (as the supplement often does). Recheck their precise versions and persistent links.
- **No obvious fabricated central citation emerged from this spot-check.** This is not an assertion that every bibliography field, page number, preprint version, or accompanying 65-KB literature inventory has been independently validated.
- Literature coverage is valuable, but the novelty section should explicitly compare attack assumptions, observer power, real work performed by dummies and whether a defense changes a provider-visible trace or only an app-visible log. This is more important than expanding the bibliography again.

## Recommended next experiment and proof plan (publication gates)

1. **A strong, falsifiable admission/refusal theorem or protocol.** Incorporate `refuse`, `fail`, and `unknown dispatch` into a visible observation semantics; prove same-status admission for all public-equal secret stores in the advertised supported domain, or prove an explicit restricted-domain theorem and explain how to check its premises. This is the largest mathematical safety gap to physical applicability.
2. **Independent observation fidelity study.** Implement one supported, fully disclosed authoritative local gateway or billing-proxy instrumentation path; log both physical and OrchLang logical events and show precisely which semantics match, which differ (dummy tool, isolated prefill, EOS), and where leaks remain. Keep claims local and bounded. If provider billing is not representative, label the experiment accordingly.
3. **Release-version matched tests.** Freeze the next release and rerun at least carefully pre-registered boundary-rich subsets across both model families, nontrivial RAG branches and several stochastic settings. Record all negative/mismatch outcomes and produce a mechanized source-to-execution assumption ledger.
4. **Compare against established alternatives.** Add trace normalization/redaction (when observer permits), all-branches dummy execution, uniform model-indexed cells, random padding and unshaped execution with the same real backend and same observation alphabet. Give confidentiality/utility/usage trade-offs, not just weighted overhead. Include a case where OrchLang is less useful or more expensive.
5. **Third-party adoption/replay.** Supply a simple CLI example, external bounded-workflow case not hand-tailored to tests, and ask one independent colleague to reproduce package checks, Lean theorem compilation, failure-domain counterexamples and one model-backed dataset slice from a fresh machine.
6. **Finish research submission custody.** Publicly archive authorized code/evidence with hashes, paper sources, linked model fetches and explicit excluded artifacts; finalize authorship, contributor roles, funding, competing interests, dataset/license permissions and the generative-AI preparation declaration. Choose SCP track after reviewing its current official Guide for Authors.

## Overall editorial recommendation

**7.8/10 — Major revision, credible SCP research-paper candidate.** The scientific transformation from the earlier draft is impressive *in verifiable substance*: new formal statements, real retained paired runs, versioned replication, failure-path controls, independently parseable records and candid negative results. For an **Original Software Publication**, submission completeness is poorer until the source is publicly deposited, third-party use is demonstrated, and OSP-specific presentation requirements are met. For an **SCP research paper**, a review may reasonably proceed after formal correction of the observation/domain boundary, a more explicit independent deployment example, and cleanup of release metadata; the outcome remains editor/reviewer-dependent.

**Do not describe the theorem as wrong solely because assumptions are unproved in physical deployment.** It is a meaningful conditional formal result. Conversely, do not describe good finite testing as proving those assumptions. The distinction is exactly where the publication bar lies.

## External source links and official policy

- SCP scope / two tracks: https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423
- SCP Guide for Authors (official; access may vary): https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors
- Current Elsevier AI authorship, use and disclosure policy: https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals
- ICCheck 2026 SCP OSP example: https://www.sciencedirect.com/science/article/pii/S0167642326000389
- Hard-KLAIM journal metadata: https://www.sciencedirect.com/science/article/pii/S2352220826000830
- Core arXiv links listed above.

## Independent checks and local reproducibility notes

Verified commands and outputs:

```
cd <unpacked supplementary archive>
python publication/verify_package.py
# {"status":"verified","files_checked":1957,"failures":[]}
python publication/build_evidence.py --require-complete
# completed_main_pairs=1172, completed_replication_pairs=512,
# fresh_conformance_pairs=21, completion_failures_or_pending=[]
python -m unittest discover -s tests -v
# Ran 33 tests; OK (skipped=2) [GGUF model files not configured]
```

Independent raw audit: read `experiments/results/runs/*/{orig,ours}.jsonl` and `publication/evidence/completion/{main,replication,conformance}/*/{orig,ours}.jsonl`, join on `id`, compare saved `store` exactly and project logical `trace` into ordered `(type, model/tool, input, output)` events (tool events omit counts). Verify no duplicate IDs, exact paired sets and all-zero `truncations`, count one shaped trace per workflow; compare `execution_events` length against projected LLM event count. Checks gave **1,705/1,705 saved-store equal** across study and separately labeled conformance, **1,486** new raw execution records and **5,831** model events.

No model file, Lean binary or source history is reproduced by merely storing this report; these remain documented verification gaps.
