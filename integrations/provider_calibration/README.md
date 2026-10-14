# Provider usage calibration readiness

This integration is an offline-first harness for a small, future API usage calibration. It is ready to make a frozen run plan, but no provider call has been authorized or made. The default command validates local files only; it does not construct a transport, inspect credentials, or read `.env` files.

The fixture contains four public synthetic prompts and two envelope profiles copied from the **shape** recorded by existing offline capsule artifacts. One shape passes one chat message; the other passes one plain-text string. The profiles are mapped to two OpenAI Responses request forms. The exact synthetic text, model-independent request templates, immutable original-source identities, profile hashes, case list, observer definitions, and caps are frozen in [public_request_manifest.json](public_request_manifest.json). Each template substitutes the literal `<EXACT_MODEL_ID_PENDING>` sentinel, which is not executable; model-specific request hashes are frozen later in the offline plan. The manifest SHA-256 is `9c8e2b720c5764b38b47c03cc3e824de131ebaf9abdff445370bb2a0727d2c42`.

The frozen manifest records the historical result-artifact drift observed while capsule authoring was active. After the capsule agent declared those results final, their digests were attached in the separate [CAPSULE_LINEAGE_BINDING.json](../../research/scp_strengthening/provider_calibration/CAPSULE_LINEAGE_BINDING.json), which leaves the prompt/profile manifest unchanged. The binding SHA-256 is `a1fa43073b7413d125729ecc49856bfc6cebc34baa7edf8110020941670cfaef`. Default `validate` checks these local result-artifact digests and source-identity metadata without reading original source code or using the network.

This is envelope-shape calibration only. It does not verify either original workflow's provider, SDK, model, configuration, prompt, or serialization path. The offline capsule artifacts contain mock-oracle traces; substituting OpenAI Responses tests the mapped shapes at a different API boundary. It is not a source-provider fidelity result, a stochastic probability-radius estimate, or evidence for future confidentiality.

## Offline use

```sh
python3 integrations/provider_calibration/provider_calibration.py validate
python3 -m unittest integrations.provider_calibration.test_provider_calibration -v
```

To prepare a run plan later, first choose and verify the provider, exact model ID, local tokenizer encoding, current per-token price schedule, and approved budget. `plan` is offline and writes every exact request body plus a SHA-256 before any model response can be collected:

```sh
python3 integrations/provider_calibration/provider_calibration.py plan \
  --manifest integrations/provider_calibration/public_request_manifest.json \
  --provider openai \
  --model '<exact model ID>' \
  --local-encoding '<locally installed tiktoken encoding>' \
  --input-price-per-million '<current rate>' \
  --cached-input-price-per-million '<current rate>' \
  --cache-write-price-per-million '<current rate>' \
  --output-price-per-million '<current rate>' \
  --budget-usd 0.25 \
  --out output/scp_strengthening/provider_calibration/run_plan.json
```

Review that plan and its SHA-256 before any spend authorization. Execution then requires a separate affirmative flag and matching provider, model, maximum wire-request count, budget, and plan hash. It makes at most eight input-token preflight requests followed by at most eight Responses requests, in order. Any error or incomplete usage stops the batch; no retry or escalation occurs. The completion requests set `max_output_tokens=64`, `store=false`, and no tools. Each input preflight must report at most 1,024 tokens before any completion call starts.

```sh
python3 integrations/provider_calibration/provider_calibration.py execute \
  --plan output/scp_strengthening/provider_calibration/run_plan.json \
  --output output/scp_strengthening/provider_calibration/receipts.json \
  --approve-real-api yes \
  --provider openai \
  --model '<same exact model ID>' \
  --max-wire-requests 16 \
  --budget-usd 0.25 \
  --plan-sha256 '<SHA-256 printed by plan>'
```

The adapter checks for `OPENAI_API_KEY` only after the explicit approval fields match the frozen plan. It never prints the key. Receipts store prompt/request hashes, normalized and raw usage counters, response/model identity, timestamps, safe headers, response status, incomplete/stop details, and redacted error identifiers. They do not store request text or generated text; generated text is represented by a hash and character count. A transport failure may have reached the provider, so its receipt says delivery and billing are unknown and the batch stops.

## Observers and budget interpretation

The output keeps three observers separate: the abstract character heuristic (`max(1, code_points // 4)` on visible prompt text only), the local `tiktoken` encoding count on visible prompt text only, and the API's reported request/response usage. The local count excludes role serialization and provider framing. Its vocabulary loader is blocked from downloading; if the requested encoding is not already cached, that observer is recorded as unavailable. The JSON usage object is preserved intact, including cached input, cache-write and reasoning subcounters when returned. Responses API output usage can include tokens absent from visible text; reasoning tokens are included within output tokens, and cached tokens within input tokens. A missing, negative, non-integral, impossible, or inconsistent counter is retained and marked incomplete rather than imputed; non-finite malformed numbers are represented by an explicit tagged marker so the receipt remains valid JSON.

The proposed ceiling is 8 model responses, 8 input-count preflights, 16 total outbound requests, 1,024 reported input tokens per case, 64 generated tokens per response, zero retries, no tools, and a planning budget of $0.25. At plan freeze, the operator must enter the exact model's current input, cached-input, cache-write, and output rates. The reserve assumes every preflight and every response input could be billed at the highest entered input/cache rate and all output could reach the 64-token cap. This is a nominal estimate, not a mathematical invoice cap: the selected model/tier, provider billing behavior, metering details, and any unknown envelope charge can differ. The executor checks its supplied schedule and stops before response calls if preflight input exceeds the token cap or the estimate exceeds budget.

The official Responses documentation describes the usage counters and token-count endpoint; the token-count guide says it accepts the same input format as Responses and includes request-structure formatting. The pricing page is dynamic. Check it again at plan freeze; this repository currently leaves provider and model pending.

- [Responses API create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Count tokens guide](https://developers.openai.com/api/docs/guides/token-counting)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
