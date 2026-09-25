# OrchLang — Phase 2 submission materials

First submitted 17 September 2026; revised 25 September 2026 after the self-audit
(`docs/AUDIT_2026-09-25.md`) withdrew billing signatures and the work in
`docs/PAPER.md` replaced them.

| File | Purpose |
| --- | --- |
| `OrchLang_Phase2_Report_Nambi_Rajan_M.docx` | Rubric-aligned implementation report: evidence table, the problem, two negative results and the theorem behind them, request signatures, token bounds, architecture, code quality, testing, the two audits, limitations, demo plan, future work. |
| `OrchLang_Phase2_Presentation_Nambi_Rajan_M.pptx` | 20-slide deck with speaker notes in every slide's notes pane. |
| `build_report.js` / `build_deck.js` | The generators, so both documents can be rebuilt from source. |

Rebuild both from the repository root:

```sh
npm install
npm run report
npm run deck
```

## The narrative both documents follow

1. **A normal LLM workflow**: input, prompt, model, output.
2. **Three ways it goes wrong**: overspending, a secret reaching the model,
   untrusted text becoming an instruction.
3. **A fourth, subtler failure**: a secret decides which requests are sent, and
   the bill and the network traffic show it, though no value crosses any
   boundary.
4. **Two wrong answers**: comparing worst-case costs (refuted by an external
   audit, 225 of 425 paired runs) and comparing request sizes (refuted by my own
   audit, with real tokenizers and a real model).
5. **Why both failed**: a theorem, checked in Coq, that no analysis comparing
   sizes can be sound without rejecting identical branches.
6. **The fix**: compare the requests' content; a proved `log2 k` leakage bound
   when a workflow must reveal a little.
7. **Token bounds built from bytes**, because token counts do not add up.
8. **Evidence**: synthetic suites, fourteen real tokenizers, one real model, and
   thirty real workflows under a fixed protocol, with what they did not show
   stated plainly.

## Where the marks come from

| Criterion | Marks | Where it is demonstrated |
| --- | --- | --- |
| Implementation Progress | 7 | Report §3–4, deck slides 10–13 |
| Technical Correctness | 5 | Report §6–7, deck slides 14–17; 137 tests, four Coq theorems, both audits' counterexamples as regressions |
| Compiler Concept Application | 4 | Report §4.1 (Table 3), deck slides 12–13 |
| Code Quality | 3 | Report §5 |
| Testing | 3 | Report §6 (Tables 4–5), deck slides 14–16 |
| Individual Understanding | 3 | Report §2 and §7, deck slides 7–9 and 17 |

## Live demonstration

The verified command sequence with expected output is in `docs/REVIEW_DEMO.md`;
every command in it was run against the built compiler.
