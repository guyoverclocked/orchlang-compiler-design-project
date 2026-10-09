# Independent relational stress study

This study checks whether the compiler's relational gate admits the generated
balanced chains while a separate Python interpreter observes equal modeled
requests and abstract usage across secret assignments. The Python interpreter
uses the generated AST directly; it does not invoke the C++ runtime, inspect
compiler analysis facts, or consume a compiler certificate. The C++ compiler is
used only for `orchc check` on the rendered source.

This is finite validation of a narrow sufficient static check. It is not a
proof of the compiler, a new general relational analysis, an exhaustive test of
OrchLang, or evidence about provider behavior.

## Reproduce

From the repository root, run:

```sh
python3 -m py_compile audit/relational_stress.py audit/test_relational_stress.py
PYTHONPATH=audit python3 -m unittest -v test_relational_stress
python3 audit/relational_stress.py
```

The study command runs the C++ binary at `./orchc`, calls only its `check`
subcommand, and writes `bench/results/relational_stress.json`. The report
records the compiler binary SHA-256, generator SHA-256, source-manifest
SHA-256, and a SHA-256 and byte length for every generated source file. Case
generation is deterministic from the script and reported generation-seed
formula. The six oracle seeds are also recorded in the report.

The command exits nonzero if any generated positive case fails `check`, any
expected mutation is accepted or lacks E236, the independent reference finds
an accepted-case request or usage difference across secret assignments, or a
per-call accounting/cap/budget premise is violated. A rejected negative case
with no witness in the finite probe grid is marked unknown and does not cause
failure.

## Generated programs and probe grid

The default run generated 264 programs: 24 instances of each accepted shape
and 24 instances of each mutation. The six accepted shapes are:

1. A dependent call chain in each arm of a secret branch.
2. A public branch nested under a secret branch, with chains in each leaf.
3. A bounded retry around a dependent chain in each secret arm.
4. Two nested secret branches, with a dependent chain in every leaf.
5. A public outer branch containing a secret branch and a chain in each leaf.
6. A dependent chain that shadows a result name in a nested public branch.

For each instance, the deterministic generator varies chain length, model cap,
template prefix, separators and suffix, literals, and which of two aliases is
used at each call. The aliases resolve to the same provider, model ID, and
output cap, so this study does not test cross-model chains. Text inputs `x`
and `y` are independently assigned from six pairs containing empty text,
ordinary prose, Unicode, quotes, backslashes, braces, tabs, and newlines. The
public Boolean input takes both values. Each accepted program is run through
the reference interpreter for all secret assignments, every public scenario,
and six fixed oracle seeds. This gives 13,824 pairwise comparisons against the
first secret assignment.

Five mutation classes alter one property in a secret-arm call: the resolved
model cap, template bytes, argument binding, argument order, or retry bound.
All 120 mutations are required to fail `orchc check` with E236. Their reference
probes are classified separately. The argument mutation also has an explicit
equal-value subgrid: the two public text values coincide, so all 1,728
comparisons there have equal traces, while the static rule still rejects the
different lexical bindings. This is a finite conservative example, not a
measured false-positive rate.

## Independent reference semantics

At each call, the reference interpreter substitutes the complete concrete
argument strings into the decoded template, preserves the resulting full
request text in the ordered trace, and charges UTF-8 bytes. For this generated
study, one UTF-8 byte is one abstract input-use token and `orchc check` is run
with `--chars-per-token 1`. The tested input-accounting premise is that each
complete rendered request uses no more than the raw template byte length plus
the declared bounds of its ordered arguments.

The response oracle is modeled as Ω(M, k, Q): SHA-256 over a fixed seed, the
canonical resolved model contract M (provider, actual model ID, and output
cap), that contract's call ordinal k, and the complete rendered request Q
selects a deterministic ASCII response of zero through `max_tokens` bytes.
Aliases and source binding names are absent from Q. Retry success or failure
uses a separate deterministic schedule shared by secret executions at the
same retry ordinal and attempt. This gives a request-sensitive full-text
reference semantics under the stated byte and cap assumptions; it is not the
compiler's runtime mock and is not a real LLM/provider model.

## Result

The frozen compiler binary accepted all 144 generated positive programs and
rejected all 120 mutations with E236. The independent interpreter performed
24,192 accepted-program runs, 66,240 model calls, and 66,240 per-call input
accounting checks. Across the 13,824 accepted pairwise comparisons, it found
zero ordered-request-trace differences and zero usage/billing differences.
The retry family exercised 5,064 attempts.

Of the 120 statically rejected mutations, 117 had a request-and-usage witness
in the finite probe grid. Three retry-bound mutations had no witness in this
grid and are recorded as unknown, not as false positives. The full first
witness traces, when present, are retained in the JSON report.

The run used compiler SHA-256
`5bae3be94e9b7d747728965e2562d06a9844d47b28f871c6fe44dcb6f0a7aa43`, generator
SHA-256
`c90e6d101d31f609eae804e60a5346df6ae7c3dcc5df8a1354f7c7aedc483a8b`, and
source-manifest SHA-256
`a48a89f19bb527b94f1f40844fe1a9cb062cb0176c538ba53cd6f7115eb72e6f`.
These hashes and case-level details are also recorded in the JSON report.

## Scope and limitations

- The generated programs exercise six structures and five controlled
  mutations; the study does not cover the full language grammar or arbitrary
  user programs.
- Only no-declassification cases are generated. The results do not establish
  universal billing noninterference for declassification workflows.
- UTF-8 byte accounting with `--chars-per-token 1` is an explicit test model.
  It does not model tokenizer boundary effects, request envelopes, provider
  billing, output text quality, time, or deployed service behavior.
- The output oracle respects each declared cap by construction. This does not
  establish that a real provider honors the cap.
- The reference evaluator and compiler analyzer are separate implementations,
  but they share the generated AST as the source for rendering and reference
  evaluation. The check is therefore differential with respect to their
  semantics, not an independent source parser or proof assistant.
- Finite rejection probes are evidence only when they find a witness. Absence
  of a witness is reported as unknown.
