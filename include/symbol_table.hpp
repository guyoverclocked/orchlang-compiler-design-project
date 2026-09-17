#pragma once

#include "ast.hpp"
#include "label.hpp"

#include <cstddef>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace orchlang {

enum class SymbolKind { Input, Secret, Model, Prompt, PromptParameter, LocalResult, Tool, Reclassified };

std::string symbolKindName(SymbolKind kind);

struct ModelMetadata {
    std::string provider;
    std::string modelName;
    std::size_t maxTokens{0};
    bool hasUnitPrice{false};
    double unitPrice{0.0};
};

struct PromptParameterInfo {
    std::string name;
    Type type;
};

struct PromptSignature {
    std::vector<PromptParameterInfo> parameters;
    Type returnType;
    // Static token cost of the template itself, excluding the substituted
    // arguments.  Derived once at declaration and reused at every call site.
    std::size_t templateTokens{0};
};

struct ToolSignature {
    std::vector<PromptParameterInfo> parameters;
};

struct Symbol {
    std::string name;
    SymbolKind kind{SymbolKind::Input};
    Type type;
    std::string scope;
    SourceLocation location;
    std::optional<ModelMetadata> model;
    std::optional<PromptSignature> prompt;
    std::optional<ToolSignature> tool;
    // Security label carried by the value this symbol denotes.
    Label label{publicTrusted()};
    // Static upper bound, in tokens, on the value this symbol denotes.
    // Only meaningful when tokenBoundKnown is set; an input with no declared
    // bound, or a model or tool name, has no bound at all.
    bool tokenBoundKnown{false};
    std::size_t tokenBound{0};
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
