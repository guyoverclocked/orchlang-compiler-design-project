#include "ast.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"

#include <exception>
#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace orchlang {
namespace {

class TestFailure : public std::runtime_error {
public:
    explicit TestFailure(const std::string& message) : std::runtime_error(message) {}
};

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw TestFailure(message);
    }
}

struct Pipeline {
    LexResult lexed;
    ParseResult parsed;
    std::optional<SemanticResult> semantic;
};

Pipeline compileSource(const std::string& source) {
    Lexer lexer(source, "test.orch");
    LexResult lexed = lexer.scan();
    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();
    Pipeline result{std::move(lexed), std::move(parsed), std::nullopt};
    if (!result.lexed.diagnostics.hasErrors() && !result.parsed.diagnostics.hasErrors()) {
        SemanticAnalyzer analyzer;
        result.semantic = analyzer.analyze(result.parsed.program);
    }
    return result;
}

bool hasCode(const DiagnosticBag& diagnostics, const std::string& code) {
    for (const Diagnostic& diagnostic : diagnostics.all()) {
        if (diagnostic.code == code) {
            return true;
        }
    }
    return false;
}

bool hasCode(const Pipeline& pipeline, const std::string& code) {
    return hasCode(pipeline.lexed.diagnostics, code) || hasCode(pipeline.parsed.diagnostics, code) ||
           (pipeline.semantic && hasCode(pipeline.semantic->diagnostics, code));
}

void requireParsed(const Pipeline& pipeline) {
    require(!pipeline.lexed.diagnostics.hasErrors(), "lexing should succeed");
    require(!pipeline.parsed.diagnostics.hasErrors(), "parsing should succeed");
}

void requireSemanticallyValid(const Pipeline& pipeline) {
    requireParsed(pipeline);
    require(pipeline.semantic.has_value(), "semantic analysis should run");
    require(pipeline.semantic->success(), "semantic analysis should succeed");
}

const WorkflowDecl& onlyWorkflow(const Pipeline& pipeline) {
    require(pipeline.parsed.program.workflows.size() == 1, "exactly one workflow expected");
    require(static_cast<bool>(pipeline.parsed.program.workflows.front()), "workflow must be present");
    return *pipeline.parsed.program.workflows.front();
}

std::string validProgram() {
    return R"(workflow Demo budget 1000 {
  input ticket: text;
  secret API_KEY;
  model local = mock("offline") max_tokens 100;
  prompt classify(message: text) -> text = "Classify: {message}";
  let result: text = call classify(ticket) using local;
  require tokens(result) <= 100;
  output result;
})";
}

void testLexerKeywordAndLocation() {
    Pipeline pipeline = compileSource("workflow Demo budget 0 { output \"ok\"; }");
    require(!pipeline.lexed.diagnostics.hasErrors(), "keyword source should lex");
    require(pipeline.lexed.tokens[0].kind == TokenKind::Workflow, "first token should be workflow");
    require(pipeline.lexed.tokens[0].location.line == 1 && pipeline.lexed.tokens[0].location.column == 1,
            "workflow location should be 1:1");
}

void testLexerCommentAndIdentifier() {
    Pipeline pipeline = compileSource("// comment\nworkflow _Demo budget 0 { output \"ok\"; }");
    require(!pipeline.lexed.diagnostics.hasErrors(), "comment source should lex");
    require(pipeline.lexed.tokens[1].lexeme == "_Demo", "identifier should preserve underscores");
    require(pipeline.lexed.tokens[1].location.line == 2, "identifier line should follow comment");
}

void testLexerStringEscapes() {
    Pipeline pipeline = compileSource("workflow Demo budget 0 { output \"a\\n\\t\\\\b\"; }");
    require(!pipeline.lexed.diagnostics.hasErrors(), "supported escapes should lex");
    bool found = false;
    for (const Token& token : pipeline.lexed.tokens) {
        if (token.kind == TokenKind::StringLiteral) {
            found = token.lexeme == "a\n\t\\b";
        }
    }
    require(found, "string escape decoding should preserve decoded value");
}

void testLexerDecimalAndBoolean() {
    Lexer lexer("workflow Demo budget 0 { output 1.25; output true; }", "test.orch");
    LexResult result = lexer.scan();
    bool decimal = false;
    bool boolean = false;
    for (const Token& token : result.tokens) {
        decimal = decimal || token.kind == TokenKind::DecimalLiteral;
        boolean = boolean || token.kind == TokenKind::BooleanLiteral;
    }
    require(decimal && boolean, "decimal and boolean literals should tokenize");
}

