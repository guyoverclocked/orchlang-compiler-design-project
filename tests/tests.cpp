#include "ast.hpp"
#include "certificate.hpp"
#include "cost_analyzer.hpp"
#include "interpreter.hpp"
#include "relational.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"
#include "sha256.hpp"
#include "tokenizer_contracts.hpp"

#include <algorithm>
#include <exception>
#include <functional>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
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
    std::string source;
    LexResult lexed;
    ParseResult parsed;
    std::optional<SemanticResult> semantic;
    std::optional<CostResult> cost;
    std::optional<RelationalResult> relational;
};

Pipeline compileSource(const std::string& source) {
    Lexer lexer(source, "test.orch");
    LexResult lexed = lexer.scan();
    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();
    Pipeline result{source, std::move(lexed), std::move(parsed), std::nullopt, std::nullopt, std::nullopt};
    if (!result.lexed.diagnostics.hasErrors() && !result.parsed.diagnostics.hasErrors()) {
        SemanticAnalyzer analyzer;
        result.semantic = analyzer.analyze(result.parsed.program);
        if (result.semantic->success()) {
            CostAnalyzer costAnalyzer;
            result.cost = costAnalyzer.analyze(result.parsed.program, *result.semantic);
            RelationalAnalyzer relationalAnalyzer;
            result.relational = relationalAnalyzer.analyze(result.parsed.program, *result.semantic);
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
           (pipeline.cost && hasCode(pipeline.cost->diagnostics, code)) ||
           (pipeline.relational && hasCode(pipeline.relational->diagnostics, code));
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
        printCertificate(pipeline.parsed.program, pipeline.source, *pipeline.semantic, *pipeline.cost,
                         lowered.program, *pipeline.relational, "content");
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


// Relational resource analysis: does a secret change the bill?

void testSecretDependentCostIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input src: text max_tokens 10;
  secret alert: boolean max_tokens 1;
  model small = mock("s") max_tokens 100;
  model large = mock("l") max_tokens 5000;
  prompt p(a: text) -> text = "{a}";
  if alert {
    let a: text = call p(src) using large;
  } else {
    let b: text = call p(src) using small;
  }
  output src;
})");
    require(hasCode(pipeline, "E236"),
            "arms that call different models bill differently under a secret guard");
}

// The counterexample that falsified the previous rule.  Both arms bound at the
// same number, so comparing upper bounds accepted it; the arms read different
// variables, so the bill really does move with the secret.
void testEqualBoundsWithDifferentArgumentsIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  input y: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(y) using m;
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"),
            "equal upper bounds must not be mistaken for equal cost");
}

void testBalancedArmsUnderSecretAreAccepted() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational.has_value() && pipeline.relational->success(),
            "arms that bill identically are accepted");
    require(pipeline.relational->obligations.size() == 1, "the obligation should be recorded");
    require(pipeline.relational->obligations.front().discharged, "and discharged");
}

void testExtraCallInOneArmIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    let a: text = call p(x) using m;
    let b: text = call p(x) using m;
  } else {
    let c: text = call p(x) using m;
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "a differing number of calls is observable");
}

void testDifferingRetryBoundsAreRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    retry 2 { let a: text = call p(x) using m; }
  } else {
    retry 3 { let b: text = call p(x) using m; }
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "a differing retry bound is observable");
}

void testMatchingRetryBoundsAreAccepted() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    retry 2 { let a: text = call p(x) using m; }
  } else {
    retry 2 { let b: text = call p(x) using m; }
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "matching retry structure bills identically");
}

// ---------------------------------------------------------------------------
// Empirical checking of relational verdicts
// ---------------------------------------------------------------------------

// Everything one observer can see of one execution.
std::string observationKey(const WorkflowRun& run, Observer observer) {
    std::ostringstream out;
    if (observer == Observer::Bill) {
        for (const auto& entry : run.billing) {
            out << entry.first << ':' << entry.second.calls << '/' << entry.second.inputTokens << '/'
                << entry.second.outputTokens << ';';
        }
        return out.str();
    }
    std::map<std::string, std::string> perProvider;
    for (const CallTrace& call : run.trace) {
        const std::string provider =
            observer == Observer::Provider ? call.modelString.substr(0, call.modelString.find('/'))
                                           : std::string("*");
        perProvider[provider] += call.identity + "|" + call.request + "|" + call.response + "|" +
                                 std::to_string(call.inputTokens) + "|" +
                                 std::to_string(call.outputTokens) + "\n";
    }
    for (const auto& entry : perProvider) {
        out << entry.first << '{' << entry.second << '}';
    }
    for (const std::size_t attempts : run.retryAttempts) {
        out << 'r' << attempts;
    }
    return out.str();
}

// One way of choosing the secrets: lengths and flags to pin.
struct Assignment {
    std::map<std::string, std::size_t> lengths;
    std::map<std::string, bool> flags;
};

std::vector<Assignment> everySecret(const std::vector<std::string>& flags,
                                    const std::vector<std::pair<std::string, std::size_t>>& lengths) {
    std::vector<Assignment> all{Assignment{}};
    for (const std::string& flag : flags) {
        std::vector<Assignment> next;
        for (const Assignment& partial : all) {
            for (const bool value : {false, true}) {
                Assignment extended = partial;
                extended.flags[flag] = value;
                next.push_back(extended);
            }
        }
        all = next;
    }
    for (const auto& length : lengths) {
        std::vector<Assignment> next;
        for (const Assignment& partial : all) {
            for (std::size_t value = 0; value <= length.second; ++value) {
                Assignment extended = partial;
                extended.lengths[length.first] = value;
                next.push_back(extended);
            }
        }
        all = next;
    }
    return all;
}

