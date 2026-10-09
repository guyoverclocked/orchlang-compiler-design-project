# OrchLang closing demo

This demo compares modeled requests, ordered token usage, aggregate billing, and exact finite probability laws. It uses only the repository's local compiler and analysis scripts. It runs through a local loopback connection and never contacts a model provider or an external network service.

## Run it

From the repository root:

```sh
python3 demo/server.py
```

Open <http://127.0.0.1:8765/>. Choose an example, adjust its bounded controls, and select **Run with local compiler** for fresh results. Stop the server with Ctrl-C.

To open the page without starting the server, open `demo/index.html` in a browser. It embeds a recorded evidence bundle generated from the checked-in fixtures. The banner identifies this as a static snapshot and shows the recorded compiler digest; it does not claim to have run the current compiler. The snapshot can be regenerated with:

```sh
python3 demo/server.py --refresh-evidence
```

That command updates both `demo/offline_evidence.json` and the embedded copy in `demo/index.html`.

## Eight examples

- **Different public lengths:** the normal compiler gate rejects two secret-selected requests with different content lengths. The demo uses the explicit offline-only `--audit-unsafe` route to show the two concrete usage witnesses.
- **Balanced dependent chain:** `orchc check` and the source-bound cost auditor inspect the OrchLang program. A separately checked finite rational graph demonstrates the same dependent-call shape; it is labeled as a companion model, not a translation of the source.
- **Productive cycle:** the JSON request graph is checked and its certificate is independently replayed. The displayed traces stop after at most eight calls.
- **Aggregate hides order, noisy usage bit, same mean:** exact finite rational channel analysis compares aggregate and ordered observers. The demo also runs the all-horizon sufficient bisimulation checker and its independent certificate replayer when a certificate is available.
- **Equal laws, hidden states:** strong probabilistic bisimulation is inconclusive, while exact rational trace equivalence proves the two ordered usage laws equal at every finite call horizon. This is an authored example of the distinction between a sufficient structural relation and observable-law equality. Equality and finite inequality witnesses are independently replayed.

- **Real source, isolated meters:** freshly replay the pinned source protocol, controlled concurrent meter witness, and six recorded source paths. The button executes standard-library replayers, not LangGraph. It reconstructs the pinned checkout from the included local Git bundle. Source usage is a code-point estimate; no provider bill is measured.

Story 08 requires Python 3.12+ because the upstream helper uses modern type syntax. Actual source execution and the isolation-manager CLI use the separate exact Python 3.14.6 dependency lock.

## Local API and limits

The page calls only `POST /api/evaluate` with a fixture ID from `GET /api/fixtures` and a small options object. The server binds to `127.0.0.1`, rejects other hosts and non-local origins, accepts at most 16 KiB per request, and does not accept paths, commands, source text, kernels, or graph JSON from the browser. Fixture paths and subprocess argument shapes are fixed in `server.py`.

The request horizon is limited to 8. Channel analyses are capped at 10,000 states and 16 MiB of analysis work. Stochastic and exact trace-law checks are capped at 5,000 states and 16 MiB of work; independent reconstruction also has 50,000 transition and 100,000 control-step caps. The trace-law stage allows at most one million matrix entries. These are deterministic analysis-work limits, not process RSS guarantees. Each local subprocess has an eight-second timeout and an eight-MiB output limit. User-facing public text is bounded before analysis. A failed operation returns an error; UNKNOWN carries no partial equality or inequality conclusion.

The offline source witnesses use the compiler's synthetic mock runtime. The two channel analyzers use the checked-in rational kernels; their probabilities describe those finite fixtures. A verified stochastic split means the sufficient all-horizon equality check could not prove equality. It is not by itself a leakage witness. A proved equality is about the supplied success-only finite semantics and its request-coupling assumptions. The cycle trace is a bounded probe and makes no total-cost or termination claim.

The accounting model uses UTF-8 byte estimates and declared abstract bounds. It does not provide a real-provider tokenizer, request-envelope, or deployment guarantee. See the fixture assumptions in the page alongside each result.

## Tests

Run the focused server tests from the repository root:

```sh
python3 -m unittest demo.test_server -v
```

They start an ephemeral loopback HTTP server and exercise live compiler, checker, analyzer, and replay routes against the checked-in fixtures.

The nine HTTP tests and a manual in-app browser pass of all eight fresh stories are recorded in `ui_review.json`. Stories 01–07 execute local compiler/analyzer tools; story 08 replays recorded actual-source evidence. Opening the HTML file directly remains a static evidence view.
