# Publication upgrade: scope and reproduction

This is the 0.5.0rc2 research-software candidate, prepared for Science of
Computer Programming's Original Software Publication track. The new paper is
`submission/research/manuscript/OrchLang_SCP_Publication_Upgrade.tex`; earlier
papers, slides and generated reports remain historical artifacts. A journal
submission is not performed by these scripts. Author identities and declarations
remain placeholders at the author's request.

## What changed

The source frontend rejects LangGraph-reserved node names and `str`/`bool`
annotation shadowing that disagrees with the runtime's typed schema. The exact
trace-law report has versioned UNKNOWN diagnostics and work counters. Independent
replay shares certificate-word prefixes while checking the same exact row-span
obligations. Independent replay reserves adjacency and parsed-row storage before
constructing those allocations.

`proofs/publication_upgrade/AtomicUpdates.v` proves request-history and
local-result agreement for normalized straight-line node semantics under the
explicit atomic-read side condition. It does not verify the Python AST parser,
final returned state, arbitrary LangGraph or the full checker. The recovered
historical Coq calculus remains on its separate research branch and is not
attributed to current code.

The frozen external-source study selects 12 repositories and 59 original
candidate files, all unsupported by the current narrow frontend. This is a
negative transferability result, not a successful framework-port benchmark.
The unchanged incident-triage integration remains a separate source-specific
offline study. Local tokenizer calibration is separate from mathematical model
proofs and from provider invoices. Agent cross-reviews are not independent human
artifact evaluation. Detailed reasoning and primary sources are under
`research/publication_upgrade/`.

## Environment setup

The native core needs make and C++17; the analysis wheel needs Python 3.10+.
The recorded full integration run uses Python 3.14.6 and LangGraph 1.2.14.
Set up two separate environments because the historical integration locks have
different LangSmith versions:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r integrations/langgraph/requirements.lock
.venv/bin/python -m pip install --no-deps --require-hashes -r research/publication_upgrade/tokenizer_requirements.lock
python3.14 -m venv integrations/incident_triage/.venv
integrations/incident_triage/.venv/bin/python -m pip install -r integrations/incident_triage/requirements.lock
```

The wheel builder needs pip, setuptools and wheel available to a local Python
interpreter. The recorded wheel build uses Python 3.11 with setuptools 82.0.1.
Install Rocq/Coq with the `coqc` compatibility command; the checked proof tool
was Rocq 9.3.0, OCaml 5.5.1. Plot generation uses Matplotlib 3.10.8 in the
interpreter that runs the wrapper; this optional research dependency does not
become a dependency of the analysis wheel.

The first tokenizer setup can retrieve public vocabulary data:

```sh
.venv/bin/python research/publication_upgrade/tokenizer_calibration.py --allow-download
```

The normal calibration blocks data downloads and uses the frozen cache. No
model API, provider key or paid request is required. The external corpus bytes,
licenses and immutable source manifests are already included. Its `--freeze`
option is selection setup and must not be used to rerun this fixed evaluation.

## Frozen reproduction and custody

Commit source changes first, then run against that complete immutable revision:

```sh
python3 scripts/reproduce_publication_upgrade.py --source-revision HEAD
```

For the delivered candidate, check out the full source revision printed in the
new paper and manifest before reproducing. A later commit containing the
companion paper is a distinct artifact identity. The runner requires HEAD to
equal the declared code revision; the packager can bind that earlier code to
the subsequently written paper after the fresh run has completed.

This runs native sanitizer/optimized checks, Python suites, authored studies,
pinned LangGraph execution, installed-wheel smoke tests, the unchanged upstream
incident study, the frozen original-source corpus, local tokenizer calibration,
five repetitions per scaling size, the same-input previous-code comparison,
and both current IR proofs. Full local Git history is needed for the audited
preceding compiler and solver revisions. Fresh run logs are under
`output/publication_upgrade/reproduction/`; a failed run has `status=failed`.
Source files must match the supplied revision before and after execution.

After writing and compiling the new standalone paper, bind and package it:

```sh
python3 scripts/package_publication_upgrade.py --source-revision FROZEN_SHA \
  --manuscript submission/research/manuscript/OrchLang_SCP_Publication_Upgrade.tex
python3 audit/publication_provenance.py output/publication_upgrade/publication_manifest.json \
  --manuscript submission/research/manuscript/OrchLang_SCP_Publication_Upgrade.tex
```

The resulting source archive is an exact Git archive. The evidence archive
contains the fresh result files, source/evidence hashes, claim references and
the paper. Timings and platform records naturally vary across machines; frozen
hashes bind the recorded run, not a promise of byte-identical timing reports.
The provenance checker verifies custody, not the truth of a theorem or an
experiment. Scientific replay and proof compilation remain separate checks.

## Remaining publication work

The candidate does not support unrestricted original Python workflows; the
zero-admission corpus result should guide future integrations rather than
broader claims. Whole-source refinement, errors/retries in stochastic kernels,
real-provider telemetry and an independent colleague's reproduction remain
uncompleted research or evaluation work. Supply final author details,
affiliations, contact information, contributions, funding and competing-interest
declarations, review all AI-assisted outputs, and obtain a persistent archive
identifier before submitting the paper. These facts are not synthesized.
