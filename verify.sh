#!/usr/bin/env bash
#
# Proves, from a clean checkout, that OrchLang works and that every committed
# result is reproducible.  Each step either passes or stops the run:
#
#   1  strict build       clean build with -Werror under -Wall -Wextra -pedantic
#   2  unit tests         the assertion suite
#   3  example corpus     every valid example accepted, every invalid rejected
#   4  sanitizers         the tests and corpus again under ASan and UBSan
#   5  benchmark          bench/evaluate.py reproduces bench/results exactly
#   6  demo rehearsal     every live-demo command still says what DEMO.md says
#   7  case studies       case_studies/verify.py reproduces case_studies/results
#                         byte for byte
#
# It writes verification/EVIDENCE.txt: the commit, the toolchain, each step's
# verdict, and SHA-256 digests of the sources and results it verified.  CI
# runs this on Linux and macOS (.github/workflows/verify.yml).
#
#   ./verify.sh            everything
#   ./verify.sh --quick    skip the sanitizer rebuild (step 4)
#
# Portable to the bash 3.2 and BSD tools that macOS ships.

cd "$(dirname "$0")" || exit 2
export LC_ALL=C

QUICK=0
case ${1:-} in
    --quick) QUICK=1 ;;
    '') ;;
    *) printf 'Usage: ./verify.sh [--quick]\n' >&2; exit 2 ;;
esac

OUT=verification
JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
STRICT='-std=c++17 -Wall -Wextra -pedantic -Werror -O2'

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    GRN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
else
    GRN=; RED=; DIM=; BOLD=; OFF=
fi

digest() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi
}

# One digest for a set of files: hash each file, then hash that list.
tree_digest() {
    find "$@" -type f | sort | while IFS= read -r file; do digest "$file"; done \
        | digest | cut -d ' ' -f 1
}

RESULTS=
STEP=0
FAILED=0

pass() {
    printf '  %sPASS%s  %s\n' "$GRN" "$OFF" "$1"
    RESULTS="${RESULTS}PASS  $1
"
}

fail_step() {
    printf '  %sFAIL%s  %s\n' "$RED" "$OFF" "$1"
    RESULTS="${RESULTS}FAIL  $1
"
    FAILED=1
    [ -f "$2" ] && tail -n 30 "$2" | sed 's/^/        /'
    finish
}

begin() {
    STEP=$((STEP + 1))
    printf '%s[%d] %s%s\n' "$BOLD" "$STEP" "$1" "$OFF"
}

finish() {
    write_evidence
    if [ "$FAILED" = 0 ]; then
        printf '\n%sVerified.%s Evidence: %s/EVIDENCE.txt\n' "$GRN" "$OFF" "$OUT"
        exit 0
    fi
    printf '\n%sVerification failed.%s Logs: %s/\n' "$RED" "$OFF" "$OUT"
    exit 1
}

write_evidence() {
    local commit dirty os compiler make_version python_version
    commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)
    dirty=
    if command -v git >/dev/null 2>&1 && [ -n "$(git status --porcelain -- src include tests examples bench case_studies Makefile 2>/dev/null)" ]; then
        dirty=' (working tree has uncommitted changes)'
    fi
    os="$(uname -srm)"
    [ "$(uname -s)" = Darwin ] && os="macOS $(sw_vers -productVersion 2>/dev/null) ($(uname -m))"
    compiler=$(${CXX:-c++} --version 2>/dev/null | grep -v -i '^configured with' | head -n 1)
    make_version=$(make --version 2>/dev/null | head -n 1)
    python_version=$(python3 --version 2>&1)
    {
        printf 'OrchLang verification evidence\n'
        printf '==============================\n\n'
        printf 'date (UTC)      %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S')"
        printf 'commit          %s%s\n' "$commit" "$dirty"
        printf 'system          %s\n' "$os"
        printf 'compiler        %s\n' "$compiler"
        printf 'make            %s\n' "$make_version"
        printf 'python          %s\n' "$python_version"
        printf 'sanitizers      %s\n\n' "$([ "$QUICK" = 1 ] && echo 'skipped (--quick)' || echo 'AddressSanitizer + UndefinedBehaviorSanitizer')"
        printf 'Steps\n\n%s\n' "$RESULTS"
        printf 'SHA-256 of what was verified\n\n'
        printf '  compiler sources (src include tests)   %s\n' "$(tree_digest src include tests)"
        printf '  example programs (examples)            %s\n' "$(tree_digest examples)"
        printf '  benchmark corpus (bench/*/*.orch)      %s\n' "$(tree_digest bench/cost bench/relational bench/security)"
        printf '  committed benchmark results            %s\n' "$(tree_digest bench/results)"
        printf '  case-study workflows                   %s\n' "$(find case_studies -name '*.orch' | sort | while IFS= read -r f; do digest "$f"; done | digest | cut -d ' ' -f 1)"
        printf '  committed case-study results           %s\n' "$(tree_digest case_studies/results)"
        printf '\nTo check this evidence, run ./verify.sh on the same commit and\n'
        printf 'compare the digests above; every step must print PASS.\n'
    } >"$OUT/EVIDENCE.txt"
}

