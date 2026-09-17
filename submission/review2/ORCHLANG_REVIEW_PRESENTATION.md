# OrchLang Review Presentation

**Project:** OrchLang: A Statically Typed Domain Specific Language Compiler for Safe and Cost Aware LLM Workflows  
**Student:** Nambi Rajan M  
**Registration number:** 24BAI0072  
**Target duration:** 8 to 9 minutes  
**Audience:** Compiler Design Laboratory review panel

## Presenter setup

Open a terminal before beginning. Run the following command once so all demonstration commands use the project directory:

```sh
cd /Users/nambi/Documents/Codex/2026-09-16/files-mentioned-by-the-user-nambi/orchlang
```

Each `---` below represents one presentation slide. Use the **On slide** content in the Markdown deck and use the **Say** section as speaker notes. The commands are deliberately placed where the output supports the narration.

---

## Slide 1: OrchLang

**Time:** 0:00 to 0:25

### On slide

**OrchLang**  
A statically typed compiler for safe and cost-aware LLM workflows

Nambi Rajan M  
24BAI0072

### Say

“Good morning. My project is OrchLang, a small domain-specific language and compiler for describing LLM-style workflows. The main idea is to catch workflow mistakes before a model request could happen. I will show the language, the compiler stages, the checks, and the working command-line demonstration.”

---

## Slide 2: Why this problem exists

**Time:** 0:25 to 1:05

### On slide

LLM workflows often contain errors that appear late:

- a misspelled input or prompt name
- a value with the wrong type
- a prompt template that refers to a missing variable
- a secret accidentally passed to a prompt or output
- a declared model limit that exceeds the workflow budget

### Say

“Many LLM workflows are written directly as code or configuration. A missing name, a mismatched prompt variable, or an unsafe secret flow may only become visible during execution. That makes testing slower and creates avoidable risk. OrchLang moves selected checks into a compiler, where they can be reported with source locations before any external service is involved.”

---

## Slide 3: Project goal and scope

**Time:** 1:05 to 1:35

### On slide

OrchLang describes:

- typed inputs and secret declarations
- offline mock-model declarations
- prompt templates and typed prompt parameters
- model calls, token requirements, and a workflow output

Current review scope: Phase 1 front end plus Phase 2 AST, symbol table, semantic analysis, and workflow IR.

### Say

“The language remains intentionally compact so every feature maps to a compiler concept. A workflow can declare inputs, secrets, models, prompts, model calls, requirements, and one output. The completed scope focuses on the compiler front end and analysis pipeline. It does not rely on a network connection, API key, database, or paid model service.”

---

## Slide 4: Why these implementation choices

**Time:** 1:35 to 2:05

### On slide

| Choice | Reason |
| --- | --- |
| C++17 | Demonstrates low-level compiler construction and RAII ownership |
| Hand-written lexer and parser | Makes tokenization, lookahead, and recovery easy to explain in a viva |
| `std::unique_ptr` AST | Gives clear ownership without raw owning pointers |
| Structured diagnostics | Connects each error to a file, line, column, and code |
| Offline mock-model declarations | Keeps the review reproducible and safe |

### Say

“I used C++17 because it exposes the main compiler structures clearly. The lexer and parser are hand-written, so I can explain exactly how the compiler reads source and recovers from errors. The AST uses `std::unique_ptr` to keep ownership safe. Structured diagnostics make the output useful in a review. Mock-model declarations keep the example workflows realistic while the demonstration remains fully offline.”

---

## Slide 5: The OrchLang language

**Time:** 2:05 to 2:40

### On slide

```orchlang
workflow SupportTriage budget 2500 {
  input ticket: text;
  secret API_KEY;
  model fast = mock("local-small") max_tokens 600;

  prompt classify(message: text) -> text =
      "Classify the ticket: {message}";

  let category: text = call classify(ticket) using fast;
  require tokens(category) <= 600;
  output category;
}
```

### Say

“This is the central example. The workflow has a declared budget of 2500. It accepts a text ticket, declares a secret, selects an offline mock model, defines a typed prompt, and stores the call result in `category`. The `require` statement records an expected token limit, and the final output is explicit. Each line becomes a compiler object that I can inspect in the next steps.”

---

## Slide 6: Compiler architecture

**Time:** 2:40 to 3:15

### On slide

```text
OrchLang source
    -> Lexer
    -> Recursive-descent parser
    -> Owned abstract syntax tree
    -> Symbol table and semantic analysis
    -> Workflow intermediate representation
    -> Text or JSON inspection output
```

### Say

“The compiler follows a standard pipeline. The lexer produces location-aware tokens. The parser checks grammar and builds an owned AST. The symbol table records what each name means and where it was declared. Semantic analysis checks meaning across the program. A valid workflow lowers to an IR graph that shows dependencies. The following terminal commands reveal every stage.”

---

## Slide 7: Build and automated tests

**Time:** 3:15 to 3:55

### On slide

```sh
make clean && make check
```

Expected result:

```text
Passed 45/45 tests.
```

The build uses `-std=c++17 -Wall -Wextra -pedantic`.

### Say

“First I perform a clean build and run the full test command. `make check` compiles the project with strict C++17 warnings, runs 45 assertions, accepts every valid example, and confirms that each invalid example fails. The tests cover the lexer, parser, AST, symbols, semantic rules, IR lowering, cycle detection, and error recovery.”

### Live command

```sh
make clean && make check
```

---

## Slide 8: Lexical analysis

**Time:** 3:55 to 4:25

### On slide

```sh
./orchc tokens examples/valid/support_triage.orch
```

Example output:

