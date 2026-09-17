#include "semantic_analyzer.hpp"

#include "token_cost.hpp"

#include <algorithm>
#include <cctype>
#include <limits>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace orchlang {

std::size_t estimateTextTokens(const std::string& text, std::size_t charsPerToken) {
    const std::size_t divisor = charsPerToken == 0 ? 1 : charsPerToken;
    return (text.size() + divisor - 1) / divisor;
}

namespace {

bool isPlaceholderName(const std::string& name) {
    if (name.empty()) {
        return false;
    }
    const unsigned char first = static_cast<unsigned char>(name.front());
    if (std::isalpha(first) == 0 && name.front() != '_') {
        return false;
    }
    for (const char character : name) {
        const unsigned char value = static_cast<unsigned char>(character);
        if (std::isalnum(value) == 0 && character != '_') {
            return false;
        }
    }
    return true;
}

// What the analysis knows about one expression: its type, its security label,
// and an upper bound on the tokens it occupies.
struct ValueFacts {
    Type type{TypeKind::Unknown};
    Label label{publicTrusted()};
    bool tokenBoundKnown{false};
    std::size_t tokenBound{0};
};

// Per-block analysis context.  The program-counter label is what carries
// implicit flows: inside a branch guarded by a secret, pc is secret, and every
// value produced there inherits it.
struct Context {
    std::size_t scope{0};
    Label pc{publicTrusted()};
    std::string workflow;
};

class Analyzer {
public:
    Analyzer(SemanticResult& result, const AnalysisOptions& options)
        : result_(result), options_(options) {}

    void run(const Program& program);

private:
    void analyzeWorkflow(const WorkflowDecl& workflow);
    void analyzeBlock(const Block& block, const Context& context);
    void analyzeStatement(const Stmt& statement, const Context& context);

    void declareInput(const InputDecl& input, const Context& context);
    void declareSecret(const SecretDecl& secret, const Context& context);
    void declareModel(const ModelDecl& model, const Context& context);
    void declarePrompt(const PromptDecl& prompt, const Context& context);
    void declareTool(const ToolDecl& tool, const Context& context);
    void analyzeLet(const LetStmt& let, const Context& context);
    void analyzeRequire(const RequireStmt& requirement, const Context& context);
    void analyzeEmit(const EmitStmt& emit, const Context& context);
    void analyzeIf(const IfStmt& branch, const Context& context);
    void analyzeRetry(const RetryStmt& retry, const Context& context);
    void analyzeReclassify(const ReclassifyStmt& reclassify, const Context& context);
    void analyzeOutput(const OutputStmt& output, const Context& context);

    ValueFacts inspect(const Expr& expression, const Context& context);
    ValueFacts inspectCall(const CallExpr& call, const Context& context);
    void checkPlaceholders(const PromptDecl& prompt);
    bool insertSymbol(std::size_t scope, Symbol symbol);

