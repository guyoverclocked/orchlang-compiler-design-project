# Beyond Equal Caps: Relational Token-Cost Contracts for LLM Workflows

**Nambi Rajan M** (24BAI0072)
Vellore Institute of Technology

---

## Abstract

A workflow that calls a language model can leak a secret through its bill. If a
secret decides which branch runs, and the branches consume different numbers of
tokens, then whoever sees the invoice learns the secret — even though no secret
value ever reaches a prompt, an output, or a tool.

Relational cost analysis and resource-aware noninterference already address this
class of problem for conventional programs, where the cost of each operation is
a known function of its input. LLM workflows break that assumption: the number
of output tokens a call consumes is chosen by the provider, not by the program,
so no numeric potential can be assigned to a call site and the usual
potential-comparison machinery does not apply.

We report two things. First, a *negative result with a counterexample*: the
natural rule for this setting — accept a secret-guarded branch when both arms
have equal certified upper bounds — is unsound, and we exhibit a workflow it
accepts whose bill nevertheless moves with the secret in 225 of 425 paired
executions. Second, a rule that works: abstract each arm to a **billing
signature** recording, in order, which model is called and a symbolic term for
its input size, where the terms range only over quantities that provably agree
across the two compared executions. Under a coupling of the model oracle,
signature equality implies that the per-model billing vector is independent of
the secret.

We implement this in OrchLang, a small statically typed DSL whose compiler also
derives a conventional worst-case token bound and a two-axis information-flow
property. On a generated benchmark, the certified bound is never exceeded in
4,600 executions — checked componentwise, not only in total — while a flat
per-call sum is exceeded on 13.8% of them and a control-flow-aware variant on
14.0%. On a paired relational benchmark, seven accepted workflows show identical
bills across 2,975 comparisons that vary only the secret, and all seven rejected
workflows have a concrete leaking witness.

We do not claim that combining information flow with resource analysis is new,
that leakage through token counts is a new defect class, or that the analysis is
complete. We state precisely what is new: the treatment of opaque stochastic
calls, for which structural comparison replaces numeric comparison.

---

## 1. Introduction

Consider a workflow that answers support tickets and, when the customer is on
the enterprise plan, escalates by calling a larger model:

```orchlang
if is_enterprise {                            // a secret
  let reply = call escalate(ticket) using large;   // 900 output tokens
} else {
  let reply = call acknowledge(ticket) using small; // 150 output tokens
}
```

No secret value reaches a prompt. No secret is returned. No tool is invoked.
An information-flow type system with a program-counter label will accept this,
because nothing observable at a sink depends on the secret. But the monthly
invoice does: a month with many enterprise customers costs visibly more than one
without, and the invoice is itemised per model.

### 1.1 Why the classical answer does not transfer

This is a resource side channel, and the literature on resource side channels is
mature. Ngo, Dehesa-Azuara, Fredrikson and Hoffmann [1] formalise
*resource-aware noninterference* by combining information-flow typing with
automatic amortized resource analysis, and can certify programs that violate a
constant-resource requirement as long as the violation leaks nothing. Çiçek,
Barthe, Gaboardi, Garg and Hoffmann [2] give RelCost, a relational refinement
type system that bounds the *difference* in cost between two executions,
explicitly motivated by side-channel reasoning.

Both rest on an assumption that LLM workflows violate. In AARA and in RelCost,
the cost of an operation is a known function of its input: a list traversal
costs its length, an arithmetic operation costs one. A potential can therefore be
attached to a value and discharged as the program runs.

An LLM call has no such function. The workflow asks for at most `max_tokens`
output; how many arrive is decided by the provider's sampling. Two executions of
the *same* program on the *same* inputs already differ in cost. So:

- a numeric potential cannot be assigned to a call site, because the cost is not
  determined by the program state; and
- "constant resource" is the wrong property, because no LLM workflow has
  constant resource consumption in the classical sense.

The question has to be reformulated. Not "is the cost constant?" but "**does the
secret change the bill, holding the model's behaviour fixed?**"

### 1.2 What this paper contributes

**A negative result.** The natural rule — compare the two arms' certified upper
bounds and accept when they are equal — is unsound. §3 gives a counterexample
and §7 measures it: the rule accepts a workflow whose bill differs in 225 of 425
paired executions.

