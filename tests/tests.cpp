#include "ast.hpp"
#include "certificate.hpp"
#include "cost_analyzer.hpp"
#include "interpreter.hpp"
#include "relational.hpp"
#include "ir.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "semantic_analyzer.hpp"

#include <exception>
#include <functional>
#include <iostream>
#include <limits>
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
    std::optional<RelationalResult> relational;
};

Pipeline compileSource(const std::string& source) {
    Lexer lexer(source, "test.orch");
    LexResult lexed = lexer.scan();
    Parser parser(lexed.tokens);
    ParseResult parsed = parser.parse();
    Pipeline result{std::move(lexed), std::move(parsed), std::nullopt, std::nullopt, std::nullopt};
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
        printCertificate(pipeline.parsed.program, *pipeline.semantic, *pipeline.cost, lowered.program,
                         *pipeline.relational);
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
    require(certificate.find("\"call_facts\"") != std::string::npos &&
                certificate.find("\"template_text\"") != std::string::npos &&
                certificate.find("\"arguments\"") != std::string::npos &&
                certificate.find("\"literal_expr_kind\"") != std::string::npos,
            "the certificate should expose source-bound request facts including literal kinds");
    require(certificate.find("\"total_tokens\"") != std::string::npos,
            "each derivation record should carry its total token bound");
    require(certificate.find("\"declassification_present\": false") != std::string::npos &&
                certificate.find("\"billing_noninterference_claimed\": true") !=
                    std::string::npos,
            "endorsement does not suppress the billing claim, and a no-declass workflow records it");
    require(certificate.find("local structural request-trace comparison") != std::string::npos &&
                certificate.find("request envelopes") != std::string::npos &&
                certificate.find("Ω(M,k,Q)") != std::string::npos &&
                certificate.find("default ordinal mock ignores Q") != std::string::npos &&
                certificate.find("Value(tokens,flag)") != std::string::npos,
            "the certificate states the local relation, accounting assumptions, and mock oracle scope");

    const std::string source = "workflow H budget 0 { output \"ok\"; }";
    Pipeline sourcePipeline = compileSource(source);
    requireSemanticallyValid(sourcePipeline);
    IRBuildResult sourceIr = lowerer.lower(sourcePipeline.parsed.program, *sourcePipeline.semantic);
    const std::string sourceBound = printCertificate(
        sourcePipeline.parsed.program, *sourcePipeline.semantic, *sourcePipeline.cost,
        sourceIr.program, *sourcePipeline.relational, source);
    require(sourceBound.find(
                "\"source_sha256\": \"aaafc99adea8127bc6aa6cdbc7dd7cdcc9e2bce555da24940d1c9a2298d34084\"") !=
                std::string::npos,
            "the certificate binds its facts to raw source bytes with SHA-256");

    const std::string pricedSource = R"(workflow Price budget 10 {
  input d: text max_tokens 4;
  model m = mock("m") max_tokens 1 cost_per_token 0.12345678901234567;
  prompt p(t: text) -> text = "{t}";
  let result: text = call p(d) using m;
  output "done";
})";
    Pipeline priced = compileSource(pricedSource);
    requireSemanticallyValid(priced);
    IRBuildResult pricedIr = lowerer.lower(priced.parsed.program, *priced.semantic);
    const std::string pricedCertificate = printCertificate(
        priced.parsed.program, *priced.semantic, *priced.cost, pricedIr.program,
        *priced.relational, pricedSource);
    require(pricedCertificate.find("\"unit_price\": 0.12345678901234566") != std::string::npos,
            "the certificate preserves the declared binary double price precisely");
    require(pricedCertificate.find("\"cost\": 0.74074073407407393") != std::string::npos,
            "the certificate preserves the nominal derived cost without six-digit rounding");

    const std::string declassifiedSource = R"(workflow Released budget 5000 {
  secret key: text max_tokens 8;
  declassify(key) as released: text because "authorized release";
  output released;
})";
    Pipeline declassified = compileSource(declassifiedSource);
    requireSemanticallyValid(declassified);
    IRBuildResult declassifiedIr = lowerer.lower(
        declassified.parsed.program, *declassified.semantic);
    const std::string declassifiedCertificate = printCertificate(
        declassified.parsed.program, *declassified.semantic, *declassified.cost,
        declassifiedIr.program, *declassified.relational, declassifiedSource);
    require(declassifiedCertificate.find("\"declassification_present\": true") !=
                std::string::npos &&
                declassifiedCertificate.find("\"billing_noninterference_claimed\": false") !=
                    std::string::npos,
            "any declassification withholds the unconditional billing claim");
}

