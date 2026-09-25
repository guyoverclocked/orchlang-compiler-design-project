#include "semantic_analyzer.hpp"

#include "token_cost.hpp"
#include "tokenizer_contracts.hpp"

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
// and upper bounds on the tokens and bytes it occupies.
struct ValueFacts {
    Type type{TypeKind::Unknown};
    Label label{publicTrusted()};
    // The label without the program counter's confidentiality.
    Label dataLabel{publicTrusted()};
    bool tokenBoundKnown{false};
    std::size_t tokenBound{0};
    bool byteBoundKnown{false};
    std::size_t byteBound{0};
    int bindingId{0};
};

// Splits a template into literal text and the arguments substituted into it,
// in the order the provider will see them.  Malformed placeholders are
// reported by checkPlaceholders; here they are simply kept as text.
std::vector<TemplatePiece> templatePieces(const std::string& text,
                                          const std::vector<PromptParameterInfo>& parameters) {
    std::vector<TemplatePiece> pieces;
    std::string pending;
    std::size_t index = 0;
    while (index < text.size()) {
        std::size_t matched = parameters.size();
        std::size_t closing = std::string::npos;
        if (text[index] == '{') {
            closing = text.find('}', index + 1);
            if (closing != std::string::npos) {
                const std::string name = text.substr(index + 1, closing - index - 1);
                for (std::size_t parameter = 0; parameter < parameters.size(); ++parameter) {
                    if (parameters[parameter].name == name) {
                        matched = parameter;
                        break;
                    }
                }
            }
        }
        if (matched == parameters.size()) {
            pending.push_back(text[index]);
            ++index;
            continue;
        }
        if (!pending.empty()) {
            pieces.push_back({false, pending, 0});
            pending.clear();
        }
        pieces.push_back({true, std::string(), matched});
        index = closing + 1;
    }
    if (!pending.empty()) {
        pieces.push_back({false, pending, 0});
    }
    return pieces;
}

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
    const Symbol* insertSymbol(std::size_t scope, Symbol symbol);
    void applyLengthFacts(Symbol& symbol, bool hasTokenBound, std::size_t tokenBound,
                          const std::string& tokenizer, bool hasByteBound, std::size_t byteBound,
                          const SourceLocation& location);
    int recordBinding(const Symbol* inserted, const CallExpr* producer, int aliasOf);

    SemanticResult& result_;
    AnalysisOptions options_;
    std::size_t outputCount_{0};
};

const Symbol* Analyzer::insertSymbol(std::size_t scope, Symbol symbol) {
    const Symbol* existing = nullptr;
    const Symbol candidate = symbol;
    if (result_.symbols.insert(scope, std::move(symbol), &existing)) {
        return result_.symbols.lookupLocal(scope, candidate.name);
    }
    if (existing) {
        result_.diagnostics.error("E201", candidate.location,
                                  "duplicate declaration '" + candidate.name + "'; first declared at " +
                                      formatLocation(existing->location));
    }
    return nullptr;
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
            facts.dataLabel = symbol->dataLabel;
            facts.tokenBoundKnown = symbol->tokenBoundKnown;
            facts.tokenBound = symbol->tokenBound;
            facts.byteBoundKnown = symbol->byteBoundKnown;
            facts.byteBound = symbol->byteBound;
            facts.bindingId = symbol->id;
            return facts;
        }
        // Every literal is measured through substitutedText, the one function
        // the runtime also uses, so the two can never drift apart.
        case ExprKind::StringLiteral:
        case ExprKind::IntegerLiteral:
        case ExprKind::DecimalLiteral:
        case ExprKind::BooleanLiteral: {
            ValueFacts facts;
            switch (expression.kind()) {
                case ExprKind::StringLiteral: facts.type = {TypeKind::Text}; break;
                case ExprKind::IntegerLiteral: facts.type = {TypeKind::Integer}; break;
                case ExprKind::DecimalLiteral: facts.type = {TypeKind::Decimal}; break;
                default: facts.type = {TypeKind::Boolean}; break;
            }
            const std::string text = substitutedText(expression);
            facts.tokenBoundKnown = true;
            facts.tokenBound = estimateTextTokens(text, options_.charsPerToken);
            facts.byteBoundKnown = true;
            facts.byteBound = text.size();
            return facts;
        }
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

