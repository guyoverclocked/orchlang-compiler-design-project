#!/usr/bin/env bash
#
# OrchLang demo pipeline.  One script, three jobs:
#
#   ./demo.sh setup    once, before the talk: check the toolchain, build from
#                      clean, run the tests, rehearse every scene, and save a
#                      plain-text transcript as a fallback
#   ./demo.sh          present: each command is shown, and runs when you press
#                      Enter, with the line that matters highlighted
#   ./demo.sh check    dress rehearsal: run every command and verify that its
#                      output still says what the presenter is going to say
#
# The scenes are defined once, in define_scenes below.  DEMO.md is the
# presenter's guide to them.
#
# Written for macOS as it ships: bash 3.2 (no associative arrays, no mapfile),
# BSD awk and grep, and the make and clang from the Xcode Command Line Tools.

cd "$(dirname "$0")" || exit 2

usage() {
    cat <<'EOF'
Usage: ./demo.sh [command] [options]

Commands
  setup            one-time preparation: toolchain, clean build, tests,
                   rehearsal, and a transcript in build/demo-transcript.txt
  (none)           present the demo interactively
  check            dress rehearsal: run every step, verify its output
  list             list the scenes

Options for presenting
  <n>              start at scene n
  --quick          the short cut (about 7 minutes)
  --scenes 2,5,9   play exactly these scenes, in this order
  --auto           no key presses; advance on a timer (for recording)
  --delay <sec>    seconds between steps with --auto (default 2)
  --no-color       plain output

Keys while presenting
  Enter, Space, Right, Down, Page Down   run the next command / next scene
  Left, Up, Page Up, p                   previous scene
  r                                      replay this scene
  s                                      skip the rest of this scene
  q                                      quit
EOF
}

# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------

IS_TTY=0
[ -t 1 ] && IS_TTY=1
KEYS_TTY=0
[ -t 0 ] && KEYS_TTY=1

USE_COLOR=$IS_TTY
[ -n "${NO_COLOR:-}" ] && USE_COLOR=0
[ "${TERM:-dumb}" = dumb ] && USE_COLOR=0

case "${LC_ALL:-}${LC_CTYPE:-}${LANG:-}" in
    *UTF-8*|*utf-8*|*UTF8*|*utf8*) UNICODE=1 ;;
    *) UNICODE=0 ;;
esac

set_glyphs() {
    if [ "$UNICODE" = 1 ]; then
        G_RULE='─'; G_ARROW='▸'; G_DOTS='…'; G_VDOTS='⋮'; G_OK='✔'; G_BAD='✘'; G_SEP='·'
    else
        G_RULE='-'; G_ARROW='>'; G_DOTS='...'; G_VDOTS=':'; G_OK='ok'; G_BAD='XX'; G_SEP='.'
    fi
}

set_colors() {
    if [ "$USE_COLOR" = 1 ]; then
        C_OFF=$'\033[0m'
        C_BOLD=$'\033[1m'
        C_DIM=$'\033[2m'
        C_RED=$'\033[31m'
        C_GRN=$'\033[32m'
        C_YEL=$'\033[33m'
        C_CYN=$'\033[36m'
        C_TITLE=$'\033[1;36m'
        C_PROMPT=$'\033[1;32m'
        C_CAP=$'\033[1;36m'
        C_KW=$'\033[1;35m'
        C_TY=$'\033[36m'
        C_STR=$'\033[32m'
        # Black on yellow reads on a projector in both light and dark themes.
        C_HL=$'\033[30;43m'
    else
        C_OFF=; C_BOLD=; C_DIM=; C_RED=; C_GRN=; C_YEL=; C_CYN=; C_TITLE=
        C_PROMPT=; C_CAP=; C_KW=; C_TY=; C_STR=; C_HL=
    fi
}

term_cols() {
    local cols=
    [ "$IS_TTY" = 1 ] && cols=$(tput cols 2>/dev/null)
    [ -n "$cols" ] || cols=80
    printf '%s' "$cols"
}

term_rows() {
    local rows=
    [ "$IS_TTY" = 1 ] && rows=$(tput lines 2>/dev/null)
    [ -n "$rows" ] || rows=24
    printf '%s' "$rows"
}

clear_screen() {
    if [ "$IS_TTY" = 1 ]; then
        printf '\033[H\033[2J'
    else
        printf '\n\n'
    fi
}

rule() {
    local width=$1 line= i=0
    while [ $i -lt "$width" ]; do
        line="$line$G_RULE"
        i=$((i + 1))
    done
    printf '%s' "$line"
}

hint() {
    [ "$MODE" = interactive ] || return 0
    printf '%s%s%s' "$C_DIM" "$1" "$C_OFF"
}

# ---------------------------------------------------------------------------
# Scene registry
# ---------------------------------------------------------------------------

SCENE_COUNT=0
STEP_COUNT=0

# scene <title> <one-line blurb> <seconds> [quick]
scene() {
    SCENE_COUNT=$((SCENE_COUNT + 1))
    SCENE_TITLE[$SCENE_COUNT]=$1
    SCENE_BLURB[$SCENE_COUNT]=$2
    SCENE_SECS[$SCENE_COUNT]=$3
    SCENE_QUICK[$SCENE_COUNT]=${4:-}
    SCENE_FIRST[$SCENE_COUNT]=$STEP_COUNT
    SCENE_STEPS[$SCENE_COUNT]=0
}

