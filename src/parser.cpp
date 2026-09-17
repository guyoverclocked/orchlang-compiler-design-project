#include "parser.hpp"

#include <limits>
#include <utility>

namespace orchlang {

namespace {

bool startsStatement(TokenKind kind) {
    return kind == TokenKind::Input || kind == TokenKind::Secret || kind == TokenKind::Model ||
           kind == TokenKind::Prompt || kind == TokenKind::Let || kind == TokenKind::Require ||
           kind == TokenKind::Output;
}

bool isComparison(TokenKind kind) {
    return kind == TokenKind::Less || kind == TokenKind::LessEqual || kind == TokenKind::Greater ||
           kind == TokenKind::GreaterEqual || kind == TokenKind::EqualEqual || kind == TokenKind::BangEqual;
}

}  // namespace

Parser::Parser(const std::vector<Token>& tokens) : tokens_(tokens) {}

const Token& Parser::current() const { return tokens_[currentIndex_]; }

const Token& Parser::previous() const {
    return tokens_[currentIndex_ == 0 ? 0 : currentIndex_ - 1];
}

bool Parser::atEnd() const { return current().kind == TokenKind::EndOfFile; }

bool Parser::check(TokenKind kind) const { return current().kind == kind; }

bool Parser::match(TokenKind kind) {
    if (!check(kind)) {
        return false;
    }
    advance();
    return true;
}

const Token* Parser::consume(TokenKind kind, const std::string& expectation) {
    if (!check(kind)) {
        report(current(), expectation);
        return nullptr;
    }
    advance();
    return &previous();
}

void Parser::advance() {
    if (!atEnd()) {
        ++currentIndex_;
    }
}

void Parser::report(const Token& token, const std::string& expectation) {
    diagnostics_.error("P001", token.location, "expected " + expectation + ", found '" +
                                              (token.lexeme.empty() ? std::string("<eof>") : token.lexeme) + "'");
}

void Parser::recoverStatement() {
    while (!atEnd()) {
        if (check(TokenKind::RightBrace) || startsStatement(current().kind) ||
            check(TokenKind::Workflow)) {
            return;
        }
        if (match(TokenKind::Semicolon)) {
            return;
        }
        advance();
    }
}

bool Parser::parseUnsigned(const Token& token, std::size_t& value) {
    value = 0;
    for (const char character : token.lexeme) {
        if (character < '0' || character > '9') {
            diagnostics_.error("P004", token.location, "expected an unsigned integer literal");
            return false;
        }
        const std::size_t digit = static_cast<std::size_t>(character - '0');
        if (value > (std::numeric_limits<std::size_t>::max() - digit) / 10U) {
            diagnostics_.error("P004", token.location, "integer literal is too large");
            return false;
        }
        value = value * 10U + digit;
    }
    return true;
}

bool Parser::parseType(Type& type) {
    const Token token = current();
    if (!isTypeToken(token.kind)) {
        report(token, "a type name");
        return false;
    }
    advance();
    switch (token.kind) {
        case TokenKind::TextType: type = {TypeKind::Text}; break;
        case TokenKind::IntegerType: type = {TypeKind::Integer}; break;
        case TokenKind::DecimalType: type = {TypeKind::Decimal}; break;
        case TokenKind::BooleanType: type = {TypeKind::Boolean}; break;
        case TokenKind::JsonType: type = {TypeKind::Json}; break;
        default: type = {TypeKind::Unknown}; break;
    }
    return true;
}

ComparisonOp Parser::parseComparison() {
    const TokenKind kind = current().kind;
    advance();
    switch (kind) {
        case TokenKind::Less: return ComparisonOp::Less;
        case TokenKind::LessEqual: return ComparisonOp::LessEqual;
        case TokenKind::Greater: return ComparisonOp::Greater;
        case TokenKind::GreaterEqual: return ComparisonOp::GreaterEqual;
        case TokenKind::EqualEqual: return ComparisonOp::Equal;
        case TokenKind::BangEqual: return ComparisonOp::NotEqual;
        default: return ComparisonOp::LessEqual;
    }
}

std::unique_ptr<Expr> Parser::parseExpression() {
    const Token token = current();
    switch (token.kind) {
        case TokenKind::Identifier:
            advance();
            return std::make_unique<IdentifierExpr>(token.lexeme, token.location);
        case TokenKind::StringLiteral:
            advance();
            return std::make_unique<StringLiteralExpr>(token.lexeme, token.location);
        case TokenKind::IntegerLiteral:
            advance();
            return std::make_unique<IntegerLiteralExpr>(token.lexeme, token.location);
        case TokenKind::DecimalLiteral:
            advance();
            return std::make_unique<DecimalLiteralExpr>(token.lexeme, token.location);
        case TokenKind::BooleanLiteral:
            advance();
            return std::make_unique<BooleanLiteralExpr>(token.lexeme, token.location);
        default:
            report(token, "an identifier or literal expression");
            return nullptr;
    }
}

std::unique_ptr<CallExpr> Parser::parseCall() {
    const Token* callToken = consume(TokenKind::Call, "'call'");
    if (!callToken) {
        return nullptr;
    }
    const Token* prompt = consume(TokenKind::Identifier, "a prompt identifier after 'call'");
    if (!prompt || !consume(TokenKind::LeftParen, "'(' after the prompt name")) {
        return nullptr;
    }

    std::vector<std::unique_ptr<Expr>> arguments;
    if (!check(TokenKind::RightParen)) {
        while (true) {
            std::unique_ptr<Expr> argument = parseExpression();
            if (!argument) {
                return nullptr;
            }
            arguments.push_back(std::move(argument));
            if (!match(TokenKind::Comma)) {
                break;
            }
        }
    }
    if (!consume(TokenKind::RightParen, "')' after call arguments") ||
        !consume(TokenKind::Using, "'using' after the call") ) {
        return nullptr;
    }
    const Token* model = consume(TokenKind::Identifier, "a model identifier after 'using'");
    if (!model) {
        return nullptr;
    }
    return std::make_unique<CallExpr>(prompt->lexeme, std::move(arguments), model->lexeme,
                                      callToken->location);
}

std::unique_ptr<InputDecl> Parser::parseInput() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "an input name");
    if (!name || !consume(TokenKind::Colon, "':' after the input name")) {
        return nullptr;
    }
    Type type;
    if (!parseType(type) || !consume(TokenKind::Semicolon, "';' after the input declaration")) {
        return nullptr;
    }
    return std::make_unique<InputDecl>(name->lexeme, type, start);
}

