# OrchLang — Review 2 submission materials

This folder contains the presentation and report prepared for the Compiler Design Laboratory Review 2 evaluation.

| File | Purpose |
| --- | --- |
| `OrchLang_Review_2_Rubric_Report_Nambi_Rajan_M.docx` | Rubric-aligned written report covering implementation progress, compiler concepts, code quality, testing, and individual understanding. |
| `OrchLang_Review_2_Presentation_Nambi_Rajan_M_Final.pptx` | Presentation deck with speaker notes and an executable live-demo sequence. |
| `ORCHLANG_REVIEW_PRESENTATION.md` | Short, under-ten-minute presentation narrative, including the commands used in the demonstration. |

The compiler implementation and its supporting technical documentation are kept at the repository root. For the live demonstration, run:

```bash
make check
./orchc examples/pipeline.orch
```

The repository reflects the Review 2 scope. Optimisation, Python generation, and runtime/provider integration are planned later phases, rather than claims of completed functionality.
