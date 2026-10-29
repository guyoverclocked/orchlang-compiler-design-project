> Current revision: see [REVISION_STATUS.md](REVISION_STATUS.md),
> [VERIFIED_PRECISION.md](VERIFIED_PRECISION.md),
> [EXACT_ACCOUNTING.md](EXACT_ACCOUNTING.md), and
> [REAL_WORKFLOWS.md](REAL_WORKFLOWS.md) for added commands and evidence.

# CPU reproduction and scoped publication evidence

For the complete explanation and documentation map, start with
[PUBLICATION_STATUS.md](PUBLICATION_STATUS.md). The reviewed PDF, checksums and
exact tested-source Git bundles are available in [publication/](../publication/README.md).
Verify their integrity, including both dated raw-evidence hash maps, with
`python scripts/verify_publication.py` from the repository root. This checks
bytes and bundle validity, not the scientific claims by itself.

Status: clean local snapshots checked; external cost-projection experiment
completed under a disclosed amended protocol. No independent human clean-machine
certification. Historical results are preserved. New runners refuse an
existing output directory and report infrastructure failures separately.

## Quick independent checks

Requires Python 3.10+ standard library. No model, GPU or network access:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

This checks finite text semantics, replay, source binding and structural baseline. It does
not execute the C++ compiler or prove correspondence to it.

For the limited mechanized results, use Lean 4.19.0:

```text
lean proof/BoundedCore.lean
lean proof/FiniteRelational.lean
lean proof/DataflowCore.lean
```

Check process exit codes and the printed axiom lists: `sorryAx` is forbidden.
See `proof/README.md` for exact theorem coverage and local toolchain provenance.

## Fresh C++ build and full development check

Use a C++17 compiler. The default `c++` must be usable, or supply an absolute
compiler path. No silent fallback to an old executable is allowed.

```text
python scripts/offline_check.py --cxx /absolute/path/to/g++ --lean /absolute/path/to/lean --output research/local-new-run
```

On Windows, set task-specific paths to your installed C++17 and Lean
4.19.0 executables, then invoke the runner from the repository root:

    $env:ORCHLANG_CXX = 'C:/path/to/g++.exe'
    $env:ORCHLANG_LEAN = 'C:/path/to/lean.exe'
    python scripts/offline_check.py --cxx $env:ORCHLANG_CXX --lean $env:ORCHLANG_LEAN --output /new/run

The run records source commit, dirty state, tracked patch, hashes of relevant
source/input files (including untracked implementation files), compiler flags,
command arguments/outputs/exits, elapsed times, corpus hash, resource spending
and per-workflow results. Dirty snapshots are explicitly marked; they are not
represented as clean release commits. `commands.json` retains raw command data.
Principal source files must be present in the eventual release to match their
hashes; hashes alone cannot reconstruct missing files.

The runner builds tests and CLI, checks development positive/negative cases with
specific diagnostics, compares compiler bounds to the independent structural
max/sum/multiply baseline, and executes five fixed seeds for each existing cost
workflow. It also validates examples and malformed CLI/pin handling. These are
development checks, not independent external applications or a final precision
study. All failures make the runner exit nonzero. Omit `--lean` only for a
compiler-only run; its manifest will explicitly record `proof_checked=false`.

The original shadow witness can be run directly using the newly built CLI:

```text
orchc check research/2026-10-23/shadowed-model-contract.orch
orchc run research/2026-10-23/shadowed-model-contract.orch --seed 1 --pin s=true
orchc run research/2026-10-23/shadowed-model-contract.orch --seed 1 --pin s=false
```

`check` must now fail with `E236`. `run` is an intentionally uncertified mock
execution command for falsification; it does not require relational acceptance.
The historical 2/987 logs were produced with the original executable before the
repair. Do not replace historical logs with new output.

## Fault injection

```text
python scripts/mutation_check.py --cxx /absolute/path/to/g++ --scratch /absolute/local/scratch --output research/local-new-mutations
```

