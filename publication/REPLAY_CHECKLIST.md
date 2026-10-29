# Independent replay form

Recommended route: SCP Research Paper, Experimental Software Technology /
Formal Techniques. The official journal scope supports those research areas;
the full current Guide for Authors must still be reviewed at submission.

This form is for a human colleague using another machine. Local replay by the
same automated assistant is not an independent review. Do not pre-fill successes.

Reviewer / date / platform: __________________________

Source archive SHA-256 / release commit: __________________________

1. Extract the supplementary source ZIP and run `python publication/verify_package.py`.
2. Restore the accompanying source-history bundle into a new directory. Check
   `git bundle verify` and confirm that both `6a24fe8` and the revision code
   freeze `c2bb75c` resolve. Keep the old large campaigns at their actual version.
3. Configure Python 3.12 and Lean 4.19.0 using `publication/README.md`. Compile
   `proof/ShapeCore.lean` and `proof/AdmissionDomain.lean`; inspect axiom reports
   for `sorryAx`. Read the premises, including the noncomputable ideal adapter.
4. Run the configured or model-free unit suite and record its explicit skips.
5. Run `experiments/admission_domain.py` into a new output file. Confirm one
   short/long refusal distinction and 45 successful finite-domain executions.
6. Run `experiments/source_binding_case.py`. Expect candidate-policy acceptance,
   source-bound unshaped rejection, and repaired acceptance.
7. Run `python publication/build_evidence.py --require-complete`. Regenerate the
   original tables, keeping new revision experiments in their separate cohort.
8. Run `publication/analyze_referee_revision.py` on the revision directory into
   a new summary. Inspect every negative outcome, the exact planned ID sets,
   local-observer checks and deliberately corrupted-count detection.
9. Download and hash-check a pinned GGUF with the supplied fetcher. Run one
   original/shaped switch slice and the standalone source-bound artifact checker.
   Optionally rerun the full revision protocol into a fresh directory.
10. Compile the paper, compare the table values with raw JSON, and inspect the
    admission, transparency, dummy-tool, EOS and isolated-prefill limitations.

Commands attempted / results / failures: __________________________

Assumptions inspected / concerns: __________________________

No successful checklist can substitute for human authorship, licensing decisions,
consent, a public archive deposit or an editor's publication decision.
