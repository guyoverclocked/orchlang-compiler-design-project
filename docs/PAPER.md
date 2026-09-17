# OrchLang: Certifying Token Cost and Information Flow for LLM Workflows Before Execution

**Nambi Rajan M** (24BAI0072)
Vellore Institute of Technology

---

## Abstract

LLM workflows fail expensively in two recurring ways: they spend more than their
operator intended, and they let data move where it should not — a secret into a
prompt, or text from a retrieved document into a privileged tool call. Today
these are treated as separate problems by separate machinery, and almost all of
that machinery runs at execution time: taint-tracking interpreters, reference
monitors, and budget wrappers that discover a violation only once tokens have
been spent and effects have fired.

We argue that both properties are consequences of a workflow's *structure*, and
that a language designed for the purpose can decide both before anything runs.
We present OrchLang, a small statically typed DSL for LLM workflows whose
compiler derives, from source alone, (i) an upper bound on the tokens any
execution can consume and (ii) a two-axis information-flow property covering
secret confidentiality and untrusted-input integrity. Both judgements are made
over the same program by the same type system, and both are written into a
machine-checkable JSON certificate.

Deriving them together is not merely an engineering convenience. It exposes a
defect neither analysis can see alone: a branch whose guard is secret and whose
arms cost different amounts leaks the guard through the token bill, with no
value crossing any boundary. We report this as a first-class error.

On a generated benchmark of 23 cost workflows executed under 200 seeds each
(4,600 executions), the certified bound was never exceeded, while the flat
"sum every call's `max_tokens`" rule — the rule the first version of this
compiler used, and the obvious thing to reach for — was exceeded on 13.5% of
executions and is unsound on 8 of 23 workflows, every one of them containing a
bounded retry. The bound's median slack over peak observed consumption is
1.23×. On a paired security suite of 26 workflows in which each unsafe workflow
has a safe counterpart differing by a single edit, the analysis rejects 13 of 13
unsafe and accepts 13 of 13 safe workflows. Analysis takes roughly 6 ms per
workflow.

---

## 1. Introduction

A workflow that calls a language model is a program, and like any program it can
be wrong before it is run. Two kinds of wrongness dominate incident reports.
The first is cost: a retry loop that fans out, a branch that selects an
expensive model, an input that turns out to be a 200-page PDF. The second is
flow: an API key interpolated into a prompt, or — the case that has attracted
the most attention — text retrieved from an untrusted source being treated as an
instruction and used to drive a tool.

Both are, in the end, questions about program structure. *How many model calls
can this program make, and how large can each be?* *Which values can reach which
positions?* These are the questions static analysis has answered for other
resources and other flows for forty years. Yet the tools built for LLM workflows
almost uniformly answer them at run time.

Consider the three families of existing work.

**Workflow DSLs.** LMQL [1], SGLang [2], DSPy [3], APPL [4], and PDL [5] make
LLM programs easier to write and often cheaper to execute. None of them
certifies a cost bound or a flow property before execution. LMQL reports 26–85%
*runtime* cost savings from constraint-guided decoding — a different claim from
a bound.

**Injection and leakage defences.** CaMeL [6] executes a restricted Python
subset in a custom interpreter that maintains a dynamic data-flow graph and
checks capabilities at each tool call. The f-secure architecture [7] filters
untrusted input through a runtime security monitor. AgentFlow [8] pairs a
runtime reference monitor with a bounded SMT check over policy fragments.
NeuroTaint [9] and GIF [10] track taint during execution. All of them are
runtime mechanisms, and all pay runtime cost for it.

**Budget enforcement.** The most directly comparable work catalogues 63
production budget-overrun incidents and mitigates them with a Rust crate that
makes a budget an affine value, so the borrow checker prevents double-spending
and post-delegation use [11]. This genuinely moves a class of error to compile
time, but the mechanism is ownership of a *runtime* budget object in a host
language, not inference of a bound from workflow structure; the authors note
that binary-level soundness remains open. Elsewhere, budget algebras with
conservation theorems govern multi-agent routing at run time [12].