# step <command> [exit=<n>] [expect=<ERE>]... [hl=<ERE>] [say=<caption>]
#                [head=<n> | tail=<n> | show=<ERE>]
#
#   exit    the exit status the command must return (default 0)
#   expect  a pattern its output must contain; checked by ./demo.sh check
#   hl      lines matching this are highlighted when presenting
#   say     a one-line caption printed under the output
#   head/tail/show  trim long output, with a visible marker where lines were cut
step() {
    local command=$1 option index=$STEP_COUNT count
    shift
    STEP_SCENE[$index]=$SCENE_COUNT
    STEP_CMD[$index]=$command
    STEP_EXIT[$index]=0
    STEP_EXPECT[$index]=
    STEP_HL[$index]=
    STEP_SAY[$index]=
    STEP_VIEW[$index]=all
    STEP_N[$index]=0
    STEP_SHOW[$index]=
    for option in "$@"; do
        case $option in
            exit=*)   STEP_EXIT[$index]=${option#exit=} ;;
            expect=*) STEP_EXPECT[$index]="${STEP_EXPECT[$index]}${option#expect=}
" ;;
            hl=*)     STEP_HL[$index]=${option#hl=} ;;
            say=*)    STEP_SAY[$index]=${option#say=} ;;
            head=*)   STEP_VIEW[$index]=head; STEP_N[$index]=${option#head=} ;;
            tail=*)   STEP_VIEW[$index]=tail; STEP_N[$index]=${option#tail=} ;;
            show=*)   STEP_VIEW[$index]=show; STEP_SHOW[$index]=${option#show=} ;;
            *) printf 'demo.sh: unknown step option: %s\n' "$option" >&2; exit 2 ;;
        esac
    done
    count=${SCENE_STEPS[$SCENE_COUNT]}
    SCENE_STEPS[$SCENE_COUNT]=$((count + 1))
    STEP_COUNT=$((STEP_COUNT + 1))
}

# ---------------------------------------------------------------------------
# The demo.  Keep DEMO.md in step with this: it narrates these scenes in order.
# Captions stay ASCII so they print cleanly on any terminal.
# ---------------------------------------------------------------------------