    SemanticResult& result_;
    AnalysisOptions options_;
    std::size_t outputCount_{0};
};

bool Analyzer::insertSymbol(std::size_t scope, Symbol symbol) {
    const Symbol* existing = nullptr;
    const Symbol candidate = symbol;
    if (result_.symbols.insert(scope, std::move(symbol), &existing)) {
        return true;
    }
    if (existing) {
        result_.diagnostics.error("E201", candidate.location,
                                  "duplicate declaration '" + candidate.name + "'; first declared at " +
                                      formatLocation(existing->location));
    }
    return false;
}

ValueFacts Analyzer::inspect(const Expr& expression, const Context& context) {
    switch (expression.kind()) {
        case ExprKind::Identifier: {
            const auto& identifier = static_cast<const IdentifierExpr&>(expression);
            const Symbol* symbol = result_.symbols.lookup(context.scope, identifier.name);
            if (!symbol) {
                result_.diagnostics.error("E202", expression.location,
                                          "use of undeclared identifier '" + identifier.name + "'");
                return {};
            }
            ValueFacts facts;
            facts.type = symbol->type;
            facts.label = symbol->label;
            facts.tokenBoundKnown = symbol->tokenBoundKnown;
            facts.tokenBound = symbol->tokenBound;
            return facts;
        }
        case ExprKind::StringLiteral: {
            const auto& literal = static_cast<const StringLiteralExpr&>(expression);
            return {{TypeKind::Text}, publicTrusted(), true,
                    estimateTextTokens(literal.value, options_.charsPerToken)};
        }
        case ExprKind::IntegerLiteral: {
            const auto& literal = static_cast<const IntegerLiteralExpr&>(expression);
            return {{TypeKind::Integer}, publicTrusted(), true,
                    estimateTextTokens(literal.value, options_.charsPerToken)};
        }
        case ExprKind::DecimalLiteral: {
            const auto& literal = static_cast<const DecimalLiteralExpr&>(expression);
            return {{TypeKind::Decimal}, publicTrusted(), true,
                    estimateTextTokens(literal.value, options_.charsPerToken)};
        }
        case ExprKind::BooleanLiteral:
            return {{TypeKind::Boolean}, publicTrusted(), true, 1};
        case ExprKind::Call:
            // A call is only syntactically reachable as the right side of a let.
            return {};
    }
    return {};
}

void Analyzer::checkPlaceholders(const PromptDecl& prompt) {
    std::set<std::string> parameterNames;
    for (const Parameter& parameter : prompt.parameters) {
        parameterNames.insert(parameter.name);
    }
    std::set<std::string> seen;
    const std::string& text = prompt.templateText;
    for (std::size_t index = 0; index < text.size(); ++index) {
        if (text[index] == '}') {
            result_.diagnostics.error("E222", prompt.location,
                                      "unexpected '}' in prompt template for '" + prompt.name + "'");
            continue;
        }
        if (text[index] != '{') {
            continue;
        }
        const std::size_t closing = text.find('}', index + 1);
        if (closing == std::string::npos) {
            result_.diagnostics.error("E222", prompt.location,
                                      "unterminated placeholder in prompt template for '" + prompt.name + "'");
            break;
        }
        const std::string placeholder = text.substr(index + 1, closing - index - 1);
        if (!isPlaceholderName(placeholder)) {
            result_.diagnostics.error("E222", prompt.location,
                                      "malformed placeholder '{" + placeholder + "}' in prompt '" + prompt.name + "'");
        } else if (parameterNames.find(placeholder) == parameterNames.end()) {
            result_.diagnostics.error("E222", prompt.location,
                                      "placeholder '{" + placeholder + "}' does not match a declared parameter of prompt '" + prompt.name + "'");
        } else if (!seen.insert(placeholder).second) {
            result_.diagnostics.error("E222", prompt.location,
                                      "placeholder '{" + placeholder + "}' is duplicated in prompt '" + prompt.name + "'");
        }
        index = closing;
    }
    for (const Parameter& parameter : prompt.parameters) {
        if (seen.find(parameter.name) == seen.end()) {
            result_.diagnostics.error("E222", parameter.location,
                                      "prompt parameter '" + parameter.name + "' has no matching placeholder");
        }
    }
}

void Analyzer::declareInput(const InputDecl& input, const Context& context) {
    Symbol symbol{input.name,   SymbolKind::Input, input.type, "", input.location, std::nullopt,
                  std::nullopt, std::nullopt,      input.label};
    symbol.tokenBoundKnown = input.hasTokenBound;
    symbol.tokenBound = input.tokenBound;
    insertSymbol(context.scope, std::move(symbol));
}

void Analyzer::declareSecret(const SecretDecl& secret, const Context& context) {
    Symbol symbol{secret.name,  SymbolKind::Secret, secret.type,
                  "",           secret.location,    std::nullopt,
                  std::nullopt, std::nullopt,       Label{Confidentiality::Secret, Integrity::Trusted}};
    symbol.tokenBoundKnown = secret.hasTokenBound;
    symbol.tokenBound = secret.tokenBound;
    insertSymbol(context.scope, std::move(symbol));
}

void Analyzer::declareModel(const ModelDecl& model, const Context& context) {
    ModelMetadata metadata{model.provider, model.modelName, model.maxTokens, model.hasUnitPrice,
                           model.unitPrice};
    Symbol symbol{model.name,   SymbolKind::Model, {TypeKind::Unknown}, "", model.location, metadata,
                  std::nullopt, std::nullopt,      publicTrusted()};
    insertSymbol(context.scope, std::move(symbol));
}

void Analyzer::declarePrompt(const PromptDecl& prompt, const Context& context) {
    PromptSignature signature;
    signature.returnType = prompt.returnType;
    for (const Parameter& parameter : prompt.parameters) {
        signature.parameters.push_back({parameter.name, parameter.type});
    }
    signature.templateTokens = estimateTextTokens(prompt.templateText, options_.charsPerToken);

    Symbol symbol{prompt.name,  SymbolKind::Prompt, prompt.returnType, "", prompt.location, std::nullopt,
                  signature,    std::nullopt,       publicTrusted()};
    insertSymbol(context.scope, std::move(symbol));

    const std::size_t parameterScope = result_.symbols.createScope(
        "workflow:" + context.workflow + "::prompt:" + prompt.name, context.scope);
    for (const Parameter& parameter : prompt.parameters) {
        Symbol parameterSymbol{parameter.name, SymbolKind::PromptParameter, parameter.type,
                               "",             parameter.location,          std::nullopt,
                               std::nullopt,   std::nullopt,                publicTrusted()};
        insertSymbol(parameterScope, std::move(parameterSymbol));
    }
    checkPlaceholders(prompt);
}

void Analyzer::declareTool(const ToolDecl& tool, const Context& context) {
    ToolSignature signature;
    for (const Parameter& parameter : tool.parameters) {
        signature.parameters.push_back({parameter.name, parameter.type});
    }
    Symbol symbol{tool.name,    SymbolKind::Tool, {TypeKind::Unknown}, "", tool.location, std::nullopt,
                  std::nullopt, signature,        publicTrusted()};
    insertSymbol(context.scope, std::move(symbol));
}

ValueFacts Analyzer::inspectCall(const CallExpr& call, const Context& context) {
    const Symbol* prompt = result_.symbols.lookup(context.scope, call.promptName);
    const Symbol* model = result_.symbols.lookup(context.scope, call.modelName);

    std::vector<ValueFacts> arguments;
    arguments.reserve(call.arguments.size());
    for (const auto& argument : call.arguments) {
        arguments.push_back(argument ? inspect(*argument, context) : ValueFacts{});
    }

    // A prompt argument is the point where workflow data becomes model input.
    // A secret may not cross it, and an argument with no token bound leaves the
    // input half of the cost bound undefined.
    Label argumentJoin = context.pc;
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const ValueFacts& argument = arguments[index];
        if (argument.label.isSecret()) {
            result_.diagnostics.error(
                "E230", call.arguments[index]->location,
                "secret value cannot be passed to prompt '" + call.promptName +
                    "'; use 'declassify' with a written justification if this is intended");
        }
        if (!argument.tokenBoundKnown && call.arguments[index]->kind() == ExprKind::Identifier) {
            const auto& identifier = static_cast<const IdentifierExpr&>(*call.arguments[index]);
            if (result_.symbols.lookup(context.scope, identifier.name)) {
                result_.diagnostics.error(
                    "E261", call.arguments[index]->location,
                    "'" + identifier.name + "' is passed to a prompt but has no declared token bound; "
                    "add 'max_tokens <n>' to its declaration so the cost bound is defined");
                auto facts = result_.workflowFacts.find(context.workflow);
                if (facts != result_.workflowFacts.end()) {
                    facts->second.inputBoundMissing = true;
                }
            }
        }
        argumentJoin = join(argumentJoin, argument.label);
    }

