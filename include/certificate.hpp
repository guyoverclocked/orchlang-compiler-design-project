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

// `source` is the exact text analysed.  Its SHA-256 is written into the
// certificate, so a checker can refuse a certificate presented for a different
// program or a different revision of this one.
std::string printCertificate(const Program& program, const std::string& source,
                             const SemanticResult& semantic, const CostResult& cost,
                             const ProgramIR& ir, const RelationalResult& relational,
                             const std::string& relationalRule);

// A short human-readable summary of the same facts, for the terminal.
std::string printCertificateSummary(const CostResult& cost, const SemanticResult& semantic,
                                    const RelationalResult& relational);

// The version of the analysis a certificate was produced by.  A checker
// compares it, because the meaning of the certificate's fields is tied to it.
constexpr const char* kAnalysisVersion = "orchlang-4";

}  // namespace orchlang
