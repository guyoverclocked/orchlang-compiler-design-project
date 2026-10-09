# Experimental OrchLang source-to-graph bridge

`audit/source_to_graph.py` translates a small, explicit OrchLang subset into
the separate version-1 request-graph format described in
[`CYCLIC_WORKFLOWS.md`](CYCLIC_WORKFLOWS.md). This makes the graph checker
usable with a few real source programs while keeping the source translation
claim narrow. The adapter is not verified, and its provenance sidecar is not a
proof of source-to-graph fidelity.

## Translate a source file

Build the compiler, then run the bridge:

```sh
make orchc
python3 audit/source_to_graph.py examples/research/accepted/chain_matched.orch \
  /tmp/chain-matched.graph.json \
  --sidecar /tmp/chain-matched.provenance.json \
  --certificate /tmp/chain-matched.certificate.json \
  --compiler ./orchc
```

The bridge snapshots the source bytes it parsed and the compiler executable it
hashes into a private temporary directory, then runs `orchc check` on those
exact snapshots with the same `--chars-per-token` value. It then checks the
generated graph with `audit/orchgraph.py` and independently replays its
accepted certificate with `audit/replay_graph_certificate.py`. It writes the
graph, producer certificate, and provenance sidecar only after all gates
pass. A parse, subset, compiler, graph-check, or replay failure exits nonzero
and does not write new outputs.

The graph file has only the version-1 graph fields; provenance is in the
separate sidecar. The sidecar binds the raw source SHA-256, exact exported graph
SHA-256, producer certificate SHA-256, adapter SHA-256, source-cost parser
SHA-256, and exact compiler binary SHA-256 used for the snapshot gate. It
records the source workflow budget and byte divisor, passed
compiler/graph/replay statuses, and maps source
input names, model declaration locations, prompt declarations, lexical result
bindings, and source control locations to generated graph names. Different
lexical declarations get different graph registers or model aliases even when
their source spelling is the same.

The sidecar is a reproducibility record. Its hashes can detect file changes;
they do not independently certify that the adapter's mapping is correct. The
compiler hash records which `orchc` bytes passed the gate on the parsed source
snapshot. The graph checker
and replayer each retain their own responsibilities and limitations as
described in the cyclic-workflow tutorial.

## Accepted source subset

The adapter requires exactly one workflow and accepts these declarations and
statements:

* `input` and `secret` of type `text` or `boolean`, at workflow-body scope.
  Every text input and text secret must have `max_tokens`, even if a particular
  value is not used by a prompt. Public untrusted inputs remain public for
  this billing projection; integrity labels are outside the graph schema.
* `model name = mock("actual-id") max_tokens n`, with optional finite,
  nonnegative `cost_per_token`. Lexically shadowed model names are mapped to
  distinct graph aliases, while request equality uses provider, actual model
  ID, cap, and optional price contract.
* `prompt` declarations returning `text`, with `text` parameters. Prompt
  templates are decoded exactly as the source language decodes strings.
  Arguments are quoted text literals or identifiers that resolve to text.
  Numeric and Boolean literals are rejected because graph argument atoms are
  type-erased text and the source mock can distinguish typed expressions with
  the same rendered spelling.
* `let result: text = call prompt(args...) using model;` where values are text
  identifiers or quoted text literals. Argument order and literal/value
  identity are preserved. Direct secret input values, dynamic Boolean/numeric
  inputs, and generated values crossing model token units are rejected by the
  compiler/graph gates.
* Nested `if`/`else` with a Boolean identifier or
  `tokens(identifier) comparison integer` guard. Public inputs become public
  graph guards; secret inputs become secret guards; generated text results are
  represented as public guards whose paired value relation must be established
  by the graph checker.
