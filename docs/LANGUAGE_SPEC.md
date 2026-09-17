# OrchLang Language Specification

## Purpose

OrchLang describes LLM workflows that can be checked completely before anything
runs. The compiler answers two questions about a workflow without contacting a
model, reading a key, or touching a network:

1. **What is the most this workflow can cost?** A worst-case upper bound on the
   tokens it can consume on any execution.
2. **Where can data go?** Whether a secret can reach a prompt, an output, or an
   external effect, and whether data derived from an untrusted source can drive
   an external effect.
3. **Can a secret change the bill?** Whether the per-model billing vector is
   independent of every secret, which is a *relational* question about two
   executions rather than a property of one.

All three are written into an analysis report the compiler emits as JSON.

## Design commitments

Three commitments shape the grammar, and each exists because a static answer to
the questions above would otherwise be impossible.

**Repetition is bounded syntactically.** `retry` carries a literal bound. An
unbounded loop would make the cost bound infinite and the analysis useless, so
the language does not offer one.

**Lengths that the compiler cannot see must be declared.** An input's length is
not knowable from the source. If an input reaches a prompt without a declared
`max_tokens`, the compiler reports `E261` rather than guessing a number and
calling the result a bound.

**Leaving the lattice requires saying why.** `declassify` and `endorse` are the
only ways to relax a security label, and both demand a written justification
that is carried into the certificate. The escape hatches exist because real
workflows need them; requiring a justification means a reviewer can find every
one of them.

## Tokens

| Category | Accepted forms |
| --- | --- |
| Structure | `workflow`, `budget` |
| Declarations | `input`, `secret`, `model`, `mock`, `max_tokens`, `cost_per_token`, `prompt`, `tool` |
| Statements | `let`, `call`, `using`, `require`, `tokens`, `output`, `emit`, `if`, `else`, `retry` |
| Security | `untrusted`, `declassify`, `endorse`, `as`, `because` |
| Types | `text`, `integer`, `decimal`, `boolean`, `json` |
| Identifiers | Letter or `_`, followed by letters, digits, or `_` |
| Literals | Quoted strings, integer literals, decimal literals, `true`, `false` |
| Delimiters | `{`, `}`, `(`, `)`, `:`, `;`, `,`, `->` |
| Operators | `=`, `<`, `<=`, `>`, `>=`, `==`, `!=` |
| Comments | `//` to the end of a line |

Strings support `\n`, `\t`, `\"`, and `\\`. The lexer records the first line and
column of every token. It reports `L001` for unexpected characters, `L002` for
unterminated strings, and `L003` for unsupported string escapes.

## Grammar

```ebnf
program          ::= workflowDecl* EOF
workflowDecl     ::= "workflow" IDENT "budget" INTEGER block
block            ::= "{" statement* "}"
statement        ::= inputDecl | secretDecl | modelDecl | promptDecl | toolDecl
                   | letStmt | requireStmt | emitStmt | ifStmt | retryStmt
                   | reclassifyStmt | outputStmt

inputDecl        ::= "input" IDENT ":" type "untrusted"? tokenBound? ";"
secretDecl       ::= "secret" IDENT (":" type)? tokenBound? ";"
tokenBound       ::= "max_tokens" INTEGER
modelDecl        ::= "model" IDENT "=" "mock" "(" STRING ")"
                     "max_tokens" INTEGER ("cost_per_token" NUMBER)? ";"
promptDecl       ::= "prompt" IDENT "(" parameters? ")" "->" type "=" STRING ";"
toolDecl         ::= "tool" IDENT "(" parameters? ")" ";"
parameters       ::= parameter ("," parameter)*
parameter        ::= IDENT ":" type

letStmt          ::= "let" IDENT ":" type "=" callExpr ";"
callExpr         ::= "call" IDENT "(" arguments? ")" "using" IDENT
arguments        ::= expression ("," expression)*
requireStmt      ::= "require" "tokens" "(" IDENT ")" comparison INTEGER ";"
emitStmt         ::= "emit" IDENT "(" arguments? ")" ";"
ifStmt           ::= "if" condition block ("else" block)?
condition        ::= "tokens" "(" IDENT ")" comparison INTEGER | IDENT
retryStmt        ::= "retry" INTEGER block
reclassifyStmt   ::= ("declassify" | "endorse") "(" IDENT ")"
                     "as" IDENT ":" type "because" STRING ";"
outputStmt       ::= "output" expression ";"

expression       ::= IDENT | STRING | INTEGER | DECIMAL | BOOLEAN
type             ::= "text" | "integer" | "decimal" | "boolean" | "json"
comparison       ::= "<" | "<=" | ">" | ">=" | "==" | "!="
```

The parser uses one-token lookahead. On a malformed statement it synchronizes at
a semicolon, a closing brace, or the next statement keyword, so independent
errors are reported together.

