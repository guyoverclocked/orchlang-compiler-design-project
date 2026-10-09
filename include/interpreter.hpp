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
#include "token_cost.hpp"

#include <cstdint>
#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace orchlang {

struct RunOptions {
    std::uint64_t seed{1};
    // Chance in [0,100] that one attempt inside a retry block fails and the
    // block tries again.  Models a transient failure or a rejected validation.
    unsigned retryFailurePercent{50};
    // For offline research counterexamples only. This bypasses budget and
    // relational rejection but never bypasses lexical, syntax, or semantic
    // type/security checks.
    bool auditUnsafe{false};
    // Optional stronger offline oracle: output draws also depend on the exact
    // abstract request content. The default remains ordinal-only for existing
    // reproducibility and benchmark compatibility.
    bool requestSensitiveOracle{false};

    // Pins the token length of named inputs and secrets instead of sampling
    // them.  This is what makes the relational claim testable: run the same
    // workflow twice under one seed, change only a secret's pinned length, and
    // compare the bills.  Without it, every difference could be blamed on the
    // sampler.
    std::map<std::string, std::size_t> pinnedLengths;
    // Pins the truth value of named boolean inputs and secrets.
    std::map<std::string, bool> pinnedFlags;
};

// Tokens billed to one model, which is what an itemised provider bill shows.
// Totals alone are not the right observation: two runs can agree on total
// tokens while charging different models at different prices.
struct ModelBilling {
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
    std::size_t calls{0};
    ModelContract contract;

    bool operator==(const ModelBilling& other) const {
        return inputTokens == other.inputTokens && outputTokens == other.outputTokens &&
               calls == other.calls && contract == other.contract;
    }
};

struct CallTrace {
    std::string binding;
    std::string prompt;
    std::string modelAlias;
    std::string modelContractKey;
    ModelContract modelContract;
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
};

struct BranchTrace {
    SourceLocation location;
    bool tookThen{false};
};

struct RetryTrace {
    SourceLocation location;
    std::size_t attempts{0};
};

struct WorkflowRun {
    std::string name;
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
    std::size_t calls{0};
    std::size_t retryAttempts{0};
    std::vector<CallTrace> trace;
    std::vector<BranchTrace> branches;
    std::vector<RetryTrace> retries;
    std::vector<std::string> effects;
    // The observation the relational analysis is stated against.
    std::map<std::string, ModelBilling> billing;

    std::size_t totalTokens() const { return addTokens(inputTokens, outputTokens); }
};

// True when two executions are indistinguishable to someone reading the bill.
bool sameBilling(const WorkflowRun& left, const WorkflowRun& right);

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
std::string printRunJson(const RunResult& result);

}  // namespace orchlang
