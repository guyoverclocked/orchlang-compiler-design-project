#include "cost_analyzer.hpp"

#include <sstream>
#include <string>

namespace orchlang {

namespace {

// Sequential composition: costs add.
CostBound sequence(const CostBound& left, const CostBound& right) {
    CostBound combined;
    combined.guaranteed = addTokens(left.guaranteed, right.guaranteed);
    combined.estimated = addTokens(left.estimated, right.estimated);
    combined.money = left.money + right.money;
    combined.moneyComplete = left.moneyComplete && right.moneyComplete;
    combined.defined = left.defined && right.defined;
    return combined;
}

// Choice: the bound is whichever arm costs more in total.  Taking that arm's
// components whole, rather than the componentwise maximum, keeps the reported
// split faithful to a single real execution path while still dominating both.
CostBound choice(const CostBound& left, const CostBound& right) {
    CostBound chosen = left.total() >= right.total() ? left : right;
    chosen.money = left.money >= right.money ? left.money : right.money;
    chosen.moneyComplete = left.moneyComplete && right.moneyComplete;
    chosen.defined = left.defined && right.defined;
    return chosen;
}

// Bounded repetition: the body may run up to `factor` times.
CostBound repeat(const CostBound& body, std::size_t factor) {
    CostBound scaled;
    scaled.guaranteed = multiplyTokens(body.guaranteed, factor);
    scaled.estimated = multiplyTokens(body.estimated, factor);
    scaled.money = body.money * static_cast<double>(factor);
    scaled.moneyComplete = body.moneyComplete;
    scaled.defined = body.defined;
    return scaled;
}

class Deriver {
public:
    Deriver(const SemanticResult& semantic, std::vector<DerivationStep>& derivation,
            DiagnosticBag& diagnostics)
        : semantic_(semantic), derivation_(derivation), diagnostics_(diagnostics) {}

    CostBound block(const Block& statements, int depth);

private:
    CostBound statement(const Stmt& node, int depth);
    void record(int depth, std::string rule, std::string detail, const CostBound& bound,
                const SourceLocation& location);
    void checkCostChannel(const IfStmt& branch, const CostBound& thenBound,
                          const CostBound& elseBound);

