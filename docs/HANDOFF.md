# Handoff: project state and how to finish the paper

Written 24 October 2026 so that the work can be continued by the authors (or anyone
else) without access to the session that produced it. Read this file first.

## 1. Status at a glance

| Item | Status | Where |
|---|---|---|
| Research direction and design | Done | Paper Sections 1–5 |
| Lean development (theorems, validator) | **Done**, checks with only `propext`/`Quot.sound` | `proof/ShapeCore.lean`, `experiments/results/logs/lean-check.log` |
| Compiler, runtime, tools, ports | Done | `orchlang/`, `workflows/` |
| Unit tests (11) | Done, passing | `tests/`, `experiments/results/logs/unit-tests.log` |
| CI on GitHub | Passing on every push | `.github/workflows/ci.yml` |
| Census of 54 example workflows | Done | `experiments/census/` |
| Differential test (1,000 programs) | Done | `experiments/results/differential.json` |
| Fault injection (210 mutants) | Done | `experiments/results/mutation.json` |
| Transparency, in-band (120 cases) | Done | `experiments/results/transparency-inband.json` |
| Preliminary in-band runs (switch, routing, chaining) | Done | `experiments/results/runs-inband-preliminary/` |
| Transparency, isolated padding (120 cases) | **Done: 120/120 identical outputs, 120/120 exact counts** | `experiments/results/transparency-isolated.json` |
| **Main evaluation, 9 workflows, isolated padding** | **Running / to do** (about 13 CPU hours) | `experiments/run_all.sh` |
| **Replication on Qwen 2.5 1.5B (3 workflows)** | **Queued / to do** (about 3 CPU hours) | `experiments/run_replication.sh` |
| Cap tuning, permutation tests, figure, final tables | To do (one command) | `experiments/finalize.sh` |
| Final pass over paper text against the numbers | To do (Section 6 below) | `paper/sections/*.tex` |
| Submission formatting, artifact DOI, author approval | To do (Section 8) | `docs/SUBMISSION.md` |

If the session that started the runs has ended, **the in-progress outputs are lost**
(they were in a temporary scratch directory). Start them again with Section 4; they
take about 16 CPU hours on 4 cores and need nothing else.

## 2. What the paper is

`paper/main.tex` (ACM `acmsmall` format, about 21 pages including the appendix).

LLM workflows that branch, loop or fan out on private content leak that content
through usage metadata that redacting telemetry still exports (model, input and
output tokens per call). OrchLang:

- labels data and detects secret-dependent usage;
- shapes programs:
  - exact input padding;
  - forced output length;
  - alignment of secret branches into a minimum-cost common supersequence with dummy calls;
  - padded loops;
- has a Lean-verified validator accept the untrusted compiler's output. The theorems
  establish that every accepted program emits the same usage trace for all secret
  inputs, for every randomness tape (hence in distribution), and that it computes the
  original results when padding is transparent.

The evaluation has five parts:

- a census;
- nine faithful ports run on Llama 3.2;
- attacks on content-free usage records;
- cost, function and latency;
- differential testing, fault injection, and a cross-family replication.

Every number in the paper comes from LaTeX macros generated from raw records by
`experiments/aggregate.py` and `experiments/paper_static.py`; no number is typed by hand.

## 3. Environment from scratch

Tested on Linux x86-64, 4 CPU cores, 15 GB RAM, no GPU.

```bash
git clone https://github.com/guyoverclocked/orchlang-compiler-design-project
cd orchlang-compiler-design-project
git checkout claude/trusting-clarke-c7eqeh          # or main once merged
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
pip install matplotlib                               # for the figure
# Lean 4.19.0
curl -sSfL https://github.com/leanprover/lean4/releases/download/v4.19.0/lean-4.19.0-linux.tar.zst -o lean.tar.zst
tar --zstd -xf lean.tar.zst                          # or: python -c "import zstandard..." if tar lacks zstd
export LEAN=$PWD/lean-4.19.0-linux/bin/lean
# Models: Llama 3.2 1B and 3B (+ Qwen 2.5 for pilots/replication), pinned and checksummed
python experiments/fetch_models.py models --all
export ORCHLANG_MODELS=$PWD/models/models.json PYTHON=$(which python)
# LaTeX (Ubuntu): texlive-latex-extra texlive-publishers texlive-science texlive-fonts-extra
#                 texlive-plain-generic texlive-bibtex-extra latexmk
```

Versions used for the recorded results: Python 3.13, llama-cpp-python 0.3.36,
numpy 2.5.4, scikit-learn 1.9.1, pandas 3.1.0, pyarrow 26.0.0, huggingface_hub 2.3.0,
Jinja2 3.1.6, Lean 4.19.0, TeX Live 2023.

Quick health check (minutes): see `docs/TESTING.md` sections 1–3.

## 4. Running (or resuming) the experiments

```bash
bash experiments/resume.sh out/runs        # starts in background; safe to re-run
tail -f out/runs/queue.log                 # progress
wc -l out/runs/*/*.jsonl                   # records so far
```

