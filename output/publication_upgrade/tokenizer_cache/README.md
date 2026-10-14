# Frozen local tokenizer data

These three cache payloads were fetched by the official `tiktoken==0.12.0`
encoding constructors on 14 October 2026. Their filenames are the library's
SHA-1 cache keys for the source URLs. The library validates the downloaded
payload SHA-256 against its declared expected vocabulary hashes. The calibration
report records the payload SHA-256 and a separate complete ordinary-vocabulary
fingerprint including token IDs, lengths and bytes.

| Encoding | Public data URL |
| --- | --- |
| `cl100k_base` | https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken |
| `o200k_base` | https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken |
| `r50k_base` | https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken |

The owning tokenizer software is OpenAI's MIT-licensed
[`tiktoken`](https://github.com/openai/tiktoken/tree/0.12.0); these data are
used through its public encoding configuration. This archive is for reproducing
plain-text tokenization measurements. It contains no provider API requests,
keys, private prompts or usage invoices. The 90 study call texts and 12 controls
are reconstructed by the calibration script from synthetic offline evidence.