```text
1:1  WORKFLOW  workflow
2:3  INPUT     input
4:3  MODEL     model
6:3  PROMPT    prompt
9:24 CALL      call
11:3 OUTPUT    output
```

### Say

“The lexer reads characters and produces tokens with line and column positions. The output shows that `workflow`, `input`, `model`, `prompt`, `call`, and `output` become separate tokens. The location data later lets diagnostics point at the source of a problem. The lexer also handles comments, strings, integer and decimal literals, boolean literals, and malformed strings.”

### Live command

```sh
./orchc tokens examples/valid/support_triage.orch
```

---

## Slide 9: Parsing and the abstract syntax tree

**Time:** 4:25 to 4:55

### On slide

```sh
./orchc ast examples/valid/support_triage.orch
```

Key AST output:

```text
Workflow SupportTriage budget=2500
  Input ticket : text
  Prompt classify(message:text) -> text
  Let category : text
    Call classify(ticket) using fast
  Output category
```

### Say

“The recursive-descent parser uses one-token lookahead. It creates AST nodes only after it has enough valid syntax to do so. The AST keeps the source structure rather than just printing summaries. Here, the call is nested inside the typed `let` statement. The parser also synchronizes at a semicolon, a closing brace, or the next statement keyword after a syntax error.”

### Live command

```sh
./orchc ast examples/valid/support_triage.orch
```

---

## Slide 10: Symbol table and semantic analysis

**Time:** 4:55 to 5:35

### On slide

```sh
./orchc symbols examples/valid/support_triage.orch
```

The table records:

- kind, name, type, scope, and declaration location
- mock-model provider, model name, and `max_tokens`
- prompt parameter types and prompt return type
- local call result type

### Say

“The symbol table gives names meaning. `ticket` becomes a typed input, `API_KEY` becomes a secret, `fast` becomes a model with metadata, `classify` becomes a prompt signature, and `category` becomes a local result. The prompt parameter lives in a child scope. This structure supports duplicate detection, name lookup, argument checking, and type checking.”

### Live command

```sh
./orchc symbols examples/valid/support_triage.orch
```

---

## Slide 11: Semantic errors and parser recovery

**Time:** 5:35 to 6:35

### On slide

```sh
./orchc check examples/invalid/multiple_errors.orch
./orchc check examples/invalid/syntax_errors.orch
```

Selected diagnostic codes:

| Code | Meaning |
| --- | --- |
| `E201` | Duplicate declaration |
| `E202` | Undeclared identifier |
| `E210` | Type mismatch |
| `E221` / `E223` | Wrong prompt arity or argument type |
| `E222` | Invalid prompt placeholder use |
| `E230` | Secret exposure |
| `E241` | Unknown model |
| `E260` | Declared token bound exceeds budget |
| `P001` | Syntax error |

### Say

“This is the main reason for the language. The first command reports several independent semantic errors in one run: a duplicate name, placeholder mistakes, a secret passed to a prompt, wrong argument count and type, an unknown model, a type mismatch, and multiple outputs. The second command has a missing semicolon. It reports `P001` and recovers safely instead of crashing. This behavior makes the compiler useful for debugging a workflow.”

### Live commands

```sh
./orchc check examples/invalid/multiple_errors.orch
./orchc check examples/invalid/syntax_errors.orch
```

---

## Slide 12: Workflow IR, declared budget, and dependencies

**Time:** 6:35 to 7:20

### On slide

```sh
./orchc ir examples/valid/support_triage.orch
```

```text
[5] Call category : text deps=[4, 3, 1]
    prompt=classify model=fast max_tokens=600
```

Budget rule: every selected model call contributes its declared `max_tokens` value. The compiler compares the total with the workflow budget.

### Say

“After semantic analysis succeeds, OrchLang lowers the AST into a workflow IR. The call node depends on the prompt, model, and input nodes. This graph makes data flow visible. For the budget check, the compiler adds the selected model limits. In this example the bound is 600 against a budget of 2500. This is a declared conservative bound, not a prediction of real API billing. The IR lowerer also runs a generic depth-first cycle detector before accepting the graph.”

### Live command

```sh
./orchc ir examples/valid/support_triage.orch
```

---

## Slide 13: Boundary case, evidence, and closing

**Time:** 7:20 to 8:20

### On slide

```sh
./orchc check examples/boundary/zero_budget.orch
./orchc ir-json examples/valid/two_step_workflow.orch
```

Evidence available in `review_evidence/`:

- clean-build and test output
- token, AST, symbol-table, and IR output
- lexical, syntax, semantic, and multi-error output

Current limitations: optimization, Python generation, and offline execution remain Phase 3 work.

### Say

“The zero-budget workflow succeeds because it has no model call, so its declared token bound is zero. The JSON command shows that the IR can also be consumed by a later backend. The project includes actual command output in `review_evidence`, rather than manually written screenshots or results. The completed Review 2 scope is the hand-written front end, AST, symbols, semantic analysis, and IR. Future Phase 3 work can add optimization, readable offline Python generation, and deterministic execution without changing these core compiler stages.”

### Live commands

```sh
./orchc check examples/boundary/zero_budget.orch
./orchc ir-json examples/valid/two_step_workflow.orch
```

---

## Closing sentence

“OrchLang demonstrates how compiler techniques can make an LLM workflow description more inspectable before execution: the lexer finds tokens, the parser builds structure, the symbol table resolves names, semantic analysis enforces safety and type rules, and the IR exposes dependencies for later compilation work.”

## Fast recovery plan if a live command fails

Run these commands in order:

```sh
pwd
make clean && make check
./orchc check examples/valid/support_triage.orch
```

If the source path changed, navigate to the directory containing `Makefile`, `orchc`, and `examples/` before repeating the command.