Static verification of agent workflows exists — Agentproof [13] extracts graphs
from LangGraph, CrewAI, AutoGen and ADK and checks structural properties and
temporal safety policies compiled to automata — but it checks topology, not
types, resources, or information flow.

Meanwhile the classical apparatus for exactly these two problems is mature and
unused here. Information-flow type systems date to Denning [14] and were given
soundness by Volpano *et al.* [15], scaled to a real language by Jif [16], and
surveyed by Sabelfeld and Myers [17]. Automatic Amortized Resource Analysis
(AARA) [18, 19] infers resource bounds as a typing problem. We found no work
applying resource typing to LLM token consumption.

**This paper.** We close that gap with a language rather than a wrapper. The
central design claim is that a *small, purpose-built* source language makes both
properties decidable, where a general-purpose host language does not: bounded
repetition is syntactic, lengths the compiler cannot see must be declared, and
the only outward effect is an explicit `emit`.

Our contributions:

1. **OrchLang**, a statically typed DSL for LLM workflows whose grammar is
   shaped by three commitments that make static certification possible rather
   than merely convenient (§3).

2. **A two-axis information-flow type system** over
   `(Public ≤ Secret) × (Trusted ≤ Untrusted)` with a program-counter label for
   implicit flows, an *injection-propagation rule* that taints model output
   derived from untrusted input transitively, and declassification and
   endorsement that require written justifications recorded in the certificate
   (§4).

3. **A structural token-cost analysis** that is inductive over control flow —
   a branch costs its more expensive arm, a retry multiplies its body — and that
   deliberately separates a *guaranteed* component (provider-enforced output
   caps, needing no tokenization assumption) from an *estimated* component
   (input tokens, sound relative to an assumption the certificate records) (§5).

4. **The secret-dependent cost channel**, a defect visible only when both
   judgements are made over the same program, reported as a first-class error
   (§6).

5. **An evaluation** with a generated benchmark, an offline mock runtime that
   makes the bound falsifiable, and a paired security suite that measures false
   positives directly (§10).

---

## 2. A motivating example

```orchlang
workflow ResearchDigest budget 2400 {
  input query:    text max_tokens 100;
  input web_page: text untrusted max_tokens 600;
  secret API_KEY: text max_tokens 16;

  model reader = mock("offline-reader") max_tokens 500;
  tool  publish(body: text);

  prompt digest(page: text) -> text = "Summarise the retrieved page: {page}";

  retry 3 {
    let digest_text: text = call digest(web_page) using reader;
    emit publish(digest_text);
  }

  output query;
}
```

This is nine lines of workflow and it is wrong in two independent ways. The
compiler reports the first immediately:

```text
13:18: error [E233] untrusted value reaches tool 'publish'; model output derived
       from untrusted input must be endorsed before it can drive an external
       effect
```

`web_page` is untrusted, so `digest_text` is untrusted by the propagation rule
of §4.2, so handing it to a tool gives an attacker who controls the retrieved
page influence over a privileged effect. A runtime taint system catches this
when it happens; we reject it before deployment. To proceed, the author must
write down why it is safe:

```orchlang
endorse(digest_text) as vetted: text because "schema validated offline";
emit publish(vetted);
```

which is then recorded verbatim in the certificate. With that edit the program
type checks, and the second problem surfaces:

```text
1:1: error [E260] certified token bound 3327 (guaranteed 1500 + estimated 1827)
     exceeds workflow budget 2400
```

The retry is the reason. A single attempt costs 500 output tokens plus 609 input
tokens; the block permits three, so the bound is `3 × 1109 = 3327`, over a budget
of 2400. A flat sum over syntactic call sites sees one call and reports 1109 —
comfortably inside budget, and wrong. §10 measures how often that gap is
realised in practice.

Note also what the two halves of the bound say. 1500 of it is
provider-enforced output and holds unconditionally; 1827 is input tokens and
holds relative to the recorded four-characters-per-token assumption. The author
can see at a glance that most of the overrun is on the assumption-bearing side,
and that tightening the input bound on `web_page` — not switching models — is
the fix.

