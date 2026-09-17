# OrchLang Demonstration Script

About eight minutes. Nothing here needs internet access; the compiler makes no
network requests at any point.

Run everything from the repository root after `make clean && make check`.

---

## 0:00 – 0:45  The problem

Say: "LLM workflows fail expensively in three ways. They spend more than you
meant. They let data go where it shouldn't — a key into a prompt, or text from a
web page into a tool call. And, more subtly, the *amount* they spend can itself
reveal a secret. Almost every tool that addresses the first two finds out at run
time, once the tokens are gone and the effect has fired. OrchLang answers all
three from the source, before anything runs."

---

## 0:45 – 1:25  Build and test

```sh
make clean && make check
```

Expected: a strict C++17 build with `-Wall -Wextra -pedantic` and no warnings,
`Passed 95/95 tests.`, the valid corpus accepted, every invalid example
rejected, and a certificate emitted for each valid workflow.

---

## 1:25 – 2:30  The headline: cost is structural, not a sum

```sh
./orchc cost examples/valid/branching_cost.orch
```

Expected: the derivation prints its working. Point at the last two lines —
the branch's two arms cost 432 and 1211, and the bound takes the **maximum**,
not the sum.

```sh
./orchc cost examples/valid/bounded_retry.orch
```

Expected: `retry-scale  3 x 1110  => 3330 tokens`. Say: "A flat sum over
syntactic call sites reports 1110 here. The workflow can spend 3330. That is
the direction that matters, because it is unsound — the benchmark shows it is
violated on 13.8% of real executions."

Point out the components line: `output <= 2100, input <= 1230 @ 4 chars/token`.
The output half is provider-enforced and assumes nothing; the input half is
relative to a recorded tokenization assumption. Each is maximised separately at
a branch, so each holds on its own.

---

## 2:30 – 3:30  Indirect prompt injection is a type error

```sh
./orchc check examples/invalid/untrusted_sink.orch
```

Expected: `E233`. Say: "`web_page` is declared untrusted. The model's answer
inherits that, because a model is only as trustworthy as what reached its
prompt. So the answer cannot drive a tool."

```sh
./orchc check bench/security/unsafe/InjectionTransitive.orch
```

Expected: still `E233`, now through **two** model calls. Say: "Chaining calls
does not launder it."

```sh
./orchc check bench/security/safe/InjectionTransitiveEndorsed.orch
```

Expected: accepted. The difference is one `endorse(...) because "..."` line.

---

## 3:30 – 4:15  Implicit flow

```sh
./orchc check examples/invalid/implicit_flow.orch
```

Expected: `E234`. Say: "No secret value is passed anywhere here. The secret only
decides *whether* the tool fires — and that alone tells an observer one bit of
the secret. The program-counter label catches it."

Mention that `bench/security/unsafe/SecretGuardedLaundered.orch` tries to escape
this by endorsing inside the branch, and is still rejected.

---

## 4:15 – 5:30  The bill leaks the secret — and my first answer was wrong

```sh
./orchc check examples/invalid/cost_channel.orch
```

Expected: `E236`, naming what each arm bills.

Say: "A secret decides which branch runs. One arm calls a big model, the other a
small one. No value crosses any boundary, no tool is called, and every taint
tracker accepts this program — but the invoice still tells you the secret."

Then the important part:

```sh
./orchc check examples/invalid/equal_bounds.orch
```

Expected: `E236`, reporting `then-arm bills [m(in=1 + |x|)]` against
`else-arm bills [m(in=1 + |y|)]`.

Say: "My first rule was to accept when both arms had the same certified upper
bound. Here both arms call the same model with an argument capped at a hundred,
so both bound at exactly 111, and that rule accepted this. But x and y are
different strings with different real lengths. An upper bound tells you a
maximum, not a value. An external audit built this counterexample and measured
it: the bill differs in 225 of 425 paired runs. I withdrew the theorem.

The repair cannot be a tighter number, because a call's output length is the
provider's choice, not the program's. So the compiler compares structure — which
model, in what order, and a symbolic input size that may only mention things
that provably agree across the two runs. Here the terms differ: |x| against |y|."

```sh
./orchc check examples/valid/balanced_signature.orch
```

Expected: accepted. The only edit is that both arms now read the same variable.

---

## 5:15 – 6:00  The certificate

```sh
./orchc certify examples/valid/untrusted_endorsed.orch
```

Expected: JSON carrying the bound and its two components, the tokenization
assumption relied on, the derivation, the final label of every binding, the
endorsement with its written justification, and the sink that was cleared.

Trace one line: `web_page` is `untrusted`, `digest_text` is `untrusted`,
`vetted` is `trusted`, and the reclassification entry says exactly why.

---

## 6:00 – 6:45  Front-end phases

```sh
./orchc tokens  examples/valid/support_triage.orch
./orchc ast     examples/valid/untrusted_endorsed.orch
./orchc symbols examples/valid/untrusted_endorsed.orch
./orchc ir      examples/valid/branching_cost.orch
```

Expected: location-aware tokens; an AST with labels and declared bounds; a
symbol table showing each symbol's label and token bound; IR nodes carrying
region paths and repeat factors.

```sh
./orchc check examples/invalid/multiple_errors.orch
```

Expected: a dozen independent diagnostics from one run — `E201`, `E202`, `E210`,
`E221`, `E222`, `E223`, `E230`, `E231`, `E241`, `E261`, `E271`. Say that the
parser synchronizes at statement boundaries rather than stopping at the first
fault.

---

## 6:45 – 7:30  The claim is falsifiable

```sh
./orchc cost examples/valid/bounded_retry.orch | head -2
./orchc run  examples/valid/bounded_retry.orch --seed 1
./orchc run  examples/valid/bounded_retry.orch --seed 2
```

Expected: the certified bound is 3330; the runs consume well under it, and a
different seed takes a different number of attempts.

Say: "A bound nothing can test is a bound nothing can trust. The mock runtime
executes the workflow against a seeded generator that respects each model's
declared cap, and counts what was actually spent. The harness checks every run
against the certificate."

---

## 7:30 – 8:00  Results and honesty

```sh
cat bench/results/evaluation.txt
```

Point at four numbers:

- certified bound exceeded, checked componentwise: **0 of 4,600 runs**
- flat per-call sum exceeded: **636 of 4,600 (13.8%)**
- control-flow-aware rule exceeded: **644 of 4,600 (14.0%)** — tightening an
  unsound bound makes it fail *more* often; retries are what break it
- slack over peak observed: median **1.11×**, with zero dead branch arms
- accepted workflows with a secret-dependent bill: **0 of 2,975 comparisons**
- rejected workflows with a real leaking witness: **7 of 7**
- security suite: **13/13 unsafe rejected, 13/13 safe accepted**

Close by naming the limitations rather than waiting to be asked:

- Combining flow and resource analysis is not new — Ngo et al. (IEEE S&P 2017)
  and RelCost (POPL 2017) did it for conventional programs. What is specific
  here is the opaque stochastic call, where numeric comparison is unavailable.
- The relational guarantee is relative to a coupling: the secret does not change
  the bill *given the model behaved the same way*.
- Declassification is trusted; the compiler records it, it does not verify it.
- Token bounds are not portable across tokenizers, which is the clearest
  remaining gap.
- The proofs are on paper, not mechanized, and the mock runtime implements the
  same assumptions the analysis relies on — so it checks the implementation
  against the specification, not the specification against reality.
- The security suite was written by the author, mitigated but not eliminated by
  pairing every unsafe workflow with a safe one differing by one edit.