// The most distinct observations any single seed yields as the secrets vary,
// across both providers, both accountings, and every coupling the observer's
// guarantee is stated under.  A verdict of "leaks nothing" predicts 1; a
// leakage bound of k classes predicts at most k.
std::size_t distinctObservations(const Pipeline& pipeline, const std::vector<Assignment>& secrets,
                                 const std::map<std::string, std::size_t>& publicPins,
                                 Observer observer = Observer::Trace, std::uint64_t seeds = 12) {
    std::vector<Coupling> couplings{Coupling::Request};
    if (observer == Observer::Trace) {
        couplings = {Coupling::Global, Coupling::Model, Coupling::Request};
    }
    std::size_t worst = 0;
    for (const ProviderMode provider : {ProviderMode::Uniform, ProviderMode::Content}) {
        for (const Coupling coupling : couplings) {
            for (const Accounting accounting : {Accounting::Estimate, Accounting::Tokenizer}) {
                for (std::uint64_t seed = 1; seed <= seeds; ++seed) {
                    std::set<std::string> seen;
                    for (const Assignment& secret : secrets) {
                        RunOptions options;
                        options.seed = seed;
                        options.provider = provider;
                        options.coupling = coupling;
                        options.accounting = accounting;
                        options.pinnedLengths = publicPins;
                        for (const auto& entry : secret.lengths) {
                            options.pinnedLengths[entry.first] = entry.second;
                        }
                        options.pinnedFlags = secret.flags;
                        Interpreter interpreter(options);
                        const RunResult result =
                            interpreter.run(pipeline.parsed.program, *pipeline.semantic);
                        require(result.success(), "the run should succeed");
                        seen.insert(observationKey(result.workflows.front(), observer));
                    }
                    worst = std::max(worst, seen.size());
                }
            }
        }
    }
    return worst;
}

const LeakageReport& onlyLeakage(const Pipeline& pipeline) {
    require(pipeline.relational.has_value(), "relational analysis should run");
    require(pipeline.relational->leakage.size() == 1, "one leakage report expected");
    return pipeline.relational->leakage.front();
}

// ---------------------------------------------------------------------------
// OP-1: a discharged relational obligation relaxes the program-counter rule
//
// A value computed inside a secret-guarded arm from public arguments has public
// *content*; only its *existence* depends on the secret, and existence is what
// the relational obligation on the enclosing branch accounts for.  So such a
// value may reach a prompt.  These tests try to break that, and each attempt
// must be caught: by the relational check, by the pc rule on effects and
// outputs, by scoping, or by the data rule on genuinely secret content.
// ---------------------------------------------------------------------------

std::string secretArm(const std::string& thenArm, const std::string& elseArm,
                      const std::string& extra = "") {
    return R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  secret t: text max_tokens 3;
  input x: text max_tokens 30;
  input y: text max_tokens 30;
  model m = mock("m") max_tokens 10;
  model n = mock("n") max_tokens 10;
  tool publish(body: text);
  prompt p(u: text) -> text = "Answer: {u}";
  prompt q(u: text) -> text = "Check: {u}";
)" + extra + R"(  if tokens(s) == 0 {
)" + thenArm + R"(  } else {
)" + elseArm + R"(  }
  output "done";
})";
}

const std::vector<Assignment>& sSecrets() {
    static const std::vector<Assignment> all = everySecret({}, {{"s", 1}, {"t", 3}});
    return all;
}

const std::map<std::string, std::size_t>& xyPins() {
    static const std::map<std::string, std::size_t> pins{{"x", 7}, {"y", 7}};
    return pins;
}

void testChainingInsideSecretArmIsAccepted() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    let a2: text = call p(a1) using m;\n",
        "    let b1: text = call p(x) using m;\n    let b2: text = call p(b1) using m;\n"));
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "chained calls with equal request structure are accepted");
    require(onlyLeakage(pipeline).classes == 1, "and leak nothing");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) == 1,
            "no seed, provider, coupling or accounting may tell the secrets apart");
}

void testChainLengthDependingOnSecretIsRejected() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    let a2: text = call p(a1) using m;\n",
        "    let b1: text = call p(x) using m;\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "a chain whose length depends on the secret leaks it");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) > 1, "and it really does leak");
}

void testChainFedDifferentPriorResultIsRejected() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    let a2: text = call p(y) using m;\n"
        "    let a3: text = call q(a1) using m;\n",
        "    let b1: text = call p(x) using m;\n    let b2: text = call p(y) using m;\n"
        "    let b3: text = call q(b2) using m;\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "feeding a different earlier response is a different request");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) > 1, "and it really does leak");
}

void testChainFedOuterVariableInsteadOfResultIsRejected() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    let a2: text = call p(a1) using m;\n",
        "    let b1: text = call p(x) using m;\n    let b2: text = call p(x) using m;\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "a response and an input are different request text");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) > 1, "and it really does leak");
}

void testChainThroughDifferentModelIsRejected() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    let a2: text = call q(a1) using m;\n",
        "    let b1: text = call p(x) using m;\n    let b2: text = call q(b1) using n;\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "a different endpoint is a different request");
}

void testPcSecretValueStillCannotBeEmitted() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n    emit publish(a1);\n",
        "    let b1: text = call p(x) using m;\n    emit publish(b1);\n"));
    require(hasCode(pipeline, "E234"),
            "whether an effect happens under a secret guard still leaks, whatever it carries");
}

void testPcSecretValueStillCannotBeOutput() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 30;
  model m = mock("m") max_tokens 10;
  prompt p(u: text) -> text = "{u}";
  if tokens(s) == 0 {
    let a1: text = call p(x) using m;
    output a1;
  }
})");
    require(hasCode(pipeline, "E231"), "an output under a secret guard is still an implicit flow");
}

void testPcSecretValueCannotEscapeItsArm() {
    Pipeline pipeline = compileSource(secretArm("    let a1: text = call p(x) using m;\n",
                                                "    let a1: text = call p(x) using m;\n") +
                                      "");
    requireSemanticallyValid(pipeline);
    Pipeline escaping = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 30;
  model m = mock("m") max_tokens 10;
  prompt p(u: text) -> text = "{u}";
  if tokens(s) == 0 {
    let a1: text = call p(x) using m;
  } else {
    let a1: text = call p(x) using m;
  }
  let after: text = call p(a1) using m;
  output "done";
})");
    require(hasCode(escaping, "E202"), "a binding made in an arm does not exist after it");
}

