# Eight-minute review script

**Target:** about eight minutes, including the final local demo. Slides 26–31 are question material. Keep every displayed count tied to the refreshed reproduction manifest and confirm the local demo server before presenting.

## Main talk

### 0:00–0:08 · Slide 1 — OrchLang

I’ll distinguish a one-run budget, cross-run usage equality, and leakage in a finite usage distribution.

### 0:08–0:42 · Slide 2 — Equal means can hide different usage laws

The secret selects between two one-call branches. One returns output usage one or three with equal probability. The other always returns two. Both means are two, but the exact finite distributions are disjoint: total variation is one. Under the shown uniform prior, the fixture gives one bit of mutual information. This is a hand-supplied kernel, not a measured model distribution.

### 0:42–1:12 · Slide 3 — Aggregate totals can hide call order

Now the two branches return usage `(1,3)` and `(3,1)`. Each makes two calls and stops with the same input and output totals. Aggregate TV is zero; ordered trace TV is one. The result depends on what the observer retains.

### 1:12–1:30 · Slide 4 — Three questions: budget, trace and channel

A unary bound limits one execution. A relational check compares two executions. A finite channel analysis computes an observation law under explicit probabilities. The tools answer different questions.

### 1:30–1:46 · Slide 5 — Four input paths keep claims separate

The bounded C++ compiler, JSON graph checker, source adapters and finite-kernel tools have separate input models and evidence. The local runtime uses an offline oracle.

### 1:46–2:04 · Slide 6 — Equal caps still permit different realized usage

Both public inputs have the same declared maximum. The secret chooses which value reaches the same call. Their actual lengths can differ, so equal bounds do not establish equal usage traces.

### 2:04–2:26 · Slide 7 — The bounded compiler compares resolved requests

The checker compares resolved model identity, exact template bytes, ordered typed arguments, public guards and matched prior results. It accepts 15 of 15 balanced source-derived projections, compared with 8 of 15 in the preceding version. These are partial projections with authored variants.

### 2:26–2:44 · Slide 8 — The cyclic checker relates two control states

The graph worklist pairs control positions and a relation `R` of values justified equal. A matched request under shared Ω can add result values to that relation.

### 2:44–3:01 · Slide 9 — Secret choices branch universally in the product

Every secret successor pair must pass. Public tests synchronize on related values, calls must match exact descriptors, and both sides must stop together. A cap cannot produce acceptance.

### 3:01–3:19 · Slide 10 — Productive cycles establish usage-prefix equality

When a productive cycle returns to the same product state and relation, its closure supports every finite usage prefix under Ω. It does not prove termination or a finite total budget.

### 3:19–3:39 · Slide 11 — Overwriting a result erases its old pairing

The second call overwrites `a`, so `a` now relates to `y`, not stale `x`. The third request pair cannot match. The figure's usage values are one finite offline witness.

### 3:39–3:52 · Slide 12 — A separate replayer rebuilds the graph closure

The replayer reconstructs the rooted product closure from raw graph bytes. It checks certificate structure under versioned rules, not source fidelity or the theorem's metatheory.

### 3:52–4:06 · Slide 13 — The source bridge admits a small OrchLang subset

The bridge exported 17 of 20 selected files. The three exclusions use retries outside graph version one. Source and output hashes make artifacts inspectable; they do not prove translation correctness.

### 4:06–4:21 · Slide 14 — Source-level StateGraph examples reach LangGraph

Across 36 original-source runs, 30 accepted trace comparisons and six rejection probes matched. The Python AST frontend has 20 tests and handles a restricted authored subset.

### 4:21–4:36 · Slide 15 — The pinned backend found no trace differences on its grid

LangGraph 1.2.14 ran 888 offline cases and compared 4,528 call-event pairs with zero differences. Twenty-four executions reached the call horizon, so these runs do not establish termination.

### 4:36–4:58 · Slide 16 — Full request text was checked in bounded compiler stress

