#include "interpreter.hpp"

#include "cost_analyzer.hpp"
#include "relational.hpp"
#include "token_cost.hpp"

#include <cmath>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

namespace {

struct PinTarget {
    Type type;
    bool hasTokenBound{false};
    std::size_t tokenBound{0};
};

void collectPinTargets(const Block& statements,
                       std::map<std::string, std::vector<PinTarget>>& targets) {
    for (const auto& statement : statements) {
        if (!statement) {
            continue;
        }
        switch (statement->kind()) {
            case StmtKind::Input: {
                const auto& input = static_cast<const InputDecl&>(*statement);
                targets[input.name].push_back({input.type, input.hasTokenBound, input.tokenBound});
                break;
            }
            case StmtKind::Secret: {
                const auto& secret = static_cast<const SecretDecl&>(*statement);
                targets[secret.name].push_back({secret.type, secret.hasTokenBound,
                                                secret.tokenBound});
                break;
            }
            case StmtKind::If: {
                const auto& branch = static_cast<const IfStmt&>(*statement);
                collectPinTargets(branch.thenBranch, targets);
                collectPinTargets(branch.elseBranch, targets);
                break;
            }
            case StmtKind::Retry:
                collectPinTargets(static_cast<const RetryStmt&>(*statement).body, targets);
                break;
            default:
                break;
        }
    }
}

bool validateRunPins(const Program& program, const RunOptions& options, DiagnosticBag& diagnostics) {
    std::map<std::string, std::vector<PinTarget>> targets;
    for (const auto& workflow : program.workflows) {
        if (workflow) {
            collectPinTargets(workflow->statements, targets);
        }
    }

    bool valid = true;
    for (const auto& pin : options.pinnedLengths) {
        const auto found = targets.find(pin.first);
        if (found == targets.end()) {
            diagnostics.error("R002", {}, "length pin '" + pin.first +
                                               "' does not name a declared input or secret");
            valid = false;
            continue;
        }
        bool textOnly = true;
        for (const PinTarget& target : found->second) {
            if (target.type.kind != TypeKind::Text) {
                textOnly = false;
            }
        }
        if (!textOnly) {
            diagnostics.error("R002", {}, "length pin '" + pin.first +
                                               "' must name text inputs/secrets only");
            valid = false;
            continue;
        }
        for (const PinTarget& target : found->second) {
            if (target.hasTokenBound && pin.second > target.tokenBound) {
                diagnostics.error("R002", {}, "length pin '" + pin.first + "' is " +
                                                   std::to_string(pin.second) +
                                                   " tokens, exceeding a declared max_tokens bound of " +
                                                   std::to_string(target.tokenBound));
                valid = false;
                break;
            }
        }
    }

    for (const auto& pin : options.pinnedFlags) {
        const auto found = targets.find(pin.first);
        if (found == targets.end()) {
            diagnostics.error("R002", {}, "boolean pin '" + pin.first +
                                               "' does not name a declared input or secret");
            valid = false;
            continue;
        }
        bool booleanOnly = true;
        for (const PinTarget& target : found->second) {
            if (target.type.kind != TypeKind::Boolean) {
                booleanOnly = false;
            }
        }
        if (!booleanOnly) {
            diagnostics.error("R002", {}, "boolean pin '" + pin.first +
                                               "' must name boolean inputs/secrets only");
            valid = false;
        }
    }
    return valid;
}

// splitmix64: deterministic and reproducible. Inputs, model responses, and
// retry outcomes use independent keys, so a secret-selected path cannot shift
// the random draws assigned to later model calls.
class Random {
public:
    explicit Random(std::uint64_t seed) : state_(seed) {}

    std::uint64_t next() {
        state_ += 0x9E3779B97F4A7C15ULL;
        std::uint64_t value = state_;
        value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9ULL;
        value = (value ^ (value >> 27)) * 0x94D049BB133111EBULL;
        return value ^ (value >> 31);
    }

    std::size_t between(std::size_t low, std::size_t high) {
        if (high <= low) {
            return low;
        }
        const std::size_t range = high - low + 1;
        if (range == 0) {
            return low + static_cast<std::size_t>(next());
        }
        return low + static_cast<std::size_t>(next() % range);
    }

    unsigned percent() { return static_cast<unsigned>(next() % 100); }

private:
    std::uint64_t state_;
};

std::uint64_t mix(std::uint64_t value) {
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9ULL;
    value = (value ^ (value >> 27)) * 0x94D049BB133111EBULL;
    return value ^ (value >> 31);
}

std::uint64_t hashText(const std::string& text) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const unsigned char byte : text) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }
    return hash;
}

