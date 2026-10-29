# Response to the independent review, 29 October 2026

The revision focuses the research paper on source-bound Python/Lean validation
and model-indexed resource envelopes. The supplied review and its entire
actionable roadmap were considered. Changes are supported by the proof files,
new immutable execution records, independent audits and manuscript QA listed
below. The final PDF has 32 pages in the existing Elsevier preprint format.

## Changes addressing the major objections

**Admission and the RunsIn lookahead problem.** The paper now explains the
two-step prefix-refusal channel directly. A regression executes two shaped
calls: both secret inputs emit the same first event, but only one admits the
second call. Their observations differ as completed(two events) versus
failed(one confirmed event). Per-call refusal is therefore not presented as
failure-observation noninterference.

A new compositional sufficient checker is defined in
`proof/AdmissionDomain.lean`. A finite vector bounds all store slots in one
declared text-size unit. Expression bounds account for literals, variables,
concatenation, escaping and trimming. Every assignment must preserve the vector;
each model call must fit its receiving-tokenizer envelope and context capacity;
and dummies and loop cover work must also pass. The checker never evaluates
`exec` or RunsIn.

Lean proves `static_certificate_sound`, `static_certificate_implies_RunsIn` and
`static_certificate_domain`. Acceptance plus the input invariant and explicit
primitive contracts implies RunsIn for every randomness tape. The new theorems
use `propext` and `Quot.sound`, with no `sorryAx`. Ten executable Lean guards
exercise accepted chaining, branches, tools and loops and rejected input,
response-slot, context, cap and dummy envelopes.

This is a constructive **core-level sufficient condition**, not a claim that
the existing heuristic frontend sizes are certified. Concrete decoded-output,
tokenizer and tool bounds remain contracts to justify. Transport failures and
unknown dispatches remain outside the theorem. Section 4.4 states these limits
beside the result rather than suggesting a physical preflight oracle.

**Isolated padding and the observer.** The paper adopts the review's
accounting-only alternative. It explicitly states that two prefill passes reveal
the actual request length below the wrapper, and that executed filler is a
resource-envelope stress test. Normalizing exported reports is acknowledged as
a useful cheaper alternative for the same log observer. The claim that
normalization is disallowed by a faithful-event contract has been removed.

Single-batch attention-isolated serving is discussed as a separate extension,
not reported as implemented. Research into the public llama.cpp interface also
shows why the roadmap's proposed acceptance criterion is insufficient on its
own: one length-T submission can still expose real-token membership through
positions, sequence IDs, masks, logits or cache behavior. The required observer
must be defined before a server-level security claim can follow.

**Cohort fragmentation.** The full older application results remain attributed
to their original releases, including the frontend correction and the retained
6/18 descriptive divergence. The evaluation states this limitation before the
benchmark tables. A new targeted release cohort runs the shortest and longest
inputs for all nine main workflows and three Qwen variants, on the same
implementation identity `ee137316c7c0ddaf02ce61dcc6f70af4815d840e`.

All **24 pairs** preserve saved fields, match their shaped traces, and have
complete nontruncated usage. Independent re-tokenization, visible-prefix and
ledger checks reconcile **48 records and 191 model calls**. Lower-level local
eval submissions are retained and reconciled too; a deliberately changed count
is detected.

A full homogeneous **1,684-pair re-execution was not performed**. The new cohort
is a targeted release check, not an accuracy or attack study, and is never added
to the old main-study denominator. This addresses current-release validation
without falsely claiming to satisfy the review's full-rerun acceptance criterion.

**Two implementations.** The architecture, implementation and main evaluation
now describe the Python/Lean system. C++ test counts, its different prompt policy
and its separate framework/accounting evidence appear only in a historical
supplementary appendix. There is no implied translation between the systems.

**Editorial handoff text.** Internal consent/approval instructions and repeated
assistance disclosures were removed from the manuscript's methods and
availability prose. Availability now describes the supplied versioned artifact
and its reproduction map. No consent, contributions, conflicts, funding,
submission status or permanent archival identifier was invented. Author-managed
declarations remain outside this research revision.

## Additional technical and presentation changes

- Added complete core grammar, representative surface constructs, big-step
  operational rules, label/padding judgments and source-bound validation/erasure
  rules matching the Lean definitions.
- Replaced shaped constant-feature classifier scores in the main tables with
  distinct shaped trace counts and empirical trace/decision MI. All twelve
  retained workflow/model cohorts have one shaped trace and zero empirical MI.
  The original classifier records remain available for reproduction.
- Recompiled twelve workflow variants with output weights **0.25, 1, 2, 4, 8 and
  16**, holding input weight at one. All **72** candidates pass Lean and each
  variant has the same shape across weights. The paper makes no new cost-saving
  or commercial-pricing claim.
- Diagnosed all **600** Qwen CRAG grader responses: **484** scores are `0`,
  **34** are `1`, **5** are `yes`, and **77** are `no`. All are parseable JSON;
  none reaches its 16-token cap. The prompt mixes numeric and yes/no instructions,
  but the parser recognizes only `yes`. A parser-only normalization accepting
  `1` still routes all **150** questions to web search. The original benchmark
  is preserved, and no branches are manufactured by retuning it.
- Checked the review's multi-token stop premise against the actual backend.
  It implements EOS and atomic token-ID stops, rather than arbitrary string
  matching. Unsupported multi-token or empty declared stops are now explicitly
  rejected instead of silently ignored, with two regression tests.
- Added the verified USENIX Security 2024 token-length attack reference and
  contextualized the existing PC-security, verified constant-time compilation,
  predictive mitigation and LMQL references. The PC-security venue is retained
  correctly as ICISC 2005 proceedings, published in 2006; the review labels it
  incorrectly as USENIX Security 2005.

## Final verification

| Check | Result |
|---|---|
| Configured unit suite, including pinned-model checks | 40 passed |
| Shape, domain and new certificate proofs | Compiled; no sorryAx |
| Executable static certificate checks | 10 passed |
| Three-way operational correspondence | 6,320 executions; 604 validator checks; no failures |
| Generated differential study | 1,000 programs; 5,000 Lean checks; 16,000 comparisons; no counterexample |
| Retained versioned campaign completeness | Passed; original denominators and versions preserved |
| Uniform final-release model validation | 24/24 pairs; 191 model calls independently reconciled |
| Weight sensitivity | 72 accepted candidates; shapes unchanged at tested weights |
| Academic-humanizer protected-content check | Numbers, equation content and citation occurrences preserved during the prose pass |
| LaTeX and bibliography | No undefined references, missing citations or overfull boxes |

Fresh receipts are under `publication/evidence/final-core-2026-10-29`,
`final-release-2026-10-29` and `final-diagnostics-2026-10-29`.
`ROADMAP_AND_ALTERNATIVES_2026-10-29.md` documents the researched alternatives
with primary-source links.

## Roadmap items kept as separate research

Predictive timing mitigation, public loop-envelope classes, grammar-constrained
grading, token-ID transport and attention-isolated serving are plausible follow-on
directions. Their cost, task utility and leakage properties need new semantics
and experiments. The review's proposed near-chance timing accuracy and large
overhead reductions are targets, not results established by the cited techniques
or by this revision. No such numerical improvements are claimed.