void testNonFiniteModelPriceIsRejected() {
    const std::string overflowingPrice = "1" + std::string(399, '0');
    const std::string source =
        "workflow PriceRange budget 100 { model m = mock(\"m\") max_tokens 2 cost_per_token " +
        overflowingPrice + "; output \"done\"; }";
    Pipeline pipeline = compileSource(source);
    require(hasCode(pipeline, "P007"),
            "a decimal lexeme that overflows double must be rejected during parsing");
}

void testDerivedMonetaryOverflowIsRejected() {
    const std::string finiteHugePrice = "1" + std::string(308, '0');
    const std::string source =
        "workflow MoneyOverflow budget 100 { model m = mock(\"m\") max_tokens 2 cost_per_token " +
        finiteHugePrice +
        "; prompt p() -> text = \"a\"; let r: text = call p() using m; output r; }";
    Pipeline pipeline = compileSource(source);
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E268"),
            "finite model price multiplied by bounded usage must reject an infinite derived cost");
}

void testJsonExportsEscapeAllControlBytes() {
    std::string modelName = "mock";
    modelName.push_back('\x01');
    modelName += "model";
    const std::string source = "workflow Control budget 100 { model m = mock(\"" + modelName +
        "\") max_tokens 10; prompt p() -> text = \"a\"; "
        "let r: text = call p() using m; output r; }";
    Pipeline pipeline = compileSource(source);
    requireSemanticallyValid(pipeline);
    IRLowerer lowerer;
    IRBuildResult lowered = lowerer.lower(pipeline.parsed.program, *pipeline.semantic);
    require(lowered.success(), "control-byte model metadata should lower successfully");

    const auto hasEscapedControl = [&](const std::string& json) {
        return json.find("\\u0001") != std::string::npos &&
               json.find('\x01') == std::string::npos;
    };
    require(hasEscapedControl(printIRJson(lowered.program)),
            "IR JSON must escape every raw control byte");

    const std::string certificate = printCertificate(
        pipeline.parsed.program, *pipeline.semantic, *pipeline.cost, lowered.program,
        *pipeline.relational, source);
    require(hasEscapedControl(certificate), "certificate JSON must escape every raw control byte");

    Interpreter interpreter(RunOptions{});
    const RunResult run = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
    require(run.success(), "the control-byte workflow should execute");
    require(hasEscapedControl(printRunJson(run)), "run JSON must escape every raw control byte");
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

void testRunReportsStructuredTraceAndBilling() {
    Pipeline pipeline = compileSource(R"(workflow Trace budget 100000 {
  input choose: boolean max_tokens 1;
  input x: text max_tokens 20;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if choose {
    retry 3 { let a: text = call p(x) using m; }
  } else {
    let b: text = call p(x) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    RunOptions options;
    options.pinnedFlags["choose"] = true;
    options.retryFailurePercent = 0;
    Interpreter interpreter(options);
    const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
    require(result.success(), "the trace example should run");
    const WorkflowRun& run = result.workflows.front();
    require(run.branches.size() == 1 && run.branches.front().tookThen,
            "the run records which branch arm executed");
    require(run.retries.size() == 1 && run.retries.front().attempts == 1,
            "the run records retry attempts at their source location");
    const std::string text = printRun(result);
    require(text.find("branch @6:3 then") != std::string::npos,
            "text output exposes branch path and source coordinates");
    require(text.find("retry @7:5 attempts 1") != std::string::npos,
            "text output exposes retry attempts and source coordinates");
    const std::string json = printRunJson(result);
    require(json.find("\"decision\":\"then\"") != std::string::npos &&
                json.find("\"attempts\":1") != std::string::npos,
            "JSON output exposes branch decisions and retry counts");
    require(json.find("\"billing\":[{\"model_contract\":\"p4x6d6f636b_m1x6d_cap10_priced0\"") !=
                std::string::npos,
            "billing is keyed by a whitespace-free resolved model contract");
}

void testRunRefusesIllTypedProgram() {
    Pipeline pipeline = compileSource("workflow B budget 10 { secret k; output k; }");
    require(pipeline.semantic.has_value(), "semantic analysis should run");
    RunOptions options;
    Interpreter interpreter(options);
    const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
    require(!result.success(), "an ill-typed workflow must not be executed");
}

void testRunValidatesPinsAgainstDeclarations() {
    Pipeline pipeline = compileSource(R"(workflow Pins budget 1000 {
  input payload: text max_tokens 4;
  input flag: boolean;
  input free: text;
  secret key: text max_tokens 3;
  output "done";
})");
    requireSemanticallyValid(pipeline);

    RunOptions validOptions;
    validOptions.pinnedLengths["payload"] = 4;
    validOptions.pinnedLengths["key"] = 3;
    validOptions.pinnedLengths["free"] = 17;
    validOptions.pinnedFlags["flag"] = true;
    Interpreter validInterpreter(validOptions);
    require(validInterpreter.run(pipeline.parsed.program, *pipeline.semantic).success(),
            "pins at declared bounds, boolean pins, and unbounded non-prompt text pins are valid");

    RunOptions tooLong;
    tooLong.pinnedLengths["payload"] = 5;
    Interpreter tooLongInterpreter(tooLong);
    const RunResult tooLongResult = tooLongInterpreter.run(pipeline.parsed.program, *pipeline.semantic);
    require(!tooLongResult.success() && hasCode(tooLongResult.diagnostics, "R002"),
            "a pinned length above declared max_tokens is rejected before execution");

    RunOptions unrepresentable;
    unrepresentable.pinnedLengths["payload"] = std::numeric_limits<std::size_t>::max();
    Interpreter unrepresentableInterpreter(unrepresentable);
    require(!unrepresentableInterpreter.run(pipeline.parsed.program, *pipeline.semantic).success(),
            "an overflowing or otherwise unrepresentable pin cannot bypass a declared bound");

    RunOptions wrongLengthType;
    wrongLengthType.pinnedLengths["flag"] = 1;
    Interpreter wrongLengthInterpreter(wrongLengthType);
    require(!wrongLengthInterpreter.run(pipeline.parsed.program, *pipeline.semantic).success(),
            "length pins apply only to text declarations");

    RunOptions wrongFlagType;
    wrongFlagType.pinnedFlags["payload"] = true;
    Interpreter wrongFlagInterpreter(wrongFlagType);
    require(!wrongFlagInterpreter.run(pipeline.parsed.program, *pipeline.semantic).success(),
            "boolean pins apply only to boolean declarations");

    RunOptions unknown;
    unknown.pinnedLengths["missing"] = 1;
    Interpreter unknownInterpreter(unknown);
    require(!unknownInterpreter.run(pipeline.parsed.program, *pipeline.semantic).success(),
            "a pin for an undeclared name is rejected");
}

void testRunTotalTokenCountSaturates() {
    WorkflowRun run;
    run.inputTokens = std::numeric_limits<std::size_t>::max() - 1;
    run.outputTokens = 10;
    require(run.totalTokens() == std::numeric_limits<std::size_t>::max(),
            "reported aggregate token counts must not wrap under unsafe witness runs");
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

// The content label excludes control dependence. The result exists only on one
// arm, so the relational gate must prove that the matched request sequence and
// shared model oracle produce the same bill before this chain is accepted.
void testMatchedChainingInsideSecretArmsIsAccepted() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 100;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    let a1: text = call p(x) using m;
    let a2: text = call p(a1) using m;
  } else {
    let b1: text = call p(x) using m;
    let b2: text = call p(b1) using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "matched chains may use prior results when both secret arms make the same requests");
    for (const bool requestSensitive : {false, true}) {
        for (std::uint64_t seed = 1; seed <= 25; ++seed) {
            std::optional<WorkflowRun> reference;
            for (const bool secretFlag : {false, true}) {
                RunOptions options;
                options.seed = seed;
                options.requestSensitiveOracle = requestSensitive;
                options.pinnedFlags["s"] = secretFlag;
                Interpreter interpreter(options);
                const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
                require(result.success(), "an accepted chained workflow should run");
                const WorkflowRun& run = result.workflows.front();
                if (reference) {
                    require(sameBilling(*reference, run),
                            "changing the secret must preserve billing under both oracle modes");
                } else {
                    reference = run;
                }
            }
        }
    }
}

void testRequestSensitiveOracleUsesExactQueryContent() {
    const auto requireRequestDifference = [](const std::string& source,
                                             const std::string& caseName) {
        Pipeline pipeline = compileSource(source);
        requireSemanticallyValid(pipeline);
        require(hasCode(pipeline, "E236"), caseName + " should have unequal relational requests");
        bool observedDifferentResponses = false;
        for (std::uint64_t seed = 1; seed <= 32 && !observedDifferentResponses; ++seed) {
            std::optional<std::size_t> firstOutput;
            for (const bool secretFlag : {false, true}) {
                RunOptions options;
                options.seed = seed;
                options.auditUnsafe = true;
                options.requestSensitiveOracle = true;
                options.pinnedFlags["s"] = secretFlag;
                Interpreter interpreter(options);
                const RunResult run = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
                require(run.success(), "unsafe request probes remain executable offline");
                require(run.workflows.front().trace.size() == 1,
                        "each request probe executes exactly one model call");
                const std::size_t output = run.workflows.front().trace.front().outputTokens;
                if (firstOutput) {
                    observedDifferentResponses = *firstOutput != output;
                } else {
                    firstOutput = output;
                }
            }
        }
        require(observedDifferentResponses,
                caseName + " should affect at least one seeded abstract response");
    };

    const std::string modelAndHeader = R"(workflow Query budget 3000000 {
  secret s: boolean max_tokens 1;
  model m = mock("same-model") max_tokens 1000000;
)";
    const std::string footer = R"(  output "done";
})";
    requireRequestDifference(modelAndHeader + R"(  prompt p(t: text) -> text = "{t}";
  prompt q(t: text) -> text = " {t}";
  if s { let a: text = call p("payload") using m; }
  else { let b: text = call q("payload") using m; }
)" + footer,
                            "template bytes");
    requireRequestDifference(modelAndHeader + R"(  prompt p(t: text) -> text = "{t}";
  if s { let a: text = call p("alpha") using m; }
  else { let b: text = call p("bravo") using m; }
)" + footer,
                            "literal bytes");
    requireRequestDifference(modelAndHeader + R"(  prompt p(a: text, b: text) -> text = "{a}{b}";
  if s { let a: text = call p("left", "right") using m; }
  else { let b: text = call p("right", "left") using m; }
)" + footer,
                            "argument order");
}

