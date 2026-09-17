#include "ir.hpp"

#include "token_cost.hpp"

#include <algorithm>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

std::string irNodeKindName(IRNodeKind kind) {
    switch (kind) {
        case IRNodeKind::Input: return "Input";
        case IRNodeKind::Secret: return "Secret";
        case IRNodeKind::Model: return "Model";
        case IRNodeKind::Prompt: return "Prompt";
        case IRNodeKind::Tool: return "Tool";
        case IRNodeKind::Call: return "Call";
        case IRNodeKind::Requirement: return "Requirement";
        case IRNodeKind::Emit: return "Emit";
        case IRNodeKind::Reclassify: return "Reclassify";
        case IRNodeKind::Branch: return "Branch";
        case IRNodeKind::Retry: return "Retry";
        case IRNodeKind::Output: return "Output";
    }
    return "Unknown";
}

namespace {

void addDependency(std::vector<int>& dependencies, int identifier) {
    if (std::find(dependencies.begin(), dependencies.end(), identifier) == dependencies.end()) {
        dependencies.push_back(identifier);
    }
}

std::string jsonEscape(const std::string& text) {
    std::ostringstream out;
    for (const char character : text) {
        switch (character) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << character; break;
        }
    }
    return out.str();
}

// A stack of name-to-node maps mirroring the block structure of the source, so
// a binding introduced inside a branch does not leak into its sibling.
class ValueScopes {
public:
    void push() { frames_.emplace_back(); }
    void pop() { frames_.pop_back(); }

    void define(const std::string& name, int id) {
        if (!frames_.empty()) {
            frames_.back()[name] = id;
        }
    }

    const int* find(const std::string& name) const {
        for (auto frame = frames_.rbegin(); frame != frames_.rend(); ++frame) {
            const auto found = frame->find(name);
            if (found != frame->end()) {
                return &found->second;
            }
        }
        return nullptr;
    }

private:
    std::vector<std::map<std::string, int>> frames_;
};

class Lowerer {
public:
    Lowerer(const SemanticResult& semantic, WorkflowIR& workflow)
        : semantic_(semantic), workflow_(workflow) {}

    void lowerBlock(const Block& statements, const std::string& region, std::size_t repeatFactor);

private:
    void lowerStatement(const Stmt& node, const std::string& region, std::size_t repeatFactor);
    void addExpressionDependency(const Expr& expression, std::vector<int>& dependencies) const;
    Label labelOf(const std::string& name, std::size_t scope) const;

    const SemanticResult& semantic_;
    WorkflowIR& workflow_;
    ValueScopes values_;
    int nextId_{1};

public:
    ValueScopes& values() { return values_; }
    std::size_t scope{0};
};

void Lowerer::addExpressionDependency(const Expr& expression, std::vector<int>& dependencies) const {
    if (expression.kind() != ExprKind::Identifier) {
        return;
    }
    const auto& identifier = static_cast<const IdentifierExpr&>(expression);
    if (const int* found = values_.find(identifier.name)) {
        addDependency(dependencies, *found);
    }
}

Label Lowerer::labelOf(const std::string& name, std::size_t lookupScope) const {
    const Symbol* symbol = semantic_.symbols.lookup(lookupScope, name);
    return symbol ? symbol->label : publicTrusted();
}

