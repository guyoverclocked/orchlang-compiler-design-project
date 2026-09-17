#include "ast.hpp"
#include "certificate.hpp"
#include "cost_analyzer.hpp"
#include "interpreter.hpp"
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
    std::optional<CostResult> cost;
};

Pipeline compileSource(const std::string& source) {
    Lexer lexer(source, "test.orch");
    LexResult lexed = lexer.scan();
    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();
    Pipeline result{std::move(lexed), std::move(parsed), std::nullopt, std::nullopt};
    if (!result.lexed.diagnostics.hasErrors() && !result.parsed.diagnostics.hasErrors()) {
        SemanticAnalyzer analyzer;
        result.semantic = analyzer.analyze(result.parsed.program);
        if (result.semantic->success()) {
            CostAnalyzer costAnalyzer;
            result.cost = costAnalyzer.analyze(result.parsed.program, *result.semantic);
        }
    }
    return result;
}

const WorkflowCost& onlyCost(const Pipeline& pipeline) {
    require(pipeline.cost.has_value(), "cost analysis should run");
    require(pipeline.cost->workflows.size() == 1, "exactly one workflow cost expected");
    return pipeline.cost->workflows.front();
}

Symbol lookupSymbol(const Pipeline& pipeline, const std::string& workflow,
                    const std::string& name) {
    require(pipeline.semantic.has_value(), "semantic analysis should run");
    const auto scope = pipeline.semantic->workflowScopes.find(workflow);
    require(scope != pipeline.semantic->workflowScopes.end(), "workflow scope should exist");
    const Symbol* symbol = pipeline.semantic->symbols.lookup(scope->second, name);
    require(symbol != nullptr, "symbol '" + name + "' should be declared");
    return *symbol;
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
           (pipeline.semantic && hasCode(pipeline.semantic->diagnostics, code)) ||
           (pipeline.cost && hasCode(pipeline.cost->diagnostics, code));
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
  input ticket: text max_tokens 40;
  secret API_KEY;
  model local = mock("offline") max_tokens 100;
  prompt classify(message: text) -> text = "Classify: {message}";
  let result: text = call classify(ticket) using local;
  require tokens(result) <= 100;
  output result;
})";
}


// ---------------------------------------------------------------------------
// Control flow and the cost algebra
// ---------------------------------------------------------------------------

std::string branchingProgram() {
    return R"(workflow Branch budget 5000 {
  input ticket: text max_tokens 10;
  model small = mock("s") max_tokens 100;
  model large = mock("l") max_tokens 900;
  prompt p(a: text) -> text = "{a}";
  let severity: text = call p(ticket) using small;
  if tokens(severity) <= 100 {
    let cheap: text = call p(ticket) using small;
  } else {
    let dear: text = call p(ticket) using large;
  }
  output severity;
})";
}

void testParserParsesBranch() {
    Pipeline pipeline = compileSource(branchingProgram());
    requireParsed(pipeline);
    const WorkflowDecl& workflow = onlyWorkflow(pipeline);
    bool found = false;
    for (const auto& statement : workflow.statements) {
        if (statement && statement->kind() == StmtKind::If) {
            const auto& branch = static_cast<const IfStmt&>(*statement);
            require(branch.hasElse, "the else arm should be recorded");
            require(branch.thenBranch.size() == 1, "the then arm should hold one statement");
            require(branch.elseBranch.size() == 1, "the else arm should hold one statement");
            found = true;
        }
    }
    require(found, "an if statement should be parsed");
}

void testCostBranchTakesMaximum() {
    Pipeline pipeline = compileSource(branchingProgram());
    requireSemanticallyValid(pipeline);
    const WorkflowCost& cost = onlyCost(pipeline);
    // first call 100 + max(cheap 100, dear 900) = 1000 guaranteed tokens,
    // never the 1100 a naive sum over all syntactic calls would report.
    require(cost.bound.guaranteed == 1000, "a branch should cost its more expensive arm, not both");
}