void appendSizedField(std::string& destination, char tag, const std::string& value) {
    destination.push_back(tag);
    destination += std::to_string(value.size());
    destination.push_back(':');
    destination += value;
}

std::uint64_t eventSeed(std::uint64_t seed, const std::string& workflow,
                        const std::string& domain, const std::string& identity,
                        std::uint64_t event, std::uint64_t attempt = 0) {
    std::uint64_t value = mix(seed ^ hashText(workflow));
    value = mix(value ^ hashText(domain));
    value = mix(value ^ hashText(identity));
    value = mix(value ^ event);
    return mix(value ^ attempt);
}

std::string jsonQuoted(const std::string& text) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char character : text) {
        switch (character) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (character < 0x20) {
                    const char hex[] = "0123456789abcdef";
                    out << "\\u00" << hex[(character >> 4) & 0xf] << hex[character & 0xf];
                } else {
                    out << static_cast<char>(character);
                }
                break;
        }
    }
    out << '"';
    return out.str();
}

std::string jsonModelContract(const ModelContract& contract) {
    std::ostringstream out;
    out << "{\"provider\":" << jsonQuoted(contract.provider)
        << ",\"model_id\":" << jsonQuoted(contract.modelName)
        << ",\"max_tokens\":" << contract.maxTokens
        << ",\"has_unit_price\":" << (contract.hasUnitPrice ? "true" : "false")
        << ",\"unit_price\":";
    if (contract.hasUnitPrice && std::isfinite(contract.unitPrice)) {
        out << std::setprecision(std::numeric_limits<double>::max_digits10) << contract.unitPrice;
    } else {
        out << "null";
    }
    out << ",\"stable_key\":" << jsonQuoted(contract.stableKey()) << '}';
    return out.str();
}

// A runtime value is abstracted to the dimensions the mock runtime observes:
// token count and a deterministic boolean used by flag conditions.
struct Value {
    std::size_t tokens{0};
    bool flag{false};
};

template <typename T>
class Environment {
public:
    void push() { frames_.emplace_back(); }
    void pop() { frames_.pop_back(); }

    void define(const std::string& name, T entry) {
        if (!frames_.empty()) {
            frames_.back()[name] = std::move(entry);
        }
    }

    const T* find(const std::string& name) const {
        for (auto frame = frames_.rbegin(); frame != frames_.rend(); ++frame) {
            const auto found = frame->find(name);
            if (found != frame->end()) {
                return &found->second;
            }
        }
        return nullptr;
    }

private:
    std::vector<std::map<std::string, T>> frames_;
};

class Machine {
public:
    Machine(const SemanticResult& semantic, const RunOptions& options, WorkflowRun& run,
            std::uint64_t seed, std::string workflow)
        : semantic_(semantic), options_(options), run_(run), seed_(seed),
          workflow_(std::move(workflow)) {}

    void block(const Block& statements);
    void enter() { values_.push(); }
    void leave() { values_.pop(); }

private:
    void statement(const Stmt& node);
    const Value* value(const std::string& name) const { return values_.find(name); }
    std::string requestContentKey(const CallExpr& call, const CallSiteFacts& site) const;

    std::size_t pinnedLength(const std::string& name, std::size_t sampled) const {
        const auto found = options_.pinnedLengths.find(name);
        return found == options_.pinnedLengths.end() ? sampled : found->second;
    }
    bool pinnedFlag(const std::string& name, bool sampled) const {
        const auto found = options_.pinnedFlags.find(name);
        return found == options_.pinnedFlags.end() ? sampled : found->second;
    }
    std::size_t bindingIdentity(const Stmt& declaration) const {
        const auto found = semantic_.declarationBindings.find(&declaration);
        return found == semantic_.declarationBindings.end() ? 0 : found->second;
    }
    const CallSiteFacts* callFacts(const CallExpr& call) const {
        const auto found = semantic_.callSites.find(&call);
        return found == semantic_.callSites.end() ? nullptr : &found->second;
    }

    const SemanticResult& semantic_;
    const RunOptions& options_;
    WorkflowRun& run_;
    std::uint64_t seed_{0};
    std::string workflow_;
    Environment<Value> values_;
    std::map<std::string, std::size_t> modelCallIndices_;
    std::size_t retryEventIndex_{0};
};

