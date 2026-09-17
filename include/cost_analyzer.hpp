#pragma once

// Static token-cost analysis.
//
// The bound is derived by structural induction over a workflow body, so it is
// computed once, without executing anything and without consulting a model.
// It is deliberately reported in two parts:
//
//   guaranteed  output tokens, capped by each provider's own max_tokens.  This
//               half needs no assumption about how text is tokenized.
//   estimated   input tokens: prompt templates plus the declared bounds of the
//               arguments substituted into them.  This half is sound only
//               relative to the declared characters-per-token assumption, which
//               is recorded alongside it.
//
// Keeping the halves apart is the point: a reader can see exactly how much of
// the certified number rests on an assumption and how much does not.

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"
#include "token_cost.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace orchlang {

// Three separately sound facts about a workflow's token consumption.
//
// `guaranteed` and `estimated` are each an upper bound on their own component.
// `total` is an upper bound on the sum.  They are tracked separately because at
// a branch they are maximised differently: the tightest sound total is the
// larger arm's total, while the tightest sound bound on each component is that
// component's maximum across arms.  Taking one arm's pair whole -- which is what
// this compiler did until audit finding 2 -- gives a correct total but does NOT
// bound each component, because the losing arm can dominate one of them.
//
// The invariant is `total <= guaranteed + estimated`, and the gap is real: it
// is the price of reporting a faithful split rather than a single number.
struct CostBound {
    std::size_t guaranteed{0};
    std::size_t estimated{0};
    std::size_t totalTokens{0};
    double money{0.0};
    // False when at least one selected model declared no price, so the
    // monetary figure is a partial total rather than a bound.
    bool moneyComplete{true};
    // False when an argument reaching a prompt had no declared token bound.
    bool defined{true};

    std::size_t total() const { return totalTokens; }
    // The sum of the componentwise bounds, which dominates total() and is what
    // a reader gets if they add the two reported halves together.
    std::size_t componentSum() const { return addTokens(guaranteed, estimated); }
};

// One line of the derivation, kept so the certificate can show its working.
struct DerivationStep {
    int depth{0};
    std::string rule;
    std::string detail;
    CostBound bound;
    SourceLocation location;
};

struct WorkflowCost {
    std::string name;
    std::size_t budget{0};
    CostBound bound;
    std::vector<DerivationStep> derivation;

    bool withinBudget() const { return bound.total() <= budget; }
};

struct CostResult {
    std::vector<WorkflowCost> workflows;
    DiagnosticBag diagnostics;
    AnalysisOptions options;

    bool success() const { return !diagnostics.hasErrors(); }
};

class CostAnalyzer {
public:
    CostResult analyze(const Program& program, const SemanticResult& semantic) const;
};

}  // namespace orchlang