**What no existing tool would report at all.** Suppose the author instead writes

```orchlang
if ALERT {                                   // a secret boolean
  let a: text = call step(src) using large;  // 900 output tokens
} else {
  let b: text = call step(src) using small;  // 150 output tokens
}
```

No value crosses any boundary. No tool is invoked. Every taint checker we know
of accepts this. The monthly bill still reveals the secret. §6 is about this
case.

---

## 3. The language

OrchLang describes a workflow as a sequence of declarations and statements
inside a declared token budget. The full grammar is in
`docs/LANGUAGE_SPEC.md`; here we state only the three commitments that exist to
make the analysis possible.

**Repetition is bounded syntactically.** `retry n { … }` carries a literal `n`.
There is no general loop and no recursion. An unbounded loop makes the cost
bound infinite and the analysis worthless, so the language does not offer one.
This is a real restriction on expressiveness, and we accept it deliberately:
the overwhelmingly common repetition pattern in production LLM workflows is a
bounded retry, which is also the shape that most often causes overruns [11].

**Lengths the compiler cannot see must be declared.** An input's length is not
knowable from source. If an input reaches a prompt without a declared
`max_tokens`, the compiler reports `E261` and derives no bound at all. The
alternative — picking a default and calling the result a bound — would produce a
number that means nothing.

**Leaving the lattice requires saying why.** `declassify` and `endorse` are the
only ways to relax a label, and both demand a string justification that is
copied verbatim into the certificate. Real workflows need escape hatches;
requiring a justification means a reviewer can enumerate every one of them.

A fourth property matters for §4: `emit` is the only construct with an outward
effect. Confining effects to one syntactic form is what makes "which values can
reach the outside world" a question with a finite answer.

---

## 4. Information-flow typing

### 4.1 Labels

Every value carries a label from the product lattice

```
L  =  Confidentiality × Integrity  =  {Public ≤ Secret} × {Trusted ≤ Untrusted}
```

ordered componentwise, with `Public/Trusted` as bottom. The two axes are the
standard confidentiality and integrity duals [17]; what is specific here is what
each axis is *for*. Confidentiality keeps credentials out of prompts, outputs,
and effects. Integrity keeps text that an attacker may have authored from
becoming an instruction that fires an effect — which is precisely the structure
of indirect prompt injection.

### 4.2 The injection-propagation rule

The rule that does the work is the one for a model call:

```
Γ; pc ⊢ aᵢ : Tᵢ, ℓᵢ        for i ∈ 1..n
──────────────────────────────────────────────────────────
Γ; pc ⊢ call p(a₁..aₙ) using m  :  ret(p),  pc ⊔ ℓ₁ ⊔ … ⊔ ℓₙ
```

A model's answer is labelled with the join of everything that reached its
prompt. A model given only trusted input yields a trusted answer; a model given
anything untrusted yields an untrusted answer, and so does every model
downstream. Injection therefore cannot be laundered by chaining calls: in our
benchmark, `InjectionTransitive` passes untrusted text through two model calls
before reaching a tool and is still rejected.

This mirrors the propagation CaMeL performs dynamically [6], obtained instead as
a typing rule with no runtime component.

### 4.3 The program-counter label and implicit flows

Inside `if c { A } else { B }`, the label of `c` joins `pc` in both arms. Values
produced in an arm inherit `pc`, and effects performed in an arm are checked
against it. A tool invoked under a secret `pc` is rejected (`E234`) because the
*occurrence* of the effect reveals the guard, even though no secret value is
passed. Under an untrusted `pc` it is rejected too (`E235`): an injected value
should not decide whether a privileged effect fires.

Relabelling does not launder `pc`. Our `SecretGuardedLaundered` case endorses a
value *inside* a secret-guarded branch and emits it; it is still rejected,
because `pc` joins into the result of the reclassification.

### 4.4 Sinks and outputs

