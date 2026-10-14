> Historical review snapshot. The prefix-only status-label issue was subsequently fixed, and the final frozen run passes 23 conservative-contract tests. The earlier findings and fault-injection limitations remain recorded below.

# Second adversarial review: robust usage checker and SCP proof

## Result

I found no false certificate or recurrence counterexample within the declared finite, full-observer-history model. The patched strict parser, type checks, explicit traversal limits, certificate coverage checks, and Rocq proofs all pass the checks below. The main limitation is that replay is a second traversal over shared semantic helpers, not a structurally independent checker; the README and function docstring now state that accurately. One small replay-status label remains misleading for prefix-only contracts.

This was a read-only review of `research/scp_strengthening/robust_usage/`, `proofs/scp_strengthening/`, and the existing proof result note. I did not inspect or use held-out inputs, execute original workflow source, or call a paid API. The only files added are this review and its two reproduction scripts.

## Findings

**[P3] Prefix-only replay says it checked a stop proof when it did not.** In [`robust_usage.py`](../robust_usage/robust_usage.py#L767), `_verify_stop_obligation` runs only when `require_stop_by_horizon` is true. The successful replay response nevertheless always includes `"stop proof"` in its `checks` list ([line 813](../robust_usage/robust_usage.py#L813)). The reproduction reports `scope=horizon_prefix_only` and `termination_proved_by_contract=false` while that label is present. This does not change or invalidate the bound: the certificate carries the correct scope and termination flag. The response should say that the stop proof was not requested, or list that check only when it ran.

**Replay shares failure points with the producer.** `replay` does not invoke `certify`, and the existing test that replaces `certify` with an exception passes. However, producer and verifier both depend on `_local_obligation`, `_possible_support`, `_tv`, `_certificate_row`, the same parser, and the same exact arithmetic helpers. A deliberately injected error in `_local_obligation` makes both accept a zero bound for deterministic `a` versus deterministic `b`, whose exact trace TV is one. This is a fault-injection demonstration of shared-code risk, not a defect in the current helper. The package explicitly disclaims structural independence; retain that qualification and do not call this a standalone independent proof checker.

## Adversarial checks

The patched unit suite passes: 21 tests, including the earlier duplicate-key, bool/integer, Unicode, recursion, horizon, node, rational-growth, and output regressions. Additional strict-parser probes reject a duplicate key written once literally and once as `\\u` escape, exponent-form JSON numbers, 1,500-level nesting, invalid UTF-8, and a lone escaped surrogate. The recursive Python-object cycle path is also covered by the iterative tree validator’s contract. The package rejects a horizon above 10,000; a valid 1,100-step chain certifies and replays. I found no path that accepted these malformed or over-limit inputs.

[`independent_finite_law_audit.py`](independent_finite_law_audit.py) constructs direct exact trace laws without using the package's center-law or recurrence code. For three horizon-two contracts over `{a,b,__STOP__}`, it enumerates every quarter-grid row in each selected TV ball at the root and both active one-symbol histories, then checks every left/right kernel pair:

| Case | Kernel pairs | Maximum exact trace TV | Checker upper bound |
|---|---:|---:|---:|
| 1 | 42,875 | 1 | 1 |
| 2 | 117,649 | 3/4 | 3/4 |
| 3 | 15,435 | 7/8 | 1 |

These are finite falsification probes, not a proof over arbitrary real-valued kernels. Case 2 also supplies an attained finite witness for the reported bound. In all cases, exact trace generation includes visible STOP and padding. The same script confirms that replay accepts a valid certificate with `certify` patched to raise, and separately records the shared-helper fault-injection limitation above.

The recurrence appears sound under its stated premise: at each shared full trace `h`, each concrete conditional row must lie in its declared TV ball. Triangle inequality bounds the next-step distance by the center distance plus both radii. Maximal coupling then gives at least `1-d(h)` chance to match an event in the common possible support, after which the minimum continuation guarantee over those shared events applies. Induction covers the finite horizon. This reasoning does not license using unconditional per-call marginals in place of the full-history conditional rows. The existing equal-marginal/different-joint-trace test correctly has trace TV one. Likewise, dropping status, usage, response metadata, or other selected observer fields changes the law being bounded; the caller owns that observer definition and the row-ball premise.

## Proof-to-compiler boundary

The Coq files compile with Rocq 9.3.0 in a disposable temporary tree. `Assumptions.v` prints seven `Closed under the global context` lines. The finite-prefix theorem is a deterministic refinement theorem over paired normalized nodes and a shared oracle; it proves equality of status, program counter, abstract request/response trace, and state for a bounded number of node transitions. It does not prove termination or probability-law equivalence.

The limit is stated correctly in [`RESULT.md`](../proof/RESULT.md#L27): `workflow_node` carries proofs of `safe_after`, uniqueness, return completeness, and local ordering as fields ([`SequentialUpdates.v` lines 392–402](../../../proofs/scp_strengthening/SequentialUpdates.v#L392)). The graph theorem assumes every paired node has equal normalized calls, returns, and decisions ([lines 404–415](../../../proofs/scp_strengthening/SequentialUpdates.v#L404)). There is no theorem that the Python extractor constructs these records, that graph JSON preserves lexical/register/route bindings, or that backend/LangGraph execution implements the model. The result note also identifies initialization, runtime errors/caps, abstract requests, and the shared deterministic oracle as trusted bridge conditions. I found no proof-to-compiler claim in that note that exceeds the actual theorem, provided this boundary stays adjacent to any summary of the result.

## Reproduction

From the repository root:

```sh
/usr/bin/python3 research/scp_strengthening/second_adversarial_review/independent_finite_law_audit.py
/usr/bin/python3 research/scp_strengthening/second_adversarial_review/compile_proofs.py
```

For the checker suite, run `/usr/bin/python3 -m unittest -v test_robust_usage.py` from `research/scp_strengthening/robust_usage/`.