What it runs, in order:

| Step | Inputs | Approximate time (4 cores) |
|---|---|---|
| transparency test (isolated padding) | 120 cases | 20 min |
| Prompt Flow switch | 210 | 40 min |
| routing | 150 | 40 min |
| prompt chaining | 150 | 50 min |
| evaluator–optimizer | 100 | 1 h |
| email agent | 152 | 1.5 h |
| orchestrator–worker | 100 | 1.5 h |
| calculator agent | 100 | 1.3 h |
| corrective RAG | 150 | 2.5 h |
| adaptive RAG (1B + 3B models) | 60 | 4 h |
| replication on Qwen 2.5 1.5B: switch, email, corrective RAG | 210/152/150 | 3 h |

**Rules that matter:**

1. **Run nothing else CPU-heavy at the same time.** llama.cpp uses all cores. Earlier
   attempts that overlapped with other jobs were slowed 10× and their latency
   measurements had to be discarded.
2. Runs are **resumable**: re-running `resume.sh` continues where records stop. A
   container or machine restart kills background processes; just run it again.
3. To stop: `ps -eo pid,args | grep run_` and `kill <pid>`. Do not use
   `pkill -f run_all`; it can match and kill your own shell.
4. If a workflow's runner crashes, its log is `out/runs/<workflow>.log`.

## 5. Finalizing results (one command)

```bash
PERM=200 bash experiments/finalize.sh out/runs out/runs/replication
```

This copies the raw records into `experiments/results/runs/`, re-runs the proof
check, unit tests, differential test, fault injection and cap tuning, aggregates all
attacks with 200-round permutation tests, regenerates `paper/generated/*.tex`, draws
`paper/figures/leakage.pdf`, exports OpenTelemetry span samples, and rebuilds
`paper/main.pdf`. Then commit everything:

```bash
git add -A experiments/results paper && git commit -m "Final evaluation results" && git push
```

## 6. Finalizing the paper text

The macros guarantee that numbers are consistent with the data, but **sentences that
interpret the numbers were written before the final runs** and must be checked. Go
through this list with `paper/generated/results.json` open.

### 6.1 Claims to verify

| Location | Current claim | Check |
|---|---|---|
| Abstract, Intro "Measurement" bullet | Usage records reveal the internal decision "in all nine workflows" | `leak.orig.decision.balanced` vs `chance_balanced` per workflow. The preliminary switch run leaked its *decision* only weakly but its *dataset attribute* clearly. If a workflow is near chance, say "in N of nine" and name the exceptions with the reason (single call, constant count). |
| Abstract | Shaped programs "preserve task accuracy within X points" | With isolated padding, outputs should be byte-identical to undefended runs (`function.output_equal` near 100%). If so, say "return exactly the undefended outputs in N% of runs" — a stronger claim. If not, investigate (truncation count, sampling). |
| Abstract, §7.4 | Alignment "X% cheaper than executing all branches" | `resNaiveSavingMedian` may be 0 because in several workflows one arm's calls are a subsequence of the other's. Prefer "up to `\resNaiveSavingMax`%" and say where the two coincide. |
| §7.3 | Pad-only, random padding and no-force leak in N workflows | Macros `resPadonlyLeaky`, `resRandpadLeaky`, `resNoforceLeaky`. Check that the prose names the right workflows. |
| §7.5 Function | Text describes in-band padding as perturbing "but not degrading" the task | **Must be rewritten.** Final runs use isolated padding (expected: identical outputs). Report the in-band preliminary results separately as the hosted-API mode: routing accuracy 64.7% → 35.3% (McNemar p ≈ 1e-12) and the placement pilots in `experiments/results/README.md`. This is an honest and useful finding: in-band padding is unsafe for function on small models, and isolated padding fixes it. |
| §7.5 | Transparency macros `trGreedyEqual` etc. | After finalize these come from the **isolated** transparency run, which tests the full hypothesis (natural decoding of the unpadded prompt vs the shaped call). Update the sentence to say so. Keep the in-band numbers (120/120, forced-decoding half) as a second sentence. |
| §7.6 Latency | Coefficient of variation and latency attack | Only valid if no other job ran concurrently. Cite the permutation p-values (`resLatPermSignificant` of `resLatPermTests` tests significant at 5%). If some are significant, say so and keep the "use predictive mitigation" advice. |
| §7.7 | Differential/mutation numbers | Regenerated by finalize; check the operator list matches `mutation.json` (12 operators including `forget_secret`). |
| §7 new paragraph | Replication | Add a short paragraph from `experiments/results/aggregate-replication.json`: same qualitative results on Qwen 2.5 1.5B (different tokenizer/template). |
| §7 new paragraph | Cap tuning | Add 2–3 sentences from `experiments/results/cap-tuning.json`: price ratio and truncation rate per quantile. |
| §6 Discussion "Hosted APIs" | Mentions in-band padding | Cite the in-band results above. |
| Figure | `paper/figures/leakage.pdf` | Add to §7.3 with `\includegraphics` (not yet included in the text). |