void testLexerBadCharacter() {
    Pipeline pipeline = compileSource("workflow Demo budget 0 { @ output \"ok\"; }");
    require(hasCode(pipeline, "L001"), "unexpected character should report L001");
}

void testLexerUnterminatedString() {
    Pipeline pipeline = compileSource("workflow Demo budget 0 { output \"unterminated; }");
    require(hasCode(pipeline, "L002"), "unterminated string should report L002");
}

void testLexerLoneBang() {
    Pipeline pipeline = compileSource("workflow Demo budget 0 { require tokens(x) ! 1; output \"ok\"; }");
    require(hasCode(pipeline, "L001"), "lone bang should report L001");
}

void testParserFullStatementForms() {
    Pipeline pipeline = compileSource(validProgram());
    requireParsed(pipeline);
    const WorkflowDecl& workflow = onlyWorkflow(pipeline);
    require(workflow.statements.size() == 7, "all seven statement forms should parse");
    require(workflow.statements[0]->kind() == StmtKind::Input, "input AST node expected");
    require(workflow.statements[1]->kind() == StmtKind::Secret, "secret AST node expected");
    require(workflow.statements[2]->kind() == StmtKind::Model, "model AST node expected");
    require(workflow.statements[3]->kind() == StmtKind::Prompt, "prompt AST node expected");
    require(workflow.statements[4]->kind() == StmtKind::Let, "let AST node expected");
    require(workflow.statements[5]->kind() == StmtKind::Require, "require AST node expected");
    require(workflow.statements[6]->kind() == StmtKind::Output, "output AST node expected");
}

void testParserCallStructure() {
    Pipeline pipeline = compileSource(validProgram());
    requireParsed(pipeline);
    const auto& let = static_cast<const LetStmt&>(*onlyWorkflow(pipeline).statements[4]);
    require(let.call && let.call->promptName == "classify", "call should retain prompt name");
    require(let.call->modelName == "local", "call should retain model name");
    require(let.call->arguments.size() == 1, "call should retain one argument");
    require(let.call->arguments.front()->kind() == ExprKind::Identifier, "argument should be identifier expression");
}

void testParserEmptyWorkflow() {
    Pipeline pipeline = compileSource("workflow Empty budget 0 { }");
    requireParsed(pipeline);
    require(onlyWorkflow(pipeline).statements.empty(), "empty workflow should have no statements");
}

void testParserMissingSemicolon() {
    Pipeline pipeline = compileSource("workflow Broken budget 0 { input x: text output x; }");
    require(hasCode(pipeline, "P001"), "missing semicolon should report P001");
}

void testParserMultipleErrorRecovery() {
    Pipeline pipeline = compileSource("workflow Broken budget 0 { input : text; output ; }");
    require(pipeline.parsed.diagnostics.all().size() >= 2, "parser should report multiple independent syntax errors");
}

void testParserMissingClosingBrace() {
    Pipeline pipeline = compileSource("workflow Broken budget 0 { output \"ok\";");
    require(hasCode(pipeline, "P001"), "missing closing brace should report P001");
}

void testParserEmptyInput() {
    Pipeline pipeline = compileSource("");
    require(hasCode(pipeline, "P001"), "empty input should report a parse error");
}

void testParserLongIdentifier() {
    const std::string name = "exceptionally_descriptive_compiler_design_identifier_2026";
    Pipeline pipeline = compileSource("workflow Long budget 0 { input " + name + ": text; output " + name + "; }");
    requireParsed(pipeline);
    const auto& input = static_cast<const InputDecl&>(*onlyWorkflow(pipeline).statements[0]);
    require(input.name == name, "long identifier should not be truncated");
}

void testParserIntegerOverflow() {
    Pipeline pipeline = compileSource("workflow Large budget 999999999999999999999999999999999999 { output \"ok\"; }");
    require(hasCode(pipeline, "P004"), "oversized integer should report P004 without throwing");
}

void testParserInvalidCallArgument() {
    Pipeline pipeline = compileSource(
        "workflow BadCall budget 0 { model m = mock(\"x\") max_tokens 1; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(,) using m; output r; }");
    require(hasCode(pipeline, "P001"), "missing call argument should report P001");
}