An emitted argument must be `Public/Trusted`, and `pc` must be `Public/Trusted`.

Returning an untrusted value through `output` is *permitted*. This is a
deliberate asymmetry: the caller of a workflow receives data, not instructions,
so untrusted output is the normal case for a summarisation workflow and
rejecting it would make the system unusable. Returning a secret is not
permitted. Our benchmark checks both directions of this distinction
(`UntrustedToOutputOnly` must be accepted; `SecretAsOutput` must not).

### 4.5 Declassification and endorsement

`declassify` lowers confidentiality; `endorse` raises integrity. Both are
trusted: the compiler records them and makes them visible, and does not verify
that a justification is true. This is the standard position — declassification
is an inherently extra-logical act [20] — and we take the pragmatic line that
the useful guarantee is *enumeration*: a reviewer reading a certificate sees
every point at which the lattice was overridden and the stated reason.

---

## 5. Cost analysis

### 5.1 The algebra

The bound is a pair `⟨guaranteed, estimated⟩` derived by structural induction:

```
C(ε)                      = ⟨0, 0⟩
C(s ; B)                  = C(s) ⊕ C(B)                    componentwise sum
C(if c { A } else { B })  = C(A) ⊔ C(B)                    costlier arm
C(retry n { A })          = n ⊗ C(A)                       componentwise scaling
C(let y = call p(a…) using m)
                          = ⟨ maxTokens(m), τ(tmpl(p)) + Σᵢ bound(aᵢ) ⟩
C(_)                      = ⟨0, 0⟩
```

All arithmetic saturates rather than wrapping, so overflow still yields an
over-approximation.

The two rules that distinguish this from a flat sum are `⊔` and `⊗`. A branch
costs its more expensive arm, not both — a flat sum is *over*-conservative here,
which is merely wasteful. A retry multiplies — a flat sum is *under*-conservative
here, which is unsound, and §10 measures exactly how often.

### 5.2 Why the bound has two components

The components rest on different foundations, and collapsing them would hide
that.

The **guaranteed** component counts output tokens. Providers enforce
`max_tokens` themselves, so this half holds without assuming anything about
tokenization.

The **estimated** component counts input tokens: the prompt template plus the
declared bounds of the arguments substituted into it. It depends on a
tokenization function τ, which the compiler takes as an explicit parameter
`--chars-per-token` (default 4, the common rule of thumb for English prose). At
1 it is unconditionally sound for any tokenizer emitting at most one token per
character; larger values are tighter but sound only relative to the stated
assumption. The value used is recorded in the certificate.

We consider this separation a contribution in its own right. A single number
would let a reader believe the whole bound is as solid as its strongest half.
Reporting `guaranteed 2100 + estimated 1230 @ 4 chars/token` says exactly how
much rests on an assumption, and our test suite pins the property that changing
the assumption moves only the second component.

A monetary figure is derived where models declare `cost_per_token`. It is
reported, not certified; the guarantee is stated over tokens.

### 5.3 Requirements

`require tokens(x) op n` is discharged against the derived bound of `x` and must
hold for every value `x` can take, i.e. every count in `[0, bound(x)]`. An upper
bound can discharge only an upper-bound comparison, so `<` and `<=` are
checkable, `>=` only against zero, and `>`, `==`, `!=` are reported as
undecidable (`E264`) rather than silently accepted.

We note this because the construct existed in the previous version of this
compiler, where it was parsed, lowered into the IR, printed — and never checked.
`require tokens(x) <= 5` against a 600-token model passed. A construct that
looks like a safety check and is inert is worse than no construct.

---

## 6. The cost channel

Consider a branch whose guard is secret and whose arms cost different amounts.
No value crosses any boundary. No tool is invoked. Every taint analysis accepts
it. And the token bill differs depending on which arm ran, so anyone who can see
the bill learns the guard.

```orchlang
if ALERT {                                   // secret
  let a: text = call step(src) using large;  // 900 output tokens
} else {
  let b: text = call step(src) using small;  // 150 output tokens
}
```

