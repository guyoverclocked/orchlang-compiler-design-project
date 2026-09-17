#pragma once

#include "source_location.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace orchlang {

enum class TypeKind { Text, Integer, Decimal, Boolean, Json, Unknown };

struct Type {
    TypeKind kind{TypeKind::Unknown};

    bool operator==(const Type& other) const { return kind == other.kind; }
    bool operator!=(const Type& other) const { return !(*this == other); }
};

std::string typeName(Type type);

struct Parameter {
    std::string name;
    Type type;
    SourceLocation location;
};

enum class ExprKind { Identifier, StringLiteral, IntegerLiteral, DecimalLiteral, BooleanLiteral, Call };

struct Expr {
    explicit Expr(SourceLocation source) : location(std::move(source)) {}
    virtual ~Expr() = default;
    virtual ExprKind kind() const = 0;

    SourceLocation location;
};

struct IdentifierExpr final : Expr {
    IdentifierExpr(std::string value, SourceLocation source)
        : Expr(std::move(source)), name(std::move(value)) {}
    ExprKind kind() const override { return ExprKind::Identifier; }

    std::string name;
};

struct StringLiteralExpr final : Expr {
    StringLiteralExpr(std::string value, SourceLocation source)
        : Expr(std::move(source)), value(std::move(value)) {}
    ExprKind kind() const override { return ExprKind::StringLiteral; }

    std::string value;
};

struct IntegerLiteralExpr final : Expr {
    IntegerLiteralExpr(std::string value, SourceLocation source)
        : Expr(std::move(source)), value(std::move(value)) {}
    ExprKind kind() const override { return ExprKind::IntegerLiteral; }

    std::string value;
};

struct DecimalLiteralExpr final : Expr {
    DecimalLiteralExpr(std::string value, SourceLocation source)
        : Expr(std::move(source)), value(std::move(value)) {}
    ExprKind kind() const override { return ExprKind::DecimalLiteral; }

    std::string value;
};

struct BooleanLiteralExpr final : Expr {
    BooleanLiteralExpr(std::string value, SourceLocation source)
        : Expr(std::move(source)), value(std::move(value)) {}
    ExprKind kind() const override { return ExprKind::BooleanLiteral; }

    std::string value;
};

struct CallExpr final : Expr {
    CallExpr(std::string prompt, std::vector<std::unique_ptr<Expr>> callArguments,
             std::string model, SourceLocation source)
        : Expr(std::move(source)), promptName(std::move(prompt)), arguments(std::move(callArguments)),
          modelName(std::move(model)) {}
    ExprKind kind() const override { return ExprKind::Call; }

    std::string promptName;
    std::vector<std::unique_ptr<Expr>> arguments;
    std::string modelName;
};

enum class ComparisonOp { Less, LessEqual, Greater, GreaterEqual, Equal, NotEqual };
std::string comparisonOpName(ComparisonOp op);

enum class StmtKind { Input, Secret, Model, Prompt, Let, Require, Output };

struct Stmt {
    explicit Stmt(SourceLocation source) : location(std::move(source)) {}
    virtual ~Stmt() = default;
    virtual StmtKind kind() const = 0;

    SourceLocation location;
};

struct InputDecl final : Stmt {
    InputDecl(std::string declaredName, Type declaredType, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), type(declaredType) {}
    StmtKind kind() const override { return StmtKind::Input; }

    std::string name;
    Type type;
};

struct SecretDecl final : Stmt {
    SecretDecl(std::string declaredName, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)) {}
    StmtKind kind() const override { return StmtKind::Secret; }

    std::string name;
};

struct ModelDecl final : Stmt {
    ModelDecl(std::string declaredName, std::string declaredProvider, std::string declaredModelName,
              std::size_t declaredMaxTokens, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), provider(std::move(declaredProvider)),
          modelName(std::move(declaredModelName)), maxTokens(declaredMaxTokens) {}
    StmtKind kind() const override { return StmtKind::Model; }

    std::string name;
    std::string provider;
    std::string modelName;
    std::size_t maxTokens{0};
};

struct PromptDecl final : Stmt {
    PromptDecl(std::string declaredName, std::vector<Parameter> declaredParameters,
               Type declaredReturnType, std::string declaredTemplate, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), parameters(std::move(declaredParameters)),
          returnType(declaredReturnType), templateText(std::move(declaredTemplate)) {}
    StmtKind kind() const override { return StmtKind::Prompt; }

    std::string name;
    std::vector<Parameter> parameters;
    Type returnType;
    std::string templateText;
};

struct LetStmt final : Stmt {
    LetStmt(std::string declaredName, Type declaredType, std::unique_ptr<CallExpr> declaredCall,
            SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), type(declaredType),
          call(std::move(declaredCall)) {}
    StmtKind kind() const override { return StmtKind::Let; }

    std::string name;
    Type type;
    std::unique_ptr<CallExpr> call;
};

struct RequireStmt final : Stmt {
    RequireStmt(std::string subject, ComparisonOp comparison, std::size_t tokenLimit,
                SourceLocation source)
        : Stmt(std::move(source)), subjectName(std::move(subject)), op(comparison), limit(tokenLimit) {}
    StmtKind kind() const override { return StmtKind::Require; }

    std::string subjectName;
    ComparisonOp op{ComparisonOp::LessEqual};
    std::size_t limit{0};
};

struct OutputStmt final : Stmt {
    OutputStmt(std::unique_ptr<Expr> outputValue, SourceLocation source)
        : Stmt(std::move(source)), value(std::move(outputValue)) {}
    StmtKind kind() const override { return StmtKind::Output; }

    std::unique_ptr<Expr> value;
};

struct WorkflowDecl {
    WorkflowDecl(std::string declaredName, std::size_t declaredBudget, SourceLocation source)
        : name(std::move(declaredName)), budget(declaredBudget), location(std::move(source)) {}

    std::string name;
    std::size_t budget{0};
    SourceLocation location;
    std::vector<std::unique_ptr<Stmt>> statements;
};

struct Program {
    std::vector<std::unique_ptr<WorkflowDecl>> workflows;
};

std::string expressionToString(const Expr& expression);
std::string printAst(const Program& program);

}  // namespace orchlang