### 6.2 Things to re-read critically

- Section 5 must match the Lean file exactly (names, hypotheses). The appendix table
  lists the correspondence; re-check it if the Lean file changes.
- Related work cites three concurrent 2026 papers (Chen; SICC; Dangol). Re-search arXiv
  before submission; the area moves weekly. The verification record is
  `research/literature-2026-10-24-shape.md`.
- The Peng et al. IEEE TNSE 2026 paper "Privacy-Preserving Agentic AI in Edge Networks
  With Content and Trace Protection" could not be read; read it and cite it if
  relevant.
- `\cite{dickerson2026loom}` is an author-hosted report, not peer reviewed; the
  bibliography says so.

## 7. Further experiments that would strengthen the paper (optional)

Ordered by value per effort. None is required for a defensible submission; each
answers a predictable reviewer question.

1. **Sampling robustness.** Re-run 2–3 workflows with `--temperature 0.7`
   (`run_workflow.py` option). Shaped traces must stay constant; undefended leakage
   typically stays.
2. **In-band mode on all nine workflows** (`"pad_mode": "inband"` in `models.json`,
   separate output directory). This characterizes the hosted-API deployment fully.
3. **Larger model.** Run 2–3 workflows with Llama 3.2 3B everywhere (edit `model llm`
   to `"llama3b"`) to show functional results do not depend on the 1B model's quality.
4. **GPU serving check.** On a GPU with vLLM, confirm `min_tokens` + `ignore_eos`
   give exact output lengths and that reported `usage.prompt_tokens` includes
   isolated padding if implemented server-side. This turns the deployment assumption
   into a demonstrated fact for a production server.
5. **Latency mitigation.** Add predictive padding of completion time (Askarov et al.)
   to the runtime and show the latency attack falls to chance.
6. **Bounded-leakage extension.** Align arms in groups (leak at most log2(groups)
   bits) to trade cost for leakage; would need a small Lean extension.
7. **More workflows.** The census lists 37 content-dependent workflows; porting more
   (especially agents with tool menus) widens coverage.

## 8. Before submission

1. **Authors:** both authors read and approve; confirm affiliations, the corresponding
   author, and the author order. The current author block is from the earlier
   manuscript.
2. **Venue:** see `docs/SUBMISSION.md`. Recommended: PETS 2027 issue 3
   (30 Nov 2026), which needs its own LaTeX template. Alternatives: USENIX Security
   2027 (26 Jan 2027), IEEE CSF 2027 (28 Jan 2027), ACM TOPS (rolling). Check page
   limits; the appendix can move to supplementary material.
3. **Artifact:** tag a release (e.g. `v2.0-paper`), archive it on Zenodo, put the DOI
   in the paper's artifact section, and say the raw records are included.
4. **AI disclosure:** keep the statement in `paper/sections/conclusion.tex` accurate.
5. **Anonymization:** if the venue is double-blind, remove author names and the GitHub
   URL, and link an anonymized artifact.

## 9. Known issues and pitfalls

- **Background processes die on container restart.** Use `resume.sh`; records survive
  only if the output directory survives.
- **CPU oversubscription.** Two llama.cpp processes on 4 cores slow both by about 10×.
- **Model behavior.**
  - Qwen 2.5 1.5B refused 70% of joke requests about obscure entities, which is why
    the main model is Llama 3.2.
  - Llama 3.2 1B often does not emit the Prompt Flow switch's exact label strings, so
    most switch queries route to "unknown". This faithfully reproduces how the
    original flow behaves with a weak model; say so if a reviewer asks.
  - The Llama 1B router never answers "story" in the routing workflow; the routing
    accuracy is therefore at most two thirds.
- **In-band padding perturbs small models** (Section 6 above). Isolated padding is the
  default for this reason.
- **Data licenses.** The customer-support tickets dataset is CC BY-NC 4.0
  (non-commercial); fine for research, but see `THIRD_PARTY_NOTICES.md`.

## 10. Decision log

| Decision | Reason |
|---|---|
| Pivot from the v1 relational cost checker | Its Lean certificate reduced to syntactic equality of branches, with no precision advantage and no real workload; reviewers would call it trivial. |
| Usage-metadata observer | Vendor docs (OTel GenAI, LangSmith, Helicone) keep exactly these fields in privacy modes; concurrent work (Chen 2026) confirms leakage at scale for single routers. |
| Translation validation in Lean, not a verified compiler | Small trusted base; the Python compiler can change freely. |
| Per-site randomness tape | Lets two executions on different secret paths share randomness for common calls; implies distributional equality under i.i.d. cells. |
| Forced decoding + visible cap | Exact output counts with the visible answer unchanged (tested). |
| Isolated padding by default | In-band filler breaks small models' instruction following (pilots). |
| Llama 3.2 1B/3B | No refusals on the datasets; fast enough on CPU. |
| Explicit loop and fan-out bounds | Required for any static shape; 22 of 25 census loops are unbounded in code. |
| Output weight 4× input in costs | Typical API price ratio; stated in the paper. |
