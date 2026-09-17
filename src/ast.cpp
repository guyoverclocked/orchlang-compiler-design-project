#include "ast.hpp"

#include <sstream>

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

void printStatement(std::ostringstream& out, const Stmt& statement) {
    switch (statement.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(statement);
            out << "  Input " << input.name << " : " << typeName(input.type) << '\n';
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(statement);
            out << "  Secret " << secret.name << '\n';
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(statement);
            out << "  Model " << model.name << " provider=" << model.provider
                << " name=" << model.modelName << " max_tokens=" << model.maxTokens << '\n';
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(statement);
            out << "  Prompt " << prompt.name << '(';
            for (std::size_t i = 0; i < prompt.parameters.size(); ++i) {
                if (i != 0) {
                    out << ", ";
                }
                out << prompt.parameters[i].name << ':' << typeName(prompt.parameters[i].type);
            }
            out << ") -> " << typeName(prompt.returnType) << '\n';
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(statement);
            out << "  Let " << let.name << " : " << typeName(let.type) << '\n';
            if (let.call) {
                out << "    Call " << let.call->promptName << '(';
                for (std::size_t i = 0; i < let.call->arguments.size(); ++i) {
                    if (i != 0) {
                        out << ", ";
                    }
                    out << expressionToString(*let.call->arguments[i]);
                }
                out << ") using " << let.call->modelName << '\n';
            }
            break;
        }
        case StmtKind::Require: {
            const auto& requirement = static_cast<const RequireStmt&>(statement);
            out << "  Require tokens(" << requirement.subjectName << ") "
                << comparisonOpName(requirement.op) << ' ' << requirement.limit << '\n';
            break;
        }
        case StmtKind::Output: {
            const auto& output = static_cast<const OutputStmt&>(statement);
            out << "  Output " << (output.value ? expressionToString(*output.value) : "<invalid>") << '\n';
            break;
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
        for (const auto& statement : workflow->statements) {
            if (statement) {
                printStatement(out, *statement);
            }
        }
    }
    return out.str();
}

}  // namespace orchlang