Mutations occur only in temporary copies, never the working source tree. A build
failure is an infrastructure failure, not a detected semantic mutant. The report
retains every injected fault, compilation exit and test failure. These deliberately
unsound mutants are not competing baselines.

## Optional exact tokenizer boundary check

This optional tier uses `tokenizers==0.21.4`, two pinned public tokenizer JSON
files, and no model weights. Download artifacts once to a local folder outside
the repository, then the probe runs locally:

```text
python scripts/fetch_tokenizers.py --output /absolute/local/tokenizers-v1
python scripts/tokenizer_probe.py --tokenizers /absolute/local/tokenizers-v1 --output research/local-new-tokenizer-run
```

Run the second command with the environment containing the pinned library.
The download uses exact model repository revisions from
`bench/protocols/tokenizers-development-v1.json`, records SHA256, and never
substitutes a model on failure. The probe records library version, script/protocol
digests, source commit, dirty state, tokenizer hashes and every token ID. Both
special-token settings, all texts and all concatenation pairs are retained.
This is a dated development protocol, not faculty-approved final preregistration.
These cases do not demonstrate provider conformance, inference, privacy or
external workflow coverage. Review source licenses before redistribution.

## Independent certificate and replay checks

See [CERTIFICATES.md](CERTIFICATES.md) for executable issuance/checking commands,
the supported source fragment and trusted boundary. This path does not trust
the C++ report as a proof. The closed-core Lean theorem now covers early-stop
retry with billed failures; the source reader rejects C++ retry syntax.

## Release limitations

The owner selected MIT on 23 October 2026. No other person has completed
clean-machine reproduction. Restricted source binding and finite replay are
implemented, but their trusted boundaries remain explicit. External cost
projections were checked under the amended frozen protocol; these are not
functional application translations. Current SCP requirements were inspected.
Public archival release, final author declarations and human review remain
outstanding. Do not call this a submission-ready release.

Current results and exact source revisions: research/validated-2026-10-23/README.md.
Run scripts/report_publication.py against the retained run directories to derive
the manuscript tables. Test-source Git bundles allow reconstruction of the exact
clean revisions even before their eventual public archive.

The response-dependent extension's current evidence is in
research/validated-2026-10-24/README.md. Its clean freeze is
00420ef202dc260fc98237ac584a6210a61e1e5e, with 106 C++ tests, 47 Python tests,
three proof files and the amended 256-source/3,072-context campaign. See
DATAFLOW_CERTIFICATES.md for its exact source/core scope and commands.
`report_dataflow.py --run RUN --cpu CPU_RUN --output NEWDIR` regenerates its
summary/macros. The final table output is tables-v2: the first table's numeric
summary is valid but a diagnostic number produced an invalid TeX macro name.
The repaired generator uses an alphabetic macro name; no result changed.

## Regenerate the manuscript evidence from retained records

The following commands use the included completed runs and need no model,
tokenizer download, GPU or network. Each output directory must be new:

```text
python scripts/report_publication.py --runs research/validated-2026-10-23 --output /new/tables-publication
python scripts/report_dataflow.py --run research/validated-2026-10-24/dataflow-v5 --cpu research/validated-2026-10-24/dataflow-cpu-v5 --output /new/tables-dataflow
```

Compare the generated `metrics.tex` and `external.tex` to the same filenames in
`docs/manuscript/evidence/`; compare `dataflow-metrics.tex` likewise. These three
files must match byte-for-byte. JSON summaries additionally contain provenance
paths, which may differ when regenerated in a different location. A successful
table regeneration reuses retained observations; it does not rerun the original
experiment or create independent experimental evidence.

For exact historical source/protocol reconstruction, clone the appropriate
bundle using the commands in publication/README.md, then follow its checked-in
runner documentation. Do not replace recorded historical commits with the later
main-branch publication commit. Original raw hashes and failed-run statuses
remain unchanged.
