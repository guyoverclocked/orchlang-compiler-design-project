# Prior-art and publication assessment

Review cutoff: 24 October 2026. Target selected by the user: **Science of Computer
Programming (SCP)**. This is a source-based research assessment, not a guarantee
of priority, an exhaustive systematic literature review, or an acceptance forecast.
The comparison includes both frozen parents and the isolated combined revision.

## What each body of work contributes

| Dimension | Latest disk work, `cef4772` | Incoming work, `9134aae` | Combined revision, campaign `6a24fe8` / corrected frontend `913530b` |
|---|---|---|---|
| Central method | Conservatively check bounded workflow costs and relational request/cost certificates | Repair bounded workflows by padding and aligning usage traces; validate the transformed core in Lean | Source-bound validation of repair with explicit execution/accounting contracts and independent operational checks |
| Useful capability | Token accounting, provider/revision identity, retained request evidence, framework/tape checks | Bounded loops, secret-dependent routing, dummy calls and forced output lengths | Both capabilities remain available; they are connected through explicit contracts rather than pretending the two languages are identical |
| Strongest fresh evidence | 106 C++ tests, 82 Python tests, four Lean files; exact accounting and retained framework reproduction | 1,000 generated programs, 5,000 Lean checks, 16,000 mock comparisons; 962 real-model paired observations re-audited | Extended proof, request/response contract checks, immutable manifests, full tool observer, independent interpreter versus production runtime versus Lean execution |
| Important limit | 24 local-model pairs; 22 independently repeated equal outputs; applications include explicit hybrid compositions | Unfinished experiments, stale paper tables, trusted source labels, unchecked runtime conformance, heuristic token envelopes | Human review, public archival deposition and external reproduction remain distinct; core-to-production refinement is tested, not proved |
| Confidentiality policy | Includes policies against exposing secrets to prompts or sinks | Model is trusted with secret prompt content; usage observer is separate | Preserve both policies and state which one a result uses |

The disk's source certificate accepted 64/80 authored source cases versus 8/80
for its older syntactic rule. That is an eightfold acceptance count on this grammar,
not an eightfold improvement in security or real application coverage. Its aggregate
observer accepted 28/256 cases versus 16/256 for its ordered observer; the 12 gains
deliberately have different ordered traces. Neither result permits replacing the
ordered observer in the shaping paper by aggregate counts.

The incoming work substantially enlarges application evidence and adds a useful
repair mechanism. It does not supersede exact accounting or implementation
custody. The combined version repairs concrete gaps identified by the audit and
retains the stronger evidence from each parent.

The planned missing experiments have now completed: 210 additional main pairs
and 512 Qwen replication pairs, plus a separate 21-pair conformance subset.
`STUDY_OUTCOME.md` quantifies the change and distinguishes completed local
checks from the remaining scientific and human publication obligations.

## Closest technical precedents