void Lowerer::lowerStatement(const Stmt& statement, const std::string& region,
                             std::size_t repeatFactor) {
    IRNode node;
    node.id = nextId_++;
    node.location = statement.location;
    node.region = region;
    node.repeatFactor = repeatFactor;

    switch (statement.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(statement);
            node.kind = IRNodeKind::Input;
            node.name = input.name;
            node.resultType = input.type;
            node.label = input.label;
            if (input.hasTokenBound) {
                node.attributes.push_back({"max_tokens", std::to_string(input.tokenBound)});
            }
            values_.define(input.name, node.id);
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(statement);
            node.kind = IRNodeKind::Secret;
            node.name = secret.name;
            node.resultType = secret.type;
            node.label = {Confidentiality::Secret, Integrity::Trusted};
            if (secret.hasTokenBound) {
                node.attributes.push_back({"max_tokens", std::to_string(secret.tokenBound)});
            }
            values_.define(secret.name, node.id);
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(statement);
            node.kind = IRNodeKind::Model;
            node.name = model.name;
            node.resultType = {TypeKind::Unknown};
            node.attributes.push_back({"provider", model.provider});
            node.attributes.push_back({"name", model.modelName});
            node.attributes.push_back({"max_tokens", std::to_string(model.maxTokens)});
            values_.define(model.name, node.id);
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(statement);
            node.kind = IRNodeKind::Prompt;
            node.name = prompt.name;
            node.resultType = prompt.returnType;
            node.attributes.push_back({"parameters", std::to_string(prompt.parameters.size())});
            values_.define(prompt.name, node.id);
            break;
        }
        case StmtKind::Tool: {
            const auto& tool = static_cast<const ToolDecl&>(statement);
            node.kind = IRNodeKind::Tool;
            node.name = tool.name;
            node.resultType = {TypeKind::Unknown};
            node.attributes.push_back({"parameters", std::to_string(tool.parameters.size())});
            node.attributes.push_back({"sink", "true"});
            values_.define(tool.name, node.id);
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(statement);
            node.kind = IRNodeKind::Call;
            node.name = let.name;
            node.resultType = let.type;
            node.label = labelOf(let.name, scope);
            if (let.call) {
                if (const int* prompt = values_.find(let.call->promptName)) {
                    addDependency(node.dependencies, *prompt);
                }
                if (const int* model = values_.find(let.call->modelName)) {
                    addDependency(node.dependencies, *model);
                }
                for (const auto& argument : let.call->arguments) {
                    if (argument) {
                        addExpressionDependency(*argument, node.dependencies);
                    }
                }
                node.attributes.push_back({"prompt", let.call->promptName});
                node.attributes.push_back({"model", let.call->modelName});
                const auto site = semantic_.callSites.find(let.call.get());
                if (site != semantic_.callSites.end()) {
                    node.attributes.push_back({"out_tokens", std::to_string(site->second.modelMaxTokens)});
                    node.attributes.push_back(
                        {"in_tokens", std::to_string(addTokens(site->second.promptTemplateTokens,
                                                               site->second.argumentTokens))});
                }
            }
            values_.define(let.name, node.id);
            break;
        }
        case StmtKind::Require: {
            const auto& requirement = static_cast<const RequireStmt&>(statement);
            node.kind = IRNodeKind::Requirement;
            node.name = "tokens(" + requirement.subjectName + ")";
            node.resultType = {TypeKind::Boolean};
            if (const int* subject = values_.find(requirement.subjectName)) {
                addDependency(node.dependencies, *subject);
            }
            node.attributes.push_back({"operator", comparisonOpName(requirement.op)});
            node.attributes.push_back({"limit", std::to_string(requirement.limit)});
            node.attributes.push_back({"discharged", "static"});
            break;
        }
        case StmtKind::Emit: {
            const auto& emit = static_cast<const EmitStmt&>(statement);
            node.kind = IRNodeKind::Emit;
            node.name = emit.toolName;
            node.resultType = {TypeKind::Unknown};
            if (const int* tool = values_.find(emit.toolName)) {
                addDependency(node.dependencies, *tool);
            }
            for (const auto& argument : emit.arguments) {
                if (argument) {
                    addExpressionDependency(*argument, node.dependencies);
                }
            }
            node.attributes.push_back({"arguments", std::to_string(emit.arguments.size())});
            node.attributes.push_back({"effect", "external"});
            break;
        }
        case StmtKind::Reclassify: {
            const auto& reclassify = static_cast<const ReclassifyStmt&>(statement);
            node.kind = IRNodeKind::Reclassify;
            node.name = reclassify.name;
            node.resultType = reclassify.type;
            node.label = labelOf(reclassify.name, scope);
            if (const int* source = values_.find(reclassify.sourceName)) {
                addDependency(node.dependencies, *source);
            }
            node.attributes.push_back({"operation", reclassify.endorsement ? "endorse" : "declassify"});
            node.attributes.push_back({"source", reclassify.sourceName});
            node.attributes.push_back({"justification", reclassify.reason});
            values_.define(reclassify.name, node.id);
            break;
        }
        case StmtKind::If: {
            const auto& branch = static_cast<const IfStmt&>(statement);
            node.kind = IRNodeKind::Branch;
            node.name = conditionToString(branch.condition);
            node.resultType = {TypeKind::Boolean};
            node.label = labelOf(branch.condition.subjectName, scope);
            if (const int* subject = values_.find(branch.condition.subjectName)) {
                addDependency(node.dependencies, *subject);
            }
            node.attributes.push_back({"guard", conditionToString(branch.condition)});
            node.attributes.push_back({"has_else", branch.hasElse ? "true" : "false"});
            workflow_.nodes.push_back(node);

            const std::string base = region + "/then@" + std::to_string(branch.location.line);
            values_.push();
            lowerBlock(branch.thenBranch, base, repeatFactor);
            values_.pop();
            if (branch.hasElse) {
                const std::string elseRegion = region + "/else@" + std::to_string(branch.location.line);
                values_.push();
                lowerBlock(branch.elseBranch, elseRegion, repeatFactor);
                values_.pop();
            }
            return;
        }
        case StmtKind::Retry: {
            const auto& retry = static_cast<const RetryStmt&>(statement);
            node.kind = IRNodeKind::Retry;
            node.name = "retry";
            node.resultType = {TypeKind::Unknown};
            node.attributes.push_back({"bound", std::to_string(retry.bound)});
            workflow_.nodes.push_back(node);

            const std::string body = region + "/retry@" + std::to_string(retry.location.line);
            values_.push();
            lowerBlock(retry.body, body, multiplyTokens(repeatFactor, retry.bound));
            values_.pop();
            return;
        }
        case StmtKind::Output: {
            const auto& output = static_cast<const OutputStmt&>(statement);
            node.kind = IRNodeKind::Output;
            node.name = output.value ? expressionToString(*output.value) : "<invalid>";
            node.resultType = {TypeKind::Unknown};
            if (output.value) {
                if (output.value->kind() == ExprKind::Identifier) {
                    const auto& identifier = static_cast<const IdentifierExpr&>(*output.value);
                    node.label = labelOf(identifier.name, scope);
                    const Symbol* symbol = semantic_.symbols.lookup(scope, identifier.name);
                    if (symbol) {
                        node.resultType = symbol->type;
                    }
                }
                addExpressionDependency(*output.value, node.dependencies);
            }
            break;
        }
    }
    workflow_.nodes.push_back(std::move(node));
}