define_scenes() {
    scene "Build it, test it" \
          "A compiler written from scratch in C++17. No libraries, no parser generator, no network." 30
    step 'make check' tail=2 \
         expect='Passed 95/95 tests' expect='invalid corpus rejected' \
         hl='Passed|examples:' \
         say="95 unit tests pass; every valid example is accepted and every invalid one rejected."

    scene "Meet a workflow" \
          "Take some input, put it in a prompt, send it to a model, return the answer." 60 quick
    step 'cat examples/valid/support_triage.orch' \
         expect='workflow SupportTriage' \
         say="Six kinds of declaration: input, secret, model, prompt, let...call, output."
    step './orchc check examples/valid/support_triage.orch' \
         expect='Check succeeded' expect='token bound +1016 / budget 2500' \
         hl='token bound' \
         say="Accepted, and certified to spend at most 1,016 tokens against a budget of 2,500."

    scene "How the compiler sees it" \
          "The textbook pipeline, every stage printable: lexer, parser, symbol table, IR." 90
    step './orchc tokens examples/valid/support_triage.orch' head=10 \
         expect='1:1 +WORKFLOW +workflow' \
         say="Lexer: every token carries its line and column."
    step './orchc ast examples/valid/support_triage.orch' \
         expect='Workflow SupportTriage budget=2500' expect='Call classify\(ticket\) using fast' \
         say="Parser: hand-written recursive descent into an owned AST."
    step './orchc symbols examples/valid/support_triage.orch' \
         expect='secret API_KEY : text label=secret/trusted' \
         hl='API_KEY' \
         say="Symbol table: every symbol with its type, security label and token bound."
    step './orchc ir examples/valid/support_triage.orch' \
         expect='Call category : text deps=\[4, 3, 1\]' \
         hl='\] Call ' \
         say="IR: a dependency graph. The call depends on the prompt [4], the model [3] and the input [1]."

    scene "Every error in one pass" \
          "The parser recovers at statement boundaries instead of stopping at the first fault." 30
    step './orchc check examples/invalid/multiple_errors.orch' exit=1 \
         expect='\[E201\]' expect='\[E202\]' expect='\[E210\]' expect='\[E221\]' \
         expect='\[E222\]' expect='\[E223\]' expect='\[E230\]' expect='\[E231\]' \
         expect='\[E241\]' expect='\[E261\]' expect='\[E271\]' \
         say="Fourteen independent diagnostics, each with a line, a column and a stable code."

    scene "Problem 1: the bill is bigger than the code" \
          "One call in the source can be three on the invoice." 90 quick
    step 'cat examples/valid/bounded_retry.orch' \
         expect='retry 3' hl='retry 3|call extract' \
         say="One call in the source..."
    step './orchc cost examples/valid/bounded_retry.orch' \
         expect='retry-scale +3 x 1110 +=> 3330 tokens' \
         hl='retry-scale|token bound' \
         say="...up to three on the invoice. A retry multiplies its body: 3 x 1,110 = 3,330."
    step './orchc run examples/valid/bounded_retry.orch --seed 4' \
         expect='calls +3' expect='actual tokens +2554' \
         hl='actual tokens' \
         say="An offline run: three attempts, 2,554 tokens. Summing the calls would have promised 1,110."
    step './orchc cost examples/valid/branching_cost.orch' \
         expect='branch-max +max\(then=432, else=1211\)' \
         hl='branch-max' \
         say="Only one arm of a branch runs, so a branch costs its more expensive arm, not the sum."
    step './orchc check examples/invalid/retry_budget.orch' exit=1 \
         expect='\[E260\] certified token bound 2418' \
         say="Over budget is a compile-time error, not a surprise at the end of the month."

    scene "Problem 2: a credential must never reach a model" \
          "A secret may not reach a prompt, an output, or a tool unless you say why." 45
    step './orchc check bench/security/unsafe/SecretToPrompt.orch' exit=1 \
         expect='\[E230\]' expect='\[E231\]' \
         say="API_KEY is declared secret: it cannot go into a prompt (E230) or come back out (E231)."
    step 'diff bench/security/unsafe/SecretToPrompt.orch bench/security/safe/SecretToPromptDeclassified.orch' exit=1 \
         expect='declassify\(API_KEY\) as fingerprint' \
         say="The way out is one explicit line, and it has to carry a written reason."
    step './orchc check bench/security/safe/SecretToPromptDeclassified.orch' \
         expect='Check succeeded' expect='1 declassify' \
         hl='escape hatches' \
         say="Accepted. The reason is copied into the certificate, so a reviewer can find every one."

    scene "Problem 3: prompt injection is a type error" \
          "Text you did not write must not decide what your tools do." 60 quick
    step 'cat bench/security/unsafe/InjectionTransitive.orch' \
         expect='emit publish\(second\)' \
         hl='untrusted|emit publish' \
         say="page is untrusted. It passes through two model calls, then drives a tool."
    step './orchc check bench/security/unsafe/InjectionTransitive.orch' exit=1 \
         expect='\[E233\]' \
         say="Still untrusted: a model's answer is only as trustworthy as what reached its prompt."
    step 'diff bench/security/unsafe/InjectionTransitive.orch bench/security/safe/InjectionTransitiveEndorsed.orch' exit=1 \
         expect='endorse\(second\) as vetted' \
         say="To let it drive a tool, someone has to vouch for it, in writing."
    step './orchc check bench/security/safe/InjectionTransitiveEndorsed.orch' \
         expect='Check succeeded' expect='1 endorse' \
         hl='escape hatches' \
         say="Accepted, with the endorsement on record."

    scene "Implicit flow" \
          "The secret is never sent anywhere. It only decides whether something happens." 30
    step 'cat examples/invalid/implicit_flow.orch' \
         expect='if ALERT_ENABLED' \
         hl='if ALERT_ENABLED|emit notify' \
         say="No secret value is passed anywhere. The secret only decides whether the tool fires..."
    step './orchc check examples/invalid/implicit_flow.orch' exit=1 \
         expect='\[E234\]' \
         say="...and that alone tells an observer one bit of it. The program-counter label catches it."

    scene "The fourth problem: the bill leaks the secret" \
          "No value goes anywhere it should not, and the invoice still gives the secret away." 75 quick
    step 'cat examples/invalid/cost_channel.orch' \
         expect='if ALERT' \
         hl='if ALERT|using large|using small' \
         say="No value crosses a boundary and no tool is called. Every taint tracker accepts this."
    step './orchc check examples/invalid/cost_channel.orch' exit=1 \
         expect='\[E236\].*large\(in=5 \+ [|]src[|]\).*small\(in=5 \+ [|]src[|]\)' \
         say="OrchLang rejects it: the two arms bill differently, so the bill reveals the secret."
    step './orchc run examples/invalid/cost_channel.orch --seed 3 --pin src=20 --pin ALERT=false' \
         expect='actual tokens +45 ' expect='small +calls 1' \
         hl='actual tokens' \
         say="Run it anyway. Secret off: 45 tokens..."
    step './orchc run examples/invalid/cost_channel.orch --seed 3 --pin src=20 --pin ALERT=true' \
         expect='actual tokens +587 ' expect='large +calls 1' \
         hl='actual tokens' \
         say="...secret on: 587 tokens. Same input, same seed. The invoice is the leak."

    scene "I got this wrong the first time" \
          "Accept when both arms have the same maximum cost. Obvious, and wrong." 75 quick
    step 'cat examples/invalid/equal_bounds.orch' \
         expect='call p\(y\)' \
         hl='call p\(' \
         say="Same model, same prompt, both arguments capped at 100: both arms have the same maximum."
    step './orchc check examples/invalid/equal_bounds.orch' exit=1 \
         expect='\[E236\].*m\(in=1 \+ [|]x[|]\).*m\(in=1 \+ [|]y[|]\)' \
         say="My first rule accepted this. But a maximum is a ceiling, not a value: |x| is not |y|."
    step './orchc run examples/invalid/equal_bounds.orch --seed 5 --pin x=14 --pin y=52 --pin s=0' \
         expect='m +calls 1 +in 15 +out 6' \
         hl='calls 1' \
         say="Secret s = 0: the bill says 15 input tokens..."
    step './orchc run examples/invalid/equal_bounds.orch --seed 5 --pin x=14 --pin y=52 --pin s=1' \
         expect='m +calls 1 +in 53 +out 6' \
         hl='calls 1' \
         say="...s = 1: 53. Equal ceilings, different bills. An external audit measured it: 225 of 425 runs."

    scene "The fix: compare structure, not numbers" \
          "Which model, in what order, and a symbolic input size that must match in both arms." 45
    step 'cat examples/valid/balanced_signature.orch' \
         expect='let b: text = call p\(x\)' \
         hl='call p\(' \
         say="The only edit: both arms now read the same variable."
    step './orchc check examples/valid/balanced_signature.orch' \
         expect='Check succeeded' \
         say="Accepted: the two arms have identical billing signatures."
    step './orchc run examples/valid/balanced_signature.orch --seed 5 --pin x=40 --pin s=0' \
         expect='m +calls 1 +in 41 +out 5' \
         hl='calls 1' \
         say="Secret s = 0: 41 in, 5 out..."
    step './orchc run examples/valid/balanced_signature.orch --seed 5 --pin x=40 --pin s=1' \
         expect='m +calls 1 +in 41 +out 5' \
         hl='calls 1' \
         say="...s = 1: identical. Only the variable name changed, and names are not billed."

    scene "An auditable certificate" \
          "Everything the compiler concluded, as JSON a reviewer or a CI job can read." 45
    step './orchc certify examples/valid/untrusted_endorsed.orch' \
         show='"(bound|chars_per_token|justification|tool)":|"name": "(web_page|digest_text|vetted)"' \
         expect='"justification": "passed the offline schema and length validator"' \
         expect='"name": "vetted".*"integrity": "trusted"' \
         hl='justification' \
         say="web_page is untrusted, so digest_text is too; vetted is trusted, and the reason is recorded."

    scene "Does it hold up?" \
          "4,600 offline executions against the certified bound, and 2,975 paired secret swaps." 45 quick
    step 'cat bench/results/evaluation.txt' \
         show='^  [a-z][a-z -]*: *([0-9]|median)' \
         expect='certified total exceeded +: 0 of 4600' \
         expect='flat per-call sum exceeded +: 636 of 4600' \
         expect='0 showed a different bill' \
         hl='total exceeded|flat per-call|0 showed' \
         say="Never exceeded in 4,600 runs; the naive sum was exceeded 636 times. Rerun it: make bench."
}

