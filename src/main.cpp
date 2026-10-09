#include "ast.hpp"
#include "certificate.hpp"
#include "cost_analyzer.hpp"
#include "diagnostic.hpp"
#include "interpreter.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "relational.hpp"
#include "semantic_analyzer.hpp"
#include "symbol_table.hpp"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

namespace {

enum class Command { Tokens, Check, Ast, Symbols, Ir, IrJson, Cost, Certify, Run, Invalid };

struct Invocation {
    Command command{Command::Invalid};
    std::string path;
    AnalysisOptions options;
    RunOptions run;
    bool jsonOutput{false};
};

void printUsage(std::ostream& out) {
    out << "Usage: orchc <tokens|check|ast|symbols|ir|ir-json|cost|certify|run> <source.orch>\n"
        << "       orchc <source.orch>\n"
        << "Options: --chars-per-token <n>   UTF-8 bytes per estimated input token (default "
        << defaultCharsPerToken() << "; applied per template/argument fragment)\n"
        << "                                 input soundness assumes complete-request usage is compositional\n"
        << "         --seed <n>            seed for the offline mock runtime used by 'run'\n"
        << "         --retry-failure <p>   percentage chance one retry attempt fails (default 50)\n"
        << "         --pin <name>=<n>      pin an input or secret's token length for 'run'\n"
        << "         --pin <name>=true     pin a boolean input or secret for 'run'\n"
        << "         --json                structured JSON output for 'run'\n"
        << "         --audit-unsafe        bypass cost/relational gates for offline witness runs\n"
        << "         --request-sensitive-oracle   include modeled request content in offline model draws\n"
        << "Compatibility flags: --tokens, --check\n";
}

Command parseCommand(const std::string& value) {
    if (value == "tokens" || value == "--tokens") return Command::Tokens;
    if (value == "check" || value == "--check") return Command::Check;
    if (value == "ast") return Command::Ast;
    if (value == "symbols") return Command::Symbols;
    if (value == "ir") return Command::Ir;
    if (value == "ir-json") return Command::IrJson;
    if (value == "cost") return Command::Cost;
    if (value == "certify") return Command::Certify;
    if (value == "run") return Command::Run;
    return Command::Invalid;
}

bool readSource(const std::string& path, std::string& source) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return false;
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    source = buffer.str();
    return static_cast<bool>(input) || input.eof();
}

void printDiagnostics(const DiagnosticBag& diagnostics) {
    const std::string rendered = formatDiagnostics(diagnostics);
    if (!rendered.empty()) {
        std::cerr << rendered;
    }
}

bool parseSizeValue(const std::string& text, std::size_t& value) {
    if (text.empty()) {
        return false;
    }
    std::size_t parsed = 0;
    for (const char character : text) {
        if (character < '0' || character > '9') {
            return false;
        }
        const std::size_t digit = static_cast<std::size_t>(character - '0');
        if (parsed > (std::numeric_limits<std::size_t>::max() - digit) / 10) {
            return false;
        }
        parsed = parsed * 10 + digit;
    }
    value = parsed;
    return true;
}

// Pulls the option flags out of the argument list, leaving the positional
// command and path behind.
bool collectArguments(int argc, char* argv[], Invocation& invocation) {
    std::vector<std::string> positional;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--chars-per-token") {
            if (index + 1 >= argc) {
                return false;
            }
            const long value = std::strtol(argv[++index], nullptr, 10);
            if (value < 1) {
                return false;
            }
            invocation.options.charsPerToken = static_cast<std::size_t>(value);
            continue;
        }
        if (argument == "--seed") {
            if (index + 1 >= argc) {
                return false;
            }
            invocation.run.seed = std::strtoull(argv[++index], nullptr, 10);
            continue;
        }
        if (argument == "--pin") {
            // --pin name=tokens, or --pin name=true / --pin name=false
            if (index + 1 >= argc) {
                return false;
            }
            const std::string spec = argv[++index];
            const std::size_t split = spec.find('=');
            if (split == std::string::npos || split == 0) {
                return false;
            }
            const std::string name = spec.substr(0, split);
            const std::string value = spec.substr(split + 1);
            if (value == "true" || value == "false") {
                invocation.run.pinnedFlags[name] = value == "true";
            } else {
                std::size_t length = 0;
                if (!parseSizeValue(value, length)) {
                    return false;
                }
                invocation.run.pinnedLengths[name] = length;
            }
            continue;
        }
        if (argument == "--retry-failure") {
            if (index + 1 >= argc) {
                return false;
            }
            const long value = std::strtol(argv[++index], nullptr, 10);
            if (value < 0 || value > 100) {
                return false;
            }
            invocation.run.retryFailurePercent = static_cast<unsigned>(value);
            continue;
        }
        if (argument == "--audit-unsafe") {
            invocation.run.auditUnsafe = true;
            continue;
        }
        if (argument == "--request-sensitive-oracle") {
            invocation.run.requestSensitiveOracle = true;
            continue;
        }
        if (argument == "--json") {
            invocation.jsonOutput = true;
            continue;
        }
        positional.push_back(argument);
    }

    if (positional.size() == 1) {
        invocation.command = Command::Check;
        invocation.path = positional[0];
        return !invocation.jsonOutput && !invocation.run.auditUnsafe &&
               !invocation.run.requestSensitiveOracle;
    }
    if (positional.size() == 2) {
        invocation.command = parseCommand(positional[0]);
        invocation.path = positional[1];
        return invocation.command != Command::Invalid &&
               ((!invocation.jsonOutput && !invocation.run.auditUnsafe &&
                 !invocation.run.requestSensitiveOracle) ||
                invocation.command == Command::Run);
    }
    return false;
}

}  // namespace

}  // namespace orchlang