* One final, unconditional root output of a quoted text literal or a
  lexically resolved public text value (`output value;`). The compiler gate
  rejects secret output; the adapter also requires a bound public text value.
  The supported scope rules prevent branch-local values from escaping into
  this root output, and every model result admitted here is built from public
  text request arguments. The compiler's effective-label check remains a
  required gate; the adapter is not an independent confidentiality analysis.
  It records the exact expression and source binding in the sidecar, then
  omits output content from the billing graph. The output has no continuation
  or effects in this supported subset. Output content is outside the graph's
  billing observer.

Declarations and results obey lexical scopes. A name introduced in a branch
does not escape that branch; nested declarations can shadow visible model,
prompt, and value names. The adapter assigns unique internal identifiers to
each source declaration and resolves every call/guard before constructing the
graph. Calls are lowered to single-call states; sequential source order is
preserved, and branch arms rejoin at the same continuation state.

The current OrchLang grammar has no `for` statement. Its bounded repetition
construct is `retry`, which carries an attempt/failure schedule not represented
by graph version 1. The adapter rejects `retry` rather than treating it as a
fixed unroll. It also rejects `declassify`, `endorse`, `tool`, `emit`,
`require`, multiple workflows, nested external input declarations, nonterminal
outputs, non-text or non-public final output values, non-text call results,
unsupported expressions, and all unrecognized statements. Unsupported source
is an error, not an omitted graph event.

## Example output and checks

For the accepted [`chain_matched.orch`](../examples/research/accepted/chain_matched.orch),
the graph contains a secret choice between two two-call sequences. Each first
call uses the same public input and resolved model contract. Each second call
uses the result from its own first call. The checker establishes the relation
between those result registers and checks the second requests under that
relation. The source-level compiler gate also has to discharge its relational
obligation.

The adapter emits `state_N`, `in_N`, `model_N`, and `r_N` identifiers. For
example, model alias spellings from source do not leak into graph model
identity; a sidecar mapping lets a reviewer trace each generated name back to
source line and binding identity. The graph itself carries the exact decoded
prompt template and ordered literal/value arguments needed by the graph
checker.

The default outputs are `graph.json`, `graph.json.certificate.json`, and
`graph.json.provenance.json`. `--certificate` and `--sidecar` select the
second and third paths explicitly. The sidecar's `certificate_sha256` is a
cross-check for the emitted checker certificate; that certificate is about the
graph and does not certify source translation.

For an identifier output, `omitted_output` records its source name, lexical
binding ID, generated input/register name, text type, public confidentiality,
and source location. The direct source interpreter evaluates that output and
stores it in each probe row. The graph comparison uses only the billing
observation (requests, usage, and stop), since graph version 1 has no output
event.

The new tests include both this matched chain and nested public tests inside
secret alternatives with result-name and model-name shadowing. They compare
the graph probe against `SourceReferenceInterpreter`, a direct evaluator over
the same small parsed AST. The source evaluator and graph probe separately
implement the declared deterministic full-text `Ω` key and response function.
The tests compare complete ordered request descriptors, response text,
input/output usage, and stop status for Unicode, quoted, newline, and ordinary
text inputs across multiple seeds and secret assignments. This is finite
differential evidence for the tested subset, not an exhaustive source parser
or translation proof.

## Existing-source corpus attempt

`audit/evaluate_source_graphs.py` attempts the five files in
`examples/research/accepted/` and the fifteen existing files in
`bench/sourced/balanced/` without editing their prompts, outputs, or control
flow. The compiler gate is recorded for every candidate. The bridge then
reports exports or explicit subset exclusions. Each exported case gets a graph,
producer certificate, provenance sidecar, replay attestation, and probe JSONL
under `bench/results/source_graphs/exports/` and `bench/results/source_graphs/probes/`.
`evaluation.json` records per-file hashes and counts; `corpus_mapping.json`
maps each original source to its result and artifacts.