Neither analysis finds this alone. The label system does not know what an arm
costs; the cost analysis does not know the guard is a secret. The check is one
line of reasoning over both judgements:

```
guard label ⊒ Secret   ∧   C(A).total ≠ C(B).total   ⟹   E236
```

The same shape with an untrusted guard means an injected value is choosing how
much the workflow spends; we report that as a warning (`W237`) rather than an
error, since it is a denial-of-service concern rather than a disclosure.

A workflow fixes an `E236` by balancing the arms, hoisting the expensive call
out of the branch, or declassifying the guard with a justification.

This is the clearest argument we have for deriving the two properties together
rather than composing two separate tools: the composition finds defects the
components cannot.

---

## 7. What is proved, and what is not

We define a big-step semantics `⟨B, σ⟩ ⇓ ⟨σ', κ, ε⟩` where `σ` maps names to
values with token counts, `κ` counts tokens consumed, and `ε` is the sequence of
tool effects with their arguments. The model is abstract, constrained by two
assumptions:

- **(A1)** a call to model `m` returns at most `maxTokens(m)` output tokens;
- **(A2)** an input honours its declared `max_tokens`, and `τ` bounds the
  tokenizer.

**Theorem 1 (Cost soundness).** If `⊢ W : ⟨g, e⟩` and `⟨W, σ⟩ ⇓ ⟨σ', κ, ε⟩`
under (A1) and (A2), then `κ ≤ g + e`.

*Proof sketch.* Induction on the derivation. The empty block consumes nothing.
Sequencing follows from additivity of `⊕`. For a branch, exactly one arm
executes and `C(A) ⊔ C(B)` dominates each. For `retry n`, the semantics executes
the body at most `n` times and `n ⊗ C(A)` dominates `k` executions for any
`k ≤ n`. For a call, (A1) bounds the output component and (A2) the input
component. Saturation preserves the inequality since the saturated value
dominates every representable total. ∎

Dropping (A1) alone invalidates the guaranteed component; dropping (A2) alone
invalidates only the estimated component. This is exactly why the bound is
reported as a pair.

**Theorem 2 (Effect non-interference).** Let `W` be well-typed with no
declassification. Then for any two stores `σ₁, σ₂` agreeing on all
non-`Secret` bindings, if `⟨W, σ₁⟩ ⇓ ⟨_, κ₁, ε₁⟩` and `⟨W, σ₂⟩ ⇓ ⟨_, κ₂, ε₂⟩`
then `ε₁ = ε₂` and the returned output values agree.

*Proof sketch.* By induction, every value whose label is `Public` is computed
without joining a `Secret` label, hence depends only on non-secret bindings.
`emit` requires `Public/Trusted` arguments and a `Public/Trusted` pc, so the
effect sequence is determined by non-secret data; `output` requires `Public`. ∎

**Theorem 2′ (with `E236`).** Under the same hypotheses, if `W` additionally
passes the cost-channel check then `κ₁ = κ₂` whenever the two executions differ
only in secret bindings and make the same model-level choices.

We state plainly what is *not* claimed.

- These are pen-and-paper proofs over a reference semantics. They are not
  mechanized, and the C++ implementation is not verified against them. §10's
  RQ1 is a differential check of the implementation against the semantics, not
  a proof.
- Theorem 2 is termination-insensitive and covers the effect and output
  channels. Wall-clock timing is not modelled. Theorem 2′ closes the token-count
  channel only under the stated condition.
- Nothing is proved about what a model *says*. The guarantees concern where
  output may flow and how much of it there can be.
- Declassification voids Theorem 2 by construction; the certificate's role is to
  make every such site visible.

---

## 8. The certificate

`orchc certify` emits JSON containing: the derived bound and both components;
the tokenization assumption relied upon; the derivation that produced the bound;
the final label of every binding; every reclassification with its written
justification; and every sink the analysis cleared.

