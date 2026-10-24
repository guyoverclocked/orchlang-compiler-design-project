#include "diagnostic.hpp"

#include <sstream>

namespace orchlang {

std::string formatLocation(const SourceLocation& location) {
    std::ostringstream out;
    out << (location.file.empty() ? "<input>" : location.file);
    if (location.valid()) {
        out << ':' << location.line << ':' << location.column;
    }
    return out.str();
}

bool DiagnosticBag::hasErrors() const {
    for (const Diagnostic& diagnostic : diagnostics_) {
        if (diagnostic.severity == Severity::Error) {
            return true;
        }
    }
    return false;
}

std::string formatDiagnostic(const Diagnostic& diagnostic) {
    std::ostringstream out;
    out << formatLocation(diagnostic.location) << ": "
        << (diagnostic.severity == Severity::Error ? "error" : "warning")
        << " [" << diagnostic.code << "] " << diagnostic.message;
    return out.str();
}

std::string formatDiagnostics(const DiagnosticBag& diagnostics) {
    std::ostringstream out;
    for (const Diagnostic& diagnostic : diagnostics.all()) {
        out << formatDiagnostic(diagnostic) << '\n';
    }
    return out.str();
}

}  // namespace orchlang