void testTypedLiteralIdentityInRelationalSignatures() {
    const auto requireKindCollision = [](const std::string& promptDeclarations,
                                         const std::string& thenCall,
                                         const std::string& elseCall,
                                         const std::string& caseName) {
        const std::string source =
            "workflow TypedLiteralCollision budget 100000 {\n"
            "  secret s: boolean max_tokens 1;\n"
            "  model m = mock(\"same-model\") max_tokens 64;\n" +
            promptDeclarations +
            "  if s { let left: text = " + thenCall + " using m; }\n"
            "  else { let right: text = " + elseCall + " using m; }\n"
            "  output \"done\";\n"
            "}";
        Pipeline pipeline = compileSource(source);
        requireSemanticallyValid(pipeline);
        require(hasCode(pipeline, "E236"),
                caseName + " must not couple different typed request literals");

        bool observedDifferentResponse = false;
        for (std::uint64_t seed = 1; seed <= 32 && !observedDifferentResponse; ++seed) {
            std::optional<std::size_t> firstOutput;
            for (const bool secretFlag : {false, true}) {
                RunOptions options;
                options.seed = seed;
                options.auditUnsafe = true;
                options.requestSensitiveOracle = true;
                options.pinnedFlags["s"] = secretFlag;
                const RunResult result = Interpreter(options).run(
                    pipeline.parsed.program, *pipeline.semantic);
                require(result.success(), "typed-literal witness must execute in audit mode");
                require(result.workflows.front().trace.size() == 1,
                        "typed-literal witness should issue one call per secret assignment");
                const std::size_t output = result.workflows.front().trace.front().outputTokens;
                if (firstOutput) {
                    observedDifferentResponse = *firstOutput != output;
                } else {
                    firstOutput = output;
                }
            }
        }
        require(observedDifferentResponse,
                caseName + " must distinguish the abstract request under a seeded oracle");
    };

    requireKindCollision(
        "  prompt p(v: boolean) -> text = \"{v}\";\n"
        "  prompt q(v: text) -> text = \"{v}\";\n",
        "call p(true)", "call q(\"true\")", "boolean/text true collision");
    requireKindCollision(
        "  prompt p(v: integer) -> text = \"{v}\";\n"
        "  prompt q(v: text) -> text = \"{v}\";\n",
        "call p(7)", "call q(\"7\")", "integer/text 7 collision");

    const auto requireSameTypedRequestsAccepted = [](const std::string& promptDeclaration,
                                                      const std::string& call) {
        Pipeline pipeline = compileSource(
            "workflow SameTypedLiteral budget 100000 {\n"
            "  secret s: boolean max_tokens 1;\n"
            "  model m = mock(\"same-model\") max_tokens 64;\n" +
            promptDeclaration +
            "  if s { let left: text = " + call + " using m; }\n"
            "  else { let right: text = " + call + " using m; }\n"
            "  output \"done\";\n"
            "}");
        requireSemanticallyValid(pipeline);
        require(pipeline.relational->success(),
                "identical typed literals and request contracts remain admissible");
    };
    requireSameTypedRequestsAccepted("  prompt p(v: boolean) -> text = \"{v}\";\n",
                                     "call p(true)");
    requireSameTypedRequestsAccepted("  prompt p(v: integer) -> text = \"{v}\";\n",
                                     "call p(7)");
}