The 264 generated cases include 144 accepted programs and 120 mutations. A separate Python interpreter compared 13,824 accepted secret pairs with zero request or usage mismatch and checked 66,240 calls. It found 117 mutation witnesses; three finite cases remain unknown.

### 4:58–5:12 · Slide 17 — The channel analyzer takes finite kernels as input

It reads explicit rational outcomes, a fixed public store, chosen secret scenarios, an observer and a finite call horizon. It does not estimate provider probabilities.

### 5:12–5:30 · Slide 18 — Dynamic programming keeps exact probability mass

The DP merges only identical future-relevant states and propagates rational mass. A separate no-merge DFS checks the finite path distributions. Resource limits return unknown.

### 5:30–5:48 · Slide 19 — Bisimulation is sufficient, not complete

The transducer saturates call ordinals at 33 because kernel tests stop at 32, and retains bounded history. Exact partition refinement compares visible usage labels and successor-block mass. A shared initial block proves equal ordered success-only laws at every finite horizon. A split is inconclusive.

### 5:48–6:02 · Slide 20 — A separate replayer checks the stable partition

The report has 11 fixtures: five prove equal laws and six are inconclusive. All 11 normal certificates replayed. The five proved cases yield 60 exact DP checks across six horizons and two observers, comparing 120 unit-mass scenario histograms. Eleven fresh cap probes returned UNKNOWN; producer and replayer have 17 and 12 tests. None of this validates a provider kernel, termination, or infinite-run laws.

### 6:02–6:33 · Slide 21 — Exact trace equivalence resolves a split

Here is a split case. In one secret path, the first response selects the next request; in the other, the workflow sends `pink`. Both yield ordered output counts `(1,1)` and `(1,3)` with probability one-half, so H=2 TV is zero. The strong-bisimulation split is a fresh analyzer comparison, not independently replayed in this study. The exact checker closes the rational span of the signed start-state difference under each usage label, then checks stopped and live mass. Zero proves every finite word; a residual gives a finite witness, and a cap returns UNKNOWN. This applies established weighted-automata equivalence with independent replay of the exact certificate.

### 6:33–6:53 · Slide 22 — Prior work narrows the contribution

Resource-aware IFC, RelCost, PPDL, QIF and probabilistic trace-equivalence methods already exist. Our delta is their application to a finite LLM usage observer with independently replayed certificates. It is not a new general equivalence algorithm.

### 6:53–7:08 · Slide 23 — Relational claims depend on request and oracle contracts

Equal public inputs, complete modeled requests, compatible usage accounting, and shared Ω are premises. Hidden provider fields and state must be included for a real deployment claim.

### 7:08–7:18 · Slide 24 — The artifact makes its limits inspectable

Reports, source hashes, replay tools, tests and build instructions support review. They do not establish provider invoices or publication outcomes.

### 7:18–7:25 · Slide 25 — A narrow usage contract supports reviewable claims

The compiler, graph checker and finite-kernel analyses answer separate questions. I’ll close with the local demonstration.

## 7:25–8:00 · Slide 32 — Live HTML demo

From the repository root, run `python3 demo/server.py` and open the clickable loopback URL. Briefly show aggregate versus ordered observations, then open `trace_equal_not_bisimilar`: the strong-bisimulation status is an unreplayed analyzer comparison, H=2 TV is zero, and exact row-span replay proves equal finite-word laws for the supplied kernel. The page runs local offline fixtures and makes no provider calls.

## Untimed Q&A note — publication fit

The final independent review rates overall applied-project novelty 5.8/10, applied method 5.9/10, research-software quality 6.5/10, evidence 7.0/10, SCP OSP originality/significance 6.2/10, the equal-weight six-criterion candidate-quality proxy 7.4/10, target fit 8.5/10, and fundamental theory 3.0/10. These are internal review aids, not journal ratings or acceptance probabilities; a novelty score of 8 is not supported. Keep them in Q&A only, not on the main slides. See `docs/FINAL_PUBLICATION_REVIEW.md`.