| Primary source | Established contribution that must be credited | Specific relationship and remaining delta |
|---|---|---|
| [Agat, Transforming out Timing Leaks](https://doi.org/10.1145/325694.325702) | Program transformation removes timing differences by balancing control flow | Branch balancing is established; the present specialization operates on model-contract and usage events with bounded workflow loops |
| [Ngo et al., Verifying and Synthesizing Constant-Resource Implementations with Types](https://www.cs.cmu.edu/~janh/assets/pdf/NgoDFH16.pdf) | Information-flow typing, resource analysis and constant-resource synthesis already combine | The paper cannot claim this general combination as new; its contribution is the LLM execution contract and auditable implementation |
| [RelCost](https://www.cs.cmu.edu/~janh/papers/CicekBGGH17.pdf) | Relational cost analysis relates two programs and their costs | Comparing two resource distributions is not a new general concept |
| [A Monadic Framework for Relational Verification](https://people.mpi-sws.org/~dg/papers/popl18.pdf) | Monadic relational reasoning encompasses cost properties | The current finite workflow core is less general; implementation specialization and evidence must carry the contribution |
| [Raising Expectations](https://arxiv.org/abs/2006.14010) | Automated expected-resource reasoning for probabilistic programs | No claim that probabilistic resource reasoning originates here |
| [eRHL, v2](https://arxiv.org/abs/2407.17127v2) | Quantitative probabilistic relational Hoare logic | OrchLang supplies a restricted executable validator, not a more expressive relational logic |
| [FaCT](https://cseweb.ucsd.edu/~dstefan/pubs/cauligi%3A2019%3Afact.pdf) | Language/compiler support for timing-sensitive programming | A close language-engineering precedent; exact logical usage shaping differs from machine timing protection |
| [Translation Validation](https://doi.org/10.1007/BFb0054170) and [Necula's optimizing-compiler validation](https://doi.org/10.1145/349299.349314) | Validate individual transformations instead of verifying an optimizer | The architecture is established; source-bound custody and the domain-specific acceptance relation are the implementation delta |
| [Wang et al., USENIX Security 2014](https://www.usenix.org/conference/usenixsecurity14/technical-sessions/presentation/wang_tao) | Provable supersequence defenses for website fingerprinting | Weighted sequence alignment and cover events must be credited as adaptations; multi-arm alignment is heuristic, not globally optimal |
| [Pacer](https://www.usenix.org/conference/usenixsecurity22/presentation/mehta) | Practical cloud traffic shaping and network-side-channel mitigation | Demonstrates the deployment boundary that logical usage equality alone does not cover |
| [Time Will Tell](https://arxiv.org/abs/2412.15431) | LLM output-token-count leakage and padding | The threat and single-call padding are established; bounded multi-call repair is the relevant extension |
| [Sensitive-Topic Leakage Through LLM Routing Metadata](https://arxiv.org/abs/2610.09981) | Routing metadata itself leaks sensitive topics | Prohibits a first-routing-metadata-attack claim; use its threat as motivation rather than claiming discovery |
| [SICC](https://arxiv.org/abs/2609.26076) | Policy-relative communication compilation for multi-agent workflows | Authorized communication form differs from exact ordered logical token counts; both assume a policy/authorization boundary |
| [Communication-Graph Metadata](https://arxiv.org/abs/2606.07150) | Workflow communication metadata and cover traffic | The present study must not claim that earlier work ignores workflow structure or constant-rate defenses |
| [CaMeL](https://arxiv.org/abs/2503.18813) | Protect agent execution against prompt injection by controlling data/control flow | Integrity and authorization are related but do not establish equality of usage observations |
| [FIDES](https://arxiv.org/abs/2505.23643) | Agent information-flow security and an explicit secrecy/integrity distinction | A close assurance precedent; the observer and source of trust must be compared explicitly |
| [Hard-KLAIM](https://doi.org/10.1016/j.jlamp.2026.101191) | Locality-aware provenance and authority effects with mechanized finite-trace safety | Full text, including Theorems 1--2, was read from a locally supplied extraction. Its administrative and adapter assumptions are important precedents; trace safety differs from resource noninterference |
| [Proof-Carrying Contracts, v1](https://arxiv.org/abs/2610.28484v1) | Machine-checkable proof before an operation, including conditions for correspondence with the world | Proof-gated operation and model/world correspondence are established; the new artifact must not imply that core proofs verify its physical backend |
| [Token Budgets](https://arxiv.org/abs/2606.04056) | Budget-overrun evidence and affine resource mitigation | The new sequential reservation ledger is less general than ownership-based concurrent accounting; it is not a novel affine type system |
| [Costwright](https://github.com/eleata/costwright), [Typed Resources](https://github.com/eleata/typed-resources), [Loom](https://loom.technology/research/bounded-llm-cost/) | Related resource contracts, typed costs and structural workflow bounds | Costwright's existence was verified; the disk retains two narrow pinned probes. External systems' entire proofs were not rebuilt. Loom is an author-hosted report. No general superiority claim is justified |

Preprints are identified as preprints in the bibliography; a searchable title is
not evidence of peer review. Exact implementation and bibliographic versions are
recorded where available. A source that could not be obtained in full is not used
to support an exclusivity claim. This review does not establish that every relevant
paper has been found. An author should update it immediately before submission.

## Defensible novelty and separating examples

The strongest claim is **a specialized implementation and assurance method**:
a bounded workflow compiler can propose an equal-usage repair, while an independent
acceptance boundary derives the original core and declared secrets from source,
checks the proposed repair, and records model-specific execution evidence. The
new per-contract budget theorem is a useful corollary of trace shape, not a new
resource logic. Three-way operational execution is evidence about implementation
correspondence and does not turn the Python frontend into a verified compiler.

Four separating examples make the claim concrete:

1. Equal input/output caps do not identify an operation. Two same-sized requests
   can select different response kernels. The disk's request-identity checks and
   the shaping validator's erasure check preserve request contents and argument order.
2. Equal aggregate cost does not imply equal ordered observations. `A; B` and
   `B; A` can have the same totals and different model/name traces. Ordered shaping
   requires a common sequence; the aggregate certificate remains a separate result.
3. Scalar token bounds do not transfer between tokenizers. The audit exhibited
   a 1-token BERT string whose complete GPT-2 request used 259 tokens against an
   18-token heuristic target. The combined runtime counts complete requests in
   the receiving model's unit and refuses overflow. This is exact admission,
   not a proof of a global static token bound.
4. A validator cannot discover a secret omitted from both its labels and its
   claimed secret list. The combined source reader supplies those independently
   of candidate code. The source reader remains trusted, as do its parser and lowering.

Additional engineering improvements include explicit model alias contracts, tool
argument escaping, preservation of tool-name observations in attacker features,
complete generated-ID evidence, retained reservations after unknown dispatches,
and hash-bound run resumption. These improvements make the software more useful
and the claims more falsifiable. Counting them is not a numerical novelty score.

## Fair comparison and evidence limits

The relevant cost comparators are all-branches dummy execution and uniform
per-model cell sizes, using the same observer and output caps. On seven historical
workflows the median weighted overhead is 1.83 times original usage, the range is
1.13--14.47, median saving against all-branches execution is zero, and maximum
saving is 52 percent. Uniform-cell savings are 14 percent at the median and
44 percent at the maximum. These results do not support universal efficiency.

The reanalysis includes tool identities. Derived padding-only, random-padding and
no-force traces are counterfactual baselines from retained observations; they are
not newly executed provider defenses. No result is attributed to a public hosted
API. Isolated filler prefill and the real request are separately processed, and
their logical counts are combined by the trusted runtime. Cache and invoice
semantics require their own contracts. Dummy tool names are logical trace events;
they do not simulate an actual external tool invocation.

All 962 historical pairs agree on the saved outputs, but task quality is weak in
some workloads: routing accuracy is 64.7 percent, switch accuracy 35.2 percent,
and calculator accuracy 1.0 percent. Preserving these outputs is a preservation
result, not evidence that the calculator is useful. Timing is also not protected:
the latency-augmented descriptive attack reaches 100 percent in one historical
workflow. No deployment privacy claim may include timing, packets, streaming,
shared caches, external tool traffic, failures, or an observer that sees contents.

## SCP assessment and remaining gates

[SCP's official scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423)
includes practical formal techniques and experimental software technology.
The combined full research paper fits that scope better than either frozen draft:
it presents a concrete programming method, an executable tool, mechanized core
properties and tests of correspondence. An Original Software Publication is a
possible alternative framing if editors prefer a shorter software contribution;
it requires the track's own current instructions and a usable public archive.
The detailed ScienceDirect guide returned HTTP 403 during this audit, so precise
submission forms, current fees and format limits remain unverified.

The principal reviewer risks are the proximity of constant-resource/supersequence
prior art, the restricted observer, the unverified execution bridge, weak task
quality for some ports, authored rather than independently sampled benchmarks,
and lack of an independent reproducer. The strongest response is the specific
contract, transparent negative results and a well-documented reusable artifact.
More formal lemmas or inflated claims would not resolve those risks.

The scope match is plausible; originality for a full research article remains
a serious review question. Source binding and accounting safeguards are valuable
engineering, but individually standard. The publication case rests on their
coherent specialization, executable mechanized acceptance relation, operational
evidence and reuse. An OSP framing may be stronger if the authors demonstrate
installation and independent research use. Neither framing becomes acceptable
merely because tests pass.

| Gate | Evidence that can be completed locally | External or explicitly scoped remainder |
|---|---|---|
| Core soundness | Rebuild Lean with axiom reports; complete unit, differential and operational comparisons | Independent proof review; no claimed parser/backend refinement theorem |
| Real execution | Complete planned missing pairs, cross-family replication and fresh conformance subset; keep all failures | New hardware and independent-site reproduction; no universal serving theorem |
| Prior art | Source-by-source overlap matrix and separating examples | Author-led final literature check; no priority guarantee |
| Reproducibility | Immutable source freeze, raw records, exact dependencies, generated tables, source/evidence archive with SHA-256 | Approved public archival deposit and stable citation/DOI |
| Authorship and integrity | Prepare review form, contribution fields, data and AI-use statements | All authors approve the actual final text, contributions, funding, conflicts, permissions and submission |
| Submission | Compile and inspect the manuscript, prepare highlights and cover-letter draft | Author-selected submission, current guide check and any publishing agreement/payment |

[Elsevier's current AI policy](https://www.elsevier.com/en-au/about/policies-and-standards/generative-ai-policies-for-journals)
requires transparent reporting and human accountability. The package records AI
assistance in code, experiments, literature synthesis and writing; it does not
assert that the authors have already reviewed the generated revision. Nothing
has been submitted, pushed or deposited publicly by this task.


## Final frontend and interface qualifications

The corrected frontend/protocol at `913530b` has 360 source/template checks,
an exhaustive Python whitespace-classification check, 320 targeted operational
executions in addition to the 6,000 generated executions, and three real-model
boundary pairs. Those tests found a genuine interpolation/trim ordering error,
literal-marker fragility and Unicode JSON framing issues. The original core
proofs were conditional and were not refuted; the errors were in their bridge.
The later custody maintenance makes workspace dirtiness informational while
retaining exact source/data/model identity for resumption.

All large application results remain tied to `6a24fe8`; they are not claims of
unchanged full-corpus accuracy after the frontend fix. A full new application
campaign would strengthen release-level external validity. The paper reports
versioned observations and targeted release controls instead of conflating them.

The logical observer must be attached to a faithful usage interface. If a host
may simply suppress or normalize the logs, that is a simpler alternative and
burning dummy model work is unnecessary. This prototype does not establish an
authoritative external invoice/gateway adapter. This is a major limit for a
security-deployment claim, and a material reviewer risk, although a precisely
scoped programming/software contribution remains assessable by SCP.