std::string Machine::requestContentKey(const CallExpr& call, const CallSiteFacts& site) const {
    std::string key;
    appendSizedField(key, 'T', site.promptTemplateText);
    for (const auto& argument : call.arguments) {
        if (!argument) {
            appendSizedField(key, 'X', {});
            continue;
        }
        if (argument->kind() == ExprKind::Identifier) {
            const auto& identifier = static_cast<const IdentifierExpr&>(*argument);
            const Value* runtimeValue = value(identifier.name);
            if (!runtimeValue) {
                appendSizedField(key, 'X', {});
                continue;
            }
            appendSizedField(key, 'V', std::to_string(runtimeValue->tokens));
            appendSizedField(key, 'F', runtimeValue->flag ? "1" : "0");
        } else {
            const char kind = static_cast<char>('0' + static_cast<int>(argument->kind()));
            appendSizedField(key, 'K', std::string(1, kind));
            appendSizedField(key, 'L', substitutedText(*argument));
        }
    }
    return key;
}

struct ScopedBlock {
    explicit ScopedBlock(Machine& machine) : machine_(machine) { machine_.enter(); }
    ~ScopedBlock() { machine_.leave(); }
    Machine& machine_;
};

void Machine::statement(const Stmt& node) {
    switch (node.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(node);
            Random random(eventSeed(seed_, workflow_, "input", "value",
                                    bindingIdentity(node)));
            const std::size_t bound = input.hasTokenBound ? input.tokenBound : 0;
            const std::size_t sampled = random.between(0, bound);
            const bool sampledFlag = random.percent() < 50;
            values_.define(input.name, {pinnedLength(input.name, sampled),
                                        pinnedFlag(input.name, sampledFlag)});
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(node);
            Random random(eventSeed(seed_, workflow_, "secret", "value",
                                    bindingIdentity(node)));
            const std::size_t bound = secret.hasTokenBound ? secret.tokenBound : 0;
            const bool sampledFlag = random.percent() < 50;
            values_.define(secret.name, {pinnedLength(secret.name, bound),
                                         pinnedFlag(secret.name, sampledFlag)});
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(node);
            if (!let.call) {
                break;
            }
            const CallSiteFacts* site = callFacts(*let.call);
            if (!site || !site->resolvedModel) {
                break;
            }

            std::size_t inputTokens = site->promptTemplateTokens;
            for (const auto& argument : let.call->arguments) {
                if (!argument) {
                    continue;
                }
                if (argument->kind() == ExprKind::Identifier) {
                    const auto& identifier = static_cast<const IdentifierExpr&>(*argument);
                    if (const Value* bound = value(identifier.name)) {
                        inputTokens = addTokens(inputTokens, bound->tokens);
                    }
                } else {
                    inputTokens = addTokens(
                        inputTokens,
                        estimateTextTokens(substitutedText(*argument), semantic_.options.charsPerToken));
                }
            }

            // The shared oracle is keyed by the resolved contract and its
            // per-contract call index. Source aliases and unrelated control
            // flow do not shift the outcome assigned to this call.
            const std::string modelKey = site->resolvedModel->stableKey();
            const std::size_t modelCallIndex = modelCallIndices_[modelKey]++;
            std::size_t outputTokens = 0;
            if (options_.requestSensitiveOracle) {
                std::string oracleKey;
                appendSizedField(oracleKey, 'M', modelKey);
                appendSizedField(oracleKey, 'K', std::to_string(modelCallIndex));
                appendSizedField(oracleKey, 'Q', requestContentKey(*let.call, *site));
                // Keep the experimental oracle a function of (seed, M, k, Q),
                // independent of source aliases, binding names, and workflow
                // spelling. The ordinal-only oracle remains the default.
                Random modelRandom(eventSeed(seed_, {}, "request-model-output", oracleKey, 0));
                outputTokens = modelRandom.between(0, site->resolvedModel->maxTokens);
            } else {
                Random modelRandom(eventSeed(seed_, workflow_, "model-output", modelKey,
                                             modelCallIndex));
                outputTokens = modelRandom.between(0, site->resolvedModel->maxTokens);
            }

            run_.inputTokens = addTokens(run_.inputTokens, inputTokens);
            run_.outputTokens = addTokens(run_.outputTokens, outputTokens);
            ++run_.calls;
            run_.trace.push_back({let.name, let.call->promptName, site->modelAlias, modelKey,
                                  *site->resolvedModel, inputTokens, outputTokens});
            ModelBilling& billing = run_.billing[modelKey];
            billing.contract = *site->resolvedModel;
            billing.inputTokens = addTokens(billing.inputTokens, inputTokens);
            billing.outputTokens = addTokens(billing.outputTokens, outputTokens);
            ++billing.calls;

            values_.define(let.name, {outputTokens, outputTokens % 2 == 0});
            break;
        }
        case StmtKind::If: {
            const auto& branch = static_cast<const IfStmt&>(node);
            const Value* subject = value(branch.condition.subjectName);
            bool taken = false;
            if (subject) {
                if (branch.condition.kind == ConditionKind::Flag) {
                    taken = subject->flag;
                } else {
                    const std::size_t actual = subject->tokens;
                    switch (branch.condition.op) {
                        case ComparisonOp::Less: taken = actual < branch.condition.limit; break;
                        case ComparisonOp::LessEqual: taken = actual <= branch.condition.limit; break;
                        case ComparisonOp::Greater: taken = actual > branch.condition.limit; break;
                        case ComparisonOp::GreaterEqual: taken = actual >= branch.condition.limit; break;
                        case ComparisonOp::Equal: taken = actual == branch.condition.limit; break;
                        case ComparisonOp::NotEqual: taken = actual != branch.condition.limit; break;
                    }
                }
            }
            run_.branches.push_back({node.location, taken});
            if (taken) {
                ScopedBlock frame(*this);
                block(branch.thenBranch);
            } else if (branch.hasElse) {
                ScopedBlock frame(*this);
                block(branch.elseBranch);
            }
            break;
        }
        case StmtKind::Retry: {
            const auto& retry = static_cast<const RetryStmt&>(node);
            const std::size_t retryEvent = retryEventIndex_++;
            const std::size_t traceIndex = run_.retries.size();
            run_.retries.push_back({node.location, 0});
            for (std::size_t attempt = 0; attempt < retry.bound; ++attempt) {
                {
                    ScopedBlock frame(*this);
                    block(retry.body);
                }
                ++run_.retryAttempts;
                ++run_.retries[traceIndex].attempts;
                Random retryRandom(eventSeed(seed_, workflow_, "retry-outcome", "schedule",
                                             retryEvent, attempt));
                if (retryRandom.percent() >= options_.retryFailurePercent) {
                    break;
                }
            }
            break;
        }
        case StmtKind::Reclassify: {
            const auto& reclassify = static_cast<const ReclassifyStmt&>(node);
            if (const Value* source = value(reclassify.sourceName)) {
                values_.define(reclassify.name, *source);
            }
            break;
        }
        case StmtKind::Emit: {
            const auto& emit = static_cast<const EmitStmt&>(node);
            run_.effects.push_back(emit.toolName);
            break;
        }
        case StmtKind::Model:
        case StmtKind::Prompt:
        case StmtKind::Tool:
        case StmtKind::Require:
        case StmtKind::Output:
            break;
    }
}

