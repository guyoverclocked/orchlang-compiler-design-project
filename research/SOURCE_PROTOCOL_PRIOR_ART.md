# Source protocol: prior art and contribution boundary

**Checked:** 9 October 2026. This is a focused primary-source review, not a
systematic literature search. It asks what a source-bound check for a
sanitizer-conditioned LLM request/usage trace could contribute beyond
established information-flow theory.

## What is established already

Treating a sanitizer as an approved release is a declassification policy. The
policy must say what may be released and under what conditions; the proof does
not establish that a chosen regular expression recognizes every sensitive
value. Sabelfeld and Sands organize declassification by what, where, who, and
when. Myers, Sabelfeld, and Zdancewic study robust declassification, where an
attacker must not be able to manipulate the release mechanism into disclosing
more than intended. Those results make a regex-specific compiler check an
instance and policy-boundary problem, not a new declassification principle.
[Sabelfeld & Sands, *Declassification: Dimensions and Principles*, JCS 17(5),
2009](https://doi.org/10.3233/JCS-2009-0352); [Myers et al., *Enforcing Robust
Declassification and Qualified Robustness*, JCS 14(2),
2006](https://doi.org/10.3233/JCS-2006-14203).

Retries, validation exceptions, and error-driven branches are also established
information-flow concerns. Malecha and Chong give a sound, more permissive
security type system for imperative programs with exceptions and prove
standard noninterference. Bichhawat's ICSE Companion paper explicitly
identifies exceptions as leaks because they cause nonlocal control transfer.
Thus including retry/error paths is necessary for a correct workflow
observation, but is not by itself novel. The specific extension here would be
to preserve exact LLM repair requests, their attempt ordering, and the
source's usage/route effects in a concrete workflow certificate.
[Malecha & Chong, PLAS 2010, DOI
10.1145/1814217.1814221](https://people.seas.harvard.edu/~chong/pubs/plas10_exceptions_tr.pdf);
[Bichhawat, *Exception handling for dynamic information flow control*, ICSE
Companion 2014, DOI 10.1145/2591062.2591195](https://doi.org/10.1145/2591062.2591195).

Likewise, dependency slicing and relational source reasoning have deep prior
art. Wasserrab and Lohner reuse a machine-checked interprocedural slicing proof
to obtain a machine-checked noninterference proof, instantiated for two
languages. Chudnov, Kuan, and Naumann interpret runtime monitors as abstract
interpretations over pairs of program runs. These works rule out novelty claims
for “extract dependencies,” “use a relational product,” or “emit a certificate”
in general. They do not make a hash-bound, framework-specific adapter useless:
its contribution can be a practical, fail-closed mapping from a real workflow's
source expressions and effects into a separately checkable request/usage
contract. But a graph certificate replay is not a source-to-graph correctness
proof unless the replayer also checks that mapping.
[Wasserrab & Lohner, VERIFY 2010, DOI
10.29007/nnzj](https://publikationen.bibliothek.kit.edu/1000027776);
[Chudnov et al., CSF 2014, DOI
10.1109/CSF.2014.12](https://doi.org/10.1109/CSF.2014.12).

The resource-security connection is similarly established. RANIF combines
information-flow typing and constant-resource reasoning; RelCost analyzes
relational differences in program costs. LLM-specific adjacent systems now
cover agent content-flow protection and probabilistic workflow execution:
FLOWSEAL uses provenance and an IFC lattice at tool boundaries; OCELOT budgets
trajectory-level inference risk; PDL/PPDL provide compositional prompt/workflow
programming and uncertainty propagation. None of those abstracts, by itself,
establishes the exact source-derived usage-trace property at issue here, but
they make “LLM workflow security” or “LLM cost analysis” too broad a novelty
claim. [RANIF, IEEE S&P 2017](https://doi.org/10.1109/SP.2017.53);
[RelCost, POPL 2017](https://doi.org/10.1145/3009837.3009858);
[PPDL, ICML 2026](https://proceedings.mlr.press/v306/mandel26a.html);
[FLOWSEAL, arXiv:2609.14003](https://arxiv.org/abs/2609.14003);
[OCELOT, arXiv:2606.12341](https://arxiv.org/abs/2606.12341). FLOWSEAL and
OCELOT are preprints as checked here; their claims are author-reported.

There is a real security motivation for observing lengths, but the observer
must be named precisely. *What Was Your Prompt?* recovers information from
token-length patterns visible in encrypted streaming traffic; *Time Will
Tell* studies timing that reveals output token counts. Conversely, the 2026
*Invisible Tokens, Visible Bills* paper concerns whether provider-side hidden
work and usage reports can be audited. These are related but distinct
observations: network token lengths, timing, provider receipts/invoices, and a
source program's estimated token/cost rows are not interchangeable. The
incident-triage source estimates `max(1, len(text)//4)` in Python code points;
it does not measure provider tokens or a charge. [Weiss et al., USENIX
Security 2024](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss);
[Time Will Tell, arXiv:2412.15431](https://arxiv.org/abs/2412.15431);
[Sun et al., ICML 2026](https://proceedings.mlr.press/v306/sun26bd.html).

## Assessment of the current source bridge

The checked artifact binds the MIT upstream revision and selected file hashes,
recognizes the exact three-step `redact_pii` implementation and the first
classifier system/user request, then creates and certifies a synthetic
self-composed request graph. Its claim is conditional on equal validated
metadata, equal post-redaction text, and a shared complete-outcome oracle. It
states explicitly that it does **not** translate the full LangGraph workflow,
model the repair completion/downstream requests, or prove source billing
conformance. The source's `call_with_repair` syntax is inspected, but its
second completion remains outside the graph. The generated request graph also
has an adapter-only output cap. Its artifact currently says the graph
certificate's independent replay validates the graph closure, while expressly
excluding source-language/framework-to-graph translation fidelity; the
producer-checker hash is marked unverified. This is a source-linked first-call
slice, not yet a compositional source dependency certificate for workflow
execution.

The direct execution study is useful evidence about that pinned application's
actual mock behavior, but it does not close this gap: it is finite, uses a
deterministic mock and one injected repair failure, and compares a selected
observer. The raw incident remains in state/checkpoints. Moreover, equality
after redaction proves only the chosen pair property. It neither proves the
regexes cover general PII nor hides marker presence, count, type, or residual
text. The source's shared mutable cost tracker/current-node state also means a
single-invocation result needs an explicit serial/isolation premise or a
per-invocation fix before it can be generalized to concurrent service use.

## A substantive, attainable software contribution

The most defensible extension is **source-to-observation translation
validation** for this pinned workflow, not another collection of authored
examples. Build a fail-closed source extractor that carries the sanitized
request expression and typed parsed fields through classification, the exact
repair/validation path, enrichment, budget check, draft request, usage rows,
and terminal route/interrupt. Bind the analyzed source, configuration, and
runtime dependencies. Have a small independent verifier check each source
mapping obligation as well as the resulting relational certificate; currently
replaying only a generated graph is insufficient. State the relation as an
explicit approved sanitizer quotient, model only the source's documented
three-pattern behavior, and either isolate tracker state per invocation or
exclude concurrent runs. Keep source estimates distinct from provider billing.

Evidence that would make this useful and technically distinctive: differential
execution of the exact pinned application against extracted graph observations
for success, unknown-site, malformed-first-response/repair-success,
repair-failure, and budget-boundary cases; independent reconstruction of
request/usage/event traces; plus authored source mutations that bypass or
reorder the sanitizer, alter the repair error/template, or add a raw-text
downstream dependency, each rejected with a concrete source location and
counterexample. This is an achievable application-specific static-analysis
artifact and a much stronger OSP case than the current first-call slice. It
would still specialize established declassification, relational IFC, and
cost-analysis ideas; it would not warrant describing the underlying theory as
new. One pinned application can demonstrate a real translation/use case, but
it should not be described as external adoption or a prevalence study.

## Selected references

- Sabelfeld, A. & Sands, D. “Declassification: Dimensions and Principles.”
  *Journal of Computer Security* 17(5), 517–548 (2009).
  [DOI](https://doi.org/10.3233/JCS-2009-0352).
- Myers, A. C., Sabelfeld, A. & Zdancewic, S. “Enforcing Robust Declassification
  and Qualified Robustness.” *Journal of Computer Security* 14(2), 157–196
  (2006). [DOI](https://doi.org/10.3233/JCS-2006-14203).
- Malecha, G. & Chong, S. “A More Precise Security Type System for Dynamic
  Security Tests.” PLAS (2010), 1–12.
  [Author-hosted paper](https://people.seas.harvard.edu/~chong/pubs/plas10_exceptions_tr.pdf).
- Bichhawat, A. “Exception handling for dynamic information flow control.”
  ICSE Companion (2014), 718–720.
  [DOI](https://doi.org/10.1145/2591062.2591195).
- Wasserrab, D. & Lohner, D. “Proving Information Flow Noninterference by
  Reusing a Machine-Checked Correctness Proof for Slicing.” VERIFY (2010),
  141–155. [KIT record](https://publikationen.bibliothek.kit.edu/1000027776),
  [DOI](https://doi.org/10.29007/nnzj).
- Chudnov, A., Kuan, G. & Naumann, D. A. “Information Flow Monitoring as
  Abstract Interpretation for Relational Logic.” CSF (2014), 48–62.
  [DOI](https://doi.org/10.1109/CSF.2014.12).
- Ngo, V. C. et al. “Verifying and Synthesizing Constant-Resource
  Implementations with Types.” IEEE S&P (2017).
  [DOI](https://doi.org/10.1109/SP.2017.53).
- Çiçek, E. et al. “Relational Cost Analysis.” POPL (2017).
  [DOI](https://doi.org/10.1145/3009837.3009858).
- Weiss, R. et al. “What Was Your Prompt? A Remote Keylogging Attack on AI
  Assistants.” USENIX Security (2024), 3367–3384.
  [Paper](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss).
- Sun, G. et al. “Position: Invisible Tokens, Visible Bills: The Urgent Need to
  Audit Hidden Operations in Opaque LLM Services.” ICML, PMLR 306 (2026),
  172196–172207. [PMLR](https://proceedings.mlr.press/v306/sun26bd.html).
