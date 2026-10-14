# SCP strengthening candidate: 0.5.0rc3

This candidate extends the rc2 software and evidence after a further review.
The review was input for technical investigation, not an official journal
decision. The frozen code revision is `8533214105aad0cc015ea1e1c2aad4057515aff7`.
The new main paper and technical supplement, written after the passing freeze,
are in `submission/research/manuscript/OrchLang_SCP_Strengthened.tex` and
`OrchLang_SCP_Technical_Supplement.tex`; matching PDFs are in `output/pdf/`.
The final source/evidence archive identities are in
`output/scp_strengthening/publication/archive_receipt.json`. The earlier rc2 release and its numerical results remain
historical records; use the new reproduction command below for this candidate.

## Results and their subjects

| Evidence | Result | Scope |
|---|---|---|
| Coq/Rocq refinement | Returned-state and finite-prefix graph refinement, including routed cycles; seven closed-context reports | Normalized paired IR and stated read/uniqueness/route premises. Extraction, initialization, register naming, implementation and provider semantics remain trusted bridges. |
| Completed-state differential | Eight authored workflows: 96 completed and 8 cutoff comparisons; 224 call events | Pinned actual LangGraph and a shared offline oracle. Full ordered request/response/usage traces, status and completed source-state projection are compared. Partial eager registers are not reported as completed state. |
| Public-source capsules | Two exact source slices, 6 and 12 finite schedules, separately replayed rational laws | Immutable public-source statements/callables with explicit local mocks, observation projections, STOP/error records and local isolation. These are not whole-file static admissions or deployed-provider validation. |
| Source transfer | Development cohort 0/59; disjoint holdout 0/9 | Holdout selected 12 repositories, retrieved 11 and 1,580 Python paths; one archive exceeded 128 MiB. 240 non-candidate parse errors are retained. Repository failures and file outcomes have different denominators. |
| Robust row-ball contract | Conservative rational finite-trace TV upper bound; sharp fixture 91/100 versus per-depth bound 99/100 | Caller supplies full-history centers/radii and complete finite alphabet. Replay shares some arithmetic helpers, and is not structurally independent or formally verified. |
| Exact row-polytope contract | Exact rectangular worst-case TV; fixture 1/2 versus conservative pathwise 1; 26 development contracts and 20,739 exhaustive law-pair comparisons without mismatch | Caller supplies convex hulls of rational row generators. Both prefix masses are retained. Shared/global row parameters are excluded; empirical provider inclusion is unproved. |
| Structured scaling | 27 additional synthetic cases, 122 operation/version groups, 732 raw rows (610 measured) | Branches, history, mutable registers, cycles, response support and alphabet vary. UNKNOWN remains UNKNOWN and is excluded from completed-result latency. Raw failures from harness development remain recorded. |
| API preparation | Eight frozen synthetic payloads, up to 16 requests; offline transport tests | Mapped OpenAI Responses envelope shapes only. Actual calls, model selection, provider/SDK fidelity, probability radii and billing validation are pending. |

The backend now emits execution format version 2 with `final_values` after a
normal stop. That map contains its initialized inputs/results/temporaries.
The source study projects named input and returned-state slots, removing internal
temporary registers. `final_values` is `null` on truncation or runtime/resource
failure, because a cap may interrupt an atomic source node.

The exact uncertain-distance and conservative row-ball tools are research
prototypes included in the source artifact; they are separate from the eight
installed graph-analysis commands. They do not consume source code or infer an
external probability model. Their APIs and certificate trust boundaries are in
the respective READMEs under `research/scp_strengthening/`.

## Reproduction

Install the locked optional runtime in a fresh environment (public package
downloads at setup; no provider key or API call):

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r integrations/langgraph/requirements.lock
```

Install Rocq/Coq with `coqc` for the proof stage. The recorded proof tool is
Rocq 9.3.0; CI checks its available Ubuntu Coq version separately. The native
stage needs make and a C++17 compiler. Optional wheel smoke validation requires
local setuptools/wheel, and does not download build dependencies.

From a checkout of the manuscript's exact code revision:

```sh
python3 scripts/reproduce_scp_strengthening.py --source-revision HEAD \
  --langgraph-python .venv/bin/python --coq --native --package
```

The standard-library stages run robust/exact/API fake-transport suites, verify
the held-out result bindings without rescoring, validate recorded structured
timing rows, and independently replay the recorded finite capsule laws. The
optional LangGraph stage executes the authored completed-state study and its
separate comparison truth table. The proof stage builds only in a disposable
tree. Logs and fresh-stage status are written to
`output/scp_strengthening/reproduction/`. Recorded scaling validation is not a
fresh timing run; the full timing reproduction command is in
`research/scp_strengthening/scalability/PREREGISTRATION.md`.

The runner refuses to overwrite a passed frozen run. For a later replication,
use a fresh result directory, for example
`--output-dir output/scp_strengthening/faculty_replication`. Its source guard
uses the declared Git tree (including staged additions as uncommitted), checks
executable/proof/config bytes, and rejects additional source outside explicit
runtime environments and byte-identical wheel build copies. Python, native
compiler, proof kernel and installed dependency/runtime integrity remain
environment premises; this is a custody guard, not proof of the host.

The source-slice execution runner uses a host-specific macOS Seatbelt profile
and a pinned Homebrew runtime path. Its independent JSON/source-hash replay is
portable; its isolated source execution is not advertised as portable. Read
`research/scp_strengthening/workflow_capsules/REPORT.md` before attempting a
rerun on another host. It denies network, writes, fork and unlisted user files;
the recorded `/opt` readability limitation remains explicit. No unchecked
external Python is imported by the ordinary reproduction command.

## Research positioning and remaining publication work

This is a specialization and integration of established resource-aware
information flow, relational cost analysis, rational automata, coupling,
imprecise probability and compiler refinement. The new focused literature
matrix includes adjacent 2026 static-budget and workflow-assurance systems.
No algorithmic priority, representative workflow coverage or acceptance
probability is asserted.

The faculty reproduction form is deliberately blank: an agent's cross-review
is not an independent human reproduction. Author names/affiliations remain
placeholders by request; correspondence, contributions, funding, conflicts,
final human review, persistent archive identifier and journal submission remain
to be completed by the authors. Real API execution also requires a chosen
provider/model and affirmative budget authorization. None of those facts is
invented by this candidate.
