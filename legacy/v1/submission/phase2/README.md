# OrchLang — Phase 2 submission materials

| File | Purpose |
| --- | --- |
| `OrchLang_Phase2_Report_Nambi_Rajan_M.docx` | Rubric-aligned implementation report: evidence table, the problem, the negative result, billing signatures, architecture, code quality, testing, the external audit, limitations, demo plan, future work. |
| `OrchLang_Phase2_Presentation_Nambi_Rajan_M.pptx` | 18-slide deck with speaker notes in every slide's notes pane. |
| `build_report.js` / `build_deck.js` | The generators, so both documents can be rebuilt from source. |

Rebuild either:

```sh
npm install docx pptxgenjs
node submission/phase2/build_report.js submission/phase2/OrchLang_Phase2_Report_Nambi_Rajan_M.docx
node submission/phase2/build_deck.js   submission/phase2/OrchLang_Phase2_Presentation_Nambi_Rajan_M.pptx
```

## The narrative both documents follow

1. **A normal LLM workflow** — input, prompt, model, output. Six declarations.
2. **Three ways it goes wrong** — overspending, a credential reaching the model,
   untrusted text becoming an instruction. All decidable from the source; all
   discovered at run time in practice.
3. **A fourth, subtler failure** — a secret decides which branch runs, the
   branches cost different amounts, and the invoice reveals the secret even
   though no value crosses any boundary.
4. **The obvious fix is unsound** — comparing the two arms' certified upper
   bounds accepts a workflow whose bill differs in 225 of 425 paired runs. This
   compiler implemented that rule and claimed a theorem for it; an external audit
   produced the counterexample.
5. **The fix that works** — compare billing *structure*, not numbers, because a
   call's output length is the provider's choice and no number can be attached
   to a call site.
6. **Evidence** — 0 bound violations in 4,600 executions checked componentwise,
   0 differing bills in 2,975 paired comparisons, and a concrete leaking witness
   behind every rejection.

## Where the marks come from

| Criterion | Marks | Where it is demonstrated |
| --- | --- | --- |
| Implementation Progress | 7 | Report §3–4, deck slides 10–12; nine working CLI commands |
| Technical Correctness | 5 | Report §6–7, deck slides 14–15; warning-free build, 95 assertions, five audit findings fixed |
| Compiler Concept Application | 4 | Report §4.1 (Table 3), deck slides 10–11 |
| Code Quality | 3 | Report §5, deck slide 12 |
| Testing | 3 | Report §6 (Table 4), deck slide 13 |
| Individual Understanding | 3 | Report §2 and §7, deck slides 7–8 and 15 — the negative result explained from first principles |

## Live demonstration

The verified command sequence with expected output is in `docs/REVIEW_DEMO.md`.
Every command in it has been run against the built compiler.

```sh
make check
./orchc check examples/invalid/equal_bounds.orch      # the counterexample
./orchc check examples/valid/balanced_signature.orch  # the balanced version
```
