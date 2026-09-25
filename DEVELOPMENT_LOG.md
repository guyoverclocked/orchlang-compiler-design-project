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

## 2026-09-17

Reworked the project from a declarative checker into a language whose type
system certifies two properties, after a prior-art survey established where the
novelty actually lies.

**Prior art.** Surveyed LLM workflow DSLs (LMQL, SGLang, DSPy, APPL, PDL),
static agent verification (Agentproof), information-flow defences (CaMeL,
f-secure, AgentFlow, NeuroTaint, GIF), budget enforcement (the 63-incident
catalogue with its affine-typed Rust mitigation; budget algebras for multi-agent
routing), and classical resource typing (AARA). Two findings shaped the work:
the cost column and the flow column of that table are near-disjoint, and
everything in the flow column is a runtime mechanism. Prompt-template
placeholder checking turned out to be commodity (promptml, promptctl,
type-safe-prompt), so it is explicitly disclaimed rather than claimed.

**Patent assessment.** Concluded against filing. A type system is squarely
within Section 3(k)'s exclusion of a computer programme per se and an algorithm,
and the CRI Guidelines 2025 gate eligibility on technical effect on an
underlying technical system, which a developer-facing static analysis is poorly
placed to show. Ferid Allani confirms there is no absolute bar but took 19
years. Recorded in docs/SUBMISSION_PLAN.md.

**Defects found in the existing build.** `require tokens(x) <= n` was parsed,
lowered into the IR, printed, and never checked: `require tokens(c) <= 5`
against a 600-token model passed. The budget rule ignored input tokens entirely
and summed over syntactic call sites. The secret check was shallow, and the
grammar was too weak for an indirect flow to exist at all.

**Language.** Added `if`/`else` and bounded `retry` so a cost bound is inductive
rather than a sum; `tool` declarations and `emit`, giving the language one
explicit sink; `untrusted` inputs and typed secrets; declared `max_tokens` on
inputs and secrets, so the analysis is defined rather than guessed; and
`declassify`/`endorse` with mandatory written justifications. Each block is its
own scope.

**Analyses.** Information-flow typing over
(Public <= Secret) x (Trusted <= Untrusted), with a program-counter label for
implicit flows and an injection-propagation rule that taints model output
derived from untrusted input transitively. Structural cost analysis separating a
guaranteed component (provider-enforced output caps) from an estimated one
(input tokens, relative to a recorded tokenization assumption). `require` is now
actually discharged, with undecidable comparisons reported rather than accepted.

**The cost channel (E236).** A branch whose guard is secret and whose arms cost
different amounts leaks the guard through the token bill with no value crossing
any boundary. Neither analysis sees it alone. This is the project's most
original result.

**Evaluation.** Built an offline mock runtime so the bound is falsifiable, a
generated benchmark of 23 cost workflows and 26 security workflows in
safe/unsafe pairs, and a harness. The certified bound was not exceeded in 4,600
executions; the flat rule the previous version used is exceeded on 13.5% of them
and unsound on 8 of 23 workflows, every one containing a retry. Median slack
1.23x. Security suite 13/13 and 13/13.

**State.** 83 tests pass, warning-free under -Wall -Wextra -pedantic. Every
command in docs/REVIEW_DEMO.md verified against the built compiler. Paper draft
in docs/PAPER.md; submission strategy in docs/SUBMISSION_PLAN.md.

**Toolchain note.** The local MinGW GCC 6.3 cannot build this (no <optional>).
Installed WinLibs GCC 16.1.0 via winget; any GCC 7+, Clang 5+, or MSVC 2017+
works.

## 2026-09-25

Worked from `docs/AGENT_BRIEF.md`. The full record of findings is
`docs/AUDIT_2026-09-25.md`; the write-up is `docs/PAPER.md`.

**Self-audit.** Billing signatures (compare request sizes) were unsound: real
tokenizers bill equal-size strings differently, a real model (SmolLM2-135M,
run locally) answers equal-length requests at different lengths, and signatures
compared names rather than bindings. The test harness shared the rule's blind
spot, because its mock provider ignored request content. Token counts turned out
not to be subadditive, which also undermined the input half of the unary bound.

**Replacements.** Requests are compared by content, with every secret branch
resolved over the outcome vectors its secret can realise; a workflow may declare
a leakage budget and gets a proved `log2 k` bound. Declarations carry unique
binding identities; inputs and secrets are top-level only (E203). The guaranteed
input bound is computed in bytes and converted through per-tokenizer contracts
generated from measurements on fourteen tokenizers. Content and program-counter
labels are separated for confidentiality (OP-1). Observers `trace`, `provider`
and `bill`; calls inside retry bodies are never reordered (a bug in the first
version of this change, caught before release).

**Theory.** `docs/FORMAL_MODEL.md` states Lemmas 1–2, Theorems 1–6 and
Proposition 7. `proofs/OrchLang.v` mechanises Lemma 2, Theorems 1, 5 and 6 in Coq
8.18 with no axioms; mechanising Theorem 6 found a gap in its paper proof.

**Evaluation.** `bench/evaluate.py` now has E0–E11: audit regressions, cost and
byte-bounded cost suites, the relational suite under content-dependent providers,
three couplings and real-tokenizer re-billing, leakage bounds, flow conformance,
tokenizer facts, a real model, and a real-workflow corpus of 52 candidates (30
ported, 22 excluded) with labels committed before porting, a frozen compiler for
the held-out split, and a cross-check against AgentDojo's recorded attacks. The
harness runs in bounded memory (re-billing in short-lived child processes,
because the tokenizers library retains memory on long inputs).

**Real workflows, results.** In 6,000 runs of the 30 ports, with real-tokenizer
re-billing, no certificate was exceeded. Every labelled flow error was reported;
two held-out ports got an extra `E233` from the integrity program-counter rule.
AgentDojo's 88 recorded successful attacks on the ported tasks all left the
fixed plan, so the plan, not the checker, stops them. No port has a secret. The
guaranteed input bound is 4 times the estimate on the AgentDojo ports and 19 to
128 times on the LangGraph chains; an earlier draft said "up to 25×", from one
development port, and was corrected when the full run printed every port.

**Language.** `{{` and `}}` are literal braces in templates (found porting a real
prompt with a JSON schema).

**State.** 137 tests pass, warning-free. `docs/LANGUAGE_SPEC.md`, `README.md`,
`docs/REVIEW_DEMO.md`, `docs/SUBMISSION_PLAN.md` (with a revised novelty
assessment) and the Phase 2 documents are rewritten to match.
`review_evidence/` is regenerated by `scripts/review_evidence.sh`.