void Machine::block(const Block& statements) {
    for (const auto& node : statements) {
        if (node) {
            statement(*node);
        }
    }
}

}  // namespace

RunResult Interpreter::run(const Program& program, const SemanticResult& semantic) const {
    RunResult result;
    if (!semantic.success()) {
        result.diagnostics.error("R001", {}, "running requires a well-typed program");
        return result;
    }
    if (!validateRunPins(program, options_, result.diagnostics)) {
        return result;
    }

    if (!options_.auditUnsafe) {
        CostAnalyzer costAnalyzer;
        CostResult cost = costAnalyzer.analyze(program, semantic);
        RelationalAnalyzer relationalAnalyzer;
        RelationalResult relational = relationalAnalyzer.analyze(program, semantic);
        result.diagnostics.append(cost.diagnostics);
        result.diagnostics.append(relational.diagnostics);
        if (result.diagnostics.hasErrors()) {
            return result;
        }
    }

    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        WorkflowRun run;
        run.name = workflow.name;

        Machine machine(semantic, options_, run, options_.seed, workflow.name);
        machine.enter();
        machine.block(workflow.statements);
        machine.leave();
        result.workflows.push_back(std::move(run));
    }
    return result;
}

bool sameBilling(const WorkflowRun& left, const WorkflowRun& right) {
    return left.billing == right.billing;
}

