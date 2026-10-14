# Publication handoff, 14 October 2026

The new standalone manuscript is `OrchLang_SCP_Publication_Upgrade.tex`, with rendered PDF at `output/pdf/OrchLang_SCP_Publication_Upgrade.pdf`. It is a research draft for SCP's Original Software Publication track, not a submitted or accepted article. Author details are placeholders at the author's explicit request. The older manuscript remains historical and was not rewritten.

Frozen software source: `dd97af2ac714f8c0dbf5ddb63ac29cbdb4a2d0dc` (0.5.0rc2). The source archive uses that exact Git revision. The later paper/evidence commit is a separate companion identity. The complete ten-stage upgrade run passes, including the 44-stage core run and 16-stage unchanged incident extension. Each optimized and sanitizer native run passes 112 tests; the Python audit suite passes 230; installed-package checks pass 23 stages; pinned LangGraph backend/frontend suites pass 11/22 tests. Two current normalized-IR theorem checks report closed global assumptions.

The key new engineering result is shared-prefix replay. At 64 calls per arm in one controlled family, median replay time is 138.51 ms before and 87.51 ms after (36.8% lower in this run). The reported verifier meters are 9,972,749 versus 1,784,025 bytes; the new meter additionally charges retained parsed-row storage, so these are neither identical accounting rules nor RSS. The old 128-call case is UNKNOWN; the new case proves equality and replays, while both 256-call cases remain UNKNOWN. These results do not establish broad scalability or algorithmic novelty.

The external-source compatibility study retains 59 AST-selected original files from 9 of 12 selected repositories: 0 admitted, 59 unsupported, no external-source differential. It is a convenience sample and includes tutorial and infrastructure-like candidates. All original bytes, source identities and unsupported outcomes are retained. The post-freeze official SPDX audit reproduces the original selected cohort; API labels are not a legal review. A repository-root path-enumeration clarification was recorded after outcomes without changing frozen sources or denominators. The current source adapter is narrow and this negative result must remain prominent.

Three GPT-6 Luna agents at max reasoning and subsequent agent cross-reviews assisted research, code, tests, proof and evidence auditing. This is not independent human artifact evaluation. The human authors must review all assistance before final declarations and submission.

## Venue choice

The ranking below is based on scope and readiness, not inferred acceptance probabilities. No official public acceptance rates were found for SCP OSP, SoftwareX or Software Impacts; a higher chance of acceptance cannot be established from the available evidence.

| Venue | Recommendation for this candidate | What remains |
| --- | --- | --- |
| [SCP Original Software Publication](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/) | Primary target: strongest match to formal program-analysis research software. | Complete author declarations, human review and persistent capsule identity; verify the current author guide. |
| [SoftwareX](https://www.elsevier.com/en-gb/researcher/author/tools-and-resources/research-elements-journals) | Closest alternative: foreground software use, reuse and the pinned incident case. | Adapt its current template; confirm archive and open-access charges from the publisher before submission. |
| [Software Impacts](https://legacyfileshare.elsevier.com/promis_misc/SIMPAC_Article_Template.pdf) | Conditional alternative for a shorter software article. | Its required OSP template allows up to three body pages excluding metadata, tables, figures and references; strengthen demonstrated impact and provide a reproducible capsule link. |
| [JOSS](https://joss.readthedocs.io/en/latest/submitting.html) | Premature under the current public-development and research-impact gates. | More than six months of public active development plus substantive research use; repository creation on 17 September 2026 alone is insufficient. |
| [Journal of Systems and Software](https://shop.elsevier.com/journals/journal-of-systems-and-software/0164-1212) | Later research-paper option. | A stronger software-engineering contribution and broader empirical evaluation. |
| [Software: Practice and Experience](https://onlinelibrary.wiley.com/page/journal/1097024x/homepage/productinformation.html) | Weak fit for this verification-centered draft despite compiler/tool overlap. | Its scope excludes work centered on validation and verification; broader practical experience would be needed. |

SoftwareX is the practical fallback. Software Impacts is relevant after reframing and demonstrating impact. The current evidence does not justify claiming that either will accept this manuscript more readily than SCP.

## Author actions before actual submission

- Supply author names, affiliations, correspondence, CRediT contributions, funding and competing-interest declarations.
- Review the manuscript, code and AI-assistance declaration and obtain a human colleague's independent artifact report.
- Confirm current SCP author requirements and persistent archive/DOI identity; current official guide access returned 403 during research.
- Upload the final approved manuscript and software/evidence package to the journal's submission system. No submission, editor contact, payment or acceptance has occurred.

## Exact packaging command

Full local Git history is needed for the paired baseline and compiler audit. Check out the code revision above for reproduction, then use the later companion manuscript and PDF for packaging:

```sh
python3 scripts/package_publication_upgrade.py \
  --source-revision dd97af2ac714f8c0dbf5ddb63ac29cbdb4a2d0dc \
  --manuscript submission/research/manuscript/OrchLang_SCP_Publication_Upgrade.tex \
  --pdf output/pdf/OrchLang_SCP_Publication_Upgrade.pdf
```
