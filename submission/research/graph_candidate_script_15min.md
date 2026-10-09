# Provisional 15-minute script

**Title:** “OrchLang: Replayable Contracts for Token Usage and
Request-Equivalent LLM Workflows.” The novelty assessment remains subject to
the final literature and venue review.

## 1. Can a secret change the model-usage trace?

The motivating observation is simple: an LLM workflow can keep a secret out of
the prompt and still let it select a model call, a request, or a loop exit. If
the external observer sees itemized model usage, that control choice can
change an observable trace. Today I’ll define exactly which trace, explain a
relational product checker for a finite cyclic JSON graph, keep it distinct
from the existing bounded OrchLang compiler, and separate the proof claim
from the experiments.

## 2. A secret can change when a call loop stops

This authored graph fixture is a small counterexample. The public query is
fixed to the empty string and the run uses seed 1. For `route=false`, the
workflow makes one call and stops. For `route=true`, the first call matches,
but the other graph path reaches another call before its public guard stops.
At event 1, one run is at stop and the other is at a call. This is a finite
offline mock witness. It is not a live provider or invoice result, and it does
not tell us a finite maximum cost for the graph.

The example is useful because the graph has a possible back-edge. A finite
unrolling would need an externally chosen loop limit; the checker instead
checks a finite product of graph states. That finite product is the object I
will define next.

## 3. The cyclic checker is a separate JSON graph front end

There are two analysis inputs in this project. The frozen OrchLang compiler
is C++17 and accepts a bounded source language. Its AST admits branches,
calls, literal-bounded retries, tools, and outputs, but no general
unbounded-loop syntax. The new prototype is a separate Python tool that reads
a versioned `orchlang-request-graph` JSON model. The JSON states represent
calls, public and secret guards, gotos, and stops, and can contain
back-edges.

This distinction matters. The graph checker is not a graph intermediate
representation produced by the C++ compiler, and the two artifacts do not
share a parser. An accepted JSON graph says something conditional about that
model. It does not establish that a framework, an OrchLang source file, or a
running agent has been translated faithfully into the model.

## 4. Compare usage-event prefixes under a shared oracle

For a graph execution, the observer is an ordered sequence of visible model
events. Each event records a resolved model contract, input usage, and output
usage. Runs start with equal values for each paired public-input identity;
their secrets may differ. Calls are related by
`Ω(contract, per-contract index, exact DSL request)`. Here the request means
the modeled template bytes and ordered literal, public-input, or register
arguments—not the provider’s complete serialized payload.

If the same key produces the same complete abstract response and usage, the
result registers can be related after a matched call. The theorem is
pathwise under that oracle. It does not compare independently sampled runs
or assert distributional equality. For a productive cycle, the checked
conclusion is equality of every finite usage-event prefix. It is not
termination, a finite total-token bound, a finite price bound, or a finite
call-count bound.

## 5. The product state pairs control and related registers

The main work item is `(pcL, pcR, R)`. `pcL` and `pcR` are the states of two
executions of the same graph. `R` is a relation between left and right
registers that are justified to hold equal abstract values. The initial
relation contains only public-input pairs sharing the same declared identity.
Secret values are not paired by default.

At a matched model call, both sides must have the same fully resolved
contract, exact decoded template, and ordered arguments. Literals are equal
by content. Public inputs match by identity. Register arguments match only
when they are related by `R`. After shared `Ω` justifies equal outcomes, the
result pair is added. If an assignment overwrites a register, any older pair
using that register is removed first. This last rule is what the witness on
slide 9 exercises.

## 6. Every secret successor pair must be checked

The product search is universal over secret choices. When both sides reach a
secret guard, the checker explores the Cartesian product of their possible
successors. A public guard advances only if both guards have the same
normalized predicate and their tested registers are related; then the runs
take the same successor. Gotos can advance silently so that graph layouts can
align. A call is compared with a call, and stop with stop. A stop/call pair
rejects.

This is a finite worklist over reachable product states, not an evaluation
over a finite list of secret samples. The finite domain comes from finite
graph states and a finite relation over register pairs. The implementation
has a product-state resource cap; hitting the cap must return unknown or
fail closed. Reachable cycles that contain only control and no calls are
rejected, so the accepted coinductive case is productive in the modeled
usage observation.

## 7. A productive cycle can close coinductively

In the accepted `unbounded_productive_cycle` fixture, each side issues a call
using the shared public query, then a second call using the corresponding
first result, then jumps back to the same choice state. Once both sides have
matched the two requests, their result registers are related. The product
returns to a previously reached control/relation state and closes the cycle.

That finite closure supports arbitrarily long finite prefixes under the
relational invariant. The separate reference probe is capped at 120 calls
per run; this fixture records 24,000 simulated calls and 200 truncated runs.
Those simulations are finite implementation checks. They are not the reason
the checker accepts the cycle, and the certificate contains no cumulative
budget or price bound for it.

## 8. A separate replayer reconstructs the product closure

The graph producer writes a certificate containing the reachable product
graph. A distinct Python replayer strict-parses the JSON graph, binds the raw
source hash, recomputes reachable source states and abstract cost summaries,
checks the initial public-input relation, and reconstructs product nodes,
local rule applications, register relations, successor identifiers, and the
complete closure. It rejects missing or extra nodes, omitted universal
successors, malformed relations, and cap violations.

The current replay suite has 33 tamper and semantic tests. This is useful
implementation evidence; it is not a mechanized proof of the relational
theorem. The attestation records the producer hash but explicitly does not
verify that hash. It also does not check a source-to-graph translation.

## 9. Overwriting a result must erase its old pairing