    const SemanticResult& semantic_;
    std::vector<DerivationStep>& derivation_;
    DiagnosticBag& diagnostics_;
};

// A branch whose arms cost different amounts and whose guard is not public
// leaks the guard through the bill, even when no value crosses a boundary.
// Neither analysis can see this on its own: the label system does not know what
// an arm costs, and the cost analysis does not know what the guard is.
void Deriver::checkCostChannel(const IfStmt& branch, const CostBound& thenBound,
                               const CostBound& elseBound) {
    const auto guard = semantic_.guardLabels.find(&branch);
    if (guard == semantic_.guardLabels.end()) {
        return;
    }
    if (thenBound.total() == elseBound.total()) {
        return;
    }
    if (guard->second.isSecret()) {
        std::ostringstream message;
        message << "the arms of this branch cost different amounts (" << thenBound.total()
                << " vs " << elseBound.total()
                << " tokens) and the branch is guarded by a secret, so the token bill reveals "
                   "the secret";
        diagnostics_.error("E236", branch.location, message.str());
    } else if (guard->second.isUntrusted()) {
        std::ostringstream message;
        message << "the arms of this branch cost different amounts (" << thenBound.total()
                << " vs " << elseBound.total()
                << " tokens) and the branch is guarded by untrusted data, so an injected value "
                   "chooses how much this workflow spends";
        diagnostics_.warning("W237", branch.location, message.str());
    }
}

void Deriver::record(int depth, std::string rule, std::string detail, const CostBound& bound,
                     const SourceLocation& location) {
    derivation_.push_back({depth, std::move(rule), std::move(detail), bound, location});
}

CostBound Deriver::statement(const Stmt& node, int depth) {
    switch (node.kind()) {
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(node);
            CostBound bound;
            if (!let.call) {
                return bound;
            }
            const auto found = semantic_.callSites.find(let.call.get());
            if (found == semantic_.callSites.end()) {
                bound.defined = false;
                record(depth, "call", let.name + " (no recorded call site)", bound, node.location);
                return bound;
            }
            const CallSiteFacts& site = found->second;
            bound.guaranteed = site.modelMaxTokens;
            bound.estimated = addTokens(site.promptTemplateTokens, site.argumentTokens);
            bound.defined = site.argumentBoundsKnown;
            if (site.hasUnitPrice) {
                bound.money = static_cast<double>(addTokens(bound.guaranteed, bound.estimated)) *
                              site.unitPrice;
            } else {
                bound.moneyComplete = false;
            }

            std::ostringstream detail;
            detail << let.name << " = " << site.promptName << " via " << site.modelName
                   << " [out<=" << site.modelMaxTokens << ", in<=" << site.promptTemplateTokens << '+'
                   << site.argumentTokens << ']';
            record(depth, "call", detail.str(), bound, node.location);
            return bound;
        }
        case StmtKind::If: {
            const auto& branch = static_cast<const IfStmt&>(node);
            record(depth, "branch", conditionToString(branch.condition), {}, node.location);
            const CostBound thenBound = block(branch.thenBranch, depth + 1);
            const CostBound elseBound =
                branch.hasElse ? block(branch.elseBranch, depth + 1) : CostBound{};
            const CostBound bound = choice(thenBound, elseBound);
            checkCostChannel(branch, thenBound, elseBound);

            std::ostringstream detail;
            detail << "max(then=" << thenBound.total() << ", else=" << elseBound.total() << ')';
            record(depth, "branch-max", detail.str(), bound, node.location);
            return bound;
        }
        case StmtKind::Retry: {
            const auto& retry = static_cast<const RetryStmt&>(node);
            record(depth, "retry", "bound " + std::to_string(retry.bound), {}, node.location);
            const CostBound body = block(retry.body, depth + 1);
            const CostBound bound = repeat(body, retry.bound);

            std::ostringstream detail;
            detail << retry.bound << " x " << body.total();
            record(depth, "retry-scale", detail.str(), bound, node.location);
            return bound;
        }
        case StmtKind::Input:
        case StmtKind::Secret:
        case StmtKind::Model:
        case StmtKind::Prompt:
        case StmtKind::Tool:
        case StmtKind::Require:
        case StmtKind::Emit:
        case StmtKind::Reclassify:
        case StmtKind::Output:
            // Declarations, requirements, effects, and relabelling consume no
            // model tokens; only a 'call' reaches a model.
            return {};
    }
    return {};
}

CostBound Deriver::block(const Block& statements, int depth) {
    CostBound bound;
    for (const auto& node : statements) {
        if (node) {
            bound = sequence(bound, statement(*node, depth));
        }
    }
    return bound;
}

}  // namespace

CostResult CostAnalyzer::analyze(const Program& program, const SemanticResult& semantic) const {
    CostResult result;
    result.options = semantic.options;

    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        WorkflowCost cost;
        cost.name = workflow.name;
        cost.budget = workflow.budget;

        Deriver deriver(semantic, cost.derivation, result.diagnostics);
        cost.bound = deriver.block(workflow.statements, 0);

        if (!cost.bound.defined) {
            result.diagnostics.error(
                "E265", workflow.location,
                "workflow '" + workflow.name +
                    "' has no defined token bound because a prompt argument carries no declared bound");
        } else if (isSaturated(cost.bound.total())) {
            result.diagnostics.error("E266", workflow.location,
                                     "workflow '" + workflow.name +
                                         "' has a token bound too large to represent; reduce the "
                                         "declared repetition bounds");
        } else if (!cost.withinBudget()) {
            std::ostringstream message;
            message << "certified token bound " << cost.bound.total() << " (guaranteed "
                    << cost.bound.guaranteed << " + estimated " << cost.bound.estimated
                    << ") exceeds workflow budget " << cost.budget;
            result.diagnostics.error("E260", workflow.location, message.str());
        }
        result.workflows.push_back(std::move(cost));
    }
    return result;
}

}  // namespace orchlang