void testCostRetryMultiplies() {
    Pipeline pipeline = compileSource(R"(workflow R budget 5000 {
  input d: text max_tokens 4;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  retry 4 { let attempt: text = call p(d) using m; }
  output d;
})");
    requireSemanticallyValid(pipeline);
    require(onlyCost(pipeline).bound.guaranteed == 400, "four attempts should cost four times one");
}

void testCostRetryOverrunIsCaught() {
    Pipeline pipeline = compileSource(R"(workflow R budget 150 {
  input d: text max_tokens 4;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  retry 3 { let attempt: text = call p(d) using m; }
  output d;
})");
    require(hasCode(pipeline, "E260"), "a retry that overruns the budget should report E260");
}

void testCostSeparatesGuaranteedFromEstimated() {
    Pipeline pipeline = compileSource(R"(workflow C budget 5000 {
  input d: text max_tokens 30;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(d) using m;
  output r;
})");
    requireSemanticallyValid(pipeline);
    const WorkflowCost& cost = onlyCost(pipeline);
    require(cost.bound.guaranteed == 100, "output tokens are provider-capped and need no assumption");
    require(cost.bound.estimated == 31, "input tokens are the template plus the declared argument bound");
    require(cost.bound.total() == 131, "the total is the sum of both components");
}

void testCostAssumptionChangesOnlyEstimatedHalf() {
    const std::string source = R"(workflow C budget 5000 {
  input d: text max_tokens 30;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(d) using m;
  output r;
})";
    Lexer lexer(source, "test.orch");
    LexResult lexed = lexer.scan();
    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();

    AnalysisOptions strict;
    strict.charsPerToken = 1;
    SemanticAnalyzer analyzer(strict);
    SemanticResult semantic = analyzer.analyze(parsed.program);
    require(semantic.success(), "the stricter assumption should still type check");
    CostAnalyzer costAnalyzer;
    CostResult cost = costAnalyzer.analyze(parsed.program, semantic);
    require(cost.workflows.front().bound.guaranteed == 100,
            "the guaranteed half must not move with the tokenizer assumption");
    require(cost.workflows.front().bound.estimated > 31,
            "a stricter assumption should widen the estimated half");
}

void testEmptyBranchArmCostsNothing() {
    Pipeline pipeline = compileSource(R"(workflow E budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 50;
  prompt p(a: text) -> text = "{a}";
  let s: text = call p(t) using m;
  if tokens(s) <= 50 { } else { let x: text = call p(t) using m; }
  output s;
})");
    requireSemanticallyValid(pipeline);
    require(onlyCost(pipeline).bound.guaranteed == 100, "an empty arm still loses to the costly arm");
}

// ---------------------------------------------------------------------------
// Requirements
// ---------------------------------------------------------------------------

void testRequireViolationIsReported() {
    Pipeline pipeline = compileSource(R"(workflow Q budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 600;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  require tokens(r) <= 5;
  output r;
})");
    require(hasCode(pipeline, "E262"), "a requirement stricter than the derived bound should fail");
}

void testRequireSatisfiedByBound() {
    Pipeline pipeline = compileSource(R"(workflow Q budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 600;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  require tokens(r) <= 600;
  output r;
})");
    requireSemanticallyValid(pipeline);
}

void testRequireOnUnboundedSubject() {
    Pipeline pipeline = compileSource(R"(workflow Q budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 600;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  require tokens(m) <= 600;
  output r;
})");
    require(hasCode(pipeline, "E263"), "a model name carries no token bound");
}

void testRequireLowerBoundIsUndecidable() {
    Pipeline pipeline = compileSource(R"(workflow Q budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 600;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  require tokens(r) > 5;
  output r;
})");
    require(hasCode(pipeline, "E264"), "a lower bound cannot be discharged from an upper bound");
}

void testUnboundedInputReachingPromptIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow U budget 5000 {
  input t: text;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  output r;
})");
    require(hasCode(pipeline, "E261"), "an unbounded input feeding a prompt should be rejected");
}