int main(int argc, char* argv[]) {
    using namespace orchlang;

    Invocation invocation;
    if (!collectArguments(argc, argv, invocation) || invocation.path.empty()) {
        printUsage(std::cerr);
        return 2;
    }

    std::string source;
    if (!readSource(invocation.path, source)) {
        std::cerr << "orchc: cannot read source file '" << invocation.path << "'\n";
        return 2;
    }

    Lexer lexer(source, invocation.path);
    LexResult lexed = lexer.scan();
    if (invocation.command == Command::Tokens) {
        std::cout << formatTokens(lexed.tokens);
        printDiagnostics(lexed.diagnostics);
        return lexed.diagnostics.hasErrors() ? 1 : 0;
    }

    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();
    DiagnosticBag diagnostics;
    diagnostics.append(lexed.diagnostics);
    diagnostics.append(parsed.diagnostics);
    if (diagnostics.hasErrors()) {
        printDiagnostics(diagnostics);
        return 1;
    }

    SemanticAnalyzer analyzer(invocation.options);
    SemanticResult semantic = analyzer.analyze(parsed.program);
    diagnostics.append(semantic.diagnostics);

    if (invocation.command == Command::Ast) {
        std::cout << printAst(parsed.program);
        printDiagnostics(diagnostics);
        return diagnostics.hasErrors() ? 1 : 0;
    }
    if (invocation.command == Command::Symbols) {
        std::cout << formatSymbolTable(semantic.symbols);
        printDiagnostics(diagnostics);
        return diagnostics.hasErrors() ? 1 : 0;
    }

    // Everything past this point needs a well-typed program: a cost bound or a
    // certificate derived from an ill-typed workflow would mean nothing.
    if (diagnostics.hasErrors()) {
        printDiagnostics(diagnostics);
        return 1;
    }

    if (invocation.command == Command::Run) {
        Interpreter interpreter(invocation.run);
        RunResult run = interpreter.run(parsed.program, semantic);
        diagnostics.append(run.diagnostics);
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        std::cout << (invocation.jsonOutput ? printRunJson(run) : printRun(run));
        return 0;
    }

    CostAnalyzer costAnalyzer;
    CostResult cost = costAnalyzer.analyze(parsed.program, semantic);
    diagnostics.append(cost.diagnostics);

    RelationalAnalyzer relationalAnalyzer;
    RelationalResult relational = relationalAnalyzer.analyze(parsed.program, semantic);
    diagnostics.append(relational.diagnostics);

    if (invocation.command == Command::Cost) {
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        std::cout << printCertificateSummary(cost, semantic);
        if (!relational.obligations.empty()) {
            std::cout << "  relational obligations:\n";
            for (const RelationalObligation& obligation : relational.obligations) {
                std::cout << "    " << (obligation.discharged ? "discharged" : "FAILED") << "  if "
                          << obligation.guard << " (line " << obligation.location.line << "): "
                          << obligation.detail << '\n';
            }
        }
        for (const WorkflowCost& workflow : cost.workflows) {
            std::cout << "  derivation for " << workflow.name << ":\n";
            for (const DerivationStep& step : workflow.derivation) {
                std::cout << "    " << std::string(static_cast<std::size_t>(step.depth) * 2 + 2, ' ')
                          << step.rule << "  " << step.detail << "  => " << step.bound.total()
                          << " tokens\n";
            }
        }
        return 0;
    }

    if (diagnostics.hasErrors()) {
        printDiagnostics(diagnostics);
        return 1;
    }

    if (invocation.command == Command::Ir || invocation.command == Command::IrJson ||
        invocation.command == Command::Certify) {
        IRLowerer lowerer;
        IRBuildResult lowered = lowerer.lower(parsed.program, semantic);
        diagnostics.append(lowered.diagnostics);
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        if (invocation.command == Command::Ir) {
            std::cout << printIR(lowered.program);
        } else if (invocation.command == Command::IrJson) {
            std::cout << printIRJson(lowered.program);
        } else {
            std::cout << printCertificate(parsed.program, semantic, cost, lowered.program,
                                          relational, source);
        }
        return 0;
    }

    std::cout << "Check succeeded: " << parsed.program.workflows.size()
              << " workflow(s) passed lexical, syntax, type, information-flow, and cost analysis.\n";
    std::cout << printCertificateSummary(cost, semantic);
    return 0;
}