This is not a strawman. It is the rule an earlier version of this compiler
implemented and claimed a theorem for, and it is what a reader who knows only
about worst-case bounds would reach for. Equal maxima say nothing about equal
costs when the maxima are not attained.

**A rule that works.** Because costs cannot be compared numerically, compare
structure instead. Each branch arm is abstracted to a **billing signature**: an
ordered record of which model is called and a symbolic term for its input size,
where the terms are built only from constants, variables bound outside the
branch, and the results of earlier calls in the same signature. Under a coupling
of the model oracle, equal signatures imply equal billing vectors (§4, §6).

**An implementation and a reproducible evaluation** (§5, §7), including a paired
experiment that enumerates every secret value under a fixed seed and fixed public
inputs, and a soundness check that is performed componentwise rather than only on
totals.

**What we do not claim.** Combining flow and resource analysis is not new [1].
Relational cost reasoning is not new [2]. Leakage through LLM token counts is not
new: *Time Will Tell* [3] recovers input properties from output token counts and
timing on production models, and token-length side channels are established at
USENIX Security [4]. Our setting — a compiler deciding, before deployment,
whether a multi-step workflow's *bill* is secret-independent — is adjacent to
those, not a discovery of the defect class.

---

## 2. The language, in one page

OrchLang describes a workflow as declarations and statements inside a token
budget. Three commitments exist specifically to make the analyses decidable.

**Repetition is bounded syntactically.** `retry n { … }` carries a literal `n`.
There is no general loop and no recursion.

**Lengths the compiler cannot see must be declared.** An input feeding a prompt
must carry `max_tokens`, or the compiler reports `E261` and derives no bound at
all rather than guessing one.

**Leaving the lattice requires saying why.** `declassify` and `endorse` are the
only ways to relax a label, and both demand a written justification recorded in
the certificate.

Information flow uses the product lattice
`(Public ≤ Secret) × (Trusted ≤ Untrusted)`. A model's answer is labelled with
the join of everything reaching its prompt, so text from an untrusted document
stays untrusted through any number of calls. A program-counter label catches
implicit flows. `emit` is the only outward effect. Full rules are in
`docs/LANGUAGE_SPEC.md`; this paper concerns the resource dimension.

---

## 3. The negative result

Here is a workflow the equal-bounds rule accepts:

```orchlang
workflow EqualBounds budget 1000 {
  secret s: text max_tokens 1;
  input  x: text max_tokens 100;
  input  y: text max_tokens 100;
  model  m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";

  if tokens(s) == 0 {
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(y) using m;
  }
  output "done";
}
```

Both arms call the same model with one argument whose declared cap is 100. Both
arms therefore certify at exactly 111 tokens. The rule sees equality and accepts.

But `x` and `y` are different values. Their *actual* lengths need not agree, and
both are within their declared caps. Fix `|x| = 14` and `|y| = 52`, fix the
oracle so both calls return zero output tokens, and the two executions consume
15 and 53 tokens. The secret chose which.

The error is elementary once stated: an upper bound constrains the maximum, and
two quantities with the same maximum are not thereby equal. It survived because
the bound was the only number available, so it was the number that got compared.

This is the shape of the problem. Any rule that compares *numbers derived from
caps* will make this mistake, because the caps are not what gets billed.

---

## 4. Billing signatures

### 4.1 The observation

Define the observation of an execution as the **billing vector**: for each
model `m`, the total input tokens, output tokens, and call count charged to `m`.

```
Obs(e)  =  { m ↦ (in_m, out_m, calls_m) }
```

This is what an itemised invoice shows. A scalar total is the wrong observation:
two runs can agree on total tokens while charging different models at different
prices, and the prices are public.

### 4.2 The coupling