This graph mutation illustrates why the register relation is explicit. On
the left, call zero stores into `a`; call one stores into `a` again, replacing
it. On the right, call zero stores into `x`; call one stores into `y`. After
call one, the relation pairs the newly written `a` with `y`. It must not keep
the old `a`-to-`x` relation. The next call uses `a` on the left and `x` on the
right, so the requests cannot be proved equal.

The finite probe reports a first difference at event two: input usage 10 on
one side and 15 on the other. That is one precise mock witness from the
authored grid. It demonstrates the check's value-sensitive bookkeeping; it
does not turn every rejected graph into a measured bill leak.

## 10. Unary bounds and relational checks answer different questions

The current C++ compiler has a unary resource analysis for its finite
language. It computes output, input, and total token envelopes under declared
caps and input-accounting assumptions. The graph product is relational: it
compares paired usage prefixes. The two properties are related but neither
subsumes the other. In particular, the C++ finite-syntax bound must not be
ported to an unbounded graph cycle without a separate analysis.

## 11. Equal caps still do not imply equal realized usage

The bounded OrchLang counterexample motivates the relational question. Two
public inputs have the same maximum declared token length and the same model
call shape. A secret selects which input is used. The unary envelope is
equal, yet a fixed concrete pair can have different rendered request lengths.
This illustrates why “both paths are under the cap” is not the same as “the
two observations are equal.” It remains a separate bounded-AST example, not
input to the graph checker.

## 12. The existing compiler remains a finite OrchLang pipeline

The C++ artifact still has its original compiler stages: lexer and parser,
scoped name/model resolution, semantic facts, flow and cost analysis,
relational checks, certificates, diagnostics, and an offline interpreter.
The relational upgrade handles matching dependent calls in bounded secret
alternatives. It still rejects unsupported or unmatched requests. No live
provider call is made. The graph checker is another research artifact, not a
replacement parser or grammar extension.

## 13. Generated C++ cases were checked against full request text

The full-text stress study generated 264 programs: 144 positives and 120
controlled mutations. The C++ compiler’s `check` command accepted all
positives and rejected all mutations. A separate Python reference interpreter
substituted complete strings into templates. It performed 24,192 executions
and compared 13,824 accepted secret-assignment pairs. It found zero request
or usage mismatches and performed 66,240 per-call accounting checks.

For rejected cases, 117 mutations had a finite request-and-usage witness.
Three retry-bound mutations had no witness in the finite grid. Their status
is unknown, not proof of a false positive. The generated source shares an AST
with the reference generator; the Python run is separate from the C++ runtime
and analysis facts, but it is not an independent source parser. The one-byte
per-token assumption and cap-respecting oracle are controlled test premises,
not provider billing guarantees.

## 14. Eight rejected graph fixtures have billing-vector witnesses

The graph corpus has 17 authored cases: six accepted, eight rejected, and
three invalid. All six accepted product certificates were replayed. The
finite reference probe ran 1,400 executions and 800 accepted
secret-assignment comparisons. It found no difference in request descriptors,
billing vectors, or complete traces. It also ran 28,580 call-accounting checks.
All eight rejected fixtures have billing-vector witnesses. A witness covers
the complete run when both sides stop. Otherwise it covers at most 120 calls.

The fixture set is authored and small. It is not a collection of full
framework ports, not an exhaustive graph generator, and not a proof of the
checker’s semantics. The independent replay establishes the reported
certificate closure under the graph rules; it does not validate the graph's
relationship to a deployment.

## 15. The graph product compares model requests across executions

Self-composition and product programs provide established ways to reduce
relational properties to single-system reachability. Resource-aware
noninterference and RelCost already address resource observations and
differences between executions. A relevant 2026 author-reported, unrefereed
Petri-net paper studies unary cumulative cost bounds on LLM-agent workflow
graphs. Agentproof and AgentFlow are preprints with static workflow checks;
PPDL models uncertainty through LLM and tool flows.

The narrow software/method delta is an executable graph specialization in
which visible transitions are resolved model calls, request atoms and
result-register relations are explicit, productive cycles close in a finite
product, and a separate replayer checks the reported closure. I do not claim
that graph verification or resource analysis is new. The novelty rubric and
venue fit assessment will be reported only after the literature review is
final.

## 16. A generated graph probe adds adversarial coverage, with a shared reference

A seeded generator produced 3,000 small graphs. The checker accepted 1,462;
the probe then compared 11,696 ordered pairs of stores with the same public
values, including 5,848 pairs with different secret stores. Across prefixes
capped at 20 calls, it saw no difference in requests, usage, response bytes,
or stop/truncation status.

The caveat belongs in the same breath: the generated graph and reference run
share the producer's `reference_run` implementation. This is a property-based
stress probe, not an independent semantic checker. It complements the
authored fixture experiment; it must not be summed with that study or the
C++ AST stress test.

## 17. The checker reports results for a declared graph model

The promise is conditional on faithful graph modeling, equal public inputs by
declared identity, shared Ω, and the full-request usage-accounting premise.
The checker does not prove the graph came from OrchLang or from a framework.
It does not implement or test provider serialization, actual invoices,
tokenizer boundaries, runtime effects, timing, or output confidentiality. It
does not establish termination or a finite total cost for an unbounded
productive cycle. Certificate replay narrows trust in the certificate
producer; it cannot make those assumptions disappear.

## 18. Productive cycles support usage-prefix equality

The conclusion is deliberately restrained. The C++ compiler handles bounded
AST workflows. The separate graph checker explores paired graph states and
can close cycles coinductively. Under its graph, oracle, and accounting
contracts, its acceptance supports equality of every finite modeled
usage-event prefix. The finite evaluations support implementation behavior;
they do not replace the proof obligations or establish deployed workflow
fidelity. This contribution should be assessed against that precise claim,
not a broader promise about all LLM agents.
