# Publication strategy

Where this work can realistically be published, what each venue needs, and what
to do first. Rewritten on 25 September 2026 after the self-audit
(`docs/AUDIT_2026-09-25.md`) withdrew billing signatures and the work described in
`docs/PAPER.md` replaced them. Journal details below were checked against
publisher and index pages in September 2026 where access allowed, and each is
marked where it was not; re-check every one before submitting. §4 ranks the
candidate journals by evidence.

---

## 1. Patent or paper?

**Paper. Do not pursue a patent.**

Section 3(k) of the Indian Patents Act excludes "a computer programme per se" and
"algorithms"; a type system is squarely both. The CRI Guidelines 2025 gate
eligibility on technical effect on an underlying technical system, which a
developer-facing static analysis is poorly placed to show. *Ferid Allani v. Union
of India* confirms there is no absolute bar, but that grant took 19 years.

If a patent is ever reconsidered, file a provisional **before** any public
disclosure, including an arXiv preprint. The repository is already public.

---

## 2. What the paper can honestly claim

**Claimed** (each reproducible by `make check`, `make proofs` or
`python bench/evaluate.py`):

1. **A size-blindness theorem**, mechanised in Coq: an analysis that sees prompt
   text only through a size measure is unsound for content-dependent providers or
   rejects identical arms. It explains the project's two withdrawn rules and
   why the classical resource-aware noninterference cannot be instantiated for
   LLM calls. Mechanising it found a gap in the pen-and-paper proof.
2. **Content-level request signatures**: noninterference for every provider,
   tokenizer and observer of the transcript (mechanised), a `log2 k`
   min-capacity bound, coarser observers, and relative completeness.
3. **Token bounds that hold for real tokenizers**, built from bytes and
   per-tokenizer contracts measured on fourteen tokenizers (mechanised relative
   to the contracts).
4. **An evaluation designed to fail**, including 30 real workflows ported under
   a protocol fixed before porting, with a held-out split, an exclusion log, and
   a cross-check against AgentDojo's recorded attacks.

**Not claimed:**

- That combining information-flow and resource analysis is new (Ngo et al.,
  IEEE S&P 2017), or relational cost analysis (RelCost, POPL 2017).
- That token-count or size leakage from LLM services is new (Weiss et al.,
  USENIX Security 2024; *Time Will Tell*; Whisper Leak; prompt-cache timing).
- That the flow half is new: it is conventional IFC; CaMeL and FIDES do more, at
  run time.
- That the relational analysis matters on real workflows: none of the 30 had a
  secret.
- That "only a unified compiler can see this class of defect", or that "every
  taint checker accepts this": both were withdrawn earlier and stay withdrawn.

---

## 3. How publishing in this field works

In programming languages and security the most prestigious venues are
conferences (PLDI, POPL, OOPSLA, IEEE S&P, CCS), not journals. *PACMPL*, which
publishes the OOPSLA, POPL, PLDI and ICFP papers, is a journal and the top
journal target in the area. A workshop paper followed by an extended journal
version (for example SOAP at PLDI, with an STTT special issue) is a well-trodden
route.

---

## 4. Where to submit: an evidence-based ranking

Researched on 25 September 2026. The aim is the highest chance of acceptance at
a journal that is indexed (Scopus and Web of Science) and respected in the
field.

### How the ranking was made

Acceptance rates are **not reliably available** for these journals. Elsevier's
and Springer's journal pages refused automated access, and third-party sites
disagree with each other (one aggregator's "29%" for SCP could not be traced to
any source). No acceptance rate is used below. The ranking rests on what could
be checked:

1. **Stated scope**, from the publishers' aims and guides for authors (read
   through search-engine extracts where the page itself was blocked).
2. **Precedent**: what each journal actually published between January 2023 and
   September 2026, from Crossref's API, counted by keyword in titles.
   `python scripts/journal_survey.py` regenerates the table. Titles only,
   because most Elsevier journals deposit no abstracts with Crossref.
3. **Explicit exclusions** in the guides for authors.
4. **The bar**: impact factor and quartile as third parties report them, given as
   ranges where they disagree. Treat these as approximate.
5. **Speed and fees**: the publishers' own journal-insights figures (via search
   extracts), OpenAlex for optional open-access fees, and DOAJ for
   open-access journals.

### What each journal published, January 2023 to September 2026

