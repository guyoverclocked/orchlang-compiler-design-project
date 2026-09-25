# OrchLang Language Specification

This is the reference for the language as implemented (analysis version
`orchlang-4`). `docs/FORMAL_MODEL.md` states and proves what the analyses
guarantee; this document says what the compiler accepts and checks.

## Purpose

OrchLang describes LLM workflows that can be checked completely before anything
runs. Without contacting a model, reading a key, or touching a network, the
compiler answers:

1. **What is the most this workflow can cost?** A worst-case bound on output
   tokens, and on input tokens both as an estimate and, where the tokenizers
   allow it, as a guarantee.
2. **Where can data go?** Whether secret content can reach a prompt, an output
   or an effect, and whether untrusted data can drive an effect.
3. **What do the requests reveal?** Whether the requests the workflow sends, and
   therefore anything computed from them (the bill, the per-provider traffic,
   the transcript), are independent of its secrets; and if not, how many bits
   they can reveal at most.

All three are written into a certificate the compiler emits as JSON.

## Design commitments

**The shape of a workflow is fixed before it runs.** Repetition is `retry n`
with a literal `n`; a branch reads a declared value; inputs are declared at the
top of the workflow. There is no general loop, no recursion, no string
operation and no arithmetic. This is what makes the cost bound finite and the
relational analysis decidable, and it is also the language's main limitation:
an agent whose model decides what runs next cannot be written in it
(`bench/real/EXCLUSIONS.md`).

**Lengths the compiler cannot see must be declared, in a stated unit.** An
input's length is not knowable from the source. It is declared in bytes
(`max_bytes`), or in tokens of a named tokenizer (`max_tokens N tokenizer T`),
or, for the estimate only, in tokens with no tokenizer. Token counts are
tokenizer-relative and do not add up under concatenation; bytes do. The
guaranteed bound is therefore built from bytes (§Cost bound).

**Leaving the lattice requires saying why.** `declassify` and `endorse` are the
only ways to relax a label, each with a written justification carried into the
certificate.

## Tokens

| Category | Accepted forms |
| --- | --- |
| Structure | `workflow`, `budget` |
| Declarations | `input`, `secret`, `model`, `mock`, `max_tokens`, `cost_per_token`, `prompt`, `tool` |
| Statements | `let`, `call`, `using`, `require`, `tokens`, `output`, `emit`, `if`, `else`, `retry` |
| Security | `untrusted`, `declassify`, `endorse`, `as`, `because` |
| Contextual words | `tokenizer`, `max_bytes`, `overhead` (declarations); `leaks`, `observer` (workflow header) |
| Types | `text`, `integer`, `decimal`, `boolean`, `json` |
| Identifiers | Letter or `_`, followed by letters, digits, or `_` |
| Literals | Quoted strings, integer literals, decimal literals, `true`, `false` |
| Delimiters | `{`, `}`, `(`, `)`, `:`, `;`, `,`, `->` |
| Operators | `=`, `<`, `<=`, `>`, `>=`, `==`, `!=` |
| Comments | `//` to the end of a line |

Contextual words are identifiers everywhere except in the position shown, so
existing programs that use them as names still parse.

Strings support `\n`, `\t`, `\"` and `\\`. In a prompt template, `{name}` is a
placeholder and `{{` and `}}` are a literal brace, as in Python format strings
and LangChain templates, so a real prompt containing JSON or code can be
written verbatim. The lexer reports `L001` for unexpected characters, `L002`
for unterminated strings, and `L003` for unsupported escapes.

## Grammar

