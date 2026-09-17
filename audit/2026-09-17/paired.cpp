#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"
#include "cost_analyzer.hpp"
#include "interpreter.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace orchlang;
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    std::ifstream input(argv[1]);
    std::string text((std::istreambuf_iterator<char>(input)), {});
    auto lex = Lexer(text, argv[1]).scan();
    auto parsed = Parser(lex.tokens).parse();
    auto semantic = SemanticAnalyzer().analyze(parsed.program);
    auto cost = CostAnalyzer().analyze(parsed.program, semantic);
    if (lex.diagnostics.hasErrors() || parsed.diagnostics.hasErrors() || !semantic.success() || !cost.success()) return 3;
    auto& secret = static_cast<SecretDecl&>(*parsed.program.workflows[0]->statements[0]);
    // Audit-only input injection: the mock has no store-input API and initializes
    // secret token counts from the declaration. Analyze ONCE with bound 1, then
    // set its initializer to 0 and 1 (both within that original bound).
    // No analyzer or interpreter implementation is changed. RNG consumption is
    // identical: Secret consumes one flag draw for either token count.
    RunOptions options;
    options.seed = 1;
    secret.tokenBound = 0;
    auto left = Interpreter(options).run(parsed.program, semantic);
    secret.tokenBound = 1;
    auto right = Interpreter(options).run(parsed.program, semantic);
    std::cout << "Analyzed original bound: " << cost.workflows[0].bound.total() << "\n";
    std::cout << "Secret token count 0:\n" << printRun(left);
    std::cout << "Secret token count 1:\n" << printRun(right);
    const auto& a = left.workflows[0];
    const auto& b = right.workflows[0];
    bool witness = a.totalTokens() != b.totalTokens() && a.outputTokens == b.outputTokens;
    std::cout << "Same model output count, unequal total: " << (witness ? "YES" : "NO") << "\n";
    return witness ? 0 : 1;
}
