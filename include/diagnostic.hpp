#pragma once

#include "source_location.hpp"

#include <string>
#include <utility>
#include <vector>

namespace orchlang {

enum class Severity { Error, Warning };

struct Diagnostic {
    Severity severity{Severity::Error};
    std::string code;
    SourceLocation location;
    std::string message;
};

class DiagnosticBag {
public:
    void error(std::string code, SourceLocation location, std::string message) {
        diagnostics_.push_back({Severity::Error, std::move(code), std::move(location), std::move(message)});
    }

    void warning(std::string code, SourceLocation location, std::string message) {
        diagnostics_.push_back({Severity::Warning, std::move(code), std::move(location), std::move(message)});
    }

    void append(const DiagnosticBag& other) {
        diagnostics_.insert(diagnostics_.end(), other.diagnostics_.begin(), other.diagnostics_.end());
    }

    void append(const std::vector<Diagnostic>& other) {
        diagnostics_.insert(diagnostics_.end(), other.begin(), other.end());
    }

    const std::vector<Diagnostic>& all() const { return diagnostics_; }
    bool empty() const { return diagnostics_.empty(); }
    bool hasErrors() const;

private:
    std::vector<Diagnostic> diagnostics_;
};

std::string formatDiagnostic(const Diagnostic& diagnostic);
std::string formatDiagnostics(const DiagnosticBag& diagnostics);

}  // namespace orchlang
