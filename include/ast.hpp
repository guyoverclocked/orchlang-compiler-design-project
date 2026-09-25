#pragma once

#include "label.hpp"
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

enum class StmtKind { Input, Secret, Model, Prompt, Tool, Let, Require, Output, Emit, If, Retry, Reclassify };

struct Stmt;

// A statement sequence.  Workflow bodies, branch arms, and retry bodies are all
// blocks, so the cost and label rules are defined once by structural induction.
using Block = std::vector<std::unique_ptr<Stmt>>;

struct Stmt {
    explicit Stmt(SourceLocation source) : location(std::move(source)) {}
    virtual ~Stmt() = default;
    virtual StmtKind kind() const = 0;

    SourceLocation location;
};

struct InputDecl final : Stmt {
    InputDecl(std::string declaredName, Type declaredType, Label declaredLabel, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), type(declaredType),
          label(declaredLabel) {}
    StmtKind kind() const override { return StmtKind::Input; }

    std::string name;
    Type type;
    Label label{publicTrusted()};
    // An input's length is not knowable from the source, so a workflow that
    // feeds an input to a prompt must declare an upper bound for it.  Without
    // one the input-token component of the cost bound would be unbounded, and
    // the compiler says so rather than guessing.
    bool hasTokenBound{false};
    std::size_t tokenBound{0};
    // The tokenizer a 'max_tokens' bound is counted under, if the author named
    // one.  Without it the count is in the compiler's estimate unit, which no
    // real tokenizer is obliged to respect.
    std::string tokenizer;
    // A bound in UTF-8 bytes.  Bytes are the one length unit that adds up under
    // concatenation and means the same thing to every tokenizer, so it is the
    // only kind of bound a guaranteed input-token figure can be built from.
    bool hasByteBound{false};
    std::size_t byteBound{0};
};

struct SecretDecl final : Stmt {
    SecretDecl(std::string declaredName, Type declaredType, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), type(declaredType) {}
    StmtKind kind() const override { return StmtKind::Secret; }

    std::string name;
    Type type;
    // A secret only needs a bound if it is declassified and then used, but the
    // declaration is the only place its length can be stated.
    bool hasTokenBound{false};
    std::size_t tokenBound{0};
    std::string tokenizer;
    bool hasByteBound{false};
    std::size_t byteBound{0};
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
    // Optional published price per token.  Monetary figures are derived and
    // reported; the certified safety property is stated over token counts.
    bool hasUnitPrice{false};
    double unitPrice{0.0};
    // The tokenizer this model bills input under.  Naming one lets the compiler
    // derive a guaranteed input bound from byte lengths, through that
    // tokenizer's measured contract; without one only an estimate is possible.
    std::string tokenizer;
    // Tokens the provider adds to every request around the prompt text (chat
    // roles, message delimiters).  Declared, because it is the provider's
    // format and not the program's.
    std::size_t overhead{0};
    // Responses longer than this many UTF-8 bytes are cut to it by the client
    // before the workflow sees them.  A token cap alone says almost nothing
    // about a response's length in bytes, which is what a later prompt is
    // billed on, so this is the only way to keep a chained bound tight.
    bool hasByteCap{false};
    std::size_t byteCap{0};
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

// A declared external effect.  Emitting to a tool is the only way a workflow
// can act on the outside world, so tools are the sinks the label rules guard.
struct ToolDecl final : Stmt {
    ToolDecl(std::string declaredName, std::vector<Parameter> declaredParameters, SourceLocation source)
        : Stmt(std::move(source)), name(std::move(declaredName)), parameters(std::move(declaredParameters)) {}
    StmtKind kind() const override { return StmtKind::Tool; }

    std::string name;
    std::vector<Parameter> parameters;
};

struct EmitStmt final : Stmt {
    EmitStmt(std::string tool, std::vector<std::unique_ptr<Expr>> emitArguments, SourceLocation source)
        : Stmt(std::move(source)), toolName(std::move(tool)), arguments(std::move(emitArguments)) {}
    StmtKind kind() const override { return StmtKind::Emit; }