# ---------------------------------------------------------------------------
# Running and rendering one step
# ---------------------------------------------------------------------------

OUT=$(mktemp "${TMPDIR:-/tmp}/orchlang-demo.XXXXXX") || exit 2
cleanup() { rm -f "$OUT"; }
trap cleanup EXIT
# Ctrl-C can land while a key read has echo switched off; give it back.
interrupted() {
    [ "$KEYS_TTY" = 1 ] && stty echo 2>/dev/null
    printf '%s\n' "$C_OFF"
    exit 130
}
trap interrupted INT TERM

# Every command in the demo writes to exactly one of stdout or stderr, so
# capturing both into one file cannot reorder its lines.
exec_step() {
    ( eval "${STEP_CMD[$1]}" ) >"$OUT" 2>&1
    LAST_STATUS=$?
}

# Colours one captured output.  Source files get light syntax colouring, diffs
# get red and green, diagnostics are red, and the step's highlight pattern wins
# over everything.  head/tail/show trim with a visible marker.
read -r -d '' RENDER_AWK <<'AWK'
BEGIN {
    kind = ENVIRON["R_KIND"]; view = ENVIRON["R_VIEW"]; n = ENVIRON["R_N"] + 0
    showre = ENVIRON["R_SHOW"]; hl = ENVIRON["R_HL"]; total = ENVIRON["R_TOTAL"] + 0
    HLON = ENVIRON["C_HL"]; OFF = ENVIRON["C_OFF"]; RED = ENVIRON["C_RED"]
    GRN = ENVIRON["C_GRN"]; YEL = ENVIRON["C_YEL"]; DIM = ENVIRON["C_DIM"]
    KWC = ENVIRON["C_KW"]; TYC = ENVIRON["C_TY"]; STRC = ENVIRON["C_STR"]
    DOTS = ENVIRON["G_DOTS"]; VDOTS = ENVIRON["G_VDOTS"]
    split("workflow budget input secret model mock max_tokens prompt let call using require tokens output untrusted tool emit if else retry declassify endorse as because cost_per_token", w, " ")
    for (i in w) KEYWORD[w[i]] = 1
    split("text integer decimal boolean json true false", w, " ")
    for (i in w) TYPE[w[i]] = 1
    gap = 0; shown = 0
}
function source(line,    out, i, j, len, c, word) {
    out = ""; i = 1; len = length(line)
    while (i <= len) {
        c = substr(line, i, 1)
        if (c == "/" && substr(line, i + 1, 1) == "/") { out = out DIM substr(line, i) OFF; break }
        if (c == "\"") {
            j = i + 1
            while (j <= len && substr(line, j, 1) != "\"") j++
            out = out STRC substr(line, i, j - i + 1) OFF; i = j + 1; continue
        }
        if (c ~ /[A-Za-z_]/) {
            j = i
            while (j <= len && substr(line, j, 1) ~ /[A-Za-z0-9_]/) j++
            word = substr(line, i, j - i)
            if (word in KEYWORD) out = out KWC word OFF
            else if (word in TYPE) out = out TYC word OFF
            else out = out word
            i = j; continue
        }
        out = out c; i++
    }
    return out
}
function emit(line) {
    if (hl != "" && line ~ hl) { print HLON line OFF; return }
    if (kind == "orch") { print source(line); return }
    if (kind == "diff") {
        if (line ~ /^</) print RED line OFF
        else if (line ~ /^>/) print GRN line OFF
        else print DIM line OFF
        return
    }
    if (line ~ /error \[E[0-9]+\]/) print RED line OFF
    else if (line ~ /warning \[W[0-9]+\]/) print YEL line OFF
    else if (line ~ /^Check succeeded/) print GRN line OFF
    else print line
}
view == "head" {
    if (FNR <= n) emit($0)
    else if (FNR == n + 1) print DIM "  " DOTS " " (total - n) " more lines" OFF
    next
}
view == "tail" {
    if (FNR == 1 && total > n) print DIM "  " DOTS " " (total - n) " earlier lines" OFF
    if (FNR > total - n) emit($0)
    next
}
view == "show" {
    if ($0 ~ showre) { if (gap) print DIM "  " VDOTS OFF; gap = 0; emit($0); shown++ }
    else gap = 1
    next
}
{ emit($0) }
END {
    if (view == "show") {
        if (gap) print DIM "  " VDOTS OFF
        print DIM "  (" shown " of " total " lines shown)" OFF
    }
}
AWK