The design intent is that the certificate outlives the compiler invocation. A
runtime can enforce the same number the compiler derived; a reviewer can read
the escape hatches without reading the source; a CI job can diff a certificate
across commits and fail when a bound grows or a new declassification appears.
This is a lighter-weight relative of proof-carrying certificates for LLM
pipelines [21], which certify semantic rather than resource and flow properties.

---

## 9. Implementation

`orchc` is 4,561 lines of hand-written C++17 with no third-party dependencies
and no parser generator: a location-tracking lexer, a
recursive-descent parser with statement-level error recovery, a scoped symbol
table, the flow-typing and cost passes, a region-annotated IR with a dependency
cycle check, the certificate emitter, and an offline mock runtime. It builds
warning-free under `-Wall -Wextra -pedantic`, and a further 1,140 lines carry 83
regression tests.

The flow and cost passes are separate modules sharing a symbol table. Call-site
facts are recorded during typing and keyed by AST node, which lets the cost pass
be a pure structural walk needing no symbol lookups — and lets the cost-channel
check of §6 read guard labels the typing pass recorded.

---

## 10. Evaluation

Benchmarks are generated by `bench/generate.py`; results are reproduced by
`python bench/evaluate.py` and stored in `bench/results/`.

The **cost suite** is 23 workflows varying chain length (1–5), branch arity
(1–4), branch nesting, retry bounds (2–6), nested retries, retry-in-branch and
branch-in-retry, and input width (200/800/2000 tokens).

The **security suite** is 26 workflows in 13 *pairs*. Each unsafe workflow has a
safe counterpart differing by exactly one edit — an added endorsement, a
declassification, a moved effect, a balanced arm. Pairing is what makes the
false-positive number meaningful: a checker cannot score well by rejecting
everything.

To make the bound falsifiable we built an offline mock runtime (`orchc run`).
It executes a workflow against a seeded splitmix64 generator that respects each
model's declared `max_tokens` and each input's declared bound, and counts tokens
actually consumed. Retry attempts stop at the first success.

### RQ1: Is the certified bound ever exceeded?

**No — 0 violations in 4,600 executions** (23 workflows × 200 seeds).

We are explicit about what this does and does not show. The mock honours (A1)
and (A2) because those are the language's contract, so RQ1 is a *differential
check of the analyser against the reference semantics*, not evidence that a
given provider honours its own caps. It would have caught an off-by-one in the
retry scaling or a missed branch arm; it cannot validate the assumptions
themselves.

### RQ2: Is the flat rule sound?

**No.** The rule "sum each syntactic call's `max_tokens`" — used by the previous
version of this compiler, and the obvious thing to reach for — was exceeded on
**621 of 4,600 executions (13.5%)** and is unsound on **8 of 23 workflows**.
Every one of the eight contains a retry:

| workflow | certified | flat | peak observed | flat violated |
|---|---|---|---|---|
| retry_2 | 556 | 278 | 542 | 43/200 |
| retry_3 | 834 | 278 | 693 | 59/200 |
| retry_4 | 1112 | 278 | 875 | 63/200 |
| retry_5 | 1390 | 278 | 1144 | 63/200 |
| retry_6 | 1668 | 278 | 1144 | 63/200 |
| retry_nested_2x2 | 1112 | 278 | 901 | 102/200 |
| retry_nested_2x3 | 1668 | 278 | 1298 | 111/200 |
| retry_nested_3x3 | 2502 | 278 | 1363 | 117/200 |

This is a lower bound on the flat rule's unsoundness: `branch_in_retry`
(certified 2462, flat 1284) is unsound in principle but was not violated within
200 seeds.

### RQ3: How tight is the bound?

Median slack over peak observed consumption is **1.23×** (min 1.02×, max
3.01×). Chains are tightest (1.02–1.17×) since little is over-approximated.
Branches are loosest (1.98–3.01×) because the bound charges the expensive arm
every time. For context, [11] reports 4–6× for a static estimator.

### RQ4: Does the flow analysis separate safe from unsafe?

