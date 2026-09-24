# OrchLang — Agent Handoff and Research Brief

**Written:** 24 September 2026
**Repository:** `github.com/guyoverclocked/orchlang-compiler-design-project`, branch `main` at `0d8c0f0`
**Target venue:** *Science of Computer Programming* (Elsevier)
**Audience:** an autonomous coding/research agent taking over this project

---

## 0. Your mission

Take a working compiler with a correct-but-narrow research contribution and make
it worth a *Science of Computer Programming* research paper. Then write that
paper.

You have **full autonomy** over the repository: change the language, change the
analyses, delete things that do not earn their place, restructure the
evaluation, disagree with any judgement recorded here. Two constraints only:

1. **Never weaken a claim's evidence to make the claim survive.** If an
   experiment contradicts a stated property, the property is wrong, not the
   experiment. This project already had one theorem withdrawn for exactly this
   reason, and that withdrawal is now among its strongest assets.
2. **Everything you assert must be reproducible from a clean clone.** If
   `make check` and `python bench/evaluate.py` do not support a sentence, the
   sentence does not go in the paper.

This brief deliberately leaves hard problems unsolved. Several of them I know
are the right problems and could not solve. They are marked. Solving even two
substantially changes what venue this work belongs in.

---

## 1. Start here: build it and break it

```sh
git clone https://github.com/guyoverclocked/orchlang-compiler-design-project
cd orchlang-compiler-design-project
make check                  # strict build, 95 assertions, example corpus
python bench/generate.py    # regenerate the benchmark corpus
python bench/evaluate.py    # every number in the paper; exits nonzero on failure
```

Requires a C++17 compiler (GCC 7+, Clang 5+, MSVC 2017+). GCC 6 is too old — no
`<optional>`. On Windows a suitable toolchain path is recorded in `.envrc`
(gitignored); regenerate it if missing.

Then read these, in this order, before changing anything:

| File | Why |
|---|---|
| `README.md` | The intuition, from zero. Read first. |
| `docs/LANGUAGE_SPEC.md` | Grammar, label lattice, cost algebra, every diagnostic code. |
| `docs/PAPER.md` | The current write-up. This is what you are replacing. |
| `docs/RESEARCH_AUDIT_2026-09-17.md` | **The most important document here.** An external audit that falsified the central theorem and found four implementation-level soundness bugs. Read it in full. |
| `audit/2026-09-17/` | The auditor's counterexamples and reproduction scripts. All five are now regression tests. |
| `docs/SUBMISSION_PLAN.md` | Venue analysis, patent reasoning, publication sequencing. |
| `docs/REVIEW_DEMO.md` | A verified command sequence. Good way to see everything work. |

**First task, before you read further:** run the three commands above, confirm
95/95 and a zero exit from the harness, then run
`./orchc check examples/invalid/equal_bounds.orch` and make sure you understand
*why* that program is rejected. If that rejection does not seem obviously
correct to you, re-read §4 of this brief. The entire contribution hinges on it.

---

## 2. What the project is, in one page

An LLM feature is a little program: take input → fill a prompt template → call a
model → do something with the answer. That program is where things go wrong, and
because it is usually Python or YAML, nothing checks it.

OrchLang is a small statically typed language for writing that program down, and
a compiler that answers three questions from source alone, offline, with no API
key:

1. **What is the most this can cost?** A worst-case token bound.
2. **Where can data go?** Can a credential reach a prompt, an output, or a tool;
   can text from an untrusted source drive a tool.
3. **Can a secret change the bill?** Is the per-model billing vector independent
   of every secret.

Question 3 is the research content. Questions 1 and 2 are competent but
derivative, and the paper must say so.

Hand-written C++17, 5,340 lines across 12 sources and 15 headers. No parser
generator, no dependencies, no network access anywhere.

---

## 3. Architecture

