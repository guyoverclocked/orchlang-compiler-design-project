# Review of a finite cyclic-graph usage checker

**Status:** independent algorithm and adversarial review of the experimental
checker on 9 October 2026, with a separate limited review of the source bridge.
The frozen producer snapshot is
`103ebc7129d117fb6416ad03d919e08abdcd787b2cc7dcb5f7290394d383ab42`; the
certificate replayer is
`675590d24c5753a36ee6645a31eed170a52abf118562a8f171296a5fdfab3ccb`. This
review covers the graph checker and replay evidence. It is not a mechanized
proof. The source bridge has a narrow accepted subset, finite differential
tests, and a corpus evaluation, but no verified translation argument.

## Implementation review at the current snapshot

The proposed checker now exists as [`audit/orchgraph.py`](../audit/orchgraph.py)
and the separate certificate replayer as
[`audit/replay_graph_certificate.py`](../audit/replay_graph_certificate.py).
The first accepts a strict versioned JSON graph and explores the reachable
self-product; the second independently normalizes the graph and reconstructs
the root relation, every product node/rule/successor, reachable source states,
and per-state abstract cost summaries. Its attestation explicitly leaves the
producer hash unverified and does not claim to mechanize the relational
metatheory or validate a source-to-graph translation.

The authored graph corpus has 17 cases: 6 accepted, 8 rejected, and 3 invalid.
All six accepted certificates independently replayed. The frozen finite
value grid in [`graphs.json`](../bench/results/graphs.json) ran 1,400 accepted
reference executions and 800 accepted secret-assignment comparisons. It
recorded zero request, billing-vector, and complete-trace differences, with
28,580 call-accounting checks. Each of the eight rejected fixtures had both a
full-trace and billing-vector witness in the finite grid; non-stopped runs are
compared only through the configured 120-call horizon. These are authored
examples and finite probes, not external workflow ports or a proof.

I also preserved a separate 3,000-case seeded property probe in
[`graph_adversarial.py`](../audit/graph_adversarial.py) and its result in
[`graph_adversarial.json`](../bench/results/graph_adversarial.json). It
accepted 1,462 generated graphs and checked 11,696 ordered equal-public store
pairs, including 5,848 distinct-secret pairs, across prefixes capped at 20
calls. It records generator seed 8675309 and protocol/oracle seed 8675309;
the refreshed report binds to the frozen producer hash above. Requests,
input/output token usage, response bytes, and stop/truncation status agreed in
all checked pairs. This probe imports the producer's own
`reference_run`; it is explicitly **not an independent interpreter**. Its
generator covers only small graphs with Boolean public/secret inputs and
literal requests. It supplies adversarial property coverage, not independent
semantic validation.

The replayer's separate test suite and root's finite graph grid are reported
in their own artifacts. A successful replay validates that the certificate
is the complete closure of the current JSON graph under the stated local
rules. The product rules remain a conventional relational product: matched
calls add a register-equality pair under the shared oracle; secret successors
are universal obligations; public guards require related operands and equal
predicates; call-free cycles fail closed; call-bearing cycles close
coinductively. For those cycles, the conclusion is finite usage-trace-prefix
equality only, with no termination or finite total-cost bound.

No soundness counterexample was found in this review's small-graph probes,
fixture replay, or certificate-tampering checks. This is evidence about the
implementation snapshot, not a proof that every graph/model meets the oracle
and accounting assumptions. A malformed producer report, unsupported graph,
product-cap exhaustion, or mismatch must not be described as accepted; the
resource-cap result is `unknown` and fails closed.

The graph producer and replayer are also packaged as an installable Python
wheel. The offline isolated-environment smoke report records a successful
build, install, cyclic check, independent replay, and rejection of stale
relation, tampered certificate, and wrong-source cases. This tests packaging
and command usability on the recorded macOS/arm64 environment; it is not
independent metatheory verification or a public release. See
[`packaging_validation.json`](../output/release/packaging_validation.json).

## Proposed claim and scope

The defensible extension is an experimental finite-control-graph checker for
the same narrow property as the bounded AST analysis: equality of the modeled
per-contract usage-event prefixes across any two executions that agree on
public inputs but may choose different secret-controlled edges. It is a
workflow-graph application of established relational verification, not a new
general bisimulation, product-program, or noninterference theory.

The graph has finite states for `call`, `publicguard`, `secretguard`, `goto`,
and `stop`. A call node stores a resolved model contract, exact template bytes,
and ordered arguments that are literals, shared public-input identities, or
register references. The abstract request descriptor is this DSL data; it is
not the provider's serialized request. A public guard is from the supported
finite predicate fragment. A secret guard has two possible successors. Every
register and state reference is graph-local and statically resolved.

This JSON graph is a model. Unless a separate, sound source-to-graph
translation is implemented and checked, accepting a graph does not prove that
an OrchLang program, framework workflow, or running agent is faithfully
represented by it. Guard labels, input identities, model contracts, and
register assignments are assumptions supplied by the graph author. The graph
checker must be described as an experimental graph checker, not as a second
source-language frontend or independent source-level proof.