Each block is its own scope. A binding introduced inside a branch arm or a retry
body does not escape it.

## Security labels

Every value carries a label drawn from the product lattice

```
L  =  Confidentiality  x  Integrity
   =  {Public <= Secret}  x  {Trusted <= Untrusted}
```

with the componentwise order and join. `Public/Trusted` is the bottom element:
it flows anywhere.

| Construct | Label |
| --- | --- |
| `input x: T;` | `Public/Trusted` |
| `input x: T untrusted;` | `Public/Untrusted` |
| `secret S: T;` | `Secret/Trusted` |
| literal | `Public/Trusted` |
| `let y = call p(a₁..aₙ) using m;` | `pc ⊔ label(a₁) ⊔ … ⊔ label(aₙ)` |
| `declassify(x) as y` | `label(x)` with confidentiality lowered to `Public` |
| `endorse(x) as y` | `label(x)` with integrity raised to `Trusted` |

### The injection propagation rule

A model's answer is labelled with the join of everything that reached its
prompt. A model given only trusted input yields a trusted answer; a model given
anything untrusted yields an untrusted answer, and so does any model downstream
of it. This is what makes indirect prompt injection a type error: text from a
retrieved page cannot become an instruction that drives a tool, however many
model calls sit between the page and the tool, unless someone endorses it and
writes down why.

### The program-counter label

Inside `if c { … }`, the label of `c` joins the program-counter label `pc` of
both arms. Every value produced in an arm inherits `pc`, and an effect performed
in an arm is checked against it. This is what catches implicit flows: an effect
guarded by a secret leaks that secret through whether the effect happened at
all, even when no secret value is passed anywhere. Relabelling inside such a
branch does not launder `pc`.

### Sinks

`emit` is the only construct with an outward effect, so tools are the strictest
position in the language. An emitted argument must be `Public/Trusted`, and `pc`
must be `Public/Trusted` too.

Returning an untrusted value through `output` is permitted: the caller receives
data, not an instruction. Returning a secret is not.

## Cost bound

The bound is derived by structural induction over a workflow body:

```
C(ε)                       = ⟨0, 0⟩
C(s ; B)                   = C(s) ⊕ C(B)                  componentwise sum
C(if c { A } else { B })   = C(A) ⊔ C(B)                  the more expensive arm
C(retry n { A })           = n ⊗ C(A)                     componentwise scaling
C(let y = call p(a…) using m)
                           = ⟨ maxTokens(m),  τ(template(p)) + Σ bound(aᵢ) ⟩
C(anything else)           = ⟨0, 0⟩
```

All arithmetic saturates rather than wrapping, so an overflow yields a bound
that is still an over-approximation.

### Why the bound has two components, and how a branch combines them

At a branch each component is maximised **separately**, and the total is tracked
alongside. Taking the larger arm's pair whole would bound the total but not each
half, because the losing arm can dominate one component; a certificate claiming
one output token once admitted an execution producing twenty. The invariant is
`total <= guaranteed + estimated`, and the gap is the price of a faithful split.



The two components are reported separately because they rest on different
foundations.

The **guaranteed** component counts output tokens. Providers enforce
`max_tokens` themselves, so this half holds without assuming anything about how
text is tokenized.

The **estimated** component counts input tokens: the prompt template plus the
declared bounds of the arguments substituted into it. It depends on a
tokenization function τ, which the compiler takes as an explicit parameter
`--chars-per-token` (default 4). At 1 the estimate is unconditionally sound for
any tokenizer that never emits more than one token per character; larger values
give a tighter bound that is sound only relative to the stated assumption. The
value used is recorded in the certificate, so a reader can see precisely how
much of the number rests on an assumption.

A monetary figure is derived from `cost_per_token` where models declare one. It
is reported, not certified: the guarantee is stated over token counts.

### The relational obligation on secret-guarded branches

A branch can leak its guard without any value crossing a boundary: if the arms
bill differently, the invoice differs, and whoever reads it learns which arm ran.

The obvious rule -- accept when both arms have equal certified upper bounds -- is
unsound, because an upper bound constrains a maximum and two quantities with the
same maximum need not be equal. `examples/invalid/equal_bounds.orch` is a
workflow that rule accepts and whose bill nonetheless moves with the secret.

Numbers cannot be compared here at all, because a call's output length is chosen
by the provider rather than the program. So the compiler compares *structure*.
Each arm is abstracted to a **billing signature**: an ordered record of which
model is called and a symbolic term for its input size, where the term is built
only from

- constants, from the template and from literal arguments;
- `|x|` for a variable bound outside the branch, equal because public inputs are
  fixed; and
- the result of an earlier call in the same signature, referred to *by position*
  and equal because the k-th call returns the same answer under a shared model
  oracle.