void testDifferentLiteralBytesInMatchedChainAreRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    let first: text = call p("alpha") using m;
    let second: text = call p("next") using m;
  } else {
    let first: text = call p("bravo") using m;
    let second: text = call p("next") using m;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"),
            "different literal bytes with equal token estimates must not couple as one request");
}

void testDirectSecretPromptArgumentRemainsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: text max_tokens 8;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  let result: text = call p(s) using m;
  output "done";
})");
    require(hasCode(pipeline, "E230"), "direct secret content remains forbidden at prompt calls");
}

void testAliasesWithTheSameResolvedModelContractAreEquivalent() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 20;
  model left = mock("same-id") max_tokens 10;
  model right = mock("same-id") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    let a: text = call p(x) using left;
  } else {
    let b: text = call p(x) using right;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "source aliases do not distinguish identical resolved model contracts");
}

void testDifferentModelCapsAreNotEquivalent() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 20;
  model left = mock("same-id") max_tokens 10;
  model right = mock("same-id") max_tokens 11;
  prompt p(t: text) -> text = "{t}";
  if s {
    let a: text = call p(x) using left;
  } else {
    let b: text = call p(x) using right;
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"), "output caps are part of the resolved request contract");
}

void testCrossTokenizerResultChainIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input x: text max_tokens 20;
  model first = mock("model-a") max_tokens 10;
  model second = mock("model-b") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  let a: text = call p(x) using first;
  let b: text = call p(a) using second;
  output "done";
})");
    require(hasCode(pipeline, "E267"),
            "an output cap in one tokenizer cannot bound another model's input");
}