    if (!prompt || prompt->kind != SymbolKind::Prompt || !prompt->prompt) {
        result_.diagnostics.error("E220", call.location,
                                  "unknown prompt '" + call.promptName + "' called from let statement");
    } else {
        const PromptSignature& signature = *prompt->prompt;
        if (call.arguments.size() != signature.parameters.size()) {
            std::ostringstream message;
            message << "prompt '" << call.promptName << "' expects " << signature.parameters.size()
                    << " argument(s), but " << call.arguments.size() << " were supplied";
            result_.diagnostics.error("E221", call.location, message.str());
        }
        const std::size_t checked = std::min(call.arguments.size(), signature.parameters.size());
        for (std::size_t index = 0; index < checked; ++index) {
            if (arguments[index].type.kind != TypeKind::Unknown &&
                arguments[index].type != signature.parameters[index].type) {
                result_.diagnostics.error(
                    "E223", call.arguments[index]->location,
                    "argument " + std::to_string(index + 1) + " of prompt '" + call.promptName +
                        "' has type " + typeName(arguments[index].type) + "; expected " +
                        typeName(signature.parameters[index].type));
            }
        }
    }

    CallSiteFacts site;
    site.promptName = call.promptName;
    site.modelName = call.modelName;
    if (prompt && prompt->prompt) {
        site.promptTemplateTokens = prompt->prompt->templateTokens;
    }
    for (const ValueFacts& argument : arguments) {
        if (argument.tokenBoundKnown) {
            site.argumentTokens = addTokens(site.argumentTokens, argument.tokenBound);
        } else {
            site.argumentBoundsKnown = false;
        }
    }

