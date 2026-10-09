# Remote branch audit: OrchLang research and demo branches

**Audited:** 9 October 2026  
**Baseline:** `origin/main` at `a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9`  
**Research branch:** `origin/claude/new-session-tvgdhj` at `34277749c70ccfa0cbd9c188568b72c19e1fff4f`  
**Demo/case-study branch:** `origin/claude/demo-pipeline-setup-ixsbbd` at `eafe2d09411a5892caa0a3cc66dcd488548ce1fc`

This is a read-only comparison; neither remote branch was checked out, merged, or edited. The branches are divergent from the baseline, and the demo branch is not based on the research branch. I inspected their source, tests, corpus protocols, paper and case-study artifacts in temporary archives, then compared their claims with the current bounded compiler and the current source-faithful study plan. The research branch changes 227 files (27,614 insertions, 2,775 deletions); the demo branch changes 68 (5,095 insertions, 240 deletions).

## What is already in the current bounded compiler

Several changes that were real advances over the original baseline are already present in the current working tree. Its relational pass compares resolved model contracts, exact decoded template/literal content, lexical identities for outer values, and positional references to matched earlier results. It preserves public choices and bounded retries in ordered signatures, aligns branch-local values, and rejects mismatched secret alternatives. The current language also tracks token units for generated values and rejects cross-model/tokenizer reuse without a conversion contract (`E267`). See `src/relational.cpp`, `include/relational.hpp`, `src/semantic_analyzer.cpp`, and `docs/LANGUAGE_SPEC.md`.

Therefore, the research branch’s early fixes for equal-size/different-content requests, model aliases/shadowing, and dependent second calls should not be presented as absent from the current compiler. The current work already addresses those cases with its exact request atoms and dependent-result correspondence. The research branch remains useful for identifying further extensions, below.

| Research-branch contribution | Current bounded compiler comparison | Audit judgment |
| --- | --- | --- |
| **Enumerate feasible secret resolutions and compare whole-program signature classes.** The research analyzer derives the signatures reachable under guard-outcome vectors, counts distinct signatures `k`, and supports a `log₂(k)` leakage bound; its corpus also tests cancellation across nested/combined guards. | Current analysis is a conservative compositional match obligation at secret-controlled branches. It establishes equality when its local signatures match, but does not enumerate feasible global outcome vectors or expose a quantitative class/leakage budget. | A substantive extension if retained with explicit assumptions. It can avoid some compositional false positives and quantify a chosen observer, but must not be described as required to repair the current exact-signature soundness argument. |
| **Compare coarser observer views.** The paper develops trace/provider/bill normal forms and classifies leakage under selected observers. | Current claim concerns its stated abstract per-contract billing/usage observation; it does not provide the research branch’s general observer-parameterized class analysis. | Potentially useful as an optional analysis mode. State precisely what the observer can see; do not imply that invoice access or a per-request trace is universal. |
| **Empirical and structural tokenizer-density contracts.** The branch adds `κ·bytes + σ`-style per-tokenizer contracts, response-byte/decoding assumptions, tokenizer measurements, and a guaranteed input-bound path. | Current token accounting deliberately uses a declared UTF-8-byte divisor plus declared value bounds and a complete-request additive-accounting premise. It identifies provider framing, tokenization boundaries, and real tokenizer identity as assumptions; it does not claim measured tokenizer contracts. | Useful supporting evidence, but the measured sample cannot establish a universal bound. A sound integration would need tokenizer/version identity, a structural argument for the entire contract, and clear separation between measured examples and guaranteed facts. |
| **Size-blindness theorem** for analyses that observe text constants only through a size measure. | Current paper/review emphasizes the limitations of size-only equality but does not rely on this Coq theorem as a current implementation theorem. | A useful abstract impossibility result under its explicit “fresh twin” and workflow-shape assumptions. It does not establish that every practical size abstraction has the required fresh twins. |
| **Corpus and source audit protocol.** The branch fixes candidate sources/split before porting and records exclusions/adaptations. | Current work has its own newer source-bound evidence, including source graphs and an ongoing study over unmodified source. | The pre-registration discipline is reusable. The specific ports are partial abstractions, not unmodified-source compiler runs or evidence of upstream adoption. |

## Coq: what is proved, and what is not

`proofs/OrchLang.v` is a **standalone mechanized model**, not a proof connected to the C++ parser, IR, analyzers, interpreter, certificate, or current implementation. Its header says so explicitly. It defines its own syntax, flat store, provider, retry validator, event semantics, and request-equivalence judgment. The paper argues, but Coq does not prove, that signatures computed by the implementation yield derivations of that judgment.

