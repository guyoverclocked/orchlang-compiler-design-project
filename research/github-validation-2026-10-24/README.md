# Fresh checkout validation before the GitHub push

Source: `9f4975e346ec7eecfe8819a2a889b48e4d3a4869`, cloned into a new local
directory on the author's Windows machine. This is an engineering check by the
same primary AI implementer, not independent human review or a new experiment.
The source checkout was clean before and after execution. Subsequent publication
updates record these results and adjust the integrity verifier/documentation;
they do not change the compiler, runtime, proof or test sources.

The fresh run builds both executables and passes 106 C++ tests, 47 Python tests
and all three Lean 4.19.0 files, with no recorded runner failures. It also
rechecks the existing examples, source diagnostics, malformed CLI inputs,
structural cost comparisons and fixed-seed mock bounds. The main generated
research campaigns were not rerun in this publication check; their retained
observations and exact source bundles remain available.

- [Summary and scope](summary.json)
- [Fresh CPU manifest](cpu/manifest.json)
- [Every command, exit code and captured output](cpu/commands.json)
- [Workflow observations](cpu/results.json)
- [Source-file checksums](cpu/source-files.json)
- [Retained-file checksums](files.json)

The reviewed PDF and four source bundles verify against publication/manifest.json;
all 76 files covered by the two original raw-evidence hash maps also verify.
Three manuscript evidence TeX files regenerate byte-identically from included
observations. Seven updated entry-point documents have no missing local Markdown
links. All 42 core source files in the commit match the earlier validated
00420ef snapshot. No provider calls, model inference, API key or payment was used.
API spending/reservations remain USD 0.

Run `python scripts/verify_publication.py` to check the artifact, original raw
evidence and six fresh-validation record checksums. This verifies byte integrity
and bundle structure, not scientific truth or author endorsement. The full fresh
CPU command is recorded in the progress log/reproduction guide; use a new output
directory when rerunning it. Raw records intentionally retain original line
endings and absolute machine paths as provenance.
