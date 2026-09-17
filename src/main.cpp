#include "ast.hpp"
#include "diagnostic.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"
#include "symbol_table.hpp"

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace orchlang {

namespace {

enum class Command { Tokens, Check, Ast, Symbols, Ir, IrJson, Invalid };

struct Invocation {
    Command command{Command::Invalid};
    std::string path;
};

void printUsage(std::ostream& out) {
    out << "Usage: orchc <tokens|check|ast|symbols|ir|ir-json> <source.orch>\n"
        << "       orchc <source.orch>\n"
        << "Compatibility flags: --tokens, --check\n";
}

Command parseCommand(const std::string& value) {
    if (value == "tokens" || value == "--tokens") return Command::Tokens;
    if (value == "check" || value == "--check") return Command::Check;
    if (value == "ast") return Command::Ast;
    if (value == "symbols") return Command::Symbols;
    if (value == "ir") return Command::Ir;
    if (value == "ir-json") return Command::IrJson;
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

void appendDiagnostics(DiagnosticBag& destination, const DiagnosticBag& source) {
    destination.append(source);
}

}  // namespace

}  // namespace orchlang

int main(int argc, char* argv[]) {
    using namespace orchlang;

    Invocation invocation;
    if (argc == 2) {
        invocation.command = Command::Check;
        invocation.path = argv[1];
    } else if (argc == 3) {
        invocation.command = parseCommand(argv[1]);
        invocation.path = argv[2];
    }
    if (invocation.command == Command::Invalid || invocation.path.empty()) {
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
    appendDiagnostics(diagnostics, lexed.diagnostics);
    appendDiagnostics(diagnostics, parsed.diagnostics);
    if (diagnostics.hasErrors()) {
        printDiagnostics(diagnostics);
        return 1;
    }

    SemanticAnalyzer analyzer;
    SemanticResult semantic = analyzer.analyze(parsed.program);
    appendDiagnostics(diagnostics, semantic.diagnostics);

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
    if (invocation.command == Command::Ir || invocation.command == Command::IrJson) {
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        IRLowerer lowerer;
        IRBuildResult lowered = lowerer.lower(parsed.program, semantic);
        appendDiagnostics(diagnostics, lowered.diagnostics);
        if (diagnostics.hasErrors()) {
            printDiagnostics(diagnostics);
            return 1;
        }
        if (invocation.command == Command::Ir) {
            std::cout << printIR(lowered.program);
        } else {
            std::cout << printIRJson(lowered.program);
        }
        return 0;
    }

    if (diagnostics.hasErrors()) {
        printDiagnostics(diagnostics);
        return 1;
    }
    std::cout << "Check succeeded: " << parsed.program.workflows.size()
              << " workflow(s) passed lexical, syntax, and semantic analysis.\n";
    for (const auto& workflow : parsed.program.workflows) {
        if (!workflow) {
            continue;
        }
        const auto total = semantic.declaredTokenTotals.find(workflow->name);
        const std::size_t tokenTotal = total == semantic.declaredTokenTotals.end() ? 0 : total->second;
        std::cout << "  " << workflow->name << ": declared token bound " << tokenTotal
                  << " / budget " << workflow->budget << "\n";
    }
    return 0;
}