    ValueFacts facts;
    facts.type = (prompt && prompt->prompt) ? prompt->prompt->returnType : Type{TypeKind::Unknown};

    // Injection propagation: a model's answer is only as trustworthy as the
    // least trustworthy thing that reached its prompt.  This is what turns an
    // untrusted document into an untrusted answer, and keeps that answer out of
    // sinks unless the author endorses it explicitly.
    facts.label = argumentJoin;

    if (!model || model->kind != SymbolKind::Model || !model->model) {
        result_.diagnostics.error("E241", call.location,
                                  "unknown model '" + call.modelName + "' in using clause");
    } else {
        facts.tokenBoundKnown = true;
        facts.tokenBound = model->model->maxTokens;
        site.modelMaxTokens = model->model->maxTokens;
        site.hasUnitPrice = model->model->hasUnitPrice;
        site.unitPrice = model->model->unitPrice;
    }
    result_.callSites[&call] = site;
    return facts;
}

void Analyzer::analyzeLet(const LetStmt& let, const Context& context) {
    ValueFacts facts;
    if (let.call) {
        facts = inspectCall(*let.call, context);
    }
    if (facts.type.kind != TypeKind::Unknown && facts.type != let.type) {
        result_.diagnostics.error("E210", let.location,
                                  "cannot assign " + typeName(facts.type) + " result to '" + let.name +
                                      "' declared as " + typeName(let.type));
    }
    Symbol symbol{let.name,     SymbolKind::LocalResult, let.type, "", let.location, std::nullopt,
                  std::nullopt, std::nullopt,            facts.label};
    symbol.tokenBoundKnown = facts.tokenBoundKnown;
    symbol.tokenBound = facts.tokenBound;
    insertSymbol(context.scope, std::move(symbol));
}

