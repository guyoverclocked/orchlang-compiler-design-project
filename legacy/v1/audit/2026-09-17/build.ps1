$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '../..')
try {
    $auditToolchain = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin'
    $env:PATH = "$auditToolchain;$env:PATH"
    $auditSources = Get-ChildItem src/*.cpp | Where-Object Name -ne 'main.cpp' | ForEach-Object FullName
    foreach ($target in @(@('src/main.cpp','orchc'), @('tests/tests.cpp','orchlang_tests'), @('audit/2026-09-17/paired.cpp','paired'))) {
        & "$auditToolchain/g++.exe" -std=c++17 -Wall -Wextra -pedantic -O2 -Iinclude @auditSources $target[0] -o "audit/2026-09-17/$($target[1]).exe"
        if ($LASTEXITCODE -ne 0) { throw "Build failed: $($target[1])" }
    }
    & ./audit/2026-09-17/orchlang_tests.exe | Tee-Object audit/2026-09-17/tests.txt
    python audit/2026-09-17/reproduce.py > audit/2026-09-17/reproduction.txt
    & ./audit/2026-09-17/paired.exe audit/2026-09-17/equal_bounds.orch | Tee-Object audit/2026-09-17/paired.txt
} finally {
    Pop-Location
}
