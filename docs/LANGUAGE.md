# OrchLang language reference (v2)

```ebnf
program   ::= "workflow" IDENT "{" item* "}"
item      ::= input | model | prompt | tool | stmt | "output" IDENT ";"
input     ::= "input" IDENT ":" "text" ("secret" | "public") "max_tokens" INT ";"
model     ::= "model" IDENT "=" STRING ";"                      (key into models.json)
prompt    ::= "prompt" IDENT "(" params? ")" "=" (ROLE STRING)+ ";"   ROLE ::= system | user | assistant
tool      ::= "tool" IDENT "(" params? ")" "max_tokens" INT ";"  (pure function from orchlang/tools.py)
stmt      ::= "let" IDENT "=" "call" IDENT "(" args? ")" "using" IDENT "max_tokens" INT ";"
            | "let" IDENT "=" "tool" IDENT "(" args? ")" ";"
            | "let" IDENT "=" STRING ";"
            | "if" cond block ("else" (stmt_if | block))?
            | "repeat" INT "until" cond block
cond      ::= IDENT "==" STRING | IDENT "startswith" STRING
args      ::= arg ("," arg)*          arg ::= IDENT | STRING
```

Prompt messages use `{param}` placeholders; every parameter must be used. Variables
are global to the workflow and initially empty. `repeat n until c` checks `c` before
each iteration and runs at most `n` iterations.

## Labels

Secret inputs are `H`. A variable assigned by a call or tool under program counter
`pc` from arguments with label `l` receives at least `pc ⊔ l`; branches and loops
raise `pc` by their guard's label. Prompts may contain secrets: the model is trusted
with content. What the compiler tracks is whether a call's **usage** can depend on a
secret.

## Diagnostics

| Code | Meaning |
|---|---|
| L001, L003 | unexpected character, unsupported escape |
| P001, P002, P005 | syntax error, prompt without messages, loop bound < 1 |
| E201, E202 | duplicate declaration, use before definition |
| E220, E221, E222 | unknown prompt, arity mismatch, placeholder/parameter mismatch |
| E241, E242, E243 | unknown model, unknown tool, tool arity mismatch |
| E270, E271 | missing or duplicate output |

## Leak findings

| Kind | Meaning |
|---|---|
| `secret-dependent-size` | a call's request contains secret-derived text |
| `secret-context-call` | a call runs under a secret branch or loop |
| `secret-dependent-branch` | a secret guard selects arms with different usage |
| `secret-dependent-loop` | a loop's iteration count depends on a secret |

## Shaping strategies

| Strategy | Pads | Secret branches | Notes |
|---|---|---|---|
| `ours` | calls with secret request or under secret control | minimum-cost common supersequence with dummies | default |
| `padall` | every call | as `ours` | no taint guidance |
| `naive` | as `ours` | every arm also runs every other arm's calls as dummies | secure multi-execution |
| `uniform` | as `ours`, but every call of a model uses one global (T, N) | as `ours` | fixed-size cells |

All four are validated by the Lean checker before execution.
