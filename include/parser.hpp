#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "token.hpp"

#include <memory>
#include <vector>

namespace orchlang {

struct ParseResult {
    Program program;
    DiagnosticBag diagnostics;
};

class Parser {
public:
    explicit Parser(const std::vector<Token>& tokens);
    ParseResult parse();

private:
    const Token& current() const;
    const Token& previous() const;
    bool atEnd() const;
    bool check(TokenKind kind) const;
    bool match(TokenKind kind);
    const Token* consume(TokenKind kind, const std::string& expectation);
    void advance();
    void report(const Token& token, const std::string& expectation);
    void recoverStatement();

    std::unique_ptr<WorkflowDecl> parseWorkflow();
    std::unique_ptr<Stmt> parseStatement();
    std::unique_ptr<InputDecl> parseInput();
    std::unique_ptr<SecretDecl> parseSecret();
    std::unique_ptr<ModelDecl> parseModel();
    std::unique_ptr<PromptDecl> parsePrompt();
    std::unique_ptr<LetStmt> parseLet();
    std::unique_ptr<RequireStmt> parseRequire();
    std::unique_ptr<OutputStmt> parseOutput();
    std::unique_ptr<CallExpr> parseCall();
    std::unique_ptr<Expr> parseExpression();
    bool parseType(Type& type);
    bool parseUnsigned(const Token& token, std::size_t& value);
    ComparisonOp parseComparison();

    const std::vector<Token>& tokens_;
    std::size_t currentIndex_{0};
    DiagnosticBag diagnostics_;
};

}  // namespace orchlang
