#pragma once

// A deterministic, fully offline mock runtime.
//
// Its only purpose is to make the compiler's claim falsifiable.  The cost
// analysis asserts that no execution of a well-typed workflow consumes more
// than the certified bound; without something that executes workflows, that
// assertion could only be argued, never measured.  This runtime executes a
// workflow against a mock model whose behaviour is a pure function of a seed,
// counts the tokens actually consumed, and reports them, so a harness can check
// every run against the certificate.
//
// It contacts no network service, reads no key, and its model is not a model:
// it is a seeded generator that respects the declared max_tokens cap, which is
// exactly the contract the guaranteed half of the bound relies on.

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

namespace orchlang {

struct RunOptions {
    std::uint64_t seed{1};
    // Chance in [0,100] that one attempt inside a retry block fails and the
    // block tries again.  Models a transient failure or a rejected validation.
    unsigned retryFailurePercent{50};
};

struct CallTrace {
    std::string binding;
    std::string prompt;
    std::string model;
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
};

struct WorkflowRun {
    std::string name;
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
    std::size_t calls{0};
    std::vector<CallTrace> trace;
    std::vector<std::string> effects;

    std::size_t totalTokens() const { return inputTokens + outputTokens; }
};

struct RunResult {
    std::vector<WorkflowRun> workflows;
    DiagnosticBag diagnostics;

    bool success() const { return !diagnostics.hasErrors(); }
};

class Interpreter {
public:
    explicit Interpreter(RunOptions options) : options_(options) {}

    RunResult run(const Program& program, const SemanticResult& semantic) const;

private:
    RunOptions options_;
};

std::string printRun(const RunResult& result);

}  // namespace orchlang