void testDeclassifyingPcSecretValueDoesNotLaunderEffects() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n"
        "    declassify(a1) as d: text because \"try to launder\";\n    emit publish(d);\n",
        "    let b1: text = call p(x) using m;\n"));
    require(hasCode(pipeline, "E234"), "relabelling does not escape the program counter");
}

void testSecretContentStillCannotReachPromptInsideArm() {
    Pipeline pipeline = compileSource(secretArm("    let a1: text = call p(t) using m;\n",
                                                "    let b1: text = call p(t) using m;\n"));
    require(hasCode(pipeline, "E230"),
            "secret *content* is still barred from prompts, identical arms or not");
}

void testEndorsedSecretIsStillSecretContent() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n",
        "    let b1: text = call p(x) using m;\n",
        "  endorse(t) as vetted: text because \"integrity only\";\n"
        "  let leak: text = call p(vetted) using m;\n"));
    require(hasCode(pipeline, "E230"), "endorsement raises integrity, it does not declassify");
}

void testGuardOnPcSecretResultIsPublicWhenArmsMatch() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n"
        "    if tokens(a1) <= 5 { let a2: text = call q(a1) using m; }\n",
        "    let b1: text = call p(x) using m;\n"
        "    if tokens(b1) <= 5 { let b2: text = call q(b1) using m; }\n"));
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "both executions evaluate the inner guard on the same response");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) == 1, "and bill identically");
}

void testGuardOnPcSecretResultWithDifferentThresholdIsRejected() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n"
        "    if tokens(a1) <= 3 { let a2: text = call q(a1) using m; }\n",
        "    let b1: text = call p(x) using m;\n"
        "    if tokens(b1) <= 7 { let b2: text = call q(b1) using m; }\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "a different inner threshold changes when the call happens");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) > 1, "and it really does leak");
}

void testChainInsideRetryInsideSecretArm() {
    Pipeline same = compileSource(secretArm(
        "    retry 3 {\n      let a1: text = call p(x) using m;\n      let a2: text = call q(a1) using m;\n    }\n",
        "    retry 3 {\n      let b1: text = call p(x) using m;\n      let b2: text = call q(b1) using m;\n    }\n"));
    requireSemanticallyValid(same);
    require(same.relational->success(), "identical retried chains are accepted");
    require(distinctObservations(same, sSecrets(), xyPins()) == 1, "and bill identically");

    Pipeline different = compileSource(secretArm(
        "    retry 2 {\n      let a1: text = call p(x) using m;\n      let a2: text = call q(a1) using m;\n    }\n",
        "    retry 3 {\n      let b1: text = call p(x) using m;\n      let b2: text = call q(b1) using m;\n    }\n"));
    require(hasCode(different, "E236"), "a different retry bound is observable");
}

void testNestedSecretBranchUsingPcSecretValue() {
    Pipeline pipeline = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n"
        "    if tokens(t) <= 1 { let a2: text = call q(a1) using m; } else { let a3: text = call q(a1) using m; }\n",
        "    let b1: text = call p(x) using m;\n"
        "    if tokens(t) <= 1 { let b2: text = call q(b1) using m; } else { let b3: text = call q(b1) using m; }\n"));
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "a nested secret branch with agreeing arms contributes one signature");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) == 1, "and leaks nothing");

    Pipeline leaking = compileSource(secretArm(
        "    let a1: text = call p(x) using m;\n"
        "    if tokens(t) <= 1 { let a2: text = call q(a1) using m; }\n",
        "    let b1: text = call p(x) using m;\n"
        "    if tokens(t) <= 1 { let b2: text = call q(b1) using m; }\n"));
    require(hasCode(leaking, "E236"), "a nested secret guard that decides a call leaks its secret");
    require(distinctObservations(leaking, sSecrets(), xyPins()) > 1, "and it really does leak");
}

// ---------------------------------------------------------------------------
// Content, not size: the self-audit of 2026-09-25
// ---------------------------------------------------------------------------

// Literals of the same estimated size, different text.  The withdrawn size
// rule accepted this; a content-dependent provider, or a real tokenizer
// ("aaaa" is 1 token and "bbbb" 2 under r50k_base), bills it differently.
void testEqualSizeLiteralsAreDifferentRequests() {
    Pipeline pipeline = compileSource(secretArm("    let a: text = call p(\"aaaa\") using m;\n",
                                                "    let b: text = call p(\"bbbb\") using m;\n"));
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "equal-size literals are different request text");
    require(distinctObservations(pipeline, sSecrets(), xyPins()) > 1, "and they really do leak");
}

// Templates of equal size, different instructions: the paper's motivating case
// after a developer has padded one prompt to the other's length.
void testEqualSizeTemplatesAreDifferentRequests() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret enterprise: boolean max_tokens 1;
  input ticket: text max_tokens 30;
  model m = mock("m") max_tokens 50;
  prompt ack(t: text) -> text = "Acknowledge briefly: {t}";
  prompt esc(t: text) -> text = "Escalate in detail!: {t}";
  if enterprise { let a: text = call esc(ticket) using m; }
  else { let b: text = call ack(ticket) using m; }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "same size, different instruction, different bill");
    require(distinctObservations(pipeline, everySecret({"enterprise"}, {}), {{"ticket", 9}}) > 1,
            "and it really does leak under a content-dependent provider");
}

void testSameTextThroughDifferentPromptNamesIsTheSameRequest() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret enterprise: boolean max_tokens 1;
  input ticket: text max_tokens 30;
  model m = mock("m") max_tokens 50;
  prompt first(t: text) -> text = "Summarise: {t}";
  prompt second(u: text) -> text = "Summarise: {u}";
  if enterprise { let a: text = call first(ticket) using m; }
  else { let b: text = call second(ticket) using m; }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "requests are compared by text, not by prompt name");
    require(distinctObservations(pipeline, everySecret({"enterprise"}, {}), {{"ticket", 9}}) == 1,
            "and identical text bills identically");
}

