# Submission guide

This file is for the authors. It summarizes what the paper claims, where each claim is
backed, what reviewers are likely to ask, and where to submit.

## The paper in one paragraph

LLM workflows that branch, loop or fan out on private content leak that content
through usage metadata (call count, model, input and output tokens), which
observability platforms, gateways and billing keep even in their content-redacting
modes. OrchLang detects these flows with information-flow labels and removes them
with a shaping transformation (exact input padding, forced output length, alignment
of secret branches into a minimum-cost common call sequence with dummy calls, padded
loops). An untrusted compiler produces the shaped program; a Lean 4 validator,
proved sound, accepts it only if it is safe and only adds padding. Evaluation: a
census of 54 example workflows (69% content-dependent), nine faithful ports run with
Llama 3.2, attacks on content-free usage records, cost, function, latency,
differential testing and fault injection.

## Claim map

| Claim | Evidence |
|---|---|
| Usage noninterference for validated programs | `proof/ShapeCore.lean`: `noninterference`, `distribution_noninterference`, `validateProgram_sound`, `secret_inputs_sound` |
| Functional preservation under transparency | `erase_correct`, `clean_data`; forced-decoding transparency tested in `experiments/transparency.py` |
| Content-dependent control flow is common | `experiments/census/` (CSV with line-level evidence, scripts) |
| Undefended workflows leak; weaker defenses leak; shaped ones do not | `experiments/results/`, `experiments/aggregate.py`, tables in `paper/generated/` |
| Cost, function and latency | same |
| Compiler/runtime agree with the model; validator catches bugs | `experiments/differential.py`, `experiments/mutation.py` |

## Likely reviewer questions and where the paper answers them

- *Is the threat realistic?* Section 2 cites the vendor documentation that keeps usage
  metadata in redacted modes, and concurrent measurements of router-log leakage.
- *Is this new given Chen 2026, SICC, Dangol, Time Will Tell?* Related work positions
  each; our baselines include their defenses' analogues (pad-only, random padding).
- *Is the theorem trivial?* The paper says plainly that the proof is a standard
  noninterference argument; the contribution is the semantics with forced decoding,
  dummies, padded loops and per-site randomness, the validator, and its use as the
  only trusted component. Fault injection shows the validator is necessary.
- *Overhead?* Reported per workflow, against naive and uniform baselines, with a
  cap-tuning analysis. It is real and stated as the price of an exact guarantee.
- *Hosted APIs?* Discussed; the no-force condition quantifies what remains.
- *Small models?* Threats to validity; the channel is structural, and the shaped
  traces are constant regardless of model quality. A Qwen replication covers a
  second model family.

## Where to submit

The work is security plus programming languages. Deadlines were verified on official
pages on 23 October 2026 and must be rechecked.

| Venue | Deadline | Fit |
|---|---|---|
| PETS 2027 (PoPETs), issue 3 | 30 Nov 2026 | Metadata privacy; traffic-analysis defense community; journal-style with revisions. **Recommended first target.** |
| USENIX Security 2027, cycle 2 | 26 Jan 2027 (registration 19 Jan) | Measurement + defense + artifact |
| IEEE CSF 2027, winter | 28 Jan 2027 | Formal guarantee and verified checker |
| ACM TOPS / IEEE TDSC / Computers & Security | rolling | Journal route with no deadline pressure |

PETS uses its own template; the content of `paper/` transfers directly. Keep the
artifact (this repository at a tagged release, with a Zenodo DOI) linked from the
paper.

## Before submitting

1. Both authors read and approve the full text; confirm affiliations and the
   corresponding author.
2. Re-run `experiments/aggregate.py` and rebuild the PDF from the committed records.
3. Tag a release and archive it (Zenodo) and put the DOI in the artifact section.
4. Re-check arXiv for new related work (the area is moving quickly) and the venue's
   current call for papers.
5. Keep the AI-assistance statement accurate.
