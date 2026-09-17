# OrchLang Language Specification

## Purpose

OrchLang describes compact LLM workflow declarations that can be checked without network access. The current compiler accepts a deliberately small grammar so the lexical, parsing, AST, symbol-table, semantic-analysis, and IR stages are easy to demonstrate.

## Tokens

| Category | Accepted forms |
| --- | --- |
| Workflow keywords | `workflow`, `budget`, `input`, `secret`, `model`, `mock`, `max_tokens`, `prompt`, `let`, `call`, `using`, `require`, `tokens`, `output` |
| Types | `text`, `integer`, `decimal`, `boolean`, `json` |
| Identifiers | Letter or `_`, followed by letters, digits, or `_` |
| Literals | Quoted strings, integer literals, decimal literals, `true`, `false` |
| Delimiters | `{`, `}`, `(`, `)`, `:`, `;`, `,`, `->` |
| Operators | `=`, `<`, `<=`, `>`, `>=`, `==`, `!=` |
| Comments | `//` to the end of a line |

Strings support `\n`, `\t`, `\"`, and `\\`. The lexer records the first line and column of every token. It reports `L001` for unexpected characters, `L002` for unterminated strings, and `L003` for unsupported string escapes.

## Grammar

```ebnf
program          ::= workflowDecl* EOF
workflowDecl     ::= "workflow" IDENT "budget" INTEGER "{" statement* "}"
statement        ::= inputDecl | secretDecl | modelDecl | promptDecl
                   | letStmt | requireStmt | outputStmt
inputDecl        ::= "input" IDENT ":" type ";"
secretDecl       ::= "secret" IDENT ";"
modelDecl        ::= "model" IDENT "=" "mock" "(" STRING ")" "max_tokens" INTEGER ";"
promptDecl       ::= "prompt" IDENT "(" parameters? ")" "->" type "=" STRING ";"
parameters       ::= parameter ("," parameter)*
parameter        ::= IDENT ":" type
letStmt          ::= "let" IDENT ":" type "=" callExpr ";"
callExpr         ::= "call" IDENT "(" arguments? ")" "using" IDENT
arguments        ::= expression ("," expression)*
requireStmt      ::= "require" "tokens" "(" IDENT ")" comparison INTEGER ";"
outputStmt       ::= "output" expression ";"
expression       ::= IDENT | STRING | INTEGER | DECIMAL | BOOLEAN
type             ::= "text" | "integer" | "decimal" | "boolean" | "json"
comparison       ::= "<" | "<=" | ">" | ">=" | "==" | "!="
```

The parser uses one-token lookahead. On a malformed statement it synchronizes at a semicolon, a closing brace, or the next statement keyword so that independent errors can be reported together.

## Valid program

```orchlang
workflow SupportTriage budget 2500 {
  input ticket: text;
  secret API_KEY;
  model fast = mock("local-small") max_tokens 600;

  prompt classify(message: text) -> text =
      "Classify the ticket as billing, technical, or other: {message}";

  let category: text = call classify(ticket) using fast;
  require tokens(category) <= 600;
  output category;
}
```

## Invalid examples

| File | Main diagnostics demonstrated |
| --- | --- |
| `examples/invalid/lexical_errors.orch` | Unexpected character |
| `examples/invalid/syntax_errors.orch` | Missing statement delimiter |
| `examples/invalid/duplicate_symbols.orch` | Duplicate declaration |
| `examples/invalid/unknown_names.orch` | Unknown variable, prompt, and model |
| `examples/invalid/type_mismatch.orch` | Prompt result and declared result type mismatch |
| `examples/invalid/placeholder_errors.orch` | Unknown, duplicate, and missing template placeholders |
| `examples/invalid/secret_exposure.orch` | Secret passed to a prompt and exposed as output |
| `examples/invalid/budget_exceeded.orch` | Declared model-call bound exceeds budget |
| `examples/invalid/multiple_errors.orch` | Several independent semantic errors from one run |

## Semantic rules

The compiler performs sequential declaration checking within each workflow scope. A prompt's parameters occupy a child scope and are retained in the prompt signature for call checking.

| Code | Rule |
| --- | --- |
| `E201` | A declaration name may appear only once in its scope. |
| `E202` | Identifiers used in calls, requirements, or outputs must be declared earlier. |
| `E210` | A `let` result type must match the called prompt's return type. |
| `E220` | A `let` call must name a previously declared prompt. |
| `E221` | The number of call arguments must equal the prompt parameter count. |
| `E222` | Every template placeholder must name one declared parameter exactly once. |
| `E223` | Each supplied argument type must match its corresponding parameter type. |
| `E230` | A secret cannot be passed directly to a prompt or selected as workflow output. |
| `E241` | The model in a `using` clause must be a declared model. |
| `E250` | The lowered IR must not contain a dependency cycle. |
| `E260` | Sum of selected model `max_tokens` values must not exceed the workflow budget. |
| `E270` | A workflow must declare one output. |
| `E271` | A workflow may not declare more than one output. |

### Budget rule

For Review 2, each syntactic model call contributes the selected model declaration's `max_tokens`. The compiler sums those declared limits and compares the total against `budget`. This is a conservative static bound only; it does not estimate provider billing, prompt tokens, runtime retries, or actual model consumption.

### IR rule

After semantic success, the compiler lowers declarations, calls, requirements, and output into numbered IR nodes. A call depends on its prompt, selected model, and identifier arguments. The lowerer calls a generic depth-first dependency-cycle detector even though declaration-before-use normally prevents cycles in the current grammar.
