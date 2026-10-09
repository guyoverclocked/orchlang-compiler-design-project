# OrchLang Language Specification

## Purpose

OrchLang describes LLM workflows that can be checked completely before anything
runs. The compiler answers three questions about a workflow without contacting a
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

Three commitments keep the supported fragment finite and make its analysis contracts explicit.

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
| `let y = call p(a₁..aₙ) using m;` | Effective label `pc ⊔ L(a₁) ⊔ … ⊔ L(aₙ)`; explicit-data label `D(a₁) ⊔ … ⊔ D(aₙ)` |
| `declassify(x) as y` | `label(x)` with confidentiality lowered to `Public` |
| `endorse(x) as y` | `label(x)` with integrity raised to `Trusted` |

Each binding has an effective label `L`, including control dependence, and an
explicit-data label `D`, excluding the program counter. `D` alone does not
establish secret independence. Direct secret argument data is rejected; a call
using a prior result produced under secret control is admitted only when the
enclosing relational request obligation succeeds. Sinks still use `L` and `pc`.

### The declared integrity propagation rule

A model's answer is labelled with the join of everything that reached its
prompt. A model given only trusted input yields a trusted answer; a model given
anything untrusted yields an untrusted answer, and so does any model downstream
of it. Thus data declared untrusted cannot reach a tool effect through model calls
without explicit endorsement. This enforces the declared policy. It does not
inspect malicious text or establish general prompt-injection resistance. An
endorsement reason is recorded, not executed as a validator.

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
C(ε)                       = ⟨0, 0, 0⟩
C(s ; B)                   = C(s) ⊕ C(B)                  componentwise sum
C(if c { A } else { B })   = C(A) ⊔ C(B)                  componentwise maximum
C(retry n { A })           = n ⊗ C(A)                     componentwise scaling
C(let y = call p(a…) using m)
                           = ⟨ cap(m), τ(template(p)) + Σ bound(aᵢ),
                               cap(m) + τ(template(p)) + Σ bound(aᵢ) ⟩
C(anything else)           = ⟨0, 0⟩
```

Arithmetic saturates to an unusable overflow sentinel rather than wrapping.
`E266` rejects a saturated total; the compiler does not issue that sentinel
as a finite numerical upper bound on an arbitrarily large mathematical cost.

### Why the bound has two components, and how a branch combines them

At a branch each component is maximised **separately**, and the total is tracked
alongside. Taking the larger arm's pair whole would bound the total but not each
half, because the losing arm can dominate one component; a certificate claiming
one output token once admitted an execution producing twenty. The invariant is
`total <= guaranteed + estimated`, and the gap is the price of a faithful split.



The output component uses each declared `max_tokens` cap; honoring that cap is
an execution contract. The input component uses `ceil(UTF8_bytes / d)` for
literal/template fragments and declared argument bounds. The compatibility
option `--chars-per-token` supplies `d` (default 4); it divides UTF-8 bytes,
not Unicode characters.

The required premise is a **complete modeled request-accounting bound**:
all charged input, including any envelope, framing and tokenizer boundary
effects, must fit within the additive estimate. Even `d=1` alone does not prove
that premise for a real provider. The offline mock implements this additive
fragment accounting; no provider serializer or tokenizer is verified.

A generated result retains its producing provider/model token unit. Reuse as
an input to a different provider/model identity is rejected with `E267`.
Different caps on the same model are compatible. External input bounds are
assumed to be in the target unit. No conversion contract is implemented.

A finite monetary figure can be derived from declared `cost_per_token` values.
It is nominal metadata, not an external invoice guarantee or a floating-point
money theorem. Invalid or unrepresentable price calculations are diagnosed.

### The relational obligation on secret-guarded branches

Equal certified maxima do not establish equal actual usage. A secret can select
between differently sized public inputs whose declarations have equal bounds.
Numeric relational and probabilistic resource analyses exist; this compiler
implements a conservative structural sufficient condition.

Its ordered signature contains:

- resolved model contracts `(provider, actual model ID, output cap, price)`;
- exact decoded template bytes, not template token estimates;
- ordered exact literals, lexically resolved outer-value identities, or
  references to earlier aligned call results;
- public choices with resolved guard identities/operators/limits; and
- bounded retries with their bound and body signature.

Source aliases and result variable spellings are not model/request identity.
Shadowed declarations are distinct; relabelling aliases preserve value identity.
Corresponding secret alternatives align their earlier result positions, including
nested branch/retry spans. A secret-data guard requires equal defined arm
signatures (`E236`). A public-data guard retains its choice node, including when
it occurs under secret control; the enclosing comparison must still match it.

The conditional claim uses two runs with equal public values, no confidentiality
declassification, and a shared complete outcome oracle `Omega(M,k,Q)` plus
matched retry-success schedule. Equal model contract `M`, contract ordinal `k`
and modeled request `Q` give equal results and usage. Matched first calls then
make result-dependent second calls match. This establishes modeled ordered
invocation and per-contract usage equality under that coupling. Independently
sampled provider responses need not be equal.

The default mock keys outcomes by workflow, seed, contract and ordinal. The
optional `--request-sensitive-oracle` also uses template/literal bytes and
identifier `(tokens,flag)` values. It probes an abstract request projection,
not real response text. The observer sees per-contract call/input/output usage;
timing and provider invoices are outside this claim.

Different outer values, different same-estimate literals, renamed template
placeholders and equivalent guards may be rejected. The rule is sufficient and
incomplete. `declassify` causes certificate v3 to withhold the unrestricted
whole-workflow billing claim even when local structural obligations discharge.
See [FORMAL_CONTRACT.md](FORMAL_CONTRACT.md) for the full assumptions and proof
sketch.

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
| `P007` | A model price must be finite and representable |
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
| `E268` | A derived monetary bound is not finite/representable |
| `E267` | A generated-value bound cannot be reused across provider/model token units |
| `R002` | A runtime pin is unknown, mistyped, or outside its declared bound |
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

`orchc certify file.orch` emits certificate v3 after semantic, cost and
relational checks. It contains a source SHA-256, output/input/total bounds,
explicit accounting assumptions, source-located derivation steps, resolved call
contracts/templates/ordered arguments, effective labels, reclassification reasons,
sinks and local relational obligations. A workflow-level security-contract field
records whether declassification prevents the billing claim.

`audit/certificate_audit.py` can independently parse the source, recompute costs,
and compare all issued request-cost facts and derivation steps. Its envelope
records source and compiler hashes. It does not independently validate types,
IFC labels, relational proofs, external contracts or justification truth.

Normal `run` and direct interpreter execution require all analyses to pass.
`--audit-unsafe` explicitly bypasses cost/relational rejection for offline
counterexample research; semantic analysis and runtime input checks remain.
`run --json` reports source-located decisions, attempts and per-contract usage.
A runtime pin cannot exceed a declared bound or name an undeclared input.

## Scope and limitations

The compiler is offline and makes no model requests. The following are outside
what it claims:

- Nothing is proven about what a model *says*, only about where its output may
  flow and how much of it there can be.
- Input bounds require complete request accounting and compatible declared token
  units at every divisor. No setting alone verifies a physical tokenizer.
- The monetary figure is derived from declared prices and is not a billing
  guarantee.
- Declassification and endorsement are trusted. The compiler records them and
  makes them visible; it does not verify that a justification is true.
- `retry` models bounded repetition. There is no general loop, no recursion, and
  no arithmetic, so the cost algebra stays decidable.
