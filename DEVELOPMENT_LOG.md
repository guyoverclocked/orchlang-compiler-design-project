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

Built a demo pipeline for presenting from a MacBook.

- `demo.sh` drives a 13-scene live demo from one scene list. `./demo.sh setup`
  checks the toolchain (and opens Apple's Command Line Tools installer when they
  are missing), builds from clean, runs the tests and the example corpus,
  rehearses every step, and writes a plain-text transcript to
  `build/demo-transcript.txt` as a fallback. `./demo.sh` presents: each command
  runs on a key press, with the line that matters highlighted and a one-line
  caption. Arrow keys and presentation clickers work. `./demo.sh check` reruns
  all 36 steps and verifies their exit status and every number the captions
  quote.
- `DEMO.md` is the presenter's guide: setup, a pre-talk checklist, the script
  scene by scene, likely questions, and troubleshooting. `docs/REVIEW_DEMO.md`
  now points to it, and the old `scripts/demo.sh` is gone.
- Added `make demo`, `demo-setup`, `demo-check` and `bench`. The README now says
  `python3`, since macOS has no `python`.
- Portability checks: the compiler builds with clang and libc++, the Mac's
  toolchain, with zero warnings and 95/95 tests passing. The script runs under
  bash 3.2.57 (built from source to match macOS's `/bin/bash`) and the
  one-true-awk that macOS ships. Seeded mock runs are byte-identical between
  libstdc++ and libc++ builds, because the runtime uses its own generator rather
  than `<random>` distributions. Not yet run on physical Mac hardware.

Later the same day: a case study against real incidents, and end-to-end proof.

- `docs/CASE_STUDY.md` models seven problems in OrchLang, each with a vulnerable
  workflow and a repaired one under `case_studies/`. Six are documented
  incidents or vulnerability classes: the GitHub MCP toxic agent flow, the
  Supabase MCP ticket leak, EchoLeak (CVE-2025-32711), LangChain CVE-2023-29374,
  OWASP LLM07's credential-in-prompt scenario, and the retry-loop cluster of the
  Token Budgets catalogue. The seventh is a constructed billing side channel
  grounded in three published token-count attacks. Every source was fetched and
  checked; the CVE entries come from the official CVE record API.
- All seven vulnerable workflows are rejected with exactly the expected codes,
  and all seven repairs are accepted. The vulnerable retry agent overran its
  budget in 3 of 200 seeded runs (the repair in none). The vulnerable router's
  bill changed with the secret in 25 of 25 paired runs (the repair's in none).
  Two `limitation_*.orch` files are accepted on purpose, to show what a
  mislabelled input or an undeclared effect hides from the compiler.
- `case_studies/verify.py` checks all of it, reusing the benchmark's driver, and
  writes deterministic results that are committed.
- `verify.sh` (`make verify`) proves the project works from a clean tree: a
  strict build with `-Werror`, the tests, ASan and UBSan, benchmark
  reproduction, the demo rehearsal, and case-study reproduction. It writes
  `verification/EVIDENCE.txt` with SHA-256 digests. It passes with GCC 13 and
  libstdc++, and with Clang 18 and libc++, and the committed results reproduce
  byte for byte across the two. `.github/workflows/verify.yml` runs it on
  Linux and macOS on every push.
- `bench/evaluate.py` takes `ORCHLANG_RESULTS_DIR`, so verification can
  reproduce the results without overwriting the committed ones.
- Fixed `demo.sh`, which failed when `CXX` carried flags such as
  `clang++ -stdlib=libc++`.

Prompt-injection survey (same day).

- `docs/CASE_STUDY.md` section 4 surveys eleven prompt-injection incidents and
  models four more: Gemini driven by a calendar invite (SafeBreach), ForcedLeak
  in Salesforce Agentforce (Noma Security), the Perplexity Comet browser
  (Brave), and MCP tool poisoning (Invariant Labs). Each vulnerable workflow is
  rejected with `E233`, and each repair mirrors the vendor's own fix and is
  accepted.
- The Comet repair separates planning from reading and needs no escape hatch.
  A plausible regression of it, one that lets the planner see the page
  summary, is rejected.
- The DPD chatbot (case 12) is accepted, and documented as out of scope: its
  harm was in what the model said, not in what it did.
- The first CI run (36088622594) passed every step on Ubuntu and on macOS 26.6
  (Apple silicon, Apple clang 21, GNU Make 3.81), with identical digests. That
  run is the first verification on real Mac hardware.
