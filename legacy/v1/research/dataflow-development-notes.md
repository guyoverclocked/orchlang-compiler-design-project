# Dataflow strengthening: decisions and failed attempts

24 October 2026 (Asia/Calcutta). This is a development extension of the software
artifact, not a claim to a new general relational logic.

- Added a Lean state-transformer semantics whose calls bind actual response text
  and whose downstream requests use those bindings. The normalizer theorem now
  applies to stores and response-dependent requests under shared public inputs
  and stateless kernels. Source parsing remains trusted Python.
- The first source preflight gets E230 in the C++ checker: branch-local responses
  carry the secret PC label. The separate resource-distribution judgment is not
  an implicit declassification or a precision win over that different policy.
  The example was placed in examples/certificates, not examples/valid.
- Tightened the shared restricted lexer from Python's Unicode whitespace class
  to the C++ language's four ASCII whitespace characters. NBSP, vertical tab and
  form feed are now rejected. This repairs source-reader agreement; it is not a
  new theorem about the entire parser.
- The new dataflow reader permits literal outputs only at workflow root. It
  rejects branch outputs rather than allowing a resource-only projection to
  hide an explicit output channel. Source retry is still unsupported; core retry
  is checked separately with status-valued errors and full-attempt billing.
- Freeze a321aee2a29ae33d00d497833722578a8d873002 generated all 256 source/core cases
  and 3,072 Python reference/replay contexts, then Lean stopped at its 16 MB
  transport guard. No Lean execution contexts completed in that attempt. Its
  initial manifest incorrectly remains `running` because failure persistence
  had not covered that helper exception. Source/context/input files are retained
  outside the repository in runs/dataflow-v3; do not use it as a successful run.
- Operational amendment: send unchanged cases in batches of 16, retaining each
  process command/exit/stdout/stderr and marking helper errors failed. Selection,
  public values, kernels and endpoints are unchanged. Extra hand-authored
  boundaries and malformed-input regressions are reported separately.
- Batched freeze df3ad0d5861bb8c32ee9edd49e8b7cad7edce71c completed all three
  execution comparisons without disagreements, but the campaign correctly
  remained failed: 240 sources got E222 for declaring unused parameters in
  constant prompts. Those are invalid source constructions, not unsafe
  rejections. The repaired generator uses zero-argument prompts/calls for fixed
  requests. Expected serialized requests/cores and all kernels/endpoints remain
  identical. Both independent source readers now enforce the unused-parameter
  rule. All v4 raw results and failure flags are retained; report the first
  complete successful amended run separately.

No live API, model inference, GPU run or key is involved. USD 0 spent/reserved.
Do not describe the new retained campaign or manuscript update as completed
until their fresh runs, comparisons and render checks actually finish.
