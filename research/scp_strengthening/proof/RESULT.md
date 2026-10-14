# Returned-state and finite-prefix refinement proof

## What is proved

[`SequentialUpdates.v`](../../../proofs/scp_strengthening/SequentialUpdates.v) extends the existing normalized request-node model in [`AtomicUpdates.v`](../../../proofs/publication_upgrade/AtomicUpdates.v). It proves two results without axioms or admitted goals.

`node_commit_refines_from` starts with source node-entry state `S` and eager target state `T` that agree on every text field. For an ordered call list `C` and return map `W`, it assumes:

- `safe_after [] C W`: after a call has written a returned field into the eager store, later calls in that node do not read that field through a state-field atom;
- returned fields are unique, returned locals are unique, and call result locals are unique;
- every returned local is produced by one of the calls.

Under those conditions, source and target have equal abstract request/response histories and equal local-result environments. After the source node returns, applying `W` atomically to `S` is observationally equal, field by field, to the target state after its per-call eager writes. The source reads from fixed `S`; the target reads the evolving `T`. The equality premise and `safe_after` are the invariant that makes those request reads agree.

`finite_prefix_graph_refines_including_cycles` composes that node result over any finite number of node transitions. Its source and target graphs are separate lists of paired nodes. Each pair must have equal normalized calls, return maps, and decisions, with targets expressed as the same node indices. Route decisions can stop, jump, or branch on an immutable Boolean input or on a text field's token count using `<`, `<=`, `>`, `>=`, `==`, or `!=`. If the starting states agree, both executions have equal status, node index, abstract request/response trace, and final state after any finite prefix. A self-cycle is included; the theorem does not claim termination or equality of infinite executions.

The separate [`Counterexamples.v`](../../../proofs/scp_strengthening/Counterexamples.v) file machine-checks three failure witnesses: reading a just-returned field later in the same node changes a request; reusing one return local for two fields leaves one eager target register unwritten; and returning one field twice makes the source commit order disagree with the order of eager writes. It also checks a cyclic graph prefix reaches the explicit fuel cutoff while the two executions refine each other. [`Assumptions.v`](../../../proofs/scp_strengthening/Assumptions.v) runs `Print Assumptions` on the results and witnesses; every line reports “Closed under the global context.”

## Relation to the implementation

The model follows the current frontend's accepted node shape. [`extract.py`](../../../integrations/langgraph/source_frontend/extract.py) accepts only ordered `local = request(...)` assignments and one plain return dictionary ([lines 452–486](../../../integrations/langgraph/source_frontend/extract.py#L452), [491–563](../../../integrations/langgraph/source_frontend/extract.py#L491)). It permits literals, text `state['field']` reads, and earlier local results, and rejects other node statements. It rejects a state read whose call index is later than the call returning that field ([lines 474–481](../../../integrations/langgraph/source_frontend/extract.py#L474)). Its return parser rejects duplicate fields and reused result locals ([lines 540–563](../../../integrations/langgraph/source_frontend/extract.py#L540)). These checks are exactly the implementation facts needed for the `safe_after`, uniqueness, and return-completeness premises.

