# Audit evidence: 23 October 2026

Repository base: `a49fcdbdaa99723d7b6e1913f6d01e4f88682dd9`, branch `main`.

This directory contains fresh test output and an executable counterexample for the publication audit. The master plan is [../../docs/PUBLICATION_MASTER_PLAN.md](../../docs/PUBLICATION_MASTER_PLAN.md). No production source was changed in this audit. Ignored local `.exe` binaries are conveniences, not release artifacts; rebuild them from source.

## Results

- `tests.txt`: fresh build, 95/95 tests passed.
- `shadowed-model-contract.orch`: a branch-local model-name collision with different model contracts/output caps.
- `shadow-check.txt`: compiler accepts the program and reports unary bound 1001.
- `shadow-true.txt`: seed 1, secret true; total usage 2.
- `shadow-false.txt`: seed 1, secret false; total usage 987.

The witness contradicts the intended relational paired-execution guarantee. It does not violate this program's unary bound. The immediate implementation issue is lexical model names being used as semantic contract identities in `src/relational.cpp` (lines 34 and 144 at the base commit). Distinguish binding resolution from semantic equivalence when repairing it.

## Reproduction on the audited Windows machine

Run PowerShell from the repository root. The following is the installed toolchain location; on another machine supply a suitable C++17 compiler instead.

```powershell
$auditToolchain = 'C:\Users\nambi\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin'
$env:PATH = "$auditToolchain;$env:PATH"
$auditSources = Get-ChildItem src/*.cpp | Where-Object Name -ne 'main.cpp' | ForEach-Object FullName
& "$auditToolchain/g++.exe" -std=c++17 -Wall -Wextra -pedantic -O2 -Iinclude @auditSources tests/tests.cpp -o research/2026-10-23/tests.exe
& ./research/2026-10-23/tests.exe
& "$auditToolchain/g++.exe" -std=c++17 -Wall -Wextra -pedantic -O2 -Iinclude @auditSources src/main.cpp -o research/2026-10-23/orchc.exe
& ./research/2026-10-23/orchc.exe check research/2026-10-23/shadowed-model-contract.orch
& ./research/2026-10-23/orchc.exe run research/2026-10-23/shadowed-model-contract.orch --seed 1 --pin s=true
& ./research/2026-10-23/orchc.exe run research/2026-10-23/shadowed-model-contract.orch --seed 1 --pin s=false
```

The observed compiler was GCC 16.1. Record your own compiler version and command exit codes. After a correct repair, `check` should reject this secret-dependent contract mismatch under the existing relational goal, or require a sound explicit alternative contract. Do not regenerate the historical logs to hide the original behavior.

The old tracked benchmark counts discussed in the master plan were inspected, not freshly rerun. Local/remote LLM experiments and the proposed proof development were not performed in this planning audit. No paid API request was made.