| Stage | File | Produces |
|---|---|---|
| Lexer | `src/lexer.cpp` | tokens with line/column |
| Parser | `src/parser.cpp` | owned AST, recursive descent, statement-level recovery |
| Symbols | `src/symbol_table.cpp` | scopes, one per block |
| Semantics | `src/semantic_analyzer.cpp` | types, names, security labels, per-call-site facts |
| Cost | `src/cost_analyzer.cpp` | worst-case bound, two components |
| **Relational** | `src/relational.cpp` | **billing signatures — the contribution** |
| IR | `src/ir.cpp` | region-annotated DAG, cycle detection |
| Report | `src/certificate.cpp` | JSON analysis certificate |
| Runtime | `src/interpreter.cpp` | deterministic offline mock, exists to falsify the bound |

The semantic pass records per-call facts (`CallSiteFacts`, `ArgumentFact` in
`include/semantic_analyzer.hpp`) so the cost and relational passes are pure
structural walks needing no symbol lookups. Preserve that separation; it is what
makes the relational pass readable.

---

## 4. The technical core

### 4.1 The problem

```orchlang
if is_enterprise {                                    // a secret
  let reply = call escalate(ticket)    using large;   // 900 tokens
} else {
  let reply = call acknowledge(ticket) using small;   // 150 tokens
}
```

No secret value reaches a prompt, an output, or a tool. Every information-flow
analysis accepts this, correctly — no *value* goes anywhere it shouldn't. The
invoice still reveals the secret. This is a resource side channel.

### 4.2 Why the classical repair does not transfer

Resource side channels are well studied. Ngo, Dehesa-Azuara, Fredrikson and
Hoffmann (IEEE S&P 2017) formalise **resource-aware noninterference** by
combining information-flow typing with automatic amortized resource analysis.
RelCost (POPL 2017) bounds the *difference* in cost between two executions,
explicitly for side-channel reasoning.

Both attach a **numeric potential** to program state, which requires that each
operation's cost be a known function of its input. An LLM call has no such
function: you request at most `max_tokens`, and how many arrive is the
provider's choice. Two runs of the same program on the same input already differ
in cost.

So: no potential can be assigned, and "constant resource" is the wrong property
because no LLM workflow has constant resource use.

### 4.3 What we do instead

Compare **structure**, not numbers.

- **Observation:** the per-model billing vector — for each model, input tokens,
  output tokens, call count. This is what an itemised invoice shows. A scalar
  total is wrong: two runs can agree on total tokens while charging different
  models at different published prices.
- **Coupling:** a model oracle fixes, for each model and call index, the output
  length and whether a retry attempt succeeded. Two executions are compared under
  the *same* oracle. Without this the bill varies for reasons unrelated to the
  secret.
- **Signature:** each branch arm becomes an ordered sequence of
  `Call(model, sizeTerm)`, `Retry(n, sig)`, `Branch(publicGuard, sig, sig)`. The
  size term may mention only quantities that provably agree across the two
  compared runs: constants, `|x|` for a variable bound *outside* the branch, and
  earlier calls referred to **by position** (not by name — the arms bind
  different names to corresponding calls).
- **Rule:** at a secret-guarded branch, both signatures must be defined and
  equal. A secret-dependent argument makes a signature undefined, which rejects.

### 4.4 The negative result

The obvious rule — accept when both arms have equal certified upper bounds — is
**unsound**. `examples/invalid/equal_bounds.orch`: both arms call the same model
with one argument capped at 100, so both bound at exactly 111. But `x` and `y`
are different strings with different actual lengths. Measured: the bill differs
in **225 of 425** paired runs.

This compiler implemented that rule and claimed a theorem for it. An external
audit produced the counterexample.

---

## 5. Current state: claims, evidence, and their exact limits

From `bench/results/evaluation.txt`:

| Experiment | Result |
|---|---|
| Certified bound exceeded, checked **componentwise** | 0 of 4,600 |
| Flat per-call sum exceeded | 636 of 4,600 (13.8%) |
| Control-flow-aware rule exceeded | 644 of 4,600 (14.0%) |
| Slack over peak observed | median 1.11×, zero dead branch arms |
| Accepted workflows: secret moved the bill | 0 of 2,975 paired comparisons |
| Rejected workflows: concrete leaking witness | 7 of 7 |
| Flow policy conformance | 13/13 unsafe rejected, 13/13 safe accepted |

**Theorems as currently stated** (`docs/PAPER.md` §6): a unary bound theorem, a
billing-noninterference theorem, and an effect-noninterference theorem. All are
**pen-and-paper sketches**. None is mechanised. The C++ is not verified against
them. Treat every one as a hypothesis you may need to restate or withdraw.