void testSameTokenizerWithDifferentCapsCanChain() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  input x: text max_tokens 20;
  model first = mock("shared-tokenizer") max_tokens 10;
  model second = mock("shared-tokenizer") max_tokens 11;
  prompt p(t: text) -> text = "{t}";
  let a: text = call p(x) using first;
  let b: text = call p(a) using second;
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "different output caps do not change the tokenizer identity for a sequential chain");
}

void testNestedBranchAndRetryChainsCouplePositionally() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 20;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    retry 2 { let a: text = call p(x) using m; let b: text = call p(a) using m; }
  } else {
    retry 2 { let c: text = call p(x) using m; let d: text = call p(c) using m; }
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "matched retry chains use the same positional result and attempt schedule");
    for (std::uint64_t seed = 1; seed <= 20; ++seed) {
        std::optional<WorkflowRun> reference;
        for (const bool secretFlag : {false, true}) {
            RunOptions options;
            options.seed = seed;
            options.pinnedFlags["s"] = secretFlag;
            Interpreter interpreter(options);
            const RunResult result = interpreter.run(pipeline.parsed.program, *pipeline.semantic);
            require(result.success(), "the matched retry-chain workflow should run");
            const WorkflowRun& run = result.workflows.front();
            if (reference) {
                require(sameBilling(*reference, run),
                        "retry attempt choices and billing must agree across secret arms");
            } else {
                reference = run;
            }
        }
    }
}