rm -rf "$OUT"
mkdir -p "$OUT"
printf '%sOrchLang verification%s  %s%s%s\n\n' "$BOLD" "$OFF" "$DIM" "$(uname -srm)" "$OFF"

if [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1; then
    printf 'The Xcode Command Line Tools are required: xcode-select --install\n' >&2
    exit 1
fi
command -v python3 >/dev/null 2>&1 || { printf 'python3 is required.\n' >&2; exit 1; }

begin "Strict build from clean"
make clean >/dev/null 2>&1
if make -j"$JOBS" CXXFLAGS="$STRICT" orchc orchlang_tests >"$OUT/build.log" 2>&1; then
    pass "strict build: -Wall -Wextra -pedantic -Werror, 0 warnings"
else
    fail_step "strict build" "$OUT/build.log"
fi

begin "Unit tests"
if ./orchlang_tests >"$OUT/tests.log" 2>&1; then
    pass "unit tests: $(grep -E '^Passed [0-9]+/[0-9]+ tests' "$OUT/tests.log")"
else
    fail_step "unit tests" "$OUT/tests.log"
fi

begin "Example corpus"
if make -s CXXFLAGS="$STRICT" examples >"$OUT/examples.log" 2>&1; then
    pass "example corpus: $(ls examples/valid/*.orch | wc -l | tr -d ' ') valid accepted, $(ls examples/invalid/*.orch | wc -l | tr -d ' ') invalid rejected, boundary cases as expected"
else
    fail_step "example corpus" "$OUT/examples.log"
fi

begin "Sanitizers"
if [ "$QUICK" = 1 ]; then
    printf '  %sskipped (--quick)%s\n' "$DIM" "$OFF"
    RESULTS="${RESULTS}SKIP  sanitizers (--quick)
"
elif make -j"$JOBS" sanitize >"$OUT/sanitize.log" 2>&1; then
    pass "sanitizers: tests and corpus clean under AddressSanitizer and UndefinedBehaviorSanitizer"
else
    fail_step "sanitizers" "$OUT/sanitize.log"
fi
# The remaining steps time nothing, but rebuild normally so they run at full speed.
if [ "$QUICK" = 0 ]; then
    make clean >/dev/null 2>&1
    make -j"$JOBS" CXXFLAGS="$STRICT" orchc orchlang_tests >>"$OUT/build.log" 2>&1 || fail_step "rebuild after sanitizers" "$OUT/build.log"
fi

begin "Benchmark reproduction"
mkdir -p "$OUT/bench"
if ORCHLANG_RESULTS_DIR="$OUT/bench" python3 bench/evaluate.py >"$OUT/bench.log" 2>&1; then
    mismatch=
    for file in cost.json relational.json security.json; do
        cmp -s "bench/results/$file" "$OUT/bench/$file" || mismatch="$mismatch $file"
    done
    # evaluation.txt ends with a wall-clock timing, the one line that may differ.
    grep -v 'workflows certified in' bench/results/evaluation.txt >"$OUT/bench/committed.txt"
    grep -v 'workflows certified in' "$OUT/bench/evaluation.txt" >"$OUT/bench/reproduced.txt"
    cmp -s "$OUT/bench/committed.txt" "$OUT/bench/reproduced.txt" || mismatch="$mismatch evaluation.txt"
    if [ -z "$mismatch" ]; then
        pass "benchmark: 7,575 executions reproduce bench/results exactly (timing line excluded)"
    else
        diff "$OUT/bench/committed.txt" "$OUT/bench/reproduced.txt" >"$OUT/bench/diff.txt"
        fail_step "benchmark: reproduced results differ in:$mismatch" "$OUT/bench/diff.txt"
    fi
else
    fail_step "benchmark: bench/evaluate.py reported a failure" "$OUT/bench.log"
fi

begin "Demo rehearsal"
if ./demo.sh check >"$OUT/demo.log" 2>&1; then
    pass "demo: $(grep -o 'All [0-9]* steps behave as scripted' "$OUT/demo.log")"
else
    fail_step "demo rehearsal" "$OUT/demo.log"
fi

begin "Case studies"
mkdir -p "$OUT/case_studies"
if ORCHLANG_CASE_RESULTS="$OUT/case_studies" python3 case_studies/verify.py >"$OUT/case_studies.log" 2>&1; then
    if diff -r case_studies/results "$OUT/case_studies" >"$OUT/case_studies.diff" 2>&1; then
        pass "case studies: every verdict and experiment reproduces case_studies/results byte for byte"
    else
        fail_step "case studies: reproduced results differ from the committed ones" "$OUT/case_studies.diff"
    fi
else
    fail_step "case studies: an expectation failed" "$OUT/case_studies.log"
fi

finish
