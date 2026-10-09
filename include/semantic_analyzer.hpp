#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "label.hpp"
#include "symbol_table.hpp"

#include <cstddef>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace orchlang {

// UTF-8 bytes per estimated input token for each template/argument fragment.
//
// The resulting call bound is sound only under the explicit compositional
// assumption that complete-request input usage is at most the sum of those
// fragment estimates and declared argument bounds. The default byte-per-four
// estimate does not model real provider tokenizers, request envelopes, or
// tokenization effects at fragment boundaries.
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
    std::string literalText;
    // The runtime request oracle distinguishes literal expression kinds even
    // when their substituted bytes happen to be equal (for example true and
    // the text literal "true").
    ExprKind literalKind{ExprKind::StringLiteral};
    bool isSecret{false};
    std::size_t literalTokens{0};
    bool tokenBoundKnown{false};
    std::size_t tokenBound{0};
    std::string tokenBoundTokenizer;
    Label contentLabel{publicTrusted()};
    std::size_t bindingIdentity{0};
    std::size_t valueIdentity{0};
};

// What one 'call' site contributes to a cost bound.  Recorded while the
// symbol table is in scope so the cost analysis can be a pure structural walk.
struct CallSiteFacts {
    std::size_t id{0};
    SourceLocation location;
    std::string resultName;
    std::size_t resultValueIdentity{0};
    std::string promptName;
    std::string modelAlias;
    // Kept for readable cost derivations; identity/equality use the resolved
    // contract below, never the source-level alias.
    std::string modelName;
    std::optional<ModelContract> resolvedModel;
    std::string promptTemplateText;
    // Output tokens capped by the declared provider contract. This half does
    // not use the input-tokenizer estimate, but assumes the provider honors
    // its declared max_tokens cap.
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

struct BranchGuardFacts {
    bool resolved{false};
    Label contentLabel{publicTrusted()};
    std::size_t bindingIdentity{0};
    std::size_t valueIdentity{0};
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
    // Intrinsic data sensitivity and lexical identity of the guard, excluding
    // the enclosing program counter. The relational pass uses these facts to
    // distinguish a secret predicate from a public predicate evaluated inside
    // a secret-dependent region.
    std::map<const IfStmt*, BranchGuardFacts> branchGuards;
    // Source declaration identity used by the offline runtime's input oracle.
    std::map<const Stmt*, std::size_t> declarationBindings;
    // The result's value identity is stable through aliases and unique under
    // shadowing; relational positional references are mapped from this value.
    std::map<const LetStmt*, std::size_t> letResultValueIdentities;
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
