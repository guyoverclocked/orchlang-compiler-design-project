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

class Machine {
public:
    Machine(const SemanticResult& semantic, const RunOptions& options, Random& random,
            WorkflowRun& run)
        : semantic_(semantic), options_(options), random_(random), run_(run) {}

    void block(const Block& statements);

private:
    void statement(const Stmt& node);
    const Value* value(const std::string& name) const;

    const SemanticResult& semantic_;
    const RunOptions& options_;
    Random& random_;
    WorkflowRun& run_;

    std::map<std::string, Value> values_;
    std::map<std::string, ModelInfo> models_;
    std::map<std::string, PromptInfo> prompts_;
};

const Value* Machine::value(const std::string& name) const {
    const auto found = values_.find(name);
    return found == values_.end() ? nullptr : &found->second;
}

void Machine::statement(const Stmt& node) {
    switch (node.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(node);
            // An input honours its declared bound, which is the contract the
            // estimated half of the cost bound is stated against.
            const std::size_t bound = input.hasTokenBound ? input.tokenBound : 0;
            values_[input.name] = {random_.between(0, bound), random_.percent() < 50};
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(node);
            const std::size_t bound = secret.hasTokenBound ? secret.tokenBound : 0;
            values_[secret.name] = {bound, random_.percent() < 50};
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(node);
            models_[model.name] = {model.maxTokens};
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(node);
            prompts_[prompt.name] = {
                estimateTextTokens(prompt.templateText, semantic_.options.charsPerToken)};
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(node);
            if (!let.call) {
                break;
            }
            const auto model = models_.find(let.call->modelName);
            const auto prompt = prompts_.find(let.call->promptName);
            if (model == models_.end() || prompt == prompts_.end()) {
                break;
            }

            std::size_t inputTokens = prompt->second.templateTokens;
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
                        estimateTextTokens(expressionToString(*argument), semantic_.options.charsPerToken));
                }
            }

            // The provider never returns more than max_tokens.  That cap is
            // the reason the guaranteed half of the bound needs no assumption.
            const std::size_t outputTokens = random_.between(0, model->second.maxTokens);

            run_.inputTokens = addTokens(run_.inputTokens, inputTokens);
            run_.outputTokens = addTokens(run_.outputTokens, outputTokens);
            ++run_.calls;
            run_.trace.push_back({let.name, let.call->promptName, let.call->modelName, inputTokens,
                                  outputTokens});

            values_[let.name] = {outputTokens, outputTokens % 2 == 0};
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
                block(branch.thenBranch);
            } else if (branch.hasElse) {
                block(branch.elseBranch);
            }
            break;
        }
        case StmtKind::Retry: {
            const auto& retry = static_cast<const RetryStmt&>(node);
            // Attempts stop at the first success, so a real execution usually
            // costs less than the declared bound.  It may never cost more.
            for (std::size_t attempt = 0; attempt < retry.bound; ++attempt) {
                block(retry.body);
                if (random_.percent() >= options_.retryFailurePercent) {
                    break;
                }
            }
            break;
        }
        case StmtKind::Reclassify: {
            const auto& reclassify = static_cast<const ReclassifyStmt&>(node);
            if (const Value* source = value(reclassify.sourceName)) {
                values_[reclassify.name] = *source;
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
        machine.block(workflow.statements);

        result.workflows.push_back(std::move(run));
    }
    return result;
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
