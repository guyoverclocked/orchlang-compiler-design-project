# Scientific revision: scope and evidence

This revision responds to the full supplied review. All work remains local:
the author explicitly prohibited pushing until asked. Publication administration
and author approval are deferred at the author's request.

## Scientific changes

| Review issue | Implemented change | Evidence |
|---|---|---|
| B5: identical-plan rule has no precision advantage | Proved request normalization, sequence units, redundant public control, plus a separate independent-call aggregate decision | proof/DataflowCore.lean; proof/AggregateReordering.lean; docs/VERIFIED_PRECISION.md |
| B6: recomputed plan is not a meaningful proof witness | Primary interface is now a verified decision procedure; saved plans are diagnostic | scripts/dataflow_certificate.py; scripts/decide_aggregate.py |
| B7: C++ accepts eight, Lean sixteen | Every differing source/diagnostic identified and explained as a distinct confidentiality/resource judgment | dataflow-precision-v2/historical-policy-differences.json |
| B8: synthetic resource units | Complete-request pinned-tokenizer source analysis and finite execution, including enforced byte-contract rules for supported dynamic cases | docs/EXACT_ACCOUNTING.md; exact-accounting-v4 |
| C9: no original applications executed | Actual original LangGraph and Prompt Flow engines compared with local-model ports; direct and hybrid counts explicitly separated | docs/REAL_WORKFLOWS.md |
| C10: unmotivated observer | Multi-tenant resource-accounting scenario plus checked metadata-side-channel references | manuscript; research/revision-2026-10-24/RELATED_WORK.md |
| C11: missing related work | Checked Token Budgets, Costwright/Typed Resources, CaMeL, FIDES, Whisper Leak and current PC2 version | RELATED_WORK.md; retained Costwright probes |
| C12: contribution buried under caveats | Rewritten results-led manuscript, with a dedicated scope/validity section | docs/manuscript/scientific-revision.tex |
| C13: historical own-tool bug leads the paper | Recast as an identity-abstraction failure mode; no unsubstantiated external vulnerability claim | manuscript; costwright-probes/results.json |
| C14: release clutter and absent CI | Git source-export exclusions and Ubuntu/Windows validation workflow | .gitattributes; .github/workflows/validate.yml |
| C15: small inconsistencies | Base revision named accurately; unused historical Python-count macro removed from current generation; own Linux validation recorded | historical-tables; Linux validation |

The AI-use statement now includes OpenAI Codex and the Claude assistance
recorded in Git history. It does not invent human verification.

## Completed formal and accounting evidence

The new ordered precision campaign has 80 source cases (eight previous accepts,
64 revised accepts) and 72 core cases (eight previous accepts, 64 revised).
There are 3,648 exact execution contexts and no accepted supplied-kernel
counterexamples. These are constructed metamorphic grammars.

The aggregate campaign has 256 source cases: 16 ordered accepts and 28 aggregate
accepts. All twelve additional accepts intentionally have different ordered
distributions. Its 512 contexts and 2,048 weighted paths have no aggregate
counterexamples. The universal statements come from the Lean proofs.

Both original campaigns were rerun: the 576-program grammar retains 24 accepts;
the 256-pipeline grammar retains 16 resource accepts and eight C++ accepts,
with no three-way execution disagreements. All eight judgment differences have
E230 in both branch arms because downstream responses inherit the secret PC label.

Exact tokenizer evidence contains 5,344 text-policy and 8,996 concatenation-policy
observations. Of 64 finite configurations, 40 have supported static bounds and
24 correctly lack the required dynamic byte rule. There are 128 supported paths
and zero bound violations. The GPT-2 hello/world and BERT a/world counterexamples
show that summing separately encoded pieces can understate a complete request.

## What the evidence does and does not settle

The specialized decisions now have observable acceptance gains beyond syntactic
identity. The accounting path works on actual supported source files and explicit
finite execution contracts. The local-model study exercises actual upstream
engines, rather than relabeling lossy projections as applications.

The aggregate source fragment remains deliberately narrow. General source
verification, mutable providers, secret text, timing and network-traffic privacy
are outside its theorem. The local study's hybrid compositions retain operations
that OrchLang cannot express; those gaps are measured rather than removed.
Model generation variability and port conformance have separate endpoints.

The scientific manuscript is a software-paper candidate with evidence-backed
claims, not a promise of journal acceptance. No public deposition, author
consent, independent human review or publication outcome is asserted by these
automated checks.
## Final implementation validation

The tested implementation freeze is local Git commit
18d0d826dc40885cbde9552cc1628e751eb7921f.
Clean Windows and Ubuntu/WSL2 checkouts both pass the full core runner and all
four Lean files. Windows runs 82 Python tests with pinned tokenizer artifacts
and no skips; Linux's standard-library tier records 11 optional tokenizer skips.
Both platforms pass 106 C++ tests. The Linux sanitizer tier completes 44 commands
without failures. These are automated checks on two operating environments
on one physical machine, rather than independent human reproduction.

The retained per-file source hashes can be compared with a committed tree:

    python scripts/verify_revision.py --run research/revision-2026-10-24/clean-windows-v1 --ref 18d0d826
    python scripts/verify_revision.py --run research/revision-2026-10-24/clean-linux-v1 --ref 18d0d826

The final workflow results are 48 completed executions and 88 actual generations,
22/24 exact independent comparisons, zero bound/count violations, 24/24 captured
conformance comparisons and one repeatability disagreement in eight controls.
There is one direct port and five explicitly labeled host compositions.

The manuscript table generator and clean-source verification utility are
publication tooling. Any subsequent wording-only generator revision is recorded
separately from the scientific implementation freeze. Final package source hashes
identify the exact included bytes.

The final paper has 12 preprint pages, no unresolved references and no overfull boxes.
All pages were visually inspected; tables and bibliography received full-page checks.
The self-contained review source bundle supplies a fresh Git snapshot of the exact
source export, so reproducing the package does not depend on an unpublished branch.