// Length facts shared by input and secret declarations.  A token bound under a
// named, lossless tokenizer also yields a byte bound, because each of its
// tokens covers at most lambda bytes of the text.
void Analyzer::applyLengthFacts(Symbol& symbol, bool hasTokenBound, std::size_t tokenBound,
                                const std::string& tokenizer, bool hasByteBound,
                                std::size_t byteBound, const SourceLocation& location) {
    symbol.tokenBoundKnown = hasTokenBound;
    symbol.tokenBound = tokenBound;
    symbol.tokenizer = tokenizer;
    if (hasByteBound) {
        symbol.byteBoundKnown = true;
        symbol.byteBound = byteBound;
        if (!hasTokenBound) {
            // The estimate half of the bound still needs a token figure: the
            // same bytes-per-token division estimateTextTokens applies.
            const std::size_t divisor = options_.charsPerToken == 0 ? 1 : options_.charsPerToken;
            symbol.tokenBoundKnown = true;
            symbol.tokenBound = byteBound / divisor + (byteBound % divisor != 0 ? 1 : 0);
        }
    }
    if (tokenizer.empty()) {
        return;
    }
    const TokenizerContract* contract = findTokenizerContract(tokenizer);
    if (!contract) {
        result_.diagnostics.error("E267", location,
                                  "unknown tokenizer '" + tokenizer + "'; known tokenizers are " +
                                      knownTokenizerNames());
        return;
    }
    if (!hasTokenBound) {
        result_.diagnostics.error("E267", location,
                                  "'tokenizer " + tokenizer + "' names the unit of a 'max_tokens' "
                                  "bound, but this declaration has none");
        return;
    }
    if (contract->lossless && !symbol.byteBoundKnown) {
        symbol.byteBoundKnown = true;
        symbol.byteBound = multiplyTokens(tokenBound, contract->lambda);
    }
}

int Analyzer::recordBinding(const Symbol* inserted, const CallExpr* producer, int aliasOf) {
    if (!inserted) {
        return 0;
    }
    BindingFact fact;
    fact.name = inserted->name;
    fact.kind = inserted->kind;
    fact.label = inserted->label;
    fact.dataLabel = inserted->dataLabel;
    fact.producer = producer;
    fact.aliasOf = aliasOf;
    fact.location = inserted->location;
    result_.bindings[inserted->id] = fact;
    return inserted->id;
}

void Analyzer::declareInput(const InputDecl& input, const Context& context) {
    Symbol symbol{input.name,   SymbolKind::Input, input.type, "", input.location, std::nullopt,
                  std::nullopt, std::nullopt,      input.label};
    symbol.dataLabel = input.label;
    applyLengthFacts(symbol, input.hasTokenBound, input.tokenBound, input.tokenizer,
                     input.hasByteBound, input.byteBound, input.location);
    recordBinding(insertSymbol(context.scope, std::move(symbol)), nullptr, 0);
}

void Analyzer::declareSecret(const SecretDecl& secret, const Context& context) {
    Symbol symbol{secret.name,  SymbolKind::Secret, secret.type,
                  "",           secret.location,    std::nullopt,
                  std::nullopt, std::nullopt,       Label{Confidentiality::Secret, Integrity::Trusted}};
    symbol.dataLabel = symbol.label;
    applyLengthFacts(symbol, secret.hasTokenBound, secret.tokenBound, secret.tokenizer,
                     secret.hasByteBound, secret.byteBound, secret.location);
    recordBinding(insertSymbol(context.scope, std::move(symbol)), nullptr, 0);
}