// ---------------------------------------------------------------------------
// Information flow
// ---------------------------------------------------------------------------

void testLabelLatticeJoinAndOrder() {
    const Label bottom = publicTrusted();
    const Label secret{Confidentiality::Secret, Integrity::Trusted};
    const Label untrusted{Confidentiality::Public, Integrity::Untrusted};
    const Label top = join(secret, untrusted);
    require(top.isSecret() && top.isUntrusted(), "the join should take both components");
    require(flowsTo(bottom, top), "the bottom label flows everywhere");
    require(!flowsTo(secret, bottom), "a secret may not flow to a public position");
    require(!flowsTo(untrusted, bottom), "untrusted data may not flow to a trusted position");
    require(join(bottom, bottom) == bottom, "the join is idempotent at the bottom");
}

std::string injectionProgram(const char* sinkArgument) {
    return std::string(R"(workflow I budget 5000 {
  input page: text untrusted max_tokens 40;
  model m = mock("m") max_tokens 100;
  tool publish(body: text);
  prompt p(a: text) -> text = "{a}";
  let summary: text = call p(page) using m;
  endorse(summary) as vetted: text because "validated offline";
  emit publish()") + sinkArgument + R"();
  output summary;
})";
}

void testUntrustedInputTaintsModelOutput() {
    Pipeline pipeline = compileSource(injectionProgram("vetted"));
    requireSemanticallyValid(pipeline);
    const Symbol summary = lookupSymbol(pipeline, "I", "summary");
    require(summary.label.isUntrusted(),
            "a model answer derived from untrusted input must itself be untrusted");
    const Symbol vetted = lookupSymbol(pipeline, "I", "vetted");
    require(!vetted.label.isUntrusted(), "endorsement should restore integrity");
}

void testUntrustedValueCannotReachSink() {
    Pipeline pipeline = compileSource(injectionProgram("summary"));
    require(hasCode(pipeline, "E233"),
            "unendorsed untrusted data reaching a tool should report E233");
}

void testSecretCannotReachSink() {
    Pipeline pipeline = compileSource(R"(workflow S budget 5000 {
  input t: text max_tokens 4;
  secret key: text;
  model m = mock("m") max_tokens 50;
  tool notify(body: text);
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  emit notify(key);
  output r;
})");
    require(hasCode(pipeline, "E232"), "a secret reaching a tool should report E232");
}

void testSecretGuardedEffectIsImplicitFlow() {
    Pipeline pipeline = compileSource(R"(workflow S budget 5000 {
  input t: text max_tokens 4;
  secret alert: boolean;
  model m = mock("m") max_tokens 50;
  tool notify(body: text);
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  if alert { emit notify(r); }
  output r;
})");
    require(hasCode(pipeline, "E234"),
            "an effect guarded by a secret leaks through whether it happens");
}

void testUntrustedGuardedEffectIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow S budget 5000 {
  input flag: boolean untrusted max_tokens 1;
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 50;
  tool notify(body: text);
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  if flag { emit notify(r); }
  output r;
})");
    require(hasCode(pipeline, "E235"),
            "an effect decided by untrusted data should be rejected");
}

void testDeclassificationClearsConfidentiality() {
    Pipeline pipeline = compileSource(R"(workflow D budget 5000 {
  input t: text max_tokens 4;
  secret key: text max_tokens 8;
  model m = mock("m") max_tokens 50;
  prompt p(a: text) -> text = "{a}";
  declassify(key) as fingerprint: text because "only a hash prefix is forwarded";
  let r: text = call p(fingerprint) using m;
  output r;
})");
    requireSemanticallyValid(pipeline);
    const Symbol fingerprint = lookupSymbol(pipeline, "D", "fingerprint");
    require(!fingerprint.label.isSecret(), "declassification should clear confidentiality");
}

