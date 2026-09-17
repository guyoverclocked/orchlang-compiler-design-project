#include "semantic_analyzer.hpp"

#include <algorithm>
#include <cctype>
#include <limits>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace orchlang {

namespace {

bool isPlaceholderName(const std::string& name) {
    if (name.empty()) {
        return false;
    }
    const unsigned char first = static_cast<unsigned char>(name.front());
    if (std::isalpha(first) == 0 && name.front() != '_') {
        return false;
    }
    for (const char character : name) {
        const unsigned char value = static_cast<unsigned char>(character);
        if (std::isalnum(value) == 0 && character != '_') {
            return false;
        }
    }
    return true;
}

void duplicateDeclaration(SemanticResult& result, const Symbol& existing, const Symbol& duplicate) {
    result.diagnostics.error(
        "E201", duplicate.location,
        "duplicate declaration '" + duplicate.name + "'; first declared at " + formatLocation(existing.location));
}

bool insertWithDuplicateDiagnostic(SemanticResult& result, std::size_t scope, Symbol symbol) {
    const Symbol* existing = nullptr;
    const Symbol candidate = symbol;
    if (result.symbols.insert(scope, std::move(symbol), &existing)) {
        return true;
    }
    if (existing) {
        duplicateDeclaration(result, *existing, candidate);
    }
    return false;
}

Type inferExpression(const Expr& expression, SemanticResult& result, std::size_t scope,
                     bool promptArgument) {
    switch (expression.kind()) {
        case ExprKind::Identifier: {
            const auto& identifier = static_cast<const IdentifierExpr&>(expression);
            const Symbol* symbol = result.symbols.lookup(scope, identifier.name);
            if (!symbol) {
                result.diagnostics.error("E202", expression.location,
                                         "use of undeclared identifier '" + identifier.name + "'");
                return {TypeKind::Unknown};
            }
            if (promptArgument && symbol->kind == SymbolKind::Secret) {
                result.diagnostics.error("E230", expression.location,
                                         "secret '" + identifier.name + "' cannot be passed to a prompt call");
            }
            return symbol->type;
        }
        case ExprKind::StringLiteral: return {TypeKind::Text};
        case ExprKind::IntegerLiteral: return {TypeKind::Integer};
        case ExprKind::DecimalLiteral: return {TypeKind::Decimal};
        case ExprKind::BooleanLiteral: return {TypeKind::Boolean};
        case ExprKind::Call:
            // Calls are only syntactically accepted as the right side of a let statement.
            return {TypeKind::Unknown};
    }
    return {TypeKind::Unknown};
}

bool isDirectSecret(const Expr& expression, const SemanticResult& result, std::size_t scope) {
    if (expression.kind() != ExprKind::Identifier) {
        return false;
    }
    const auto& identifier = static_cast<const IdentifierExpr&>(expression);
    const Symbol* symbol = result.symbols.lookup(scope, identifier.name);
    return symbol && symbol->kind == SymbolKind::Secret;
}

void checkPlaceholders(const PromptDecl& prompt, SemanticResult& result) {
    std::set<std::string> parameterNames;
    for (const Parameter& parameter : prompt.parameters) {
        parameterNames.insert(parameter.name);
    }
    std::set<std::string> seen;
    const std::string& text = prompt.templateText;
    for (std::size_t index = 0; index < text.size(); ++index) {
        if (text[index] == '}') {
            result.diagnostics.error("E222", prompt.location,
                                     "unexpected '}' in prompt template for '" + prompt.name + "'");
            continue;
        }
        if (text[index] != '{') {
            continue;
        }
        const std::size_t closing = text.find('}', index + 1);
        if (closing == std::string::npos) {
            result.diagnostics.error("E222", prompt.location,
                                     "unterminated placeholder in prompt template for '" + prompt.name + "'");
            break;
        }
        const std::string placeholder = text.substr(index + 1, closing - index - 1);
        if (!isPlaceholderName(placeholder)) {
            result.diagnostics.error("E222", prompt.location,
                                     "malformed placeholder '{" + placeholder + "}' in prompt '" + prompt.name + "'");
        } else if (parameterNames.find(placeholder) == parameterNames.end()) {
            result.diagnostics.error("E222", prompt.location,
                                     "placeholder '{" + placeholder + "}' does not match a declared parameter of prompt '" + prompt.name + "'");
        } else if (!seen.insert(placeholder).second) {
            result.diagnostics.error("E222", prompt.location,
                                     "placeholder '{" + placeholder + "}' is duplicated in prompt '" + prompt.name + "'");
        }
        index = closing;
    }
    for (const Parameter& parameter : prompt.parameters) {
        if (seen.find(parameter.name) == seen.end()) {
            result.diagnostics.error("E222", parameter.location,
                                     "prompt parameter '" + parameter.name + "' has no matching placeholder");
        }
    }
}

Type checkCall(const CallExpr& call, SemanticResult& result, std::size_t scope,
               std::size_t& declaredTokenTotal) {
    const Symbol* prompt = result.symbols.lookupLocal(scope, call.promptName);
    const Symbol* model = result.symbols.lookupLocal(scope, call.modelName);

    std::vector<Type> argumentTypes;
    argumentTypes.reserve(call.arguments.size());
    for (const auto& argument : call.arguments) {
        if (argument) {
            argumentTypes.push_back(inferExpression(*argument, result, scope, true));
        } else {
            argumentTypes.push_back({TypeKind::Unknown});
        }
    }

    if (!prompt || prompt->kind != SymbolKind::Prompt || !prompt->prompt) {
        result.diagnostics.error("E220", call.location,
                                 "unknown prompt '" + call.promptName + "' called from let statement");
    } else {
        const PromptSignature& signature = *prompt->prompt;
        if (call.arguments.size() != signature.parameters.size()) {
            std::ostringstream message;
            message << "prompt '" << call.promptName << "' expects " << signature.parameters.size()
                    << " argument(s), but " << call.arguments.size() << " were supplied";
            result.diagnostics.error("E221", call.location, message.str());
        }
        const std::size_t checked = std::min(call.arguments.size(), signature.parameters.size());
        for (std::size_t index = 0; index < checked; ++index) {
            if (argumentTypes[index].kind != TypeKind::Unknown &&
                argumentTypes[index] != signature.parameters[index].type) {
                result.diagnostics.error(
                    "E223", call.arguments[index]->location,
                    "argument " + std::to_string(index + 1) + " of prompt '" + call.promptName +
                        "' has type " + typeName(argumentTypes[index]) + "; expected " +
                        typeName(signature.parameters[index].type));
            }
        }
    }

    if (!model || model->kind != SymbolKind::Model || !model->model) {
        result.diagnostics.error("E241", call.location,
                                 "unknown model '" + call.modelName + "' in using clause");
    } else {
        const std::size_t maxTokens = model->model->maxTokens;
        if (declaredTokenTotal > std::numeric_limits<std::size_t>::max() - maxTokens) {
            declaredTokenTotal = std::numeric_limits<std::size_t>::max();
        } else {
            declaredTokenTotal += maxTokens;
        }
    }

    return (prompt && prompt->kind == SymbolKind::Prompt && prompt->prompt)
               ? prompt->prompt->returnType
               : Type{TypeKind::Unknown};
}

}  // namespace