render() {
    local index=$1 kind=plain total
    case ${STEP_CMD[$index]} in
        'cat '*.orch) kind=orch ;;
        'diff '*) kind=diff ;;
    esac
    total=$(wc -l <"$OUT")
    total=$((total + 0))
    R_KIND=$kind R_VIEW=${STEP_VIEW[$index]} R_N=${STEP_N[$index]} \
    R_SHOW=${STEP_SHOW[$index]} R_HL=${STEP_HL[$index]} R_TOTAL=$total \
    C_HL=$C_HL C_OFF=$C_OFF C_RED=$C_RED C_GRN=$C_GRN C_YEL=$C_YEL C_DIM=$C_DIM \
    C_KW=$C_KW C_TY=$C_TY C_STR=$C_STR G_DOTS=$G_DOTS G_VDOTS=$G_VDOTS \
        awk "$RENDER_AWK" "$OUT"
}

# orchc's exit status is part of its interface (0 accepted, 1 rejected), so
# show it; for other commands, only speak up if something unexpected happened.
status_line() {
    local index=$1 note=
    case ${STEP_CMD[$index]} in
        './orchc check '*)
            [ "$LAST_STATUS" = 0 ] && note=' (accepted)'
            [ "$LAST_STATUS" = 1 ] && note=' (rejected)'
            printf '%s[exit %s%s]%s\n' "$C_DIM" "$LAST_STATUS" "$note" "$C_OFF" ;;
        './orchc '*)
            printf '%s[exit %s]%s\n' "$C_DIM" "$LAST_STATUS" "$C_OFF" ;;
    esac
    if [ "$LAST_STATUS" != "${STEP_EXIT[$index]}" ]; then
        printf '%s(!) exit status %s, but the script expected %s. Run ./demo.sh check.%s\n' \
            "$C_YEL" "$LAST_STATUS" "${STEP_EXIT[$index]}" "$C_OFF"
    fi
}

caption() {
    [ -n "${STEP_SAY[$1]}" ] || return 0
    printf '%s %s %s%s\n' "$C_CAP" "$G_ARROW" "${STEP_SAY[$1]}" "$C_OFF"
}

show_command() {
    printf '%s$%s %s%s%s' "$C_PROMPT" "$C_OFF" "$C_BOLD" "$1" "$C_OFF"
}

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

# Sets KEY_ACTION to next, prev, replay, skip or quit.  Presentation clickers
# send arrow keys or Page Up/Down, so those work too.
wait_key() {
    local key c1 c2 c3
    KEY_ACTION=next
    if [ "$MODE" = auto ]; then
        [ "$DELAY" = 0 ] || sleep "$DELAY"
        return 0
    fi
    while :; do
        IFS= read -rsn1 key || { KEY_ACTION=quit; return 0; }
        case $key in
            ''|' '|n|j) KEY_ACTION=next; return 0 ;;
            p|k)        KEY_ACTION=prev; return 0 ;;
            r)          KEY_ACTION=replay; return 0 ;;
            s)          KEY_ACTION=skip; return 0 ;;
            q|Q)        KEY_ACTION=quit; return 0 ;;
            $'\033')
                c1=; c2=; c3=
                IFS= read -rsn1 -t 1 c1
                IFS= read -rsn1 -t 1 c2
                case "$c1$c2" in
                    '[C'|'[B'|OC|OB) KEY_ACTION=next; return 0 ;;
                    '[D'|'[A'|OD|OA) KEY_ACTION=prev; return 0 ;;
                    '[6') IFS= read -rsn1 -t 1 c3; KEY_ACTION=next; return 0 ;;
                    '[5') IFS= read -rsn1 -t 1 c3; KEY_ACTION=prev; return 0 ;;
                esac ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Presenting
# ---------------------------------------------------------------------------