**Known limitations, all of which the paper states openly:** the guarantee is
relative to an oracle coupling; declassification is trusted; token bounds are not
portable across tokenizers; the corpus is generated; the security labels are the
author's; the certificate is a report with no independent checker; timing is not
modelled.

---

## 6. Novelty assessment

My honest scoring, for you to challenge.

**Absolute novelty against the global literature: 4.5 / 10.**

| Component | Score | Reasoning |
|---|---|---|
| Billing signatures under an oracle coupling | 5 | Sound, but close to two known things joined: the constant-time discipline (make both branches execute the same operation sequence) and coupling-based relational reasoning. The fresh part is *why* it is necessary, not the mechanism. |
| The negative result | 5 | Crisp, reproducible, measured — but elementary once stated, and it is our own bug with no evidence anyone else made it. |
| Guaranteed/estimated bound split | 5 | Small but thoughtful; I have not seen the assumption boundary drawn explicitly this way. |
| Executable falsification harness for a relational claim | 5 | Good methodology, modest novelty. |
| The integrated artifact | 6 | Combination and completeness are distinctive; no single piece is. |
| Two-axis flow typing in a compiled DSL | 3 | Textbook IFC. The injection-propagation rule is CaMeL's rule restated as a typing rule. |
| Structural cost bound (branch max, retry multiply) | 2 | Genuinely textbook. |

**For SCP specifically: the research track will read this as ~5/10 today.** That
is publishable-adjacent, not publishable. §9 is how you move it.

**Challenge this.** If you think I over- or under-scored a row, say so with an
argument and a citation. I would rather be corrected than deferred to.

---

## 7. Prior art you must know

Each of these is a potential reviewer weapon. Know what it does and where our
boundary is.

| Work | What it establishes | Our boundary |
|---|---|---|
| **Ngo, Dehesa-Azuara, Fredrikson, Hoffmann, IEEE S&P 2017** (arXiv:1801.01896) | Resource-aware noninterference via AARA + IFC. Certifies programs that violate constant-time when it leaks nothing. | **The most dangerous citation.** Assumes known per-operation costs. We have none. |
| **RelCost, POPL 2017** (Çiçek, Barthe, Gaboardi, Garg, Hoffmann) | Relational refinement types bounding cost *differences*, motivated by side channels. | Same assumption. We compare structure because no number exists. |
| **AARA** (Hoffmann et al., TOPLAS 2012; Kahn & Hoffmann, FoSSaCS 2020) | Potential method for resource bounds as type inference. | Never applied to LLM tokens; the potential method needs known costs. |
| **Time Will Tell** (arXiv:2412.15431) | Recovers input properties from output token counts and timing on production models. | Establishes the attack at single-call granularity. We address workflow-level billing. |
| **USENIX Security 2024 token-length attacks** (Weiss et al.) | Remote keylogging from token-length side channels. | Same channel family, network observer. |
| **CaMeL** (arXiv:2503.18813, DeepMind) | Dual-LLM planner, custom interpreter, dynamic dataflow graph, capabilities at tool calls. | Runtime. Not string scanning — do not mischaracterise it; an earlier draft did. |
| **FIDES** (arXiv:2505.23643) | Planner with dynamic confidentiality/integrity labels and controlled release; AgentDojo evaluation. | Closest flow comparator. Runtime. No resource reasoning. |
| **AgentFlow** (arXiv:2608.22868) | Policy language, runtime monitor **plus a bounded SMT verifier**. | Partly static. Policy-level, not a source type system. |
| **NeuroTaint** (arXiv:2604.23374) | **Offline auditing of execution traces.** | Post-hoc, not pre-execution. An earlier draft called it runtime; that was wrong. |
| **Agentproof** (arXiv:2603.20356) | Static verification of extracted workflow graphs; topology and temporal policies. | Static, but no types, resources, or information flow. |
| **Token Budgets** (arXiv:2606.04056) | 63 production budget-overrun incidents; affine-typed Rust budget with runtime caps. | Compile-time *bookkeeping integrity*; the cap is enforced at run time. Its 4–6× reservation slack is **not** comparable to our bound/observed-peak ratio on a different corpus — do not compare them directly. |
| Classical IFC: Denning 1977; Volpano, **Smith, Irvine** 1996; Myers POPL'99; Sabelfeld & Myers JSAC'03; Sabelfeld & Sands CSFW'05 | Foundations. | Note the author order on Volpano — an earlier draft had it wrong. |

