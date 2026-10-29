# Actual local workflow execution

The final amended experiment executes six upstream source variants representing five patterns: LangGraph Python graph and functional prompt chaining, LangGraph parallelization and routing, and Prompt Flow basic completion and named entity recognition. It runs each original framework and a port on two inputs at output caps 24 and 64, with seed 1, temperature zero and a 512-token complete-request admission ceiling. All 48 executions complete. The selected final run contains **88 actual model generations**, **22/24 independently equal final-output and complete request/response comparisons**, **zero recorded deployment-bound violations**, and **zero tokenizer/server input-count disagreements**.

This is a runtime deployment experiment. Only the basic completion flow has a direct call-kernel port. The other five variants retain explicit Python host operations around executable OrchLang kernels. These operations include response predicates, JSON validation, branch joins, aggregation and cleansing. The parallel port serializes independent CPU inference; scheduler order and latency are not preserved. These are not six whole-program translations into the production compiler, and the new Python text interpreter is outside the Lean theorem.

The data are an amended development experiment. Earlier outcomes are retained; a new final run was made after fixing concrete harness or translation errors. They are not untouched preregistered results or independent samples of an application population.

## Evidence and failures

The final protocol is [real-workflows-local-v4.json](../bench/protocols/real-workflows-local-v4.json), SHA-256 `5e35163bd85626580a6c0cf6b734c439068abcde5ab3b1bf1ffa72f328cdddf7`. It binds [faithful-local-v3/manifest.json](../bench/corpus/faithful-local-v3/manifest.json). The legacy directory name does not change the direct/hybrid distinction recorded in that manifest.

| Source variant | Comparisons | Independently equal | Peak observed input + generated output | Guarded bound range |
|---|---:|---:|---:|---:|
| Chain graph | 4 | 4 | 41 | 1608–1728 |
| Chain functional | 4 | 4 | 187 | 1608–1728 |
| Parallel graph | 4 | 4 | 200 | 1608–1728 |
| Routing graph | 4 | 4 | 125 | 1072–1152 |
| Basic completion | 4 | 2 | 75 | 536–576 |
| NER | 4 | 4 | 127 | 536–576 |

The remaining two mismatches are the basic completion inputs at cap 64. In each case the two arms send exactly the same complete request, schema, effective output cap and generation options, then receive different model text. No port prompt mismatch precedes either disagreement. The cause is not established. Caching and numerical batching are hypotheses; a seed and temperature zero do not prove deterministic or stateless backend behavior.

A separately frozen diagnostic repeatability control makes 16 new actual generations in eight identical-request pairs selected from earlier mismatching cases. Seven pairs agree and one differs. This supports the observed repeatability limitation without identifying its cause.

Strict captured-response conformance passes 24/24 comparisons and matches all 44 original requests before returning a recorded response, with **zero new generations**. Request order must match for chaining, routing, basic and NER; only the three independent parallel calls may reorder. All original calls must be consumed and final outputs must agree. This checks the ports under common captured actual outcomes; it is not an all-input proof or a replacement for the independently generated disagreements.

Machine-readable retained evidence is in [research/real-workflows-2026-10-24](../research/real-workflows-2026-10-24/):

- `v1/`, `v2/`, `v3/`, `v4/`: original JSON files copied byte for byte, including all failures. Each has an exact implementation snapshot verified against its recorded hashes.
- `conformance-v4/conformance.json`: strict captured-response conformance and replay/source hashes.
- `repeatability-v1/`: diagnostic protocol outcomes, separate actual-generation counts and original responses.
- `final-analysis-v2/analysis.json`: per-comparison first-difference diagnoses, costs, quality and source metrics.
- `final-analysis-v2/annotation-counts.{json,md,tex}`: corrected source/annotation/glue counts.
- `upstream/`: a pinned public-source subset and the upstream licenses; its source manifest is the complete source-census manifest, not a claim that every census file was copied.

Earlier retained failures are material. V1 had a leftover optional routing visualization and a missing `promptflow-tools` dependency. V2 completed model calls but compared Prompt Flow's `Status.Completed` enum with a string, misclassifying completed engine runs. V3 repaired that harness error and exposed four real basic-port request mismatches: the port retained a leading newline that the original Prompt Flow template renderer strips. V4 removes only that newline. Earlier equal-request model disagreements remain in their original records.

## Actual requests, token accounting and bounds

[local_model.py](../runtime/local_model.py) sends the entire constructed request with Ollama `raw=true`, using an explicit ChatML serializer for chat calls and the original raw string for completion calls. It does not add Ollama's default system prompt. The trace stores the full request string, token IDs, schema, effective generation options, response, server input and generated-output counts, stop reason and elapsed time. The adapter has no conversation history or retry loop. This does not establish that the backend's numerical kernel is unaffected by caches or other internal state.

Before dispatch, the adapter counts the complete serialized request with the pinned Qwen tokenizer and admits it only below the input ceiling and context limit. A per-run call-count guard and an output cap yield the deployment bound

`maximum admitted calls × (complete-request input ceiling + output cap)`.

The server-reported input count must equal the complete token-ID count. Silent truncation is rejected. Generated-output accounting uses Ollama `eval_count`, which may include an end token; retokenizing returned text is recorded separately and is not substituted for generation usage. All successful recorded calls satisfy their caps. The large bound/observation gaps in the table are retained; this experiment does not establish tight bounds or an advantage over a manually implemented guard.

These are dynamically guarded model-token bounds, not the production analyzer's abstract token bound, a verified tokenizer composition rule, or a static theorem about arbitrary inputs. Source `max_tokens` annotation counts are measured separately. Requests exceeding the complete input ceiling are rejected before inference; no truncation or silently altered prompt is used.