```ebnf
program          ::= workflowDecl* EOF
workflowDecl     ::= "workflow" IDENT "budget" INTEGER workflowOption* block
workflowOption   ::= "leaks" NUMBER
                   | "observer" ("trace" | "provider" | "bill")
block            ::= "{" statement* "}"
statement        ::= inputDecl | secretDecl | modelDecl | promptDecl | toolDecl
                   | letStmt | requireStmt | emitStmt | ifStmt | retryStmt
                   | reclassifyStmt | outputStmt

inputDecl        ::= "input" IDENT ":" type "untrusted"? lengthClause* ";"
secretDecl       ::= "secret" IDENT (":" type)? lengthClause* ";"
lengthClause     ::= "max_tokens" INTEGER | "tokenizer" IDENT | "max_bytes" INTEGER
modelDecl        ::= "model" IDENT "=" "mock" "(" STRING ")" "max_tokens" INTEGER
                     modelOption* ";"
modelOption      ::= "cost_per_token" NUMBER | "tokenizer" IDENT
                   | "overhead" INTEGER | "max_bytes" INTEGER
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

The parser uses one-token lookahead and synchronises at a semicolon, a closing
brace, or the next statement keyword, so independent errors are reported
together.

**Scopes and bindings.** Each block is its own scope; a binding made in a branch
arm or a retry body does not escape it. Every declaration receives a unique
binding identity, and every later analysis refers to bindings, models and
prompts by identity, never by name, so a redeclaration inside an arm is a
different binding. Inputs and secrets may be declared only at the top level of
a workflow (`E203`): an input declared inside an arm would have no single
meaning for the environment that supplies it.

**Models.** `mock("provider/model")` names the endpoint; the part before the
first `/` is the provider. A model's identity for every analysis is its
provider, model name, `max_tokens` and byte cap. `tokenizer T` names the
tokenizer the provider bills its input with; `overhead k` bounds the tokens the
provider's request envelope adds (chat formatting, tool schemas it renders);
`max_bytes b` is a client-side cap on the bytes of a response.

## Security labels

Every value carries a label from the product lattice

```
L  =  Confidentiality × Integrity  =  {Public ≤ Secret} × {Trusted ≤ Untrusted}
```

and, separately, a **data label**: what its *content* depends on, as opposed to
the program counter under which it was computed.

| Construct | Label | Data label |
| --- | --- | --- |
| `input x: T;` | `Public/Trusted` | same |
| `input x: T untrusted;` | `Public/Untrusted` | same |
| `secret S: T;` | `Secret/Trusted` | same |
| literal | `Public/Trusted` | same |
| `let y = call p(a…) using m;` | `pc ⊔ ⨆ label(aᵢ)` | confidentiality: `⨆ data(aᵢ)`; integrity: `pc ⊔ ⨆ data(aᵢ)` |
| `declassify(x) as y` | confidentiality lowered to `Public` | same |
| `endorse(x) as y` | integrity raised to `Trusted` | same |

**Why two labels.** A model call made inside a secret-guarded arm from public
arguments produces public *content*; only the fact that it was made depends on
the secret, and that fact is exactly what the relational analysis accounts for.
So a prompt may receive such a value (`E230` checks the data label), and a
chain of calls inside a secret arm is allowed. Outputs and effects are still
checked against the program counter as well (`E231`, `E232`, `E234`), because
whether they happen is observable. The integrity data label, by contrast,
includes the program counter: a value computed inside an arm guarded by
untrusted data is itself untrusted. That is conservative, and the real-workflow
corpus shows where it over-reports (`bench/real/PROTOCOL.md`, D5).

**Injection propagation.** A model's answer is labelled with the join of
everything that reached its prompt, so text from a retrieved page cannot become
an argument of an effect, however many model calls sit between the page and the
effect, unless someone endorses it and writes down why.

**Sinks.** `emit` is the only construct with an outward effect: its arguments
must be `Public/Trusted`, and so must `pc`. `output` may return untrusted data
(the caller receives data, not an instruction) but not secret data.

## Cost bound

The bound is derived by structural induction over a workflow body, with sum for
sequencing, the componentwise maximum of the two arms for a branch, and `n`
times the body for `retry n`. Arithmetic saturates; a saturated bound is
rejected (`E266`). Each component is maximised separately at a branch, and the
certificate checks the total against the budget (`E260`).

A call `let y = call p(a…) using m` contributes three components.

**Output tokens: `max_tokens(m)`.** Providers enforce the cap themselves, so
this holds with no assumption about tokenization.

**Estimated input tokens.** The template and literal arguments at
`--chars-per-token` (default 4) bytes per token, plus each variable argument's
declared or derived token bound. This is an estimate, not a bound: it is
exceeded on most non-English text by every real tokenizer measured
(`bench/results/tokenizers.json`).

**Guaranteed input tokens.** `κ_T · bytes(request) + σ_T + overhead(m)`, where
`bytes(request)` is the template's bytes plus each argument's byte bound, and
`(κ_T, σ_T)` is the contract of the model's tokenizer `T`:
`tokens_T(s) ≤ κ_T · bytes(s) + σ_T` for every string `s`. Bytes add up under
concatenation and do not depend on the tokenizer; token counts do neither, which
is why the bound is computed in bytes and converted once per request. An
argument's byte bound is

* for a literal, its bytes;
* for an input or secret, its `max_bytes`, or `λ_T · N` for `max_tokens N
  tokenizer T` with `T` lossless, where `λ_T` is the most bytes one token of
  `T` decodes to;
* for a response of model `m'`, `λ_{T'} · max_tokens(m')` for its tokenizer
  `T'`, or its `max_bytes` cap if declared, whichever is smaller.

The contracts are generated from measurements by
`bench/tokenizers/contracts.py` into `src/tokenizer_contracts.cpp`. A tokenizer
with no structural contract (T5, XLM-R, whose normalisers can emit many more
tokens than bytes) is known but unverified: naming it is allowed, with a
warning (`W267`), and the guaranteed bound for calls through it is undefined.
If any call's model names no tokenizer, or any argument has no byte bound, the
certificate says the guaranteed input bound is undefined and why.

`cost_per_token` gives a monetary figure, which is reported, not certified.

**Requirements.** `require tokens(x) op n` is discharged against the derived
bound of `x` over every value `x` can take. An upper bound can discharge `<` and
`<=`; `>=` only against zero; `>`, `==` and `!=` are reported as undecidable
(`E264`) rather than accepted.

## The relational analysis

A branch whose guard depends on a secret can leak it with no value crossing a
boundary: if the arms send different requests, anyone who sees the requests, or
anything computed from them, can tell which arm ran.

**Request signatures.** The compiler abstracts each region of the workflow to a
signature: a sequence of `Call(model, pieces)`, `Retry(n, signature)` and
`Branch(guard, signature, signature)` nodes. A call's pieces are the request's
text as sent: template and literal text (adjacent text merged), a binding made
outside the region (by identity), or the response of an earlier call in the
region (by position). A branch on a public guard is kept whole. A branch whose
guard reads secret content is *resolved*: for each vector of outcomes of the
secret guard predicates that some secret values realise, the selected arm is
inlined. The number of distinct signatures over these feasible outcome
vectors, `k`, is the number of classes of secrets the observer can
distinguish, and the workflow reveals at most `log2 k` bits (min-capacity; for
any number of invocations, with adaptively chosen public inputs).

Equal signatures mean identical requests, so the analysis needs no assumption
about tokenizers or about how a provider answers. Comparing request *sizes*
instead, as an earlier version did, is unsound for content-dependent providers
and real tokenizers (`docs/AUDIT_2026-09-25.md`), and `docs/FORMAL_MODEL.md`
Theorem 6 shows no size-based comparison can be both sound and useful.

**Observers.** The workflow header chooses who is watching:

| `observer` | Sees | Signatures are compared |
|---|---|---|
| `trace` (default) | every request and response, in order | exactly |
| `provider` | each provider's own requests, in order | after stably sorting independent calls by provider |
| `bill` | per model: calls and token totals | after sorting independent calls by request |

Calls inside a retry body are never reordered: a retry's success can depend on
the order of its transcript.

**Leakage budget.** `leaks b` allows up to `b` bits; the default is 0. A
workflow whose `k` exceeds `2^b` is rejected (`E236`, which names each
branch whose arms differ and what differs). One that leaks within its budget is
accepted with `W238`, and the certificate records `k` and the bits.

A rejection is justified relative to the class of all providers except when the
difference sits under a public guard that can never go the relevant way.

**Spend influence.** `W237` warns when a branch guarded by untrusted data has
arms whose bounds differ: an injected value chooses how much the workflow
spends. It is reported, not rejected.

## Diagnostics

| Code | Rule |
| --- | --- |
| `L001`–`L003` | Unexpected character, unterminated string, unsupported escape |
| `P001`, `P004` | Unexpected token; malformed integer literal |
| `P005` | `retry` requires a bound of at least 1 |
| `P006` | A reclassification justification may not be empty |
| `P007` | Unknown observer in a workflow header |
| `E201` | A declaration name may appear only once in its scope |
| `E202` | Identifiers must be declared before use |
| `E203` | Inputs and secrets may be declared only at the top level of a workflow |
| `E210` | A `let` result type must match the called prompt's return type |
| `E211` | An `if` condition naming an identifier must be boolean |
| `E212` | A reclassification must preserve the value's type |
| `E220` | A `let` call must name a declared prompt |
| `E221` | Call arity must match the prompt's parameter count |
| `E222` | Every placeholder must name one declared parameter exactly once; a lone brace is an error (write `{{` or `}}`) |
| `E223` | Argument types must match parameter types |
| `E230` | Secret content may not be passed to a prompt |
| `E231` | A secret, or a value computed under a secret guard, may not be the workflow output |
| `E232` | A secret, or a value computed under a secret guard, may not reach a tool |
| `E233` | An untrusted value may not reach a tool |
| `E234` | An effect may not be guarded by a secret condition |
| `E235` | An effect may not be guarded by an untrusted condition |
| `W236` | A reclassification that changes nothing (warning) |
| `E236` | The requests the workflow sends reveal more about its secrets than its leakage budget allows |
| `W237` | An untrusted-guarded branch whose arms bound differently (warning) |
| `W238` | The workflow reveals some information about its secrets, within its budget (warning) |
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
| `E267` | An unknown tokenizer, or `tokenizer` without a `max_tokens` bound to give a unit to |
| `W267` | A tokenizer with no verified byte contract: the input bound through it is an estimate |
| `E270` | A workflow must declare one output |
| `E271` | A workflow may not declare more than one output |

## Worked example

```orchlang
workflow ResearchDigest budget 1000000 {
  input query: text max_bytes 400;
  input web_page: text untrusted max_bytes 4000;
  model reader = mock("openai/gpt-4o-mini") max_tokens 500 tokenizer o200k_base overhead 9;
  tool publish(body: text);

  prompt digest(page: text) -> text = "Summarise the retrieved page: {page}";

  let digest_text: text = call digest(web_page) using reader;
  endorse(digest_text) as vetted: text because "passed the offline schema and length validator";
  emit publish(vetted);

  output query;
}
```

`web_page` is untrusted, so `digest_text` is untrusted, so
`emit publish(digest_text)` would be rejected with `E233`; the endorsement
permits the effect and is recorded in the certificate. The output bound is 500
tokens; the guaranteed input bound is `1 · (30 + 4000) + 0 + 9 = 4039` tokens
under the `o200k_base` contract (`κ = 1`, `σ = 0`).

## Certificate

`orchc certify file.orch` emits JSON (format version 2) binding the result to
the source by SHA-256 and to the analysis version, with: the output bound, the
estimated and guaranteed input bounds (or the reason the guaranteed one is
undefined), the tokenization assumption of the estimate, the derivation, the
final label of every binding, every reclassification with its justification,
every sink cleared, the relational rule used, and for each workflow the
observer, the number of distinguishable classes `k`, the bits, and the budget.

The certificate is a report, not a proof object: nothing yet re-checks it
independently of the compiler.

## Scope and limitations

* Nothing is proven about what a model *says*, only about where its output may
  flow, how much of it there can be, and what the requests reveal.
* The guaranteed input bound rests on the tokenizer contracts, on `overhead`
  covering the provider's envelope, and on `λ` bounding a response's bytes;
  `docs/FORMAL_MODEL.md` §7 states each assumption. The estimate rests on
  nothing and is reported as such.
* The relational guarantee is about distributions under independent sampling
  per call. It excludes timing, observers who see more than the requests and
  responses, and providers whose randomness is correlated with the secret by a
  channel outside the program.
* Declassification is all or nothing: a value declassified to reach one
  provider is public to every observer.
* Declassification and endorsement are trusted, not verified.
* `retry` cannot carry information from one attempt to the next, so
  self-correction loops that feed back earlier attempts must be unrolled.