The finite grid uses seeds 1, 17, and 29; up to four fixed public UTF-8 text
samples per text input; every public Boolean assignment; and every secret
assignment over false/true Boolean values and bounded empty/short/UTF-8 text
samples. For every run, a direct parsed-source AST interpreter and the graph
value probe compare ordered request descriptors, full mock response strings,
per-call usage, and stop status. Final output values are recorded separately
by the source interpreter because output is not in the graph's billing
observer. Under each fixed public store and seed, the
report also compares all secret assignments against the first assignment. A
subset exclusion is reported separately from a compiler rejection. This is a
finite cross-check over selected projections and does not establish adapter
correctness for the language as a whole.

The recorded run attempted all twenty files; the compiler accepted all twenty.
Seventeen exported. The only three subset exclusions are the research retry
example and two balanced retry examples. Across the seventeen graphs, the
finite grid produced 720 direct-source/graph run pairs, 360 secret-assignment
trace comparisons, and 1,584 call events. There were no source/graph or
secret-trace differences. Output values are recorded in probe JSONL and in the
sidecar expression mapping, but are excluded from the billing comparison.
Per-file statuses, hashes, graph certificates, provenance, replay reports, and
full trace probes are under `bench/results/source_graphs/`.

Reproduce after building `orchc`:

```sh
python3 audit/evaluate_source_graphs.py --compiler ./orchc
```

Run the bridge tests with:

```sh
make orchc
PYTHONPATH=audit python3 -m unittest -v test_source_to_graph
```

The source evaluator is an offline test model. It uses the same graph probe
contract: `Ω(resolved-contract, per-contract-ordinal, template,
ordered-text-values)` yields the same deterministic full response for equal
keys; the response has at most `min(max_tokens, 32)` abstract tokens, each
rendered as `chars_per_token` ASCII bytes. That output construction is a
reproducible test choice. The relational claim assumes a cap-respecting shared
oracle; it does not depend on this particular hash response generator.

Input usage is estimated as
`ceil(UTF8_bytes(template)/chars_per_token) + sum(ceil(UTF8_bytes(arg)/chars_per_token))`.
This requires the full complete-request accounting premise: actual modeled
input usage must fit the template estimate plus declared argument bounds in
compatible target-model units. The byte divisor and additive fragment model
do not guarantee real-provider tokenizer or envelope behavior.

Source parsing is capped at 4 MiB, 250,000 lexical tokens, and 128 nested
blocks. The source reference probe accepts seeds in `[0, 2^64-1]`, at most
10,000 calls, and caps each input/request/response at 1 MiB, accumulated
request/response trace bytes at 16 MiB, and control steps at 1,000,000. These
limits apply to the offline differential probe, not static export; a large
`chars_per_token` divisor can therefore export statically but fail closed when
it would require materializing an oversized mock response.

## Guarantee boundary

The adapter applies a compiler-success gate and a graph proof/replay gate. Its
source parser is intentionally narrow and does not use or emit the C++ AST or
IR. Passing all gates is evidence that the particular generated graph passes
the graph rules and replay, with the source/compiler/adapter files bound by
hash. It is not an independently verified source-to-graph translation.

The graph describes modeled request descriptors, not serialized provider
requests. The shared-oracle and input-accounting assumptions remain those in
[`CYCLIC_WORKFLOWS.md`](CYCLIC_WORKFLOWS.md). The adapter does not prove a
provider's behavior, source workflow termination generally, actual invoices,
confidentiality of output data, correctness of an external framework port, or
a finite total budget for arbitrary cyclic graphs. The emitted graph from the
accepted source subset is acyclic because that subset excludes repetition;
cycle acceptance is a capability of the separate hand-authored JSON graph
frontend, not a claim that this adapter translates cyclic OrchLang source.

The source-language relational signature includes literal expression kind in
request identity. Boolean `true` and text `"true"` remain distinct even when
their displayed spellings match. Graph version 1's argument atoms are
type-erased, so the adapter rejects non-text literal call arguments and
accepts only quoted text literals or text identifiers. The shipped
[`typed_literal_collision.orch`](../examples/research/rejected/typed_literal_collision.orch)
is a compiler-level counterexample to comparing rendered literal bytes alone.
