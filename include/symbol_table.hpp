#pragma once

#include "ast.hpp"

#include <cstddef>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace orchlang {

enum class SymbolKind { Input, Secret, Model, Prompt, PromptParameter, LocalResult };

std::string symbolKindName(SymbolKind kind);

struct ModelMetadata {
    std::string provider;
    std::string modelName;
    std::size_t maxTokens{0};
};

struct PromptParameterInfo {
    std::string name;
    Type type;
};

struct PromptSignature {
    std::vector<PromptParameterInfo> parameters;
    Type returnType;
};

struct Symbol {
    std::string name;
    SymbolKind kind{SymbolKind::Input};
    Type type;
    std::string scope;
    SourceLocation location;
    std::optional<ModelMetadata> model;
    std::optional<PromptSignature> prompt;
};

struct Scope {
    std::string name;
    std::optional<std::size_t> parent;
    std::map<std::string, Symbol> symbols;
};

class SymbolTable {
public:
    std::size_t createScope(std::string name, std::optional<std::size_t> parent = std::nullopt);
    const Scope& scope(std::size_t index) const;
    bool insert(std::size_t scopeIndex, Symbol symbol, const Symbol** existing = nullptr);
    const Symbol* lookupLocal(std::size_t scopeIndex, const std::string& name) const;
    const Symbol* lookup(std::size_t scopeIndex, const std::string& name) const;
    const std::vector<Scope>& scopes() const { return scopes_; }

private:
    std::vector<Scope> scopes_;
};

std::string formatSymbolTable(const SymbolTable& table);

}  // namespace orchlang
