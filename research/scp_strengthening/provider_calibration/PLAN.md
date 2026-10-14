# Provider usage calibration: approval-ready plan

Status: **offline readiness only**. There have been zero live provider requests, no credential inspection, no `.env` load, and no model/provider selection. A later human approval must name the actual provider and exact model and approve the frozen plan's call and budget caps.

## What this experiment can answer

The frozen fixture has four public synthetic prompts, each sent in two envelope shapes taken from the structure recorded in offline capsule artifacts: a single chat-message list and a plain-text invocation argument. The OpenAI Responses mapping keeps the content synthetic and retains only those input-shape distinctions. Prompt hashes, exact model-independent payload templates, immutable source identities, envelope-profile hashes, case IDs, and manifest digest are frozen before outcomes. The model-specific plan later replaces `<EXACT_MODEL_ID_PENDING>` and hashes every final request body offline before approval or outcome collection. The immutable manifest preserves the result-artifact drift observed during development; after the capsule agent declared the outputs final, a separate [lineage binding](CAPSULE_LINEAGE_BINDING.json) attached their final digests without changing the frozen prompt/profile manifest. The frozen manifest SHA-256 is `9c8e2b720c5764b38b47c03cc3e824de131ebaf9abdff445370bb2a0727d2c42`.

This can measure whether declared character counts and an explicitly named local tokenizer track usage returned by one selected Responses API model for these eight synthetic payloads. It cannot validate the original workflows' provider, SDK, model or exact request serialization. For that claim, the same original provider/model path and its actual configuration must be exercised at the frozen source boundary. It also cannot establish a stochastic row-TV premise or a confidentiality property.

## Proposed run limits

| Item | Limit |
| --- | ---: |
| Synthetic prompts | 4 frozen prompts |
| Envelope shapes | 2 mapped profiles |
| Responses completions | 8 maximum |
| Input-token preflights | 8 maximum |
| All outbound requests | 16 maximum |
| Input cap per case | 1,024 reported tokens |
| Generated-token cap | 64 per response, including non-visible reasoning tokens |
| Retries / escalation | 0 / disabled |
| Tools / persistence | none / `store=false` |
| Proposed budget | $0.25, subject to final model-specific price calculation and human approval |

The price schedule remains unset with provider/model selection. At the later offline plan freeze, use current official rates for input, cached input, cache writes, and output. The reserve charges each preflight and each completion input at the highest of those input rates and reserves each output at the response cap. A current OpenAI pricing illustration—not a chosen model—is GPT-6 Luna at Standard rates: $0.10/M input, $0.01/M cached input, and $0.50/M output; the pricing page lists a $0.125/M cache-write rate. Under those rates and the full token caps, the reserve is **$0.002304**: 16,384 reserved input tokens × $0.125/M plus 512 output tokens × $0.50/M. Account availability, service tier, request metering and later prices remain unverified. The actual plan must recalculate using the selected model and tier; it refuses a nominal reserve above $0.25.

This is a spending estimate and request-count guard, not a mathematical cap on the invoice. Provider-specific billing, requests whose delivery is uncertain after transport failure, unreported counters, price/tier changes, and unknown fixed charges may differ. The input-count request is conservatively reserved as if it were input-billed; official documentation explains its token-counting function but does not establish its separate billing behavior. An error or incomplete usage halts the remaining batch and preserves the partial receipt. The batch never retries.

## Calibration relation to the source capsules

The one-node capsule artifact records a single chat-message input nested inside an invocation envelope; this is mapped to a one-element `input` message list. Its immutable source identity is `didilili/ai-agents-from-zero`, commit `9de20be80dad6d410268ae75f75cf94c355dd364`, source SHA-256 `b35741309de653d79e2cb403ebc5ddfa6b74383dd22f2e0d0142a1359225818b`. The sequential async capsule artifact records a plain-text value at an async invocation envelope; this is mapped to a string `input`. Its immutable source identity is `JoshuaC215/agent-service-toolkit`, commit `88ebfa1fadd1a207aa92115635abf7ed20d66a88`, source SHA-256 `6a96b47a58e855444fa410bef6e077220f578f188476a605aabeb88d88bf0ccc`. In both cases the experiment substitutes the frozen synthetic prompt for capsule content and calls OpenAI Responses. Thus the comparison studies envelope *shape* at the target API's boundary. It does not claim the source capsules used OpenAI or that their SDK/provider payload is equivalent to Responses.

The capsule result JSONs changed digest between initial capture and later validation while their authoring work was still active. This is a development-artifact drift guard finding, not evidence that original source identities changed. The final capsule-artifact hashes are `1f8d8eca8860350d0d9d8422005c62dc222b5c79910d1c1a3d59fc61860e45dd` (one-node) and `3b56bda34f906f4f44cf053316ee8b008119a55bcabb977f3b0b1095989342f1` (sequential async); the separate lineage record also binds each digest to its source identity and frozen profile hash.

The usage trace records the request hash, requested and returned model IDs, provider, timestamps, response status, incomplete/stop fields, safe HTTP metadata, error type/code/status, and the complete JSON usage object. Normalized fields keep `input_tokens`, `output_tokens`, `total_tokens`, `cached_tokens`, `cache_write_tokens`, and `reasoning_tokens` distinct. Cached input is part of input usage; reasoning is part of output usage. Non-finite malformed numbers are encoded as explicit tagged markers so partial receipts remain valid JSON. API usage does not get inferred from the wrapper payload or its visible `.content` text.

The evidence can describe measurement error for these fixed synthetic requests. It cannot show future provider kernels fall in any asserted TV ball, validate real-workflow result equivalence, or justify a confidentiality claim.

## Current official OpenAI documentation reviewed

Reviewed 2026-10-14. The Responses reference exposes total/input/output usage, cached input and cache-write details, and reasoning output details. The counting guide describes an input-count endpoint that accepts the Responses request's input form, including message-role formatting. The dynamic pricing page and model changelog provide the illustrative rates above. Recheck them when preparing the model-specific run plan.

- [Responses API create reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Count tokens guide](https://developers.openai.com/api/docs/guides/token-counting)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI API changelog](https://developers.openai.com/api/docs/changelog)