The principal theorems are:

* `equiv_sound` (Lemma 2): programs related by the Coq request-equivalence judgment generate the same history on every shared tape and leave related stores.
* `resolve_exact`: resolving secret guards according to a store’s outcome vector preserves execution, under the condition that the program does not assign secrets.
* `request_trace_noninterference` and `observers_agree` (Theorem 1): if the two resolved programs satisfy that judgment and stores agree on public variables, their histories agree for every tape; consequently any function of those histories agrees.
* `unary_bound` / `guaranteed_bound` (Theorem 5): abstract input/output usage is bounded under the provider cap, response-byte bound, tokenizer-density-plus-envelope contract, and well-formed byte-bound hypotheses.
* `size_blind` (Theorem 6): an analysis that sees constants only through a measure and is sound for total output tokens must reject a feasible secret branch whose then-arm has a positive-cap call containing a constant with a same-measure “fresh twin.” The twin must contain a character absent from every program text constant; the theorem’s shape and feasibility assumptions matter.

The model includes dependent call results in its store and retry bodies, and its request-equivalence relation aligns variables/results. That supports a pointwise argument for dependent calls **inside the abstract calculus**. It does not prove that the current C++ matcher is complete, that its binding correspondence implements the Coq relation, or that runtime data matches the modeled store. Request/template pieces and guards are simplified abstractions, not the full typed OrchLang AST, declarations, parser, model contracts, output labels, certificates, or source-graph semantics. There is no Coq treatment of machine-width saturation, sentinel rejection, C++ overflow behavior, UTF-8 decoding implementation, or concurrency. The byte and token bounds are hypotheses, not derived tokenizer facts.

The research paper marks coupling validity, quantitative leakage (`log₂ k`), coarser-observer results, completeness, tokenizer contracts, and the implementation correspondence as not mechanized. In particular, the mechanized noninterference result is per shared tape; the probabilistic coupling argument that maps this to a distributional statement is outside the proof. Thus Coq is meaningful evidence for the abstract lemmas, but cannot be counted as a mechanized proof of the current compiler or as evidence that the current implementation’s relational/cost semantics are newly proved end to end. Reuse is viable only as a separately versioned formal model with an explicit correspondence plan; it must not be attached to current code claims without proving that connection.

The branch paper’s stronger tokenizer result is conditional too: the token-density and decoding properties are assumed in the Coq section. Measurements on 14 tokenizers are evidence about those measured revisions and strings, not a proof of a universal density bound. T5/XLM-R are called unverified in the branch’s own discussion. The size-blindness result is a model-level theorem, not a proof about which abstractions are used in every deployed compiler.

## Corpus and evaluation limits in the research branch

The research branch pins 52 candidates from three sources (Anthropic Cookbook, LangGraph tutorials, AgentDojo), ports 30 and excludes 22. The split is 15 development and 37 held-out candidates, with eight development ports and 22 held-out ports. It reports 6,000 seeded mock runs and zero observed certificate violations. These are branch-reported counts; they are not a fresh independent rerun of its full benchmark here.

The study explicitly reports that **none of the corpus candidates declares a secret**. It therefore evaluates flow labels, cost bounds, and source expressiveness, but does not exercise secret-conditioned billing noninterference on a real source workflow. AgentDojo entries are ground-truth plans converted into fixed workflows, not the original tool-using agents. The 30 artifacts are hand-ported OrchLang abstractions; several omit or alter source behavior (response parsing, early exits, structured responses, data-dependent loops). Some ports impose limits absent from the source. This is not a defect hidden by the authors: the protocol lists the adaptations and says whether the cost bound still applies. It does mean their “real workflow” evidence is not source-faithful execution or adoption.

There are also methodological qualifications:

* The protocol commits the candidate set, split, and initial labels before porting. After the held-out results, D5–D7 change scoring and source-text matching: extra diagnostics are treated as imprecision, and the minimum prompt-text match is relaxed for some dynamically assembled strings (including whole constants as short as three characters). These deviations are disclosed, but held-out agreement is not untouched pre-registered scoring after those changes.
* `verify_sources.py` checks for text substrings in source string constants. It does not prove data-flow correspondence or behavioral equivalence between a port and its source.
* The AgentDojo cross-check classifies a run using tool-function names and call multiplicities, not arguments or full semantics. Its outside-plan/within-plan labels should be read at that declared granularity.
* The local SmolLM2 experiment has 15 equal-token-length request pairs. Each pair differs at least once across its repeated trials, but not every individual paired generation differs; it is evidence for a small local model, not hosted-model prevalence.
* The size-blindness theorem’s “fresh twin” assumption and branch shape are necessary hypotheses, not established for every size abstraction in practice.

