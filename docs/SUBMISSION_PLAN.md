# Publication strategy

Where this work can realistically be published, what each venue needs, and what
to do first. Rewritten on 25 September 2026 after the self-audit
(`docs/AUDIT_2026-09-25.md`) withdrew billing signatures and the work described in
`docs/PAPER.md` replaced them. Journal details below were checked against
publisher and index pages in September 2026 where access allowed, and each is
marked where it was not; re-check every one before submitting.

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

## 4. Target: Science of Computer Programming, research track

The brief targets *Science of Computer Programming* (Elsevier), and the work now
fits its research track better than its Original Software Publication (OSP) track:
it has theorems, a mechanisation, an implementation and an evaluation, which is
more than an OSP's three to six pages can carry.

**What SCP asks for, as far as could be verified.** SCP's guide for authors
states that the abstract must not exceed 250 words and that an OSP is three to six
pages pointing to a publicly available repository. The guide itself
(`sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors`)
refused automated access, so these were read from search-engine extracts of it.
**Before submitting, read the guide in a browser and confirm:** highlights (Elsevier
journals usually ask for three to five bullets of at most 85 characters; the
paper has five), keywords, the declaration of generative AI use (Elsevier's
policy requires one; the paper has one), the competing-interest declaration, the
data-availability statement, and the reference style.

**A licence is needed before submitting anything.** The repository has no licence
file. An OSP requires the code to be publicly available under an open-source
licence, and the research track's data-availability statement is much stronger
with one. Choosing the licence is the author's decision (MIT or Apache-2.0 are
usual for research compilers; the corpus reproduces MIT-licensed text, whose
notices are in `THIRD_PARTY_NOTICES.md`).

**The venue study the brief asked for was not possible from here.** ScienceDirect
blocks automated access to SCP's articles, so eight to twelve recent SCP papers
could not be read. The paper's form follows SCP's published requirements above
and the conventions shared by programming-languages journals: contributions
stated up front, related work positioned early, theorems with proofs or proof
sketches and a pointer to the full proofs, an evaluation organised by research
questions, a threats-to-validity section, and limitations in the body. **Do this
before submitting:** read eight to twelve research-track papers from the last two
volumes of SCP that combine a formal development with an implementation, and note
for each its length, section structure, where proofs live (body or appendix), how
the evaluation is presented, whether threats to validity are a section, and how
the artifact is cited. Adjust `docs/PAPER.md` to match the median. Expect to move
the full proofs of `docs/FORMAL_MODEL.md` into an appendix.

### Other venues, if SCP declines

| Venue | Fit | Gap |
|---|---|---|
| *STTT* (via SOAP, or regular) | Semantics-based tools, applied to realistic systems — the real-workflow corpus now answers this | Tool-paper framing |
| *International Journal of Information Security* | Language-based security and LLM security are both in scope | The relational half is not exercised on real workflows |
| *Journal of Computer Security* | Information flow is core scope | Needs observer-relative declassification to be interesting to that audience |
| *PACMPL* (OOPSLA) | The theorem, mechanisation and evaluation are the right kind of work | A demonstration that deployed workflows contain the channel; a verified or certificate-checked implementation |

Venues to avoid or use with care are unchanged from the previous plan:
*Computers & Security* excludes AI/ML security from scope; *IPL* is theoretical;
*IEEE Access* charges a substantial fee and carries less weight here; *JOSS* is a
good home for the artifact alongside a paper, not instead of one.

**Do not submit one paper to two journals at once.** Dual submission is a
publication-ethics violation at every publisher listed here.

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
3. **Do the SCP venue study** in §4 and adjust the paper's form.
4. **Post an arXiv preprint** (cs.PL, cross-listed to cs.CR) after checking SCP's
   preprint policy.
5. **Submit to the SCP research track.**
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
