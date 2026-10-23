# Text-dataflow certificates: response contents matter

This additional path supports root public text/Boolean inputs, secret Boolean
guards, lexical mock contracts/prompts and text-valued call bindings. A response
can construct a later request. `proof/DataflowCore.lean` mechanizes the relevant
store semantics; the earlier closed-request theorem remains a separate result.
Only literal outputs at workflow root are permitted. Branch-local outputs fail
closed, so the resource projection cannot silently hide an explicit output channel.

```text
python scripts/dataflow_certificate.py issue examples/certificates/dataflow_certificate.orch /new/certificate.json --lean /absolute/path/to/lean
python scripts/dataflow_certificate.py check examples/certificates/dataflow_certificate.orch /new/certificate.json --lean /absolute/path/to/lean
```

Issuance refuses to overwrite a file. The output parent must already exist.
The same bytes and independently reconstructed core must match when checking.
An untrusted plan is decoded and checked in Lean; it is never executed as Lean
source. The Python reader/slot allocation/serialization/hash binding are trusted.
No verified source parser or full C++ implementation theorem is claimed.

## Guarantee and scope

Text expressions contain literal strings, public/response slots and append.
Calls evaluate the full expression, query a shared stateless kernel indexed by
contract and serialized request, bind the response text and record its UTF-8
byte counts and failure status. Sequence uses the returned store for the next
call. Public Booleans have the same values in the compared executions. Secret
Booleans can affect control only; secret text inputs are outside the fragment.

The normalizer removes a secret branch only when its arms have the same
normalized plan, including response-slot dependencies. Source-local names are
aligned positionally across sibling blocks, with fresh slots after a join.
Lexical lookup prevents branch locals escaping or overwriting an outer binding.
Raw core stores retain unreachable branch-local slots; these slots have no
source-level uses after scope exit. The reference/replay executors erase their
lexical locals. Their conformance comparison is on requests and event traces,
not equality of those internal store representations.

`normalize_correct` proves equality of the complete state-transformer semantics
to its normalized plan, for any shared initial text store and public Booleans.
`relational_sound`, `observer_projection` and `decoded_certificate_sound`
derive equality between secret Boolean stores after a successful check. All
response outcomes are retained, so the proof covers request dependence on
actual response contents. It does not substitute an equal-length response.

As in the closed core, the equality is algebraic over finite weighted lists.
Probability interpretation additionally requires normalized nonnegative kernels.
The executable evaluator checks its explicit rows, rejects duplicate request
keys, invalid rational weights, lost mass and execution limits. A missing
positive-probability request causes lost-mass rejection. The decoder and JSON
library are not proved source parsers. Its bounded enumeration is evidence on
supplied kernels, not a universal provider test.

The core also defines lexical bounded retry with failed attempts billed. Errors
are statuses with response text, not exceptions: a body completes before retry
decides whether any call failed. A successful attempt has no failed call. This
does not promise SDK exception behavior. The core restarts an attempt from its
outer store; local bindings do not escape. Source retry remains rejected because
the C++ mock uses a different failure rule. Timing, tools, stateful providers,
secret request contents, output declassification and money are not modeled.

## Relationship to the C++ checker

The demonstration is deliberately in `examples/certificates`, not `examples/valid`.
The C++ information-flow policy joins a secret branch's PC label into its
responses and rejects their use in later prompts with E230. The dataflow core
can certify matched request distributions under its narrower secret-Boolean
model. These are distinct judgments. No precision ranking or implicit
declassification follows from one checker accepting what the other rejects.
Neither certificate path certifies the source's C++ mock budget as a tokenizer
budget. Declared bounds are recorded, not reinterpreted as byte-token facts.

## Development comparison

`bench/protocols/dataflow-development-v1.json` specifies an exhaustive source
grammar before retained campaign outcomes. It compares source reconstruction
against separately constructed cores, plan checking between Python and Lean,
and event/request distributions among Lean, the finite reference and replay.
Public values and secret contexts are fixed by the protocol; all outcomes are
retained. Separate hand-authored core cases exercise UTF-8, zero/two/nested
retry, empty bodies and lexical shadowing. This is development validation, not
a held-out corpus or a new general relational logic.

```text
python scripts/check_dataflow.py --lean /absolute/path/to/lean --orchc /absolute/path/to/orchc --protocol-commit ACTUAL_CLEAN_COMMIT --output /new/run/directory
```

Supply the real frozen commit from a clean source checkout. The runner checks
the committed protocol bytes and writes outside that checkout. No inference,
GPU or API key is used.
