# Closed-request certificates and replay

For public text inputs and downstream response use, see the separate
[DATAFLOW_CERTIFICATES.md](DATAFLOW_CERTIFICATES.md) path. The closed path below
retains its original restricted scope.

This additional certification path is independent of C++ `check` and `certify`.
It reads source again, constructs fully substituted text requests, and checks an
untrusted normal-form plan with Lean 4.19.0. Python's source reader, SHA256
binding, serialization, Lean's JSON library and execution environment are
trusted. The normalizer/checker theorem applies to the decoded finite core.
This is not a proof of the full source implementation or a cloud-provider claim.

From the repository root, with Python 3.10+ and Lean 4.19.0:

```text
python scripts/closed_certificate.py issue examples/valid/closed_certificate.orch /new/output/certificate.json --lean /absolute/path/to/lean
python scripts/closed_certificate.py check examples/valid/closed_certificate.orch /new/output/certificate.json --lean /absolute/path/to/lean
```

Use a writable existing output parent; issuance refuses to overwrite a file.
Changing source bytes invalidates the certificate. Changing the core is detected
by independent reconstruction. Changing its plan is checked by Lean. Hashes
bind files but are not author signatures or provenance authentication.

The source fragment admits one workflow, secret Boolean guards, lexical mock
models, text-only prompts and literal arguments/outputs. It rejects input pins,
response-dependent requests, retries, tools, prices and reclassification.
The certificate concerns ordered resource traces under shared, stateless finite
kernels indexed by full request and contract. Its contracts explicitly use raw
UTF-8 and byte counts. They do not reinterpret C++ mock budget units. The declared
source budget is recorded by the reader, not checked as a byte-token budget.
Calls' return texts are unused in this closed fragment. Probability semantics
requires normalized nonnegative kernels, beyond the algebraic Lean theorem.

`runtime/replay_adapter.py` separately executes text-valued finite tables using
explicit choice tapes. `runtime/finite_reference.py` enumerates semantics.
Both bill errors and stop retries when no call failed in an attempt. This retry
rule is covered by the closed-core Lean proof, but differs from the C++ mock's
independent retry-failure sample. Source retry therefore fails closed here.

```text
python scripts/check_replay.py --output /new/output/replay-run
python scripts/check_certificates.py --programs /generated-run/programs.json --lean /absolute/path/to/lean --output /new/output/certificate-run
```

Conformance retains every request, trace and exact weight for 12 fixed cases:
two synthetic units, three retry bounds and two public-guard values. Additional
tests check downstream text requests, invalid kernel mass/status, lexical scope,
missing requests and an unselected cap violation. This is finite replay
validation. GPT-2/BERT tokenizer probes are separate exact-library experiments;
neither component runs model inference or establishes a provider contract.
