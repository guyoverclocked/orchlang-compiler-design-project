#include "parser.hpp"

#include <cstdlib>
#include <limits>
#include <string>
#include <utility>

namespace orchlang {

namespace {

bool startsStatement(TokenKind kind) {
    return kind == TokenKind::Input || kind == TokenKind::Secret || kind == TokenKind::Model ||
           kind == TokenKind::Prompt || kind == TokenKind::Let || kind == TokenKind::Require ||
           kind == TokenKind::Output || kind == TokenKind::Tool || kind == TokenKind::Emit ||
           kind == TokenKind::If || kind == TokenKind::Retry || kind == TokenKind::Declassify ||
           kind == TokenKind::Endorse;
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
    if (!parseType(type)) {
        return nullptr;
    }
    Label label = publicTrusted();
    if (match(TokenKind::Untrusted)) {
        label.integrity = Integrity::Untrusted;
    }
    auto input = std::make_unique<InputDecl>(name->lexeme, type, label, start);
    if (match(TokenKind::MaxTokens)) {
        const Token* bound = consume(TokenKind::IntegerLiteral, "an integer after 'max_tokens'");
        std::size_t value = 0;
        if (!bound || !parseUnsigned(*bound, value)) {
            return nullptr;
        }
        input->hasTokenBound = true;
        input->tokenBound = value;
    }
    if (!consume(TokenKind::Semicolon, "';' after the input declaration")) {
        return nullptr;
    }
    return input;
}

std::unique_ptr<SecretDecl> Parser::parseSecret() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a secret name");
    if (!name) {
        return nullptr;
    }
    Type type{TypeKind::Text};
    if (match(TokenKind::Colon) && !parseType(type)) {
        return nullptr;
    }
    auto secret = std::make_unique<SecretDecl>(name->lexeme, type, start);
    if (match(TokenKind::MaxTokens)) {
        const Token* bound = consume(TokenKind::IntegerLiteral, "an integer after 'max_tokens'");
        std::size_t value = 0;
        if (!bound || !parseUnsigned(*bound, value)) {
            return nullptr;
        }
        secret->hasTokenBound = true;
        secret->tokenBound = value;
    }
    if (!consume(TokenKind::Semicolon, "';' after the secret declaration")) {
        return nullptr;
    }
    return secret;
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
    if (!maxTokens || !parseUnsigned(*maxTokens, value)) {
        return nullptr;
    }
    auto model = std::make_unique<ModelDecl>(name->lexeme, "mock", modelName->lexeme, value, start);
    if (match(TokenKind::CostPerToken)) {
        const Token price = current();
        if (price.kind != TokenKind::DecimalLiteral && price.kind != TokenKind::IntegerLiteral) {
            report(price, "a numeric price after 'cost_per_token'");
            return nullptr;
        }
        advance();
        model->hasUnitPrice = true;
        model->unitPrice = std::strtod(price.lexeme.c_str(), nullptr);
    }
    if (!consume(TokenKind::Semicolon, "';' after the model declaration")) {
        return nullptr;
    }
    return model;
}

std::unique_ptr<PromptDecl> Parser::parsePrompt() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a prompt name");
    if (!name || !consume(TokenKind::LeftParen, "'(' after the prompt name")) {
        return nullptr;
    }
    std::vector<Parameter> parameters;
    if (!parseParameterList(parameters)) {
        return nullptr;
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

bool Parser::parseParameterList(std::vector<Parameter>& parameters) {
    if (check(TokenKind::RightParen)) {
        return true;
    }
    while (true) {
        const Token* parameterName = consume(TokenKind::Identifier, "a parameter name");
        if (!parameterName || !consume(TokenKind::Colon, "':' after the parameter name")) {
            return false;
        }
        Type parameterType;
        if (!parseType(parameterType)) {
            return false;
        }
        parameters.push_back({parameterName->lexeme, parameterType, parameterName->location});
        if (!match(TokenKind::Comma)) {
            return true;
        }
    }
}

std::unique_ptr<ToolDecl> Parser::parseTool() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a tool name");
    if (!name || !consume(TokenKind::LeftParen, "'(' after the tool name")) {
        return nullptr;
    }
    std::vector<Parameter> parameters;
    if (!parseParameterList(parameters) ||
        !consume(TokenKind::RightParen, "')' after tool parameters") ||
        !consume(TokenKind::Semicolon, "';' after the tool declaration")) {
        return nullptr;
    }
    return std::make_unique<ToolDecl>(name->lexeme, std::move(parameters), start);
}

std::unique_ptr<EmitStmt> Parser::parseEmit() {
    const SourceLocation start = previous().location;
    const Token* name = consume(TokenKind::Identifier, "a tool name after 'emit'");
    if (!name || !consume(TokenKind::LeftParen, "'(' after the tool name")) {
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
    if (!consume(TokenKind::RightParen, "')' after emit arguments") ||
        !consume(TokenKind::Semicolon, "';' after the emit statement")) {
        return nullptr;
    }
    return std::make_unique<EmitStmt>(name->lexeme, std::move(arguments), start);
}

bool Parser::parseCondition(Condition& condition) {
    condition.location = current().location;
    if (match(TokenKind::Tokens)) {
        condition.kind = ConditionKind::TokenBound;
        if (!consume(TokenKind::LeftParen, "'(' after 'tokens'")) {
            return false;
        }
        const Token* subject = consume(TokenKind::Identifier, "an identifier inside 'tokens(...)'");
        if (!subject || !consume(TokenKind::RightParen, "')' after the token subject")) {
            return false;
        }
        condition.subjectName = subject->lexeme;
        if (!isComparison(current().kind)) {
            report(current(), "a comparison operator after 'tokens(...)'");
            return false;
        }
        condition.op = parseComparison();
        const Token* limit = consume(TokenKind::IntegerLiteral, "an integer token limit");
        return limit != nullptr && parseUnsigned(*limit, condition.limit);
    }
    const Token* flag = consume(TokenKind::Identifier, "a condition");
    if (!flag) {
        return false;
    }
    condition.kind = ConditionKind::Flag;
    condition.subjectName = flag->lexeme;
    return true;
}

bool Parser::parseBlock(Block& block) {
    if (!consume(TokenKind::LeftBrace, "'{' before a statement block")) {
        return false;
    }
    while (!atEnd() && !check(TokenKind::RightBrace)) {
        const std::size_t before = currentIndex_;
        std::unique_ptr<Stmt> statement = parseStatement();
        if (statement) {
            block.push_back(std::move(statement));
        } else {
            recoverStatement();
        }
        if (currentIndex_ == before && !atEnd() && !check(TokenKind::RightBrace)) {
            advance();
        }
    }
    return consume(TokenKind::RightBrace, "'}' after a statement block") != nullptr;
}

std::unique_ptr<IfStmt> Parser::parseIf() {
    const SourceLocation start = previous().location;
    Condition condition;
    if (!parseCondition(condition)) {
        return nullptr;
    }
    Block thenBranch;
    if (!parseBlock(thenBranch)) {
        return nullptr;
    }
    Block elseBranch;
    bool hasElse = false;
    if (match(TokenKind::Else)) {
        hasElse = true;
        if (!parseBlock(elseBranch)) {
            return nullptr;
        }
    }
    return std::make_unique<IfStmt>(std::move(condition), std::move(thenBranch), std::move(elseBranch),
                                    hasElse, start);
}

std::unique_ptr<RetryStmt> Parser::parseRetry() {
    const SourceLocation start = previous().location;
    const Token* bound = consume(TokenKind::IntegerLiteral, "an integer repetition bound after 'retry'");
    std::size_t value = 0;
    if (!bound || !parseUnsigned(*bound, value)) {
        return nullptr;
    }
    if (value == 0) {
        diagnostics_.error("P005", bound->location, "'retry' requires a repetition bound of at least 1");
        return nullptr;
    }
    Block body;
    if (!parseBlock(body)) {
        return nullptr;
    }
    return std::make_unique<RetryStmt>(value, std::move(body), start);
}

std::unique_ptr<ReclassifyStmt> Parser::parseReclassify(bool endorsement) {
    const SourceLocation start = previous().location;
    const std::string keyword = endorsement ? "'endorse'" : "'declassify'";
    if (!consume(TokenKind::LeftParen, "'(' after " + keyword)) {
        return nullptr;
    }
    const Token* subject = consume(TokenKind::Identifier, "an identifier to reclassify");
    if (!subject || !consume(TokenKind::RightParen, "')' after the reclassified identifier") ||
        !consume(TokenKind::As, "'as' after the reclassified identifier")) {
        return nullptr;
    }
    const Token* name = consume(TokenKind::Identifier, "a name for the reclassified result");
    if (!name || !consume(TokenKind::Colon, "':' after the reclassified result name")) {
        return nullptr;
    }
    Type type;
    if (!parseType(type) || !consume(TokenKind::Because, "'because' and a written justification")) {
        return nullptr;
    }
    const Token* reason = consume(TokenKind::StringLiteral, "a quoted justification");
    if (!reason || !consume(TokenKind::Semicolon, "';' after the reclassification")) {
        return nullptr;
    }
    if (reason->lexeme.empty()) {
        diagnostics_.error("P006", reason->location, "a reclassification justification may not be empty");
        return nullptr;
    }
    return std::make_unique<ReclassifyStmt>(endorsement, subject->lexeme, name->lexeme, type,
                                            reason->lexeme, start);
}

std::unique_ptr<Stmt> Parser::parseStatement() {
    if (match(TokenKind::Input)) return parseInput();
    if (match(TokenKind::Secret)) return parseSecret();
    if (match(TokenKind::Model)) return parseModel();
    if (match(TokenKind::Prompt)) return parsePrompt();
    if (match(TokenKind::Let)) return parseLet();
    if (match(TokenKind::Require)) return parseRequire();
    if (match(TokenKind::Output)) return parseOutput();
    if (match(TokenKind::Tool)) return parseTool();
    if (match(TokenKind::Emit)) return parseEmit();
    if (match(TokenKind::If)) return parseIf();
    if (match(TokenKind::Retry)) return parseRetry();
    if (match(TokenKind::Declassify)) return parseReclassify(false);
    if (match(TokenKind::Endorse)) return parseReclassify(true);
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