// Audit finding F3: the size rule compared models, prompts and variables by
// local name, so a redeclaration inside one arm went unnoticed.
void testShadowedModelInArmIsADifferentEndpoint() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 30;
  model m = mock("small") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if flag {
    model m = mock("large") max_tokens 1000;
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "the same local name may denote a different endpoint");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 5}}, Observer::Bill) > 1,
            "and the invoice shows it");
}

void testShadowedPromptInArmIsADifferentRequest() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 30;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "Reply briefly: {t}";
  if flag {
    prompt p(t: text) -> text = "Reply at length {t}";
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "the same prompt name may denote different text");
}

void testInputDeclaredInsideArmIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 30;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if flag {
    input x: text max_tokens 30;
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    require(hasCode(pipeline, "E203"),
            "an input arrives before the workflow runs, so it is declared at the top level only");
}

// The runtime's invoice is keyed by the provider's model name, as a real one is.
void testBillingIsKeyedByProviderModelName() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input x: text max_tokens 3;
  model first = mock("shared") max_tokens 5;
  model second = mock("shared") max_tokens 5;
  prompt p(t: text) -> text = "{t}";
  let a: text = call p(x) using first;
  let b: text = call p(x) using second;
  output "done";
})");
    requireSemanticallyValid(pipeline);
    const RunResult result = runWith(pipeline, 3);
    require(result.workflows.front().billing.size() == 1 &&
                result.workflows.front().billing.begin()->first == "shared" &&
                result.workflows.front().billing.begin()->second.calls == 2,
            "two local names for one endpoint are one line on the invoice");
}

// ---------------------------------------------------------------------------
// OP-4: how much, not just whether
// ---------------------------------------------------------------------------

void testOneBitBranchNeedsABudget() {
    const std::string body = R"( {
  secret enterprise: boolean max_tokens 1;
  input ticket: text max_tokens 20;
  model small = mock("small") max_tokens 20;
  model large = mock("large") max_tokens 60;
  prompt p(t: text) -> text = "Reply: {t}";
  if enterprise { let a: text = call p(ticket) using large; }
  else { let b: text = call p(ticket) using small; }
  output "done";
})";
    Pipeline strict = compileSource("workflow C budget 100000" + body);
    require(hasCode(strict, "E236"), "without a budget, one bit is too many");
    Pipeline allowed = compileSource("workflow C budget 100000 leaks 1" + body);
    requireSemanticallyValid(allowed);
    require(allowed.relational->success(), "with a one-bit budget the branch is accepted");
    require(hasCode(allowed, "W238"), "and the leak is still reported");
    require(onlyLeakage(allowed).classes == 2, "two classes");
    require(distinctObservations(allowed, everySecret({"enterprise"}, {}), {{"ticket", 9}}) <= 2,
            "no seed may reveal more than the two classes");
}

// Three thresholds on one secret split it into four intervals, not eight
// combinations: the count is exact because infeasible outcome vectors are
// never enumerated.
void testThresholdsOnOneSecretCountIntervals() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 leaks 2 {
  secret tier: text max_tokens 9;
  input x: text max_tokens 10;
  model m = mock("m") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  prompt q(t: text) -> text = "more: {t}";
  if tokens(tier) <= 2 { let a: text = call p(x) using m; }
  if tokens(tier) <= 5 { let b: text = call q(x) using m; }
  if tokens(tier) <= 7 { let c: text = call p(x) using m; }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(onlyLeakage(pipeline).outcomeVectors == 4, "three thresholds give four feasible vectors");
    require(onlyLeakage(pipeline).classes == 4, "and four distinguishable behaviours");
    require(pipeline.relational->success(), "two bits is within a two-bit budget");
    require(distinctObservations(pipeline, everySecret({}, {{"tier", 9}}), {{"x", 4}}) <= 4,
            "no seed may reveal more than four classes");
}

void testIndependentSecretsMultiplyClasses() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 leaks 1.6 {
  secret a: boolean max_tokens 1;
  secret b: boolean max_tokens 1;
  input x: text max_tokens 10;
  model m = mock("m") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  if a { let r1: text = call p(x) using m; }
  if b { let r2: text = call p(x) using m; }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    // a,b in {00, 01, 10, 11} give 0, 1, 1, 2 calls: three classes, not four.
    require(onlyLeakage(pipeline).outcomeVectors == 4, "two independent flags give four vectors");
    require(onlyLeakage(pipeline).classes == 3, "but 01 and 10 send the same requests");
    require(pipeline.relational->success(), "log2 3 = 1.58 bits, within 1.6");
    require(distinctObservations(pipeline, everySecret({"a", "b"}, {}), {{"x", 4}}) <= 3,
            "no seed may reveal more than three classes");
}

// Two branches on the same secret whose differences cancel: each is
// undischarged on its own, but every secret value sends the same requests.
void testCancellingBranchesAreAcceptedGlobally() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 10;
  model m = mock("m") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  if flag { let a: text = call p(x) using m; }
  if flag { } else { let b: text = call p(x) using m; }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "the resolved programs are identical");
    require(onlyLeakage(pipeline).classes == 1, "one class");
    require(pipeline.relational->obligations.size() == 2 &&
                !pipeline.relational->obligations[0].discharged,
            "even though neither branch is balanced on its own");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 4}}) == 1,
            "and the executions are indistinguishable");
}

// ---------------------------------------------------------------------------
// OP-7: a lattice of observers
// ---------------------------------------------------------------------------