void testReclassificationIsRecordedWithJustification() {
    Pipeline pipeline = compileSource(injectionProgram("vetted"));
    requireSemanticallyValid(pipeline);
    require(pipeline.semantic->reclassifications.size() == 1, "the endorsement should be recorded");
    const ReclassificationSite& site = pipeline.semantic->reclassifications.front();
    require(site.endorsement, "the recorded site should be an endorsement");
    require(site.reason == "validated offline", "the written justification should be preserved");
    require(site.from.isUntrusted() && !site.to.isUntrusted(), "the label change should be recorded");
}

void testEmptyJustificationIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow D budget 5000 {
  input t: text max_tokens 4;
  secret key: text;
  declassify(key) as fingerprint: text because "";
  output t;
})");
    require(hasCode(pipeline, "P006"), "an empty justification should be rejected");
}

void testPcLabelSurvivesDeclassificationInsideSecretBranch() {
    Pipeline pipeline = compileSource(R"(workflow P budget 5000 {
  input t: text max_tokens 4;
  secret alert: boolean;
  model m = mock("m") max_tokens 50;
  tool notify(body: text);
  prompt p(a: text) -> text = "{a}";
  let r: text = call p(t) using m;
  if alert { endorse(r) as ok: text because "checked"; emit notify(ok); }
  output r;
})");
    require(hasCode(pipeline, "E234"),
            "relabelling inside a secret branch must not launder the program counter");
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

void testUnknownToolIsReported() {
    Pipeline pipeline = compileSource(R"(workflow T budget 5000 {
  input t: text max_tokens 4;
  output t;
  emit missing(t);
})");
    require(hasCode(pipeline, "E242"), "emitting to an undeclared tool should report E242");
}

void testToolArityAndTypesAreChecked() {
    Pipeline pipeline = compileSource(R"(workflow T budget 5000 {
  input t: text max_tokens 4;
  tool notify(body: text, level: integer);
  emit notify(t);
  output t;
})");
    require(hasCode(pipeline, "E243"), "a tool arity mismatch should report E243");

    Pipeline typed = compileSource(R"(workflow T budget 5000 {
  input t: text max_tokens 4;
  tool notify(level: integer);
  emit notify(t);
  output t;
})");
    require(hasCode(typed, "E244"), "a tool argument type mismatch should report E244");
}

void testCleanSinkIsAccepted() {
    Pipeline pipeline = compileSource(R"(workflow T budget 5000 {
  input t: text max_tokens 4;
  tool notify(body: text);
  emit notify(t);
  output t;
})");
    requireSemanticallyValid(pipeline);
}

// ---------------------------------------------------------------------------
// Scoping and the certificate
// ---------------------------------------------------------------------------

void testBranchBindingDoesNotEscape() {
    Pipeline pipeline = compileSource(R"(workflow B budget 5000 {
  input t: text max_tokens 4;
  model m = mock("m") max_tokens 50;
  prompt p(a: text) -> text = "{a}";
  let s: text = call p(t) using m;
  if tokens(s) <= 50 { let inner: text = call p(t) using m; }
  output inner;
})");
    require(hasCode(pipeline, "E202"), "a binding made inside a branch should not escape it");
}

void testCertificateRecordsBoundAndLabels() {
    Pipeline pipeline = compileSource(injectionProgram("vetted"));
    requireSemanticallyValid(pipeline);
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    require(lowered.success(), "IR lowering should succeed");
    const std::string certificate =
        printCertificate(pipeline.parsed.program, *pipeline.semantic, *pipeline.cost, lowered.program);
    require(certificate.find("orchlang-safety-certificate") != std::string::npos,
            "the certificate should name its format");
    require(certificate.find("\"chars_per_token\": 4") != std::string::npos,
            "the certificate should record the tokenization assumption it relied on");
    require(certificate.find("\"guaranteed_tokens\"") != std::string::npos,
            "the certificate should separate the guaranteed component");
    require(certificate.find("validated offline") != std::string::npos,
            "the certificate should carry every written justification");
    require(certificate.find("\"tool\": \"publish\"") != std::string::npos,
            "the certificate should list the sinks it cleared");
}

