#pragma once

#include "ast.hpp"
#include "label.hpp"

#include <cstddef>
#include <map>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace orchlang {

enum class SymbolKind { Input, Secret, Model, Prompt, PromptParameter, LocalResult, Tool, Reclassified };

std::string symbolKindName(SymbolKind kind);

// A resolved model contract.  Source aliases are deliberately not part of its
// identity: two aliases with the same provider/model/cap/price denote the same
// oracle and billing contract.
struct ModelContract {
    std::string provider;
    std::string modelName;
    std::size_t maxTokens{0};
    bool hasUnitPrice{false};
    double unitPrice{0.0};

    bool operator==(const ModelContract& other) const {
        return provider == other.provider && modelName == other.modelName &&
               maxTokens == other.maxTokens && hasUnitPrice == other.hasUnitPrice &&
               unitPrice == other.unitPrice;
    }
    bool operator!=(const ModelContract& other) const { return !(*this == other); }
    bool operator<(const ModelContract& other) const {
        return std::tie(provider, modelName, maxTokens, hasUnitPrice, unitPrice) <
               std::tie(other.provider, other.modelName, other.maxTokens, other.hasUnitPrice,
                        other.unitPrice);
    }

    std::string stableKey() const;
    std::string displayName() const;
    std::string tokenizerIdentity() const;
};

using ModelMetadata = ModelContract;

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
    // Exact decoded template bytes used to form requests.  Token estimates are
    // not an equality oracle: different strings can have the same estimate.
    std::string templateText;
};

struct ToolSignature {
    std::vector<PromptParameterInfo> parameters;
};

struct Symbol {
    Symbol() = default;
    Symbol(std::string declaredName, SymbolKind declaredKind, Type declaredType,
           std::string declaredScope, SourceLocation declaredLocation,
           std::optional<ModelMetadata> declaredModel,
           std::optional<PromptSignature> declaredPrompt,
           std::optional<ToolSignature> declaredTool, Label declaredLabel)
        : name(std::move(declaredName)), kind(declaredKind), type(declaredType),
          scope(std::move(declaredScope)), location(std::move(declaredLocation)),
          model(std::move(declaredModel)), prompt(std::move(declaredPrompt)),
          tool(std::move(declaredTool)), label(declaredLabel), contentLabel(declaredLabel) {}

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
    // Non-empty only for model-generated output bounds, whose unit is tied to
    // the producing model's tokenizer. Empty means the source supplied an
    // external bound under the language's declared input-size assumption.
    std::string tokenBoundTokenizer;
    // `label` includes control dependence (the program counter). `contentLabel`
    // describes the value's contents alone. A model result created under a
    // secret guard can have public contents but secret-dependent existence.
    Label contentLabel{publicTrusted()};
    // Every lexical declaration gets a unique binding identity. Aliases made by
    // reclassification retain valueIdentity, while shadowing gets a new one.
    std::size_t bindingIdentity{0};
    std::size_t valueIdentity{0};
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
    std::size_t nextBindingIdentity_{1};
};

std::string formatSymbolTable(const SymbolTable& table);

}  // namespace orchlang