std::string reorderedCalls(const std::string& observer, const std::string& firstModel,
                           const std::string& secondModel) {
    return "workflow C budget 100000" + observer + R"( {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 10;
  model m1 = mock(")" + firstModel + R"(") max_tokens 20;
  model m2 = mock(")" + secondModel + R"(") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  if flag {
    let a1: text = call p(x) using m1;
    let a2: text = call p(x) using m2;
  } else {
    let b2: text = call p(x) using m2;
    let b1: text = call p(x) using m1;
  }
  output "done";
})";
}

void testReorderingIsVisibleToTheTraceObserver() {
    Pipeline pipeline = compileSource(reorderedCalls("", "alpha/one", "beta/two"));
    require(hasCode(pipeline, "E236"), "a log of requests in order shows the reordering");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 4}}, Observer::Trace) > 1,
            "and the transcripts do differ");
}

void testReorderingAcrossProvidersIsInvisibleToEachProvider() {
    Pipeline pipeline = compileSource(reorderedCalls(" observer provider", "alpha/one", "beta/two"));
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "each provider sees only its own, unchanged, request");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 4}}, Observer::Provider) == 1,
            "under the request coupling no provider's log differs");
}

void testReorderingWithinOneProviderIsVisibleToIt() {
    Pipeline pipeline = compileSource(reorderedCalls(" observer provider", "alpha/one", "alpha/two"));
    require(hasCode(pipeline, "E236"), "one provider hosting both models sees their order");
}

void testReorderingIsInvisibleOnTheInvoice() {
    Pipeline pipeline = compileSource(reorderedCalls(" observer bill", "alpha/one", "alpha/two"));
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "an invoice shows sums, not order");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 4}}, Observer::Bill) == 1,
            "and the invoices are identical");
}

// Found while writing the soundness argument for the observer lattice: an
// earlier version reordered calls inside retry bodies too.  A retry attempt's
// success is decided on its transcript, whose order a validator may depend on,
// so reordering there changes the number of attempts and the invoice.  The
// runtime showed it: 1 attempt against 3 under the same seed.
void testCallsInsideRetryAreNeverReordered() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 observer bill {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 10;
  model m1 = mock("alpha/one") max_tokens 20;
  model m2 = mock("alpha/two") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  if flag {
    retry 4 {
      let a1: text = call p(x) using m1;
      let a2: text = call p(x) using m2;
    }
  } else {
    retry 4 {
      let b2: text = call p(x) using m2;
      let b1: text = call p(x) using m1;
    }
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "reordering inside a retry body can change the attempts");
    require(distinctObservations(pipeline, everySecret({"flag"}, {}), {{"x", 4}}, Observer::Bill) > 1,
            "and the invoice does change");
}

void testDependentCallsAreNotReorderedForTheBill() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 observer bill {
  secret flag: boolean max_tokens 1;
  input x: text max_tokens 10;
  model m = mock("m") max_tokens 20;
  prompt p(t: text) -> text = "{t}";
  prompt q(t: text) -> text = "again {t}";
  if flag {
    let a1: text = call p(x) using m;
    let a2: text = call q(a1) using m;
  } else {
    let b1: text = call q(x) using m;
    let b2: text = call p(b1) using m;
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "a data dependence fixes the order, and the requests differ");
}

// ---------------------------------------------------------------------------
// OP-3: tokenizer contracts and the guaranteed input bound
// ---------------------------------------------------------------------------

void testGuaranteedInputIsBuiltFromBytes() {
    Pipeline pipeline = compileSource(R"(workflow G budget 100000 {
  input doc: text max_bytes 400;
  model m = mock("m") max_tokens 50 tokenizer llama2 overhead 7;
  prompt p(t: text) -> text = "Summarise: {t}";
  let s: text = call p(doc) using m;
  output s;
})");
    requireSemanticallyValid(pipeline);
    const CostBound& bound = onlyCost(pipeline).bound;
    require(bound.inputGuaranteedDefined, "a verified tokenizer and byte bounds give a guarantee");
    // kappa=1: 11 template bytes + 400 argument bytes, plus sigma for llama2, plus 7.
    const TokenizerContract* contract = findTokenizerContract("llama2");
    require(contract != nullptr, "llama2 is a known tokenizer");
    require(bound.inputGuaranteed == 11 + 400 + contract->sigma + 7,
            "the guarantee is template bytes plus argument bytes plus sigma plus overhead");
    require(onlyCost(pipeline).budgetGuaranteed(), "and the budget is checked against it");
}

void testUnverifiedTokenizerGivesNoGuarantee() {
    Pipeline pipeline = compileSource(R"(workflow G budget 100000 {
  input doc: text max_bytes 400;
  model m = mock("m") max_tokens 50 tokenizer t5;
  prompt p(t: text) -> text = "{t}";
  let s: text = call p(doc) using m;
  output s;
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "W267"), "an NFKC tokenizer has no verified byte contract");
    require(!onlyCost(pipeline).bound.inputGuaranteedDefined,
            "so the compiler refuses to certify a guaranteed input bound through it");
}

void testUnknownTokenizerIsAnError() {
    Pipeline pipeline = compileSource(R"(workflow G budget 100000 {
  model m = mock("m") max_tokens 50 tokenizer cl99k;
  output "x";
})");
    require(hasCode(pipeline, "E267"), "a tokenizer the compiler has no contract for is rejected");
}

void testEstimateUnitInputHasNoByteBound() {
    Pipeline pipeline = compileSource(R"(workflow G budget 100000 {
  input doc: text max_tokens 100;
  model m = mock("m") max_tokens 50 tokenizer cl100k_base;
  prompt p(t: text) -> text = "{t}";
  let s: text = call p(doc) using m;
  output s;
})");
    requireSemanticallyValid(pipeline);
    require(!onlyCost(pipeline).bound.inputGuaranteedDefined,
            "a token count in the estimate unit says nothing any real tokenizer must respect");
}