## Relational state and transition rules

For one graph self-composed with itself, a product work item is
`(pcL, pcR, R)`. `pcL` and `pcR` are control states. `R` is a finite relation
between left and right registers that currently denote equal abstract values.
Initialize it only with pairs of inputs that have the same declared public
identity; the proof premise is that those input values agree in the two runs.
Secret inputs are not related by default. A matched model call can add an
output-register pair because the shared oracle gives equal abstract outcomes.

The worklist must explore every feasible pairing of secret choices:

* `goto` advances silently on either side to allow control-flow alignment.
* A secret guard advances either side through every outgoing edge; when both
  sides are at secret guards, explore the Cartesian product of successors.
  This is universal over both runs' secret choices, not a sampled path.
* A public guard can advance only when its normalized predicate is supported,
  its operands are paired by `R`, and its bound/operator agree with the paired
  public predicate. The two executions take the same successor. A graph whose
  public tests cannot be aligned is rejected conservatively.
* A call advances only when both sides are at calls with the same complete
  resolved contract, exact template bytes, and ordered arguments. Literal
  arguments must be identical; public inputs must have the same public
  identity; register arguments must be related by `R`. The input-charge
  premise must make matching descriptors have equal input usage. Calls also
  use the same per-contract ordinal: if every prior visible call in the pair
  matched contract-by-contract, these ordinals are equal inductively. Under
  the shared oracle `Ω(c,k,Q)`, output usage and the complete modeled result
  then agree. Remove any old relation involving either overwritten result
  register and add the new result-register pair.
* `stop` succeeds only against `stop`. A stop against a call or an unmatched
  control state is a counterexample/rejection.

The billing event is `(resolvedContract, inputUsage, outputUsage)`. Requiring
calls to match in global order is stronger than equality after grouping events
by contract, so the graph checker may conservatively reject cases whose
per-contract projections agree but whose cross-contract interleaving differs.
No completeness claim follows from acceptance/rejection.

### Progress and cycles

Reject any reachable cycle consisting only of call-free control states. An
implementation can detect this by removing call nodes and checking whether any
reachable strongly connected component still contains a cycle. This includes
silent `goto` cycles and loops whose only nodes are guards. The restriction
avoids treating an infinite internal divergence as harmless stuttering and
ensures that every infinite execution of an accepted graph performs infinitely
many visible calls.

Cycles that include calls can be checked coinductively by the finite product
worklist. Register relations range over a finite set of register pairs; the
product domain is finite, though potentially large. A configurable node/state
cap is an engineering bound only: exceeding it must return `unknown` or reject,
never accept. A replayable certificate should bind the input graph hash and
semantic version, list the initial relation and every reachable product node,
and provide every required successor and local call/guard justification. A
replayer must reconstruct the closure and reject omitted successors or invalid
relations; it must not trust a checker-produced `safe: true` flag.

## Soundness sketch and exact guarantee

Suppose (1) both runs start from the same graph and agree on values for each
public-input identity; (2) all graph nodes and classifications faithfully
represent the abstract program being claimed; (3) equal `(c,k,Q)` keys under
the same shared oracle give equal complete abstract call outcomes; (4) matching
abstract requests have equal charged input usage under the declared full
request-accounting premise; and (5) there is no confidentiality declassification.

The worklist's reachable set is an inductive invariant over paired control
states and `R`. `goto` does not change the observation. Related operands and
equal normalized predicates make paired public decisions agree. Universal
secret-successor expansion covers every pair of secret choices. At a call,
the request descriptors match, and all previous visible calls matched, so the
contract-specific ordinals match. The shared-oracle premise supplies the same
output usage and equal modeled result; the event matches and the result pair
can safely extend `R`. Synchronized stops close finite executions. By induction
on the number of visible calls, every finite usage-event prefix is equal for
every paired execution. Coinductive closure covers arbitrarily many iterations
of a billable cycle.

For graphs with unbounded call cycles the conclusion is **prefix equality of
usage-event traces** only. The checker does not derive a finite total-token,
price, or call-count bound for such a graph. Any unary cost analyzer that only
supports bounded syntax remains separate and must reject or leave unbounded
cycles uncertified. The graph checker remains a deterministic shared-oracle
analysis: it does not encode or verify stochastic provider kernels. A separate
conditional identity-coupling corollary for matched secret-independent kernels
is stated in [`FORMAL_CONTRACT.md`](FORMAL_CONTRACT.md); it is not checked by
this artifact and is not provider evidence. The checker proves nothing about
actual invoice records, tool effects, output confidentiality,
prompt-injection resistance, or timing. The current graph fragment also
excludes dynamic graph discovery, arbitrary expressions, concurrency, and
implicit runtime retries unless they are explicitly encoded and modeled.

## Red-team coverage present in the frozen prototype

The 17 graph fixtures, producer regressions, and separate replayer regressions
cover the principal proof-boundary cases below. They test authored models, not
bugs in the upstream workflow frameworks.

