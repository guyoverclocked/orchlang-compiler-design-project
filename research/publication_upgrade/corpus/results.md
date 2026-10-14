# External-source admission study: audit and result

The reproducible offline command is `python3 scripts/publication_upgrade_corpus.py --evaluate`. It reads the frozen repository manifest and source snapshots under `output/publication_upgrade/corpus/`, validates their revisions and SHA-256 digests, and evaluates each original candidate file with the checked-in LangGraph frontend. It performs no network selection or source rewriting.

## Selection audit

The source protocol and initial repository allowlist were frozen before frontend outcomes were collected. Because the cohort was first assembled using a manual allowlist, we later replayed the selection against the frozen two-query GitHub search response and the official SPDX License List 3.29.0 OSI flags. This is an audit of the existing cohort; it does not retroactively turn the original allowlist step into a fully automated preregistered selection.

The replay covers 200 search rows and 129 unique repositories. Under the written public/non-archived/license/star criteria, it identifies 84 eligible repositories before the top-12 cutoff: 45 fail a recorded eligibility or exclusion criterion, 72 eligible repositories fall below the cutoff, and the 12 selected repositories are the same in the same order as the frozen allowlist. License identifiers present in the frozen search frame have the same OSI-approved flag in the initial allowlist and the pinned official SPDX data, so this correction did not change the selected cohort. The machine-readable replay and raw license list are `output/publication_upgrade/corpus/selection_audit.json` and `output/publication_upgrade/corpus/spdx_osi_license_list_v3.29.0.json`.

This remains a high-star GitHub search convenience sample, not a representative sample of LangGraph projects. The two search result pages are a bounded, mutable ranking frame, and repository selection is not an independent random sample.

## Frozen sources and outcomes

The 12 immutable repository snapshots contain 4,348 tracked Python files under the path rule in `protocol.md`. Retrieval completed without errors. Enumeration found 59 original source candidates across 9 repositories; the other 3 selected repositories had no candidate file. One additional non-candidate template failed Python AST parsing. All 59 candidate files parsed and were preserved byte-for-byte with source URL, commit, byte count, and SHA-256 in `source_enumeration.json` and the `sources/` tree.

Running the current frontend on those original bytes produced:

| Unit | Count |
|---|---:|
| Frozen repositories | 12 |
| Repositories with candidate files | 9 |
| Candidate original files | 59 |
| Admitted | 0 |
| Unsupported | 59 |
| Exceptions | 0 |
| Not attempted | 0 |
| External-source dynamic differentials run | 0 |

The first deterministic rejection classes are 34 unsupported imports, 19 unsupported top-level `Import` statements, 4 unsupported state-field annotations, and 2 unsupported top-level `If` statements. These are file-level first rejections; later incompatibilities in a file are not counted. `admission_results.json` records per-file source identity, admission, first reason, contract derivability, and the evaluated frontend hash.

No original file was admitted, so no source-to-graph differential was possible. The harness records this as `differential_not_run: no original files admitted; no external source was projected or rewritten`. Authored fixtures and the separate incident-triage example belong to different evidence strata and are not added to these corpus counts.

## Interpretation and limits

The measured outcome is compatibility with this exact narrow frontend on this bounded set of repositories and candidate files. It is not an estimate of the prevalence of LangGraph patterns, Python support, security defects, or provider behavior. Zero admission is direct evidence that the current frontend does not transfer to the sampled original files under this protocol; it does not establish impossibility of supporting those projects or the soundness of any translation.

The external contract is mechanically generated only when extraction reaches contract-dependent checks. Its labels, token bounds, and placeholder model metadata exercise parser admission and are not source-authentic confidentiality labels, request declarations, billing data, or provider guarantees. Since admission was zero, the corpus says nothing about the differential correctness of admitted real-world source.

The protocol, all original snapshots, raw search frame, frozen commit/license manifest, selection replay, and per-file outcomes are retained as evidence. The extractor revision is reported with the results but is not a source-selection criterion; it includes post-freeze soundness repairs to the reserved LangGraph names and TypedDict annotation checks.
