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
    std::string tokenizer;
    std::size_t overhead{0};
    bool hasByteCap{false};
    std::size_t byteCap{0};

    // What the endpoint is, independent of the name the program gives it.  Two
    // declarations with the same identity send identical requests to the same
    // place; two with the same local name need not (audit finding F3: a model
    // redeclared inside a branch arm under an old name).
    std::string identity() const;
};

struct PromptParameterInfo {
    std::string name;
    Type type;
};

struct PromptSignature {
    std::vector<PromptParameterInfo> parameters;
    Type returnType;
    // Estimated token cost of the template as written, placeholders included.
    // Derived once at declaration and reused at every call site.
    std::size_t templateTokens{0};
    // The template itself.  Requests are compared by what they say, not by
    // how big an estimate of them is.
    std::string templateText;
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
    // Security label carried by the value this symbol denotes, including the
    // program counter at the point it was bound.
    Label label{publicTrusted()};
    // The same label with the program counter's confidentiality left out: what
    // the value's *content* depends on.  A result computed inside a
    // secret-guarded arm from public arguments has public content even though
    // its existence depends on the secret; the relational analysis is what
    // accounts for existence (open problem OP-1).
    Label dataLabel{publicTrusted()};
    // Static upper bound, in tokens, on the value this symbol denotes.
    // Only meaningful when tokenBoundKnown is set; an input with no declared
    // bound, or a model or tool name, has no bound at all.  The unit is the
    // compiler's estimate unit unless tokenizer names a real one.
    bool tokenBoundKnown{false};
    std::size_t tokenBound{0};
    std::string tokenizer{};
    // Static upper bound in UTF-8 bytes, the unit a guaranteed input bound is
    // built from.
    bool byteBoundKnown{false};
    std::size_t byteBound{0};
    // Unique across the whole program, assigned at declaration.  Later passes
    // compare bindings by this, never by name.
    int id{0};
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
    int nextId_{0};
};

std::string formatSymbolTable(const SymbolTable& table);

}  // namespace orchlang
