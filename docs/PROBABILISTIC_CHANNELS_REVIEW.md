# Design and proof review: finite probabilistic usage channels

**Status (2026-10-09):** the saved finite-rational DP study is independently
replayed for all 130 reports, with its hashes and caps recorded below. The
separate all-horizon equality checker is reviewed as an experimental
implementation with 17 passing tests; its certificate does not yet have an
independent replayer. Per-state key serialization is preflighted against a
16 MiB cap, while cumulative work is a deterministic serialization estimate,
not a process-RSS bound. The combined reproduction may refresh exact hashes.
This remains a research prototype, not part of the C++ compiler or a provider
adapter.

## Candidate research contribution

The current relational checker proves a universal statement under a shared
request-sensitive oracle: all related secret-controlled executions have equal
modeled usage traces when each matched call has the same resolved contract,
ordinal, and abstract request. A probabilistic analyzer answers a different
question. Given one explicit finite stochastic contract, what distribution
does a chosen **usage-only observer** see for each secret assignment, and how
much can those distributions distinguish the secrets?

This is an application candidate at the intersection of probabilistic
workflow semantics, quantitative information flow, and per-call LLM usage.
It is not a new general QIF metric or coupling theory. PPDL already gives
probabilistic semantics to multi-call LLM/tool flows, explores trace/output
distributions, uses total-token budgets in its experiments, and logs token
usage in its proof-repair example. IBM's [official PDL tutorial](https://ibm.github.io/prompt-declaration-language/tutorial/)
also exposes runtime counters for calls, prompt tokens, and completion tokens;
usage collection itself is established workflow functionality. General
probabilistic leakage analysis already covers arbitrary program points, and
symbolic QIF already computes entropy, KL divergence, and mutual information
for discrete programs.
Therefore a distribution engine, usage counter, token budget, TV metric, or
MI formula alone cannot carry the novelty claim. The research delta must be
the exact semantics and compositional analysis of a secret-conditioned,
request/history-indexed **usage observer**, plus evidence that it answers
questions the current universal request-equality check cannot express.

Primary comparison points:

* Mandel et al., [*PPDL: LLM-Based Flows as Probabilistic Programs*, ICML
  2026](https://proceedings.mlr.press/v306/mandel26a.html), especially the
  paper's probabilistic trace semantics and token-budgeted proof/repair
  experiment ([author-hosted full text](https://guillaume.baudart.eu/papers/icml26.pdf)).
* Chothia et al., [*Probabilistic Point-to-Point Information Leakage*, IEEE
  CSF 2013](https://doi.org/10.1109/CSF.2013.20), which measures leakage
  between arbitrary program points and includes nontermination and input.
* Schröer et al., [*Symbolic Quantitative Information Flow for Probabilistic
  Programs*, 2024](https://doi.org/10.1007/978-3-031-75783-9_6), which computes
  symbolic entropy, conditional entropy, KL divergence, and mutual information
  and gives exact expressions for discrete programs.
* Barthe et al., [*Relational Reasoning via Probabilistic Coupling*, LPAR
  2015](https://doi.org/10.1007/978-3-662-48899-7_27), for the standard
  coupling argument that can connect a pathwise theorem to equal marginal
  distributions.
* Provider/report audits are a different threat model: [Sun et al., ICML
  2026](https://proceedings.mlr.press/v306/sun26bd.html), [IMMACULATE,
  arXiv:2602.22700](https://arxiv.org/abs/2602.22700), [Token Inflation,
  arXiv:2605.30040](https://arxiv.org/abs/2605.30040), and [The More It Says,
  the More You Pay, arXiv:2609.20370](https://arxiv.org/abs/2609.20370).
  These sources make clear that a local program analysis is not a provider
  execution or invoice audit.

## Finite semantics

### Program and oracle

Let `G` be a versioned finite typed workflow graph, `x` a fixed public-input
valuation, and `s` a valuation of its finite declared secret inputs. The
graph's data and control semantics are deterministic between model calls.
Each call resolves to contract `c`, per-contract ordinal `k`, and request
descriptor `Q`. `Q` is exactly the current graph/source abstraction (template
bytes plus ordered argument values); it is not a provider's wire request or
serialized chat payload.

Specify a finite conditional kernel:

```text
Ω(c, k, Q, h) : Outcome -> Rational[0,1]
```

`h` is the suffix of the last `m` complete modeled call outcomes, for a
declared finite memory window `m` (the current accepted range is 0 through 4).
Each row's rational probabilities must sum exactly to one. The current v1
kernel outcome contains returned text and reported output usage. This is a
success-only model: it has no transport errors, retry state, provider status,
or per-call usage-receipt status. If a future format models those fields,
they must be included in the kernel outcome and, when visible, the observer.
Every currently modeled field that affects later source control or request
construction is part of the outcome/history. The current kernel requires a
default distribution for every resolved contract; matching partial rules
override it in file order. Missing defaults or an inconsistent response/cap
must fail closed. A broad default is an explicit model assumption for every
request not covered by a more specific rule.

The current JSON kernel also has ordered partial rules: each rule may constrain
some subset of `(contract, ordinal, Q, h)`, the first matching rule supplies
the distribution, and a per-contract default handles the remainder. This
first-match order is part of the mathematical input. For reviewability, bind
the raw ordered kernel file hash in the result and test overlapping rules. A
stronger format could reject overlapping rules with different distributions
and require exact complete-key rows; do not describe a wildcard/default table
as an unordered map keyed only by exact `(c,k,Q,h)`.

This is a Markov-window assumption. It is not a discovery of provider
behavior: any provider/session state that affects the real law must be
represented in `h` or the modeled contract, or the result does not apply to
that provider. At each invocation, execution samples a fresh conditional
outcome according to the row selected by `(c,k,Q,h)`. Calls may still be
dependent through `h`; no independence claim follows. A finite kernel table
is a user-supplied mathematical model, not a fitted or validated API model.

The graph, public/secret domains, request values, response support, model
contracts, and per-call accounting are all finite. Kernel rows enumerate all
modeled success outcomes in this v1 fragment, not only output-token counts.
This allows response text to update registers and affect later requests and
guards.

### Observer

Define and version the observation before evaluating a graph. The current v1
implementation supports two usage observers (the JSON format retains some
legacy `billing` field names):

1. `aggregate`: per-contract call count, summed input usage, summed output
   usage, and whether execution stopped or was truncated; or
2. `trace`: the ordered sequence of resolved contract, input usage, and output
   usage for each call, plus stopped/truncated.

Input usage is the graph's explicit byte-based estimate: for divisor `d`,
`ceil(UTF8_bytes(template)/d) + Σ_i ceil(UTF8_bytes(argument_i)/d)` over the
ordered template and argument fragments. This is an abstract accounting unit,
not provider-tokenizer accounting or a serialized provider request. These
results are usage statistics, not currency bills. Although a model
contract can carry a unit price, the current observer does not multiply usage
by that price or model price tiers, rounding, cache discounts, or invoice
adjustments. Do not describe `aggregate` as an exact monetary charge.

This observer excludes request contents, response contents, per-call errors,
latency, tool effects, and provider-side hidden work. It is therefore a
usage-log channel for an observer who sees those fields; it is not a
confidentiality property against the provider, which ordinarily sees the
request itself. Do not call it a general privacy property for the workflow.

### Bounded execution and exact dynamic programming

Fix a call horizon `H` with `1 <= H <= 32`, finite input assignments, and a
control-step resource bound. For each fixed `(x,s)`, evaluate the graph with
memoized dynamic programming over a state containing at least:

```text
(control location, call index, register store, per-contract ordinals,
 history suffix h, calls remaining, observer accumulator)
```

At a call, compute its resolved `(c,k,Q,h)`, branch over every positive-mass
outcome, multiply its exact `Fraction` probability, update the store, ordinal,
history, usage accumulator, and control location, then sum masses for equal
terminal observations. At deterministic nodes, continue according to the
ordinary graph semantics. On reaching `stop`, emit a stopped observation.
After `H` calls, continue resolving control until either `stop` or the next
call: reaching `stop` is a stopped run; reaching another call emits an
explicit truncated observation without executing that call. A control-step
cap reached before either point returns `UNKNOWN` rather than discarding or
renormalizing partial mass.

The distribution must be closed: for every analyzed secret assignment,
`Σ_t P(T=t | x,s) = 1` exactly. If any reachable state is unsupported,
resource-capped, lacks a normalized kernel row, or cannot be resolved within
the declared control bound, return `UNKNOWN` for the whole distribution.
Never treat missing mass as zero, silently ignore paths, or interpret
truncation as normal termination. Call-free cycles must be rejected or
resolved through an explicit bound; productive cycles are finite under `H`.

The memoization key must include all semantic state that can affect future
execution. Merging states solely by current usage vector is unsound when
distinct response text or long history changes a later request. If using the
`aggregate` observer, aggregate only the observer accumulator; preserve the
full store and history in the execution state.

### Metrics

For fixed public valuation `x` and secret `s`, let `P_s(t) = P(T=t | x,s)`.
For every pair of secret values, compute total variation exactly:

```text
TV(P_s, P_s') = (1/2) * Σ_t |P_s(t) - P_s'(t)|
```

TV is the maximum difference in event probabilities for this finite observer
under the declared distributions. For an equal-prior binary secret test, the
optimal success probability is `(1 + TV)/2`, so its advantage over random
guessing is `TV/2`. Zero for every pair is equality in distribution of the
chosen usage observation. It does not prove pathwise equality under a
particular coupling, equality of requests, content confidentiality, or
security against another observer.

Given a declared finite prior `π` over secrets, report Bayes vulnerability
`V(π) = Σ_t max_s π(s) P_s(t)` and min-entropy leakage
`log2(V(π) / max_s π(s))`. Report the pairwise maximum-likelihood ratio with
explicit treatment of zero probabilities. Mutual information is

```text
I(S;T) = Σ_s,t π(s) P_s(t) log(P_s(t) / Σ_r π(r)P_r(t)).
```

The probability weights, TV, Bayes vulnerability, vulnerability ratios, and
likelihood ratios are exact rationals. Min-entropy leakage and MI are generally
not rational; retain exact log expressions and label floating results as
approximations, ideally with certified intervals. Record the prior, units,
observer, and max-divergence convention in the result. To make a result
replayable, also bind the public valuation and secret scenarios, not only the
graph and kernel.

## Soundness and termination sketch

**Theorem target.** If the typed graph is finite, each input domain and
response support is finite, every reachable kernel row is a normalized
rational distribution over complete modeled outcomes, `h` contains exactly
the history context assumed by `Ω`, and each execution either reaches stop,
reaches the call horizon, or is explicitly marked truncated within the
control-step bound, then the analyzer terminates with the exact conditional
distribution of the declared observer for that graph, public input, secret
assignment, kernel, and horizon. If a resource cap is reached, the analyzer
returns `UNKNOWN` and makes no distributional claim.

**Proof outline.** Prove by structural induction on a finite unrolling
measure: remaining call allowance followed by the bounded control-step budget
within the current call-free segment. Deterministic transitions preserve
probability mass and follow the graph semantics. At a call, the reachable
kernel alternatives are finite; their exact rational weights sum to one.
For each outcome, the store/history/ordinal update is the specified semantic
transition. By the induction hypothesis, each continuation's computed
distribution is exact. Multiplying by the branch weight and adding
distributions over equal observations is precisely the law of total
probability. Stop and horizon boundaries emit the declared terminal
observation. Since every path ends in one such boundary, exact total mass is
one. If a cap prevents the induction premise from being discharged, fail
closed with `UNKNOWN`.

This establishes soundness only for the declared finite kernel semantics.
It does not establish that the kernel is an adequate model of a deployed
provider, that the graph faithfully represents arbitrary source code, or that
the usage observer is what a real service exposes. If the history window
omits a state variable that affects the response law, exactness remains true
for the supplied kernel but the provider interpretation is invalid.

## Relationship to the universal shared-oracle checker

The two analyses answer different questions and must be reported side by
side:

| Analysis | Guarantee | What it does not mean |
|---|---|---|
| Universal request-equality checker | A sufficient pathwise equality property for all paired secret arms under its shared abstract oracle assumptions. If it accepts, every modeled outcome along a matched request sequence yields the same usage observation. | It is not a probability estimate, invoice audit, or provider-kernel validation. |
| Finite probabilistic-channel analyzer | Exact equality or quantitative distinguishability of one chosen usage observer under one explicitly supplied finite conditional kernel, horizon, prior, and input domain. | TV zero does not imply equal requests or pathwise equality under the original shared oracle; positive TV is model-specific. It does not protect request text from the provider. |

The universal checker can reject two secret arms because their request
descriptors differ even when a declared model assigns them the same
usage-trace distribution. A finite-channel result of TV zero in that case is
useful evidence of distributional precision **for that kernel**; it does
not change the universal checker result. Conversely, equal expected aggregate
usage does not imply equal usage-trace distributions: a benchmark should
include secret-conditioned distributions with the same mean and nonzero TV.

When request, ordinal, and the full relevant kernel history match on paired
calls, the identity coupling yields equal call outcomes and pathwise-equal
usage traces. This is a standard consequence of probabilistic coupling, not a
new theorem about independent executions. The new analyzer computes
single-run marginal distributions and compares them; it need not pair
sampled executions or use a common random seed. If a request/history key is
missing or mismatched, do not claim the identity-coupling guarantee.

## Evidence coverage

The 11-fixture study exercises equal requests, different requests with equal
usage laws, equal-mean but distributionally different outcomes,
response-dependent follow-up calls, history-conditioned rules, output usage,
stop and horizon-truncation behavior, productive cycles, aggregate-versus-trace
observers, alias-resolved contracts, exact rational merges, and fail-closed
input/resource cases. Raw graph/kernel hashes and scenario inputs are bound in
each report. Repeated finite comparisons are model checks, not independent
provider observations.

## Current finite-channel implementation and evidence

The producer now uses canonical positive rational strings, rejects singleton
scenario sets for pairwise leakage, binds public and secret inputs, separates
the exact vulnerability ratio from its logarithm, and has deterministic
cumulative serialized-work bounds in addition to state and per-value limits.
Resource exhaustion returns `UNKNOWN` without a partial histogram. The bound
is a serialized-work estimate, not a process-RSS guarantee. The independent
DFS evaluator parses and executes without importing the DP producer,
normalizer, or kernel lookup. A separate report replayer checks raw source
hashes, scenario bindings, exact row histograms and metrics; producer counters
and floating log displays remain explicitly unverified.

On the saved synthetic study, all 130 producer reports replayed as verified
under `max_reference_paths=1,000,000`, `max_reference_steps=10,000,000`, and
`max_reference_work_bytes=1 GiB`. The producer/reference/replayer suites pass
46 tests. The controlled fixture set includes different requests with equal
usage laws, same-mean distinct laws, history-dependent follow-up usage,
aggregate-versus-trace differences, productive cycles, alias-normalized
contracts, and state-merging stress. The report has 11 authored graph/kernel
fixtures, 130 horizon/observer analyses, and 260 DP-versus-DFS histogram/mass
comparisons with no mismatch. Eleven explicit cap probes return `UNKNOWN`
without histograms. Seventeen analyses have equal expected usage totals but
positive total variation. For the noisy binary usage example, TV is `1/2` and
Bayes vulnerability is `3/4`; the ordered trace distinguishes a two-call
permutation that aggregate usage hides. These are controlled model results,
not estimates of a provider channel.

The study result is
[`probabilistic_channels.json`](../bench/results/probabilistic_channels.json);
the exact independent verifier is
[`replay_probabilistic_report.py`](../audit/replay_probabilistic_report.py).
At the time of this review the principal source hashes are producer
`45380e75cdcc4d6f285a0027cbb85dab97d22dff11c5c94d3940b6813e8dce00`,
independent DFS `9c081f87e1dcd7b283bb4894a1a1794c8183e09fcadeac53c9467cb1606e3012`,
and report replayer
`7297248e651c3972cc62287409b47a95f3f41b6b1800adc1011dc7bb4cfb1e1f`.
The final combined reproduction may refresh these hashes and counts.

## All-horizon finite-state extension

The experimental checker in
[`stochastic_bisimulation.py`](../audit/stochastic_bisimulation.py) builds a
finite semantic transition system for a fixed public store and explicit
secret scenarios under the same declared conditional kernel. Its semantic
state retains the normalized control point, all concrete register values,
per-resolved-contract call ordinals, and the complete retained history
window. Ordinals in state and history saturate at 33 because kernel ordinal
and history-event literals are bounded by 32. The visible call label is the
resolved contract plus integer input/output usage. Request and response
contents are hidden labels but remain in state and history when they affect
future requests or kernel selection. Stop is a terminal class distinct from
call states.

The checker constructs all reachable states and applies exact-rational strong
probabilistic partition refinement. Equal initial blocks imply equal
probability distributions over every finite ordered usage-trace prefix,
including stop positions. This follows by induction on finite trace length
from equality of each visible-label/successor-block probability mass. The
least fixed point handles productive cycles without an arbitrary call
horizon. A different block is only `inconclusive`: bisimulation is
sufficient, not complete, for equality of visible trace laws. The result
does not bound total cost, prove almost-sure termination, compare infinite
run laws, or validate a provider kernel. Call-free control cycles are
excluded; resource caps yield `UNKNOWN`.

This is a domain-specific use of established probabilistic bisimulation, not
a new bisimulation theory. Larsen and Skou introduced probabilistic
bisimulation for probabilistic transition systems; Kamaleson, Parker, and
Rowe later give partition-refinement minimization for finite-horizon
probabilistic systems. The present code's fixed-point test is the ordinary
all-step/strong form over usage labels, with an LLM-workflow-specific finite
state representation. [Larsen & Skou, 1991](https://doi.org/10.1016/0890-5401(91)90030-6),
[Kamaleson et al., SPIN 2016](https://doi.org/10.1007/978-3-319-32582-8_10)
([author-hosted paper](https://www.cs.ox.ac.uk/david.parker/papers/spin16fh.pdf)).

The current checker passes 17 unit tests, including tests for productive
cycles, exact usage labels, request-sensitive history, hidden response
quotienting, stop-versus-call behavior, resource caps, and the ordinal/history
boundary at 33. Resource regressions cover the pre-serialization state-key
limit and preflight JSON sizing. Its SHA-256 at review time is
`9d153ec842c89756579ec7296060478283c45e965441105430851614d205a495`.
The report includes a closed transition system and partition description,
but there is not yet a separately implemented certificate replayer. The
per-state key size is checked before canonicalization and over-limit states
return `UNKNOWN`; the cumulative deterministic work meter is not a
process-RSS bound. The semantic theorem remains sound for every completed
`proved_equal` result under the defined finite semantics.

## Remaining limits on a novelty claim

The strongest defensible claim after implementation is a software-specialized
analysis for request/history-indexed LLM-workflow usage channels: bounded
exact distributional metrics for a declared finite kernel, plus a sufficient
all-finite-horizon equality check based on a finite semantic quotient. Both
are applications of established quantitative information-flow and
probabilistic bisimulation methods. To support a substantial method novelty
assessment beyond the current specialization, the paper would need:

1. A formal semantics and theorem matching the code's precise control,
   request, history, usage, stop, and truncation behavior.
2. Independent DP-vs-DFS agreement over systematic small kernels (now
   available for the saved 130-analysis grid), plus adversarial tests for
   mass loss, stale history, output/store updates, and caps.
3. Examples that establish a meaningful distinction from both the current
   universal checker and PPDL-style probabilistic flow execution, not just
   metric computation on synthetic examples.
4. A targeted comparison with point-to-point and symbolic QIF methods that
   explains whether the kernel-indexed workflow semantics is new, a direct
   embedding, or mainly a software specialization.
5. Explicit privacy scope: secret values, prior, public input, observer,
   horizon, kernel source, and provider assumptions.

The all-horizon extension improves the precision and horizon coverage of the
specialized method, but its bisimulation algorithm is standard and it has no
independent certificate replay yet. Preserve the overall project novelty
score at 5.5/10 absent a materially new result; do not assign a journal-
specific novelty score of 8 based on metric breadth or cycle handling alone.