    std::string toolName;
    std::vector<std::unique_ptr<Expr>> arguments;
};

enum class ConditionKind { TokenBound, Flag };

// The guard of an 'if'.  Both forms name an identifier, which is what the
// analysis needs: the guard's label becomes the program-counter label of the
// arms, which is how implicit flows are caught.
struct Condition {
    ConditionKind kind{ConditionKind::TokenBound};
    std::string subjectName;
    ComparisonOp op{ComparisonOp::LessEqual};
    std::size_t limit{0};
    SourceLocation location;
};

std::string conditionToString(const Condition& condition);

struct IfStmt final : Stmt {
    IfStmt(Condition guard, Block thenBlock, Block elseBlock, bool elsePresent, SourceLocation source)
        : Stmt(std::move(source)), condition(std::move(guard)), thenBranch(std::move(thenBlock)),
          elseBranch(std::move(elseBlock)), hasElse(elsePresent) {}
    StmtKind kind() const override { return StmtKind::If; }

    Condition condition;
    Block thenBranch;
    Block elseBranch;
    bool hasElse{false};
};

// Bounded repetition.  The bound is syntactic and mandatory, which is what
// keeps the cost analysis terminating and the derived bound finite.
struct RetryStmt final : Stmt {
    RetryStmt(std::size_t repetitionBound, Block repeatedBody, SourceLocation source)
        : Stmt(std::move(source)), bound(repetitionBound), body(std::move(repeatedBody)) {}
    StmtKind kind() const override { return StmtKind::Retry; }

    std::size_t bound{0};
    Block body;
};

// 'declassify' lowers confidentiality; 'endorse' raises integrity.  Both are
// the deliberate escape hatches from the lattice, and both are recorded in the
// emitted certificate so a reviewer sees every place the guarantee was relaxed.
struct ReclassifyStmt final : Stmt {
    ReclassifyStmt(bool isEndorsement, std::string source_, std::string declaredName, Type declaredType,
                   std::string justification, SourceLocation location_)
        : Stmt(std::move(location_)), endorsement(isEndorsement), sourceName(std::move(source_)),
          name(std::move(declaredName)), type(declaredType), reason(std::move(justification)) {}
    StmtKind kind() const override { return StmtKind::Reclassify; }

    bool endorsement{false};
    std::string sourceName;
    std::string name;
    Type type;
    std::string reason;
};

struct OutputStmt final : Stmt {
    OutputStmt(std::unique_ptr<Expr> outputValue, SourceLocation source)
        : Stmt(std::move(source)), value(std::move(outputValue)) {}
    StmtKind kind() const override { return StmtKind::Output; }

    std::unique_ptr<Expr> value;
};

// Who is assumed to watch the calls a workflow makes.  Each observer sees a
// function of the call transcript, and each is coarser than the one before it,
// so a workflow safe against one is safe against every observer after it.
enum class Observer {
    // Every request and response, in order: the provider's own logs, or a
    // proxy that records traffic.
    Trace,
    // Each provider's own requests, in order, but not how calls to different
    // providers interleave.
    Provider,
    // The itemised invoice: per model, input tokens, output tokens, and calls.
    Bill,
};

std::string observerName(Observer observer);

struct WorkflowDecl {
    WorkflowDecl(std::string declaredName, std::size_t declaredBudget, SourceLocation source)
        : name(std::move(declaredName)), budget(declaredBudget), location(std::move(source)) {}

    std::string name;
    std::size_t budget{0};
    SourceLocation location;
    Block statements;
    // How much the observer may learn about the secrets, in bits, per secret
    // value.  Zero, the default, demands that the observation not depend on
    // the secrets at all.
    double leakBudgetBits{0.0};
    bool hasLeakBudget{false};
    Observer observer{Observer::Trace};
};

struct Program {
    std::vector<std::unique_ptr<WorkflowDecl>> workflows;
};

std::string expressionToString(const Expr& expression);

// The text a value actually contributes when it is substituted into a prompt.
//
// This is deliberately separate from expressionToString, which renders source
// syntax for diagnostics and adds quotation marks around strings.  Substituting
// a string into a template inserts the string's *value*, not its source
// spelling, and the analysis and the runtime must agree on that down to the
// character or the certified bound does not describe the execution.  Audit
// finding 3 was exactly this disagreement.
std::string substitutedText(const Expr& expression);
std::string printAst(const Program& program);

}  // namespace orchlang