void Lowerer::lowerBlock(const Block& statements, const std::string& region,
                         std::size_t repeatFactor) {
    for (const auto& statement : statements) {
        if (statement) {
            lowerStatement(*statement, region, repeatFactor);
        }
    }
}

}  // namespace

bool hasDependencyCycle(const WorkflowIR& workflow, std::vector<int>* cycle) {
    std::map<int, const IRNode*> nodes;
    for (const IRNode& node : workflow.nodes) {
        nodes[node.id] = &node;
    }
    std::map<int, int> state;
    std::vector<int> path;

    std::function<bool(int)> visit = [&](int identifier) {
        const auto stateFound = state.find(identifier);
        const int currentState = stateFound == state.end() ? 0 : stateFound->second;
        if (currentState == 1) {
            if (cycle) {
                const auto start = std::find(path.begin(), path.end(), identifier);
                cycle->assign(start, path.end());
                cycle->push_back(identifier);
            }
            return true;
        }
        if (currentState == 2) {
            return false;
        }
        const auto node = nodes.find(identifier);
        if (node == nodes.end()) {
            return false;
        }
        state[identifier] = 1;
        path.push_back(identifier);
        for (const int dependency : node->second->dependencies) {
            if (visit(dependency)) {
                return true;
            }
        }
        path.pop_back();
        state[identifier] = 2;
        return false;
    };

    for (const IRNode& node : workflow.nodes) {
        if (visit(node.id)) {
            return true;
        }
    }
    return false;
}

