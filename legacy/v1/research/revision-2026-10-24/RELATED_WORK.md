# Primary-source comparison checked 24 October 2026

This is a focused comparison for the revision, not a systematic review. The
contribution is a specialized executable analysis with explicit contracts and
validation. Classical resource analysis, noninterference, probabilistic
relational reasoning, and compiler normalization are established techniques.

| Primary source | Material inspected | Relevance and boundary |
|---|---|---|
| [Token Budgets, Khan, arXiv:2606.04056](https://arxiv.org/html/2606.04056) | Abstract, scope, estimator discussion, single-agent comparison, evaluation and limitations | Reports 63 production incidents and studies affine budget ownership. Its key distinction from disciplined counters is integrity during delegation. Its monetary cap depends on a sound estimator. OrchLang does not establish an ownership or concurrency result; it checks a secret-dependent resource relation in bounded workflows. |
| [Costwright 0.2.15](https://github.com/eleata/costwright/tree/2531c37cc2aa06472a2628bccfb527f185f6b4c0) | README, cap/extraction/mapping code and noninterference scope note; two executable probes below | Static graph bounds and provider-specific output-cap checking already exist. The cost/risk noninterference note concerns whether budget instrumentation invalidates a calibrated risk certificate; that is a different property from invariance under secret input. Do not compare them by their shared word “noninterference.” |
| [Typed Resources](https://github.com/eleata/typed-resources) | Project description, theorem inventory and vector-resource coverage | Potential-based, machine-checked scalar and vector resource bounds for LLM workflows are prior art. A scalar or vector resource theorem alone cannot be presented as OrchLang's research novelty. The external proofs were not rebuilt in this audit. |
| [CaMeL, Debenedetti et al., arXiv:2503.18813](https://arxiv.org/html/2503.18813) | Design/threat model and Section 7 side channels | Separates privileged control from untrusted data and tracks capabilities/dependencies. Its own discussion includes implicit-flow, exception and timing examples. OrchLang evaluates a narrower resource observation under stateless kernels; it is not a replacement for CaMeL or an end-to-end prompt-injection defense. |
| [FIDES, Costa et al., arXiv:2505.23643](https://arxiv.org/html/2505.23643) | Section 4 labels, noninterference/explicit secrecy distinction, Proposition 1 and planner design | IFC for agents and deterministic permitted-flow policies already exist. Their distinction between confidentiality as explicit secrecy and integrity as noninterference motivates naming the precise observer rather than claiming generic privacy. |
| [Weiss et al., USENIX Security 2024](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss) | Conference record and open paper | Demonstrates inference from encrypted token-length sequences. This motivates scrutiny of resource metadata; it does not show invoice leakage or establish that OrchLang prevents the network attack. The PDF lists four authors; the conference page's auto-generated BibTeX omits Guy Amit, so the paper's author list is used. |
| [Whisper Leak, Microsoft Research, November 2025](https://www.microsoft.com/en-us/research/publication/whisper-leak-a-side-channel-attack-on-large-language-models/) | Primary publication description and security report | Studies prompt-topic inference from encrypted packet sizes and timing. These observations are richer than the billing/resource events in OrchLang's theorem. |
| [PC2, arXiv:2610.28484v1](https://arxiv.org/abs/2610.28484v1) | Current submission history, model/operation obligations and correspondence discussion | On 24 October the record lists only v1, submitted 20 October 2026. Proof-before-operation and world/model correspondence are existing ideas. OrchLang's normalizer recomputes its result and should be called a verified decision procedure, not a witness with cheaper checking. |
| [Loom, Dickerson, May 2026](https://loom.technology/research/bounded-llm-cost/) | Structural theorem, Section 8 live-model evaluation, failure-accounting caveat | Reports structural bounds and 55 live-model configurations. Its explicit distinction between productive cost and later failure accounting reinforces the need to identify the measured resource. No external name-identity defect was reproduced. |

## Executed Costwright probes

The GitHub connector resolved the renamed project to `eleata/costwright`. A
clean local clone at `2531c37cc2aa06472a2628bccfb527f185f6b4c0`
was used for source inspection and execution. `scripts/compare_related_tool.py`
requires that exact commit, checks cleanliness, and retains source hashes,
fixtures, commands, exits and JSON findings in `costwright-probes/results.json`.

* An imported `ChatOpenAI` alias with an explicit literal cap produced no cap
  finding.
* A dynamically selected model with a potentially ineffective cap produced
  the expected conservative `ineffective` finding.

These two development probes do not establish general correctness or absence
of bugs. They supply no evidence that Costwright has OrchLang's historical
model-name conflation error. The revised paper treats that error as a failure
mode illustrated by OrchLang, not as an external vulnerability finding.

## Defensible distinction

The paper should make the following practical question central: can a developer
audit both a worst-case resource contract and invariance of resource observations
when a secret Boolean changes, while preserving complete response-dependent
requests? The artifact supplies separate judgments for those questions, checked
core transformations, concrete rejection witnesses, and measurements that expose
where source support and execution assumptions limit their use. No claim of a
new general cost logic, superior expressiveness, or priority is supported.