**Gap you must close yourself:** I did not systematically search quantitative
information flow (Smith's min-entropy leakage, Köpf & Basin's information-theoretic
side-channel bounds) or probabilistic relational Hoare logic (Barthe et al.). Both
are directly relevant to OP-4 below and may already contain what you need — or may
already contain something that sinks it. **Search them before building.**

---

## 8. Reviewer attacks, ranked

For each: the attack, the current defence, and why the defence is weak. Your job
is to convert the weak ones into strong ones.

### A1. "This is Ngo et al. instantiated with tokens as the resource."

*Defence:* the potential method requires a known cost function per operation; an
LLM call has none, so the instantiation is not mechanical.

*Weakness:* **asserted, never demonstrated.** We never show a naive AARA-style
instantiation failing. This is the single highest-value gap in the paper. See OP-2.

### A2. "You are publishing the fix to your own bug."

*Defence:* the rule is the natural first move, and the counterexample is crisp
and measured.

*Weakness:* no evidence anyone else compares bounds this way. Without that, it is
a personal error, not a community pitfall. See OP-5.

### A3. "The benchmark is synthetic and the security labels are yours."

*Defence:* the security suite is *paired* — every unsafe workflow has a safe twin
differing by one edit, so a checker cannot score well by rejecting everything.

*Weakness:* pairing rules out trivial over-rejection; it does not rule out
designer bias. See OP-10.

### A4. "Your guarantee is relative to a coupling, so it says very little."

*Defence:* coupling is the standard device for relational reasoning about
randomised systems, and without it the question is not well posed.

*Weakness:* we never characterise what the coupling *excludes* — e.g. a provider
whose sampling correlates with the secret. Make the adversary model explicit.

### A5. "Binary accept/reject is useless in practice. Real workflows must leak a little."

*Defence:* none currently.

*Weakness:* this is a genuine design limitation and a reviewer will land it. See
OP-4 — which is also the biggest novelty lever available.

### A6. "The proofs are sketches."

*Defence:* honestly stated as such.

*Weakness:* honesty is not a substitute. See OP-12.

### A7. "`max_tokens` is not portable across tokenizers, so your bound is wrong."

*Defence:* stated as a known limitation.

*Weakness:* it is an actual soundness gap in the implementation, not merely a
scope note. See OP-3.

---

## 9. Open problems

These are real. Where I know the shape of a solution I say so; where I do not, I
say that too. **OP-1 through OP-4 are the ones that change the venue.**

---

### OP-1 — Let a discharged relational obligation weaken the unary rule
**Novelty if solved: high. Difficulty: high. This is theory, not engineering.**

**Issue.** Chaining calls inside a secret-guarded arm is rejected:

```orchlang
if tokens(s) == 0 {
  let a1 = call p(x)  using m;
  let a2 = call p(a1) using m;    // E230: a1 is secret-tainted
}
```

See `testChainingInsideSecretArmIsRejectedConservatively` in `tests/tests.cpp`.

**Cause.** The unary program-counter rule taints everything produced inside a
secret-guarded branch, and a secret may not reach a prompt. The pc rule is
conservative because it does not know the *relational* obligation on the
enclosing branch was discharged.

**Why the rejection is stronger than necessary.** `a1`'s *content* depends only
on public data and the oracle. Its *existence* depends on the secret — but that
is exactly what the relational obligation already covers. Block scoping means
`a1` cannot escape the arm, and `emit` under a secret pc is separately banned.

**What success looks like.** A rule that admits the program above, still rejects
a variant where the *chain length* depends on the secret, and comes with a
soundness argument. Build the counterexample suite before the rule.

**Warning.** This is easy to get subtly wrong. Treat any version you cannot break
with an adversarial test as *unproven*, not correct.

---

### OP-2 — Demonstrate that the classical instantiation fails
**Novelty if solved: moderate. Difficulty: low-moderate. Highest value per unit of work.**