void Analyzer::analyzeRequire(const RequireStmt& requirement, const Context& context) {
    const Symbol* subject = result_.symbols.lookup(context.scope, requirement.subjectName);
    if (!subject) {
        result_.diagnostics.error("E202", requirement.location,
                                  "use of undeclared identifier '" + requirement.subjectName + "'");
        return;
    }
    if (!subject->tokenBoundKnown) {
        result_.diagnostics.error(
            "E263", requirement.location,
            "'" + requirement.subjectName + "' (" + symbolKindName(subject->kind) +
                ") carries no token bound, so 'require tokens(...)' cannot be discharged");
        return;
    }

    // The requirement must hold for every value the subject can actually take,
    // which is any count in [0, bound].  Only an upper-bound comparison can be
    // discharged from an upper bound; the rest are reported as undecidable
    // rather than silently accepted.
    const std::size_t bound = subject->tokenBound;
    bool discharged = false;
    bool decidable = true;
    switch (requirement.op) {
        case ComparisonOp::LessEqual: discharged = bound <= requirement.limit; break;
        case ComparisonOp::Less: discharged = bound < requirement.limit; break;
        case ComparisonOp::GreaterEqual: discharged = requirement.limit == 0; break;
        case ComparisonOp::Greater:
        case ComparisonOp::Equal:
        case ComparisonOp::NotEqual: decidable = false; break;
    }
    if (!decidable) {
        result_.diagnostics.error(
            "E264", requirement.location,
            "'require tokens(" + requirement.subjectName + ") " + comparisonOpName(requirement.op) + " " +
                std::to_string(requirement.limit) +
                "' cannot be established from an upper bound; use '<' or '<='");
        return;
    }
    if (!discharged) {
        result_.diagnostics.error(
            "E262", requirement.location,
            "requirement 'tokens(" + requirement.subjectName + ") " + comparisonOpName(requirement.op) +
                " " + std::to_string(requirement.limit) + "' is not met: '" + requirement.subjectName +
                "' is bounded by " + std::to_string(bound) + " tokens");
    }
}

void Analyzer::analyzeEmit(const EmitStmt& emit, const Context& context) {
    const Symbol* tool = result_.symbols.lookup(context.scope, emit.toolName);

    std::vector<ValueFacts> arguments;
    arguments.reserve(emit.arguments.size());
    for (const auto& argument : emit.arguments) {
        arguments.push_back(argument ? inspect(*argument, context) : ValueFacts{});
    }

    if (!tool || tool->kind != SymbolKind::Tool || !tool->tool) {
        result_.diagnostics.error("E242", emit.location,
                                  "unknown tool '" + emit.toolName + "' in emit statement");
    } else {
        const ToolSignature& signature = *tool->tool;
        if (emit.arguments.size() != signature.parameters.size()) {
            std::ostringstream message;
            message << "tool '" << emit.toolName << "' expects " << signature.parameters.size()
                    << " argument(s), but " << emit.arguments.size() << " were supplied";
            result_.diagnostics.error("E243", emit.location, message.str());
        }
        const std::size_t checked = std::min(emit.arguments.size(), signature.parameters.size());
        for (std::size_t index = 0; index < checked; ++index) {
            if (arguments[index].type.kind != TypeKind::Unknown &&
                arguments[index].type != signature.parameters[index].type) {
                result_.diagnostics.error(
                    "E244", emit.arguments[index]->location,
                    "argument " + std::to_string(index + 1) + " of tool '" + emit.toolName + "' has type " +
                        typeName(arguments[index].type) + "; expected " +
                        typeName(signature.parameters[index].type));
            }
        }
    }

    // A tool is the workflow's only outward effect, so it is the strictest
    // sink: its arguments must be public and trusted, and the decision to fire
    // it must not itself depend on a secret.
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const SourceLocation& where = emit.arguments[index]->location;
        if (arguments[index].label.isSecret()) {
            result_.diagnostics.error("E232", where,
                                      "secret value reaches tool '" + emit.toolName +
                                          "'; declassify it explicitly if this is intended");
        }
        if (arguments[index].label.isUntrusted()) {
            result_.diagnostics.error(
                "E233", where,
                "untrusted value reaches tool '" + emit.toolName +
                    "'; model output derived from untrusted input must be endorsed before it can "
                    "drive an external effect");
        }
    }
    if (context.pc.isSecret()) {
        result_.diagnostics.error("E234", emit.location,
                                  "tool '" + emit.toolName +
                                      "' is invoked under a secret-dependent condition, which leaks "
                                      "the secret through whether the effect happens");
    }
    if (context.pc.isUntrusted()) {
        result_.diagnostics.error("E235", emit.location,
                                  "tool '" + emit.toolName +
                                      "' is invoked under a condition derived from untrusted data, "
                                      "so an injected value decides whether the effect happens");
    }
}

