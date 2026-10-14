# LangGraph source semantics audit

**Scope.** This audit covers the Python source extractor in
`integrations/langgraph/source_frontend/`, its mapping into the request-graph
IR, and the straight-line atomic-update proof in
`proofs/publication_upgrade/`. It does not establish correctness of the full
OrchLang toolchain or of arbitrary Python/LangGraph programs. The runtime
checks below used Python 3.14.6 and LangGraph 1.2.14 from the task's isolated
environment.

## Findings and dispositions

### 1. Reserved LangGraph node names caused a real source/runtime mismatch

The extractor accepted any nonempty Unicode node name, then replaced the
source name with an internal `lg_state_NNNN` name in its output. Consequently,
it could export a graph for source that the pinned LangGraph builder refuses
to compile. A minimal witness is:

```python
builder = StateGraph(State)
builder.add_node("__start__", run)
```

The original frontend accepted this node and lowered it to a private state
name; LangGraph 1.2.14 raises `ValueError: Node '__start__' is reserved.` Its
`StateGraph.add_node` implementation also rejects `__end__` and names
containing its namespace separators `|` and `:`. These checks apply before
the frontend's renaming can help. The extractor now rejects all four forms
before lowering, with regression coverage in
`test_langgraph_reserved_node_names_are_rejected_before_lowering`.

This was a concrete validity gap: the exporter could attest a graph for source
whose actual framework builder would fail. The fix mirrors the pinned
framework's current naming boundary; if the adapter changes its supported
LangGraph version, this compatibility rule should be rechecked against that
version's `StateGraph.add_node` implementation.