After the final generation campaign, independent review found a reusable adapter API defect outside the positive-integer frozen cases: `upstream_cap or deployment_cap` could treat zero as a default and allow negative/fractional values. Current code rejects zero, negative, Boolean, fractional and string caps before dispatch, checks the exact `tokenizers` version and forbids configured padding/truncation. Transport failures now mark usage incomplete with unknown input/output consumption rather than reporting missing usage as zero. The captured v4 implementation is retained; its recorded source caps were all 64 or 120, so those repairs do not change any recorded admitted request. Dependency-free regression tests cover the repairs and response-dependent interpretation.

## Scope and task quality

Prompts, source punctuation predicates, actual response dependencies and final outputs are preserved under the recorded local deployment replacement. The `refine.orch` kernel makes two calls and renders the second prompt from the first actual response. Its interpreter does not replace outputs with length-only mock values. The two upstream Python chaining APIs have opposite punctuation gates; both are preserved, rather than normalized into an invented common behavior.

The original source model/provider is replaced with the same pinned local CPU adapter in both arms. The original OpenAI/Azure/Anthropic provider behavior, SDK retry behavior under failures, cloud token accounting, end-to-end timing and production deployments are not validated. Source framework calls, final state, routing decisions, call counts and full requests/responses are retained. The experiment does not record an independent scheduler-node visitation trace.

Task quality is deliberately separate from conformance. For NER, both arms correctly extract the two job titles but incorrectly split the phone number into `321`, `654`, `0987`, at both caps. The router selects `joke` for a request for a compiler poem, at both caps. These failures remain failures even though the two arms agree. Across both arms, each of these two scored tasks passes 4/8 execution-level exact checks. Open-ended joke/story/code quality is not rated. Forty-four of the 88 final generations terminate at their output limit; short bounds can produce incomplete text.

## Source and annotation effort

Counts use parsed source declarations, not substring searches in prompt text. The original source span excludes optional display/invocation code and counts only active Prompt Flow YAML, prompts and tools. Nonempty LOC include comments. Host case LOC are the AST span of the corresponding branch in `port`; shared driver, interpreter and port-function counts are reported separately. Shared kernels reused across variants are listed explicitly. These descriptive counts do not measure authoring time, maintainability or a productivity improvement.

| Source variant | Original LOC | Kernel LOC | Input / model-cap annotations | Host case LOC |
|---|---:|---:|---:|---:|
| Chain graph | 42 | 16 | 2 / 2 | 13 |
| Chain functional | 30 | 16 | 2 / 2 | 13 |
| Parallel graph | 43 | 21 | 3 / 3 | 9 |
| Routing graph | 71 | 14 | 2 / 2 | 14 |
| Basic | 106 | 7 | 1 / 1 | 2 |
| NER | 56 | 8 | 2 / 1 | 5 |

The original frozen manifests retain two earlier descriptive counting errors: a prompt containing the word `input` inflated the routing input count, and a NER test filename inflated original LOC. The final derived table reparses declarations and names each active upstream file; the historical manifests are not silently rewritten.

## Reproduction

The recorded environment uses CPython 3.12.11, Ollama 0.32.15, `langgraph==1.2.16`, `langchain-core==1.7.0`, `promptflow==1.18.5`, `promptflow-tools==1.6.1` and `tokenizers==0.21.4`. All installed versions are retained in each run manifest and [real-workflows-requirements.txt](../bench/protocols/real-workflows-requirements.txt). Optional framework/tokenizer dependencies are not required to run the dependency-free unit tests; the actual experiment fails if its dependencies or pinned artifacts are absent.

The model is `qwen2.5:3b`, 3.1B Q4_K_M, with manifest digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b` and independently hash-checked GGUF `5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6`. The tokenizer is Qwen/Qwen2.5-3B-Instruct revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`, tokenizer JSON SHA-256 `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`. Weights are not redistributed. Requests set `num_gpu=0`, `num_thread=4`, `num_ctx=4096`, `repeat_penalty=1`, the recorded cap and seed, and temperature zero.

Upstream Prompt Flow is pinned to `33a68c9d3cf349d7fdfad1f41969af27543c0406`; LangChain docs are pinned to `ecda7f522a6ffd5faaabb843b581fe57cd5eb782`. Original file URLs and hashes are in the corpus manifest. Reproduce from the frozen corpus; `real_workflow_prepare.py` can create a new explicitly named development corpus without overwriting any frozen files.

From the repository root, with the recorded optional environment and pinned local model available:

```powershell
python -m unittest discover -s tests -p test_real_workflows.py -v
python scripts/real_workflows.py --sources research/real-workflows-2026-10-24/upstream --tokenizer C:/path/to/pinned/tokenizer.json --orchc ./orchc.exe --protocol bench/protocols/real-workflows-local-v4.json --output C:/new/run
python scripts/real_workflow_replay.py --run C:/new/run --protocol bench/protocols/real-workflows-local-v4.json --output C:/new/replay
python scripts/real_workflow_repeatability.py --tokenizer C:/path/to/pinned/tokenizer.json --output C:/new/control
python scripts/real_workflow_evidence.py --run C:/new/run --protocol bench/protocols/real-workflows-local-v4.json --output C:/new/analysis
```

Each output directory must be new. The new manifest records the executing implementation hashes, including subsequent adapter hardening. A rerun need not reproduce the exact generated words; do not replace or discard disagreeing runs. Captured-response conformance should reproduce the full-request/output correspondence for its recorded original outcomes.

The final actual generation run and diagnostic control spend no API money. Their 88 + 16 actual calls are distinct from conformance replay. Development v1/v2/v3 calls and the disclosed initial smoke generation are retained or disclosed separately and are not added to the final sample size.