A branch on a public guard keeps both arms, since both executions see the same
public data and take the same one. A nested secret-guarded branch whose arms
already agree contributes that common signature, which makes the analysis
compositional. An argument whose label is secret makes the signature undefined.

At a secret-guarded branch, both signatures must be defined and equal, or `E236`
reports which events differ.

The rule is sound and deliberately incomplete: two arms reading different
variables that happen always to have equal length are rejected, because the
compiler has no reason to believe they do.

### Spend influence

`W237` is a warning, not a secrecy claim: when an *untrusted*-guarded branch has
arms of differing bounds, an injected value is choosing how much the workflow
spends. That is a denial-of-service concern, so it is surfaced rather than
rejected.

### Requirements

`require tokens(x) op n` is discharged against the derived bound of `x`, and it
must hold for every value `x` can take, which is any count in `[0, bound(x)]`.
An upper bound can only discharge an upper-bound comparison, so `<` and `<=` are
checkable, `>=` is checkable only against zero, and `>`, `==` and `!=` are
reported as undecidable rather than silently accepted.

## Diagnostics

| Code | Rule |
| --- | --- |
| `L001`–`L003` | Unexpected character, unterminated string, unsupported escape |
| `P001`, `P004` | Unexpected token; malformed integer literal |
| `P005` | `retry` requires a bound of at least 1 |
| `P006` | A reclassification justification may not be empty |
| `E201` | A declaration name may appear only once in its scope |
| `E202` | Identifiers must be declared before use |
| `E210` | A `let` result type must match the called prompt's return type |
| `E211` | An `if` condition naming an identifier must be boolean |
| `E212` | A reclassification must preserve the value's type |
| `E220` | A `let` call must name a declared prompt |
| `E221` | Call arity must match the prompt's parameter count |
| `E222` | Every placeholder must name one declared parameter exactly once |
| `E223` | Argument types must match parameter types |
| `E230` | A secret may not be passed to a prompt |
| `E231` | A secret may not be exposed as the workflow output |
| `E232` | A secret may not reach a tool |
| `E233` | An untrusted value may not reach a tool |
| `E234` | An effect may not be guarded by a secret condition |
| `E235` | An effect may not be guarded by an untrusted condition |
| `W236` | A reclassification that changes nothing (warning) |
| `E236` | A secret-guarded branch whose arms have unequal billing signatures |
| `W237` | An untrusted-guarded branch whose arms bound differently (warning) |
| `E241` | The model in a `using` clause must be declared |
| `E242` | The tool in an `emit` statement must be declared |
| `E243` | Emit arity must match the tool's parameter count |
| `E244` | Emit argument types must match the tool's parameter types |
| `E250` | The lowered IR must not contain a dependency cycle |
| `E260` | The certified bound must not exceed the declared budget |
| `E261` | A value reaching a prompt must carry a declared token bound |
| `E262` | A `require` must be satisfied by the derived bound |
| `E263` | A `require` or `tokens(...)` guard needs a subject with a bound |
| `E264` | A requirement that an upper bound cannot discharge |
| `E265` | The workflow has no defined bound |
| `E266` | The bound is too large to represent |
| `E270` | A workflow must declare one output |
| `E271` | A workflow may not declare more than one output |

## Worked example

```orchlang
workflow ResearchDigest budget 2400 {
  input query: text max_tokens 100;
  input web_page: text untrusted max_tokens 600;
  model reader = mock("offline-reader") max_tokens 500;
  tool publish(body: text);

  prompt digest(page: text) -> text = "Summarise the retrieved page: {page}";

  let digest_text: text = call digest(web_page) using reader;
  endorse(digest_text) as vetted: text because "passed the offline schema and length validator";
  emit publish(vetted);

  output query;
}
```

`web_page` is untrusted, so `digest_text` is untrusted, so `emit publish(digest_text)`
would be rejected with `E233`. The endorsement is what permits the effect, and
the certificate records it verbatim alongside the derived bound.

## Certificate

`orchc certify file.orch` emits JSON containing the derived bound and its two
components, the tokenization assumption relied on, the derivation that produced
the bound, the final label of every binding, every reclassification with its
justification, and every sink the analysis cleared. A runtime, a reviewer, or a
CI job can check a deployed workflow against the same numbers the compiler
derived without re-running the analysis.

## Scope and limitations

The compiler is offline and makes no model requests. The following are outside
what it claims:

- Nothing is proven about what a model *says*, only about where its output may
  flow and how much of it there can be.
- The estimated half of the bound is relative to the declared tokenization
  assumption. It is not a bound on adversarially chosen text at a
  characters-per-token setting above 1.
- The monetary figure is derived from declared prices and is not a billing
  guarantee.
- Declassification and endorsement are trusted. The compiler records them and
  makes them visible; it does not verify that a justification is true.
- `retry` models bounded repetition. There is no general loop, no recursion, and
  no arithmetic, so the cost algebra stays decidable.
