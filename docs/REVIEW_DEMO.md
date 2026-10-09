# Current OrchLang review demo

Eight minutes. Use the frozen optimized compiler; avoid rebuilding during a live talk. Commands below are offline. The full speaker scripts and examiner Q&A accompany the new presentation.

## 0:00–1:00 · Open with the distinction

“A budget bound limits how much a run can use. It does not tell us whether a private decision changes the usage record. This project checks both, for a small bounded workflow language.”

Show `bench/relational/reject/DifferentArgument.orch`: both public inputs have cap 100; a secret flag selects x or y.

```sh
./orchc check bench/relational/reject/DifferentArgument.orch
```

Expected: E236 comparing resolved outer x versus y. Do not say existing resource-aware or taint analyses universally miss this issue.

## 1:00–2:15 · Show one concrete witness

```sh
./orchc run bench/relational/reject/DifferentArgument.orch --audit-unsafe --seed 3 --pin x=37 --pin y=61 --pin s=0 --pin flag=false --json
./orchc run bench/relational/reject/DifferentArgument.orch --audit-unsafe --seed 3 --pin x=37 --pin y=61 --pin s=0 --pin flag=true --json
```

Expected ordinal mock: input usage 69 versus 45; output usage 51 in both. The public inputs and oracle seed stay fixed. The rejection witness uses the explicit offline bypass; ordinary `run` refuses this program. No real provider invoice is involved.

## 2:15–3:00 · Cost is a different property

```sh
./orchc cost examples/valid/bounded_retry.orch
```

Point to the retry multiplication and separate output/input/total components. State the cap and full input-accounting assumptions. The 4,600-run synthetic grid has zero certificate violations; the flat retry-unaware baseline has 741, not an estimated industry failure rate.

## 3:00–4:30 · Show the substantive improvement

```sh
./orchc check examples/research/accepted/chain_matched.orch
./orchc run examples/research/accepted/chain_matched.orch --seed 3 --json
./orchc run examples/research/accepted/chain_matched.orch --seed 3 --request-sensitive-oracle --json
```

Show the two secret arms with a second call consuming the first result. Explain explicit-data versus effective labels, prior-result positions and the required combined relational gate. The first requests match; shared results make the second requests match. Outputs/tools still cannot occur under secret control. Seven sourced balanced patterns were newly admitted; acceptance rose from 8/15 to 15/15.

## 4:30–5:15 · Show a near miss

```sh
./orchc check examples/research/rejected/chain_literal_mismatch.orch
./orchc check examples/research/rejected/template_bytes_differ.orch
./orchc check examples/research/rejected/cross_model_chain.orch
```

Expected: E236 for mismatching requests, E267 for unsupported token-unit conversion. Equal rounded literal sizes are not equal requests. Model alias spelling is not identity.

## 5:15–6:00 · Flow policy and explicit trust

```sh
./orchc check bench/security/unsafe/InjectionTransitive.orch
./orchc check bench/security/safe/InjectionTransitiveEndorsed.orch
```

Expected: E233, then acceptance after explicit endorsement. “This enforces a declared flow policy. The compiler records the review assertion; it does not perform that review or detect malicious text.”

## 6:00–7:00 · Evidence and auditability

Show `bench/results/sourced.json` and `sourced_request_sensitive.json`. Both repeat the same 15 source patterns / 45 authored bounded projections. Each has 2,250 equal balanced comparisons and witnesses in all 2,250 unequal-arm slices. Inputs, loop bounds, source reductions and exclusions are explicit. This is not a production-agent benchmark.

```sh
python3 audit/certificate_audit.py bind examples/research/accepted/chain_matched.orch /tmp/chain-report.json
python3 audit/certificate_audit.py verify examples/research/accepted/chain_matched.orch /tmp/chain-report.json
```

The Python auditor checks source hashes, request cost facts and each derivation. It does not verify the IFC/relational theorem.

## 7:00–8:00 · Close with the functioning HTML demo

Start the local server before the talk, from the repository root:

```sh
python3 demo/server.py
```

Open **http://127.0.0.1:8765/**. Slide 32 of the current deck links to this address.
Choose story 06, “Same mean, different laws”, and click **Run with local compiler**.
Wait for **LIVE LOCAL RUN**. Both means are 2; the supplied output-usage laws
have total variation 1. The independent replayer verifies the bound report.
Next choose story 07, “Equal laws, hidden states”, and run it live. Strong bisimulation is inconclusive; exact trace-law checking proves equal laws at every finite call horizon under the supplied closed model, and the independent replayer verifies the proof. If time permits, story 04 shows aggregate TV 0 and ordered-trace TV 1.
These are exact finite models with declared kernels, not provider measurements.

“The contribution is an inspectable software pipeline: bounded compiler
contracts, replayable cyclic graph analysis, exact usage channels, and a
sufficient bisimulation check and an exact all-finite-horizon trace-law check. The methods specialize
established relational resource analysis, quantitative information flow probabilistic bisimulation and weighted-automaton equivalence. The artifact has restricted source adapters,
actual offline LangGraph execution, independent replay and explicit limits.”

The seven stories cover a compiler rejection, a matched dependent chain, a
productive cycle, hidden order, noisy usage, and equal means with different
laws, and equal observable laws with different hidden transition structure. Opening `demo/index.html` directly gives clearly marked **STATIC
EVIDENCE**; use the server for a current live run. No provider calls occur.

## Assessment if asked

Historical overall novelty was 4.5/10; the current independent assessment is
5.8/10. The applied method rose from 3.5 to 5.9. SCP OSP
originality/novelty/significance is 6.2/10, the six-criterion candidate-quality
proxy is 7.4/10, and scope fit is 8.5/10. These are subjective internal
judgments, not journal ratings or acceptance probabilities. The requested
novelty-based score of 8 is not supported. See
[FINAL_PUBLICATION_REVIEW.md](FINAL_PUBLICATION_REVIEW.md).