| Case | Current evidence |
|---|---|
| Overwriting a result must remove stale register-equality pairs | `overwritten_result_relation.json`; producer and replayer overwrite tests |
| Resolved contract identity, alias-equivalent calls, and cap/model mismatch | `canonical_alias_cycle.json`, `model_cap_mutation.json`; replayer tests for contract and model-id mismatch |
| Template bytes, literal arguments, argument order, public-input identity | `request_template_mutation.json`, `literal_result_mutation.json`; separate replayer tamper tests |
| Related prior result used by a dependent call | accepted chain/cycle fixtures and replayer's secret-choice/dependent-call test |
| Public guard subject, operator, limit, and related-value checks | `unmatched_public_guard.json`; producer and replayer guard tests |
| Universal secret-successor expansion and call/stop mismatch | `one_sided_private_transition.json`; producer and replayer tests |
| Silent-cycle rejection and productive billable-cycle closure | `private_silent_cycle.json`, `matched_cyclic_chain.json`, `unbounded_productive_cycle.json`; call-free and productive-cycle replayer tests |
| Counterexample against hiding shifted events behind total equality | `private_termination_count.json`; finite full-trace and billing-vector witnesses |
| Resource caps fail closed; malformed, omitted, extra, or altered certificate facts are rejected | producer cap regression plus replayer tests for closure, source hashes, schema, rules, nodes, edges, and relations |
| Initial public values pair by identity; no finite budget for an unbounded cycle | initial-relation replay checks; productive-cycle certificate explicitly states prefix-only scope |

The separate graph-grid report binds every fixture to its source hash and
records full-trace and billing-vector witnesses independently. A rejected
fixture without a finite witness would be unknown as an empirical false
positive; the current finite grid reports witnesses for all eight rejected
fixtures.

## What this adds—and what it does not

Self-composition, product programs, 2-safety reductions, control-flow
alignment, loop reasoning, and resource-aware noninterference are established
ideas. Barthe, D'Argenio and Rezk present self-composition for secure
information flow; *Product Programs and Relational Program Logics* compares
product constructions and relational logics for properties including
noninterference and describes loop synchronization. Ngo et al. already combine
information-flow and resource analysis to enforce resource-aware
noninterference. RelCost already compares resource use across executions.
These sources rule out presenting a product worklist or cyclic coinduction as
new general theory.

The implemented and replayed method delta is an executable finite
workflow-graph specialization whose visible transition is a resolved external
model call with an exact abstract request descriptor, whose result-register
relation is justified by `Ω(c,k,Q)`, and whose observer is per-call usage. It
extends the bounded-AST artifact to coinductively checked billable cycles. The
demonstrated value is workflow-shape support and a precise reusable contract;
the theory remains an application of relational verification.

The separate source bridge snapshots the parsed source and compiler binary,
runs the compiler gate on those snapshots, then checks and independently
replays the emitted graph certificate. Its 12 tests cover matched chains,
lexical shadows, nested branches, type-erased literal rejection, identifier
outputs, unsupported source, and source replacement between parse and
compiler gate.

The corpus evaluation attempts five existing accepted examples and fifteen
balanced source-derived inputs without rewriting prompts or outputs. The
compiler accepts all twenty; the bridge exports seventeen and explicitly
excludes three retry examples. Across the seventeen exported files, the finite
grid records 720 source/graph run pairs, 360 secret-trace comparisons, and
1,584 call events with zero source/graph or secret-trace differences. It uses
seeds 1, 17, and 29 and bounded public/secret values, including UTF-8. The
source interpreter and graph probe are distinct evaluators for the same
authored deterministic oracle; output values are recorded separately because
the graph observer covers billing requests, usage, and stop only. This is
finite lowering evidence for the tested subset, not a proof of translation or
an independent application study. A successful graph replay remains evidence
about the graph and does not prove that an arbitrary OrchLang program was
translated faithfully. The evidence supports a modest software contribution,
not an 8/10 general novelty claim absent outside use or a substantially new
formal result. Per-file hashes and generated artifacts are in
[`source_graphs/evaluation.json`](../bench/results/source_graphs/evaluation.json)
and [`SOURCE_GRAPH_BRIDGE.md`](SOURCE_GRAPH_BRIDGE.md).

### Primary sources

- Barthe, D'Argenio & Rezk, [*Secure Information Flow by Self-Composition*](https://doi.org/10.1109/CSFW.2004.1310735), IEEE CSFW 2004.
- Barthe, Crespo & Kunz, [*Product Programs and Relational Program Logics*](https://www.sciencedirect.com/science/article/pii/S235222081630044X), *Journal of Logical and Algebraic Methods in Programming* 85(5), 2016, DOI [10.1016/j.jlamp.2016.05.004](https://doi.org/10.1016/j.jlamp.2016.05.004).
- Ngo et al., [*Verifying and Synthesizing Constant-Resource Implementations with Types*](https://doi.org/10.1109/SP.2017.53), IEEE S&P 2017; [primary conference PDF](https://www.ieee-security.org/TC/SP2017/papers/408.pdf).
- Çiçek et al., [*Relational Cost Analysis*](https://doi.org/10.1145/3009837.3009858), POPL 2017.