void testIrCarriesRegionsAndRepeatFactors() {
    Pipeline pipeline = compileSource(R"(workflow R budget 5000 {
  input d: text max_tokens 4;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  retry 3 { let attempt: text = call p(d) using m; }
  output d;
})");
    requireSemanticallyValid(pipeline);
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    require(lowered.success(), "IR lowering should succeed");
    bool found = false;
    for (const IRNode& node : lowered.program.workflows.front().nodes) {
        if (node.kind == IRNodeKind::Call) {
            require(node.repeatFactor == 3, "a call inside retry 3 may run three times");
            require(node.region != "root", "a call inside retry should sit in its own region");
            found = true;
        }
    }
    require(found, "the retried call should be lowered");
}

void testSaturatingArithmeticNeverWraps() {
    require(addTokens(saturatedTokens(), 1) == saturatedTokens(), "addition should saturate");
    require(multiplyTokens(saturatedTokens(), 2) == saturatedTokens(), "multiplication should saturate");
    require(multiplyTokens(0, 1000) == 0, "an empty body costs nothing however often it repeats");
    require(maxTokens(3, 9) == 9, "the maximum should pick the larger bound");
}


// ---------------------------------------------------------------------------
// The offline mock runtime, which is what makes the bound falsifiable
// ---------------------------------------------------------------------------

std::string retryProgram() {
    return R"(workflow M budget 100000 {
  input d: text max_tokens 40;
  model m = mock("m") max_tokens 120;
  prompt p(a: text) -> text = "{a}";
  retry 4 { let attempt: text = call p(d) using m; }
  output d;
})";
}

RunResult runWith(const Pipeline& pipeline, std::uint64_t seed) {
    RunOptions options;
    options.seed = seed;
    Interpreter interpreter(options);
    return interpreter.run(pipeline.parsed.program, *pipeline.semantic);
}

void testRunIsDeterministicForASeed() {
    Pipeline pipeline = compileSource(retryProgram());
    requireSemanticallyValid(pipeline);
    const RunResult first = runWith(pipeline, 12345);
    const RunResult second = runWith(pipeline, 12345);
    require(first.success() && second.success(), "both runs should succeed");
    require(first.workflows.front().totalTokens() == second.workflows.front().totalTokens(),
            "the same seed must replay the same execution");
}

void testRunStaysWithinCertifiedBound() {
    Pipeline pipeline = compileSource(retryProgram());
    requireSemanticallyValid(pipeline);
    const std::size_t bound = onlyCost(pipeline).bound.total();
    for (std::uint64_t seed = 1; seed <= 200; ++seed) {
        const RunResult result = runWith(pipeline, seed);
        require(result.success(), "the run should succeed");
        require(result.workflows.front().totalTokens() <= bound,
                "no execution may exceed the certified bound");
    }
}

void testRunNeverExceedsDeclaredRetryBound() {
    Pipeline pipeline = compileSource(retryProgram());
    requireSemanticallyValid(pipeline);
    for (std::uint64_t seed = 1; seed <= 100; ++seed) {
        const RunResult result = runWith(pipeline, seed);
        require(result.workflows.front().calls <= 4,
                "a retry block may not run its body more often than its declared bound");
        require(result.workflows.front().calls >= 1, "a retry block runs its body at least once");
    }
}

void testRunTakesExactlyOneBranchArm() {
    Pipeline pipeline = compileSource(R"(workflow B budget 100000 {
  input d: text max_tokens 10;
  model m = mock("m") max_tokens 100;
  prompt p(a: text) -> text = "{a}";
  let head: text = call p(d) using m;
  if tokens(head) <= 50 {
    let x: text = call p(d) using m;
  } else {
    let y: text = call p(d) using m;
  }
  output head;
})");
    requireSemanticallyValid(pipeline);
    for (std::uint64_t seed = 1; seed <= 50; ++seed) {
        const RunResult result = runWith(pipeline, seed);
        require(result.workflows.front().calls == 2,
                "exactly one arm of a branch should run, so the head call plus one arm");
    }
}

