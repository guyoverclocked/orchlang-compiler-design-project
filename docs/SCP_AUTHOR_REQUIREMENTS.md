# Science of Computer Programming: verified OSP submission requirements

**Checked:** 9 October 2026. **Target:** Original Software Publication (OSP), Software Track.

The current [SCP Guide for Authors](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors#toc-60) was successfully read in the Codex in-app browser on this date. The web-fetch service's earlier HTTP 403 was an access limitation of that service, not an unresolved journal rule. This document supersedes the earlier provisional requirements inventory. The original [EAPLS call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/) remains useful context, but the current guide supplies the specific instructions below.

## Manuscript length and required template

- Use the publisher's **OSP template**, preserving its formatting settings.
- The OSP manuscript **must be single column**, including a LaTeX submission. This specific track rule takes precedence over the general guide's allowance for double-column LaTeX.
- The **suggested length is 3–6 pages**, counting abstract and running text. The guide excludes title, authors, affiliations, references, metadata, tables and figures from that suggestion. It is not described as a mandatory six-page maximum for the entire PDF.
- Include the completed metadata table at the end of the OSP template.
- Templates: [official LaTeX OSP template](https://legacyfileshare.elsevier.com/promis_misc/scico-osp-template.tex), [official Word OSP template](https://legacyfileshare.elsevier.com/promis_misc/scico-osp-template.docx). Local copies and hashes are in `submission/research/journal_templates/`.

## Files and submission type

| Item | Current guide requirement |
|---|---|
| Article type | Select **Original Software Publication** for a first unpublished software submission. A software change following an existing SCP OSP uses **Software Update**; OrchLang has no existing OSP, so the latter does not apply. |
| Word route | Fill the official `.docx` template, embed figures, and upload it under the manuscript file category. Keep the editable source; a PDF alone is not an editable manuscript source. |
| LaTeX route | Fill the official `.tex` OSP template. Upload the compiled PDF as the manuscript and a ZIP containing all LaTeX sources, figures and bibliography under the LaTeX-source ZIP category. |
| Public software | Identify a publicly accessible external repository/archive in the metadata table. The specific OSP instructions require a public code location. |
| Software ZIP alternative | The guide also describes uploading software with the manuscript. Each software ZIP must be at most **100 MB**, with an informative description. Multiple ZIP files are allowed. Confirm the portal categories before upload. |
| Documentation | User/documentary material must accompany the submission. Developer design notes, tests and other useful supplements are welcome. |
| Software license | MIT is explicitly among accepted licenses, together with Apache, BSD, GPL/LGPL, MPL and other listed/OSI-approved choices. Article publication licensing is a separate matter. |
| Submission site | The current guide links [Editorial Manager](https://www.editorialmanager.com/scico/default1.aspx) for OSP and [Elsevier's SCP submission entry](https://submit.elsevier.com/SCICO). A previously checked alternate `default.aspx` page displayed an under-development notice; that does not establish that the current official entry is unusable. No submission has been attempted. |

## Required article components

- **Title page:** concise informative title; correctly ordered author given/family names; affiliations with full postal addresses and countries; one corresponding author and their email. A changed present address is a separate footnote, while the work's affiliation remains the main address.
- **Abstract:** factual, standalone, **at most 250 words**; purpose, procedure, main findings and conclusion. Avoid citations and unexplained abbreviations.
- **Keywords:** **1–7**, in English; avoid unnecessary multiword constructions and unfamiliar abbreviations.
- **Highlights:** required at submission as a separate editable file with `highlights` in its filename. Provide **3–5 bullets**, **at most 85 characters each**, including spaces.
- **Sections:** use numbered main sections and subsections, with abstract unnumbered. Cross-reference numbered sections.
- **Equations:** editable text, not images; number displayed equations in citation order.
- **Tables:** editable, numbered, cited in text and captioned. Avoid vertical rules and cell shading. Put notes below the table.
- **Figures:** numbered in order, cited and captioned; supply separate files. Word embeds them as well. Vector drawings may be EPS/PDF with embedded fonts. The guide specifies at least 300 dpi for photographs and 1,000 dpi for bitmap line drawings; reproducible vector diagrams avoid bitmap resolution ambiguity.
- **Supplements:** accurate, relevant, cited, descriptively captioned and submitted with the manuscript. They appear online as received; the publisher does not typeset them.
- **Video, if supplied:** descriptive manuscript references, filenames and still images. Preferred maximum 150 MB per file and 1 GB total. The current project requests an HTML demo and PowerPoint, not a video.

## References and data

The guide allows any **consistent** reference format at initial submission but asks for complete bibliographic details. The journal style uses numeric citations in square brackets, ordered by first appearance. Include DOI links where available. Every listed reference must be cited and every citation listed. Clearly identify preprints; use the peer-reviewed version when one exists. Web references include URL and access date. Software references identify creator, title, repository/archive, date, version and resolvable identifier; a permanent identifier is preferred, while a software URL is usable when no PID exists. Do not invent a DOI.

SCP applies **research-data Option B**: depositing, citing and linking data is encouraged; when sharing is impossible, explain why. A data-availability statement is encouraged. This general data policy does not weaken the OSP's specific public-software and documentation requirements. The current artifact has generated offline evidence and provenance; it has no private provider or participant dataset.

## Declarations and human author completion

- All listed authors must have substantially contributed, approved the submitted version and accepted accountability. The corresponding author must verify publication approval and that the manuscript is not under consideration elsewhere.
- Provide CRediT contribution roles for co-author contributions. Determine names/order/affiliations/contact and roles from the human authors, not repository inference.
- Complete the Elsevier competing-interest declarations tool even if there is nothing to declare, then upload its generated `.doc/.docx`. The guide does not require signatures.
- Disclose funding and sponsor roles. Do not assert no funding or no competing interests without author confirmation.
- Disclose generative AI used in manuscript preparation in a separate section **before references**, naming tools/purposes. The final statement must reflect actual human review and responsibility; draft text must not falsely assert that author review has already happened.
- Describe AI-assisted research/code development in Methods, following the [publisher's AI policy](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals). AI tools are not authors.
- Acknowledgements, if applicable, belong in a separate section immediately before references. Do not invent contributors.
- The guide allows preprints under Elsevier's sharing policy. A preprint is not a journal acceptance; simultaneous journal submission is prohibited.
- The guide specifies **single-anonymized review**, normally with at least two independent reviewers after editorial screening. Authors are not asked to anonymize the manuscript under a double-blind model in this guide.

No manuscript, editor message, declaration form, publishing agreement or payment has been submitted. Human authorship/declaration facts remain the last completion items after the substantive artifact is prepared.

## Software review dimensions and price

Reviewers assess manuscript clarity; originality/novelty/significance; source quality/completeness/readability; user/developer documentation; empirical reproducibility; and accessibility/configuration. The publisher does not provide a numerical novelty threshold or an acceptance-probability scale.

The [official APC workbook](https://legacyfileshare.elsevier.com/els_com_pricing/article-publishing-charge.xlsx), linked from [Elsevier pricing](https://www.elsevier.com/about/policies-and-standards/pricing/journals), was independently checked on 9 October 2026. Its prices dated 5 October 2026 list SCP as hybrid OA at **US$3,150 / €2,870 / £2,520 / ¥410,230**, excluding tax. This is a dated list price, not an invoice or personalized quote. The [OSP call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/) also describes institutional OA agreements. A Gold OA purchase has not been authorized or made; the applicable route/discount must be checked at submission.

## Preparation checklist

1. Build the paper from the unaltered OSP template; check the suggested text-page budget.
2. Keep abstract ≤250 words, 1–7 keywords and 3–5 separate highlights of ≤85 characters.
3. Include accurate software metadata, public code version/link, recognized license and documentation.
4. Reproduce every numerical table/figure from bound code/data; distinguish synthetic evidence from practical reuse.
5. Supply editable sources, figure files and a complete LaTeX ZIP, plus cited supplements where used.
6. Finish human author/contact/CRediT/funding/conflict/AI-review declarations.
7. Verify the current submission entry and choose **Original Software Publication**. Submission and publication decisions are separate from the internal readiness score.

**Primary sources:** [current SCP author guide](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors), [journal scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423), [OSP editor call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/), [official templates](https://legacyfileshare.elsevier.com/promis_misc/scico-osp-template.tex), and linked Elsevier policies above. All checked on 9 October 2026. No third-party template was used to infer these requirements.
