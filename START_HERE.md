# OrchLang — start here

**Current review package · 9 October 2026 · research candidate 0.5.0-rc1.**

## Open these first

1. **Presentation:** [32-slide editable PowerPoint](submission/research/dist_current/OrchLang_Current_Software_Review.pptx). Its final slide opens the functioning HTML demo. Use the [8-minute script](submission/research/script_8min.md) or [15-minute script](submission/research/script_15min.md).
2. **Live demo:** from this repository, run `python3 demo/server.py`, then open **http://127.0.0.1:8765/**. It is already running in the current session. Opening [the HTML file](demo/index.html) directly works as explicitly labelled recorded evidence.
3. **Journal manuscript:** [official-template editable LaTeX](submission/research/manuscript/OrchLang_SCP_OSP.tex), [rendered PDF](output/pdf/OrchLang_SCP_OSP.pdf), [highlights](submission/research/manuscript/OrchLang_highlights.txt), and [checked journal requirements](docs/SCP_AUTHOR_REQUIREMENTS.md).
4. **Full explanation:** [17-page technical report](output/pdf/OrchLang_Technical_Report.pdf), [editable report](docs/PAPER.md), [upgrade assessment](docs/UPGRADE_ASSESSMENT.md), and [independent publication review](docs/FINAL_PUBLICATION_REVIEW.md).

## The presentation story

“A token budget answers how much a workflow can use. We also ask whether private routing changes the observable usage record.”

Start with equal caps but different input usage. Show a matched dependent chain that the improved compiler admits. Show a productive cycle and independent replay. Then separate equal means from equal laws and aggregate totals from call order. Finish with HTML story **07**: the hidden structures differ, strong bisimulation is inconclusive, and exact trace-law checking proves equal observable laws under the supplied finite model. Its independent replayer verifies the proof.

The software contribution is the inspectable pipeline from declared requests to bounds, relational checks, source adapters, finite stochastic models, independently replayed evidence, and actual offline LangGraph execution. The general mathematical methods have prior art.

## Initial versus current assessment

These are subjective internal scores, **not journal scores or acceptance probabilities**. The requested novelty-based score of 8 has not been established.

| Dimension | Initial | Current |
|---|---:|---:|
| Overall project novelty | 4.5 | **5.8** |
| Applied analysis method | 3.5 | **5.9** |
| Research-software contribution | 4.0 | **6.5** |
| Evaluation evidence | 2.0 | **7.0** |
| SCP OSP originality / significance | — | **6.2** |
| SCP six-dimension candidate-quality proxy | — | **7.4** |
| Journal scope fit | — | **8.5** |

The selected route is **Science of Computer Programming — Software Track — Original Software Publication**. This is a credible software-paper candidate for human review. No submission, editorial decision or acceptance guarantee is asserted.

## Evidence you can defend

- Full 44-stage reproduction passed, including ASan/UBSan, 112 C++ tests, 203 audit tests, 8 demo HTTP tests, 31 optional LangGraph tests, and isolated wheel checks. Source inputs did not change during the run.
- The same 15 authored balanced source projections rise from 8/15 baseline admissions to 15/15. They are partial projections, not complete application ports.
- Independent bounded semantics find no accepted request/usage difference in 13,824 secret comparisons. This corroborates the implementation within the tested model.
- The exact trace-law corpus has six equality proofs and six finite inequality witnesses, all independently replayed. Twelve resource probes return UNKNOWN; twelve semantic tamper probes reject.
- Real LangGraph executes offline; no provider distribution or invoice measurement is claimed.

The frozen manifest is [audit/final/manifest.json](audit/final/manifest.json). Full reproduction:

```sh
python3 audit/reproduce_final.py --sanitize --package \
  --integration-python integrations/langgraph/.venv/bin/python
```

The optional environment must be installed from the documented lock first; the reproduction script does not install it. See [REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Before journal submission

Confirm name ordering, affiliation and full postal address, correspondence, co-authors, CRediT roles, funding and competing interests. Review the implementation and manuscript and complete the human responsibility statement for AI-assisted work. The public immutable software identity and final archive inventory are recorded in the release/compliance files when frozen.

The strongest remaining novelty direction is a source-faithful result on an existing workflow with an independently documented confidentiality boundary. The separate [candidate research note](research/source_faithful_candidates.md) describes this direction. Ongoing experiments are not included in the frozen scores until reviewed.