void testTokenBoundUnderNamedTokenizerGivesBytes() {
    Pipeline pipeline = compileSource(R"(workflow G budget 1000000 {
  input doc: text max_tokens 100 tokenizer cl100k_base;
  model m = mock("m") max_tokens 50 tokenizer cl100k_base;
  prompt p(t: text) -> text = "{t}";
  let s: text = call p(doc) using m;
  output s;
})");
    requireSemanticallyValid(pipeline);
    const CostBound& bound = onlyCost(pipeline).bound;
    const TokenizerContract* contract = findTokenizerContract("cl100k_base");
    require(bound.inputGuaranteedDefined && bound.inputGuaranteed == 100 * contract->lambda,
            "100 tokens of a lossless tokenizer are at most 100 * lambda bytes");
}

// A response's byte length is what a later prompt is billed on.  A token cap
// bounds it only through lambda; a client byte cap bounds it directly.
void testChainedCallUsesResponseByteBound() {
    const std::string body = R"(
  input doc: text max_bytes 100;
  prompt p(t: text) -> text = "{t}";
  let first: text = call p(doc) using m;
  let second: text = call p(first) using m;
  output second;
})";
    Pipeline loose = compileSource(
        "workflow G budget 100000000 {\n  model m = mock(\"m\") max_tokens 50 tokenizer cl100k_base;" + body);
    Pipeline capped = compileSource(
        "workflow G budget 100000000 {\n  model m = mock(\"m\") max_tokens 50 tokenizer cl100k_base max_bytes 300;" + body);
    requireSemanticallyValid(loose);
    requireSemanticallyValid(capped);
    const TokenizerContract* contract = findTokenizerContract("cl100k_base");
    require(onlyCost(loose).bound.inputGuaranteed == 100 + 50 * contract->lambda,
            "without a cap the second request is bounded through lambda");
    require(onlyCost(capped).bound.inputGuaranteed == 100 + 300,
            "with a cap it is bounded by the cap");
}

// Under the runtime's content-sensitive tokenizer the guaranteed bound must
// hold on every execution; the estimate is allowed to fail, and does.
void testGuaranteedBoundHoldsUnderRealTokenization() {
    Pipeline pipeline = compileSource(R"(workflow G budget 100000000 {
  input doc: text max_bytes 300;
  model m = mock("m") max_tokens 40 tokenizer mockbpe overhead 3 max_bytes 200;
  prompt p(t: text) -> text = "Process this payload: {t}";
  retry 3 {
    let first: text = call p(doc) using m;
    let second: text = call p(first) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    const CostBound& bound = onlyCost(pipeline).bound;
    require(bound.inputGuaranteedDefined, "the runtime tokenizer has a verified contract");
    for (std::uint64_t seed = 1; seed <= 200; ++seed) {
        RunOptions options;
        options.seed = seed;
        options.accounting = Accounting::Tokenizer;
        options.provider = ProviderMode::Content;
        Interpreter interpreter(options);
        const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
        require(result.workflows.front().inputTokens <= bound.inputGuaranteed,
                "no execution may exceed the guaranteed input bound");
        require(result.workflows.front().outputTokens <= bound.guaranteed,
                "nor the output bound");
    }
}

void testMockTokenizerIsNotSubadditive() {
    // Greedy longest match takes "er" across the join and strands "est".
    require(mockTokenCount("e") == 1 && mockTokenCount("rest") == 1 && mockTokenCount("erest") == 4,
            "the mock tokenizer, like a real one, can bill a join more than its parts");
    require(mockTokenCount("aaaa") != mockTokenCount("bbbb"),
            "equal-length strings need not have equal token counts");
    for (const std::string text : {"", "x", "Process this payload: café", "日本語"}) {
        require(mockTokenCount(text) <= text.size(), "but it never exceeds one token per byte");
    }
}

// ---------------------------------------------------------------------------
// The certificate names its source; the withdrawn rules are reproducible
// ---------------------------------------------------------------------------

void testSha256MatchesStandardVectors() {
    require(sha256Hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "SHA-256 of the empty string");
    require(sha256Hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "SHA-256 of 'abc'");
    require(sha256Hex("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq") ==
                "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
            "SHA-256 of the two-block vector");
}

void testWithdrawnRulesAreReproducedAsBaselines() {
    const std::string equalSize = secretArm("    let a: text = call p(\"aaaa\") using m;\n",
                                            "    let b: text = call p(\"bbbb\") using m;\n");
    Pipeline pipeline = compileSource(equalSize);
    requireSemanticallyValid(pipeline);
    const RelationalResult sizes = analyzeWithSizeRule(pipeline.parsed.program, *pipeline.semantic);
    const RelationalResult bounds = analyzeWithBoundsRule(pipeline.parsed.program, *pipeline.semantic);
    require(sizes.success(), "the withdrawn size rule accepts equal-size literals");
    require(bounds.success(), "so does the withdrawn bounds rule");
    require(!pipeline.relational->success(), "the content rule does not");
}

// A public guard inside a secret-guarded arm is fine: both executions see the
// same public data and take the same inner arm.
void testPublicGuardInsideSecretArmIsAllowed() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  let head: text = call p(x) using m;
  if tokens(s) == 0 {
    if tokens(head) <= 5 { let a: text = call p(x) using m; }
  } else {
    if tokens(head) <= 5 { let b: text = call p(x) using m; }
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "matching public sub-branches bill identically");
}

void testDifferingPublicSubBranchIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  let head: text = call p(x) using m;
  if tokens(s) == 0 {
    if tokens(head) <= 5 { let a: text = call p(x) using m; }
  } else {
    if tokens(head) <= 7 { let b: text = call p(x) using m; }
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "a differing inner guard changes when billing happens");
}

void testPublicGuardWithUnequalArmsIsFine() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input src: text max_tokens 10;
  model small = mock("s") max_tokens 100;
  model large = mock("l") max_tokens 5000;
  prompt p(a: text) -> text = "{a}";
  let head: text = call p(src) using small;
  if tokens(head) <= 100 {
    let a: text = call p(src) using large;
  } else {
    let b: text = call p(src) using small;
  }
  output head;
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "a public guard may steer cost freely");
}

