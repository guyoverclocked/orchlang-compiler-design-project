# Exact accounting with pinned offline tokenizers

The exact tokenizer CLI accepts a real `.orch` file for closed-request analysis,
or an explicit finite text program for execution. It counts the **complete
constructed request** using a SHA-256-pinned tokenizer artifact and an explicit
special-token policy. It requires `tokenizers==0.21.4`; a wrong hash or version
fails. Padding and truncation are disabled. No model weights, inference API,
credentials or paid service are used by this component.

This adds an exact accounting path; it does not change the C++ mock interpreter's
synthetic units. Its Python source reader and accounting implementation remain
trusted. The Lean resource-equivalence result and the C++ cost analyzer have not
been proved to refine this tokenizer implementation.

## Actual source analysis

After installing `tokenizers==0.21.4` in an isolated Python environment, fetch the
public pinned tokenizer files with:

```text
python scripts/fetch_tokenizers.py --output /path/to/new-tokenizer-directory
```

The exact protocol independently fixes the artifact hashes. For GPT-2:

```text
python scripts/exact_tokenizer.py --tokenizer /path/to/new-tokenizer-directory/gpt2-bpe.json --tokenizer-sha256 8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6 analyze-source --source bench/exact/closed-source.orch
```

The example substitutes `"hello"` and `"world"` into `"{left}{right}"`, then
encodes `"helloworld"` as one request. Its GPT-2 input bound is 3, output cap 8,
and total bound 11. The corresponding BERT plain input count is 2 and total
bound 10. Inserting BERT's special tokens gives input count 4 and total bound
12; the source budget of 11 is then explicitly reported insufficient.

The supported source fragment is exactly the trusted closed-request reader:
one workflow, lexical mock model declarations, secret Boolean guards, text
prompts, literal arguments, literal private output, sequences and branches.
Calls are summed; branch bounds take the larger arm. Source input declarations,
response-dependent requests, retry, tools and reclassification are rejected.
The JSON result includes source SHA-256, each fully substituted request and token
IDs, the source's original mock contract, and a separate accounting tokenizer
identity. The mock contract is never relabeled as a deployed-model contract.

Source `max_tokens` is an **assumed output cap in the selected accounting
policy**. Analysis does not run the primitive or establish cap conformance. The
result makes this assumption explicit. Source privacy acceptance is a separate
judgment; an exact resource bound alone does not certify privacy.

For an arbitrary raw UTF-8 request file, the same CLI's `count --text-file FILE`
command returns exact token IDs and count. Reading raw bytes preserves CRLF.
Invalid UTF-8, including isolated surrogate code points, is rejected.

## Executable finite text programs

```text
python scripts/exact_tokenizer.py --tokenizer /path/to/new-tokenizer-directory/gpt2-bpe.json --tokenizer-sha256 8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6 run --case bench/exact/dynamic-chain.json
```

The runner independently constructs requests, substitutes earlier response text,
enumerates exact finite-table probabilities, bills successful and failed
attempts, and stops retries on success. It validates all response alternatives
against the exact token cap, including unselected error outcomes. Before each
call it reserves the exact request count plus declared output cap from the
remaining budget. `max_request_tokens`, when supplied, is checked before the
replay dispatch. Output files use exclusive creation.

The JSON format declares `models` with revision and `max_tokens`, a replay table
for each model, the program and initial environment. It can additionally declare
`input_byte_bounds`, per-model `max_output_bytes`, `budget_tokens` and
`max_request_tokens`. See the two runnable examples in `bench/exact/`.

For **closed** JSON requests, the static input bound is their exact encoded count
under either pinned family and either special-token policy. For **dynamic**
requests, the static analyzer uses separately enforced UTF-8 byte contracts and
an audited byte upper bound described below. A token cap is not a byte cap.

The default mode derives a whole-program bound, adds sequential bounds, takes
branch maxima, and multiplies retry bodies by the syntactic bound. Retry is
limited to the finite executor's range 0–16. A budget smaller than this derived
bound is rejected. Execution must remain below the bound on every enumerated
path.

`run --runtime-only --case FILE` instead admits complete requests one at a time
under an explicit `budget_tokens`. It supports dynamic requests for either
tokenizer; its result sets `static_bound` to `null`. It does not claim that every
possible run will finish within the budget: a future request can be rejected
before dispatch.

## Why tokenized pieces cannot be added

