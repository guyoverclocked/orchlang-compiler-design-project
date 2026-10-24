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

// Historical option name. std::string::size measures UTF-8 bytes, not Unicode
// characters or model tokens. The mock defines literal/template length as
// ceil(bytes/divisor), then adds bounded argument lengths. This is a synthetic
// resource unit, not tokenization of a fully serialized deployed request.
// Real tokenizers need separate exact serialization/tokenizer contracts.
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
    std::size_t bindingId{0};
    std::string literalText;
    std::string type;
};

// What one 'call' site contributes to a cost bound.  Recorded while the
// symbol table is in scope so the cost analysis can be a pure structural walk.
struct CallSiteFacts {
    std::string promptName;
    std::string modelName;
    std::size_t modelBindingId{0};
    std::size_t promptBindingId{0};
    std::string modelContract;
    std::string requestTemplate;
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
    std::map<const IfStmt*, std::size_t> guardBindings;
    std::map<const Stmt*, std::size_t> declarationBindings;
    std::map<const ReclassifyStmt*, std::size_t> reclassificationSources;
    std::map<const Stmt*, std::size_t> statementScopes;
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