std::string printRun(const RunResult& result) {
    std::ostringstream out;
    for (const WorkflowRun& run : result.workflows) {
        out << run.name << ":\n";
        out << "  calls          " << run.calls << '\n';
        out << "  actual tokens  " << run.totalTokens() << "  (input " << run.inputTokens
            << " + output " << run.outputTokens << ")\n";
        for (const CallTrace& call : run.trace) {
            out << "    " << call.binding << " = " << call.prompt << " via " << call.modelAlias
                << " [model-contract=" << call.modelContractKey << "]  in " << call.inputTokens
                << " out " << call.outputTokens << '\n';
        }
        for (const BranchTrace& branch : run.branches) {
            out << "  branch @" << branch.location.line << ':' << branch.location.column << ' '
                << (branch.tookThen ? "then" : "else") << '\n';
        }
        out << "  retry attempts " << run.retryAttempts << '\n';
        for (const RetryTrace& retry : run.retries) {
            out << "    retry @" << retry.location.line << ':' << retry.location.column
                << " attempts " << retry.attempts << '\n';
        }
        if (!run.billing.empty()) {
            out << "  billing\n";
            for (const auto& entry : run.billing) {
                out << "    model-contract=" << entry.first << "  calls " << entry.second.calls
                    << "  in " << entry.second.inputTokens << "  out "
                    << entry.second.outputTokens << '\n';
            }
        }
        if (!run.effects.empty()) {
            out << "  effects        ";
            for (std::size_t index = 0; index < run.effects.size(); ++index) {
                if (index != 0) {
                    out << ", ";
                }
                out << run.effects[index];
            }
            out << '\n';
        }
    }
    return out.str();
}

std::string printRunJson(const RunResult& result) {
    std::ostringstream out;
    out << "{\"workflows\":[";
    for (std::size_t workflowIndex = 0; workflowIndex < result.workflows.size(); ++workflowIndex) {
        const WorkflowRun& run = result.workflows[workflowIndex];
        if (workflowIndex != 0) {
            out << ',';
        }
        out << "{\"name\":" << jsonQuoted(run.name)
            << ",\"input_tokens\":" << run.inputTokens
            << ",\"output_tokens\":" << run.outputTokens
            << ",\"total_tokens\":" << run.totalTokens()
            << ",\"calls\":" << run.calls
            << ",\"retry_attempts\":" << run.retryAttempts
            << ",\"branches\":[";
        for (std::size_t index = 0; index < run.branches.size(); ++index) {
            if (index != 0) {
                out << ',';
            }
            const BranchTrace& trace = run.branches[index];
            out << "{\"file\":" << jsonQuoted(trace.location.file)
                << ",\"line\":" << trace.location.line
                << ",\"column\":" << trace.location.column
                << ",\"decision\":" << jsonQuoted(trace.tookThen ? "then" : "else") << '}';
        }
        out << "],\"retries\":[";
        for (std::size_t index = 0; index < run.retries.size(); ++index) {
            if (index != 0) {
                out << ',';
            }
            const RetryTrace& trace = run.retries[index];
            out << "{\"file\":" << jsonQuoted(trace.location.file)
                << ",\"line\":" << trace.location.line
                << ",\"column\":" << trace.location.column
                << ",\"attempts\":" << trace.attempts << '}';
        }
        out << "],\"trace\":[";
        for (std::size_t index = 0; index < run.trace.size(); ++index) {
            if (index != 0) {
                out << ',';
            }
            const CallTrace& trace = run.trace[index];
            out << "{\"binding\":" << jsonQuoted(trace.binding)
                << ",\"prompt\":" << jsonQuoted(trace.prompt)
                << ",\"model_alias\":" << jsonQuoted(trace.modelAlias)
                << ",\"model_contract\":" << jsonQuoted(trace.modelContractKey)
                << ",\"model_contract_details\":" << jsonModelContract(trace.modelContract)
                << ",\"input_tokens\":" << trace.inputTokens
                << ",\"output_tokens\":" << trace.outputTokens << '}';
        }
        out << "],\"billing\":[";
        std::size_t billingIndex = 0;
        for (const auto& entry : run.billing) {
            if (billingIndex++ != 0) {
                out << ',';
            }
            out << "{\"model_contract\":" << jsonQuoted(entry.first)
                << ",\"model_contract_details\":" << jsonModelContract(entry.second.contract)
                << ",\"calls\":" << entry.second.calls
                << ",\"input_tokens\":" << entry.second.inputTokens
                << ",\"output_tokens\":" << entry.second.outputTokens << '}';
        }
        out << "],\"effects\":[";
        for (std::size_t index = 0; index < run.effects.size(); ++index) {
            if (index != 0) {
                out << ',';
            }
            out << jsonQuoted(run.effects[index]);
        }
        out << "]}";
    }
    out << "]}\n";
    return out.str();
}

}  // namespace orchlang