plan_minutes() {
    local p=0 secs=0 s
    while [ $p -lt ${#PLAN[@]} ]; do
        s=${PLAN[$p]}
        secs=$((secs + ${SCENE_SECS[$s]}))
        p=$((p + 1))
    done
    printf '%s' $(((secs + 30) / 60))
}

title_card() {
    local cols rows
    clear_screen
    printf '\n'
    printf '   %sOrchLang%s\n\n' "$C_TITLE" "$C_OFF"
    printf '   A small language for LLM workflows, and a compiler that checks them\n'
    printf '   before they run: what they can cost, where secrets can go, what\n'
    printf '   untrusted text can trigger, and whether the bill itself leaks a secret.\n\n'
    printf '   %sNambi Rajan M %s 24BAI0072 %s Compiler Design Laboratory%s\n\n' \
        "$C_DIM" "$G_SEP" "$G_SEP" "$C_OFF"
    printf '   %s%d scenes %s about %s minutes %s fully offline, no API key%s\n\n' \
        "$C_DIM" "${#PLAN[@]}" "$G_SEP" "$(plan_minutes)" "$G_SEP" "$C_OFF"
    if [ "$MODE" = interactive ]; then
        cols=$(term_cols); rows=$(term_rows)
        if [ "$cols" -lt 100 ] || [ "$rows" -lt 30 ]; then
            printf '   %sThis window is %sx%s. For an audience, aim for at least 100x30:%s\n' \
                "$C_YEL" "$cols" "$rows" "$C_OFF"
            printf '   %sfull screen with Ctrl+Cmd+F, then Cmd+Plus / Cmd+Minus to taste.%s\n\n' \
                "$C_YEL" "$C_OFF"
        fi
    fi
    hint "   Enter to begin $G_SEP arrows or a clicker to move $G_SEP q to quit"
}

scene_header() {
    local s=$1 position=$2 of=$3 width
    width=$(term_cols)
    [ "$width" -gt 100 ] && width=100
    printf '%s%s%s\n' "$C_DIM" "$(rule "$width")" "$C_OFF"
    printf '%s %s%s  %s%d/%d%s\n' "$C_TITLE" "${SCENE_TITLE[$s]}" "$C_OFF" "$C_DIM" "$position" "$of" "$C_OFF"
    printf '%s %s%s\n' "$C_DIM" "${SCENE_BLURB[$s]}" "$C_OFF"
    printf '%s%s%s\n\n' "$C_DIM" "$(rule "$width")" "$C_OFF"
}

# Plays one scene and sets SCENE_ACTION to next, prev, replay or quit.
play_scene() {
    local s=$1 index last
    index=${SCENE_FIRST[$s]}
    last=$((index + ${SCENE_STEPS[$s]}))
    clear_screen
    scene_header "$s" "$2" "$3"
    while [ "$index" -lt "$last" ]; do
        show_command "${STEP_CMD[$index]}"
        wait_key
        printf '\n'
        case $KEY_ACTION in
            next) ;;
            skip) SCENE_ACTION=next; return 0 ;;
            *)    SCENE_ACTION=$KEY_ACTION; return 0 ;;
        esac
        exec_step "$index"
        render "$index"
        status_line "$index"
        caption "$index"
        printf '\n'
        index=$((index + 1))
    done
    hint "Enter: next scene $G_SEP r: replay $G_SEP p: previous $G_SEP q: quit"
    wait_key
    [ "$MODE" = interactive ] && printf '\n'
    case $KEY_ACTION in
        skip) SCENE_ACTION=next ;;
        *)    SCENE_ACTION=$KEY_ACTION ;;
    esac
}

closing_card() {
    clear_screen
    printf '\n   %sOrchLang checks, before anything runs:%s\n\n' "$C_TITLE" "$C_OFF"
    printf '     %scost%s        a certified token bound: retries multiply, branches take the max\n' "$C_BOLD" "$C_OFF"
    printf '     %ssecrets%s     credentials never reach a prompt, an output, or a tool\n' "$C_BOLD" "$C_OFF"
    printf '     %sinjection%s   untrusted text cannot drive a tool without a written endorsement\n' "$C_BOLD" "$C_OFF"
    printf '     %sthe bill%s    a secret cannot change what you are charged\n\n' "$C_BOLD" "$C_OFF"
    printf '   %sOffline %s no API key %s no dependencies %s C++17 from scratch%s\n\n' \
        "$C_DIM" "$G_SEP" "$G_SEP" "$G_SEP" "$C_OFF"
    printf '   Thank you. Questions?\n\n'
}

present() {
    local p=0
    title_card
    wait_key
    [ "$MODE" = interactive ] && printf '\n'
    [ "$KEY_ACTION" = quit ] && return 0
    while [ $p -lt ${#PLAN[@]} ]; do
        play_scene "${PLAN[$p]}" $((p + 1)) ${#PLAN[@]}
        case $SCENE_ACTION in
            next)   p=$((p + 1)) ;;
            prev)   [ $p -gt 0 ] && p=$((p - 1)) ;;
            replay) ;;
            quit)   printf '\n'; return 0 ;;
        esac
    done
    closing_card
}

# ---------------------------------------------------------------------------
# Rehearsal
# ---------------------------------------------------------------------------

