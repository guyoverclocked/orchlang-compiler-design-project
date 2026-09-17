#include "ir.hpp"

#include <algorithm>
#include <functional>
#include <map>
#include <sstream>
#include <string>

namespace orchlang {

std::string irNodeKindName(IRNodeKind kind) {
    switch (kind) {
        case IRNodeKind::Input: return "Input";
        case IRNodeKind::Secret: return "Secret";
        case IRNodeKind::Model: return "Model";
        case IRNodeKind::Prompt: return "Prompt";
        case IRNodeKind::Call: return "Call";
        case IRNodeKind::Requirement: return "Requirement";
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

void addExpressionDependency(const Expr& expression, const std::map<std::string, int>& values,
                             std::vector<int>& dependencies) {
    if (expression.kind() != ExprKind::Identifier) {
        return;
    }
    const auto& identifier = static_cast<const IdentifierExpr&>(expression);
    const auto found = values.find(identifier.name);
    if (found != values.end()) {
        addDependency(dependencies, found->second);
    }
}

Type expressionType(const Expr& expression, const SymbolTable& symbols, std::size_t scope) {
    switch (expression.kind()) {
        case ExprKind::Identifier: {
            const auto& identifier = static_cast<const IdentifierExpr&>(expression);
            const Symbol* symbol = symbols.lookup(scope, identifier.name);
            return symbol ? symbol->type : Type{TypeKind::Unknown};
        }
        case ExprKind::StringLiteral: return {TypeKind::Text};
        case ExprKind::IntegerLiteral: return {TypeKind::Integer};
        case ExprKind::DecimalLiteral: return {TypeKind::Decimal};
        case ExprKind::BooleanLiteral: return {TypeKind::Boolean};
        case ExprKind::Call: return {TypeKind::Unknown};
    }
    return {TypeKind::Unknown};
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
        const std::size_t scope = scopeFound->second;
        WorkflowIR lowered;
        lowered.workflowName = workflow.name;
        std::map<std::string, int> values;
        int nextId = 1;

        for (const auto& statementPointer : workflow.statements) {
            if (!statementPointer) {
                continue;
            }
            const Stmt& statement = *statementPointer;
            IRNode node;
            node.id = nextId++;
            node.location = statement.location;
            switch (statement.kind()) {
                case StmtKind::Input: {
                    const auto& input = static_cast<const InputDecl&>(statement);
                    node.kind = IRNodeKind::Input;
                    node.name = input.name;
                    node.resultType = input.type;
                    values[input.name] = node.id;
                    break;
                }
                case StmtKind::Secret: {
                    const auto& secret = static_cast<const SecretDecl&>(statement);
                    node.kind = IRNodeKind::Secret;
                    node.name = secret.name;
                    node.resultType = {TypeKind::Unknown};
                    values[secret.name] = node.id;
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
                    values[model.name] = node.id;
                    break;
                }
                case StmtKind::Prompt: {
                    const auto& prompt = static_cast<const PromptDecl&>(statement);
                    node.kind = IRNodeKind::Prompt;
                    node.name = prompt.name;
                    node.resultType = prompt.returnType;
                    node.attributes.push_back({"parameters", std::to_string(prompt.parameters.size())});
                    values[prompt.name] = node.id;
                    break;
                }
                case StmtKind::Let: {
                    const auto& let = static_cast<const LetStmt&>(statement);
                    node.kind = IRNodeKind::Call;
                    node.name = let.name;
                    node.resultType = let.type;
                    if (let.call) {
                        const auto prompt = values.find(let.call->promptName);
                        const auto model = values.find(let.call->modelName);
                        if (prompt != values.end()) addDependency(node.dependencies, prompt->second);
                        if (model != values.end()) addDependency(node.dependencies, model->second);
                        for (const auto& argument : let.call->arguments) {
                            if (argument) addExpressionDependency(*argument, values, node.dependencies);
                        }
                        node.attributes.push_back({"prompt", let.call->promptName});
                        node.attributes.push_back({"model", let.call->modelName});
                        const Symbol* modelSymbol = semantic.symbols.lookupLocal(scope, let.call->modelName);
                        if (modelSymbol && modelSymbol->model) {
                            node.attributes.push_back({"max_tokens", std::to_string(modelSymbol->model->maxTokens)});
                        }
                    }
                    values[let.name] = node.id;
                    break;
                }
                case StmtKind::Require: {
                    const auto& requirement = static_cast<const RequireStmt&>(statement);
                    node.kind = IRNodeKind::Requirement;
                    node.name = "tokens(" + requirement.subjectName + ")";
                    node.resultType = {TypeKind::Boolean};
                    const auto subject = values.find(requirement.subjectName);
                    if (subject != values.end()) addDependency(node.dependencies, subject->second);
                    node.attributes.push_back({"operator", comparisonOpName(requirement.op)});
                    node.attributes.push_back({"limit", std::to_string(requirement.limit)});
                    break;
                }
                case StmtKind::Output: {
                    const auto& output = static_cast<const OutputStmt&>(statement);
                    node.kind = IRNodeKind::Output;
                    node.name = output.value ? expressionToString(*output.value) : "<invalid>";
                    node.resultType = output.value ? expressionType(*output.value, semantic.symbols, scope)
                                                   : Type{TypeKind::Unknown};
                    if (output.value) addExpressionDependency(*output.value, values, node.dependencies);
                    break;
                }
            }
            lowered.nodes.push_back(std::move(node));
        }

        std::vector<int> cycle;
        if (hasDependencyCycle(lowered, &cycle)) {
            std::ostringstream message;
            message << "dependency cycle detected in lowered workflow '" << workflow.name << "': ";
            for (std::size_t index = 0; index < cycle.size(); ++index) {
                if (index != 0) message << " -> ";
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
                if (index != 0) out << ", ";
                out << node.dependencies[index];
            }
            out << ']';
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
                << typeName(node.resultType) << "\", \"dependencies\": [";
            for (std::size_t dependencyIndex = 0; dependencyIndex < node.dependencies.size(); ++dependencyIndex) {
                if (dependencyIndex != 0) out << ", ";
                out << node.dependencies[dependencyIndex];
            }
            out << "], \"attributes\": {";
            for (std::size_t attributeIndex = 0; attributeIndex < node.attributes.size(); ++attributeIndex) {
                if (attributeIndex != 0) out << ", ";
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
