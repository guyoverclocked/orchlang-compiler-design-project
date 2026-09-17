#include "ast.hpp"

#include <sstream>
#include <string>

namespace orchlang {

std::string typeName(Type type) {
    switch (type.kind) {
        case TypeKind::Text: return "text";
        case TypeKind::Integer: return "integer";
        case TypeKind::Decimal: return "decimal";
        case TypeKind::Boolean: return "boolean";
        case TypeKind::Json: return "json";
        case TypeKind::Unknown: return "<unknown>";
    }
    return "<unknown>";
}

std::string comparisonOpName(ComparisonOp op) {
    switch (op) {
        case ComparisonOp::Less: return "<";
        case ComparisonOp::LessEqual: return "<=";
        case ComparisonOp::Greater: return ">";
        case ComparisonOp::GreaterEqual: return ">=";
        case ComparisonOp::Equal: return "==";
        case ComparisonOp::NotEqual: return "!=";
    }
    return "?";
}

std::string labelName(const Label& label) {
    const std::string confidentiality = label.isSecret() ? "secret" : "public";
    const std::string integrity = label.isUntrusted() ? "untrusted" : "trusted";
    return confidentiality + "/" + integrity;
}

std::string conditionToString(const Condition& condition) {
    if (condition.kind == ConditionKind::Flag) {
        return condition.subjectName;
    }
    return "tokens(" + condition.subjectName + ") " + comparisonOpName(condition.op) + " " +
           std::to_string(condition.limit);
}

std::string expressionToString(const Expr& expression) {
    switch (expression.kind()) {
        case ExprKind::Identifier:
            return static_cast<const IdentifierExpr&>(expression).name;
        case ExprKind::StringLiteral:
            return "\"" + static_cast<const StringLiteralExpr&>(expression).value + "\"";
        case ExprKind::IntegerLiteral:
            return static_cast<const IntegerLiteralExpr&>(expression).value;
        case ExprKind::DecimalLiteral:
            return static_cast<const DecimalLiteralExpr&>(expression).value;
        case ExprKind::BooleanLiteral:
            return static_cast<const BooleanLiteralExpr&>(expression).value;
        case ExprKind::Call: {
            const auto& call = static_cast<const CallExpr&>(expression);
            std::ostringstream out;
            out << "call " << call.promptName << '(';
            for (std::size_t i = 0; i < call.arguments.size(); ++i) {
                if (i != 0) {
                    out << ", ";
                }
                out << expressionToString(*call.arguments[i]);
            }
            out << ") using " << call.modelName;
            return out.str();
        }
    }
    return "<invalid-expression>";
}

namespace {

std::string indentOf(int depth) { return std::string(static_cast<std::size_t>(depth) * 2, ' '); }

void printBlock(std::ostringstream& out, const Block& block, int depth);

void printArguments(std::ostringstream& out, const std::vector<std::unique_ptr<Expr>>& arguments) {
    for (std::size_t i = 0; i < arguments.size(); ++i) {
        if (i != 0) {
            out << ", ";
        }
        out << (arguments[i] ? expressionToString(*arguments[i]) : "<invalid>");
    }
}

void printStatement(std::ostringstream& out, const Stmt& statement, int depth) {
    const std::string pad = indentOf(depth);
    switch (statement.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(statement);
            out << pad << "Input " << input.name << " : " << typeName(input.type) << " ["
                << labelName(input.label) << "]\n";
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(statement);
            out << pad << "Secret " << secret.name << " : " << typeName(secret.type);
            if (secret.hasTokenBound) {
                out << " max_tokens=" << secret.tokenBound;
            }
            out << '\n';
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(statement);
            out << pad << "Model " << model.name << " provider=" << model.provider
                << " name=" << model.modelName << " max_tokens=" << model.maxTokens << '\n';
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(statement);
            out << pad << "Prompt " << prompt.name << '(';
            for (std::size_t i = 0; i < prompt.parameters.size(); ++i) {
                if (i != 0) {
                    out << ", ";
                }
                out << prompt.parameters[i].name << ':' << typeName(prompt.parameters[i].type);
            }
            out << ") -> " << typeName(prompt.returnType) << '\n';
            break;
        }
        case StmtKind::Tool: {
            const auto& tool = static_cast<const ToolDecl&>(statement);
            out << pad << "Tool " << tool.name << '(';
            for (std::size_t i = 0; i < tool.parameters.size(); ++i) {
                if (i != 0) {
                    out << ", ";
                }
                out << tool.parameters[i].name << ':' << typeName(tool.parameters[i].type);
            }
            out << ")\n";
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(statement);
            out << pad << "Let " << let.name << " : " << typeName(let.type) << '\n';
            if (let.call) {
                out << pad << "  Call " << let.call->promptName << '(';
                printArguments(out, let.call->arguments);
                out << ") using " << let.call->modelName << '\n';
            }
            break;
        }
        case StmtKind::Require: {
            const auto& requirement = static_cast<const RequireStmt&>(statement);
            out << pad << "Require tokens(" << requirement.subjectName << ") "
                << comparisonOpName(requirement.op) << ' ' << requirement.limit << '\n';
            break;
        }
        case StmtKind::Emit: {
            const auto& emit = static_cast<const EmitStmt&>(statement);
            out << pad << "Emit " << emit.toolName << '(';
            printArguments(out, emit.arguments);
            out << ")\n";
            break;
        }
        case StmtKind::If: {
            const auto& branch = static_cast<const IfStmt&>(statement);
            out << pad << "If " << conditionToString(branch.condition) << '\n';
            out << pad << "  Then\n";
            printBlock(out, branch.thenBranch, depth + 2);
            if (branch.hasElse) {
                out << pad << "  Else\n";
                printBlock(out, branch.elseBranch, depth + 2);
            }
            break;
        }
        case StmtKind::Retry: {
            const auto& retry = static_cast<const RetryStmt&>(statement);
            out << pad << "Retry " << retry.bound << '\n';
            printBlock(out, retry.body, depth + 1);
            break;
        }
        case StmtKind::Reclassify: {
            const auto& reclassify = static_cast<const ReclassifyStmt&>(statement);
            out << pad << (reclassify.endorsement ? "Endorse " : "Declassify ") << reclassify.sourceName
                << " as " << reclassify.name << " : " << typeName(reclassify.type) << " because \""
                << reclassify.reason << "\"\n";
            break;
        }
        case StmtKind::Output: {
            const auto& output = static_cast<const OutputStmt&>(statement);
            out << pad << "Output " << (output.value ? expressionToString(*output.value) : "<invalid>")
                << '\n';
            break;
        }
    }
}

void printBlock(std::ostringstream& out, const Block& block, int depth) {
    for (const auto& statement : block) {
        if (statement) {
            printStatement(out, *statement, depth);
        }
    }
}

}  // namespace

std::string printAst(const Program& program) {
    std::ostringstream out;
    for (const auto& workflow : program.workflows) {
        if (!workflow) {
            continue;
        }
        out << "Workflow " << workflow->name << " budget=" << workflow->budget << '\n';
        printBlock(out, workflow->statements, 1);
    }
    return out.str();
}

}  // namespace orchlang
