# OrchLang Review 2 Progress Report

**Student:** Nambi Rajan M  
**Registration number:** 24BAI0072  
**Project:** OrchLang A Statically Typed Domain Specific Language Compiler for Safe and Cost Aware LLM Workflows

## Current status

The Review 2 build is complete for the implemented Phase 1 and Phase 2 scope. It builds offline with standard C++17 and demonstrates a lexer, recursive-descent parser, owned AST, scoped symbol table, semantic analysis, workflow IR, and automated tests. No live LLM provider, API key, database, network connection, or external compiler generator is used.

No pre-existing OrchLang source repository was present in the supplied workspace. The review build therefore implements the stated Phase 1 compatibility surface directly rather than claiming to preserve unavailable source files.

## Phase 1 functionality in the build

- Hand-written lexer recognizes the required workflow vocabulary, primitive types, strings, numbers, comments, operators, and delimiters.
- Tokens retain source line and column locations and can be printed with `orchc tokens`.
- A hand-written one-token-lookahead recursive-descent parser recognizes inputs, secrets, models, prompts, model calls, requirements, and output statements.
- The parser reports structured syntax errors and performs statement-level recovery.
- The command-line compiler supports check and token views, valid examples, invalid examples, and a one-command test path.

## Phase 2 modules completed

| Module | Completed evidence |
| --- | --- |
| Owned AST | `ast.hpp`, `ast.cpp`, parser construction actions, `orchc ast` |
| Symbol table | `symbol_table.hpp`, `symbol_table.cpp`, `orchc symbols` |
| Semantic analysis | `semantic_analyzer.hpp`, `semantic_analyzer.cpp`, stable diagnostic codes |
| Workflow IR | `ir.hpp`, `ir.cpp`, `orchc ir`, `orchc ir-json` |
| Tests | `tests/tests.cpp`, 45 passing assertions through `make check` |
| Examples and evidence | `examples/` and `review_evidence/` |

## Architecture

```text
source .orch
  -> Lexer and L001-L003 diagnostics
  -> Recursive-descent parser and P001/P004 diagnostics
  -> Owned AST
  -> Symbol table and semantic checks E201-E271
  -> Validated workflow IR and cycle detector
  -> Text or JSON inspection output
```

Each stage has an explicit C++ data type and can be observed through the command line. The semantic analyzer is separate from parsing, allowing syntax errors to be handled before name and type analysis begins.

## Compiler concepts demonstrated

- Lexical analysis: maximal identifier scanning, recognized keywords, string escape handling, numeric tokens, and location tracking.
- Syntax analysis: a compact context-free grammar, one-token lookahead, expected-token diagnostics, and synchronization after errors.
- AST construction: RAII ownership with `std::unique_ptr`; no raw owning pointers.
- Symbol tables: top-level workflow scopes plus child prompt-parameter scopes, lookup, insertion, duplicate detection, types, and metadata.
- Semantic analysis: names, prompt signatures, argument types, prompt templates, secret flow, declared token budgets, and output rules.
- Intermediate representation: explicit dependency edges and a depth-first cycle safety check.

## Tests and results

The test executable contains 45 assertions. The completed `make check` result is `Passed 45/45 tests.` It also verifies all three valid workflows, the valid zero-budget and long-identifier boundaries, every invalid example, and the intentionally invalid empty-workflow boundary.

The required strict build flags are active: `-std=c++17 -Wall -Wextra -pedantic`. The ordinary build reported no compiler warnings during the final clean build.

## Technical challenges and resolutions

| Challenge | Resolution |
| --- | --- |
| Recover after malformed statements without looping | The parser always advances or reaches a safe delimiter, closing brace, or next statement keyword. |
| Keep partial source from constructing unsafe AST nodes | Statement parsers return null on incomplete syntax; the workflow retains only fully constructed nodes. |
| Report several semantic faults together | Semantic checks continue when independent information is available, such as checking call arguments and model selection even if the prompt name is invalid. |
| Make the budget rule explainable | The implementation sums declared `max_tokens` values only and labels it a conservative static upper bound. |
| Validate an acyclic IR despite declaration ordering | The lowerer invokes a generic DFS detector and the test suite creates a synthetic cycle to verify it. |

## Current limitations

The current grammar does not implement conditions, arithmetic, nested workflow control flow, or literal JSON values. Phase 3 components are not implemented: no optimizer, Python generator, deterministic mock execution runtime, or live provider adapter is present. The project intentionally does not make any external model call.

## Remaining Phase 3 work

Future work can be isolated from the review build: IR optimization, offline Python generation, deterministic mock execution, and end-to-end generated-workflow tests. None of these are needed to run the demonstrated compiler front end and Phase 2 analysis modules.
