# OrchLang Review Demonstration Script

This rehearsal is designed for approximately six minutes and does not need internet access.

## 0:00 to 0:35 Introduce the problem

Say: “OrchLang is a small statically typed language for LLM workflow descriptions. The compiler checks names, prompt templates, secret flow, model selection, and declared token limits before any request could execute. Today I will show the full Review 2 compiler path from tokens to IR.”

## 0:35 to 1:15 Build and test

```sh
cd /Users/nambi/Documents/Codex/2026-09-16/files-mentioned-by-the-user-nambi/orchlang
make clean && make check
```

Expected result: the C++17 build completes with strict warnings enabled, `Passed 45/45 tests.` is printed, valid examples succeed, and each invalid example emits diagnostics while being confirmed as invalid by the Makefile.

## 1:15 to 1:45 Show the language as tokens

```sh
./orchc tokens examples/valid/support_triage.orch
```

Expected result: location-aware tokens such as `WORKFLOW`, `IDENTIFIER`, `BUDGET`, `PROMPT`, `CALL`, and `OUTPUT` are printed. Point out that `ticket`, `fast`, and `category` retain their original locations.

## 1:45 to 2:25 Show the AST

```sh
./orchc ast examples/valid/support_triage.orch
```

Expected result: a tree beginning with `Workflow SupportTriage budget=2500`, then typed input, secret, model, prompt, let/call, requirement, and output nodes. State that AST ownership uses `std::unique_ptr`.

## 2:25 to 3:05 Show the symbol table

```sh
./orchc symbols examples/valid/support_triage.orch
```

Expected result: the workflow scope includes input, secret, model, prompt, and local-result symbols. The prompt child scope shows `message : text`. Point out the model's provider, mock name, maximum tokens, and declaration locations.

## 3:05 to 4:00 Show semantic diagnostics

```sh
./orchc check examples/invalid/multiple_errors.orch
```

Expected result: a non-zero status and several independent diagnostics, including duplicate name `E201`, template errors `E222`, secret exposure `E230`, call arity/type errors `E221`/`E223`, unknown model `E241`, and multiple output `E271`. Explain that the compiler deliberately continues when it can safely find another independent fault.

## 4:00 to 4:35 Show syntax recovery

```sh
./orchc check examples/invalid/syntax_errors.orch
```

Expected result: a non-zero status with `P001` identifying the missing semicolon. Say that parser recovery synchronizes at a statement boundary rather than crashing.

## 4:35 to 5:25 Show the workflow IR

```sh
./orchc ir examples/valid/support_triage.orch
```

Expected result: numbered input, secret, model, prompt, call, requirement, and output nodes. The call node lists dependencies on the prompt, model, and input; it also prints `max_tokens=600`. Explain that the lowerer runs a defensive cycle detector before accepting IR.

## 5:25 to 6:00 Summarize the boundary and remaining scope

```sh
./orchc check examples/boundary/zero_budget.orch
./orchc ir-json examples/valid/two_step_workflow.orch
```

Expected result: the zero-budget workflow succeeds because it contains no model call; the JSON view shows the two-step workflow's IR. Close with: “The completed Review 2 scope is the front end, AST, symbols, semantics, and IR. Phase 3 work is deliberately isolated and not claimed as complete: optimization, offline Python generation, and mock execution.”
