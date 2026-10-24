#pragma once

#include "diagnostic.hpp"
#include "token.hpp"

#include <string>
#include <vector>

namespace orchlang {

struct LexResult {
    std::vector<Token> tokens;
    DiagnosticBag diagnostics;
};

class Lexer {
public:
    Lexer(std::string source, std::string filename);
    LexResult scan();

private:
    bool atEnd() const;
    char peek(std::size_t offset = 0) const;
    char advance();
    bool match(char expected);
    SourceLocation location() const;
    void skipWhitespaceAndComments();
    Token identifierOrKeyword();
    Token number();
    Token stringLiteral();
    Token single(TokenKind kind, std::string lexeme, SourceLocation start) const;

    std::string source_;
    std::string filename_;
    std::size_t index_{0};
    std::size_t line_{1};
    std::size_t column_{1};
    DiagnosticBag diagnostics_;
};

std::string formatTokens(const std::vector<Token>& tokens);

}  // namespace orchlang