SemanticResult SemanticAnalyzer::analyze(const Program& program) const {
    SemanticResult result;
    std::set<std::string> workflowNames;

    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        if (!workflowNames.insert(workflow.name).second) {
            result.diagnostics.error("E201", workflow.location,
                                     "duplicate declaration of workflow '" + workflow.name + "'");
        }

        const std::size_t workflowScope = result.symbols.createScope("workflow:" + workflow.name);
        result.workflowScopes[workflow.name] = workflowScope;
        std::size_t declaredTokenTotal = 0;
        std::size_t outputCount = 0;

        for (const auto& statementPointer : workflow.statements) {
            if (!statementPointer) {
                continue;
            }
            const Stmt& statement = *statementPointer;
            switch (statement.kind()) {
                case StmtKind::Input: {
                    const auto& input = static_cast<const InputDecl&>(statement);
                    insertWithDuplicateDiagnostic(result, workflowScope,
                                                  {input.name, SymbolKind::Input, input.type, "", input.location,
                                                   std::nullopt, std::nullopt});
                    break;
                }
                case StmtKind::Secret: {
                    const auto& secret = static_cast<const SecretDecl&>(statement);
                    insertWithDuplicateDiagnostic(result, workflowScope,
                                                  {secret.name, SymbolKind::Secret, {TypeKind::Unknown}, "", secret.location,
                                                   std::nullopt, std::nullopt});
                    break;
                }
                case StmtKind::Model: {
                    const auto& model = static_cast<const ModelDecl&>(statement);
                    ModelMetadata metadata{model.provider, model.modelName, model.maxTokens};
                    insertWithDuplicateDiagnostic(result, workflowScope,
                                                  {model.name, SymbolKind::Model, {TypeKind::Unknown}, "", model.location,
                                                   metadata, std::nullopt});
                    break;
                }
                case StmtKind::Prompt: {
                    const auto& prompt = static_cast<const PromptDecl&>(statement);
                    PromptSignature signature;
                    signature.returnType = prompt.returnType;
                    for (const Parameter& parameter : prompt.parameters) {
                        signature.parameters.push_back({parameter.name, parameter.type});
                    }
                    insertWithDuplicateDiagnostic(result, workflowScope,
                                                  {prompt.name, SymbolKind::Prompt, prompt.returnType, "", prompt.location,
                                                   std::nullopt, signature});

                    const std::size_t parameterScope = result.symbols.createScope(
                        "workflow:" + workflow.name + "::prompt:" + prompt.name, workflowScope);
                    for (const Parameter& parameter : prompt.parameters) {
                        insertWithDuplicateDiagnostic(result, parameterScope,
                                                      {parameter.name, SymbolKind::PromptParameter, parameter.type, "",
                                                       parameter.location, std::nullopt, std::nullopt});
                    }
                    checkPlaceholders(prompt, result);
                    break;
                }
                case StmtKind::Let: {
                    const auto& let = static_cast<const LetStmt&>(statement);
                    Type callType{TypeKind::Unknown};
                    if (let.call) {
                        callType = checkCall(*let.call, result, workflowScope, declaredTokenTotal);
                    }
                    if (callType.kind != TypeKind::Unknown && callType != let.type) {
                        result.diagnostics.error("E210", let.location,
                                                 "cannot assign " + typeName(callType) + " result to '" + let.name +
                                                     "' declared as " + typeName(let.type));
                    }
                    insertWithDuplicateDiagnostic(result, workflowScope,
                                                  {let.name, SymbolKind::LocalResult, let.type, "", let.location,
                                                   std::nullopt, std::nullopt});
                    break;
                }
                case StmtKind::Require: {
                    const auto& requirement = static_cast<const RequireStmt&>(statement);
                    if (!result.symbols.lookup(workflowScope, requirement.subjectName)) {
                        result.diagnostics.error("E202", requirement.location,
                                                 "use of undeclared identifier '" + requirement.subjectName + "'");
                    }
                    break;
                }
                case StmtKind::Output: {
                    const auto& output = static_cast<const OutputStmt&>(statement);
                    ++outputCount;
                    if (output.value) {
                        inferExpression(*output.value, result, workflowScope, false);
                        if (isDirectSecret(*output.value, result, workflowScope)) {
                            const auto& identifier = static_cast<const IdentifierExpr&>(*output.value);
                            result.diagnostics.error("E230", output.value->location,
                                                     "secret '" + identifier.name + "' cannot be exposed as workflow output");
                        }
                    }
                    break;
                }
            }
        }

        result.declaredTokenTotals[workflow.name] = declaredTokenTotal;
        if (declaredTokenTotal > workflow.budget) {
            result.diagnostics.error("E260", workflow.location,
                                     "declared maximum token use " + std::to_string(declaredTokenTotal) +
                                         " exceeds workflow budget " + std::to_string(workflow.budget));
        }
        if (outputCount == 0) {
            result.diagnostics.error("E270", workflow.location,
                                     "workflow '" + workflow.name + "' has no output declaration");
        }
        if (outputCount > 1) {
            result.diagnostics.error("E271", workflow.location,
                                     "workflow '" + workflow.name + "' has multiple output declarations");
        }
    }
    return result;
}

}  // namespace orchlang