Primary implementation source: [LangGraph 1.2.14 `StateGraph` source](https://github.com/langchain-ai/langgraph/blob/1.2.14/libs/langgraph/langgraph/graph/state.py).

### 2. Python 3.14 can change a `TypedDict` annotation after its class body

The frontend reads a field written `query: str` as the builtin text type and
`private: bool` as the Boolean type. In Python 3.14, annotations are lazily
evaluated by default. The task environment reproduced this case:

```python
class State(TypedDict):
    query: str

def str(state):
    return {}
```

After the function definition, `State.__annotations__["query"]` and
`typing.get_type_hints(State)["query"]` resolve to the function `str`, not
`builtins.str`. LangGraph obtains type hints from the schema, so the runtime
schema metadata no longer agrees with what the frontend inferred from the
annotation spelling. A function named `str` before the class causes the same
shadowing directly; `bool` has the analogous issue.

This is a schema-interpretation mismatch, not evidence that `TypedDict`
performs runtime input validation or that the witness leaks a secret. In the
reproduction, LangGraph still created a `LastValue` channel, and `TypedDict`
annotations do not validate dictionary values at runtime. The sound response
for this deliberately typed subset is to reject either builtin name if any
top-level function shadows it, regardless of whether the function appears
before or after the class. `_validate_state` now performs that check after
the module has been parsed; the test covers both orders for `str` and `bool`.

The version dependence matters: Python 3.14's lazy annotation model differs
from earlier eager evaluation, and the source frontend does not execute the
submitted code to discover the runtime schema. Rejecting both orders keeps
the accepted source subset stable across supported Python versions.

Primary language references: [Python 3.14 class-definition execution](https://docs.python.org/3.14/reference/compound_stmts.html#class-definitions), [Python 3.14 annotation introspection](https://docs.python.org/3.14/library/annotationlib.html), and [PEP 649, deferred evaluation of annotations](https://peps.python.org/pep-0649/). The behavior was also reproduced with the pinned Python interpreter and `typing.TypedDict`; the PEP and docs explain the lazy lookup mechanism, while the local reproduction establishes the concrete `TypedDict` result.

### 3. Atomic returned-state updates are the right boundary for eager registers

LangGraph node functions read the node's input state and return a partial
state update. In the supported straight-line body, the source reads
`state["draft"]` from that input snapshot throughout the invocation. The
lowered IR writes a call result into its state register as soon as that call
is processed. Therefore, this source can diverge if `draft` is returned from
an earlier request and read later in the same node:

```python
def write_and_read(state):
    draft = request(model="m", template="draft", arguments=[state["query"]])
    answer = request(model="m", template="answer", arguments=[state["draft"]])
    return {"draft": draft, "answer": answer}
```

The source's second request sees the entry value of `draft`; an eager-register
lowering would see the newly generated draft. `_parse_nodes` rejects a read
when its call index is strictly later than the call whose result is returned
in that field. It allows a read before that writer, or in the writer call's
own arguments, because those reads still occur before that call's result
exists. This is a conservative check: it does not try to prove that a new
response happens to equal the old value.

The check matches the accepted grammar: node bodies contain only unique
`local = request(...)` assignments followed by one plain returned dictionary.
Other statements, mutation, effects, early returns, and dynamic calls fail
closed. Thus no unmodeled statement in a node can read or mutate the state
between the inspected request reads. Existing tests cover the rejecting
read-after-write case and a positive case where later requests use the
earlier local result explicitly.

### 4. Current mechanized result and its limit

`AtomicUpdates.v` defines a normalized straight-line call IR. Its source
semantics reads state fields from a fixed node-entry snapshot; its lowered
semantics can update a result register after each call. The premise
`safe_after` says that a request does not read a field already written by an
earlier returned-result call. `atomic_update_request_trace_refines_from`
proves that, if the current lowered store agrees with the source snapshot on
all not-yet-written fields, both executions produce the same request/response
history and local-result environment. The equal-initial-store corollary starts
with no fields written. The oracle is an arbitrary deterministic function of
the prior history and request, so the proof covers adaptive deterministic
responses pointwise; it does not itself prove equality of probability
distributions for randomized providers.

The frontend invariants needed to relate this IR condition to parsed source
are explicit in code. Request-result locals are assigned once, returned
state keys are unique, and `_parse_return` rejects reusing one local for
multiple state fields. `_lower` converts that unique `field -> local` map to
the register mapping consumed by the IR. This prevents duplicate-local
ambiguity in `field_for_local`; the Coq theorem itself does not encode the
frontend's injectivity invariant.

The theorem does **not** state that the final returned state is equal, does
not model the actual AST parser or prove that it emits the normalized IR,
and does not prove LangGraph's execution semantics, graph-level branch
refinement, contracts, bounds, or noninterference. It establishes a narrow
but relevant IR theorem for the atomic-update side condition. Its proof is
not a mechanization of the full source-to-IR compiler.

The file compiles with Rocq 9.3.0, compiled with OCaml 5.5.1. Compiling
`Assumptions.v` prints `Closed under the global context` for both main
theorems. No axioms or admitted goals are used in this new development. The
imports use Coq's legacy `From Coq` namespace for compatibility with earlier
Coq releases. This run checked Rocq 9.3 only; it reports that namespace as
deprecated, but compiles it successfully.

### 5. Review of existing control-flow and effect handling

The extractor accepts one class, a finite set of top-level functions, a
single builder, literal node registrations and edges, and one final compile
assignment. It checks the complete module statement-by-statement. Node
functions reject every statement except the recognized local request
assignment and final return; router functions are separately restricted to
the supported predicates. Route labels and targets are checked against the
literal two-way map, and unsupported imports, statements, state mutation,
parallel fan-out, retries, effects, reducers, and dynamic graph APIs are
rejected rather than omitted from the IR. The existing source frontend test
module passed after the changes (22 tests).

This inspection did not find a second dropped-statement or route-target
counterexample in the accepted subset. That is a bounded review conclusion,
not proof that every accepted Python AST has correct semantics; the new
reserved-name counterexample demonstrates why runtime-version-specific
differential fixtures remain useful.

### 6. Older Coq development: useful theory, no current-source theorem

The recovered `origin/claude/new-session-tvgdhj:proofs/OrchLang.v` develops
results for an abstract OrchLang core calculus. Its README says the C++
implementation is not verified against that model, and the file header
repeats that limitation. The old development compiled in a temporary folder
with the available Rocq 9.3.0, and its seven `Print Assumptions` checks each
reported `Closed under the global context` (with expected deprecation
warnings for Coq-era syntax). This confirms that the old proof is buildable;
it does not connect its core-calculus rules to the current Python extractor,
LangGraph runtime, or current signature implementation. It remains a separate
abstract result and is not used as evidence for the new source-adapter claim.
