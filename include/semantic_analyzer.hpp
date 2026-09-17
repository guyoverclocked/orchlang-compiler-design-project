#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "label.hpp"
#include "symbol_table.hpp"

#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace orchlang {

// How many source characters the analysis assumes fit in one token.
//
// The input-token half of a cost bound is only as sound as this assumption, so
// it is an explicit, recorded parameter rather than a hidden constant.  A value
// of 1 is unconditionally sound for any tokenizer that never emits more than
// one token per character; larger values trade that unconditional soundness for
// a tighter, assumption-relative bound.  The default follows the widely used
// four-characters-per-token rule for English prose.
inline constexpr std::size_t defaultCharsPerToken() { return 4; }

struct AnalysisOptions {
    std::size_t charsPerToken{defaultCharsPerToken()};
};

// Upper bound, in tokens, on a piece of source text under the declared
// characters-per-token assumption.  Rounds up, because a bound may only err high.
std::size_t estimateTextTokens(const std::string& text, std::size_t charsPerToken);

// One place where the author deliberately stepped outside the lattice.
// Every such site is reported in the certificate.
struct ReclassificationSite {
    std::string workflow;
    std::string sourceName;
    std::string resultName;
    bool endorsement{false};
    Label from;
    Label to;
    std::string reason;
    SourceLocation location;
};

// One argument at a call site, as the relational analysis needs to see it: a
// literal contributes a constant, a variable contributes its identity, and a
// secret contributes nothing the analysis may rely on.
struct ArgumentFact {
    std::string name;
    bool isLiteral{false};
    bool isSecret{false};
    std::size_t literalTokens{0};
};

// What one 'call' site contributes to a cost bound.  Recorded while the
// symbol table is in scope so the cost analysis can be a pure structural walk.
struct CallSiteFacts {
    std::string promptName;
    std::string modelName;
    // Output tokens the provider itself caps.  This half of the bound holds
    // without any tokenizer assumption.
    std::size_t modelMaxTokens{0};
    // Input tokens: the template plus the bounded arguments substituted into
    // it.  Sound relative to the declared characters-per-token assumption.
    std::size_t promptTemplateTokens{0};
    std::size_t argumentTokens{0};
    bool argumentBoundsKnown{true};
    bool hasUnitPrice{false};
    double unitPrice{0.0};
    std::vector<ArgumentFact> arguments;
};

struct WorkflowFacts {
    std::string name;
    std::size_t budget{0};
    std::size_t scope{0};
    // Set when an input feeding a prompt had no declared token bound, which
    // makes the input-token component of the bound undefined.
    bool inputBoundMissing{false};
};

struct SemanticResult {
    SymbolTable symbols;
    DiagnosticBag diagnostics;
    std::map<std::string, std::size_t> workflowScopes;
    std::map<std::string, WorkflowFacts> workflowFacts;
    std::vector<ReclassificationSite> reclassifications;
    std::map<const CallExpr*, CallSiteFacts> callSites;
    // Program-counter label inside each branch: the guard joined with the
    // enclosing context.  This is what decides whether an effect in the arm is
    // an implicit flow.
    std::map<const IfStmt*, Label> guardLabels;
    // The guard expression's own label, ignoring the enclosing context.  The
    // relational analysis needs this one: a public guard inside a secret arm
    // still sends both compared executions down the same path.
    std::map<const IfStmt*, Label> guardOwnLabels;
    AnalysisOptions options;

    bool success() const { return !diagnostics.hasErrors(); }
};

class SemanticAnalyzer {
public:
    SemanticAnalyzer() = default;
    explicit SemanticAnalyzer(AnalysisOptions options) : options_(options) {}

    SemanticResult analyze(const Program& program) const;

private:
    AnalysisOptions options_;
};

}  // namespace orchlang
