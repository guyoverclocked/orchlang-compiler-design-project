# Publication strategy

This document records the decision between a patent and an academic paper, the
evidence behind it, and a concrete submission plan.

---

## 1. Patent or paper?

**Recommendation: paper. Do not pursue a patent.**

### Why a patent is the wrong instrument here

**Section 3(k) hits this work twice.** The Indian Patents Act excludes "a
mathematical method or business method or a **computer programme per se** or
**algorithms**." A type system that derives a bound and a label assignment is
both a computer programme and an algorithm. This is not a borderline case that
careful drafting rescues; it is the centre of the exclusion.

**The technical-effect gateway is hard to clear for a static analysis.** The CRI
Guidelines 2025 (issued 29 July 2025) make *technical effect* — a concrete,
measurable improvement to an underlying technical system — the test, and require
examiners to identify the core problem, map the solution, and judge whether the
effect is genuinely technical or "merely functional and administrative." The
beneficiary of OrchLang's analysis is the *developer*, who learns something
before deployment. No hardware behaves differently. That is the hardest possible
posture.

An argument exists — the analysis demonstrably prevents real token expenditure
and real data exfiltration, which are effects on a technical system — and
*Ferid Allani v. Union of India* (Delhi HC 2019; IPAB grant 20 July 2020)
confirms there is no absolute bar. But Allani's patent took **19 years** from
provisional filing to grant.

**The economics are bad.** Even a smooth prosecution runs 4–6 years and, with
attorney fees, ₹1–2 lakh. A rejection under 3(k) is the modal outcome for a
claim of this shape.

**It delays and constrains the thing that actually has value.** For a student,
publication is the currency: it is citable, it supports applications, and it
takes months rather than years.

### If a patent is nonetheless wanted later

File a provisional *before* any public disclosure, and draft claims around a
**system** that measurably reduces resource consumption and prevents credential
transmission — not around the type system itself. Note that publishing first
does not destroy Indian novelty if a provisional is on file first, so the
sequence matters: provisional, then arXiv. Given the analysis above, we judge
this a poor use of time and money, but the ordering is the thing to get right if
the decision is revisited.

---

## 2. What the paper claims

A one-line statement of novelty, which the prior-art survey in `PAPER.md` §12
supports:

> The first compiled source DSL whose type system certifies, before any model is
> invoked, both a token-cost bound and a two-axis information-flow property, and
> which detects secret-dependent cost channels that neither analysis finds
> alone.

The strongest defensible claims, in order:

1. **The cost channel (`E236`).** A genuinely new defect class, and the best
   argument for unifying the two analyses. This is the paper's most original
   idea and should lead the pitch.
2. **Sound structural cost bounds, with the flat rule measured as unsound.**
   0 violations in 4,600 runs vs 13.5% for the obvious rule is a clean,
   quantified result.
3. **Static two-axis flow typing for LLM workflows.** Every comparable system is
   a runtime monitor.
4. **The guaranteed/estimated split.** A small idea that reviewers tend to like,
   because it is honest about where the guarantee stops.

**Explicitly not claimed:** prompt-template placeholder checking. It is
commodity (promptml, promptctl, type-safe-prompt). The paper disclaims it.

---

## 3. Where to submit

Ranked by expected value for an undergraduate first paper.

### Step 0 — arXiv preprint (do this first, immediately)

cs.PL primary, cs.CR and cs.SE cross-list. Free, same-day, establishes priority,
and citable while under review. There is no reason to delay this.

### Tier 1 — best fit, realistic

| Venue | Why it fits | Timing |
|---|---|---|
| **ACM SAC** — Software Verification and Testing, or Programming Languages track | Full paper, archival, ~25% acceptance, explicitly welcomes applied PL work with real artifacts. The evaluation is strong enough to compete. | Deadlines typically Sep–Oct for the following spring |
| **SOAP** (State of the Art in Program Analysis), co-located with PLDI | Exactly this topic — a new static analysis with a real implementation. Workshop acceptance rates are friendly and the audience is the right one. | Spring deadline, June workshop |
| **ACM SIGPLAN Student Research Competition** (PLDI / SPLASH / POPL) | Built for undergraduate work. The cost-channel result presents extremely well in a poster/talk format. | Varies by host conference |

### Tier 2 — credible, broader

| Venue | Notes |
|---|---|
| **ICSE NIER / FSE IVR / ASE NIER** | Short "new ideas" tracks. The cost-channel finding is precisely a new-idea contribution. Competitive but the right shape. |
| **IEEE COMPSAC** | Broad, archival, realistic acceptance, well-indexed. |
| **LLM4Code / AIware** and similar ICSE-colocated workshops | Topical match with the LLM-engineering audience. |

### Tier 3 — security framing

The work maps directly onto OWASP LLM01 (Prompt Injection) and LLM07 (System
Prompt Leakage). A reframed version emphasising the injection results suits
workshops at **ACSAC** or **CCS**. Only pursue this if the PL framing stalls;
do not submit both simultaneously.

### Avoid

Predatory or unindexed venues, and low-quality "international journals" that
solicit by email. This work is good enough not to need them, and publishing
there actively damages its value.

---

## 4. Before submitting

Ordered by how much each improves acceptance odds per unit of effort.

**High value**

1. **Port an independent security benchmark.** The author-written suite is the
   paper's most serious weakness (§11) and the first thing a reviewer will
   attack. Translating a subset of an existing injection corpus such as
   AgentDojo into OrchLang would convert the weakest section into a strong one.
2. **Mechanize Theorem 1** in Coq, Lean, or Agda. The cost algebra is small
   enough that this is genuinely tractable, and "mechanized soundness" changes
   how the whole paper reads.
3. **Reformat to the target template** (ACM `acmart` or IEEE conference) and cut
   to the page limit. The current draft is longer than most limits allow; §7 and
   §12 compress well.

**Medium value**

4. **A case study on a real workflow.** Port one published LangChain or
   LangGraph pipeline to OrchLang and report what the analysis says about it.
   Even one convincing example blunts the "synthetic corpus" criticism.
5. **Figures.** The lattice, the derivation tree for a branch/retry workflow,
   and the injection propagation path. Reviewers read figures first.
6. **Resolve the citation placeholders.** Several references are cited by arXiv
   ID with incomplete author lists; fill these in from the actual papers before
   submission.

**Lower value, worth doing**

7. Mention the ~6 ms figure carefully — it is dominated by process startup, and a
   reviewer may ask. Measure in-process analysis time separately.
8. Add a short "language design rationale" appendix; the three commitments in §3
   are a defensible contribution on their own.

---

## 5. Honest assessment

The work is real. It compiles, it is tested (83 assertions), the evaluation is
reproducible from a generator and a harness, and the prior-art position holds up
to scrutiny: the cost column and the flow column of the related-work table are
near-disjoint, and everything in the flow column runs at execution time.

The cost-channel result is the part that makes this publishable rather than
merely competent, because it is a finding rather than an implementation — a
defect class that exists only because two analyses were put in the same type
system.

The honest weaknesses are the author-written security benchmark, the synthetic
cost corpus, and the unmechanized proofs. All three are stated plainly in §11
rather than hidden, which is the right call: reviewers punish concealed
limitations far more than acknowledged ones.

Realistic expectation: **a good chance at a workshop or SAC on the current
draft**, and a credible shot at a NIER/short track. With items 1 and 2 from §4
done, it would be competitive for a stronger venue.