**Issue.** We assert AARA/RelCost cannot transfer. Attack A1 lands because we
never show it.

**Cause.** No experiment, no formal statement.

**What success looks like.** Either (a) a small theorem — no potential function
over program states can be both sound and non-trivial when a primitive's cost is
chosen externally — or (b) a worked construction attempting the instantiation and
showing precisely where it breaks. (a) is better. Both are far better than the
current assertion.

**Do this early.** It is cheap and it shapes the paper's framing.

---

### OP-3 — Tokenizer-portable bounds
**Novelty if solved: high. Difficulty: moderate. Also closes a real soundness gap.**

**Issue.** `inspectCall` assigns a call's result the producing model's output cap,
then reuses that count as a *later, possibly different* model's input bound. A
string of at most N tokens under tokenizer A may exceed N under tokenizer B.

**Cause.** Token counts are tokenizer-relative. The language has no tokenizer
identity and no conversion contract. Separately, `std::string::size()` measures
**bytes** while the option is documented in **characters** — fine for ASCII, wrong
otherwise.

**What success looks like.** Units on resource facts (tokens-under-A, UTF-8 bytes,
serialised-request bytes, tokens-under-B); derived conversion contracts;
**measured** worst-case expansion ratios between real tokenizers on multilingual
text, code, JSON, and adversarial Unicode; rejection of unsupported conversions.
Model special tokens and request-envelope overhead explicitly.

**You will need real data.** Fetch actual tokenizers and measure. Do not invent
ratios.

**Risk.** A reviewer may call this routine engineering. Defend it with a
compositional result or a surprising empirical finding, not with the
implementation alone.

---

### OP-4 — Quantitative leakage instead of binary rejection
**Novelty if solved: highest available. Difficulty: high.**

**Issue.** The analysis is all-or-nothing. A real workflow that must branch on a
secret is simply rejected, with no way to say "this leaks a little and that is
acceptable."

**Cause.** We only ask whether two signatures are equal.

**What success looks like.** Bound the leakage in bits — min-entropy leakage or
channel capacity — as a function of the signature difference and the declared
bounds, so an author can write a budget: *this branch leaks at most 1 bit per
invocation*. Compose those bounds across a workflow.

**Why this is the big lever.** It converts a binary checker into a quantitative
analysis, answers attack A5 directly, and is the kind of result that makes a
reviewer sit up. It also moves the work from "adaptation" toward "contribution".

**Before you build:** search quantitative information flow (Smith; Köpf & Basin)
and probabilistic relational Hoare logic. This may be partly solved already —
in which case cite it and build on it rather than reinventing it badly.

---

### OP-5 — Make the negative result a community finding
**Novelty if solved: moderate. Difficulty: low. Directly answers A2.**

**Issue.** "You are publishing the fix to your own bug."

**Cause.** No evidence anyone else reasons this way.

**What success looks like.** Survey real orchestration frameworks and published
budget-guard code (LangChain, LangGraph, Semantic Kernel, the systems catalogued
in arXiv:2606.04056) for logic that compares *bounds* where it should compare
*costs*. Document what you find.

**A null result is still worth reporting** — state honestly that no instance was
found and argue the pitfall from first principles instead. Do not manufacture
evidence.

---

### OP-6 — Incompleteness: different variables of equal length

**Issue.** Two arms reading different variables that always happen to have equal
length are rejected.

**Cause.** Size terms compare variable *identity*, not length.

**What success looks like.** A size refinement on types, or an explicit
equi-length assumption with a checkable contract and a recorded justification —
the way `declassify` already works.

---

### OP-7 — A lattice of observers

**Issue.** One observation model is hard-coded: the per-model billing vector.
A real adversary may see less (a monthly total) or more (request timing, ordering,
concurrency).

**Cause.** The observation is baked into the analysis rather than being a parameter.

**What success looks like.** Parameterise by an observer; show soundness for a
lattice of observers; exhibit a program safe under one and unsafe under another.
This also sharpens the adversary model that attack A4 targets.

---

### OP-8 — Verified declassification

**Issue.** `declassify` and `endorse` are trusted strings. The compiler records
them; it does not check them.

**Cause.** No checkable contract exists for a justification.