A **model oracle** ω determines, for each model and each call index, how many
output tokens come back (bounded by that model's `max_tokens`) and whether a
retry attempt succeeded. Two executions are compared under the *same* ω.

This is the standard device for relational reasoning about randomised systems,
and it is the only way to ask a meaningful question here. Without it, the bill
varies run to run for reasons that have nothing to do with the secret. With it,
the question is exactly: *given that the model behaved the same way, did the
secret change what we paid?*

### 4.3 The abstraction

A **size term** is built only from quantities that agree across the two compared
executions:

```
Term ::= const(n)                  literals and template text
       | outer(x)                  a variable bound outside the branch
       | result(k)                 the k-th prior call in this signature
```

`outer(x)` agrees because public inputs are equal by hypothesis. `result(k)`
agrees because the k-th call to a model returns the same answer under the shared
oracle. Positional reference matters: the two arms bind different names to
corresponding calls, so names cannot be compared, but positions can.

A **signature** is a sequence of nodes:

```
Node ::= Call(model, Term)
       | Retry(n, Signature)
       | Branch(publicGuard, Signature, Signature)
```

The rules:

- A `let` bound to a call appends `Call(m, τ(template) + Σ terms)`.
- `retry n { B }` appends `Retry(n, Sig(B))`.
- A branch on a **public** guard appends `Branch(g, Sig(A), Sig(B))` — the arms
  need not match, because both executions see the same public data and take the
  same arm.
- A branch on a **secret** guard is checked recursively; if its arms agree, the
  common signature is spliced in, which is what makes the analysis compositional.
- An argument whose label is `Secret` makes the signature **undefined**, and an
  undefined signature is rejected.

The rule: **at a secret-guarded branch, both arms' signatures must be defined and
equal.**

On the §3 counterexample the arms yield `m(in = 1 + |x|)` and `m(in = 1 + |y|)`.
These differ, and the compiler says so in those terms.

### 4.4 Incompleteness, stated plainly

The rule rejects safe programs. Two arms that read different variables which
happen always to have equal length are rejected, because the compiler has no
reason to believe they do. Making that judgement would need length refinements
on types, which the language does not have.

A second incompleteness is a consequence of the program-counter rule rather than
of this analysis: chaining calls inside a secret-guarded arm is rejected, because
the intermediate result inherits the secret pc and a secret may not reach a
prompt. That rejection is sound but stronger than necessary — the intermediate
value's *content* depends only on public data, and its *existence* is exactly
what the relational obligation already covers. Letting the relational judgement
discharge part of the unary one is the most promising next step (§9).

---

## 5. Implementation

`orchc` is hand-written C++17, no parser generator and no third-party
dependencies: a location-tracking lexer, a recursive-descent parser with
statement-level recovery, a scoped symbol table, the flow-typing pass, the cost
pass, the relational pass, a region-annotated IR, a certificate emitter, and a
deterministic offline mock runtime. It builds warning-free under
`-Wall -Wextra -pedantic` and carries 95 regression tests.

The flow pass records, for each call site, the model, the template size, and for
each argument whether it is a literal (with its size), a variable (with its
name), or secret. The relational pass reads those records, so it is a pure
structural walk. The same separation lets the cost pass avoid symbol lookups.

### 5.1 The unary bound, and a correction

Alongside the relational property the compiler derives a conventional worst-case
bound by structural induction: a branch costs its more expensive arm, a retry
multiplies its body, calls add. It is reported in two components — output tokens,
which providers cap themselves, and input tokens, which depend on a declared
characters-per-token assumption recorded in the certificate.

An audit found that the branch rule took the larger arm's *pair* whole. That
bounds the total but not each component: a certificate reporting one output token
admitted an execution producing twenty, because the other arm dominated that
component while losing on the total. The compiler now maximises each component
separately and tracks the total alongside, with the invariant
`total ≤ guaranteed + estimated`. The gap between them is the price of reporting
a faithful split instead of a single number, and the certificate shows both.

### 5.2 The runtime exists to falsify the claim

`orchc run` executes a workflow against a seeded generator that respects each
model's declared cap and each input's declared bound, and reports the billing
vector. `--pin name=value` fixes an input or secret's length, which is what makes
the relational claim testable: run twice under one seed, change only the secret,
compare bills.

This is a differential check of the implementation against the language's
semantics. It is not evidence that a provider honours its own caps — that
assumption is stated, not tested.

---

## 6. What is proved, and what is not

Let `⟨W, σ⟩ ⇓_ω ⟨κ, β, ε⟩` denote execution of `W` in store `σ` under oracle `ω`,
yielding total tokens `κ`, billing vector `β`, and effect sequence `ε`. Write
`σ = σ_P ⊎ σ_S` for the public and secret parts.

**Assumptions.** (A1) a call to model `m` returns at most `maxTokens(m)` output
tokens; (A2) inputs honour their declared bounds and `τ` bounds the tokenizer;
(A3) `ω` is shared between the two compared executions.

**Theorem 1 (Unary bound).** If `⊢ W : ⟨g, e, t⟩` then under (A1) and (A2), for
any execution, output tokens `≤ g`, input tokens `≤ e`, and `κ ≤ t`.

*Proof sketch.* Induction over the derivation. Sequencing adds; a branch executes
one arm and each component's maximum dominates it; `retry n` runs its body at most
`n` times. (A1) bounds the output component of a call and (A2) the input
component. Saturation preserves the inequality for successfully certified
programs; saturated bounds are rejected by `E266` rather than trusted. ∎

**Theorem 2 (Billing noninterference).** Let `W` be well-typed, contain no
declassification, and pass the relational check. Then for any `σ_P`, any
`σ_S¹, σ_S²`, and any `ω`, if `⟨W, σ_P ⊎ σ_S^i⟩ ⇓_ω ⟨κ_i, β_i, ε_i⟩` then
`β_1 = β_2` (and hence `κ_1 = κ_2`).

*Proof sketch.* Induction on the signature. A `Call` node bills
`(term, oracle(m, k))`; the term's constants are literal, its `outer(x)` are
equal because `σ_P` is shared, and its `result(j)` are equal because `ω` is
shared and the two executions have made the same `j` prior calls by the induction
hypothesis. A `Branch` on a public guard takes the same arm in both, since the
guard reads only public data. A `Retry` node runs its body under the same oracle
outcomes, so the same number of attempts occur. At a secret-guarded branch the
two arms have equal signatures by the check, so whichever arm each execution
takes, the sequence of billing events is the same. ∎

**Theorem 3 (Effect noninterference).** Under the same hypotheses the effect
sequence and the returned output agree, by the program-counter discipline: `emit`
requires `Public/Trusted` arguments and a `Public/Trusted` pc, and `output`
requires `Public`.

### What is not claimed

- **These are pen-and-paper proofs over a reference semantics.** They are not
  mechanized, and the C++ implementation is not verified against them. The
  experiments in §7 are differential evidence, not proof.
- **Relative to the coupling.** Theorem 2 says the secret does not change the
  bill *given the model behaves the same way*. It says nothing about a provider
  whose sampling itself correlates with the secret.
- **Relative to declassification.** A declassified value is treated as public by
  assumption. The compiler records every such site; it does not verify one.
- **Timing is not modelled.** Wall-clock latency is a separate channel, and the
  one *Time Will Tell* [3] actually exploits.
- **Sound, not complete.** §4.4 lists the programs rejected unnecessarily.
- **The tokenizer assumption is real.** A token bound under one model's tokenizer
  is not a bound under another's; §9 treats this as future work rather than
  pretending `max_tokens` is portable.

---

## 7. Evaluation

Benchmarks are generated by `bench/generate.py` and results reproduced by
`python bench/evaluate.py`, which exits nonzero if any assertion fails.

The harness was rewritten after an audit found the previous one could hide
failures: it skipped workflows that failed to certify, counted *any* nonzero exit
as a security success — so a parse error scored as a caught leak — and returned
success even when violations were recorded. It now requires every workflow to
certify, requires every rejection to cite the diagnostic family it was supposed
to raise, and fails loudly.

### E1: Is the unary bound exceeded? — no, componentwise

23 cost workflows × 200 seeds = 4,600 executions. **Zero violations of the
total, zero of the output component, and zero of the input component.** The
componentwise check matters: checking only totals is what let the split bug
through.

### E2: Do simpler rules hold? — no

| Rule | Violated |
|---|---|
| Flat sum over syntactic call sites | **636 / 4,600 (13.8%)** |
| Control-flow-aware (larger arm, retry charged once) | **644 / 4,600 (14.0%)** |

The control-flow-aware rule is *slightly worse*, which is the informative part:
taking the larger branch arm tightens the bound, and tightening an unsound bound
makes it fail more often. Branch-awareness alone does not rescue the rule.
Retries do the damage — every violated workflow contains one.

### E3: How tight, and is the benchmark honest?

Median slack over peak observed consumption is **1.11×** (range 1.02–1.84×).

This number is lower than the 1.23× an earlier draft reported, and the reason is
a correction rather than an improvement. The generated branch guards were
`tokens(head) <= 150` where `head` came from a model capped at 150 — always true,
so the expensive arm never ran and the slack was being measured through dead
code. Guards now sit at half the cap, both arms are reachable, and the harness
reports the number of distinct execution paths observed per workflow alongside
the slack. Zero branch workflows now have a dead arm.

### E4: Does an accepted workflow really have a secret-independent bill?

For each accepted relational workflow, the harness fixes the seed and the public
inputs, enumerates every combination of secret values (a boolean and a
nine-valued length), and compares billing vectors.

**7 accepted workflows, 2,975 paired comparisons, 0 differing bills.**

### E5: Are the rejections real, or is the analysis just strict?

For each rejected workflow the harness searches for a witness: two secret values
whose bills differ.

**7 of 7 rejected workflows have a concrete witness**, none rejected without one.
`DifferentArgument` — the §3 counterexample — differs in 225 of 425 comparisons.

| Workflow | Comparisons | Bills differ |
|---|---|---|
| DifferentArgument | 425 | 225 |
| DifferentModel | 425 | 225 |
| ExtraCall | 425 | 225 |
| CallInOneArmOnly | 425 | 225 |
| DifferentLiteralLength | 425 | 225 |
| DifferentInnerPublicGuard | 425 | 126 |
| DifferentRetryBound | 425 | 81 |

### E6: Flow policy conformance

The paired security suite: **13 of 13 unsafe rejected for a flow reason, 13 of 13
safe accepted.**

We describe this as *policy conformance*, not injection robustness. Each safe
variant differs from its unsafe partner by a trusted `endorse` or `declassify`,
which the compiler records rather than verifies. The suite shows the compiler
enforces the policy it is given; it does not show that an application resists
adversarial text.

### E7: Analysis cost

36 workflows certified in 0.44 s, about 12 ms each **including process startup**.
This is not an isolated measurement of analyser time and should not be read as
one. The analyses are linear in program size and no solver is involved.

---

## 8. Related work

| Work | Setting | Costs known? | Relation to this paper |
|---|---|---|---|
| Ngo et al., S&P'17 [1] | Resource-aware noninterference via AARA | yes, per operation | The foundation. We cannot use its potential method because LLM call costs are not program-determined. |
| RelCost, POPL'17 [2] | Relational cost bounds, side-channel motivated | yes | Bounds cost *differences* numerically; we compare structure because numbers are unavailable. |
| Time Will Tell [3] | Output-token-count and timing leakage, single call | — | Establishes the attack. We address a compiler-side guarantee at workflow-billing granularity. |
| Token-length side channels [4] | Encrypted-traffic token-length attacks | — | Same channel family, network observer. |
| CaMeL [5] | Dual-LLM planner, custom interpreter, capabilities at tool calls | — | Runtime data/control separation, not string scanning. No resource reasoning. |
| FIDES [6] | Planner with dynamic confidentiality/integrity labels and controlled release | — | Closest flow comparator; runtime; evaluated on AgentDojo. No resource reasoning. |
| AgentFlow [7] | Policy language, runtime monitor **plus a bounded SMT verifier** | — | Partly static; policy-level, not a source type system. No resource reasoning. |
| NeuroTaint [8] | **Offline auditing of execution traces** | — | Post-hoc rather than pre-execution; a different point in the lifecycle from either runtime monitoring or source analysis. |
| Agentproof [9] | Static verification of extracted workflow graphs | — | Static, but checks topology and temporal policies, not types or resources. |
| Token Budgets [10] | Affine-typed Rust budget with runtime caps | — | Compile-time *bookkeeping integrity*; the cap itself is enforced at run time. Its 4–6× reservation slack is not comparable to our bound/observed-peak ratio on a different corpus. |
| AARA [11, 12] | Amortized resource typing | yes | Not applied to LLM tokens; the potential method needs known costs. |

An earlier draft of this paper described NeuroTaint as a runtime mechanism and
characterised the injection-defence literature as string scanning. Both are
wrong, and the corrected descriptions are above. We also withdraw the claim that
a defect of this kind is visible "only" to a unified compiler: separate analyses
can share facts, and the implementation here does exactly that across two
modules.

We did not find an existing system that decides, from source, whether a
multi-step LLM workflow's billing vector is secret-independent. That is a gap,
not a guarantee of significance: combining known ideas inside a narrow new
language can be useful without being a major theoretical advance, and we position
this as an application and tool contribution built on [1] and [2].

---

## 9. Limitations and future work

**Token bounds are not portable across tokenizers.** The compiler reuses one
model's output cap as a later model's input bound. A string of at most *N* tokens
under model A may exceed *N* under model B. The language has no tokenizer
identity and no conversion contract. This is the most concrete correctness gap
remaining, and closing it — units on resource facts, conversion contracts,
byte-level fallbacks, explicit request-envelope overhead — is a well-defined next
project.

**`std::string::size()` measures bytes** while the option is documented in
characters. For ASCII these coincide; for anything else they do not.

**The proofs are not mechanized.** The cost algebra and signature equality are
small enough that a Coq or Lean development is tractable and would change how the
work reads.

**The relational rule could be less strict.** Letting a discharged relational
obligation relax the program-counter rule inside the branch would admit chained
calls in secret arms (§4.4) — the single most useful expressiveness gain.

**The corpus is synthetic and the security labels are ours.** An independent
benchmark, ported from an existing injection corpus, would address the most
serious threat to the evaluation.

**The certificate is a report, not a proof.** It is JSON emitted by the compiler.
There is no independent checker, no binding hash tying it to a source revision,
and no runtime that consumes it. Calling it machine-checkable would require
writing the small trusted checker that rejects forged or stale evidence.

---

## 10. Conclusion

Asking "what is the maximum this workflow can cost?" is not the same as asking
"can a secret change what it costs?", and the first question's answer does not
settle the second. Comparing upper bounds looks like it should work and does not,
for a reason that is obvious once written down and was not obvious in code.

For LLM workflows the usual repair is unavailable, because a call's cost is the
provider's choice rather than the program's. Comparing the *structure* of the
billing — which model, and an input size expressed only in quantities that
provably agree — recovers a usable rule, and it is decidable by syntactic
comparison.

The compiler that implements it derives a conventional bound that held in 4,600
executions where two simpler rules did not, and a relational property that held
across 2,975 paired comparisons while every rejection it made had a concrete
leaking witness. The remaining gaps — tokenizer portability, mechanization, an
independent corpus, a real certificate checker — are named rather than hidden.

---

## References

[1] V. C. Ngo, M. Dehesa-Azuara, M. Fredrikson, J. Hoffmann. *Verifying and
Synthesizing Constant-Resource Implementations with Types.* IEEE S&P 2017.
arXiv:1801.01896.

[2] E. Çiçek, G. Barthe, M. Gaboardi, D. Garg, J. Hoffmann. *Relational Cost
Analysis.* POPL 2017.

[3] *Time Will Tell: Timing Side Channels via Output Token Count in Large
Language Models.* arXiv:2412.15431.

[4] R. Weiss et al. *What Was Your Prompt? A Remote Keylogging Attack on AI
Assistants.* USENIX Security 2024.

[5] E. Debenedetti et al. *Defeating Prompt Injections by Design (CaMeL).*
arXiv:2503.18813.

[6] *FIDES: Information-Flow Control for AI Agents.* arXiv:2505.23643.

[7] *AgentFlow: A Flow-Centric Policy Language and Framework for Securing LLM
Agent Systems.* arXiv:2608.22868.

[8] *Ghost in the Agent: Redefining Information Flow Tracking for LLM Agents.*
arXiv:2604.23374.

[9] *Agentproof: Static Verification of Agent Workflow Graphs.* arXiv:2603.20356.

[10] *Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun
Incidents, with an Affine-Typed Rust Mitigation as a Case Study.*
arXiv:2606.04056.

[11] J. Hoffmann, K. Aehlig, M. Hofmann. *Multivariate Amortized Resource
Analysis.* ACM TOPLAS 34(3), 2012.

[12] D. M. Kahn, J. Hoffmann. *Exponential Automatic Amortized Resource
Analysis.* FoSSaCS 2020.

[13] D. Volpano, G. Smith, C. Irvine. *A Sound Type System for Secure Flow
Analysis.* Journal of Computer Security 4(2–3), 1996.

[14] A. Sabelfeld, A. C. Myers. *Language-Based Information-Flow Security.*
IEEE JSAC 21(1), 2003.

[15] A. Sabelfeld, D. Sands. *Dimensions and Principles of Declassification.*
CSFW 2005.

---

## Artifact

`https://github.com/guyoverclocked/orchlang-compiler-design-project`

```sh
make check                  # build, 95 tests, example corpus
python bench/generate.py    # regenerate the benchmark
python bench/evaluate.py    # reproduce every number in §7; exits nonzero on failure
```

The audit that produced the negative result in §3, with its reproduction
scripts, is preserved under `audit/2026-09-17/`.