void testPublicGuardIdentityUsesResolvedLexicalValue() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 20;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    let prior: text = call p(x) using m;
    if tokens(prior) <= 5 { let a: text = call p(prior) using m; }
  } else {
    let prior: text = call p(x) using m;
    if tokens(prior) <= 5 { let b: text = call p(prior) using m; }
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(pipeline.relational->success(),
            "branch-local names resolve to the corresponding prior result position");
}

void testUnequalNormalizedGuardInsideSecretArmsIsRejected() {
    Pipeline pipeline = compileSource(R"(workflow C budget 100000 {
  secret s: boolean max_tokens 1;
  input x: text max_tokens 20;
  model m = mock("m") max_tokens 10;
  prompt p(t: text) -> text = "{t}";
  if s {
    let prior: text = call p(x) using m;
    if tokens(prior) <= 5 { let a: text = call p(prior) using m; }
  } else {
    let prior: text = call p(x) using m;
    if tokens(prior) <= 6 { let b: text = call p(prior) using m; }
  }
  output "done";
})");
    requireSemanticallyValid(pipeline);
    require(hasCode(pipeline, "E236"),
            "different comparison limits produce different normalized guard paths");
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

    RunOptions safeOptions;
    Interpreter safeByDefault(safeOptions);
    const RunResult refused = safeByDefault.run(pipeline.parsed.program, *pipeline.semantic);
    require(!refused.success() && hasCode(refused.diagnostics, "E236"),
            "the runtime refuses a relationally rejected workflow by default");

    // Public inputs of different lengths, both within their declared bounds.
    RunOptions base;
    base.seed = 11;
    base.auditUnsafe = true;
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
        {"matched chaining inside secret arms accepted", testMatchedChainingInsideSecretArmsIsAccepted},
        {"request-sensitive oracle uses exact query", testRequestSensitiveOracleUsesExactQueryContent},
        {"typed literal identity in relational signatures", testTypedLiteralIdentityInRelationalSignatures},
        {"different literal bytes in chain rejected", testDifferentLiteralBytesInMatchedChainAreRejected},
        {"direct secret prompt argument remains rejected", testDirectSecretPromptArgumentRemainsRejected},
        {"same resolved model aliases accepted", testAliasesWithTheSameResolvedModelContractAreEquivalent},
        {"different model caps rejected", testDifferentModelCapsAreNotEquivalent},
        {"cross-tokenizer chain rejected", testCrossTokenizerResultChainIsRejected},
        {"same tokenizer different caps can chain", testSameTokenizerWithDifferentCapsCanChain},
        {"nested retry chains couple positionally", testNestedBranchAndRetryChainsCouplePositionally},
        {"public guard identity uses lexical result", testPublicGuardIdentityUsesResolvedLexicalValue},
        {"unequal normalized guards rejected", testUnequalNormalizedGuardInsideSecretArmsIsRejected},
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
        {"run reports structured trace and billing", testRunReportsStructuredTraceAndBilling},
        {"run refuses ill-typed program", testRunRefusesIllTypedProgram},
        {"run validates pins against declarations", testRunValidatesPinsAgainstDeclarations},
        {"run total token count saturates", testRunTotalTokenCountSaturates},
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
        {"nonfinite model price rejected", testNonFiniteModelPriceIsRejected},
        {"derived monetary overflow rejected", testDerivedMonetaryOverflowIsRejected},
        {"JSON exports escape all control bytes", testJsonExportsEscapeAllControlBytes},
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