**13/13 unsafe rejected, 13/13 safe accepted** — precision 1.000, recall 1.000,
covering direct injection, transitive injection through two model calls,
injection inside branches and retries, secrets to prompts, outputs and tools,
implicit flows, laundered implicit flows, untrusted-guarded effects, and the
cost channel.

We do not present this as a general accuracy claim. The suite was written by the
author, from the shapes the analysis was designed to catch. Pairing guards
against trivial over-rejection; it does not eliminate designer bias. §11
addresses this.

### RQ5: What does the analysis cost?

**~6 ms per workflow**, including process startup, for 36 certifications in
0.23 s. The analyses are linear in program size; no constraint solver is
involved. At run time the cost is zero, which is the structural advantage over
every runtime monitor discussed in §1.

---

## 11. Threats to validity

**The security benchmark is author-written.** This is the most serious threat.
The unsafe workflows are instances of shapes we designed for. We mitigate with
pairing — every false-positive opportunity is a workflow one edit away from an
unsafe one — but an independent benchmark (an AgentDojo-style corpus ported to
OrchLang) would be far stronger, and we have not done it.

**RQ1 is not independent of the specification.** As noted, the mock implements
the same assumptions the analysis relies on. A provider that silently exceeds
`max_tokens`, or a tokenizer worse than the declared ratio, breaks the bound;
neither is tested here.

**Expressiveness is restricted.** No general loops, recursion, arithmetic,
higher-order prompts, or dynamic model selection. Whether the analysis survives
those extensions is open; bounded repetition is exactly what makes it decidable.

**The corpus is synthetic.** Workflows are generated from templates, not drawn
from production systems. The cost suite's shapes were chosen to stress control
flow, which is where the flat rule fails — an argument that the suite is fair on
that question, not that it is representative.

**Proofs are not mechanized**, and the implementation is not verified against
them.

**Single-implementation results.** All numbers come from one compiler on one
platform (GCC 16, Windows).

---

## 12. Related work

| System | Form | Static? | Cost bound | Secrets | Injection/integrity |
|---|---|---|---|---|---|
| LMQL [1] | query language | partial (decoding constraints) | no (runtime savings) | no | no |
| SGLang [2] | structured programs + runtime | no | no | no | no |
| DSPy [3] | declarative modules + optimizer | signatures only | no | no | no |
| APPL [4] / PDL [5] | prompt languages | host types | no | no | no |
| Agentproof [13] | extracted graphs + LTL | yes | no | no | no |
| CaMeL [6] | interpreter + capabilities | no (dynamic) | no | yes | yes |
| f-secure [7] | system architecture | no | no | yes | yes |
| AgentFlow [8] | policy + monitor (+bounded SMT) | partial | no | yes | yes |
| NeuroTaint [9], GIF [10] | runtime taint | no | no | yes | yes |
| Token Budgets [11] | Rust affine types | compile-time ownership | runtime cap, not inferred | no | no |
| Budget algebras [12] | multi-agent contracts | no | runtime conservation | no | no |
| AARA [18, 19] | resource type system | yes | yes (not for LLM tokens) | no | no |
| **OrchLang** | **source DSL + type system** | **yes** | **yes, inferred** | **yes** | **yes** |

Two observations. First, the columns are near-disjoint: work that does cost does
not do flow, and vice versa. Second, everything in the flow column is a runtime
mechanism. OrchLang is, to our knowledge, the first system to place both in a
compiler's type system and emit a single certificate — and §6 shows that the
combination is more than the sum.

Prompt-template placeholder checking, which OrchLang also performs, is *not* a
contribution: it is commodity, available in promptml (Rust), promptctl (Python),
type-safe-prompt (TypeScript), and others. We mention it only to disclaim it.

---

## 13. Conclusion and future work

Cost and information flow in LLM workflows are structural properties, and a
language designed for the purpose can certify both before anything runs.
OrchLang derives a token bound that was never exceeded in 4,600 executions where
the obvious flat rule was exceeded 13.5% of the time, and a two-axis flow
property that separates a paired safety benchmark perfectly — at roughly 6 ms
per workflow and zero runtime cost.

