#pragma once

// Relational resource analysis: does a secret change the bill?
//
// WHY THIS REPLACES THE OLD RULE
//
// The previous compiler accepted a secret-guarded branch whenever the two arms
// had equal *upper bounds*, and claimed that established cost noninterference.
// It does not, and the counterexample is short:
//
//     secret s: text max_tokens 1;
//     input x: text max_tokens 100;
//     input y: text max_tokens 100;
//     if tokens(s) == 0 { let a = call p(x) using m; }
//     else              { let b = call p(y) using m; }
//
// Both arms bound at the same number, so the old rule accepted it.  But x and y
// are different values with different actual lengths, so the secret really does
// move the bill.  Equal maxima say nothing about equal costs.
//
// WHAT REPLACES IT
//
// Costs here cannot be compared numerically at all, because a model call's
// output length is chosen by the provider, not by the program.  So instead of
// comparing numbers we compare *structure*: each arm is abstracted to a billing
// signature recording, in order, which model is called and a symbolic term for
// how large its input is.  Two arms are indistinguishable to someone reading the
// bill when their signatures are identical.
//
// The symbolic terms refer only to things that provably agree across the two
// executions being compared: constants, variables bound outside the branch
// (fixed by hypothesis), and the results of earlier calls in the same signature
// (fixed by the oracle coupling, since the k-th call to a model returns the same
// answer in both runs).  A term that depends on a secret makes the signature
// undefined, and an undefined signature is rejected.
//
// This is deliberately incomplete.  Two arms that always happen to cost the same
// but read different variables are rejected, because the compiler has no reason
// to believe those variables have equal length.

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace orchlang {

// A symbolic term for the input size of one call, built only from quantities
// that are equal across the two compared executions.
struct SizeTerm {
    // Tokens contributed by the template and by literal arguments.
    std::size_t constant{0};
    // Variables bound outside the branch under comparison, by name.  Sorted, so
    // two terms compare equal exactly when they name the same variables.
    std::vector<std::string> outer;
    // Indices, within this arm's own signature, of earlier calls whose results
    // are used as arguments.  Positional rather than by name, because the two
    // arms bind different names to corresponding calls.
    std::vector<std::size_t> priorResults;

    bool operator==(const SizeTerm& other) const {
        return constant == other.constant && outer == other.outer &&
               priorResults == other.priorResults;
    }
    bool operator!=(const SizeTerm& other) const { return !(*this == other); }

    std::string text() const;
};

enum class SignatureNodeKind { Call, Retry, Branch };

struct SignatureNode;
using Signature = std::vector<SignatureNode>;

struct SignatureNode {
    SignatureNodeKind kind{SignatureNodeKind::Call};

    // Call
    std::string model;
    SizeTerm inputSize;

    // Retry
    std::size_t repeatBound{0};

    // Branch on a public guard: both executions take the same arm, so the two
    // arms are kept separately rather than being required to match.
    std::string guard;

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