| Journal | Articles | LLM | Prompt injection | Information flow | Side channel / leakage | Resource / cost | Mechanised proof |
|---|---|---|---|---|---|---|---|
| Science of Computer Programming (SCP) | 459 | 11 | 0 | 1 | 1 | 1 | 5 |
| Journal of Computer Languages (COLA) | 141 | 7 | 0 | 0 | 0 | 0 | 1 |
| The Art, Science, and Engineering of Programming | 59 | 1 | 0 | 0 | 0 | 0 | 0 |
| Int. J. on Software Tools for Technology Transfer (STTT) | 168 | 5 | 0 | 1 | 0 | 0 | 0 |
| International Journal of Information Security (IJIS) | 535 | 7 | 0 | 2 | 7 | 0 | 0 |
| Journal of Computer Security (JCS) | 73 | 0 | 0 | 0 | 0 | 0 | 1 |
| J. of Information Security and Applications (JISA) | 1,029 | 18 | 0 | 0 | 14 | 0 | 0 |
| Computers & Security | 1,808 | 14 | 0 | 11 | 29 | 0 | 0 |
| Cybersecurity (Springer) | 480 | 11 | 4 | 0 | 6 | 0 | 0 |
| J. of Logical and Algebraic Methods in Programming | 214 | 0 | 0 | 0 | 0 | 0 | 3 |
| Journal of Systems and Software | 1,199 | 75 | 1 | 1 | 0 | 1 | 1 |
| IEEE Trans. Dependable and Secure Computing | 2,187 | 35 | 5 | 7 | 54 | 1 | 0 |

