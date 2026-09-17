#pragma once

#include "ast.hpp"
#include "diagnostic.hpp"
#include "symbol_table.hpp"

#include <cstddef>
#include <map>
#include <string>

namespace orchlang {

struct SemanticResult {
    SymbolTable symbols;
    DiagnosticBag diagnostics;
    std::map<std::string, std::size_t> workflowScopes;
    std::map<std::string, std::size_t> declaredTokenTotals;

    bool success() const { return !diagnostics.hasErrors(); }
};

class SemanticAnalyzer {
public:
    SemanticResult analyze(const Program& program) const;
};

}  // namespace orchlang
