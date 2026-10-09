#include "symbol_table.hpp"

#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace orchlang {

std::string ModelContract::stableKey() const {
    std::ostringstream out;
    // Hex encoding keeps this safe to print as one whitespace-free key while
    // length prefixes make every component unambiguous.
    const auto hex = [](const std::string& text) {
        std::ostringstream encoded;
        encoded << std::hex << std::setfill('0');
        for (const unsigned char byte : text) {
            encoded << std::setw(2) << static_cast<unsigned>(byte);
        }
        return encoded.str();
    };
    out << "p" << provider.size() << "x" << hex(provider) << "_m" << modelName.size() << "x"
        << hex(modelName) << "_cap" << maxTokens << "_priced" << (hasUnitPrice ? '1' : '0');
    if (hasUnitPrice) {
        out << "_unit" << std::hexfloat << unitPrice;
    }
    return out.str();
}

std::string ModelContract::displayName() const {
    std::ostringstream out;
    out << provider << ':' << modelName << " (max_tokens=" << maxTokens;
    if (hasUnitPrice) {
        out << ", cost_per_token=" << std::setprecision(17) << unitPrice;
    }
    out << ')';
    return out.str();
}

std::string ModelContract::tokenizerIdentity() const {
    std::ostringstream out;
    out << provider.size() << ':' << provider << modelName.size() << ':' << modelName;
    return out.str();
}

std::string symbolKindName(SymbolKind kind) {
    switch (kind) {
        case SymbolKind::Input: return "input";
        case SymbolKind::Secret: return "secret";
        case SymbolKind::Model: return "model";
        case SymbolKind::Prompt: return "prompt";
        case SymbolKind::PromptParameter: return "prompt-parameter";
        case SymbolKind::LocalResult: return "local-result";
        case SymbolKind::Tool: return "tool";
        case SymbolKind::Reclassified: return "reclassified";
    }
    return "unknown";
}

std::size_t SymbolTable::createScope(std::string name, std::optional<std::size_t> parent) {
    if (parent && *parent >= scopes_.size()) {
        throw std::out_of_range("symbol-table parent scope does not exist");
    }
    scopes_.push_back({std::move(name), parent, {}});
    return scopes_.size() - 1;
}

const Scope& SymbolTable::scope(std::size_t index) const {
    return scopes_.at(index);
}

bool SymbolTable::insert(std::size_t scopeIndex, Symbol symbol, const Symbol** existing) {
    Scope& target = scopes_.at(scopeIndex);
    symbol.scope = target.name;
    const auto found = target.symbols.find(symbol.name);
    if (found != target.symbols.end()) {
        if (existing) {
            *existing = &found->second;
        }
        return false;
    }
    if (symbol.bindingIdentity == 0) {
        symbol.bindingIdentity = nextBindingIdentity_++;
    }
    if (symbol.valueIdentity == 0) {
        symbol.valueIdentity = symbol.bindingIdentity;
    }
    target.symbols.emplace(symbol.name, std::move(symbol));
    if (existing) {
        *existing = nullptr;
    }
    return true;
}

const Symbol* SymbolTable::lookupLocal(std::size_t scopeIndex, const std::string& name) const {
    const Scope& target = scopes_.at(scopeIndex);
    const auto found = target.symbols.find(name);
    return found == target.symbols.end() ? nullptr : &found->second;
}

const Symbol* SymbolTable::lookup(std::size_t scopeIndex, const std::string& name) const {
    std::optional<std::size_t> next = scopeIndex;
    while (next) {
        const Scope& target = scopes_.at(*next);
        const auto found = target.symbols.find(name);
        if (found != target.symbols.end()) {
            return &found->second;
        }
        next = target.parent;
    }
    return nullptr;
}

namespace {

std::string signatureText(const PromptSignature& signature) {
    std::ostringstream out;
    out << '(';
    for (std::size_t i = 0; i < signature.parameters.size(); ++i) {
        if (i != 0) {
            out << ", ";
        }
        out << signature.parameters[i].name << ':' << typeName(signature.parameters[i].type);
    }
    out << ") -> " << typeName(signature.returnType);
    return out.str();
}

std::string toolSignatureText(const ToolSignature& signature) {
    std::ostringstream out;
    out << '(';
    for (std::size_t i = 0; i < signature.parameters.size(); ++i) {
        if (i != 0) {
            out << ", ";
        }
        out << signature.parameters[i].name << ':' << typeName(signature.parameters[i].type);
    }
    out << ") sink";
    return out.str();
}

}  // namespace

std::string formatSymbolTable(const SymbolTable& table) {
    std::ostringstream out;
    for (const Scope& scope : table.scopes()) {
        out << "Scope " << scope.name << '\n';
        if (scope.symbols.empty()) {
            out << "  <empty>\n";
        }
        for (const auto& entry : scope.symbols) {
            const Symbol& symbol = entry.second;
            out << "  " << symbolKindName(symbol.kind) << ' ' << symbol.name;
            if (symbol.type.kind != TypeKind::Unknown) {
                out << " : " << typeName(symbol.type);
            }
            if (symbol.model) {
                out << " provider=" << symbol.model->provider
                    << " name=" << symbol.model->modelName
                    << " max_tokens=" << symbol.model->maxTokens;
                if (symbol.model->hasUnitPrice) {
                    out << " cost_per_token=" << symbol.model->unitPrice;
                }
            }
            if (symbol.prompt) {
                out << ' ' << signatureText(*symbol.prompt)
                    << " template_tokens=" << symbol.prompt->templateTokens;
            }
            if (symbol.tool) {
                out << ' ' << toolSignatureText(*symbol.tool);
            }
            out << " label=" << labelName(symbol.label)
                << " content_label=" << labelName(symbol.contentLabel)
                << " binding_id=" << symbol.bindingIdentity
                << " value_id=" << symbol.valueIdentity;
            if (symbol.tokenBoundKnown) {
                out << " token_bound=" << symbol.tokenBound;
            }
            out << " declared=" << formatLocation(symbol.location) << '\n';
        }
    }
    return out.str();
}

}  // namespace orchlang
