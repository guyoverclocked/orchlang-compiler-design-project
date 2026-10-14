# Reproduction runner development record

The first full development invocation used `--allow-working-source`; it did
not claim a frozen source revision. It failed before native build because the
runner scheduled the Python audit suite first. Two suite setup classes require
`orchc`; the new checkout had not built that binary. The original failed
manifest and log are retained under
`output/scp_strengthening/reproduction/development_attempt_1/`.

The runner was corrected to build/test the native core before its dependent
Python audit stage when `--native` is requested. Default prototype/recorded-data
checks do not claim the native-dependent audit suite. The full final run must
be performed again after source commit, with `frozen_source_verified: true`.
No source outcomes, held-out candidates or timing samples were selected or
dropped as part of this dependency-order repair.

The second development invocation built the native core and passed the audit,
frontend, prototype, provider and capsule suites. Its independent parser probe
then found that the system Python accepted a 1,500-level JSON array where the
earlier review interpreter had rejected it through its recursion guard. The
failed manifest/logs are retained under `development_attempt_2/`. Both new
contract tools now apply an explicit 64-level iterative JSON depth cap. This
does not limit the length of a flat history list or a valid graph prefix.

Additional adversarial review found certificate producer/reader item limits,
accumulated-rational digit limits and unfinished recursive state accounting
were inconsistent. The exact checker now reserves every state before descent,
allows certificate rationals within its bounded arithmetic domain, and checks
output tree/byte limits. The conservative checker also validates its produced
certificate tree before emission. Reproduction after these repairs is a fresh
run, not exclusion of prior failed checks.

The third development run passed through native/audit/prototype/capsule checks,
the independent law enumerators, wheel smoke and Coq. It then failed the
LangGraph suite: the wrapper resolved the venv executable symlink to the base
interpreter, losing its packages. `development_attempt_3/` retains that failed
manifest/logs. The wrapper now preserves the executable launch path and checks
LangGraph 1.2.14 / LangChain Core 1.6.9 before running the framework stages.
The pre-freeze audit also led to an untracked executable-source guard, a full
ordered stage-profile gate, explicit claim/evidence membership checks and a
required TeX/PDF build receipt. These are custody/runner repairs, separate from
the mathematical and source-execution results.
