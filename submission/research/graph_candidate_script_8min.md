# Provisional 8-minute script

**Title:** “OrchLang: Replayable Contracts for Token Usage and
Request-Equivalent LLM Workflows.” The deck cover shortens this to “OrchLang.”

## 1. Can a secret change the model-usage trace?

Imagine the prompt contains only a public support ticket. A secret still might
choose a model-call path—or decide when a loop stops. If a system exposes
itemized usage, that secret can affect an observable trace without entering
the model prompt. I’ll focus on that narrow property and two separate analysis
artifacts.

## 2. A secret can change when a call loop stops

Here is one finite counterexample from the JSON graph fixtures. Hold the public
query empty and choose seed 1. With `route=false`, the workflow calls once and
stops. With `route=true`, it takes one more call before the public result guard
stops. The first event is shared; at the next event, one side has stopped and
the other calls. This is an offline mock witness, not a live invoice.

## 3. The cyclic checker is a separate JSON graph front end

The existing C++ compiler still accepts OrchLang source and analyzes a finite
AST. It can express literal bounded retries, but it is not a general cyclic
graph checker. The experimental Python checker accepts a versioned JSON model
with calls, public and secret guards, gotos, and stops. Those are separate
inputs. The graph does not prove that a framework or source program translates
faithfully into it.

## 4. Compare usage-event prefixes under a shared oracle

The graph property compares ordered per-call events: resolved model contract,
input usage, and output usage. The runs agree on public input identities but
may differ on secret values. Matching calls share an outcome under
`Ω(contract, per-contract index, exact DSL request)`. For an accepted
productive cycle, the claim is equality of every finite usage-event prefix.
The claim does not imply termination or a finite total-cost bound.

## 5. The product state pairs control and related registers

The worklist explores `(pcL, pcR, R)`: a left control state, a right control
state, and a relation between registers known to hold equal values. Public
inputs are paired by declared identity. A call result is paired only after
both requests match and the shared oracle supplies aligned outcomes.

## 6. Every secret successor pair must be checked

Secret guards expand universally over all left and right successor pairs.
Public guards synchronize only when the normalized tests match and their
operands are related. Calls must have the same resolved contract, exact
template bytes, and ordered arguments. Stops must align. Gotos are silent; a
reachable call-free cycle is invalid. If the product-state cap is exceeded,
the checker fails closed rather than accepting.

## 7. A productive cycle can close coinductively

In this accepted graph, each side calls on the same public query, calls again
on its related result, then returns to the same paired control state. The
finite product closure supports arbitrarily long finite prefixes. Its separate
reference probe stops after 120 calls per run and includes truncated runs;
that simulation is not the coinductive argument and supplies no total budget.

## 8. A separate replayer reconstructs the product closure

The certificate names the input graph and lists the product states and edges.
The replayer parses the source again and reconstructs the root relation,
states, local rules, and complete closure. It rejects missing, extra, or
malformed items. The current graph-replay suite has 33 tamper and semantic
tests. Replay checks the modeled graph rules; it does not verify source
translation or mechanize the relational theorem.

## 9. Overwriting a result must erase its old pairing

This rejection is a useful precision point. The left execution writes register
`a`, then overwrites `a`; the right writes `x`, then `y`. After the overwrite,
the relation pairs the new `a` with `y`, not the old `x`. A later request using
`a` versus `x` therefore cannot be justified. One finite mock probe finds
input usage 10 versus 15 at event 2. It illustrates why the relation must track
value identity, not just bounds.

## 10. Unary bounds and relational checks answer different questions

The C++ compiler has a one-run bound for its admitted finite programs. The
graph checker compares two runs. Neither result should be substituted for the
other: the graph product does not inherit a finite total-token bound for
unbounded call cycles.

## 11. Equal caps still do not imply equal realized usage

The bounded OrchLang baseline makes the same point with two public text
arguments that have equal declared caps. A secret chooses which request is
made. Matching worst-case envelopes do not imply matching realized request
usage.

## 12. The existing compiler remains a finite OrchLang pipeline

The C++ pipeline stays intact: parse source, resolve names and model
contracts, run information-flow, unary-cost, and relational checks, then emit
certificates and diagnostics. Its interpreter is an offline mock. The JSON
product checker is a separate research tool, not a new OrchLang syntax.

## 13. Generated C++ cases were checked against full request text

The compiler accepted 144 generated balanced programs and rejected 120
mutations. A separate Python reference ran 24,192 executions and compared
13,824 accepted secret-assignment pairs. It found zero request or usage
mismatches and performed 66,240 per-call accounting checks. Of the rejected
mutations, 117 had finite request-and-usage witnesses; three retry mutations
remain unknown in the chosen grid. These are synthetic cases, not provider
tests or exhaustive language coverage.

## 14. Eight rejected graph fixtures have billing-vector witnesses

The graph corpus has 17 authored cases: six accepted, eight rejected, and
three invalid. All six accepting certificates replayed. The finite probe
checked 1,400 accepted runs and 800 secret comparisons with no request,
billing-vector, or complete-trace differences, plus 28,580 call-accounting
checks. All eight rejected fixtures have billing-vector witnesses. A witness
covers the complete run when both sides stop; otherwise it covers at most 120
calls.

## 15. The graph product compares model requests across executions

Self-composition, product programs, resource-aware noninterference, and
relational cost analysis are established. Kevin Dickerson’s May 2026
author-reported, unrefereed Petri-net paper studies unary cumulative cost
bounds on LLM workflow graphs. Agentproof and AgentFlow are adjacent
preprints with static workflow checks. The narrower delta here is matching
ordered model-call events across secret alternatives, with a request-linked
register relation and a replayable product closure.

## 16. A generated graph probe adds adversarial coverage

The small-graph generator produced 3,000 graphs and 11,696 paired stores; it
observed zero differences across request, usage, response bytes, and
stop/truncation status. Its generator and reference use the producer’s own
module, so this is supplementary coverage, not independent semantic
validation.

## 17. The checker reports results for a declared graph model

Acceptance relies on a faithful graph model, the declared oracle, and complete
request accounting. The work does not establish source-to-graph fidelity,
provider serialization or billing, timing, tool effects, output secrecy,
termination, or finite cumulative cost. Certificate replay verifies the
product closure under the JSON rules—not that the rules describe a deployed
agent.

## 18. Productive cycles support usage-prefix equality

The main result is a conditional relation over usage-event prefixes in an
explicit finite graph model. The method applies established relational
reasoning to model-call events and supports productive cycles through a
checkable finite product. The graph and its meaning remain assumptions; a
separate publication assessment should follow the completed literature and
venue review.
