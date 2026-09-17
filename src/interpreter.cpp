#include "interpreter.hpp"

#include "token_cost.hpp"

#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

namespace {

// splitmix64: a small, well-behaved, fully reproducible generator.  The point
// is determinism, not statistical quality: the same seed must always replay the
// same execution so a reported violation can be reproduced exactly.
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

    // Uniform in [low, high].
    std::size_t between(std::size_t low, std::size_t high) {
        if (high <= low) {
            return low;
        }
        return low + static_cast<std::size_t>(next() % (high - low + 1));
    }

    unsigned percent() { return static_cast<unsigned>(next() % 100); }

private:
    std::uint64_t state_;
};

// A runtime value is just its token count; the mock never needs the text
// itself, and counting tokens is the whole measurement.
struct Value {
    std::size_t tokens{0};
    bool flag{false};
};

struct ModelInfo {
    std::size_t maxTokens{0};
};

struct PromptInfo {
    std::size_t templateTokens{0};
};

// A stack of frames mirroring the source's block structure.
//
// The static analysis gives every block its own scope, so the runtime must too.
// Until audit finding 4, this was a set of flat maps: a model declared inside a
// branch stayed visible after the branch ended, and a later call was charged
// against one model while executing another.  Every binding kind is scoped here,
// not just values, because that finding was about a shadowed *model*.
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
    Machine(const SemanticResult& semantic, const RunOptions& options, Random& random,
            WorkflowRun& run)
        : semantic_(semantic), options_(options), random_(random), run_(run) {}

    void block(const Block& statements);
    void enter() {
        values_.push();
        models_.push();
        prompts_.push();
    }
    void leave() {
        values_.pop();
        models_.pop();
        prompts_.pop();
    }

private:
    void statement(const Stmt& node);
    const Value* value(const std::string& name) const { return values_.find(name); }

    std::size_t pinnedLength(const std::string& name, std::size_t sampled) const {
        const auto found = options_.pinnedLengths.find(name);
        return found == options_.pinnedLengths.end() ? sampled : found->second;
    }
    bool pinnedFlag(const std::string& name, bool sampled) const {
        const auto found = options_.pinnedFlags.find(name);
        return found == options_.pinnedFlags.end() ? sampled : found->second;
    }

    const SemanticResult& semantic_;
    const RunOptions& options_;
    Random& random_;
    WorkflowRun& run_;

    Environment<Value> values_;
    Environment<ModelInfo> models_;
    Environment<PromptInfo> prompts_;
};

// Runs a block in its own frame, so nothing declared inside escapes it.
struct ScopedBlock {
    explicit ScopedBlock(Machine& machine) : machine_(machine) { machine_.enter(); }
    ~ScopedBlock() { machine_.leave(); }
    Machine& machine_;
};

void Machine::statement(const Stmt& node) {
    switch (node.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(node);
            // An input honours its declared bound, which is the contract the
            // estimated half of the cost bound is stated against.
            const std::size_t bound = input.hasTokenBound ? input.tokenBound : 0;
            const std::size_t sampled = random_.between(0, bound);
            const bool sampledFlag = random_.percent() < 50;
            values_.define(input.name, {pinnedLength(input.name, sampled),
                                        pinnedFlag(input.name, sampledFlag)});
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(node);
            const std::size_t bound = secret.hasTokenBound ? secret.tokenBound : 0;
            const bool sampledFlag = random_.percent() < 50;
            values_.define(secret.name, {pinnedLength(secret.name, bound),
                                        pinnedFlag(secret.name, sampledFlag)});
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(node);
            models_.define(model.name, {model.maxTokens});
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(node);
            prompts_.define(prompt.name, {
                estimateTextTokens(prompt.templateText, semantic_.options.charsPerToken)});
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(node);
            if (!let.call) {
                break;
            }
            const ModelInfo* model = models_.find(let.call->modelName);
            const PromptInfo* prompt = prompts_.find(let.call->promptName);
            if (!model || !prompt) {
                break;
            }

            std::size_t inputTokens = prompt->templateTokens;
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

            // The provider never returns more than max_tokens.  That cap is
            // the reason the guaranteed half of the bound needs no assumption.
            const std::size_t outputTokens = random_.between(0, model->maxTokens);

            run_.inputTokens = addTokens(run_.inputTokens, inputTokens);
            run_.outputTokens = addTokens(run_.outputTokens, outputTokens);
            ++run_.calls;
            run_.trace.push_back({let.name, let.call->promptName, let.call->modelName, inputTokens,
                                  outputTokens});
            ModelBilling& billing = run_.billing[let.call->modelName];
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
            // Attempts stop at the first success, so a real execution usually
            // costs less than the declared bound.  It may never cost more.
            for (std::size_t attempt = 0; attempt < retry.bound; ++attempt) {
                {
                    ScopedBlock frame(*this);
                    block(retry.body);
                }
                if (random_.percent() >= options_.retryFailurePercent) {
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

    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        const WorkflowDecl& workflow = *workflowPointer;
        WorkflowRun run;
        run.name = workflow.name;

        // Seeding per workflow keeps each workflow's execution reproducible on
        // its own, independent of how many workflows precede it in the file.
        Random random(options_.seed * 0x2545F4914F6CDD1DULL + workflow.name.size());
        Machine machine(semantic, options_, random, run);
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
            out << "    " << call.binding << " = " << call.prompt << " via " << call.model << "  in "
                << call.inputTokens << " out " << call.outputTokens << '\n';
        }
        if (!run.billing.empty()) {
            out << "  billing\n";
            for (const auto& entry : run.billing) {
                out << "    " << entry.first << "  calls " << entry.second.calls << "  in "
                    << entry.second.inputTokens << "  out " << entry.second.outputTokens << '\n';
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

}  // namespace orchlang
