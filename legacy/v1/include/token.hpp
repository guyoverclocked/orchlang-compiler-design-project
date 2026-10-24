#pragma once

#include "source_location.hpp"

#include <string>

namespace orchlang {

enum class TokenKind {
    EndOfFile,
    Invalid,
    Identifier,
    StringLiteral,
    IntegerLiteral,
    DecimalLiteral,
    BooleanLiteral,

    Workflow,
    Budget,
    Input,
    Secret,
    Model,
    Mock,
    MaxTokens,
    Prompt,
    Let,
    Call,
    Using,
    Require,
    Tokens,
    Output,
    Untrusted,
    Tool,
    Emit,
    If,
    Else,
    Retry,
    Declassify,
    Endorse,
    As,
    Because,
    CostPerToken,
    TextType,
    IntegerType,
    DecimalType,
    BooleanType,
    JsonType,

    LeftBrace,
    RightBrace,
    LeftParen,
    RightParen,
    Colon,
    Semicolon,
    Comma,
    Arrow,
    Assign,
    Less,
    LessEqual,
    Greater,
    GreaterEqual,
    EqualEqual,
    BangEqual,
};

struct Token {
    TokenKind kind{TokenKind::Invalid};
    std::string lexeme;
    SourceLocation location;
};

const char* tokenKindName(TokenKind kind);
bool isTypeToken(TokenKind kind);

}  // namespace orchlang
