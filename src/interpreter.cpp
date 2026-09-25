#include "interpreter.hpp"

#include "token_cost.hpp"

#include <algorithm>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

std::string providerModeName(ProviderMode mode) {
    return mode == ProviderMode::Uniform ? "uniform" : "content";
}

std::string couplingName(Coupling coupling) {
    switch (coupling) {
        case Coupling::Global: return "global";
        case Coupling::Model: return "model";
        case Coupling::Request: return "request";
    }
    return "global";
}

std::string accountingName(Accounting accounting) {
    return accounting == Accounting::Estimate ? "estimate" : "tokenizer";
}

namespace {

// ------------------------------------------------------------ randomness ----

std::uint64_t fnv1a(const std::string& text) {
    std::uint64_t hash = 0xcbf29ce484222325ULL;
    for (const char character : text) {
        hash ^= static_cast<unsigned char>(character);
        hash *= 0x100000001b3ULL;
    }
    return hash;
}

// splitmix64's finaliser: a small, well-behaved, fully reproducible mixer.  The
// point is determinism, not statistical quality: the same seed and key must
// always give the same draw, so a reported violation replays exactly.
std::uint64_t mix(std::uint64_t value) {
    value += 0x9E3779B97F4A7C15ULL;
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9ULL;
    value = (value ^ (value >> 27)) * 0x94D049BB133111EBULL;
    return value ^ (value >> 31);
}

class Stream {
public:
    explicit Stream(std::uint64_t state) : state_(state) {}
    std::uint64_t next() {
        state_ = mix(state_);
        return state_;
    }
    std::size_t below(std::size_t bound) {
        return bound == 0 ? 0 : static_cast<std::size_t>(next() % bound);
    }

private:
    std::uint64_t state_;
};

// ------------------------------------------------------------------ text ----

// Words the runtime writes values and responses with.  Some are single tokens
// for the mock tokenizer, some are not, and some are not ASCII, so byte length,
// estimated tokens and counted tokens all come apart.  None is longer than
// eleven bytes, so with its separating space a word is at most twelve bytes,
// the most one token of the mock tokenizer decodes to.
const char* const kWords[] = {
    "the", "and", "payload", "ticket", "invoice", "order", "report", "summary",
    "refund", "account", "status", "urgent", "printer", "broken", "queue", "reply",
    "zqxv", "jkwb", "pfft", "xylyl", "qoph", "cwm", "vug", "aaaa",
    "bbbb", "café", "naïve", "日本", "données", "résumé", "Ω", "façade",
};
constexpr std::size_t kWordCount = sizeof(kWords) / sizeof(kWords[0]);

// The mock tokenizer's vocabulary.  Greedy longest match; any byte no entry
// covers is its own token, so every token covers at least one byte and
// tokens(s) <= bytes(s) holds for every string.
const char* const kVocabulary[] = {
    " the", " and", " payload", " ticket", " invoice", " order", " report", " summary",
    " refund", " account", " status", " urgent", " printer", " broken", " queue", " reply",
    "the", "and", "Process", " this", "Classify", "Summarise", " as", " or", " is", " a",
    "aa", "ing", "tion", "er", "re", "on", "th", "in", ": ", ", ", ". ", "  ",
    // Overlapping entries, as a real BPE vocabulary has: "e" + "rest" is two
    // tokens apart and four together, because "er" wins at the join.
    "rest",
};
constexpr std::size_t kVocabularySize = sizeof(kVocabulary) / sizeof(kVocabulary[0]);

std::string wordsText(std::size_t count, Stream& stream) {
    std::string text;
    for (std::size_t index = 0; index < count; ++index) {
        text += (index == 0 ? "" : " ");
        text += kWords[stream.below(kWordCount)];
    }
    return text;
}

// Exactly `bytes` bytes of well-formed UTF-8.
std::string bytesText(std::size_t bytes, Stream& stream) {
    std::string text;
    while (true) {
        const std::string word = std::string(text.empty() ? "" : " ") + kWords[stream.below(kWordCount)];
        if (text.size() + word.size() > bytes) {
            break;
        }
        text += word;
    }
    while (text.size() < bytes) {
        text.push_back('x');
    }
    return text;
}

// The longest prefix of at most `limit` bytes that ends on a code point boundary.
std::string truncateUtf8(const std::string& text, std::size_t limit) {
    if (text.size() <= limit) {
        return text;
    }
    std::size_t cut = limit;
    while (cut > 0 && (static_cast<unsigned char>(text[cut]) & 0xC0) == 0x80) {
        --cut;
    }
    return text.substr(0, cut);
}

// ---------------------------------------------------------------- values ----

struct Value {
    std::string text;
    bool flag{false};
    // Tokens in the analysis's estimate unit: what the certified estimate
    // charged for this value, and what a 'tokens(...)' guard reads.
    std::size_t estimate{0};
};

struct ModelInfo {
    std::size_t maxTokens{0};
    std::string modelString;
    std::string identity;
    std::size_t overhead{0};
    bool hasByteCap{false};
    std::size_t byteCap{0};
};

struct PromptInfo {
    std::string templateText;
    std::vector<std::string> parameters;
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
    Machine(const SemanticResult& semantic, const RunOptions& options, WorkflowRun& run)
        : semantic_(semantic), options_(options), run_(run) {}

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
    void declareValue(const std::string& name, bool hasTokenBound, std::size_t tokenBound,
                      bool hasByteBound, std::size_t byteBound, bool alwaysAtBound);
    void call(const LetStmt& let);
    bool attemptSucceeded(const std::string& attemptTranscript);
    std::uint64_t draw(const std::string& key) const {
        return mix(options_.seed * 0x2545F4914F6CDD1DULL ^ fnv1a(key));
    }
    const Value* value(const std::string& name) const { return values_.find(name); }