void testRunRefusesIllTypedProgram() {
    Pipeline pipeline = compileSource("workflow B budget 10 { secret k; output k; }");
    require(pipeline.semantic.has_value(), "semantic analysis should run");
    RunOptions options;
    Interpreter interpreter(options);
    const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
    require(!result.success(), "an ill-typed workflow must not be executed");
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
    const WorkflowCost& cost = onlyCost(pipeline);
    require(cost.bound.guaranteed == 100, "guaranteed component should be the model output cap");
    require(cost.bound.estimated == 45, "estimated component should be template plus argument bound");
    require(cost.withinBudget(), "the derived bound should fit the declared budget");
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
    require(hasCode(pipeline, "E231"), "secret output should report E231");
}

void testSemanticBudgetExceeded() {
    Pipeline pipeline = compileSource(
        "workflow B budget 5 { input x: text max_tokens 1; model m = mock(\"x\") max_tokens 6; prompt p(a: text) -> text = \"{a}\"; let r: text = call p(x) using m; output r; }");
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
    require(onlyCost(pipeline).bound.total() == 0, "zero-call workflow should have zero token bound");
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
        {"run is deterministic for a seed", testRunIsDeterministicForASeed},
        {"run stays within certified bound", testRunStaysWithinCertifiedBound},
        {"run respects declared retry bound", testRunNeverExceedsDeclaredRetryBound},
        {"run takes exactly one branch arm", testRunTakesExactlyOneBranchArm},
        {"run refuses ill-typed program", testRunRefusesIllTypedProgram},
        {"parser parses branch", testParserParsesBranch},
        {"cost branch takes maximum", testCostBranchTakesMaximum},
        {"cost retry multiplies", testCostRetryMultiplies},
        {"cost retry overrun caught", testCostRetryOverrunIsCaught},
        {"cost separates guaranteed from estimated", testCostSeparatesGuaranteedFromEstimated},
        {"cost assumption moves only estimated half", testCostAssumptionChangesOnlyEstimatedHalf},
        {"empty branch arm costs nothing", testEmptyBranchArmCostsNothing},
        {"require violation reported", testRequireViolationIsReported},
        {"require satisfied by bound", testRequireSatisfiedByBound},
        {"require on unbounded subject", testRequireOnUnboundedSubject},
        {"require lower bound undecidable", testRequireLowerBoundIsUndecidable},
        {"unbounded input reaching prompt rejected", testUnboundedInputReachingPromptIsRejected},
        {"label lattice join and order", testLabelLatticeJoinAndOrder},
        {"untrusted input taints model output", testUntrustedInputTaintsModelOutput},
        {"untrusted value cannot reach sink", testUntrustedValueCannotReachSink},
        {"secret cannot reach sink", testSecretCannotReachSink},
        {"secret guarded effect is implicit flow", testSecretGuardedEffectIsImplicitFlow},
        {"untrusted guarded effect rejected", testUntrustedGuardedEffectIsRejected},
        {"declassification clears confidentiality", testDeclassificationClearsConfidentiality},
        {"reclassification recorded with justification", testReclassificationIsRecordedWithJustification},
        {"empty justification rejected", testEmptyJustificationIsRejected},
        {"pc label survives declassification", testPcLabelSurvivesDeclassificationInsideSecretBranch},
        {"unknown tool reported", testUnknownToolIsReported},
        {"tool arity and types checked", testToolArityAndTypesAreChecked},
        {"clean sink accepted", testCleanSinkIsAccepted},
        {"branch binding does not escape", testBranchBindingDoesNotEscape},
        {"certificate records bound and labels", testCertificateRecordsBoundAndLabels},
        {"IR carries regions and repeat factors", testIrCarriesRegionsAndRepeatFactors},
        {"saturating arithmetic never wraps", testSaturatingArithmeticNeverWraps},
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
