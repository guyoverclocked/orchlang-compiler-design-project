#pragma once

// A deterministic, fully offline mock runtime.
//
// Its only purpose is to make the compiler's claims falsifiable.  The cost
// analysis asserts that no execution consumes more than the certified bound;
// the relational analysis asserts that a secret cannot change what an observer
// of the calls sees.  Neither can be measured without something that executes
// workflows, so this runtime does, against a mock provider whose behaviour is a
// pure function of a seed, and reports the full call transcript.
//
// It contacts no network service and reads no key.  Its "model" is a seeded
// generator that respects the declared max_tokens cap.
//
// WHAT CHANGED, AND WHY
//
// The first version of this runtime carried token counts, not text, and drew
// every model's output length uniformly from [0, max_tokens] no matter what the
// request said.  That is exactly the assumption the withdrawn size rule needed,
// so the runtime could never catch that rule out: the checker and the thing
// checked shared a blind spot.  Values now carry text; the provider can be made
// content-dependent, as real ones are; the provider's randomness can be coupled
// in several ways; and requests can be billed by a content-sensitive tokenizer
// instead of by the analysis's own estimate.  The harness runs every relational
// claim under all of them.

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <cstdint>
#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace orchlang {

// How the mock provider chooses a response length.
enum class ProviderMode {
    // Uniform in [0, max_tokens], whatever the request says.  The old runtime,
    // and the assumption the withdrawn size rule silently relied on.
    Uniform,
    // A function of the request's text as well as the random draw, as with a
    // real model: "reply briefly" and "reply at length" come back different.
    Content,
};

// How the provider's randomness is shared between two compared executions.
// Each is a valid coupling: every call receives a fresh draw, so a single
// execution is distributed exactly as under independent sampling.  They differ
// in which calls of two *different* executions receive the same draw.
enum class Coupling {
    // The k-th random event of the execution.
    Global,
    // The k-th call to a given model.
    Model,
    // The k-th occurrence of a given request to a given model.  The weakest
    // alignment requirement, and the one the provider and bill observers need.
    Request,
};

// How input tokens are counted for the bill.
enum class Accounting {
    // Exactly the analysis's own estimate: the template and each argument
    // counted separately at the declared characters-per-token.  Useful to check
    // the implementation against its specification; useless against reality.
    Estimate,
    // A content-sensitive tokenizer (greedy longest match over a fixed
    // vocabulary, one token per unmatched byte) applied to the request as sent,
    // plus the model's declared envelope.  It satisfies the "mockbpe" contract in
    // the tokenizer table, and it is not subadditive, like real tokenizers.
    Tokenizer,
};

std::string providerModeName(ProviderMode mode);
std::string couplingName(Coupling coupling);
std::string accountingName(Accounting accounting);

// The runtime's content-sensitive tokenizer.
std::size_t mockTokenCount(const std::string& text);

struct RunOptions {
    std::uint64_t seed{1};
    // Chance in [0,100] that one attempt inside a retry block fails and the
    // block tries again.  Models a transient failure or a rejected validation.
    unsigned retryFailurePercent{50};

    // Pins the length of named inputs and secrets instead of sampling them: in
    // words for a token-bounded value, in bytes for a byte-bounded one.  This
    // is what makes the relational claim testable: run the same workflow twice
    // under one seed, change only a secret, and compare what an observer sees.
    std::map<std::string, std::size_t> pinnedLengths;
    // Pins the truth value of named boolean inputs and secrets.
    std::map<std::string, bool> pinnedFlags;

    ProviderMode provider{ProviderMode::Uniform};
    Coupling coupling{Coupling::Global};
    Accounting accounting{Accounting::Estimate};
};

// Tokens billed to one model, which is what an itemised provider bill shows.
// Totals alone are not the right observation: two runs can agree on total
// tokens while charging different models at different prices.
struct ModelBilling {
    std::size_t inputTokens{0};
    std::size_t outputTokens{0};
    std::size_t calls{0};

    bool operator==(const ModelBilling& other) const {
        return inputTokens == other.inputTokens && outputTokens == other.outputTokens &&
               calls == other.calls;
    }
};

struct CallTrace {
    std::string binding;
    std::string prompt;
    std::string model;
    // The model as the provider names it, and the full endpoint identity.
    std::string modelString;
    std::string identity;
    std::string request;
    std::string response;
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
    // Attempts made by each retry block executed, in order.
    std::vector<std::size_t> retryAttempts;
    // The invoice: keyed by the provider's model name, never the local name.
    std::map<std::string, ModelBilling> billing;

    std::size_t totalTokens() const { return inputTokens + outputTokens; }
};

// True when two executions are indistinguishable to someone reading the bill.
bool sameBilling(const WorkflowRun& left, const WorkflowRun& right);
// True when they are indistinguishable to someone reading the provider's logs.
bool sameTranscript(const WorkflowRun& left, const WorkflowRun& right);

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
std::string printRunJson(const RunResult& result, const RunOptions& options);

}  // namespace orchlang