void Analyzer::analyzeIf(const IfStmt& branch, const Context& context) {
    Label guardLabel = publicTrusted();
    const Symbol* subject = result_.symbols.lookup(context.scope, branch.condition.subjectName);
    if (!subject) {
        result_.diagnostics.error("E202", branch.condition.location,
                                  "use of undeclared identifier '" + branch.condition.subjectName + "'");
    } else {
        guardLabel = subject->label;
        if (branch.condition.kind == ConditionKind::Flag && subject->type.kind != TypeKind::Boolean &&
            subject->type.kind != TypeKind::Unknown) {
            result_.diagnostics.error("E211", branch.condition.location,
                                      "condition '" + branch.condition.subjectName + "' has type " +
                                          typeName(subject->type) + "; expected boolean");
        }
        if (branch.condition.kind == ConditionKind::TokenBound && !subject->tokenBoundKnown) {
            result_.diagnostics.error("E263", branch.condition.location,
                                      "'" + branch.condition.subjectName +
                                          "' carries no token bound, so 'tokens(...)' cannot guard a branch");
        }
    }

    // Everything inside either arm is controlled by the guard, so the guard's
    // label joins the program counter for both.
    Context inner = context;
    inner.pc = join(context.pc, guardLabel);
    result_.guardLabels[&branch] = inner.pc;

    Context thenContext = inner;
    thenContext.scope = result_.symbols.createScope(
        "workflow:" + context.workflow + "::then@" + std::to_string(branch.location.line), context.scope);
    analyzeBlock(branch.thenBranch, thenContext);

    if (branch.hasElse) {
        Context elseContext = inner;
        elseContext.scope = result_.symbols.createScope(
            "workflow:" + context.workflow + "::else@" + std::to_string(branch.location.line),
            context.scope);
        analyzeBlock(branch.elseBranch, elseContext);
    }
}

void Analyzer::analyzeRetry(const RetryStmt& retry, const Context& context) {
    Context inner = context;
    inner.scope = result_.symbols.createScope(
        "workflow:" + context.workflow + "::retry@" + std::to_string(retry.location.line), context.scope);
    analyzeBlock(retry.body, inner);
}

void Analyzer::analyzeReclassify(const ReclassifyStmt& reclassify, const Context& context) {
    const Symbol* subject = result_.symbols.lookup(context.scope, reclassify.sourceName);
    if (!subject) {
        result_.diagnostics.error("E202", reclassify.location,
                                  "use of undeclared identifier '" + reclassify.sourceName + "'");
        return;
    }

    const Label from = subject->label;
    Label to = from;
    if (reclassify.endorsement) {
        to.integrity = Integrity::Trusted;
    } else {
        to.confidentiality = Confidentiality::Public;
    }

    if (to == from) {
        result_.diagnostics.warning(
            "W236", reclassify.location,
            std::string(reclassify.endorsement ? "endorsing" : "declassifying") + " '" +
                reclassify.sourceName + "' has no effect; it is already " + labelName(from));
    }
    if (subject->type.kind != TypeKind::Unknown && subject->type != reclassify.type) {
        result_.diagnostics.error("E212", reclassify.location,
                                  "cannot reclassify " + typeName(subject->type) + " value '" +
                                      reclassify.sourceName + "' as " + typeName(reclassify.type));
    }

    // Reclassification does not escape the program counter: relabelling inside
    // a secret-guarded branch still yields a secret-dependent value.
    to = join(to, reclassify.endorsement ? Label{to.confidentiality, context.pc.integrity}
                                         : Label{context.pc.confidentiality, to.integrity});

    Symbol symbol{reclassify.name, SymbolKind::Reclassified, reclassify.type, "",
                  reclassify.location, std::nullopt, std::nullopt, std::nullopt, to};
    symbol.tokenBoundKnown = subject->tokenBoundKnown;
    symbol.tokenBound = subject->tokenBound;
    insertSymbol(context.scope, std::move(symbol));

    result_.reclassifications.push_back({context.workflow, reclassify.sourceName, reclassify.name,
                                         reclassify.endorsement, from, to, reclassify.reason,
                                         reclassify.location});
}

