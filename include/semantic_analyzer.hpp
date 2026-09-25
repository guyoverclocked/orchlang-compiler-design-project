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
// literal contributes its text, a variable contributes the identity of the
// binding it names, and a secret contributes nothing the analysis may rely on.
struct ArgumentFact {
    std::string name;
    bool isLiteral{false};
    // The binding's content depends on a secret.  Such a value may not reach a
    // prompt at all (E230).
    bool isSecret{false};
    // The binding was made under a secret program counter, so its existence
    // depends on a secret even when its content does not.  The withdrawn size
    // rule treated this like isSecret; it is kept so that baseline can be
    // reproduced exactly.
    bool isPcSecret{false};
    std::size_t literalTokens{0};
    // What a literal substitutes into the prompt, character for character.
    std::string literalText;
    // The binding an identifier resolves to; 0 for a literal.
    int bindingId{0};
    bool byteBoundKnown{false};
    std::size_t byteBound{0};
};

// A prompt template split at its placeholders.  A piece is either literal
// template text or a reference to the argument substituted at that point.
struct TemplatePiece {
    bool isArgument{false};
    std::string text;
    std::size_t argument{0};
};

// What one 'call' site contributes to a cost bound.  Recorded while the
// symbol table is in scope so the cost analysis can be a pure structural walk.
struct CallSiteFacts {
    std::string promptName;
    std::string modelName;
    // The endpoint the request goes to, independent of local names.
    std::string modelIdentity;
    // The model as the provider names it on an invoice, and the provider: the
    // part of that name before the first '/', or the whole name.
    std::string modelString;
    std::string modelProvider;
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
    // The request as the provider will receive it, symbolically.
    std::vector<TemplatePiece> pieces;
    // Bytes of template text sent, placeholders excluded.
    std::size_t templateBytes{0};
    std::string tokenizer;
    std::size_t overhead{0};
    bool hasByteCap{false};
    std::size_t byteCap{0};
};

// The guard of one 'if', as the relational analysis needs it.
struct GuardFact {
    // The binding the guard tests.
    int subjectId{0};
    // The guard tests secret data, so its outcome is a function of a secret.
    // Such a branch is where the relational obligation arises.
    bool secretData{false};
    // For a secret guard, the secret declaration whose value it tests, after
    // following any endorsed copies back to their source.
    int secretRootId{0};
    // Tokens or bytes the tested secret may have, when declared.
    bool secretBoundKnown{false};
    std::size_t secretBound{0};
};

// Every binding the program makes, by id, so later passes never have to
// resolve a name again.
struct BindingFact {
    std::string name;
    SymbolKind kind{SymbolKind::Input};
    Label label{publicTrusted()};
    Label dataLabel{publicTrusted()};
    // For a call result, the call that produced it.
    const CallExpr* producer{nullptr};
    // For a reclassified value, the binding it copies.
    int aliasOf{0};
    SourceLocation location;
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
    std::map<const IfStmt*, GuardFact> guards;
    std::map<int, BindingFact> bindings;
    // The binding each 'let' and each reclassification introduces.
    std::map<const Stmt*, int> introduced;
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
