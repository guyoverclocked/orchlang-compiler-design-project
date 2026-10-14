# Pre-freeze reproduction and package audit

Scope: read-only recheck of `scripts/reproduce_scp_strengthening.py`,
`scripts/replicate_completed_state.py`, `scripts/package_scp_strengthening.py`,
`scripts/build_strengthening_pdfs.py`, and the rc3 packaging change. I did not
run the full reproduction, build a wheel or PDF, create publication archives,
or read held-out source bytes. Held-out result/implementation metadata was
previously inspected only for denominator and custody statements. Focused
temporary Git-repository probes exercised both the earlier failing guard and
the patched guard; all fixtures were created and removed inside this review
directory.

## Verdict

**Ready for the frozen run after the planned source commit.** The patched
source guard passes the focused adversarial probes; the runner, packager, and
replication stage support a clean run-specific reproduction directory. The
packager now binds the claim logs and replication evidence to the selected
manifest, verifies and includes the PDF build logs, and the rc3 documentation
points to the current candidate. This audit did not run the frozen profile.

## Findings

1. **The source-guard bypass is closed by the latest patch.** The old guard
   used `git ls-files`, skipped any path containing a component named `build`,
   and omitted root-level files. I reproduced that bypass before the patch.
   The current guard builds its membership set from `git ls-tree <revision>`,
   walks the checkout including the root, prunes only Git metadata and the
   three explicit venv roots, and rejects symlink source paths outside those
   roots. Its only build-output exception permits a `build/lib/<module>.py`
   file when its bytes equal the corresponding committed `audit/<module>.py`.
   Re-running the same fixture now rejects staged `scripts/staged_payload.py`,
   `scripts/build/importable.py`, root-level `root_payload.py`, and a root-level
   source symlink. An exact generated `build/lib/mod.py` copy of committed
   `audit/mod.py` remains allowed. The fixture was temporary; no source bytes
   from the held-out cohort were opened.

   The committed-source fingerprint includes TOML, lock, YAML, Makefile and
   selected JSON configuration, while the extra untracked scan checks
   executable/source suffixes. That is consistent with the guard's stated
   untracked-source scope; if an untracked configuration file can affect a
   stage, extend the suffix set to cover that configuration type too.

2. **The full-profile gate now enforces all 19 stages in order.** The runner’s
   optional flags produce the names in `FULL_PROFILE`, including native,
   Coq, wheel and pinned LangGraph stages. The packager requires exact ordered
   equality and exit code zero for every row, so a partial profile or reordered
   set fails. This resolves the former set-membership-only check.

3. **The relevant LangGraph package versions are now checked.** The pinned
   runtime identity stage asserts `langgraph==1.2.14` and
   `langchain-core==1.6.9`, and the runner preserves the venv executable path
   instead of resolving its symlink to the base interpreter. This addresses
   the prior runtime-version gap. It establishes those two package versions,
   not a hash of the complete installed environment; keep “pinned” scoped to
   the declared packages and interpreter path.

4. **Claim evidence is checked and its scientific boundaries are clearer.**
   The packager now rejects claim paths absent from either the committed
   source fingerprint or evidence inventory, and it checks the files exist.
   The Coq `.v` source is covered by the Git source archive/fingerprint. The
   finite-capsule claim now explicitly describes a replay of previously
   recorded finite models, without fresh source execution or whole-file
   admission. The transfer statement gives the separated counts: 0 admitted,
   9/9 candidates unsupported, and one retrieval failure among 12 selected
   repositories. These are materially clearer. The packager still uses
   hard-coded claim strings rather than deriving their numbers from each
   result; the required validators and exact stage profile must remain the
   independent checks for those values.

5. **The PDF gate binds the final source and PDF bytes through a build
   receipt.** `build_strengthening_pdfs.py` records the Tectonic command and
   version, source and PDF byte counts/hashes, exit codes and logs. The
   packager requires a passed two-document receipt and exact source/PDF record
   matches for the files being packaged. This resolves the earlier missing
   TeX-to-PDF binding. The receipt is local hash custody, not a signed compiler
   attestation or visual review; the script’s own scope text says visual QA
   and scientific validity remain separate. Tectonic may fetch TeX packages
   when needed, and the receipt does not pin/hash the compiler binary or its
   package cache, so describe the build as recorded rather than hermetically
   reproduced.

6. **Fresh run and replication outputs are now plumbed through packaging.**
   The reproduction runner accepts a run-specific `--output-dir` and refuses
   to overwrite a manifest already marked as a passed frozen run. The
   packager accepts `--reproduction-manifest` and locates the state-replication
   result relative to that manifest. The replication runner now rejects any
   populated destination. These close the prior output-mixing path when the
   final run uses a fresh directory. The publication archive/index destination
   remains fixed and is rewritten when packaging; retain prior package files
   separately if multiple versions must be preserved.

7. **The rc2 documentation ambiguity is resolved.** The publication-upgrade
   and software-metadata pages identify rc2 as historical and point to rc3;
   the installation guide names the rc3 wheel artifact. The software metadata
   reports rc3 as the current candidate while labeling older rc2 run
   identifiers historical.

8. **No human/API/submission result is fabricated by the packager.** Its
   explicit fields are `human_reproduction: pending`, `journal_submission:
   not performed`, and `paid_api_calls: 0`; the API claim says approval is
   pending. The transfer denominator above is based on the already inspected
   metadata, not source contents. No live provider calls or human reproduction
   were performed in this review.

9. **Custom reproduction manifest evidence is now bound to the selected
   run.** IR, SLICE and EXACT claim log paths come from their stage rows in the
   selected manifest. The packager adds every stage log and the manifest to
   the evidence inventory, verifies row log hashes, and verifies/includes
   each PDF build log against its receipt record. This resolves the stale
   default-path claim issue.

## Resolved earlier findings

- Ordered full-profile validation and inclusion of the completed-state review
  stage are implemented.
- Claim evidence must exist and be indexed; proof-source custody through the
  source archive is clear.
- The capsule replay and transfer denominator claims now state their limits
  and counts directly.
- The final PDF files must match a successful two-document build receipt.
- The runner checks the declared LangGraph/Core versions and keeps the venv
  launch path intact.
- The reproduction output can be isolated, the packager accepts its manifest,
  and the replication tool refuses a populated destination.
- `docs/PUBLICATION_UPGRADE.md` clearly labels its rc2 content historical and
  points readers to the rc3 candidate.
- Selected-manifest claim logs, replication output and PDF build logs are
  included and bound to their recorded hashes.
- The packager records author fields as placeholders, paid API calls as zero,
  human reproduction as pending, and journal submission as not performed.

## Remaining pre-run action

No further review change is needed before the freeze. Commit all intended
code/config changes, then run the exact 19-stage profile on that immutable
revision using the declared pinned environment and a new output directory.
No frozen reproduction, publication archive or final PDF build was run during
this review.