void Analyzer::analyzeOutput(const OutputStmt& output, const Context& context) {
    ++outputCount_;
    if (!output.value) {
        return;
    }
    const ValueFacts facts = inspect(*output.value, context);
    const Label effective = join(facts.label, context.pc);
    if (effective.isSecret()) {
        result_.diagnostics.error("E231", output.value->location,
                                  "secret value cannot be exposed as workflow output");
    }
}

void Analyzer::analyzeStatement(const Stmt& statement, const Context& context) {
    switch (statement.kind()) {
        case StmtKind::Input:
            declareInput(static_cast<const InputDecl&>(statement), context);
            break;
        case StmtKind::Secret:
            declareSecret(static_cast<const SecretDecl&>(statement), context);
            break;
        case StmtKind::Model:
            declareModel(static_cast<const ModelDecl&>(statement), context);
            break;
        case StmtKind::Prompt:
            declarePrompt(static_cast<const PromptDecl&>(statement), context);
            break;
        case StmtKind::Tool:
            declareTool(static_cast<const ToolDecl&>(statement), context);
            break;
        case StmtKind::Let:
            analyzeLet(static_cast<const LetStmt&>(statement), context);
            break;
        case StmtKind::Require:
            analyzeRequire(static_cast<const RequireStmt&>(statement), context);
            break;
        case StmtKind::Emit:
            analyzeEmit(static_cast<const EmitStmt&>(statement), context);
            break;
        case StmtKind::If:
            analyzeIf(static_cast<const IfStmt&>(statement), context);
            break;
        case StmtKind::Retry:
            analyzeRetry(static_cast<const RetryStmt&>(statement), context);
            break;
        case StmtKind::Reclassify:
            analyzeReclassify(static_cast<const ReclassifyStmt&>(statement), context);
            break;
        case StmtKind::Output:
            analyzeOutput(static_cast<const OutputStmt&>(statement), context);
            break;
    }
}

void Analyzer::analyzeBlock(const Block& block, const Context& context) {
    for (const auto& statement : block) {
        if (statement) {
            analyzeStatement(*statement, context);
        }
    }
}

void Analyzer::analyzeWorkflow(const WorkflowDecl& workflow) {
    Context context;
    context.workflow = workflow.name;
    context.scope = result_.symbols.createScope("workflow:" + workflow.name);
    context.pc = publicTrusted();

    result_.workflowScopes[workflow.name] = context.scope;
    result_.workflowFacts[workflow.name] = {workflow.name, workflow.budget, context.scope, false};

    outputCount_ = 0;
    analyzeBlock(workflow.statements, context);

    if (outputCount_ == 0) {
        result_.diagnostics.error("E270", workflow.location,
                                  "workflow '" + workflow.name + "' has no output declaration");
    }
    if (outputCount_ > 1) {
        result_.diagnostics.error("E271", workflow.location,
                                  "workflow '" + workflow.name + "' has multiple output declarations");
    }
}

void Analyzer::run(const Program& program) {
    std::set<std::string> workflowNames;
    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        if (!workflowNames.insert(workflow.name).second) {
            result_.diagnostics.error("E201", workflow.location,
                                      "duplicate declaration of workflow '" + workflow.name + "'");
        }
        analyzeWorkflow(workflow);
    }
}

}  // namespace

SemanticResult SemanticAnalyzer::analyze(const Program& program) const {
    SemanticResult result;
    result.options = options_;
    Analyzer analyzer(result, options_);
    analyzer.run(program);
    return result;
}

}  // namespace orchlang
