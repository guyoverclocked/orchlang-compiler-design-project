# OrchLang

## A statically typed DSL whose compiler asks whether a secret can change your LLM bill

**Student:** Nambi Rajan M
**Registration number:** 24BAI0072

A workflow that calls a language model can leak a secret through its invoice. If
a secret decides which branch runs, and the branches consume different numbers of
tokens, whoever sees the bill learns the secret — even though no secret value
ever reaches a prompt, an output, or a tool.

OrchLang is a small compiler that decides, from source alone and without
contacting any model, three things about a workflow:

1. **What is the most this can cost?** A worst-case token bound.
2. **Where can data go?** Whether a secret can reach a prompt, an output, or an
   external effect, and whether text from an untrusted source can drive one.
3. **Can a secret change the bill?** The relational property above.

Hand-written C++17. No parser generator, no third-party dependencies, no network
access at any point.

## The interesting part

The obvious way to answer question 3 is to compare the two branches' certified
upper bounds and accept when they are equal. **That rule is unsound**, and this
repository contains the counterexample:

```orchlang
secret s: text max_tokens 1;
input  x: text max_tokens 100;
input  y: text max_tokens 100;

if tokens(s) == 0 {
  let a: text = call p(x) using m;   // both arms: same model,
} else {                             // same declared cap,
  let b: text = call p(y) using m;   // so both bound at 111 tokens
}
```

Equal bounds. But `x` and `y` are different values with different actual lengths.
In the paired experiment this workflow's bill differs in **225 of 425**
executions that vary only the secret. An earlier version of this compiler
accepted it and claimed a theorem for it.

The repair is not a tighter number. In an LLM workflow a call's output length is
chosen by the *provider*, not the program, so no numeric potential can be
attached to a call site — which is exactly the assumption that classical
relational cost analysis (RelCost, POPL'17) and resource-aware noninterference
(Ngo et al., S&P'17) rest on.

So OrchLang compares **structure** instead of numbers. Each branch arm is
abstracted to a *billing signature* — which model is called, in what order, and a
symbolic term for its input size built only from quantities that provably agree
across the two compared runs. Equal signatures under a shared model oracle imply
equal per-model billing.

```
error [E236] this branch is guarded by a secret and its two arms bill
differently, so the bill reveals the secret;
then-arm bills [m(in=1 + |x|)] and else-arm bills [m(in=1 + |y|)]
```

## Results

From `bench/results/evaluation.txt`, reproduced by `python bench/evaluate.py`
(which exits nonzero if any assertion fails):

| Experiment | Result |
| --- | --- |
| Unary bound exceeded? (checked **componentwise**) | **0 of 4,600** executions, on total, output, and input |
| Flat per-call sum exceeded? | **636 / 4,600 (13.8%)** |
| Control-flow-aware rule exceeded? | **644 / 4,600 (14.0%)** — branch-awareness alone does not rescue it |
| Slack over peak observed | median **1.11×** (1.02–1.84×), with zero dead branch arms |
| Accepted workflows: does the secret move the bill? | **0 differing bills in 2,975 paired comparisons** |
| Rejected workflows: is the rejection real? | **7 of 7 have a concrete leaking witness** |
| Flow policy conformance | **13/13 unsafe rejected, 13/13 safe accepted** |

The relational experiment fixes the seed and the public inputs and enumerates
every secret value, so a difference can only be attributed to the secret.

## Build and test

```sh
make clean
make check
```

Builds with `-std=c++17 -Wall -Wextra -pedantic`, runs 95 assertions, accepts
every valid example, confirms every invalid example is rejected, and emits a
certificate for each valid workflow.

Requires a C++17 compiler. GCC 6 is too old (`std::optional`); GCC 7+, Clang 5+,
or MSVC 2017+ will work.

## Command-line use

```sh
./orchc check   examples/valid/untrusted_endorsed.orch   # types, flow, cost, relational
./orchc cost    examples/valid/branching_cost.orch       # the bound, with its derivation
./orchc certify examples/valid/untrusted_endorsed.orch   # JSON analysis report
./orchc run     examples/valid/bounded_retry.orch --seed 7
./orchc run     file.orch --seed 7 --pin x=40 --pin s=0  # pin inputs for paired runs
./orchc tokens  file.orch
./orchc ast     file.orch
./orchc symbols file.orch
./orchc ir      file.orch
./orchc ir-json file.orch
```

Valid source returns 0; lexical, syntax, type, flow, cost, or relational errors
return 1; missing files and bad usage return 2.

## The mock runtime

`orchc run` exists to make the claims falsifiable. It executes a workflow against
a seeded generator that respects each model's declared cap and each input's
declared bound, and reports the per-model billing vector. `--pin` fixes an input
or secret's length, which is what lets the harness vary one secret and hold
everything else constant.

It is a differential check of the implementation against the language's
semantics — not evidence that a provider honours its own caps. That assumption is
stated, not tested.

## Repository structure

```text
include/            Compiler data structures and module interfaces
src/                Lexer, parser, AST, symbols, flow typing, cost analysis,
                    relational analysis, IR, certificate, mock runtime, CLI
tests/tests.cpp     Standalone 95-test regression executable
examples/           Valid, invalid, and boundary programs
bench/              Generated corpus (cost, relational, security) and harness
audit/              An external audit, its counterexamples, and repro scripts
docs/               Language specification, the paper, submission materials
```

## What this does not claim

- **Combining flow and resource analysis is not new.** Ngo et al. (S&P'17)
  formalised resource-aware noninterference; RelCost (POPL'17) gave relational
  cost bounds for side-channel reasoning. What is specific here is the treatment
  of *opaque stochastic calls*, where numeric comparison is unavailable.
- **Leakage through token counts is not a new defect class.** *Time Will Tell*
  and the USENIX token-length attacks establish it at the single-call level.
- **The relational guarantee is relative to a coupling** of the model oracle: it
  says the secret does not change the bill *given the model behaved the same way*.
- **Declassification and endorsement are trusted.** The compiler records every
  site with its written justification; it does not verify one.
- **The certificate is a report, not a proof.** No independent checker exists yet.
- **Token bounds are not portable across tokenizers.** A cap in one model's
  tokens is reused as another model's input bound, which is a real gap.
- **The proofs are on paper**, not mechanized, and the implementation is not
  verified against them.
- **The corpus is generated and the security labels are the author's.**

`docs/PAPER.md` states all of this precisely; `audit/2026-09-17/` preserves the
external audit that produced several of these corrections.