**What success looks like.** Even partial progress helps: a length-preserving
redaction primitive whose *cost behaviour* is checkable would make some
declassifications verified rather than asserted. Full verification is out of
reach and should stay out of scope — say so.

---

### OP-9 — Composition and modularity

**Issue.** The language is flat. No procedures, so signatures do not compose
across workflow boundaries.

**Cause.** Deliberate simplification for Phase 2.

**What success looks like.** A signature calculus with function abstraction and a
composition theorem: the signature of a composed workflow derived from its parts.
This is the most natural route to a *theoretical* contribution that is clearly ours.

---

### OP-10 — Real workflows and an independent benchmark

**Issue.** Synthetic corpus, author-written security labels. Attack A3.

**Cause.** No porting has been done.

**What success looks like.** Port real LangChain/LangGraph pipelines and a subset
of an existing prompt-injection corpus (AgentDojo). **Keep an exclusion log** of
features the language cannot express — that log is itself a finding and SCP
reviewers will value the honesty. Separate development fixtures from held-out
evaluation.

**SCP cares about this specifically.** Its scope emphasises industrial practice.

---

### OP-11 — A real certificate checker

**Issue.** The certificate is JSON emitted by the compiler. Calling it
"machine-checkable" would be an overclaim, and the paper currently avoids doing so.

**Cause.** No independent checker, no hash binding it to a source revision.

**What success looks like.** A small trusted checker that rejects forged, stale,
or incomplete certificates, plus a source-revision binding. Test it with
deliberately tampered certificates.

---

### OP-12 — Mechanise the proofs

**Issue.** Theorems are sketches.

**Cause.** Never attempted.

**What success looks like.** The cost algebra and signature equality are small
enough for Coq, Lean, or Agda. Even mechanising *only* the unary bound theorem
changes how the paper reads.

---

### OP-13 — Retry schedules and oracle-draw alignment

**Issue.** Under coupling, retry attempt counts match because both arms consume
the same oracle draws. This is currently guaranteed *by* requiring structural
equality — which may be stronger than necessary.

**Cause.** We never characterised the weakest condition under which two arms
consume oracle draws compatibly.

**What success looks like.** A precise condition, and a demonstration that it
admits programs structural equality rejects. **I am not certain this is
solvable** — it may be that structural equality is exactly right here. A negative
answer, argued, is a legitimate outcome.

---

## 10. The target: Science of Computer Programming

SCP publishes research on software systems development, use, and maintenance,
spanning methodological foundations, technical detail, and industrial practice.
It has **two relevant routes**:

- **The research track** — a full paper. This is the goal.
- **The Software Track (Original Software Publications)** — publishes useful
  software in programming languages and software development. The artifact
  already qualifies; this is a parallel, lower-risk submission.

**Before writing a line of the paper, study the venue.** Read 8–12 recent SCP
papers on static analysis, type systems, or DSLs. Extract:

- typical structure and length
- how much formalism is expected, and in what style
- how evaluations are presented
- how threats to validity are handled
- how tool papers differ from method papers there

Then match it. A paper that reads like it belongs in SCP has a materially better
chance than one that does not, independent of content.

**What SCP will want from this work specifically:** evidence of practical
relevance. That means OP-10 is not optional for the research track.

---

## 11. Deliverable: the paper

Write it to `docs/PAPER.md`, replacing the current draft.

Constraints:

- **Claim only what you can reproduce.** Every number traceable to
  `bench/evaluate.py`.
- **Keep the negative result.** It is a genuine asset and reviewers respect it.
  Strengthen it via OP-5 if you can.
- **Do not restore any withdrawn claim.** Specifically: combining flow and
  resource analysis is *not* new; token-count leakage is *not* a new defect
  class; no claim that only a unified compiler can see this class of defect; no
  "every taint checker accepts this".
- **State limitations in the body, not only at the end.** The current draft does
  this and it is one of its strengths.
- **Position against Ngo et al. and RelCost explicitly and early.** A reviewer
  who reaches §5 still wondering about A1 is already lost.

Also update, to stay consistent: `README.md`, `docs/LANGUAGE_SPEC.md`,
`docs/SUBMISSION_PLAN.md`, `docs/REVIEW_DEMO.md`, and the Phase 2 documents under
`submission/phase2/` (regenerate via `npm install && npm run report && npm run deck`).