    const SemanticResult& semantic_;
    const RunOptions& options_;
    WorkflowRun& run_;

    Environment<Value> values_;
    Environment<ModelInfo> models_;
    Environment<PromptInfo> prompts_;

    // Counters behind the three couplings.
    std::size_t events_{0};
    std::size_t coins_{0};
    std::map<std::string, std::size_t> perModel_;
    std::map<std::string, std::size_t> perRequest_;
    std::map<std::string, std::size_t> perAttempt_;
    // What the innermost running retry attempt has sent and received.
    std::vector<std::string> attemptLog_;
};

// Runs a block in its own frame, so nothing declared inside escapes it.
struct ScopedBlock {
    explicit ScopedBlock(Machine& machine) : machine_(machine) { machine_.enter(); }
    ~ScopedBlock() { machine_.leave(); }
    Machine& machine_;
};

// Inputs and secrets.  Their values come from the environment, not from the
// provider, so they are drawn from a stream keyed by name alone: the same seed
// gives the same public inputs whatever path an execution takes.
void Machine::declareValue(const std::string& name, bool hasTokenBound, std::size_t tokenBound,
                           bool hasByteBound, std::size_t byteBound, bool alwaysAtBound) {
    Stream stream(draw("env#" + name));
    Value produced;
    produced.flag = stream.below(2) == 1;
    const auto pinnedFlag = options_.pinnedFlags.find(name);
    if (pinnedFlag != options_.pinnedFlags.end()) {
        produced.flag = pinnedFlag->second;
    }
    const auto pinned = options_.pinnedLengths.find(name);
    const std::size_t divisor = semantic_.options.charsPerToken == 0 ? 1 : semantic_.options.charsPerToken;
    if (hasByteBound && !hasTokenBound) {
        std::size_t bytes = alwaysAtBound ? byteBound : stream.below(byteBound + 1);
        if (pinned != options_.pinnedLengths.end()) {
            bytes = std::min(pinned->second, byteBound);
        }
        produced.text = bytesText(bytes, stream);
        produced.estimate = produced.text.size() / divisor + (produced.text.size() % divisor != 0);
    } else {
        const std::size_t bound = hasTokenBound ? tokenBound : 0;
        std::size_t words = alwaysAtBound ? bound : stream.below(bound + 1);
        if (pinned != options_.pinnedLengths.end()) {
            words = pinned->second;
        }
        produced.text = wordsText(words, stream);
        if (hasByteBound) {
            produced.text = truncateUtf8(produced.text, byteBound);
        }
        produced.estimate = words;
    }
    values_.define(name, std::move(produced));
}

bool Machine::attemptSucceeded(const std::string& attemptTranscript) {
    std::string key;
    switch (options_.coupling) {
        case Coupling::Global:
            key = "g#" + std::to_string(events_++);
            break;
        case Coupling::Model:
            key = "c#" + std::to_string(coins_++);
            break;
        case Coupling::Request: {
            const std::string content = std::to_string(fnv1a(attemptTranscript));
            key = "v#" + content + "#" + std::to_string(perAttempt_[content]++);
            break;
        }
    }
    std::uint64_t coin = draw(key);
    if (options_.provider == ProviderMode::Content) {
        coin = mix(coin ^ fnv1a(attemptTranscript));
    }
    return coin % 100 >= options_.retryFailurePercent;
}

void Machine::call(const LetStmt& let) {
    const ModelInfo* model = models_.find(let.call->modelName);
    const PromptInfo* prompt = prompts_.find(let.call->promptName);
    if (!model || !prompt) {
        return;
    }

    // Build the request the provider will receive, substituting each argument
    // at its placeholder.  This is an independent implementation of what the
    // analysis records symbolically, so a disagreement shows up as a failed
    // check rather than being shared by both.
    std::vector<std::string> argumentText;
    std::size_t estimateTokens = estimateTextTokens(prompt->templateText, semantic_.options.charsPerToken);
    for (const auto& argument : let.call->arguments) {
        if (!argument) {
            argumentText.emplace_back();
            continue;
        }
        if (argument->kind() == ExprKind::Identifier) {
            const Value* bound = value(static_cast<const IdentifierExpr&>(*argument).name);
            argumentText.push_back(bound ? bound->text : std::string());
            estimateTokens = addTokens(estimateTokens, bound ? bound->estimate : 0);
        } else {
            argumentText.push_back(substitutedText(*argument));
            estimateTokens = addTokens(
                estimateTokens, estimateTextTokens(argumentText.back(), semantic_.options.charsPerToken));
        }
    }
    std::string request;
    const std::string& text = prompt->templateText;
    for (std::size_t index = 0; index < text.size();) {
        if ((text[index] == '{' || text[index] == '}') && index + 1 < text.size() &&
            text[index + 1] == text[index]) {
            request.push_back(text[index]);
            index += 2;
            continue;
        }
        bool substituted = false;
        if (text[index] == '{') {
            const std::size_t closing = text.find('}', index + 1);
            if (closing != std::string::npos) {
                const std::string name = text.substr(index + 1, closing - index - 1);
                for (std::size_t parameter = 0; parameter < prompt->parameters.size(); ++parameter) {
                    if (prompt->parameters[parameter] == name && parameter < argumentText.size()) {
                        request += argumentText[parameter];
                        index = closing + 1;
                        substituted = true;
                        break;
                    }
                }
            }
        }
        if (!substituted) {
            request.push_back(text[index]);
            ++index;
        }
    }

    const std::size_t inputTokens =
        options_.accounting == Accounting::Estimate
            ? estimateTokens
            : addTokens(mockTokenCount(request), model->overhead);

    // The provider's draw, aligned across executions by the chosen coupling.
    std::string key;
    switch (options_.coupling) {
        case Coupling::Global:
            key = "g#" + std::to_string(events_++);
            break;
        case Coupling::Model:
            key = "m#" + model->identity + "#" + std::to_string(perModel_[model->identity]++);
            break;
        case Coupling::Request: {
            const std::string content = model->identity + "\n" + request;
            key = "q#" + std::to_string(fnv1a(content)) + "#" + std::to_string(perRequest_[content]++);
            break;
        }
    }
    std::uint64_t drawn = draw(key);
    if (options_.provider == ProviderMode::Content) {
        // A real model's answer depends on what it was asked.
        drawn = mix(drawn ^ fnv1a(model->identity + "\n" + request));
    }
    // The provider never returns more than max_tokens.  That cap is the reason
    // the output half of the bound needs no assumption.
    const std::size_t outputTokens = static_cast<std::size_t>(drawn % (model->maxTokens + 1));
    Stream words(drawn);
    std::string response = wordsText(outputTokens, words);
    if (model->hasByteCap) {
        response = truncateUtf8(response, model->byteCap);
    }

    run_.inputTokens = addTokens(run_.inputTokens, inputTokens);
    run_.outputTokens = addTokens(run_.outputTokens, outputTokens);
    ++run_.calls;
    run_.trace.push_back({let.name, let.call->promptName, let.call->modelName, model->modelString,
                          model->identity, request, response, inputTokens, outputTokens});
    ModelBilling& billing = run_.billing[model->modelString];
    billing.inputTokens = addTokens(billing.inputTokens, inputTokens);
    billing.outputTokens = addTokens(billing.outputTokens, outputTokens);
    ++billing.calls;
    attemptLog_.push_back(model->identity + "\n" + request + "\n" + response);

    values_.define(let.name, {response, outputTokens % 2 == 0, outputTokens});
}

void Machine::statement(const Stmt& node) {
    switch (node.kind()) {
        case StmtKind::Input: {
            const auto& input = static_cast<const InputDecl&>(node);
            // An input honours its declared bound, which is the contract the
            // estimated half of the cost bound is stated against.
            declareValue(input.name, input.hasTokenBound, input.tokenBound, input.hasByteBound,
                         input.byteBound, false);
            break;
        }
        case StmtKind::Secret: {
            const auto& secret = static_cast<const SecretDecl&>(node);
            declareValue(secret.name, secret.hasTokenBound, secret.tokenBound, secret.hasByteBound,
                         secret.byteBound, true);
            break;
        }
        case StmtKind::Model: {
            const auto& model = static_cast<const ModelDecl&>(node);
            ModelMetadata metadata{model.provider, model.modelName, model.maxTokens, false, 0.0,
                                   model.tokenizer, model.overhead, model.hasByteCap, model.byteCap};
            models_.define(model.name, {model.maxTokens, model.modelName, metadata.identity(),
                                        model.overhead, model.hasByteCap, model.byteCap});
            break;
        }
        case StmtKind::Prompt: {
            const auto& prompt = static_cast<const PromptDecl&>(node);
            PromptInfo info;
            info.templateText = prompt.templateText;
            for (const Parameter& parameter : prompt.parameters) {
                info.parameters.push_back(parameter.name);
            }
            prompts_.define(prompt.name, std::move(info));
            break;
        }
        case StmtKind::Let: {
            const auto& let = static_cast<const LetStmt&>(node);
            if (let.call) {
                call(let);
            }
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
                    const std::size_t actual = subject->estimate;
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
            std::size_t attempts = 0;
            for (std::size_t attempt = 0; attempt < retry.bound; ++attempt) {
                std::vector<std::string> outer;
                outer.swap(attemptLog_);
                {
                    ScopedBlock frame(*this);
                    block(retry.body);
                }
                ++attempts;
                std::string transcript;
                for (const std::string& entry : attemptLog_) {
                    transcript += entry + "\n";
                }
                outer.insert(outer.end(), attemptLog_.begin(), attemptLog_.end());
                attemptLog_.swap(outer);
                if (attemptSucceeded(transcript)) {
                    break;
                }
            }
            run_.retryAttempts.push_back(attempts);
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
            std::string effect = emit.toolName + "(";
            for (std::size_t index = 0; index < emit.arguments.size(); ++index) {
                const Expr* argument = emit.arguments[index].get();
                std::string text;
                if (argument && argument->kind() == ExprKind::Identifier) {
                    const Value* bound = value(static_cast<const IdentifierExpr&>(*argument).name);
                    text = bound ? bound->text : std::string();
                } else if (argument) {
                    text = substitutedText(*argument);
                }
                effect += (index == 0 ? "" : ", ") + text;
            }
            run_.effects.push_back(effect + ")");
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

std::string jsonString(const std::string& text) {
    std::ostringstream out;
    out << '"';
    for (const char character : text) {
        switch (character) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (static_cast<unsigned char>(character) < 0x20) {
                    out << "\\u00" << "0123456789abcdef"[(character >> 4) & 0xF]
                        << "0123456789abcdef"[character & 0xF];
                } else {
                    out << character;
                }
                break;
        }
    }
    out << '"';
    return out.str();
}

}  // namespace

std::size_t mockTokenCount(const std::string& text) {
    std::size_t tokens = 0;
    std::size_t index = 0;
    while (index < text.size()) {
        std::size_t longest = 1;
        for (std::size_t entry = 0; entry < kVocabularySize; ++entry) {
            const std::string piece = kVocabulary[entry];
            if (piece.size() > longest && text.compare(index, piece.size(), piece) == 0) {
                longest = piece.size();
            }
        }
        index += longest;
        ++tokens;
    }
    return tokens;
}

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

        // Keys include the workflow name, so each workflow's execution is
        // reproducible on its own, independent of what precedes it in the file.
        RunOptions options = options_;
        options.seed = options_.seed * 0x9E3779B97F4A7C15ULL ^ fnv1a(workflow.name);
        Machine machine(semantic, options, run);
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

bool sameTranscript(const WorkflowRun& left, const WorkflowRun& right) {
    if (left.trace.size() != right.trace.size()) {
        return false;
    }
    for (std::size_t index = 0; index < left.trace.size(); ++index) {
        const CallTrace& a = left.trace[index];
        const CallTrace& b = right.trace[index];
        if (a.identity != b.identity || a.request != b.request || a.response != b.response ||
            a.inputTokens != b.inputTokens || a.outputTokens != b.outputTokens) {
            return false;
        }
    }
    return true;
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

std::string printRunJson(const RunResult& result, const RunOptions& options) {
    std::ostringstream out;
    out << "{\"options\": {\"seed\": " << options.seed << ", \"provider\": "
        << jsonString(providerModeName(options.provider)) << ", \"coupling\": "
        << jsonString(couplingName(options.coupling)) << ", \"accounting\": "
        << jsonString(accountingName(options.accounting)) << "},\n \"workflows\": [";
    for (std::size_t w = 0; w < result.workflows.size(); ++w) {
        const WorkflowRun& run = result.workflows[w];
        out << (w == 0 ? "" : ",") << "\n  {\"name\": " << jsonString(run.name)
            << ", \"input_tokens\": " << run.inputTokens << ", \"output_tokens\": " << run.outputTokens
            << ", \"calls\": [";
        for (std::size_t c = 0; c < run.trace.size(); ++c) {
            const CallTrace& call = run.trace[c];
            out << (c == 0 ? "" : ",") << "\n    {\"binding\": " << jsonString(call.binding)
                << ", \"prompt\": " << jsonString(call.prompt) << ", \"model\": " << jsonString(call.model)
                << ", \"model_string\": " << jsonString(call.modelString)
                << ", \"identity\": " << jsonString(call.identity)
                << ", \"request\": " << jsonString(call.request)
                << ", \"response\": " << jsonString(call.response)
                << ", \"input_tokens\": " << call.inputTokens
                << ", \"output_tokens\": " << call.outputTokens << "}";
        }
        out << "],\n   \"billing\": {";
        bool first = true;
        for (const auto& entry : run.billing) {
            out << (first ? "" : ", ") << jsonString(entry.first) << ": {\"calls\": " << entry.second.calls
                << ", \"input_tokens\": " << entry.second.inputTokens
                << ", \"output_tokens\": " << entry.second.outputTokens << "}";
            first = false;
        }
        out << "},\n   \"retry_attempts\": [";
        for (std::size_t r = 0; r < run.retryAttempts.size(); ++r) {
            out << (r == 0 ? "" : ", ") << run.retryAttempts[r];
        }
        out << "], \"effects\": [";
        for (std::size_t e = 0; e < run.effects.size(); ++e) {
            out << (e == 0 ? "" : ", ") << jsonString(run.effects[e]);
        }
        out << "]}";
    }
    out << "\n]}\n";
    return out.str();
}

}  // namespace orchlang