The lowering assigns a returned call's result to its stable state-field register and other call results to temporary registers ([lines 806–813](../../../integrations/langgraph/source_frontend/extract.py#L806)). A state-field atom is rewritten to its input or state register; a local-result atom is rewritten to its earlier call's result register ([lines 833–859](../../../integrations/langgraph/source_frontend/extract.py#L833)). The graph records `goto`, stop, and two-way guard decisions, translating source route labels to graph-state names ([lines 872–903](../../../integrations/langgraph/source_frontend/extract.py#L872)). The backend executes calls in list order, stores each response under the call's result register, then evaluates the route ([`backend.py`, lines 489–550](../../../integrations/langgraph/backend.py#L489)). This matches the proof's eager `state_after` step and the rule that a later node sees the preceding node's committed register values.

LangGraph's pinned 1.2.14 [`StateGraph` implementation](https://github.com/langchain-ai/langgraph/blob/1.2.14/libs/langgraph/langgraph/graph/state.py) and its [Graph API documentation](https://docs.langchain.com/oss/python/langgraph/graph-api) describe nodes as producing state updates that are applied through per-field reducers; the default behavior for these plain fields is replacement. The source model treats a node's direct state reads as reads from its invocation state and applies the returned update at node completion. The accepted grammar excludes state mutation and other statements that could invalidate that abstraction.

## Trusted bridge conditions and limits

This is a theorem about normalized IR records. It is not a proof that Python AST parsing, the extractor, graph JSON generation, the request-graph checker, certificate replay, or LangGraph runtime code constructs or executes those records correctly. The paired-graph premise `paired_graph_matches` is the explicit bridge condition: every source/target pair must preserve call order and descriptors, the return field/local map, route guard, and target node indices. Relating those logical names to emitted register names also remains outside Coq. The correspondence to the current lowering is inspectable in the locations above, but it is not yet a machine-checked source-to-IR theorem.

The frontend separately checks definite initialization for reachable result registers ([`extract.py`, lines 957–1020](../../../integrations/langgraph/source_frontend/extract.py#L957)). The Coq store has a total lookup that returns an empty string for an absent text key, while the actual backend raises on an uninitialized register. Therefore any source-to-runtime use of this theorem also needs the frontend's path-sensitive initialization condition. The proof does not establish that check's soundness.

The oracle is one shared deterministic function of abstract prior history and the current request. The abstract request contains model alias, template, and ordered text arguments; it does not contain the complete provider request, retries, token usage, costs, side effects, or errors. The proof makes no probability-law claim, no billable-usage claim, no confidentiality/noninterference claim, and no claim about equality when a runtime cap truncates in the middle of a node. Its finite-prefix fuel counts completed node transitions, not individual request events.

Boolean routing assumes immutable Boolean inputs; token-count routing assumes the same `estimate : text -> nat` function on both sides. The current Python parser recognizes those predicates and rewrites reversed comparisons, but their AST-to-descriptor equivalence is part of the trusted bridge. Public/secret route labels and graph-checker enforcement are not modeled by the proof.

## Traceability matrix

| Supported rule | Coq model and obligation | Current implementation location | Remaining bridge obligation |
|---|---|---|---|
| Ordered request assignments | `call`, `make_request`, `run_source`, `run_lowered` | [`extract.py`, 461–473 and 491–538](../../../integrations/langgraph/source_frontend/extract.py#L461) | The AST parser must emit exactly these ordered model/template/argument descriptors. |
| Literal and state-field arguments | `Literal`, `StateField`, `eval_atoms` | [`extract.py`, 515–531](../../../integrations/langgraph/source_frontend/extract.py#L515) | Source field names and emitted input/result registers must preserve the looked-up text. |
| Earlier local-result arguments | `LocalResult`, `local_reads_precede`; local environment updated per call | [`extract.py`, 532–538 and 840–846](../../../integrations/langgraph/source_frontend/extract.py#L532) | Emitted temporary/result register names must preserve lexical bindings and be overwritten before reuse in a cycle. |
| Atomic returned-state map | `commit_returns`; unique returned fields and locals; all return locals are calls | [`extract.py`, 540–563](../../../integrations/langgraph/source_frontend/extract.py#L540) | Parsed return dictionary and result-register map must be complete and injective. |
| Snapshot reads versus eager writes | `safe_after`; source snapshot fixed, lower state updated after each response | [`extract.py`, 474–481](../../../integrations/langgraph/source_frontend/extract.py#L474), [`backend.py`, 494–540](../../../integrations/langgraph/backend.py#L494) | Parser side condition must imply the Coq `safe_after`; each runtime node must receive its prior committed state. |
| Stop and direct edges | `Stop`, `Goto`, `choose_next` | [`extract.py`, 872–878](../../../integrations/langgraph/source_frontend/extract.py#L872) | Source targets and graph-state indices must match in each paired node. |
| Boolean route | `BooleanInput`; immutable Boolean store | [`extract.py`, `_router_test` at 691–725](../../../integrations/langgraph/source_frontend/extract.py#L691) | Boolean input type, lookup, and guard descriptor must be preserved. |
| Token-count route | `TokenCount`, shared estimator and six comparisons | [`extract.py`, 691–738](../../../integrations/langgraph/source_frontend/extract.py#L691), [`backend.py`, 466–486](../../../integrations/langgraph/backend.py#L466) | Parsed comparison normalization and token estimator must equal the supplied Coq estimator. |
| Sequential paths and cycles | fuel-bounded source/target graph executions | [`extract.py`, 903–955](../../../integrations/langgraph/source_frontend/extract.py#L903), [`backend.py`, 489–550](../../../integrations/langgraph/backend.py#L489) | Pairing all nodes by index and preserving route targets must be established; no termination claim follows. |
| Path-sensitive initialization | Not modeled as an error semantics | [`extract.py`, 957–1020](../../../integrations/langgraph/source_frontend/extract.py#L957), [`backend.py`, 450–463](../../../integrations/langgraph/backend.py#L450) | Prove or trust that every reachable request/guard register has been initialized. |

## Novelty and prior art

Semantic preservation by relating source and target executions, matching observable traces, and composing local simulation results is established compiler-correctness methodology. Leroy's primary CompCert paper presents semantic preservation in terms of observable behaviors and traces, describes induction over executions, and explains composition of verified passes ([paper](https://xavierleroy.org/publi/compcert-CACM.pdf); [CompCert manual](https://compcert.org/man/manual001.html)). The new mechanization should therefore not be described as inventing simulation, refinement, or compositional compiler correctness.

The defensible project-level claim is narrower: this proof adds a final returned-state result and a finite-prefix, routed-graph composition result to the existing OrchLang source-adapter IR evidence, with a mechanized distinction between a node-entry snapshot and per-call eager register writes. I did not establish priority or novelty against all workflow, state-machine, or compiler-refinement literature. Any stronger novelty claim needs a separate systematic prior-art review and, more importantly, a machine-checked theorem connecting the accepted extractor/lowering to these normalized records.

## Reproduction

With Rocq/Coq's `coqc` command available, run these from the repository root:

```sh
coqc -Q proofs/publication_upgrade PublicationUpgrade proofs/publication_upgrade/AtomicUpdates.v
coqc -Q proofs/publication_upgrade PublicationUpgrade -Q proofs/scp_strengthening SCPStrengthening proofs/scp_strengthening/SequentialUpdates.v
coqc -Q proofs/publication_upgrade PublicationUpgrade -Q proofs/scp_strengthening SCPStrengthening proofs/scp_strengthening/Counterexamples.v
coqc -Q proofs/publication_upgrade PublicationUpgrade -Q proofs/scp_strengthening SCPStrengthening proofs/scp_strengthening/Assumptions.v
```

The machine used for this development has Rocq 9.3.0 (`/opt/homebrew/bin/coqc`). The final command prints seven `Closed under the global context` lines. The old file emits only the existing `From Coq` namespace deprecation warning on Rocq 9.3.
