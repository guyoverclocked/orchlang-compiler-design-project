# Final review audit, 29 October 2026

This audit records decisions before revision. The supplied independent review was
read in full. The research target remains Science of Computer Programming.

| Review point | Decision and concrete change |
|---|---|
| Major 1: editorial handoff prose | Remove internal approval instructions and repeated assistance disclosures from the research narrative. Keep author decisions in the separate author-review file. Do not invent consent, conflicts, contributions, funding or an archival DOI. |
| Major 2: version fragmentation | Preserve the historical records and their identities. Make their status explicit at the start of evaluation; run a fresh, uniformly versioned release-validation cohort. Never call a subset a full 1,684-pair rerun. |
| Major 3: isolated padding | Accept the review's accounting-only alternative. State that two-pass prefill is a budget/accounting stress test, exposes request length below the wrapper, and has no confidentiality advantage over permitted report normalization. Do not claim masked single-batch padding or server protection. |
| Major 4: trajectory-dependent admission | Add a compositional sufficient certificate based on bounded values, expression expansion, response/tool bounds and context capacity. Prove that it implies RunsIn for every tape under explicit primitive contracts. Distinguish this from certification of the existing heuristic targets or physical failures. |
| Major 5: two implementations | Remove C++ architecture and test counts from the main narrative. Retain the independent implementation only in a short historical appendix. |
| Multi-token stops | Check the implementation before accepting the review's premise. The backend recognizes EOS and declared single-token stop IDs, not arbitrary string matching. Reject unsupported multi-token declared stops explicitly and add regressions. |
| Minor 1: weight 1:4 | Explain it as a chosen decode-sensitive score, not a measured price. Evaluate static alignment sensitivity across several weights instead of importing an unsourced commercial-price rationale. |
| Minor 2: Qwen CRAG collapse | Diagnose the actual prompt, raw response and branch rule. Retain the original cohort and any degenerate result; do not tune the primary benchmark to manufacture branches. |
| Minor 3/4: formal presentation | Add core grammar, big-step rules, label/padding judgments and source-bound acceptance/erasure rules matching Lean. Improve connective explanations around the rules. |
| Additional literature | Verify and cite the relevant foundational entries already in the bibliography. Verify any new bibliographic addition against primary sources. The review misidentifies the venue of the PC-security paper. |
| Pacing and quantized loops | Defer as a separate research extension. Neither proposed BA/overhead threshold follows from the review; no measured timing improvement or leakage bound will be invented. |

## Academic-humanizer pre-edit audit

The existing manuscript uses a neutral research register, but several paragraphs
read as custody notes. Locations needing revision: the introduction's dual-system
paragraph; scope's faithful-reporting argument; the domain theorem's explanation;
implementation's repeated assistance/approval notes; evaluation's version chronology;
and availability's internal handoff text. Replace repeated caveats with explicit
assumptions beside the relevant claim. Keep negative results, all existing numeric
observations, formal hypotheses and cited keys.

Empirical claims are supported by retained tables/logs, with important limits:
historical records cannot support current-release output equality; finite character-
token comparisons do not instantiate BPE semantics; primitive transparency is a
bounded test; equal saved outputs do not establish task accuracy; and a constant
exported trace does not establish a constant low-level request trace. New results
must have separate immutable receipts before being added to the paper.
