# Venue decision after rc3 strengthening

Checked 14 October 2026. SCP remains the user's first choice. The strongest
current framing is an Original Software Publication (OSP), supported by a
separate technical supplement. The official SCP OSP template already retained
in this repository advises a short paper of no more than six pages; it says
the software is evaluated and the paper supports that submission. The new
draft should follow that structure rather than claim a new general theorem.
The current [Elsevier SCP scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423)
explicitly covers verification, languages, tools and the software track.

| Venue | Fit and route | Evidence still needed |
|---|---|---|
| SCP, Original Software Publication | Primary: verification/compiler software with exact artifacts, an exemplary use and explicit semantic boundaries. | Human author responsibility and declarations; independent reproduction; persistent code/capsule archive; final current-author-guide check. Broad Python support is not demonstrated and must not be implied. |
| SoftwareX | Closest software-centered Elsevier fallback: detailed research-software description and application. | Retarget to its current template, document a concrete research use and support artifact; confirm current APC/waiver with the publisher. |
| Software Impacts | Shorter route when a concrete research application and its outputs support a software-impact story. | Evidence of use/impact and its own mandatory template. Less space for the proof/method story. |
| JOSS | Possible later software review, with no publication/submission fee. | More than six months of public active history and actual research use are current gates; the recorded repository creation date is 17 September 2026, so age alone does not meet them now. Human review of AI-assisted work must be confirmed. |

The SoftwareX and Software Impacts descriptions are supported by
[Elsevier's Research Elements page](https://www.elsevier.com/en-gb/researcher/author/tools-and-resources/research-elements-journals).
JOSS's current [submission requirements](https://joss.readthedocs.io/en/latest/submitting.html)
make its age, impact, public iteration and human-responsibility requirements
explicit. The nominal six-month calendar point is 17 March 2027; active history
and impact remain separate conditions. Its policy says more than six months,
so a date calculation alone is not an eligibility assertion.

No defensible submission-specific acceptance probability was found. A broad
scope or software format does not demonstrate a higher acceptance rate for
OrchLang. SoftwareX is a fallback by fit, not a quantified promise of easier
acceptance. Do not submit the same paper simultaneously to multiple journals.

The current ScienceDirect author-guide pages returned 403 in this check;
SoftwareX's attempted shop URL returned 404. No fee amount, deadline, review
duration or newly changed format limit is inferred from those failures. The
retained SCP template's identity and earlier official-guide retrieval are
recorded in `submission/research/journal_templates/provenance.json`.
