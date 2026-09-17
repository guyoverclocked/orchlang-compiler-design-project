# OrchLang

## A statically typed DSL whose compiler certifies the cost and the information flow of an LLM workflow before it runs

**Student:** Nambi Rajan M
**Registration number:** 24BAI0072

OrchLang is an offline compiler for a small language that describes LLM
workflows. It answers two questions about a workflow without contacting a model,
reading a key, or touching a network:

- **What is the most this can cost?** A certified upper bound on the tokens any
  execution can consume.
- **Where can data go?** Whether a secret can reach a prompt, an output, or an
  external effect, and whether data derived from an untrusted source can drive
  an external effect.

Both answers come from one type system over one program, and both are written
into a machine-checkable JSON certificate.

The compiler is hand-written C++17. It uses no Flex, Bison, ANTLR, or external
parsing framework, and it has no third-party runtime dependencies.

## Why this is not the obvious thing

The obvious way to bound a workflow's cost is to add up the `max_tokens` of
every model call in the source. That rule is unsound, and the benchmark
quantifies how unsound: it is **violated on 13.5% of executions**, across
**8 of 23 workflows** — every workflow containing a retry. A retry block runs its
body more than once, and a flat sum counts it once.

The obvious way to stop secrets and injected text from reaching tools is to scan
strings at runtime. Every published defence in this space works that way, and
pays for it in runtime overhead and coverage gaps. OrchLang makes it a typing
judgement instead, so the answer is available before deployment and costs
nothing at run time.

## What the compiler checks

**Cost.** The bound is derived by structural induction, so a branch costs its
more expensive arm and a retry multiplies its body:

```
C(if c { A } else { B })  =  C(A) ⊔ C(B)
C(retry n { A })          =  n ⊗ C(A)
```

It is reported in two parts. The **guaranteed** part counts output tokens, which
providers cap themselves, so it assumes nothing about tokenization. The
**estimated** part counts input tokens and is sound relative to a declared
characters-per-token assumption, which the certificate records. Keeping them
apart lets a reader see exactly how much of the number rests on an assumption.

**Information flow.** Labels live in the product lattice
`(Public ≤ Secret) × (Trusted ≤ Untrusted)`. A model's answer inherits the join
of everything that reached its prompt, so untrusted text stays untrusted through
any number of model calls. A program-counter label catches implicit flows, where
a secret leaks through *whether* an effect happened rather than through a value.
`declassify` and `endorse` are the only escapes and both require a written
justification that lands in the certificate.

**The cost channel.** Putting both analyses in one type system finds a defect
neither can see alone. Consider:

```orchlang
if ALERT {                                   // a secret boolean
  let a: text = call step(src) using large;  // 900 output tokens
} else {
  let b: text = call step(src) using small;  // 150 output tokens
}
```

No value crosses any boundary. No tool is invoked. Every taint checker accepts
it. The token bill still reveals the secret. The label system does not know what
an arm costs; the cost analysis does not know the guard is a secret; together
they reject it (`E236`). This is the most interesting thing in the project.

## Results

From `bench/results/evaluation.txt`, reproducible with `python bench/evaluate.py`:

| Question | Result |
| --- | --- |
| Is the certified bound ever exceeded? | **0 violations in 4,600 executions** |
| Is the flat `Σ max_tokens` rule ever exceeded? | **621 of 4,600 runs (13.5%)**, unsound on 8 of 23 workflows |
| How much slack does the bound carry? | median **1.23×** peak observed (range 1.02–3.01×) |
| Does the flow analysis separate safe from unsafe? | **13/13 unsafe rejected, 13/13 safe accepted** |
| What does the analysis cost? | ~6 ms per workflow, including process startup |

The security suite is *paired*: every unsafe workflow has a safe counterpart
differing by one edit (an added endorsement, a declassification, a moved
effect). A checker cannot score well on it by rejecting everything.

## Build and test

```sh
make clean
make check
```

`make check` builds with `-std=c++17 -Wall -Wextra -pedantic`, runs 83
assertions, accepts every valid example, confirms every invalid example is
rejected, and emits a certificate for each valid workflow.

Requires a C++17 compiler. GCC 6 is too old (`std::optional`); GCC 7 or later,
Clang 5 or later, or MSVC 2017 or later will work.

## Command-line use

```sh
./orchc check   examples/valid/untrusted_endorsed.orch   # type, flow, and cost
./orchc cost    examples/valid/branching_cost.orch       # the bound, with its derivation
./orchc certify examples/valid/untrusted_endorsed.orch   # the JSON safety certificate
./orchc run     examples/valid/bounded_retry.orch --seed 7   # offline mock execution
./orchc tokens  examples/valid/summarization.orch
./orchc ast     examples/valid/summarization.orch
./orchc symbols examples/valid/summarization.orch
./orchc ir      examples/valid/branching_cost.orch
./orchc ir-json examples/valid/branching_cost.orch
```

Options: `--chars-per-token <n>` sets the tokenization assumption (1 is
unconditionally sound, larger is tighter; default 4). `--seed <n>` and
`--retry-failure <p>` control the mock runtime.

Valid source returns 0. Lexical, syntax, type, flow, or cost errors return 1.
Missing files and bad usage return 2.

A `cost` run shows its working:

```text
TieredTriage:
  token bound   1639 / budget 2000  (guaranteed 1020 + estimated 619 @ 4 chars/token)
  derivation for TieredTriage:
      call  severity = triage via small [out<=120, in<=8+300]  => 428 tokens
      branch  tokens(severity) <= 120  => 0 tokens
        call  reply = acknowledge via small [out<=120, in<=12+300]  => 432 tokens
        call  reply = escalate via large [out<=900, in<=11+300]  => 1211 tokens
      branch-max  max(then=432, else=1211)  => 1211 tokens
```

## The mock runtime

`orchc run` exists to make the compiler's claim falsifiable. A bound nothing can
test is a bound nothing can trust. The runtime executes a workflow against a
seeded generator that respects each model's declared `max_tokens`, counts the
tokens actually consumed, and reports them, so the harness can check every
execution against the certificate.

It is a differential check of the analyser against the language's semantics, not
evidence that a particular provider honours its own caps. That assumption is
stated, not tested.

## Repository structure

```text
include/            Compiler data structures and module interfaces
src/                Lexer, parser, AST, symbols, flow typing, cost analysis,
                    IR, certificate, mock runtime, CLI
tests/tests.cpp     Standalone 83-test regression executable
examples/           Valid, invalid, and boundary OrchLang programs
bench/              Generated benchmark corpus and the evaluation harness
docs/               Language specification and the paper
Makefile            C++17 build, tests, and example checks
```

## Known limitations

- Nothing is proven about what a model *says*, only about where its output may
  flow and how much of it there can be.
- The estimated half of the bound is relative to the declared tokenization
  assumption, and is not a bound on adversarially chosen text above 1
  character per token.
- Declassification and endorsement are trusted. The compiler records them and
  makes every one visible; it does not verify that a justification is true.
- There is no general loop, no recursion, and no arithmetic, which is what keeps
  the cost algebra decidable.
- The security suite was written by the author. Pairing each unsafe workflow
  with a minimally different safe one guards against trivial over-rejection, but
  it is not an independent benchmark.