void Analyzer::declareModel(const ModelDecl& model, const Context& context) {
    ModelMetadata metadata{model.provider, model.modelName, model.maxTokens, model.hasUnitPrice,
                           model.unitPrice, model.tokenizer, model.overhead, model.hasByteCap,
                           model.byteCap};
    if (!model.tokenizer.empty()) {
        const TokenizerContract* contract = findTokenizerContract(model.tokenizer);
        if (!contract) {
            result_.diagnostics.error("E267", model.location,
                                      "unknown tokenizer '" + model.tokenizer +
                                          "'; known tokenizers are " + knownTokenizerNames());
        } else if (!contract->verified) {
            result_.diagnostics.warning(
                "W267", model.location,
                "tokenizer '" + model.tokenizer + "' (" + contract->family +
                    ") has no verified byte contract, so the input bound for calls to model '" +
                    model.name + "' is an estimate, not a guarantee");
        }
    }
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
    signature.templateText = prompt.templateText;

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
    //
    // "Secret" here means the argument's *content* depends on a secret.  A
    // value computed inside a secret-guarded arm from public arguments has
    // public content; only its existence depends on the secret, and existence
    // is exactly what the relational obligation on the enclosing branch
    // already accounts for.  Rejecting it here, as this compiler once did, is
    // sound but blocks every chained call inside a secret arm (OP-1).
    Label argumentJoin = context.pc;
    Label dataJoin{Confidentiality::Public, context.pc.integrity};
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const ValueFacts& argument = arguments[index];
        if (argument.dataLabel.isSecret()) {
            result_.diagnostics.error(
                "E230", call.arguments[index]->location,
                "secret value cannot be passed to prompt '" + call.promptName +
                    "'; use 'declassify' with a written justification if this is intended");
        }
        dataJoin = join(dataJoin, argument.dataLabel);
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
        site.pieces = templatePieces(prompt->prompt->templateText, prompt->prompt->parameters);
        for (const TemplatePiece& piece : site.pieces) {
            if (!piece.isArgument) {
                site.templateBytes += piece.text.size();
            }
        }
    }
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const ValueFacts& argument = arguments[index];
        if (argument.tokenBoundKnown) {
            site.argumentTokens = addTokens(site.argumentTokens, argument.tokenBound);
        } else {
            site.argumentBoundsKnown = false;
        }

        ArgumentFact fact;
        fact.isSecret = argument.dataLabel.isSecret();
        fact.isPcSecret = argument.label.isSecret();
        fact.byteBoundKnown = argument.byteBoundKnown;
        fact.byteBound = argument.byteBound;
        fact.bindingId = argument.bindingId;
        if (index < call.arguments.size() && call.arguments[index]) {
            const Expr& expression = *call.arguments[index];
            if (expression.kind() == ExprKind::Identifier) {
                fact.name = static_cast<const IdentifierExpr&>(expression).name;
            } else {
                fact.isLiteral = true;
                fact.literalText = substitutedText(expression);
                fact.literalTokens = estimateTextTokens(fact.literalText, options_.charsPerToken);
            }
        }
        site.arguments.push_back(std::move(fact));
    }

    ValueFacts facts;
    facts.type = (prompt && prompt->prompt) ? prompt->prompt->returnType : Type{TypeKind::Unknown};

    // Injection propagation: a model's answer is only as trustworthy as the
    // least trustworthy thing that reached its prompt.  This is what turns an
    // untrusted document into an untrusted answer, and keeps that answer out of
    // sinks unless the author endorses it explicitly.
    facts.label = argumentJoin;
    facts.dataLabel = dataJoin;

    if (!model || model->kind != SymbolKind::Model || !model->model) {
        result_.diagnostics.error("E241", call.location,
                                  "unknown model '" + call.modelName + "' in using clause");
    } else {
        const ModelMetadata& metadata = *model->model;
        facts.tokenBoundKnown = true;
        facts.tokenBound = metadata.maxTokens;
        site.modelMaxTokens = metadata.maxTokens;
        site.modelIdentity = metadata.identity();
        site.modelString = metadata.modelName;
        site.modelProvider = metadata.modelName.substr(0, metadata.modelName.find('/'));
        site.hasUnitPrice = metadata.hasUnitPrice;
        site.unitPrice = metadata.unitPrice;
        site.tokenizer = metadata.tokenizer;
        site.overhead = metadata.overhead;
        site.hasByteCap = metadata.hasByteCap;
        site.byteCap = metadata.byteCap;

        // How long the response can be in bytes, which is what a later prompt
        // is billed on.  A token cap bounds it only through the most bytes one
        // token can decode to; a client-side byte cap bounds it directly.
        const TokenizerContract* contract =
            metadata.tokenizer.empty() ? nullptr : findTokenizerContract(metadata.tokenizer);
        if (contract) {
            facts.byteBoundKnown = true;
            facts.byteBound = multiplyTokens(metadata.maxTokens, contract->lambda);
        }
        if (metadata.hasByteCap &&
            (!facts.byteBoundKnown || metadata.byteCap < facts.byteBound)) {
            facts.byteBoundKnown = true;
            facts.byteBound = metadata.byteCap;
        }
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
    symbol.dataLabel = facts.dataLabel;
    symbol.tokenBoundKnown = facts.tokenBoundKnown;
    symbol.tokenBound = facts.tokenBound;
    symbol.byteBoundKnown = facts.byteBoundKnown;
    symbol.byteBound = facts.byteBound;
    const int id = recordBinding(insertSymbol(context.scope, std::move(symbol)), let.call.get(), 0);
    if (id != 0) {
        result_.introduced[&let] = id;
    }
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
    result_.guardOwnLabels[&branch] = guardLabel;

    // What the relational analysis needs: does the guard's outcome depend on
    // a secret's content, and if so which secret's.  A guard on a value that
    // was merely computed under a secret program counter has public content,
    // so both compared executions evaluate it alike.
    GuardFact guard;
    if (subject) {
        guard.subjectId = subject->id;
        guard.secretData = subject->dataLabel.isSecret();
        if (guard.secretData) {
            int root = subject->id;
            for (int hops = 0; hops < 64; ++hops) {
                const auto found = result_.bindings.find(root);
                if (found == result_.bindings.end() || found->second.aliasOf == 0) {
                    break;
                }
                root = found->second.aliasOf;
            }
            guard.secretRootId = root;
            guard.secretBoundKnown = subject->tokenBoundKnown;
            guard.secretBound = subject->tokenBound;
        }
    }
    result_.guards[&branch] = guard;

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

    // The copied value's content is the source's content, relabelled on one
    // axis.  Declassification is the one place secret content may become
    // public, and it is trusted: the compiler records it, it does not check it.
    Label data = subject->dataLabel;
    if (reclassify.endorsement) {
        data.integrity = Integrity::Trusted;
    } else {
        data.confidentiality = Confidentiality::Public;
    }

    // Reclassification does not escape the program counter: relabelling inside
    // a secret-guarded branch still yields a secret-dependent value.
    to = join(to, reclassify.endorsement ? Label{to.confidentiality, context.pc.integrity}
                                         : Label{context.pc.confidentiality, to.integrity});
    data.integrity = to.integrity;

    Symbol symbol{reclassify.name, SymbolKind::Reclassified, reclassify.type, "",
                  reclassify.location, std::nullopt, std::nullopt, std::nullopt, to};
    symbol.dataLabel = data;
    symbol.tokenBoundKnown = subject->tokenBoundKnown;
    symbol.tokenBound = subject->tokenBound;
    symbol.tokenizer = subject->tokenizer;
    symbol.byteBoundKnown = subject->byteBoundKnown;
    symbol.byteBound = subject->byteBound;
    const int id = recordBinding(insertSymbol(context.scope, std::move(symbol)), nullptr, subject->id);
    if (id != 0) {
        result_.introduced[&reclassify] = id;
    }

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
