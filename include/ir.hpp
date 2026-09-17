#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "label.hpp"
#include "semantic_analyzer.hpp"

#include <string>
#include <utility>
#include <vector>

namespace orchlang {

enum class IRNodeKind {
    Input,
    Secret,
    Model,
    Prompt,
    Tool,
    Call,
    Requirement,
    Emit,
    Reclassify,
    Branch,
    Retry,
    Output
};

std::string irNodeKindName(IRNodeKind kind);

struct IRNode {
    int id{0};
    IRNodeKind kind{IRNodeKind::Input};
    std::string name;
    Type resultType;
    std::vector<int> dependencies;
    std::vector<std::pair<std::string, std::string>> attributes;
    SourceLocation location;

    // Where this node sits in the workflow's control structure, as a path such
    // as "root/then@7".  Nodes in different regions are ordered by the region
    // tree rather than by their position in the flat list.
    std::string region{"root"};
    // Product of the repetition bounds of the enclosing retry blocks, so a
    // reader can see how many times this node may run.
    std::size_t repeatFactor{1};
    // Security label carried by the value this node produces.
    Label label{publicTrusted()};
};

struct WorkflowIR {
    std::string workflowName;
    std::vector<IRNode> nodes;
};

struct ProgramIR {
    std::vector<WorkflowIR> workflows;
};

struct IRBuildResult {
    ProgramIR program;
    DiagnosticBag diagnostics;

    bool success() const { return !diagnostics.hasErrors(); }
};

class IRLowerer {
public:
    IRBuildResult lower(const Program& program, const SemanticResult& semantic) const;
};

bool hasDependencyCycle(const WorkflowIR& workflow, std::vector<int>* cycle = nullptr);
std::string printIR(const ProgramIR& program);
std::string printIRJson(const ProgramIR& program);

}  // namespace orchlang
