# Finite decisive fixtures

The executable fixtures isolate the semantic distinction this extension is meant to check. They use only hand-authored rational rows; they contain no provider measurements and establish no external kernel-calibration premise.

| Fixture | Exact result | Checker result | What it distinguishes |
|---|---:|---:|---|
| Same rows, immediate visible stop | center trace TV `0` | robust upper bound `0`; complete-stop check passes | Zero-radius exact-law behavior is preserved. |
| Equal row centers, radius `1/4` on each scenario | admissible concrete rows attain TV `1/2` | robust upper bound `1/2` | Misspecification is accounted for even when nominal laws coincide. |
| Uniform first event; second event copies it vs flips it | both slot marginals match; joint trace TV `1` | robust upper bound `1` | Unconditional per-call marginal comparison misses complete history leakage. |
| Stop at slot 1 vs slot 2 | center trace TV `1` | upper bound `1`; completion by horizon passes | The first visible stop marker preserves the stop position in the bounded trace. |
| `sharp_history_contract.json` | center trace TV `91/100` | history recurrence `91/100`; per-level-max product `99/100` | Local maxima occur on incompatible histories; the trie recurrence is strictly tighter and sharp here. |
| Omitted row after a shared event | unspecified | upper bound `1`, row flagged missing | Incomplete contracts fail closed. |

The sharp-history fixture visits five shared-prefix rows for a horizon of three. `python3 -m unittest -v test_robust_usage.py` checks these results, contract rejection cases, stop padding, node-limit behavior, and certificate tamper detection. Regressions also cover duplicate keys, escaped surrogates, invalid UTF-8, strict JSON type checks, oversized files and rationals, intermediate rational growth, no-partial-output on node exhaustion, and a valid deterministic horizon-1,100 chain. Replay discharges local arithmetic, exact required continuation coverage, root-bound, and stop-proof obligations without calling the producer recurrence; that is a separate verifier implementation, not a formally verified independent checker.

These are semantic conformance fixtures, not an empirical study of provider kernels, source-adapter coverage, or runtime scaling. Any publication claim should separately compare the integrated checker with the existing request-equality baseline and exact nominal-law checker on pinned source fixtures. Provider data may be used to motivate uncertainty radii only after a separate statistical coverage analysis; it is not part of these theorem inputs.
