#include "lexer.hpp"

#include <cctype>
#include <sstream>

namespace orchlang {

namespace {

bool isIdentifierStart(char character) {
    const unsigned char value = static_cast<unsigned char>(character);
    return std::isalpha(value) != 0 || character == '_';
}

bool isIdentifierPart(char character) {
    const unsigned char value = static_cast<unsigned char>(character);
    return std::isalnum(value) != 0 || character == '_';
}

TokenKind keywordKind(const std::string& value) {
    if (value == "workflow") return TokenKind::Workflow;
    if (value == "budget") return TokenKind::Budget;
    if (value == "input") return TokenKind::Input;
    if (value == "secret") return TokenKind::Secret;
    if (value == "model") return TokenKind::Model;
    if (value == "mock") return TokenKind::Mock;
    if (value == "max_tokens") return TokenKind::MaxTokens;
    if (value == "prompt") return TokenKind::Prompt;
    if (value == "let") return TokenKind::Let;
    if (value == "call") return TokenKind::Call;
    if (value == "using") return TokenKind::Using;
    if (value == "require") return TokenKind::Require;
    if (value == "tokens") return TokenKind::Tokens;
    if (value == "output") return TokenKind::Output;
    if (value == "text") return TokenKind::TextType;
    if (value == "integer") return TokenKind::IntegerType;
    if (value == "decimal") return TokenKind::DecimalType;
    if (value == "boolean") return TokenKind::BooleanType;
    if (value == "json") return TokenKind::JsonType;
    if (value == "true" || value == "false") return TokenKind::BooleanLiteral;
    return TokenKind::Identifier;
}

std::string displayLexeme(const Token& token) {
    if (token.kind == TokenKind::StringLiteral) {
        return "\"" + token.lexeme + "\"";
    }
    if (token.kind == TokenKind::EndOfFile) {
        return "<eof>";
    }
    return token.lexeme;
}

}  // namespace

const char* tokenKindName(TokenKind kind) {
    switch (kind) {
        case TokenKind::EndOfFile: return "EOF";
        case TokenKind::Invalid: return "INVALID";
        case TokenKind::Identifier: return "IDENTIFIER";
        case TokenKind::StringLiteral: return "STRING";
        case TokenKind::IntegerLiteral: return "INTEGER";
        case TokenKind::DecimalLiteral: return "DECIMAL";
        case TokenKind::BooleanLiteral: return "BOOLEAN";
        case TokenKind::Workflow: return "WORKFLOW";
        case TokenKind::Budget: return "BUDGET";
        case TokenKind::Input: return "INPUT";
        case TokenKind::Secret: return "SECRET";
        case TokenKind::Model: return "MODEL";
        case TokenKind::Mock: return "MOCK";
        case TokenKind::MaxTokens: return "MAX_TOKENS";
        case TokenKind::Prompt: return "PROMPT";
        case TokenKind::Let: return "LET";
        case TokenKind::Call: return "CALL";
        case TokenKind::Using: return "USING";
        case TokenKind::Require: return "REQUIRE";
        case TokenKind::Tokens: return "TOKENS";
        case TokenKind::Output: return "OUTPUT";
        case TokenKind::TextType: return "TYPE_TEXT";
        case TokenKind::IntegerType: return "TYPE_INTEGER";
        case TokenKind::DecimalType: return "TYPE_DECIMAL";
        case TokenKind::BooleanType: return "TYPE_BOOLEAN";
        case TokenKind::JsonType: return "TYPE_JSON";
        case TokenKind::LeftBrace: return "LBRACE";
        case TokenKind::RightBrace: return "RBRACE";
        case TokenKind::LeftParen: return "LPAREN";
        case TokenKind::RightParen: return "RPAREN";
        case TokenKind::Colon: return "COLON";
        case TokenKind::Semicolon: return "SEMICOLON";
        case TokenKind::Comma: return "COMMA";
        case TokenKind::Arrow: return "ARROW";
        case TokenKind::Assign: return "ASSIGN";
        case TokenKind::Less: return "LESS";
        case TokenKind::LessEqual: return "LESS_EQUAL";
        case TokenKind::Greater: return "GREATER";
        case TokenKind::GreaterEqual: return "GREATER_EQUAL";
        case TokenKind::EqualEqual: return "EQUAL_EQUAL";
        case TokenKind::BangEqual: return "BANG_EQUAL";
    }
    return "UNKNOWN";
}

bool isTypeToken(TokenKind kind) {
    return kind == TokenKind::TextType || kind == TokenKind::IntegerType ||
           kind == TokenKind::DecimalType || kind == TokenKind::BooleanType ||
           kind == TokenKind::JsonType;
}

Lexer::Lexer(std::string source, std::string filename)
    : source_(std::move(source)), filename_(std::move(filename)) {}

bool Lexer::atEnd() const { return index_ >= source_.size(); }

char Lexer::peek(std::size_t offset) const {
    const std::size_t position = index_ + offset;
    return position < source_.size() ? source_[position] : '\0';
}

char Lexer::advance() {
    if (atEnd()) {
        return '\0';
    }
    const char character = source_[index_++];
    if (character == '\n') {
        ++line_;
        column_ = 1;
    } else {
        ++column_;
    }
    return character;
}

bool Lexer::match(char expected) {
    if (peek() != expected) {
        return false;
    }
    advance();
    return true;
}

SourceLocation Lexer::location() const { return {filename_, line_, column_}; }

Token Lexer::single(TokenKind kind, std::string lexeme, SourceLocation start) const {
    return {kind, std::move(lexeme), std::move(start)};
}

void Lexer::skipWhitespaceAndComments() {
    for (;;) {
        const char character = peek();
        if (character == ' ' || character == '\r' || character == '\t' || character == '\n') {
            advance();
            continue;
        }
        if (character == '/' && peek(1) == '/') {
            while (!atEnd() && peek() != '\n') {
                advance();
            }
            continue;
        }
        break;
    }
}

Token Lexer::identifierOrKeyword() {
    const SourceLocation start = location();
    const std::size_t first = index_;
    advance();
    while (isIdentifierPart(peek())) {
        advance();
    }
    const std::string value = source_.substr(first, index_ - first);
    return single(keywordKind(value), value, start);
}

Token Lexer::number() {
    const SourceLocation start = location();
    const std::size_t first = index_;
    while (std::isdigit(static_cast<unsigned char>(peek())) != 0) {
        advance();
    }
    bool decimal = false;
    if (peek() == '.' && std::isdigit(static_cast<unsigned char>(peek(1))) != 0) {
        decimal = true;
        advance();
        while (std::isdigit(static_cast<unsigned char>(peek())) != 0) {
            advance();
        }
    }
    return single(decimal ? TokenKind::DecimalLiteral : TokenKind::IntegerLiteral,
                  source_.substr(first, index_ - first), start);
}

Token Lexer::stringLiteral() {
    const SourceLocation start = location();
    advance();  // Opening quote.
    std::string decoded;
    while (!atEnd() && peek() != '"' && peek() != '\n') {
        const char character = advance();
        if (character != '\\') {
            decoded.push_back(character);
            continue;
        }

        if (atEnd() || peek() == '\n') {
            diagnostics_.error("L002", start, "unterminated string literal");
            return single(TokenKind::Invalid, decoded, start);
        }
        const char escaped = advance();
        switch (escaped) {
            case 'n': decoded.push_back('\n'); break;
            case 't': decoded.push_back('\t'); break;
            case '"': decoded.push_back('"'); break;
            case '\\': decoded.push_back('\\'); break;
            default:
                diagnostics_.error("L003", start,
                                   std::string("unsupported escape sequence ") + '\\' + escaped);
                decoded.push_back(escaped);
                break;
        }
    }
    if (atEnd() || peek() != '"') {
        diagnostics_.error("L002", start, "unterminated string literal");
        return single(TokenKind::Invalid, decoded, start);
    }
    advance();
    return single(TokenKind::StringLiteral, decoded, start);
}

LexResult Lexer::scan() {
    std::vector<Token> tokens;
    while (true) {
        skipWhitespaceAndComments();
        if (atEnd()) {
            tokens.push_back(single(TokenKind::EndOfFile, "", location()));
            break;
        }

        const SourceLocation start = location();
        const char character = peek();
        if (isIdentifierStart(character)) {
            tokens.push_back(identifierOrKeyword());
            continue;
        }
        if (std::isdigit(static_cast<unsigned char>(character)) != 0) {
            tokens.push_back(number());
            continue;
        }

        advance();
        switch (character) {
            case '"':
                --index_;
                --column_;
                tokens.push_back(stringLiteral());
                break;
            case '{': tokens.push_back(single(TokenKind::LeftBrace, "{", start)); break;
            case '}': tokens.push_back(single(TokenKind::RightBrace, "}", start)); break;
            case '(': tokens.push_back(single(TokenKind::LeftParen, "(", start)); break;
            case ')': tokens.push_back(single(TokenKind::RightParen, ")", start)); break;
            case ':': tokens.push_back(single(TokenKind::Colon, ":", start)); break;
            case ';': tokens.push_back(single(TokenKind::Semicolon, ";", start)); break;
            case ',': tokens.push_back(single(TokenKind::Comma, ",", start)); break;
            case '-':
                if (match('>')) {
                    tokens.push_back(single(TokenKind::Arrow, "->", start));
                } else {
                    diagnostics_.error("L001", start, "unexpected character '-'");
                    tokens.push_back(single(TokenKind::Invalid, "-", start));
                }
                break;
            case '=':
                if (match('=')) {
                    tokens.push_back(single(TokenKind::EqualEqual, "==", start));
                } else {
                    tokens.push_back(single(TokenKind::Assign, "=", start));
                }
                break;
            case '!':
                if (match('=')) {
                    tokens.push_back(single(TokenKind::BangEqual, "!=", start));
                } else {
                    diagnostics_.error("L001", start, "unexpected character '!'");
                    tokens.push_back(single(TokenKind::Invalid, "!", start));
                }
                break;
            case '<':
                if (match('=')) {
                    tokens.push_back(single(TokenKind::LessEqual, "<=", start));
                } else {
                    tokens.push_back(single(TokenKind::Less, "<", start));
                }
                break;
            case '>':
                if (match('=')) {
                    tokens.push_back(single(TokenKind::GreaterEqual, ">=", start));
                } else {
                    tokens.push_back(single(TokenKind::Greater, ">", start));
                }
                break;
            default:
                diagnostics_.error("L001", start, std::string("unexpected character '") + character + "'");
                tokens.push_back(single(TokenKind::Invalid, std::string(1, character), start));
                break;
        }
    }
    return {std::move(tokens), std::move(diagnostics_)};
}

std::string formatTokens(const std::vector<Token>& tokens) {
    std::ostringstream out;
    for (const Token& token : tokens) {
        out << token.location.line << ':' << token.location.column << "  "
            << tokenKindName(token.kind) << "  " << displayLexeme(token) << '\n';
    }
    return out.str();
}

}  // namespace orchlang