The counts matter less than the specific papers behind them. **SCP has
published the two papers closest to this one:** a static worst-case cost
analysis for a workflow modelling language (Ali, Lamo and Pun, "Cost analysis
for a resource sensitive workflow modelling language", SCP 225, 2023) and a
language for secure information flow (Manzino and de Latorre, "A
Haskell-embedded DSL for secure information-flow", SCP 247, 2026). It has also
published work on LLM code-generation security (SCP 251, 2026) and five
mechanised-proof papers. STTT published an information-flow program logic
(Filinski, Larsen and Jensen, 2024). Cybersecurity published four
prompt-injection papers in 2026.

### Ranking

| Rank | Journal | Evidence of fit | Risks | Bar (IF, quartile) | Speed | Author fee |
|---|---|---|---|---|---|---|
| **1** | **Science of Computer Programming**, research track | Scope names programming languages, formal methods and program analysis; the two closest precedents above are SCP papers; the paper is already in SCP's format | Q3 journal, so reviewers expect solid engineering and clear writing; the practical-relevance gap (no real secret) will be raised | 1.4 to 1.95, Q3 (Software Engineering) | 6 days to first decision, 87 to a decision after review, 222 to acceptance | None on the subscription route; USD 2,600 optional open access |
| **2** | **Journal of Computer Languages** (Elsevier) | Scope: design, implementation and use of computer languages, type systems, language tools; published a type-system paper in 2026 and LLM-for-code work | Small (about 40 papers a year), so fewer slots; frame the paper as a DSL with a type system | 2.0 to 2.4, Q3 | 2 days to first decision, 71 to a decision after review, 196 to acceptance | None on the subscription route; USD 2,640 optional open access |
| **3** | **International Journal of Information Security** (Springer) | Scope includes "formal methods in information security"; published information-flow control (2024, 2025) and seven LLM-security papers (2025) | Higher bar; security reviewers will weigh real-world impact, the paper's weakest point; crowd-reported review times are long (few reports) | 5.0 (2025; five-year 4.6), Q1 | Median 9 days to first decision | None on the subscription route |
| **4** | **The Art, Science, and Engineering of Programming** | Scope explicitly lists "security programming", "program verification" and "interpreters, virtual machines, and compilers"; diamond open access; two-round review with at least three reviewers | 22-page limit, so the paper must be cut; Scopus Q4 (SJR about 0.2 to 0.3); Web of Science status not found, so it may not satisfy an institutional indexing rule | Q4 (Scopus) | Fixed deadlines; the next is 1 October 2026 (too soon), then the following round | None |
| **5** | **STTT** (Springer) | Tool-oriented; published an information-flow logic (2024) and LLM-plus-analysis work (2025, 2026) | Many papers arrive through conference special issues; the paper would need a tool-paper framing | 1.7 (2025), Q3 | not found | None on the subscription route |
| **6** | **Cybersecurity** (Springer, open access) | Published four prompt-injection papers in 2026 | Less oriented to programming languages; the fee is unclear (DOAJ lists USD 1,485, while the journal's own fee text, via search, says its sponsor covers costs); confirm before submitting | about 4.1 (2025) | about 9 weeks to publication (DOAJ) | Unclear, see risks |
| 7 | Journal of Information Security and Applications (Elsevier) | Publishes much LLM-security work | Its guide restricts AI/ML-centred submissions; language-based security is not in its topic list | about 5.2, Q1 or Q2 by category | 5 days to first decision | None on the subscription route |
| 8 | Journal of Computer Security (IOS Press/SAGE) | Information flow is core scope | Only 15 to 17 papers a year, so very few slots | about 1.3 | not found | None on the subscription route |

**Avoid: Computers & Security.** Its guide for authors says "items directed to
the security of AI/ML systems themselves (such as LLM and federated learning)
are out of scope", and it has had a moratorium on AI/ML-centred submissions
since early 2024. A desk rejection is likely.

**Low chance for now:** PACMPL (OOPSLA, POPL), ACM TOPLAS, ACM TOPS, ACM TOSEM,
IEEE TDSC. They are the right kind of venue, but the paper lacks a demonstrated
real-world instance of the channel, which these venues would expect.

**Pay-to-publish fallbacks, only if a deadline forces it:** IEEE Access (its
own page states "an average acceptance rate of 20%" and 4 to 6 weeks from
submission to publication; APC USD 2,160 per DOAJ) and PeerJ Computer Science
(APC USD 1,395). They are faster but carry less weight in programming languages
and security.

### Recommended order

1. **SCP research track**, as planned. It has the strongest evidence of fit and
   no fee.
2. If SCP declines, **COLA** (Elsevier can offer to transfer a rejected
   manuscript between its journals) or **IJIS**, depending on the reviewers'
   comments: COLA if they valued the language and type system, IJIS if they
   valued the security results.
3. **<Programming>** if the institution accepts Scopus-only indexing and the
   paper can be cut to 22 pages.

Submit to one journal at a time; see the warning below.

### What raises the odds at any of them

- **Cite the SCP precedents.** The paper does not yet cite Ali, Lamo and Pun
  (2023) or Manzino and de Latorre (2026). Both are related work, and editors
  often choose reviewers from the authors of such papers. Read both first.
- **A cover letter** naming the fit (the two precedents), the artifact (`make
  check`, `make proofs`, `python bench/evaluate.py`), and the negative results
  stated plainly.
- **An arXiv preprint** after checking each journal's preprint policy.
- **Show the channel in a real workflow** (§7, item 1). This is the single
  change most likely to move every venue above from "possible" to "likely".

### SCP's requirements

SCP's guide for authors states that the abstract must not exceed 250 words.
Its Software Track takes Original Software Publications (OSPs) of three to six
pages pointing to a public repository; the research track suits this paper. The
guide (`sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors`)
refused automated access, so these were read from search-engine extracts.
**Before submitting, read the guide in a browser and confirm:** highlights
(Elsevier journals usually ask for three to five bullets of at most 85
characters; the paper has five), keywords, the declaration of generative AI use
(the paper has one), the competing-interest declaration, the data-availability
statement, and the reference style.

**A licence is needed before submitting anything.** The repository has no licence
file. An OSP requires one, and the research track's data-availability statement
is much stronger with one. Choosing the licence is the author's decision (MIT or
Apache-2.0 are usual for research compilers; the corpus reproduces MIT-licensed
text, whose notices are in `THIRD_PARTY_NOTICES.md`).

**Read recent SCP papers before submitting.** ScienceDirect blocks automated
access, so this could not be done from here. Read eight to twelve research-track
papers from the last two volumes, starting with the two precedents above, and
note their length, section structure, where proofs live, how the evaluation is
presented and how the artifact is cited. Adjust `docs/PAPER.md` to match the
median; expect to move the full proofs of `docs/FORMAL_MODEL.md` into an
appendix.

Venues to use with care, unchanged from the previous plan: *IPL* is
theoretical; *JOSS* is a good home for the artifact alongside a paper, not
instead of one.

**Do not submit one paper to two journals at once.** Dual submission is a
publication-ethics violation at every publisher listed here.

### Sources

- Journal-insights timings (SCP, COLA, Computers & Security, JISA) and Computers
  & Security's out-of-scope statement: search-engine extracts of the
  ScienceDirect journal, insights and guide-for-authors pages, 25 September 2026.
- IJIS scope and median time to first decision, STTT's 2025 impact factor:
  search-engine extracts of the Springer journal pages.
- <Programming>: `programming-journal.org/cfp/` and `/submission/`, read
  directly.
- IEEE Access acceptance rate: `ieeeaccess.ieee.org/authors/`, read directly.
- Fees: OpenAlex source records (optional open-access prices) and DOAJ
  (open-access journals), queried directly.
- Impact factors and quartiles: LetPub, journalmetrics.org, Researcher.Life and
  Editage, which disagree by up to 0.5; the ranges above span them.
- Publication counts: Crossref, via `scripts/journal_survey.py`.

---

## 5. Institutional rules to check first

UGC-CARE no longer exists as an approval list (discontinued 11 February 2025);
each institution sets its own evaluation mechanism, usually Scopus and/or Web of
Science indexing. Ask the department. Avoid predatory journals: unsolicited
invitations, promised acceptance in days, fees before review, impact factors not
from Clarivate, unverifiable editorial boards. Confirm every submission link on
the publisher's own site.

---

## 6. Recommended sequence

1. **Choose a licence** and add it to the repository.
2. **Confirm the institution's indexing requirement.**
3. **Read recent SCP papers** (§4), cite the two SCP precedents, and adjust the paper's form.
4. **Post an arXiv preprint** (cs.PL, cross-listed to cs.CR) after checking SCP's
   preprint policy.
5. **Submit to the SCP research track**; if it declines, follow the order in §4.
6. In parallel, and only if it is a *different* paper, consider an OSP for the
   compiler. An OSP about the same contribution as the research paper would be
   close to dual submission; ask the editor first.

---

## 7. What would most improve the odds, in order

1. **Show the channel in the wild.** Find deployed or published workflows that
   branch on private data they do not send to a model (tier-based model
   routing, risk flags, local PII detectors) and port them. This is the single
   largest gap: the relational analysis has not met a real secret.
2. **Observer-relative declassification**, so that workflows sending private data
   to a trusted provider can still be analysed against the network and the bill.
3. **Separate data and program-counter labels for integrity**, removing the two
   false positives the held-out split found.
4. **A certificate checker** with tampering tests (open problem OP-11).
5. **A hosted provider**: check the envelope overheads and output caps the ports
   assume against a real endpoint's billing.

---

## 8. Novelty self-assessment

A revision of the brief's §6, in its style: component scores against the global
literature, with reasons, meant to be challenged.

**Absolute novelty against the global literature: 5 / 10** (was 4.5).

| Component | Score | Reasoning |
|---|---|---|
| Size-blindness theorem (Theorem 6), mechanised | 6 | A clean impossibility result that turns "the classical instantiation does not transfer" from an assertion into a theorem, and explains two concrete unsound rules. The proof is elementary once the adversarial provider is found; a reviewer may call it obvious. The mechanisation and the gap it caught add credibility, not novelty. |
| Content-level request signatures, resolution by feasible outcome vectors | 4 | The mechanism is the constant-time discipline with requests as the observable operation, and RelCost's refinements can already express "identical inputs, zero cost difference" for a fixed pair of runs. What is new is the resolution over every feasible secret outcome, the provider-independence of the guarantee under the coupling, the observers, relative completeness, and the application to LLM calls. |
| Leakage bound `log2 k` (Theorem 2) | 3 | A direct application of min-capacity and Köpf–Basin counting. The only fresh step is counting classes modulo the coupling, which is what makes the bound finite and small. |
| Byte-based guaranteed token bound with measured tokenizer contracts | 6 | I have not found a sound worst-case input-token bound for LLM calls in the literature, nor the measurements that show why token counts cannot be composed (non-subadditivity, re-encoding inflation, `tokens > bytes`). Individually, tokenizer irregularities are known (Petrov et al. 2023); the methodology is the contribution. The search was not exhaustive: LLM cost-estimation tools may do something similar unpublished. |
| Coq mechanisation | 4 | A small calculus with standard techniques. It raises the paper's credibility more than its novelty. |
| Real-workflow corpus and protocol | 4 | Careful methodology (pre-registered labels, held-out split, source verification, AgentDojo cross-check) on a modest corpus. Its most interesting results are negative or neutral: the relational analysis never fires, the fixed plan, not the checker, stops every recorded AgentDojo attack, and the flow checker over-reports twice. |
| Two-axis flow typing with the data/pc split (OP-1) | 3 | Textbook IFC with a standard refinement. CaMeL and FIDES enforce richer policies dynamically. |
| Structural cost bound | 2 | Textbook. |
| The integrated artifact | 6 | Distinctive in combination and completeness; no single piece is. |

**For the SCP research track: about 6 / 10 today**, up from the brief's 5. The
reason is not higher novelty but that every claim is now backed by a theorem,
a mechanisation or a measurement, and the negative results are demonstrated
rather than asserted, which is what that venue weighs. The largest risk is
practical relevance: a reviewer can fairly say the side channel the paper is
built around was not found in any of the thirty real workflows. The paper says so
in its abstract; it cannot yet say more.

**Where I might be over-scoring.** The byte-bound row at 6 depends on no one
having published the same methodology; I searched the LLM-security and
programming-languages literature I could reach, not industry documentation. The
size-blindness row at 6 assumes reviewers accept that an impossibility result
about a whole class of analyses is worth more than its short proof.