This corpus can still contribute candidate patterns, exclusions, and an auditable protocol. The current source-faithful workflow study, which runs upstream source with captured calls/retries/human gates and makes no compiler-translation claim, is a stronger basis for claims about source behavior. Keep the branch corpus as a separate authored-port experiment rather than merging its counts into source-faithful counts.

## Demo and incident case-study branch

The three demo-branch commits add an offline 13-scene demonstration, presenter guide, scripted rehearsal, CI verification, and 12 manually authored vulnerable/repaired OrchLang scenarios. They do **not** add a new compiler analysis or static correctness fix; the compiler implementation is unchanged relative to that branch’s baseline. The scenarios cover eight reported prompt-injection incidents/probes (GitHub MCP, Supabase MCP, EchoLeak, LangChain `LLMMathChain`, Gemini calendar, Agentforce ForcedLeak, Comet, MCP tool poisoning), plus credentials in prompts, retry budget overrun, a constructed billing side channel, and an out-of-scope DPD chatbot.

The case-study report gives the essential limitation clearly: none of the original systems was written in OrchLang, and the models do not show actual remediation or product detection. A result means only that the authored abstraction is rejected/accepted under OrchLang’s declarations and policy. Some source behavior is intentionally simplified; “repaired” files may add declarations, endorsements, or safer workflow structure chosen by the authors. Treat these as motivating scenario illustrations and regression ideas, not external workflow ports, independent compiler validation, or evidence that the named products were vulnerable for the exact modeled reason. The current source-faithful incident study is the right place to report raw-source findings; any overlap should be labeled as an authored comparison.

One external-evidence distinction worth preserving: the GitHub MCP report describes an architectural agent-workflow problem and explicitly says it is not a defect in the MCP server code itself. Do not shorten this to “GitHub MCP vulnerability.” Likewise the Comet report notes that later testing did not establish a complete mitigation. Keep incident labels and mitigation claims tied to each cited source’s wording/date.

## Validation and artifacts

I inspected the full Coq file and relevant paper/protocol sections, the current relational/cost contract, commit histories, case-study report and reproduction scripts. In temporary archives, the research branch’s `make check` passed 137/137 C++ tests plus its example corpus. `make proofs` could not run because `coqc` is not installed in this environment; therefore I did not locally reproduce the paper’s Coq build. The demo branch’s `./verify.sh --quick` passed its build, 95/95 tests, example corpus, benchmark reproduction, 36-step demo rehearsal, and case-study result reproduction; quick mode skips sanitizers. The branch docs report additional Linux/macOS CI and sanitizer runs, which were not independently rerun here. The manuscript PDF was present in the archive, but the current environment lacks `latexmk`, `pdflatex`, and `bibtex`, so I did not rebuild it.

### Relevant history

* Research protocol/candidate manifest: `256b045b8a247c7fe6e0dc200dd3b7ddbf0958dd`.
* Development ports/frozen compiler: `42f837d2c43594e237e1ec5aa9eaba1f39e3ca88`; held-out split freeze: `c49c03d6e13f9360681a9de1cbdc4f153ab0be19`.
* Held-out corpus and AgentDojo cross-check: `bec0a6299cf19de3ba89fa84f424e25478a85b32`.
* Coq development: `27e0f98cd8365f79763e27c880ff6c3d30354620`.
* SCP manuscript draft: `1c819c3bf1340a2d33843c4d4a0ee371df2b6b27`.
* Demo/case-study branch: rehearsal `5bc25c20d63321457f33782b841ab53990514272`; cases `4364b58817770815f8d6109f3d0d58eceb29bf37`; final survey commit `eafe2d09411a5892caa0a3cc66dcd488548ce1fc`.

The research branch also contains a substantial SCP manuscript package (Elsarticle source, figures, references, PDF, cover letter/highlights/bundle). It still contains submission TODOs for author affiliation/contact, CRediT/funding, license/DOI, AI diagram-tool policy and journal-guide review; the cover letter date/contact need completion. It should not be described as submission-ready based solely on a generated PDF.