The result we find most interesting is the one we did not set out to find: a
secret-guarded branch with unbalanced arms leaks through the bill, and only a
system holding both judgements at once can see it.

The most valuable next steps are, in order: mechanizing Theorems 1 and 2; an
independent security benchmark ported from an existing injection corpus;
extending the cost algebra to data-dependent repetition, where AARA's potential
method [18] is the obvious tool; and a runtime that enforces the emitted
certificate, closing the loop between what the compiler proved and what the
deployment does.

---

## References

[1] L. Beurer-Kellner, M. Fischer, M. Vechev. *Prompting Is Programming: A Query
Language for Large Language Models.* PLDI 2023 / PACMPL 7(PLDI). arXiv:2212.06094.

[2] L. Zheng *et al.* *SGLang: Efficient Execution of Structured Language Model
Programs.* arXiv:2312.07104.

[3] O. Khattab *et al.* *DSPy: Compiling Declarative Language Model Calls into
Self-Improving Pipelines.* ICLR 2024. arXiv:2310.03714.

[4] H. Dong *et al.* *APPL: A Prompt Programming Language for Harmonious
Integration of Programs and Large Language Model Prompts.* ACL 2025.
arXiv:2406.13161.

[5] M. Vaziri *et al.* *PDL: A Declarative Prompt Programming Language.*
arXiv:2410.19135.

[6] E. Debenedetti *et al.* *Defeating Prompt Injections by Design (CaMeL).*
Google DeepMind. arXiv:2503.18813.

[7] *System-Level Defense against Indirect Prompt Injection Attacks: An
Information Flow Control Perspective.* arXiv:2409.19091.

[8] *AgentFlow: A Flow-Centric Policy Language and Framework for Securing LLM
Agent Systems.* arXiv:2608.22868.

[9] *Ghost in the Agent: Redefining Information Flow Tracking for LLM Agents.*
arXiv:2604.23374.

[10] *GIF: Locally Sound Geometric Information Flow Control for LLMs.*
arXiv:2606.23277.

[11] *Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun
Incidents, with an Affine-Typed Rust Mitigation as a Case Study.*
arXiv:2606.04056.

[12] *Retrieval-Conditioned Topology Selection with Provable Budget Conservation
for Multi-Agent Code Generation.* arXiv:2605.05657.

[13] *Agentproof: Static Verification of Agent Workflow Graphs.*
arXiv:2603.20356.

[14] D. E. Denning, P. J. Denning. *Certification of Programs for Secure
Information Flow.* CACM 20(7), 1977.

[15] D. Volpano, C. Irvine, G. Smith. *A Sound Type System for Secure Flow
Analysis.* Journal of Computer Security 4(2–3), 1996.

[16] A. C. Myers. *JFlow: Practical Mostly-Static Information Flow Control.*
POPL 1999.

[17] A. Sabelfeld, A. C. Myers. *Language-Based Information-Flow Security.* IEEE
JSAC 21(1), 2003.

[18] J. Hoffmann, K. Aehlig, M. Hofmann. *Multivariate Amortized Resource
Analysis.* ACM TOPLAS 34(3), 2012.

[19] D. M. Kahn, J. Hoffmann. *Exponential Automatic Amortized Resource
Analysis.* FoSSaCS 2020.

[20] A. Sabelfeld, D. Sands. *Dimensions and Principles of Declassification.*
CSFW 2005.

[21] *Proof-Carrying Certificates for LLM Pipelines: A Trust-Boundary
Architecture.* arXiv:2605.16407.

[22] OWASP. *Top 10 for Large Language Model Applications*, 2025. (LLM01 Prompt
Injection; LLM07 System Prompt Leakage.)

---

## Artifact

Compiler, benchmark generator, evaluation harness, and results:
`https://github.com/guyoverclocked/orchlang-compiler-design-project`

```sh
make check                  # build, 83 tests, example corpus
python bench/generate.py    # regenerate the benchmark
python bench/evaluate.py    # reproduce every number in §10
```
