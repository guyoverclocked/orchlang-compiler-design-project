# Preregistered external-source admission study

**Protocol frozen:** 2026-10-14, before running the OrchLang frontend over any selected external workflow source.
**Question:** How often does the repository's current, deliberately narrow Python/LangGraph frontend admit original source files from independent public projects that use LangGraph?
**This protocol is a bounded transferability check, not a representative estimate of LangGraph usage or a benchmark of all agent frameworks.**

## Sampling frame

At the frozen date, query the public GitHub repository search API with these two exact queries, 100 results per query, sorted by stars descending and then GitHub's search ordering:

1. `langgraph language:Python stars:>=100`
2. `topic:langgraph language:Python stars:>=100`

Store the raw response and retrieval metadata. Deduplicate by `full_name`, preserving the better (lower) rank and both query memberships. The sampling frame is the union of only the first 100 results for each query; GitHub search ranking is mutable and not a population census.

## Repository eligibility and deterministic selection

Retain repositories that, at selection time, are public, not archived, have an API-detected OSI SPDX license, and have at least 100 stars. Exclude the following preregistered framework, adapter, and evaluation-library repositories by identity: `langchain-ai/langchain`, `langchain-ai/langgraph`, `langchain-ai/deepagents`, `langchain-ai/langchain-mcp-adapters`, `langchain-ai/langgraph-supervisor-py`, `langchain-ai/langgraph-swarm-py`, `aegra/aegra`, `hinthornw/trustcall`, and `JudgmentLabs/judgeval`. These are software infrastructure rather than independently developed workflow applications. The exclusion list is fixed before source extraction, and every exclusion is logged with its reason. Include tutorials, templates, and example repositories that meet the other criteria. Do not screen by whether code appears compatible with OrchLang.

Select every eligible repository in descending star count, up to the first 12 eligible repositories. If fewer than 12 qualify, include all. This convenience sample emphasizes publicly visible LangGraph projects and does not support prevalence claims.

For each selected project, freeze the default-branch commit SHA from the GitHub API, license identifier, repository URL, stars, default branch, and retrieval timestamp. The commit SHA, rather than a moving branch, defines the source snapshot.

## Source-unit enumeration

At each frozen commit, enumerate every tracked `.py` file under the repository root or conventional application directories (`src/`, `app/`, `agent/`, `agents/`, `workflow/`, `workflows/`, `examples/`, `example/`, `demo/`, `demos/`). Exclude paths with a component equal to `test`, `tests`, `docs`, `doc`, `vendor`, `vendored`, `generated`, `.venv`, or `site-packages`, case-insensitively. This is a path-only rule fixed before contents are parsed.

The candidate source units are all enumerated Python files whose AST imports `StateGraph` from a module path ending in `langgraph.graph`, or whose AST contains a call whose function is the simple name `StateGraph`. Record the full enumerated-file count, candidate-file count, parse errors, exact frozen bytes, SHA-256, and repository-relative path. A file is a unit; files from one repository are not independent repositories or independent statistical observations.

## Admission and outcome rules

Run the checked-in `integrations/langgraph/source_frontend/extract.py` on each candidate's original UTF-8 bytes without editing, rewriting, or wrapping the Python source. Use one documented, mechanically generated external contract only if extraction reaches contract-dependent checks: derive text input keys from the file's top-level `TypedDict` annotations, label them public, assign a 256-token input bound, derive model aliases only from literal calls to the frontend's own `request` helper, and assign each a placeholder provider/model pair and a 2,048-token cap. If the source does not expose those declarations in the admitted syntax, record `contract_not_derivable`; do not repair the source to make it pass. The generic declarations exist only to exercise parser admission and are not claimed as source-authentic labels, contracts, or billing metadata.

Record only the first deterministic frontend rejection reason as the primary outcome, plus parser/runtime exception class. A file is `admitted` only if the unmodified bytes pass extraction. Preserve unsupported source files and all rejection outcomes. Do not omit failed or awkward cases from denominators. Aggregate first by repository and then by file; report both denominators and avoid confidence intervals or broad frequency claims for this convenience sample.

## Dynamic differential rule

For every admitted original file, attempt an offline original-source-versus-graph differential only if its unchanged source runs with the already-supported offline request helper and pinned local dependencies, without network credentials or edits. Compare ordered request/usage/status traces on mechanically declared public inputs and at least two repeated seeds. Preserve logs and state exactly what the comparison shares (including any common oracle or model code). If no files are admitted, record the differential as not feasible under the current frontend and retain the authored-fixture differential only as separate prior evidence; do not create projections or count them as external-source runs.

## Reporting and limitations

Report all selected repositories, frozen commits, licenses, source counts, exclusions, hashes, every unsupported candidate, extraction error categories, and any dynamic comparisons in machine-readable evidence. The result measures compatibility with this exact frontend grammar on this bounded GitHub search sample. It cannot establish support or prevalence for arbitrary Python/LangGraph, correctness of the source translation, provider behavior, actual token billing, privacy against timing/cache/transport observations, or independent human review.