void testUntrustedGuardOnUnequalArmsWarns() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input flag: boolean untrusted max_tokens 1;
  input src: text max_tokens 10;
  model small = mock("s") max_tokens 100;
  model large = mock("l") max_tokens 5000;
  prompt p(a: text) -> text = "{a}";
  if flag {
    let a: text = call p(src) using large;
  } else {
    let b: text = call p(src) using small;
  }
  output src;
})");
    require(hasCode(pipeline, "W237"),
            "untrusted data steering spend should at least be surfaced");
    require(pipeline.cost.has_value() && pipeline.cost->success(),
            "the warning should not reject the workflow");
}

// The componentwise bound must hold for each component on its own, which is
// what audit finding 2 showed the old rule did not do.
void testBranchBoundsEachComponentSeparately() {
    Pipeline pipeline = compileSource(R"(workflow S budget 100000 {
  input flag: boolean max_tokens 1;
  input wide: text max_tokens 200;
  input narrow: text max_tokens 0;
  model small = mock("small") max_tokens 1;
  model large = mock("large") max_tokens 100;
  prompt p(x: text) -> text = "{x}";
  if flag {
    let a: text = call p(wide) using small;
  } else {
    let b: text = call p(narrow) using large;
  }
  output narrow;
})");
    requireSemanticallyValid(pipeline);
    const WorkflowCost& cost = onlyCost(pipeline);
    require(cost.bound.guaranteed >= 100, "the output component must dominate the larger arm's output");
    require(cost.bound.estimated >= 201, "the input component must dominate the larger arm's input");
    require(cost.bound.total() <= cost.bound.componentSum(),
            "the total bound is at least as tight as the sum of the components");
}

// Audit finding 3: the analysis and the runtime must measure a literal the same
// way, or the certified bound does not describe the execution.
void testLiteralAccountingAgreesWithRuntime() {
    const char* sources[] = {
        R"(workflow L budget 100 { model m = mock("m") max_tokens 1; prompt p(x: text) -> text = "{x}"; let y: text = call p("") using m; output y; })",
        R"(workflow L budget 100 { model m = mock("m") max_tokens 1; prompt p(x: boolean) -> text = "{x}"; let y: text = call p(false) using m; output y; })",
        R"(workflow L budget 100 { model m = mock("m") max_tokens 1; prompt p(x: text) -> text = "{x}"; let y: text = call p("hello world") using m; output y; })",
    };
    for (const char* source : sources) {
        Pipeline pipeline = compileSource(source);
        requireSemanticallyValid(pipeline);
        const CostBound bound = onlyCost(pipeline).bound;
        for (std::uint64_t seed = 1; seed <= 50; ++seed) {
            RunOptions options;
            options.seed = seed;
            Interpreter interpreter(options);
            const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
            const WorkflowRun& run = result.workflows.front();
            require(run.inputTokens <= bound.estimated,
                    "the runtime must not consume more input tokens than were certified");
            require(run.outputTokens <= bound.guaranteed,
                    "the runtime must not consume more output tokens than were certified");
            require(run.totalTokens() <= bound.total(), "nor more in total");
        }
    }
}

// Audit finding 4: a binding made inside a branch must not survive it at run
// time, or the runtime charges one model while executing another.
void testRuntimeRespectsBlockScope() {
    Pipeline pipeline = compileSource(R"(workflow Shadow budget 100000 {
  input flag: boolean max_tokens 1;
  input src: text max_tokens 0;
  model m = mock("outer") max_tokens 1;
  prompt p(x: text) -> text = "{x}";
  if flag {
    model m = mock("inner") max_tokens 1000;
  }
  let y: text = call p(src) using m;
  output y;
})");
    requireSemanticallyValid(pipeline);
    const std::size_t bound = onlyCost(pipeline).bound.total();
    for (std::uint64_t seed = 1; seed <= 100; ++seed) {
        RunOptions options;
        options.seed = seed;
        Interpreter interpreter(options);
        const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
        require(result.workflows.front().totalTokens() <= bound,
                "a model shadowed inside a branch must not leak out of it");
    }
}

// The relational claim itself: for an accepted workflow, changing only the
// secret must not change the bill.
void testAcceptedWorkflowHasSecretIndependentBilling() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 8;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(), "the workflow should be accepted");

    for (std::uint64_t seed = 1; seed <= 40; ++seed) {
        std::optional<WorkflowRun> reference;
        for (std::size_t secretLength = 0; secretLength <= 8; ++secretLength) {
            RunOptions options;
            options.seed = seed;
            options.pinnedLengths["x"] = 37;
            options.pinnedLengths["s"] = secretLength;
            Interpreter interpreter(options);
            const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
            const WorkflowRun& run = result.workflows.front();
            if (!reference) {
                reference = run;
            } else {
                require(sameBilling(*reference, run),
                        "changing only the secret must not change the bill");
            }
        }
    }
}

