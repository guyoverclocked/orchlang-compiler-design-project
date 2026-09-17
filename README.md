# OrchLang

## A Statically Typed Domain Specific Language Compiler for Safe and Cost Aware LLM Workflows

**Student:** Nambi Rajan M  
**Registration number:** 24BAI0072

OrchLang is an offline, educational compiler project for describing small LLM-oriented workflows. It accepts typed inputs, secrets, offline mock-model declarations, prompt templates, model calls, token requirements, and one output. The compiler detects workflow mistakes before any model request could run. It never contacts a network service, reads an API key, or requires a database.

This review build implements the Phase 1 front end and the core Phase 2 analysis pipeline in hand-written C++17. It does not use Flex, Bison, ANTLR, or an external parsing framework.

## Implemented compiler phases

Phase 1 functionality:

- Location-aware hand-written lexer with line comments, strings, numeric literals, keywords, and structured lexical diagnostics.
- One-token-lookahead recursive-descent parser for all statement forms used in the supplied Phase 1 syntax.
- Statement-level parser recovery at semicolons, closing braces, and the next statement keyword.
- Token printing, diagnostic printing, valid/invalid examples, and a command-line compiler named `orchc`.

Phase 2 functionality:

- Owned AST using `std::unique_ptr`; no raw owning pointers or global mutable compiler state.
- Printable symbol table with kinds, types, scopes, locations, model metadata, and prompt signatures.
- Semantic checks for duplicate names, undeclared names, types, prompt arity and argument types, prompt placeholders, secret exposure, models, declared budgets, and outputs.
- Typed workflow IR with dependencies, a textual viewer, a JSON viewer, and a defensive dependency-cycle detector.
- 45 automated tests covering lexer, parser, AST, symbols, semantics, IR lowering, and recovery behavior. The first 18 lexer/parser checks provide more than the 12 Phase 1 smoke cases required for this review build.

## Repository structure

```text
orchlang/
  include/                 Public compiler data structures and module interfaces
  src/                     Lexer, parser, AST, symbols, semantics, IR, and CLI
  tests/tests.cpp          Standalone 45-test regression executable
  examples/                Valid, invalid, and boundary OrchLang programs
  docs/                    Language specification and review materials
  scripts/demo.sh          Rehearsal command sequence
  review_evidence/         Outputs generated from actual compiler commands
  Makefile                 C++17 build, tests, example checks, and sanitizer target
```

## Build and test

From this directory:

```sh
make clean
make check
```

`make check` builds the compiler with `-std=c++17 -Wall -Wextra -pedantic`, runs all 45 assertions, accepts every valid example, and confirms that every invalid/boundary-invalid example exits unsuccessfully.

For an optional memory/undefined-behavior check on a toolchain that supports sanitizers:

```sh
make sanitize
```

Rebuild normally with `make clean && make check` after the sanitizer run.

## Command-line use

```sh
./orchc tokens examples/valid/support_triage.orch
./orchc check examples/valid/support_triage.orch
./orchc ast examples/valid/support_triage.orch
./orchc symbols examples/valid/support_triage.orch
./orchc ir examples/valid/support_triage.orch
./orchc ir-json examples/valid/support_triage.orch
```

The compatibility forms `./orchc --tokens file.orch`, `./orchc --check file.orch`, and `./orchc file.orch` are also accepted. Valid source returns status 0. Lexical, syntax, or semantic errors return status 1. Missing files and bad usage return status 2.

For example, `check` on the supplied triage workflow reports:

```text
Check succeeded: 1 workflow(s) passed lexical, syntax, and semantic analysis.
  SupportTriage: declared token bound 600 / budget 2500
```

## Review examples

- `examples/valid/` contains three semantically valid workflows.
- `examples/invalid/` contains separate demonstrations of lexical, syntax, duplicate-name, unknown-name, type, placeholder, secret-flow, budget, and multi-error diagnostics.
- `examples/boundary/` contains empty-workflow, zero-budget, and long-identifier cases.

## Known limitations

This review build intentionally stops after the required Phase 2 compiler work. It does not generate Python, run a mock model, optimize IR, call a live provider, implement conditionals, or support arithmetic expressions. The budget check is a conservative declared upper bound: it adds each selected model's `max_tokens`; it does not predict actual API cost or exact token usage.

## Future work

The isolated Phase 3 candidates are an optimizer, readable offline Python generation, a deterministic mock runtime, and end-to-end execution of generated workflows. These are not represented as implemented in this repository.