---

## 12. Acceptance criteria

Falsifiable, so neither of us can bluff about whether this worked.

**Must hold at all times:**

1. `make check` — clean strict build, all assertions pass.
2. `python bench/evaluate.py` — exit 0.
3. Every counterexample in `audit/2026-09-17/` still a passing regression test.
4. No claim in any document unsupported by a reproducible command.

**Minimum to call the mission complete:**

5. **OP-2 done** — attack A1 has a demonstrated, not asserted, defence.
6. **At least two of OP-1, OP-3, OP-4, OP-9** substantially solved, with tests
   and an argued soundness story.
7. **OP-10 done to at least 15 real or independently-sourced workflows**, with a
   published exclusion log.
8. A new `docs/PAPER.md` in SCP form, with the related-work positioning above.
9. A revised novelty self-assessment in the style of §6, with reasoning — **and
   it must be defensible, not flattering.** If the honest number is still 5, say 5.

**Stretch:** OP-12 (mechanisation) on any one theorem. That single item probably
moves this out of SCP's range and into a stronger venue.

---

## 13. Traps

Things that will waste your time or quietly damage the work.

- **Do not compare our slack to the Token Budgets paper's 4–6× reservation
  figure.** Different corpora, different quantities. An earlier draft flirted
  with this; it is not a valid comparison.
- **Do not add features because they are easy.** The language is small on
  purpose: bounded repetition and declared input lengths are what make the
  analyses decidable. Adding a general loop destroys the cost bound.
- **Do not trust the harness silently passing.** It was rewritten *because* an
  earlier version skipped failures, counted any nonzero exit as a security
  success, and returned 0 despite recorded violations. If you extend it, extend
  its ability to fail.
- **Do not check only totals.** One audit finding was that each bound component
  must be checked separately. Component-wise checking is why that bug surfaced.
- **Beware benchmark guards that cannot be satisfied.** Another audit finding:
  generated guards were always true, so the expensive branch never ran and slack
  was measured through dead code. `bench/evaluate.py` now reports observed path
  counts — watch them.
- **`substitutedText` is the single definition** of what a value contributes to a
  prompt, shared by analyser and runtime. They disagreed once, and it was a real
  soundness bug. Keep exactly one definition.
- **Do not publish to two journals at once.** Ethics violation at every publisher.

---

## 14. Document index

| Path | Contents |
|---|---|
| `README.md` | Project introduction from zero knowledge |
| `docs/LANGUAGE_SPEC.md` | Grammar, labels, cost algebra, all diagnostics |
| `docs/PAPER.md` | Current write-up — replace this |
| `docs/RESEARCH_AUDIT_2026-09-17.md` | External audit; read in full |
| `docs/SUBMISSION_PLAN.md` | Venue analysis, patent reasoning, sequencing |
| `docs/REVIEW_DEMO.md` | Verified demonstration sequence |
| `docs/REVIEW2_PROGRESS_REPORT.md` | Historical, Phase 1 |
| `audit/2026-09-17/` | Counterexamples, reproduction scripts, auditor's harness |
| `bench/generate.py` | Corpus generator |
| `bench/evaluate.py` | Evaluation harness (E1–E6) |
| `bench/results/` | `evaluation.txt` plus per-experiment JSON |
| `examples/` | 34 programs: valid, invalid, boundary |
| `review_evidence/` | Captured compiler output |
| `submission/phase2/` | Report, deck, and their generators |
| `THIRD_PARTY_NOTICES.md` | Attribution |

---

## 15. A closing note

The most valuable thing in this repository is not the compiler. It is
`docs/RESEARCH_AUDIT_2026-09-17.md` — a record of a central claim being falsified
and withdrawn, with the counterexamples preserved as tests.

Hold yourself to that standard. If you find that billing signatures are also
unsound, or that OP-1 cannot be made to work, or that my 4.5/10 is generous —
**write that down, with the counterexample, and change the project accordingly.**
A paper that survives its own audit is worth more than one that was never
audited, and this project has already demonstrated that once.

You have full permission to work autonomously. Good luck.
