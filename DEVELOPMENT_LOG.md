# Development Log

## 2026-09-16

- Inspected the assigned workspace with `rg --files` before editing. No existing OrchLang source tree, Phase 1 source files, or project-instruction PDF was present in this workspace.
- Reviewed the supplied Compiler Design master-plan document as background only. The implemented scope follows the separate user request: a hand-written C++17 compiler rather than the document's planned Flex/Bison approach.
- Created the `orchlang/` C++17 project with lexer, recursive-descent parser, diagnostics, owned AST, symbol table, semantic analyzer, workflow IR, CLI, Makefile, examples, tests, and review documents.
- Built the compiler with `-std=c++17 -Wall -Wextra -pedantic`; the initial strict build completed without warnings.
- Added three valid workflows, nine invalid workflows, and three boundary cases. Each invalid file includes a comment describing its expected diagnostic family.
- Added and ran 45 assertion-based tests. The completed initial regression run reported `Passed 45/45 tests.`
- Ran `make check`, which reran the 45-test suite, accepted the valid corpus, and confirmed invalid inputs returned unsuccessful status.
- Added Review 2 documentation and prepared the exact command sequence for the live demonstration.
- Generated the required `review_evidence/` text files by redirecting output from actual build, test, token, AST, symbol-table, IR, lexical-error, syntax-error, semantic-error, and multi-error compiler commands.
- Ran `make sanitize` with AddressSanitizer and UndefinedBehaviorSanitizer. All 45 tests and the example corpus completed without sanitizer findings.
- Rebuilt normally with `make clean && make check`, ran every command in `docs/REVIEW_DEMO.md`, verified valid commands returned 0, verified invalid examples returned non-zero, and confirmed missing-file and usage errors return status 2.
- Searched the project for `TODO`, `FIXME`, fake-output markers, placeholder implementation markers, raw `new` allocations, and inconsistent project naming. No such implementation-quality markers were found.
