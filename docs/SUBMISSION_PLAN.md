# Publication strategy

Where this work can realistically be published, what each venue needs, and what
to do first. Written after the external audit in
`docs/RESEARCH_AUDIT_2026-09-17.md` and the corrections that followed it, so the
claims below are the corrected ones.

Journal details were checked against publisher and index pages in September 2026.
Scopes, fees, and metrics change: re-check each one before submitting.

---

## 1. Patent or paper?

**Paper. Do not pursue a patent.**

Section 3(k) of the Indian Patents Act excludes "a computer programme per se" and
"algorithms"; a type system is squarely both. The CRI Guidelines 2025 gate
eligibility on technical effect on an underlying technical system, which a
developer-facing static analysis is poorly placed to show. *Ferid Allani v. Union
of India* confirms there is no absolute bar, but that grant took 19 years.

If a patent is ever reconsidered, file a provisional **before** any public
disclosure — including an arXiv preprint.

---

## 2. What the paper can honestly claim

**Claimed:**

1. **A negative result.** Comparing the two branches' certified upper bounds does
   not establish that a secret leaves the bill unchanged. Counterexample in
   `examples/invalid/equal_bounds.orch`; measured at 225 differing bills in 425
   paired runs.
2. **A repair for opaque stochastic calls.** Classical relational cost analysis
   assumes an operation's cost is a known function of its input. An LLM call's
   output length is the provider's choice, so no numeric potential exists.
   Billing signatures compare structure instead, under an oracle coupling.
3. **A working compiler and a reproducible evaluation**, including componentwise
   bound checks and a paired relational experiment.

**Not claimed:**

- That combining information-flow and resource analysis is new — Ngo et al.
  (IEEE S&P 2017) and RelCost (POPL 2017) precede it.
- That token-count leakage is a new defect class — *Time Will Tell* and the
  USENIX token-length attacks establish it for single calls.
- Prompt-template placeholder checking, which is commodity.

---

## 3. How publishing in this field works

In programming languages and security, **the most prestigious venues are
conferences** (PLDI, POPL, OOPSLA, IEEE S&P, CCS), not journals. Two consequences
matter here:

- **PACMPL is a journal.** *Proceedings of the ACM on Programming Languages* is a
  Gold Open Access journal that publishes the OOPSLA, POPL, PLDI, and ICFP papers.
  It is the top journal target in this area, and it is reviewed like a top
  conference.
- **The most natural journal route runs through a workshop.** SOAP 2026 (at PLDI)
  invited selected accepted papers to extend them for a special issue of *STTT*.
  A workshop paper followed by the extended journal version is a well-trodden,
  realistic path for work at this stage.

---

## 4. Candidate journals

### Tier A — fits the work as it stands

| Journal | Why it fits | What it needs from this work |
|---|---|---|
| **Science of Computer Programming** (Elsevier) — **Software Track** | The Software Track publishes *Original Software Publications*: useful software in programming languages and software development. OrchLang is exactly that. | A mature, documented, tested artifact — which exists. The shortest route to a peer-reviewed, indexed publication. |
| **Journal of Systems and Software** (Elsevier) — **New Ideas and Trends Papers** | A short-paper format for a single new idea in an emerging area. Full validation is not required; preliminary results are welcome, and publication is fast. | Frame around LLM-workflow engineering: the negative result plus billing signatures as one new idea. |
| **International Journal on Software Tools for Technology Transfer** (Springer) — via the **SOAP → STTT** route | STTT covers semantics-based tools for development and verification, with programming languages and software engineering among its foci. | Submit to SOAP first; if accepted and invited, extend for the special issue. |

### Tier B — realistic after one or two more pieces of work

| Journal | Why it fits | Gap to close first |
|---|---|---|
| **STTT**, regular submission | As above, without a workshop invitation. | Its scope emphasises applying tools to realistic systems — port at least one real LangChain or LangGraph workflow. |
| **Science of Computer Programming**, research track | Broad programming-languages and software-methodology scope. | Complete semantics and a fuller proof than the current sketches. |
| **International Journal of Information Security** (Springer) | Scope covers theory, applications, and implementations of security. It has published static information-flow work and, in 2026, LLM prompt-injection work — both halves of this paper. | An independent security benchmark; the current one is author-written. |
| **Journal of Computer Security** | Language-based and information-flow security are within its scope. It has moved from IOS Press to SAGE — confirm the current submission system. | Precise attacker model and a stronger noninterference argument. |