std::unique_ptr<SecretDecl> Parser::parseSecret() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a secret name");
    if (!name || !consume(TokenKind::Semicolon, "';' after the secret declaration")) {
        return nullptr;
    }
    return std::make_unique<SecretDecl>(name->lexeme, start);
}

std::unique_ptr<ModelDecl> Parser::parseModel() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a model name");
    if (!name || !consume(TokenKind::Assign, "'=' after the model name") ||
        !consume(TokenKind::Mock, "'mock' as the offline model provider") ||
        !consume(TokenKind::LeftParen, "'(' after 'mock'")) {
        return nullptr;
    }
    const Token* modelName = consume(TokenKind::StringLiteral, "a quoted mock model name");
    if (!modelName || !consume(TokenKind::RightParen, "')' after the mock model name") ||
        !consume(TokenKind::MaxTokens, "'max_tokens' after the model provider")) {
        return nullptr;
    }
    const Token* maxTokens = consume(TokenKind::IntegerLiteral, "an integer after 'max_tokens'");
    std::size_t value = 0;
    if (!maxTokens || !parseUnsigned(*maxTokens, value) ||
        !consume(TokenKind::Semicolon, "';' after the model declaration")) {
        return nullptr;
    }
    return std::make_unique<ModelDecl>(name->lexeme, "mock", modelName->lexeme, value, start);
}

std::unique_ptr<PromptDecl> Parser::parsePrompt() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a prompt name");
    if (!name || !consume(TokenKind::LeftParen, "'(' after the prompt name")) {
        return nullptr;
    }
    std::vector<Parameter> parameters;
    if (!check(TokenKind::RightParen)) {
        while (true) {
            const Token* parameterName = consume(TokenKind::Identifier, "a parameter name");
            if (!parameterName || !consume(TokenKind::Colon, "':' after the parameter name")) {
                return nullptr;
            }
            Type parameterType;
            if (!parseType(parameterType)) {
                return nullptr;
            }
            parameters.push_back({parameterName->lexeme, parameterType, parameterName->location});
            if (!match(TokenKind::Comma)) {
                break;
            }
        }
    }
    if (!consume(TokenKind::RightParen, "')' after prompt parameters") ||
        !consume(TokenKind::Arrow, "'->' before the prompt return type")) {
        return nullptr;
    }
    Type returnType;
    if (!parseType(returnType) || !consume(TokenKind::Assign, "'=' before the prompt template")) {
        return nullptr;
    }
    const Token* templateToken = consume(TokenKind::StringLiteral, "a quoted prompt template");
    if (!templateToken || !consume(TokenKind::Semicolon, "';' after the prompt declaration")) {
        return nullptr;
    }
    return std::make_unique<PromptDecl>(name->lexeme, std::move(parameters), returnType,
                                        templateToken->lexeme, start);
}