// And the converse: a workflow the analysis rejects really is one where the
// secret moves the bill, so the rejection is not spurious.
void testRejectedWorkflowActuallyLeaks() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 1;
  input x: text max_tokens 100;
  input y: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if tokens(s) == 0 {
    let a: text = call p(x) using m;
  } else {
    let b: text = call p(y) using m;
  }
  output "done";
})");
    require(hasCode(pipeline, "E236"), "the workflow should be rejected");

    // Public inputs of different lengths, both within their declared bounds.
    RunOptions base;
    base.seed = 11;
    base.pinnedLengths["x"] = 14;
    base.pinnedLengths["y"] = 52;

    RunOptions low = base;
    low.pinnedLengths["s"] = 0;
    RunOptions high = base;
    high.pinnedLengths["s"] = 1;

    Interpreter lowRun(low);
    Interpreter highRun(high);
    const RunResult first = lowRun.run(pipeline.parsed.program, *pipeline.semantic);
    const RunResult second = highRun.run(pipeline.parsed.program, *pipeline.semantic);
    require(!sameBilling(first.workflows.front(), second.workflows.front()),
            "the rejected workflow really does leak through the bill");
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
        {"secret-dependent cost is rejected", testSecretDependentCostIsRejected},
        {"equal bounds with different arguments rejected", testEqualBoundsWithDifferentArgumentsIsRejected},
        {"extra call in one arm rejected", testExtraCallInOneArmIsRejected},
        {"differing retry bounds rejected", testDifferingRetryBoundsAreRejected},
        {"matching retry bounds accepted", testMatchingRetryBoundsAreAccepted},
        {"chaining inside secret arm accepted (OP-1)", testChainingInsideSecretArmIsAccepted},
        {"OP-1: chain length depending on secret rejected", testChainLengthDependingOnSecretIsRejected},
        {"OP-1: chain fed a different prior result rejected", testChainFedDifferentPriorResultIsRejected},
        {"OP-1: chain fed outer variable instead of result rejected", testChainFedOuterVariableInsteadOfResultIsRejected},
        {"OP-1: chain through a different model rejected", testChainThroughDifferentModelIsRejected},
        {"OP-1: pc-secret value still cannot be emitted", testPcSecretValueStillCannotBeEmitted},
        {"OP-1: pc-secret value still cannot be output", testPcSecretValueStillCannotBeOutput},
        {"OP-1: pc-secret value cannot escape its arm", testPcSecretValueCannotEscapeItsArm},
        {"OP-1: declassify does not launder effects", testDeclassifyingPcSecretValueDoesNotLaunderEffects},
        {"OP-1: secret content still barred from prompts", testSecretContentStillCannotReachPromptInsideArm},
        {"OP-1: endorsed secret is still secret content", testEndorsedSecretIsStillSecretContent},
        {"OP-1: guard on pc-secret result public when arms match", testGuardOnPcSecretResultIsPublicWhenArmsMatch},
        {"OP-1: guard on pc-secret result with different threshold rejected", testGuardOnPcSecretResultWithDifferentThresholdIsRejected},
        {"OP-1: chain inside retry inside secret arm", testChainInsideRetryInsideSecretArm},
        {"OP-1: nested secret branch using pc-secret value", testNestedSecretBranchUsingPcSecretValue},
        {"content: equal-size literals are different requests", testEqualSizeLiteralsAreDifferentRequests},
        {"content: equal-size templates are different requests", testEqualSizeTemplatesAreDifferentRequests},
        {"content: same text via different prompt names is one request", testSameTextThroughDifferentPromptNamesIsTheSameRequest},
        {"F3: shadowed model in arm is a different endpoint", testShadowedModelInArmIsADifferentEndpoint},
        {"F3: shadowed prompt in arm is a different request", testShadowedPromptInArmIsADifferentRequest},
        {"E203: input declared inside an arm rejected", testInputDeclaredInsideArmIsRejected},
        {"F4: billing keyed by provider model name", testBillingIsKeyedByProviderModelName},
        {"OP-4: one-bit branch needs a budget", testOneBitBranchNeedsABudget},
        {"OP-4: thresholds on one secret count intervals", testThresholdsOnOneSecretCountIntervals},
        {"OP-4: independent secrets multiply classes", testIndependentSecretsMultiplyClasses},
        {"OP-4: cancelling branches accepted globally", testCancellingBranchesAreAcceptedGlobally},
        {"OP-7: reordering visible to trace observer", testReorderingIsVisibleToTheTraceObserver},
        {"OP-7: reordering across providers invisible to each", testReorderingAcrossProvidersIsInvisibleToEachProvider},
        {"OP-7: reordering within one provider visible to it", testReorderingWithinOneProviderIsVisibleToIt},
        {"OP-7: reordering invisible on the invoice", testReorderingIsInvisibleOnTheInvoice},
        {"OP-7: dependent calls not reordered for the bill", testDependentCallsAreNotReorderedForTheBill},
        {"OP-7: calls inside retry are never reordered", testCallsInsideRetryAreNeverReordered},
        {"OP-3: guaranteed input built from bytes", testGuaranteedInputIsBuiltFromBytes},
        {"OP-3: unverified tokenizer gives no guarantee", testUnverifiedTokenizerGivesNoGuarantee},
        {"OP-3: unknown tokenizer is an error", testUnknownTokenizerIsAnError},
        {"OP-3: estimate-unit input has no byte bound", testEstimateUnitInputHasNoByteBound},
        {"OP-3: token bound under named tokenizer gives bytes", testTokenBoundUnderNamedTokenizerGivesBytes},
        {"OP-3: chained call uses response byte bound", testChainedCallUsesResponseByteBound},
        {"OP-3: guaranteed bound holds under real tokenization", testGuaranteedBoundHoldsUnderRealTokenization},
        {"OP-3: mock tokenizer is not subadditive", testMockTokenizerIsNotSubadditive},
        {"OP-11: SHA-256 matches standard vectors", testSha256MatchesStandardVectors},
        {"withdrawn rules reproduced as baselines", testWithdrawnRulesAreReproducedAsBaselines},
        {"public guard inside secret arm allowed", testPublicGuardInsideSecretArmIsAllowed},
        {"differing public sub-branch rejected", testDifferingPublicSubBranchIsRejected},
        {"branch bounds each component separately", testBranchBoundsEachComponentSeparately},
        {"literal accounting agrees with runtime", testLiteralAccountingAgreesWithRuntime},
        {"runtime respects block scope", testRuntimeRespectsBlockScope},
        {"accepted workflow has secret-independent billing", testAcceptedWorkflowHasSecretIndependentBilling},
        {"rejected workflow actually leaks", testRejectedWorkflowActuallyLeaks},
        {"balanced arms under secret accepted", testBalancedArmsUnderSecretAreAccepted},
        {"public guard with unequal arms fine", testPublicGuardWithUnequalArmsIsFine},
        {"untrusted guard on unequal arms warns", testUntrustedGuardOnUnequalArmsWarns},
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
