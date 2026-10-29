# Paper and exact tested source

This directory contains the **author-review draft**, not an accepted or
author-approved journal submission. Publication of these files on GitHub was
requested by the owner. No journal submission, fee agreement, independent human
review or permanent archival DOI is implied.

- [Paper PDF, revised 24 October 2026](OrchLang-software-paper-review-2026-10-24.pdf)
- [Editable LaTeX and build instructions](../docs/manuscript/README.md)
- [Complete explanation, evidence and limitations](../docs/PUBLICATION_STATUS.md)
- [Checksums and artifact provenance](manifest.json)
- [Claim-to-evidence ledger](../research/claims.csv)
- [Outstanding author checks](../docs/AUTHOR_REVIEW.md)

The nine-page PDF was compiled and visually checked before this GitHub
documentation update. It is copied byte-for-byte from the previously checked
review package; its claims and evidence have not changed. The current GitHub
branch includes a later navigation/status guide and venue search that are not
inside that frozen PDF. The draft's local-release wording is historical; a
GitHub push makes source accessible but does not create the still-missing
permanent archival record or final author declarations.

## Why the Git bundles are included

Historical experiment manifests cite clean, isolated snapshot commits. Those
commits are not ancestors of the development repository's main branch. A SHA
alone cannot reconstruct an unavailable snapshot. These self-contained bundles
preserve the exact source/protocol revisions, without rewriting the main
repository's history or modifying old experimental records.

| Bundle | Exact commit | Purpose |
|---|---|---|
| [source-v3.bundle](tested-source/source-v3.bundle) | `6f325be2d00b8f617b09fb3f7f3f50b4e8f91f82` | Original complete CPU/generated/certificate/replay/tokenizer validation source |
| [source-v4.bundle](tested-source/source-v4.bundle) | `7a0095dd4346dae7045308ceffcc60ede8962647` | Amended external cost-projection protocol/source |
| [source-dataflow.bundle](tested-source/source-dataflow.bundle) | `00420ef202dc260fc98237ac584a6210a61e1e5e` | Current 106 C++ / 47 Python / three-proof validation and dataflow campaign source |
| [review-source.bundle](tested-source/review-source.bundle) | `11d495a83fad30c27d22f121b8a547058b3667ba` | Frozen manuscript/source/evidence package used for the PDF and prior same-host reconstruction |

From this repository root, check artifacts and both retained evidence hash maps:

```text
python scripts/verify_publication.py
```

To reconstruct a historical source tree, clone to a new directory outside the
current checkout. Replace the destination with an absolute writable local path:

```text
git clone publication/tested-source/source-dataflow.bundle /new/source-dataflow
git -C /new/source-dataflow rev-parse HEAD
```

Run the [reproduction commands](../docs/REPRODUCIBILITY.md) from that checkout,
with new result directories outside it. Git bundles contain source, not a
compiler, Lean binary, Python installation, model, private paper or API key.
The prior same-host reconstruction is recorded in
[reconstruction.json](../research/validated-2026-10-24/reconstruction.json);
it is not independent human reproduction.

## Rebuilding the paper

All editable files are under `docs/manuscript/`. Use a LaTeX distribution with
`elsarticle`, `amsmath`, `amssymb` and `hyperref`. Run `pdflatex` twice as described
in its README. To preserve the historical reviewed PDF, direct a new build to
a separate output directory and compare it separately. A new LaTeX build need
not have an identical binary PDF hash because timestamps and tool versions may
differ; the evidence macros must match the retained generated tables.

The project software is MIT. The Elsevier template derivative has separate LPPL
notices; upstream projections have documented sources/licenses. Read
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) before reuse. No private
subscription literature is included.