IRBuildResult IRLowerer::lower(const Program& program, const SemanticResult& semantic) const {
    IRBuildResult result;
    if (!semantic.success()) {
        result.diagnostics.error("I001", {}, "IR lowering requires a semantically valid program");
        return result;
    }

    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        const auto scopeFound = semantic.workflowScopes.find(workflow.name);
        if (scopeFound == semantic.workflowScopes.end()) {
            result.diagnostics.error("I001", workflow.location,
                                     "missing symbol-table scope for workflow '" + workflow.name + "'");
            continue;
        }
        WorkflowIR lowered;
        lowered.workflowName = workflow.name;

        Lowerer lowerer(semantic, lowered);
        lowerer.scope = scopeFound->second;
        lowerer.values().push();
        lowerer.lowerBlock(workflow.statements, "root", 1);
        lowerer.values().pop();

        std::vector<int> cycle;
        if (hasDependencyCycle(lowered, &cycle)) {
            std::ostringstream message;
            message << "dependency cycle detected in lowered workflow '" << workflow.name << "': ";
            for (std::size_t index = 0; index < cycle.size(); ++index) {
                if (index != 0) {
                    message << " -> ";
                }
                message << cycle[index];
            }
            result.diagnostics.error("E250", workflow.location, message.str());
        }
        result.program.workflows.push_back(std::move(lowered));
    }
    return result;
}

std::string printIR(const ProgramIR& program) {
    std::ostringstream out;
    for (const WorkflowIR& workflow : program.workflows) {
        out << "Workflow " << workflow.workflowName << " IR\n";
        for (const IRNode& node : workflow.nodes) {
            out << "  [" << node.id << "] " << irNodeKindName(node.kind) << ' ' << node.name;
            if (node.resultType.kind != TypeKind::Unknown) {
                out << " : " << typeName(node.resultType);
            }
            out << " deps=[";
            for (std::size_t index = 0; index < node.dependencies.size(); ++index) {
                if (index != 0) {
                    out << ", ";
                }
                out << node.dependencies[index];
            }
            out << ']';
            out << " label=" << labelName(node.label);
            if (node.region != "root") {
                out << " region=" << node.region;
            }
            if (node.repeatFactor != 1) {
                out << " repeat=" << node.repeatFactor;
            }
            for (const auto& attribute : node.attributes) {
                out << ' ' << attribute.first << '=' << attribute.second;
            }
            out << '\n';
        }
    }
    return out.str();
}

std::string printIRJson(const ProgramIR& program) {
    std::ostringstream out;
    out << "{\n  \"workflows\": [\n";
    for (std::size_t workflowIndex = 0; workflowIndex < program.workflows.size(); ++workflowIndex) {
        const WorkflowIR& workflow = program.workflows[workflowIndex];
        out << "    {\n      \"name\": \"" << jsonEscape(workflow.workflowName)
            << "\",\n      \"nodes\": [\n";
        for (std::size_t nodeIndex = 0; nodeIndex < workflow.nodes.size(); ++nodeIndex) {
            const IRNode& node = workflow.nodes[nodeIndex];
            out << "        {\"id\": " << node.id << ", \"kind\": \"" << irNodeKindName(node.kind)
                << "\", \"name\": \"" << jsonEscape(node.name) << "\", \"type\": \""
                << typeName(node.resultType) << "\", \"label\": \"" << labelName(node.label)
                << "\", \"region\": \"" << jsonEscape(node.region) << "\", \"repeat\": "
                << node.repeatFactor << ", \"dependencies\": [";
            for (std::size_t dependencyIndex = 0; dependencyIndex < node.dependencies.size();
                 ++dependencyIndex) {
                if (dependencyIndex != 0) {
                    out << ", ";
                }
                out << node.dependencies[dependencyIndex];
            }
            out << "], \"attributes\": {";
            for (std::size_t attributeIndex = 0; attributeIndex < node.attributes.size();
                 ++attributeIndex) {
                if (attributeIndex != 0) {
                    out << ", ";
                }
                out << "\"" << jsonEscape(node.attributes[attributeIndex].first) << "\": \""
                    << jsonEscape(node.attributes[attributeIndex].second) << "\"";
            }
            out << "}}" << (nodeIndex + 1 == workflow.nodes.size() ? "" : ",") << '\n';
        }
        out << "      ]\n    }" << (workflowIndex + 1 == program.workflows.size() ? "" : ",") << '\n';
    }
    out << "  ]\n}\n";
    return out.str();
}

}  // namespace orchlang