# Runs every step in the plan and checks its exit status and expected output.
# Sets REHEARSAL_PASSED and REHEARSAL_FAILED; returns nonzero on any failure.
rehearse() {
    local quiet=${1:-} p=0 s index last number pattern why
    REHEARSAL_PASSED=0
    REHEARSAL_FAILED=0
    while [ $p -lt ${#PLAN[@]} ]; do
        s=${PLAN[$p]}
        index=${SCENE_FIRST[$s]}
        last=$((index + ${SCENE_STEPS[$s]}))
        number=1
        [ -z "$quiet" ] && printf '%s%2d  %s%s\n' "$C_BOLD" "$s" "${SCENE_TITLE[$s]}" "$C_OFF"
        while [ "$index" -lt "$last" ]; do
            exec_step "$index"
            why=
            if [ "$LAST_STATUS" != "${STEP_EXIT[$index]}" ]; then
                why="exit status $LAST_STATUS, expected ${STEP_EXIT[$index]}"
            fi
            while IFS= read -r pattern; do
                [ -n "$pattern" ] || continue
                grep -Eq -- "$pattern" "$OUT" || why="${why:+$why; }output lacks /$pattern/"
            done <<EOF
${STEP_EXPECT[$index]}
EOF
            if [ -z "$why" ]; then
                REHEARSAL_PASSED=$((REHEARSAL_PASSED + 1))
                [ -z "$quiet" ] && printf '    %s%s%s %-5s %s\n' "$C_GRN" "$G_OK" "$C_OFF" "$s.$number" "${STEP_CMD[$index]}"
            else
                REHEARSAL_FAILED=$((REHEARSAL_FAILED + 1))
                printf '    %s%s %-5s %s%s\n' "$C_RED" "$G_BAD" "$s.$number" "${STEP_CMD[$index]}" "$C_OFF"
                printf '          %s\n' "$why"
                sed -n '1,12s/^/          | /p' "$OUT"
            fi
            index=$((index + 1))
            number=$((number + 1))
        done
        p=$((p + 1))
    done
    [ "$REHEARSAL_FAILED" = 0 ]
}

# ---------------------------------------------------------------------------
# Toolchain and build
# ---------------------------------------------------------------------------

JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)

ok_line()   { printf '  %s%s%s %-26s %s\n' "$C_GRN" "$G_OK" "$C_OFF" "$1" "$2"; }
bad_line()  { printf '  %s%s %-26s %s%s\n' "$C_RED" "$G_BAD" "$1" "$2" "$C_OFF"; }
note_line() { printf '  %s-%s %-26s %s\n' "$C_DIM" "$C_OFF" "$1" "$2"; }

# On a Mac, make and c++ are stubs until the Command Line Tools are installed,
# and calling one pops up an installer.  Check first and explain instead.
need_toolchain() {
    if [ "$(uname -s)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1; then
        bad_line "Xcode Command Line Tools" "not installed"
        cat <<'EOF'

    macOS needs Apple's free command-line developer tools (clang and make).
    A dialog should open now: click "Install". It takes a few minutes and
    does not need the full Xcode app. When it finishes, run:

        ./demo.sh setup

EOF
        xcode-select --install >/dev/null 2>&1
        return 1
    fi
    if ! command -v make >/dev/null 2>&1; then
        bad_line "make" "not found"
        return 1
    fi
    if ! command -v "${CXX:-c++}" >/dev/null 2>&1; then
        bad_line "C++ compiler" "${CXX:-c++} not found"
        return 1
    fi
    return 0
}

# Builds orchc and the test binary if they are missing or stale.
ensure_built() {
    need_toolchain || exit 1
    if [ -x ./orchc ] && [ -x ./orchlang_tests ] && make -q orchc orchlang_tests >/dev/null 2>&1; then
        return 0
    fi
    printf '%sBuilding the compiler...%s\n' "$C_DIM" "$C_OFF"
    mkdir -p build
    if ! make -j"$JOBS" orchc orchlang_tests >build/demo-build.log 2>&1; then
        tail -n 20 build/demo-build.log
        printf '\n%sThe build failed; the full log is build/demo-build.log. Try ./demo.sh setup.%s\n' "$C_RED" "$C_OFF"
        exit 1
    fi
}

setup() {
    local started os version arch cxx_version make_version warnings tests log
    printf '\n%sOrchLang demo setup%s\n\n' "$C_TITLE" "$C_OFF"

    os=$(uname -s)
    arch=$(uname -m)
    if [ "$os" = Darwin ]; then
        version=$(sw_vers -productVersion 2>/dev/null)
        ok_line "macOS" "$version ($arch)"
    else
        ok_line "System" "$os ($arch)"
    fi

    need_toolchain || return 1
    if [ "$os" = Darwin ]; then
        ok_line "Command Line Tools" "$(xcode-select -p)"
    fi
    cxx_version=$("${CXX:-c++}" --version 2>/dev/null | grep -v -i '^configured with' | head -n 1)
    ok_line "C++ compiler" "${cxx_version:-${CXX:-c++}}"
    make_version=$(make --version 2>/dev/null | head -n 1)
    ok_line "make" "$make_version"
    if command -v python3 >/dev/null 2>&1; then
        ok_line "python3 (optional)" "$(python3 --version 2>&1), for make bench"
    else
        note_line "python3 (optional)" "not found; only needed to rerun the benchmark"
    fi

    printf '\n'
    make clean >/dev/null 2>&1
    mkdir -p build
    log=build/demo-setup.log
    started=$SECONDS
    if ! make -j"$JOBS" orchc orchlang_tests >"$log" 2>&1; then
        bad_line "Build" "failed; last lines of $log:"
        tail -n 25 "$log"
        return 1
    fi
    warnings=$(grep -c 'warning:' "$log")
    ok_line "Clean build" "orchc and tests, $warnings warnings, $((SECONDS - started)) s"

    if ! ./orchlang_tests >>"$log" 2>&1; then
        bad_line "Unit tests" "failed; see $log"
        grep -v '^PASS' "$log" | tail -n 15
        return 1
    fi
    tests=$(grep -E '^Passed [0-9]+/[0-9]+ tests' "$log" | tail -n 1)
    ok_line "Unit tests" "$tests"

    if ! make -s examples >>"$log" 2>&1; then
        bad_line "Example corpus" "failed; see $log"
        tail -n 5 "$log"
        return 1
    fi
    ok_line "Example corpus" "valid accepted, invalid rejected, certificates emitted"

    if rehearse quiet; then
        ok_line "Dress rehearsal" "$REHEARSAL_PASSED/$REHEARSAL_PASSED demo steps behave as scripted"
    else
        bad_line "Dress rehearsal" "$REHEARSAL_FAILED step(s) did not behave as scripted (above)"
        return 1
    fi

    ./demo.sh --auto --no-color >build/demo-transcript.txt 2>&1
    ok_line "Fallback transcript" "build/demo-transcript.txt"

    printf '\n%sReady.%s Present with:  %s./demo.sh%s   (or ./demo.sh --quick for the short cut)\n' \
        "$C_GRN" "$C_OFF" "$C_BOLD" "$C_OFF"
    printf '%sThe presenter guide is DEMO.md.%s\n\n' "$C_DIM" "$C_OFF"
}

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

list_scenes() {
    local s=1 quick
    printf '%s  #  scene                                              steps  time  quick%s\n' "$C_BOLD" "$C_OFF"
    while [ $s -le $SCENE_COUNT ]; do
        quick=
        [ -n "${SCENE_QUICK[$s]}" ] && quick=yes
        printf ' %2d  %-50s %5d  %3ds  %s\n' "$s" "${SCENE_TITLE[$s]}" "${SCENE_STEPS[$s]}" "${SCENE_SECS[$s]}" "$quick"
        s=$((s + 1))
    done
}

build_plan() {
    local s item
    PLAN=()
    case $PLAN_SPEC in
        all)
            s=${START:-1}
            if [ "$s" -lt 1 ] || [ "$s" -gt "$SCENE_COUNT" ]; then
                printf 'demo.sh: there is no scene %s (1-%d)\n' "$s" "$SCENE_COUNT" >&2
                exit 2
            fi
            while [ "$s" -le "$SCENE_COUNT" ]; do PLAN[${#PLAN[@]}]=$s; s=$((s + 1)); done ;;
        quick)
            s=1
            while [ $s -le $SCENE_COUNT ]; do
                [ -n "${SCENE_QUICK[$s]}" ] && PLAN[${#PLAN[@]}]=$s
                s=$((s + 1))
            done ;;
        *)
            for item in $(printf '%s' "$PLAN_SPEC" | tr ',' ' '); do
                case $item in
                    *[!0-9]*|'') printf 'demo.sh: bad scene number: %s\n' "$item" >&2; exit 2 ;;
                esac
                if [ "$item" -lt 1 ] || [ "$item" -gt "$SCENE_COUNT" ]; then
                    printf 'demo.sh: there is no scene %s (1-%d)\n' "$item" "$SCENE_COUNT" >&2
                    exit 2
                fi
                PLAN[${#PLAN[@]}]=$item
            done ;;
    esac
}

COMMAND=present
PLAN_SPEC=all
START=
MODE=interactive
DELAY=

while [ $# -gt 0 ]; do
    case $1 in
        setup)            COMMAND=setup ;;
        check|rehearse)   COMMAND=check ;;
        list|--list|-l)   COMMAND=list ;;
        help|-h|--help)   usage; exit 0 ;;
        --quick|-q)       PLAN_SPEC=quick ;;
        --scenes)         [ $# -ge 2 ] || { usage >&2; exit 2; }; PLAN_SPEC=$2; shift ;;
        --scenes=*)       PLAN_SPEC=${1#--scenes=} ;;
        --auto)           MODE=auto ;;
        --delay)          [ $# -ge 2 ] || { usage >&2; exit 2; }; DELAY=$2; shift ;;
        --delay=*)        DELAY=${1#--delay=} ;;
        --no-color)       USE_COLOR=0 ;;
        [0-9]|[0-9][0-9]) START=$1 ;;
        *) printf 'demo.sh: unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

# Without a keyboard and a screen there is nobody to press Enter.
if [ "$KEYS_TTY" = 0 ] || [ "$IS_TTY" = 0 ]; then
    MODE=auto
fi
if [ -z "$DELAY" ]; then
    if [ "$IS_TTY" = 1 ]; then DELAY=2; else DELAY=0; fi
fi

set_glyphs
set_colors
define_scenes
build_plan

case $COMMAND in
    list)
        list_scenes ;;
    setup)
        setup ;;
    check)
        ensure_built
        printf '\n%sDress rehearsal%s %severy demo command, checked against the script%s\n\n' \
            "$C_TITLE" "$C_OFF" "$C_DIM" "$C_OFF"
        if rehearse; then
            printf '\n%s%s All %d steps behave as scripted.%s\n' "$C_GRN" "$G_OK" "$REHEARSAL_PASSED" "$C_OFF"
        else
            printf '\n%s%s %d of %d steps did not behave as scripted.%s\n' "$C_RED" "$G_BAD" \
                "$REHEARSAL_FAILED" $((REHEARSAL_PASSED + REHEARSAL_FAILED)) "$C_OFF"
            exit 1
        fi ;;
    present)
        ensure_built
        present ;;
esac
