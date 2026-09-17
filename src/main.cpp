#include "ast.hpp"
#include "certificate.hpp"
#include "cost_analyzer.hpp"
#include "diagnostic.hpp"
#include "interpreter.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"
#include "symbol_table.hpp"

#include <cstdlib>
#include <fstream>
#include <iostream>
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
};

void printUsage(std::ostream& out) {
    out << "Usage: orchc <tokens|check|ast|symbols|ir|ir-json|cost|certify|run> <source.orch>\n"
        << "       orchc <source.orch>\n"
        << "Options: --chars-per-token <n>   tokenization assumption for input tokens (default "
        << defaultCharsPerToken() << ";\n"
        << "                                 1 is unconditionally sound, larger is tighter)\n"
        << "         --seed <n>            seed for the offline mock runtime used by 'run'\n"
        << "         --retry-failure <p>   percentage chance one retry attempt fails (default 50)\n"
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
    std::ifstream input(path);
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
        positional.push_back(argument);
    }

    if (positional.size() == 1) {
        invocation.command = Command::Check;
        invocation.path = positional[0];
        return true;
    }
    if (positional.size() == 2) {
        invocation.command = parseCommand(positional[0]);
        invocation.path = positional[1];
        return invocation.command != Command::Invalid;
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
        std::cout << printRun(run);
        return 0;
    }

    CostAnalyzer costAnalyzer;
    CostResult cost = costAnalyzer.analyze(parsed.program, semantic);
    diagnostics.append(cost.diagnostics);

    if (invocation.command == Command::Cost) {
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        std::cout << printCertificateSummary(cost, semantic);
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
            std::cout << printCertificate(parsed.program, semantic, cost, lowered.program);
        }
        return 0;
    }

    std::cout << "Check succeeded: " << parsed.program.workflows.size()
              << " workflow(s) passed lexical, syntax, type, information-flow, and cost analysis.\n";
    std::cout << printCertificateSummary(cost, semantic);
    return 0;
}
