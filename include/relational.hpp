#pragma once

// Relational resource analysis: can a secret change what an observer sees?
//
// HOW THIS GOT HERE
//
// The first version of this compiler accepted a secret-guarded branch whenever
// its two arms had equal certified upper bounds.  An external audit refuted
// that with a two-line counterexample: equal maxima say nothing about equal
// costs (examples/invalid/equal_bounds.orch).
//
// The repair compared "billing signatures": which model each arm calls, in
// order, and a symbolic *size* for each request -- template tokens, literal
// tokens, |x| for outer variables.  That was also unsound, for the same reason
// one level down (docs/AUDIT_2026-09-25.md).  A provider's output length depends
// on what a request *says*, not on how long it is: a small real model answers
// "acknowledge briefly" in 12-16 tokens and "escalate in detail" in 64, from
// prompts one token apart.  And a real tokenizer does not bill two strings of
// equal estimated size equally: "aaaa" and "bbbb" are 1 and 2 tokens under
// r50k_base.  Any rule that compares sizes compares something coarser than what
// determines the bill.  The repair also compared models, prompts and variables
// by local name, so a model redeclared inside one arm passed unnoticed.
//
// WHAT IS COMPARED NOW
//
// Requests, by content.  Each arm is abstracted to a sequence of symbolic
// requests: the endpoint's identity (never its local name), the template text
// and literal text exactly as sent, and, for the parts not known statically,
// references that provably denote the same text in both compared executions:
//
//   var(b)    a binding made outside the region compared, by identity, whose
//             content is public, so it is equal because public inputs are;
//   res(p)    the response to an earlier call in the region, by position,
//             equal because the two executions made the same earlier requests
//             and the provider's randomness is coupled.
//
// Two arms with equal signatures send the provider identical requests in the
// same order, and so receive identical responses under the coupling.
// Everything any observer of the call transcript can see is then equal: the
// invoice, under any tokenizer and any pricing; the provider's logs; even a
// prompt cache's hit pattern.  No tokenizer assumption is needed at all.
//
// HOW MUCH, NOT JUST WHETHER
//
// The analysis resolves every secret guard to each combination of outcomes the
// secrets allow and counts the distinct signatures that result.  If there are k,
// the observation is a function of which of k classes the secret falls in plus
// randomness independent of the secret, so no observer learns more than log2 k
// bits about it (min-capacity), however many times the workflow runs and
// whatever public inputs an adversary chooses.  A workflow declares how many
// bits it may leak ('leaks b', default 0).

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace orchlang {

// Which relational rule to apply.  Only Content is sound.  The other two are
// the withdrawn rules, kept so the evaluation can measure them on the same
// programs; they are never the default and the certificate names the rule.
enum class RelationalRule {
    Content,
    // Withdrawn 2026-09-25: symbolic sizes, models and variables by local name.
    Sizes,
    // Withdrawn 2026-09-17: equal certified upper bounds.
    Bounds,
};

std::string relationalRuleName(RelationalRule rule);

struct RelationalOptions {
    RelationalRule rule{RelationalRule::Content};
    // Most combinations of secret-guard outcomes enumerated exactly.  Beyond
    // this the count of combinations itself is used as the class bound, which
    // is sound and looser.
    std::size_t maxOutcomeVectors{4096};
};

// One secret-guarded branch the analysis examined, kept so the certificate can
// show which obligations were discharged rather than merely asserting safety.
struct RelationalObligation {
    std::string workflow;
    std::string guard;
    // The two arms send identical requests, so this branch alone reveals
    // nothing about its guard.
    bool discharged{false};
    std::string detail;
    std::string thenSignature;
    std::string elseSignature;
    SourceLocation location;
};

// The quantitative verdict for one workflow.
struct LeakageReport {
    std::string workflow;
    std::string observer;
    std::string rule;
    double budgetBits{0.0};
    // The distinct secret-dependent guard predicates, as written.
    std::vector<std::string> predicates;
    // Combinations of predicate outcomes the declared secrets allow.
    std::size_t outcomeVectors{0};
    bool enumerated{true};
    // Distinct observable behaviours across those combinations; the leakage
    // bound is log2 of this.
    std::size_t classes{1};
    double bits{0.0};
    bool withinBudget{true};
    // One canonical signature per class, the evidence an independent checker
    // can recompute from the source.
    std::vector<std::string> classSignatures;
};

struct RelationalResult {
    std::vector<RelationalObligation> obligations;
    std::vector<LeakageReport> leakage;
    DiagnosticBag diagnostics;

    bool success() const { return !diagnostics.hasErrors(); }
};

class RelationalAnalyzer {
public:
    RelationalAnalyzer() = default;
    explicit RelationalAnalyzer(RelationalOptions options) : options_(options) {}

    RelationalResult analyze(const Program& program, const SemanticResult& semantic) const;

private:
    RelationalOptions options_;
};

// The withdrawn rules, as they were.  Evaluation baselines only.
RelationalResult analyzeWithSizeRule(const Program& program, const SemanticResult& semantic);
RelationalResult analyzeWithBoundsRule(const Program& program, const SemanticResult& semantic);

}  // namespace orchlang