void testParserUnexpectedStatement() {
    Pipeline pipeline = compileSource("workflow Bad budget 0 { unexpected; output \"ok\"; }");
    require(hasCode(pipeline, "P001"), "unknown statement should report P001");
}

void testAstPrinter() {
    Pipeline pipeline = compileSource(validProgram());
    requireParsed(pipeline);
    const std::string text = printAst(pipeline.parsed.program);
    require(text.find("Workflow Demo budget=1000") != std::string::npos, "AST printer should show workflow");
    require(text.find("Call classify(ticket) using local") != std::string::npos, "AST printer should show call");
}

void testSymbolTableLookup() {
    Pipeline pipeline = compileSource(validProgram());
    requireSemanticallyValid(pipeline);
    const std::size_t scope = pipeline.semantic->workflowScopes.at("Demo");
    const Symbol* input = pipeline.semantic->symbols.lookupLocal(scope, "ticket");
    const Symbol* prompt = pipeline.semantic->symbols.lookupLocal(scope, "classify");
    require(input && input->kind == SymbolKind::Input && input->type.kind == TypeKind::Text,
            "input lookup should return typed input symbol");
    require(prompt && prompt->prompt && prompt->prompt->parameters.size() == 1,
            "prompt lookup should retain signature");
}

void testSemanticValidProgram() {
    Pipeline pipeline = compileSource(validProgram());
    requireSemanticallyValid(pipeline);
    require(pipeline.semantic->declaredTokenTotals.at("Demo") == 100, "budget pass should calculate token total");
}

void testSemanticDuplicateSymbols() {
    Pipeline pipeline = compileSource("workflow D budget 0 { input x: text; input x: text; output x; }");
    require(hasCode(pipeline, "E201"), "duplicate declaration should report E201");
}

void testSemanticUndeclaredIdentifier() {
    Pipeline pipeline = compileSource("workflow U budget 0 { output missing; }");
    require(hasCode(pipeline, "E202"), "undeclared output should report E202");
}

void testSemanticTypeMismatch() {
    Pipeline pipeline = compileSource(
        "workflow T budget 10 { input x: text; model m = mock(\"x\") max_tokens 1; prompt p(a: text) -> integer = \"{a}\"; let r: text = call p(x) using m; output r; }");
    require(hasCode(pipeline, "E210"), "declared type mismatch should report E210");
}

void testSemanticUnknownPrompt() {
    Pipeline pipeline = compileSource(
        "workflow P budget 10 { input x: text; model m = mock(\"x\") max_tokens 1; let r: text = call missing(x) using m; output r; }");
    require(hasCode(pipeline, "E220"), "unknown prompt should report E220");
}

void testSemanticPromptArity() {
    Pipeline pipeline = compileSource(
        "workflow A budget 10 { input x: text; model m = mock(\"x\") max_tokens 1; prompt p(a: text, b: text) -> text = \"{a} {b}\"; let r: text = call p(x) using m; output r; }");
    require(hasCode(pipeline, "E221"), "wrong prompt arity should report E221");
}

void testSemanticPromptArgumentType() {
    Pipeline pipeline = compileSource(
        "workflow A budget 10 { input x: integer; model m = mock(\"x\") max_tokens 1; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(x) using m; output r; }");
    require(hasCode(pipeline, "E223"), "wrong prompt argument type should report E223");
}

void testSemanticPlaceholderUnknown() {
    Pipeline pipeline = compileSource(
        "workflow H budget 0 { prompt p(a: text) -> text = \"{missing}\"; output \"ok\"; }");
    require(hasCode(pipeline, "E222"), "unknown placeholder should report E222");
}

void testSemanticPlaceholderMissing() {
    Pipeline pipeline = compileSource(
        "workflow H budget 0 { prompt p(a: text, b: text) -> text = \"{a}\"; output \"ok\"; }");
    require(hasCode(pipeline, "E222"), "missing placeholder should report E222");
}

void testSemanticPlaceholderDuplicate() {
    Pipeline pipeline = compileSource(
        "workflow H budget 0 { prompt p(a: text) -> text = \"{a} {a}\"; output \"ok\"; }");
    require(hasCode(pipeline, "E222"), "duplicate placeholder should report E222");
}

void testSemanticUnknownModel() {
    Pipeline pipeline = compileSource(
        "workflow M budget 0 { input x: text; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(x) using no_model; output r; }");
    require(hasCode(pipeline, "E241"), "unknown model should report E241");
}