With the pinned plain GPT-2 tokenizer,
`count("hello") + count("world") = 2`, while `count("helloworld") = 3`.
For plain BERT, `count("a") + count("world") = 2`, while
`count("aworld") = 3`. Adding individually encoded pieces can therefore
**underestimate** the final request, as well as overestimate it. The exact path
never does this.

The dynamic static rule uses UTF-8 bytes, which are additive under concatenation
of valid strings. For the exact GPT-2 artifact with SHA-256
`8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6`,
library 0.21.4 and special tokens disabled, the configuration has no normalizer,
uses byte-level BPE without an inserted prefix, and has a complete byte alphabet.
Each initial symbol represents one input byte; BPE merges do not increase the
number of symbols. Its sole added token consumes a nonempty input string.
Consequently `count(text) <= len(text.encode("utf-8"))`. The implementation
enables this rule only for that audited content hash and policy. This is an
implementation argument under the pinned library semantics, not a Lean theorem.

The [pinned byte-level implementation](https://github.com/huggingface/tokenizers/blob/v0.21.4/tokenizers/src/pre_tokenizers/byte_level.rs)
and [BPE implementation](https://github.com/huggingface/tokenizers/blob/v0.21.4/tokenizers/src/models/bpe/model.rs)
are the primary sources for this rule. The
[Tokenizer API](https://huggingface.co/docs/tokenizers/v0.20.3/api/tokenizer)
documents explicit special-token, truncation and padding controls; the local
implementation and dependency are pinned to 0.21.4.

No byte rule is asserted for BERT or other artifacts. BERT can remove control
characters: 4,096 NUL bytes encode to zero tokens in the pinned plain policy.
Thus even a zero token cap cannot bound arbitrary response bytes under this
normalizer. A response used in a later dynamic static request therefore needs
a separate `max_output_bytes`; the finite executor validates that cap for all
table alternatives. For a live model, output-token accounting must measure its
actual generated token IDs under the generation contract; recounting decoded
text is a different measurement.

## Retained development evidence

The completed run is
[`research/readiness-2026-10-24/exact-accounting-v4/`](../research/readiness-2026-10-24/exact-accounting-v4/).
It records source hashes, artifact revisions/hashes, Python/platform data, raw
token IDs, concatenation cases, complete finite traces, source analysis results,
and required test/CLI command outputs. The protocol explicitly follows preliminary
exploration and is not described as preregistered.

| Policy | Text cases | Concatenation pairs | Joined > separate | Joined < separate |
|---|---:|---:|---:|---:|
| GPT-2 plain | 1,336 | 2,249 | 36 | 430 |
| GPT-2 special | 1,336 | 2,249 | 36 | 430 |
| BERT plain | 1,336 | 2,249 | 75 | 604 |
| BERT special | 1,336 | 2,249 | 0 | 2,249 |

These are 5,344 text-policy observations and 8,996 concatenation-policy
observations, not that many independent real applications. The audited GPT-2
plain byte rule had zero violations among its 1,336 boundary texts. Across 64
finite program/policy/guard configurations, 40 had supported static bounds;
24 dynamic configurations were intentionally unsupported because no audited
byte rule applied. The 40 supported configurations enumerated 128 paths with
zero bound violations. Four source-policy analyses and two actual source CLI
checks completed. All 12 required tests passed with no skips. Cost was USD 0.00.

The stress inputs cover combining marks, emoji and ZWJ sequences, CJK, controls,
CRLF, bidirectional controls, special-token-looking strings, boundary Unicode
scalars and seeded mixed Unicode. This establishes implementation evidence for
the declared paths; it does not measure provider billing, quality, a production
deployment or an end-to-end theorem. The v3 directory retains an infrastructure
failure: its first smoke assertion incorrectly reused GPT-2's expected source
count for BERT; the completed v4 check compares tokenizer-specific results.

Reproduce in a fresh output directory:

```text
python scripts/exact_tokenizer_probe.py --tokenizers /path/to/new-tokenizer-directory --output research/local-exact-run
```

This runner requires the exact dependency and artifacts and treats a skipped
required test as failure. The ordinary standard-library test suite explicitly
skips optional real-tokenizer integration tests when the dependency or
`ORCHLANG_TOKENIZER_DIR` is absent. To run those tests directly in PowerShell:

```powershell
$env:ORCHLANG_TOKENIZER_DIR = '/path/to/new-tokenizer-directory'
python -m unittest tests.test_token_accounting -v
```
