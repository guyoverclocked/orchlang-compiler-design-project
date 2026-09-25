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

    // Input tokens that hold for the real tokenizer, not an estimate: every
    // request's bytes, through the called model's verified tokenizer contract,
    // plus the tokens the tokenizer and the provider's envelope add.  Bytes add
    // up under concatenation and token counts do not, which is why this is
    // computed from bytes.  Undefined when some call's model names no verified
    // tokenizer, or some argument has no byte bound; the reason says which.
    bool inputGuaranteedDefined{true};
    std::string inputGuaranteedReason;
    std::size_t inputGuaranteed{0};
    // Output plus guaranteed input, maximised per branch like totalTokens.
    std::size_t totalGuaranteed{0};

    // A lower bound on total tokens in the estimate unit: templates only, no
    // output, one attempt per retry, the cheaper arm of each branch.  It exists
    // for the interval-counting leakage baseline of Ngo et al., which needs
    // both ends of the interval.
    std::size_t lowerTotal{0};

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

    // The budget is checked against the guaranteed total when one exists, and
    // against the estimate otherwise; the certificate says which.
    bool budgetGuaranteed() const { return bound.inputGuaranteedDefined; }
    std::size_t budgetBasis() const {
        return budgetGuaranteed() ? bound.totalGuaranteed : bound.total();
    }
    bool withinBudget() const { return budgetBasis() <= budget; }
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

// The bound of one block on its own, with no diagnostics.  Used by the
// withdrawn equal-bounds relational rule, which compared these per arm.
CostBound boundOfBlock(const Block& block, const SemanticResult& semantic);

}  // namespace orchlang