void testSemanticSecretCallExposure() {
    Pipeline pipeline = compileSource(
        "workflow S budget 10 { secret key; model m = mock(\"x\") max_tokens 1; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(key) using m; output r; }");
    require(hasCode(pipeline, "E230"), "secret prompt argument should report E230");
}

void testSemanticSecretOutputExposure() {
    Pipeline pipeline = compileSource("workflow S budget 0 { secret key; output key; }");
    require(hasCode(pipeline, "E230"), "secret output should report E230");
}

void testSemanticBudgetExceeded() {
    Pipeline pipeline = compileSource(
        "workflow B budget 5 { input x: text; model m = mock(\"x\") max_tokens 6; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(x) using m; output r; }");
    require(hasCode(pipeline, "E260"), "over-budget model call should report E260");
}

void testSemanticMissingOutput() {
    Pipeline pipeline = compileSource("workflow Missing budget 0 { input x: text; }");
    require(hasCode(pipeline, "E270"), "missing output should report E270");
}

void testSemanticMultipleOutputs() {
    Pipeline pipeline = compileSource("workflow Outputs budget 0 { output \"a\"; output \"b\"; }");
    require(hasCode(pipeline, "E271"), "multiple outputs should report E271");
}

void testSemanticMultipleDiagnostics() {
    Pipeline pipeline = compileSource(
        "workflow Many budget 1 { input x: integer; input x: text; secret key; model m = mock(\"x\") max_tokens 2; prompt p(a: text) -> integer = \"{bad}\"; let r: text = call p(key, x) using absent; output key; output r; }");
    require(pipeline.semantic.has_value(), "semantic analysis should run on valid syntax");
    require(pipeline.semantic->diagnostics.all().size() >= 7, "multiple independent semantic diagnostics expected");
    require(hasCode(pipeline, "E201") && hasCode(pipeline, "E222") && hasCode(pipeline, "E230") &&
                hasCode(pipeline, "E241") && hasCode(pipeline, "E271"),
            "multiple error categories should be retained");
}

void testSemanticDeclarationBeforeUse() {
    Pipeline pipeline = compileSource(
        "workflow Order budget 2 { input x: text; model m = mock(\"x\") max_tokens 1; let r: text = call later(x) using m; prompt later(a: text) -> text = \"{a}\"; output r; }");
    require(hasCode(pipeline, "E220"), "call before prompt declaration should report E220");
}

void testSemanticUnknownRequirementSubject() {
    Pipeline pipeline = compileSource("workflow R budget 0 { require tokens(missing) <= 1; output \"ok\"; }");
    require(hasCode(pipeline, "E202"), "unknown requirement subject should report E202");
}

void testSemanticZeroBudgetWithoutCalls() {
    Pipeline pipeline = compileSource("workflow Zero budget 0 { input x: text; output x; }");
    requireSemanticallyValid(pipeline);
    require(pipeline.semantic->declaredTokenTotals.at("Zero") == 0, "zero-call workflow should have zero token bound");
}

void testOutputLiteralExpression() {
    Pipeline pipeline = compileSource("workflow Literal budget 0 { output \"done\"; }");
    requireSemanticallyValid(pipeline);
    const auto& output = static_cast<const OutputStmt&>(*onlyWorkflow(pipeline).statements.front());
    require(output.value && output.value->kind() == ExprKind::StringLiteral, "output literal should be an AST expression");
}

void testIrValidLowering() {
    Pipeline pipeline = compileSource(validProgram());
    requireSemanticallyValid(pipeline);
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    require(lowered.success(), "valid program should lower to IR");
    require(lowered.program.workflows.size() == 1, "one workflow IR expected");
    const WorkflowIR& workflow = lowered.program.workflows.front();
    require(workflow.nodes.size() == 7, "IR should contain one node per statement");
    require(workflow.nodes[4].kind == IRNodeKind::Call && workflow.nodes[4].dependencies.size() == 3,
            "call IR node should depend on prompt, model, and input");
}

void testIrRefusesInvalidProgram() {
    Pipeline pipeline = compileSource("workflow Invalid budget 0 { output missing; }");
    require(pipeline.semantic.has_value() && !pipeline.semantic->success(), "program should be semantically invalid");
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    require(hasCode(lowered.diagnostics, "I001"), "IR lowerer should refuse semantic errors");
}