std::unique_ptr<LetStmt> Parser::parseLet() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a local result name");
    if (!name || !consume(TokenKind::Colon, "':' after the local result name")) {
        return nullptr;
    }
    Type type;
    if (!parseType(type) || !consume(TokenKind::Assign, "'=' before the call expression")) {
        return nullptr;
    }
    std::unique_ptr<CallExpr> call = parseCall();
    if (!call || !consume(TokenKind::Semicolon, "';' after the let statement")) {
        return nullptr;
    }
    return std::make_unique<LetStmt>(name->lexeme, type, std::move(call), start);
}

std::unique_ptr<RequireStmt> Parser::parseRequire() {
    const SourceLocation start = previous().location;
    if (!consume(TokenKind::Tokens, "'tokens' after 'require'") ||
        !consume(TokenKind::LeftParen, "'(' after 'tokens'")) {
        return nullptr;
    }
    const Token* subject = consume(TokenKind::Identifier, "an identifier inside 'tokens(...)'");
    if (!subject || !consume(TokenKind::RightParen, "')' after the token subject")) {
        return nullptr;
    }
    if (!isComparison(current().kind)) {
        report(current(), "a comparison operator after 'tokens(...)'");
        return nullptr;
    }
    const ComparisonOp op = parseComparison();
    const Token* limit = consume(TokenKind::IntegerLiteral, "an integer token limit");
    std::size_t value = 0;
    if (!limit || !parseUnsigned(*limit, value) ||
        !consume(TokenKind::Semicolon, "';' after the require statement")) {
        return nullptr;
    }
    return std::make_unique<RequireStmt>(subject->lexeme, op, value, start);
}

std::unique_ptr<OutputStmt> Parser::parseOutput() {
    const SourceLocation start = previous().location;
    std::unique_ptr<Expr> value = parseExpression();
    if (!value || !consume(TokenKind::Semicolon, "';' after the output statement")) {
        return nullptr;
    }
    return std::make_unique<OutputStmt>(std::move(value), start);
}

std::unique_ptr<Stmt> Parser::parseStatement() {
    if (match(TokenKind::Input)) return parseInput();
    if (match(TokenKind::Secret)) return parseSecret();
    if (match(TokenKind::Model)) return parseModel();
    if (match(TokenKind::Prompt)) return parsePrompt();
    if (match(TokenKind::Let)) return parseLet();
    if (match(TokenKind::Require)) return parseRequire();
    if (match(TokenKind::Output)) return parseOutput();
    report(current(), "a workflow statement");
    return nullptr;
}

std::unique_ptr<WorkflowDecl> Parser::parseWorkflow() {
    const Token* workflowToken = consume(TokenKind::Workflow, "'workflow'");
    if (!workflowToken) {
        return nullptr;
    }
    const Token* name = consume(TokenKind::Identifier, "a workflow name");
    if (!name || !consume(TokenKind::Budget, "'budget' after the workflow name")) {
        return nullptr;
    }
    const Token* budget = consume(TokenKind::IntegerLiteral, "an integer workflow budget");
    std::size_t budgetValue = 0;
    if (!budget || !parseUnsigned(*budget, budgetValue) ||
        !consume(TokenKind::LeftBrace, "'{' before workflow statements")) {
        return nullptr;
    }

    auto workflow = std::make_unique<WorkflowDecl>(name->lexeme, budgetValue, workflowToken->location);
    while (!atEnd() && !check(TokenKind::RightBrace)) {
        const std::size_t before = currentIndex_;
        std::unique_ptr<Stmt> statement = parseStatement();
        if (statement) {
            workflow->statements.push_back(std::move(statement));
        } else {
            recoverStatement();
        }
        if (currentIndex_ == before && !atEnd() && !check(TokenKind::RightBrace)) {
            advance();
        }
    }
    if (!consume(TokenKind::RightBrace, "'}' after workflow statements")) {
        return nullptr;
    }
    return workflow;
}

ParseResult Parser::parse() {
    Program program;
    if (atEnd()) {
        report(current(), "a 'workflow' declaration");
    }
    while (!atEnd()) {
        if (!check(TokenKind::Workflow)) {
            report(current(), "a 'workflow' declaration");
            advance();
            continue;
        }
        std::unique_ptr<WorkflowDecl> workflow = parseWorkflow();
        if (workflow) {
            program.workflows.push_back(std::move(workflow));
        } else {
            recoverStatement();
            if (!atEnd() && !check(TokenKind::Workflow) && !check(TokenKind::RightBrace)) {
                advance();
            }
        }
    }
    return {std::move(program), std::move(diagnostics_)};
}

}  // namespace orchlang
