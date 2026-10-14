# Adversarial review: SCP strengthening

Read-only review of the candidate package. Only this memo, `reproduce_checker_edges.py`, and `duplicate_keys_contract.json` were added here. I did not inspect held-out source.

## Blockers for stronger claims

**The Coq theorem is IR-level, not a proof about accepted Python/LangGraph source or implemented lowering.** It proves refinement for normalized `workflow_node` records under `safe_after`, injective return maps, and equal paired descriptors; graph composition additionally assumes `paired_graph_matches` and common target indices. No theorem constructs those records from `extract.py`, establishes source-field/result-register and route-label/index correspondence, or proves runtime execution implements the Coq step. `RESULT.md` accurately discloses this. Any source/compiler-correctness headline is blocked until this bridge is proved or independently validated and scoped.

**The robust-TV bound is conditional on caller-supplied full-history rows.** The checker neither derives rows from source executions nor establishes a provider stays in the declared TV balls. Row coverage, observer, horizon, and any neighboring-input relation remain premises; the README and opportunity memo correctly say so. Keep these conditions next to every bound.

**Do not call robust `replay` independent.** `replay` invokes `certify` on the same contract, then compares its result to the submitted dictionary (`robust_usage.py:300–302`). It is recomputation. Current README wording (“replays its own certificate”) is appropriately modest; stronger independent-checker language would be false.

## Checker findings

For the stated finite-alphabet/full-history contract, I found no arithmetic counterexample to the recurrence. The local TV triangle bound and the conservative continuation over shared possible symbols appear sound. These defects affect resource handling, malformed-input handling, and certificate integrity, not the bound returned on successful runs:

1. **The node budget does not bound horizon work.** `certify` scans every depth in `range(horizon)` to build level summaries (`robust_usage.py:271–280`), even after a missing root row has already made the bound 1. The reproducer reports `H=2,000,000`, `max_nodes=1`, and about 0.046 s on this machine; input has no horizon cap, so the loop can be made arbitrarily large while visiting no trie nodes. Iterate populated depths or check a total-work/horizon limit.
2. **Deep valid contracts crash instead of returning unknown/rejected.** Recursive `survival` (`196–267`) and stop coverage (`155–181`) hit Python’s recursion limit. The reproducer builds a deterministic valid chain at `H=1,100` with `max_nodes=10,000`; `certify` raises uncaught `RecursionError`, outside the CLI’s handled exceptions (`344–346`). Use an explicit stack or a checked depth limit.
3. **Replay has JSON type confusion.** Python has `True == 1`, so replacing certificate `horizon: 1` with `horizon: true` still passes dictionary equality. This does not alter the recomputed bound, but it defeats strict tamper detection. Require exact recursive JSON types as well as equal values.
4. **JSON parsing accepts ambiguity and leaks encoding errors.** Standard `json.load` silently keeps the last duplicate key (`305–313`); the included input’s first schema is invalid and first horizon is 99, yet it is accepted as the later valid schema/horizon 1 and hashes identically to clean normalized input. Neighboring `audit/orchgraph.py:40–49` rejects duplicate keys. An escaped lone surrogate also raises uncaught `UnicodeEncodeError` during canonical UTF-8 hashing (`133`). Reject duplicate keys/non-scalar Unicode or convert failures to `ContractError`.

Reproduce with `python3 research/scp_strengthening/adversarial_review/reproduce_checker_edges.py`. It demonstrates the four cases above. The JSON examples are in this review directory.

## Proof and source bridge

I compiled temporary copies of `AtomicUpdates.v`, `SequentialUpdates.v`, `Counterexamples.v`, and `Assumptions.v` with `/opt/homebrew/bin/coqc` 9.3.0, keeping generated files out of the reviewed tree. All compile and `Assumptions.v` prints seven “Closed under the global context” lines. The three failure witnesses and finite-prefix cycle result match their stated scope.

By inspection, current frontend checks do correspond to the needed side conditions: node parsing only permits earlier locals, rejects reads of a returned field after its writer, enforces unique call locals, and requires unique return fields/locals (`extract.py:461–481`, `491–563`). Lowering assigns returned results to stable state registers and other results to temporaries (`806–859`); the backend writes each response before later calls and routes after the node (`backend.py:489–553`). These are code-review support for the bridge, not machine-checked premises. Coq total lookup returns `""` for absent fields while the backend errors; the required definite-initialization argument is also correctly listed as outside the proof (`RESULT.md:31`).

## Literature and feasible contribution

The opportunity memo mislabels `Coupling proofs are probabilistic product programs` as **POPL 2016**. DOI `10.1145/3009837.3009896` is the **POPL 2017** paper; 2016 is its arXiv preprint. The [official POPL 2017 entry](https://popl17.sigplan.org/details/POPL-2017-papers/1/Coupling-proofs-are-probabilistic-product-programs) and [arXiv record](https://arxiv.org/abs/1607.03455) establish the distinction. Correct the proceedings year. OpenAlex title/DOI discovery returned 2016 metadata, which should not override the proceedings record.

The novelty posture is otherwise cautious. Chen and Kiefer’s [LICS 2014 paper](https://chentaolue.github.io/pub-papers/lics14.pdf) develops TV distance between labelled-Markov-chain trace laws and approximation algorithms. Sen, Viswanathan, and Agha’s [TACAS 2006 paper record and abstract](https://osl.cs.illinois.edu/publications/conf/tacas/SenVA06.html) already cover interval transition uncertainty under uncertain-chain and adversarial IMDP semantics. These rule out generic “new trace TV” or “first robust uncertain probabilistic model” claims; they do **not** establish that this exact finite observer-history row-ball recurrence appeared earlier. This was not a systematic priority search.

A feasible distinguishing contribution is to close the existing boundary: formally define the accepted Python/LangGraph fragment and prove its AST-to-normalized-IR, register, and route correspondence, then tie the observable event contract to a source example. Until then, describe an IR theorem and a standalone conditional robust checker, not a compiler-level guarantee or a first result.

OpenAlex was used for discovery/metadata; literature claims were checked against primary proceedings, arXiv, and author-hosted paper sources. This agent review is not independent human artifact evaluation.