void testIrDependencyCycleDetector() {
    WorkflowIR cyclic;
    cyclic.workflowName = "Cycle";
    cyclic.nodes.push_back({1, IRNodeKind::Call, "one", {TypeKind::Text}, {2}, {}, {}});
    cyclic.nodes.push_back({2, IRNodeKind::Call, "two", {TypeKind::Text}, {1}, {}, {}});
    std::vector<int> cycle;
    require(hasDependencyCycle(cyclic, &cycle), "cycle detector should identify a cycle");
    require(cycle.size() >= 3 && cycle.front() == cycle.back(), "cycle trace should close the loop");
}

void testIrJsonExport() {
    Pipeline pipeline = compileSource(validProgram());
    requireSemanticallyValid(pipeline);
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    const std::string json = printIRJson(lowered.program);
    require(json.find("\"workflows\"") != std::string::npos && json.find("\"Call\"") != std::string::npos,
            "JSON export should serialize IR node kinds");
}

struct TestCase {
    std::string name;
    std::function<void()> function;
};

}  // namespace
}  // namespace orchlang

int main() {
    using namespace orchlang;
    const std::vector<TestCase> tests = {
        {"lexer keyword and location", testLexerKeywordAndLocation},
        {"lexer comment and identifier", testLexerCommentAndIdentifier},
        {"lexer string escapes", testLexerStringEscapes},
        {"lexer decimal and boolean", testLexerDecimalAndBoolean},
        {"lexer bad character", testLexerBadCharacter},
        {"lexer unterminated string", testLexerUnterminatedString},
        {"lexer lone bang", testLexerLoneBang},
        {"parser full statement forms", testParserFullStatementForms},
        {"parser call structure", testParserCallStructure},
        {"parser empty workflow", testParserEmptyWorkflow},
        {"parser missing semicolon", testParserMissingSemicolon},
        {"parser multiple error recovery", testParserMultipleErrorRecovery},
        {"parser missing closing brace", testParserMissingClosingBrace},
        {"parser empty input", testParserEmptyInput},
        {"parser long identifier", testParserLongIdentifier},
        {"parser integer overflow", testParserIntegerOverflow},
        {"parser invalid call argument", testParserInvalidCallArgument},
        {"parser unexpected statement", testParserUnexpectedStatement},
        {"AST printer", testAstPrinter},
        {"symbol table lookup", testSymbolTableLookup},
        {"semantic valid program", testSemanticValidProgram},
        {"semantic duplicate symbols", testSemanticDuplicateSymbols},
        {"semantic undeclared identifier", testSemanticUndeclaredIdentifier},
        {"semantic type mismatch", testSemanticTypeMismatch},
        {"semantic unknown prompt", testSemanticUnknownPrompt},
        {"semantic prompt arity", testSemanticPromptArity},
        {"semantic prompt argument type", testSemanticPromptArgumentType},
        {"semantic placeholder unknown", testSemanticPlaceholderUnknown},
        {"semantic placeholder missing", testSemanticPlaceholderMissing},
        {"semantic placeholder duplicate", testSemanticPlaceholderDuplicate},
        {"semantic unknown model", testSemanticUnknownModel},
        {"semantic secret prompt exposure", testSemanticSecretCallExposure},
        {"semantic secret output exposure", testSemanticSecretOutputExposure},
        {"semantic budget exceeded", testSemanticBudgetExceeded},
        {"semantic missing output", testSemanticMissingOutput},
        {"semantic multiple outputs", testSemanticMultipleOutputs},
        {"semantic multiple diagnostics", testSemanticMultipleDiagnostics},
        {"semantic declaration before use", testSemanticDeclarationBeforeUse},
        {"semantic unknown requirement subject", testSemanticUnknownRequirementSubject},
        {"semantic zero budget", testSemanticZeroBudgetWithoutCalls},
        {"output literal expression", testOutputLiteralExpression},
        {"IR valid lowering", testIrValidLowering},
        {"IR refuses invalid program", testIrRefusesInvalidProgram},
        {"IR dependency cycle detector", testIrDependencyCycleDetector},
        {"IR JSON export", testIrJsonExport},
    };

    std::size_t passed = 0;
    for (const TestCase& test : tests) {
        try {
            test.function();
            ++passed;
            std::cout << "PASS " << test.name << '\n';
        } catch (const std::exception& error) {
            std::cerr << "FAIL " << test.name << ": " << error.what() << '\n';
        }
    }
    std::cout << "Passed " << passed << '/' << tests.size() << " tests.\n";
    return passed == tests.size() ? 0 : 1;
}
