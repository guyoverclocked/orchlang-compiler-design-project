#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "semantic_analyzer.hpp"

#include <string>
#include <utility>
#include <vector>

namespace orchlang {

enum class IRNodeKind { Input, Secret, Model, Prompt, Call, Requirement, Output };

std::string irNodeKindName(IRNodeKind kind);

struct IRNode {
    int id{0};
    IRNodeKind kind{IRNodeKind::Input};
    std::string name;
    Type resultType;
    std::vector<int> dependencies;
    std::vector<std::pair<std::string, std::string>> attributes;
    SourceLocation location;
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
