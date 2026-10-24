#pragma once

// The safety certificate.
//
// A certificate is what the compiler hands downstream once a workflow type
// checks: the derived token bound together with the assumption it rests on, the
// final security label of every binding, and every place the author stepped
// outside the lattice with a written justification.  It is emitted as JSON so a
// runtime, a reviewer, or a CI job can check a deployed workflow against the
// same numbers the compiler proved, without re-running the analysis.

#include "cost_analyzer.hpp"
#include "ir.hpp"
#include "relational.hpp"
#include "semantic_analyzer.hpp"

#include <string>

namespace orchlang {

std::string printCertificate(const Program& program, const SemanticResult& semantic,
                             const CostResult& cost, const ProgramIR& ir,
                             const RelationalResult& relational);

// A short human-readable summary of the same facts, for the terminal.
std::string printCertificateSummary(const CostResult& cost, const SemanticResult& semantic);

}  // namespace orchlang