### Tier C — stretch, needs substantial new results

| Journal | What would be required |
|---|---|
| **PACMPL** (OOPSLA issue) | Mechanised proofs, tokenizer-portable bounds, real-workflow case studies, comparison with a classical constant-resource baseline. |
| **ACM Transactions on Privacy and Security**, **IEEE Transactions on Dependable and Secure Computing** | A substantial security advance beyond Ngo et al., with an independent attack evaluation. |
| **ACM TOSEM**, **IEEE TSE** | A large empirical study on real workflows. |

### Use with care

| Venue | Issue |
|---|---|
| **Computers & Security** (Elsevier) | Its scope explicitly excludes work on the security of AI/ML systems such as LLMs. This paper concerns the orchestration program rather than the model, but a submission framed around LLMs risks desk rejection. |
| **Information Processing Letters** (Elsevier) | Short, but its stated focus is theoretical computer science — algorithms, complexity, formal languages. An applied PL paper with an empirical evaluation is a weak fit. |
| **IEEE Access** | In scope and fast, but charges a substantial article processing charge and carries less weight in this community. Reasonable only if the institution needs a quick Scopus-indexed publication. |
| **Journal of Open Source Software** | Free, open review, publishes research software — a good home for the artifact itself. But its process has impeded Web of Science inclusion, so it may not satisfy an institutional indexing requirement. Pursue alongside a paper, not instead of one. |

---

## 5. Institutional rules to check first

**UGC-CARE no longer exists as an approval list.** UGC discontinued it on
11 February 2025. In its place are suggestive parameters, and each institution
sets its own journal-evaluation mechanism. Ask the department which indexing it
recognises — usually Scopus and/or Web of Science — before choosing among the
journals above.

**Avoid predatory journals.** Warning signs: an unsolicited email inviting a
submission; a promised acceptance or review in days; a fee requested before
review; a vague "international journal of engineering and technology" title
covering every subject; an impact factor that is not from Clarivate; and an
editorial board you cannot verify. Every journal in Tiers A–C is published by
Elsevier, Springer, SAGE, ACM, or IEEE — confirm the submission link on the
publisher's own website, never from an email.

**Do not submit one paper to two journals at once.** Dual submission is a
publication-ethics violation at every publisher listed here.

---

## 6. Recommended sequence

1. **Confirm the institution's indexing requirement.**
2. **Post an arXiv preprint** (cs.PL, cross-listed to cs.CR). The claims are now
   corrected, so the audit's advice against posting early no longer applies.
   Check the target journal's preprint policy first.
3. **Submit the compiler to the SCP Software Track.** It is the fastest
   peer-reviewed outcome and publishes the artifact in its own right.
4. **In parallel, submit the research paper** — the negative result plus billing
   signatures — as a **JSS New Ideas and Trends Paper**, *or* to **SOAP** aiming
   for the STTT special issue. Choose one; they target the same contribution.
5. **Close the gaps for Tier B:** an independent security benchmark, one real
   workflow case study, and fuller semantics.
6. **Treat PACMPL as the long-term target**, once the proofs are mechanised and
   the tokenizer-portability gap is closed.

---

## 7. What most improves the odds, in order

1. **An independent benchmark.** The author-written security suite is the first
   thing any reviewer will question. Port a subset of an existing prompt-injection
   corpus such as AgentDojo.
2. **One real workflow.** Port a published LangChain or LangGraph pipeline and
   report what the analysis finds. This also answers STTT's emphasis on realistic
   systems.
3. **Tokenizer-portable bounds.** The clearest correctness gap left: one model's
   output cap is reused as another model's input bound.
4. **Mechanised proofs.** The cost algebra and signature equality are small enough
   for Coq or Lean.
5. **A certificate checker.** Until one exists, the certificate is a report.

---

## 8. Honest assessment

The artifact is solid: a warning-free compiler, 95 tests, and an evaluation that
fails loudly. The research contribution is real but narrow — an application of
relational cost reasoning to a setting its classical assumptions do not cover,
plus a documented negative result.

That makes it **a good fit now for a software-track or short new-ideas journal
paper**, and for the workshop-to-journal route. It is **not yet ready for a top
journal**, and polishing the prose will not change that; the gaps in section 7
will.
