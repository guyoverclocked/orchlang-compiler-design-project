#pragma once

// Relational resource analysis: a sufficient structural check for whether a
// secret changes the per-contract billing trace under a declared shared oracle.
// It compares resolved model contracts and exact symbolic request content; the
// check is intentionally incomplete and does not claim that numeric or
// probabilistic resource analyses are inapplicable in other settings.

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <cstddef>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace orchlang {

enum class RequestAtomKind { Literal, OuterValue, PriorResult };

// One ordered prompt argument. Literal contents are exact decoded bytes;
// outer identities are resolved lexical values; prior results are positional
// references to matched calls under the oracle coupling.
struct RequestAtom {
    RequestAtomKind kind{RequestAtomKind::Literal};
    std::string literal;
    std::size_t identity{0};
    ExprKind literalKind{ExprKind::StringLiteral};

    bool operator==(const RequestAtom& other) const {
        if (kind != other.kind) {
            return false;
        }
        return kind == RequestAtomKind::Literal
                   ? literal == other.literal && literalKind == other.literalKind
                                                : identity == other.identity;
    }
    bool operator!=(const RequestAtom& other) const { return !(*this == other); }
    std::string text() const;
};

struct GuardTerm {
    ConditionKind kind{ConditionKind::Flag};
    ComparisonOp op{ComparisonOp::LessEqual};
    std::size_t limit{0};
    RequestAtom subject;

    bool operator==(const GuardTerm& other) const {
        return kind == other.kind && op == other.op && limit == other.limit &&
               subject == other.subject;
    }
    bool operator!=(const GuardTerm& other) const { return !(*this == other); }
};

enum class SignatureNodeKind { Call, Retry, Branch };

struct SignatureNode;
using Signature = std::vector<SignatureNode>;

struct SignatureNode {
    SignatureNodeKind kind{SignatureNodeKind::Call};

    // Call. `modelAlias` is for display only; equality uses the resolved
    // provider/model/cap/price contract and exact request representation.
    std::optional<ModelContract> modelContract;
    std::string modelAlias;
    std::string promptTemplateText;
    std::vector<RequestAtom> arguments;

    // Retry
    std::size_t repeatBound{0};

    // Branch on a public guard: both executions take the same arm, so the two
    // arms are kept separately rather than being required to match.
    std::string guard;
    GuardTerm guardTerm;

    // Retry body, or the two arms of a public branch.
    std::vector<Signature> children;

    SourceLocation location;

    bool operator==(const SignatureNode& other) const;
    bool operator!=(const SignatureNode& other) const { return !(*this == other); }
};

bool signaturesEqual(const Signature& left, const Signature& right);
std::string signatureText(const Signature& signature);

// Why a signature could not be built, which is itself a reason to reject.
struct SignatureResult {
    Signature signature;
    bool defined{true};
    std::string reason;
    SourceLocation location;
};

// One secret-guarded branch the analysis examined, kept so the certificate can
// show which obligations were discharged rather than merely asserting safety.
struct RelationalObligation {
    std::string workflow;
    std::string guard;
    bool discharged{false};
    std::string detail;
    SourceLocation location;
};

struct RelationalResult {
    std::vector<RelationalObligation> obligations;
    DiagnosticBag diagnostics;

    bool success() const { return !diagnostics.hasErrors(); }
};

class RelationalAnalyzer {
public:
    RelationalResult analyze(const Program& program, const SemanticResult& semantic) const;
};

}  // namespace orchlang
