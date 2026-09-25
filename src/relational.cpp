#include "relational.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <sstream>
#include <utility>

namespace orchlang {

std::string relationalRuleName(RelationalRule rule) {
    switch (rule) {
        case RelationalRule::Content: return "content";
        case RelationalRule::Sizes: return "sizes (withdrawn)";
        case RelationalRule::Bounds: return "bounds (withdrawn)";
    }
    return "content";
}

namespace {

// ------------------------------------------------------------ signatures ----

// One part of a request as the provider receives it.
struct Piece {
    enum class Kind { Text, Var, Result };
    Kind kind{Kind::Text};
    // Text: the characters sent.
    std::string text;
    // Var: a binding outside the compared region, by identity.
    int binding{0};
    // Result: an earlier call's position in the signature.
    std::string path;
    // What the author called it, for messages only.
    std::string display;
};

struct GuardTerm {
    Piece subject;
    ConditionKind kind{ConditionKind::Flag};
    ComparisonOp op{ComparisonOp::LessEqual};
    std::size_t limit{0};
};

enum class NodeKind { Call, Retry, Branch };

struct Node;
using Sig = std::vector<Node>;

struct Node {
    NodeKind kind{NodeKind::Call};
    // Where this node sits, so later requests can refer to its response.
    std::string path;
    // Call
    std::string model;
    std::string modelString;
    std::string provider;
    std::vector<Piece> pieces;
    // Retry
    std::size_t bound{0};
    // Branch on a guard both executions evaluate alike
    GuardTerm guard;
    std::vector<Sig> children;
    SourceLocation location;
};

using Remap = std::map<std::string, std::string>;

std::string pieceKey(const Piece& piece, const Remap& remap) {
    switch (piece.kind) {
        case Piece::Kind::Text:
            return "t" + std::to_string(piece.text.size()) + ":" + piece.text;
        case Piece::Kind::Var:
            return "v" + std::to_string(piece.binding);
        case Piece::Kind::Result: {
            const auto found = remap.find(piece.path);
            return "r" + (found == remap.end() ? piece.path : found->second);
        }
    }
    return "?";
}

std::string guardKey(const GuardTerm& guard, const Remap& remap) {
    std::ostringstream out;
    out << (guard.kind == ConditionKind::Flag ? "flag(" : "tokens(") << pieceKey(guard.subject, remap)
        << ')';
    if (guard.kind == ConditionKind::TokenBound) {
        out << comparisonOpName(guard.op) << guard.limit;
    }
    return out.str();
}

std::string sigKey(const Sig& signature, const Remap& remap);

std::string callKey(const Node& node, const Remap& remap) {
    std::string key = "C<" + node.model + ">(";
    for (const Piece& piece : node.pieces) {
        key += pieceKey(piece, remap) + ";";
    }
    return key + ")";
}

std::string nodeKey(const Node& node, const Remap& remap) {
    switch (node.kind) {
        case NodeKind::Call:
            return callKey(node, remap);
        case NodeKind::Retry:
            return "R" + std::to_string(node.bound) + "{" +
                   (node.children.empty() ? std::string() : sigKey(node.children[0], remap)) + "}";
        case NodeKind::Branch:
            return "B(" + guardKey(node.guard, remap) + "){" +
                   (node.children.size() > 0 ? sigKey(node.children[0], remap) : std::string()) +
                   "}{" +
                   (node.children.size() > 1 ? sigKey(node.children[1], remap) : std::string()) +
                   "}";
    }
    return "?";
}

std::string sigKey(const Sig& signature, const Remap& remap) {
    std::string key;
    for (const Node& node : signature) {
        key += nodeKey(node, remap) + "|";
    }
    return key;
}

bool refersInto(const Node& node, const std::set<std::string>& paths) {
    for (const Piece& piece : node.pieces) {
        if (piece.kind == Piece::Kind::Result && paths.count(piece.path) != 0) {
            return true;
        }
    }
    return false;
}

// The canonical form of a signature for one observer.
//
// Trace: the requests in order.  Provider: within each maximal run of calls
// with no data dependence between them, the order of calls to *different*
// providers is forgotten, because each provider sees only its own requests.
// Bill: within such a run, order is forgotten altogether, because an invoice
// shows sums.  Control nodes are never reordered, and references to a moved
// call are rewritten to its new position so that they still denote the same
// response.  Soundness rests on the request-indexed coupling (the k-th
// occurrence of a request to a model receives the k-th draw for that request),
// under which a call's response does not depend on where in a run it is made.
std::string normalizedKey(const Sig& signature, Observer observer, Remap& remap);

std::string normalizedChildren(const Node& node, Observer observer, Remap& remap) {
    switch (node.kind) {
        case NodeKind::Call:
            return callKey(node, remap);
        case NodeKind::Retry:
            // Never reorder inside a retry body, for any observer.  Whether an
            // attempt succeeds is decided on the attempt's transcript, and a
            // validator may care about order ("the last response must parse"),
            // so reordering there can change how many attempts are made, and
            // with them the bill.  An earlier version of this function did
            // reorder here; tests/tests.cpp has the counterexample.
            return "R" + std::to_string(node.bound) + "{" +
                   (node.children.empty() ? std::string()
                                          : normalizedKey(node.children[0], Observer::Trace, remap)) +
                   "}";
        case NodeKind::Branch:
            return "B(" + guardKey(node.guard, remap) + "){" +
                   (node.children.size() > 0 ? normalizedKey(node.children[0], observer, remap)
                                             : std::string()) +
                   "}{" +
                   (node.children.size() > 1 ? normalizedKey(node.children[1], observer, remap)
                                             : std::string()) +
                   "}";
    }
    return "?";
}

std::string normalizedKey(const Sig& signature, Observer observer, Remap& remap) {
    std::string key;
    std::size_t index = 0;
    while (index < signature.size()) {
        if (signature[index].kind != NodeKind::Call || observer == Observer::Trace) {
            key += normalizedChildren(signature[index], observer, remap) + "|";
            ++index;
            continue;
        }
        // Collect a run of mutually independent calls.
        std::size_t end = index;
        std::set<std::string> inRun;
        while (end < signature.size() && signature[end].kind == NodeKind::Call &&
               !refersInto(signature[end], inRun)) {
            inRun.insert(signature[end].path);
            ++end;
        }
        std::vector<std::size_t> order;
        for (std::size_t k = index; k < end; ++k) {
            order.push_back(k);
        }
        std::vector<std::string> keys(signature.size());
        for (std::size_t k : order) {
            keys[k] = callKey(signature[k], remap);
        }
        std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
            if (observer == Observer::Provider) {
                return signature[a].provider < signature[b].provider;
            }
            return keys[a] < keys[b];
        });
        // A call's new position is where it now sits; later references follow it.
        const std::string prefix = signature[index].path.substr(
            0, signature[index].path.find_last_of('.') == std::string::npos
                   ? 0
                   : signature[index].path.find_last_of('.') + 1);
        for (std::size_t slot = 0; slot < order.size(); ++slot) {
            remap[signature[order[slot]].path] = prefix + std::to_string(index + slot);
        }
        for (std::size_t k : order) {
            key += keys[k] + "|";
        }
        index = end;
    }
    return key;
}

// Human-readable rendering, for diagnostics and the certificate.
std::string pieceText(const Piece& piece) {
    switch (piece.kind) {
        case Piece::Kind::Text: {
            std::string shown = piece.text.size() > 40 ? piece.text.substr(0, 37) + "..." : piece.text;
            std::string escaped;
            for (const char c : shown) {
                if (c == '\n') {
                    escaped += "\\n";
                } else if (c == '"') {
                    escaped += "\\\"";
                } else {
                    escaped += c;
                }
            }
            return "\"" + escaped + "\"";
        }
        case Piece::Kind::Var:
            return piece.display;
        case Piece::Kind::Result:
            return "response#" + piece.path + (piece.display.empty() ? "" : "(" + piece.display + ")");
    }
    return "?";
}

std::string sigText(const Sig& signature);

std::string nodeText(const Node& node) {
    std::ostringstream out;
    switch (node.kind) {
        case NodeKind::Call: {
            out << node.modelString << "(";
            for (std::size_t k = 0; k < node.pieces.size(); ++k) {
                out << (k == 0 ? "" : " + ") << pieceText(node.pieces[k]);
            }
            out << ")";
            break;
        }
        case NodeKind::Retry:
            out << "retry " << node.bound << " {"
                << (node.children.empty() ? std::string() : sigText(node.children[0])) << "}";
            break;
        case NodeKind::Branch: {
            out << "if " << (node.guard.kind == ConditionKind::Flag ? "" : "tokens(")
                << pieceText(node.guard.subject);
            if (node.guard.kind == ConditionKind::TokenBound) {
                out << ") " << comparisonOpName(node.guard.op) << ' ' << node.guard.limit;
            }
            out << " {" << (node.children.size() > 0 ? sigText(node.children[0]) : std::string())
                << "} else {" << (node.children.size() > 1 ? sigText(node.children[1]) : std::string())
                << "}";
            break;
        }
    }
    return out.str();
}

std::string sigText(const Sig& signature) {
    if (signature.empty()) {
        return "nothing";
    }
    std::string text;
    for (std::size_t k = 0; k < signature.size(); ++k) {
        text += (k == 0 ? "" : "; ") + nodeText(signature[k]);
    }
    return text;
}

// Explains the first place two signatures part ways.
std::string firstDifference(const Sig& left, const Sig& right) {
    const std::size_t common = std::min(left.size(), right.size());
    const Remap none;
    for (std::size_t k = 0; k < common; ++k) {
        if (nodeKey(left[k], none) == nodeKey(right[k], none)) {
            continue;
        }
        const Node& a = left[k];
        const Node& b = right[k];
        if (a.kind != b.kind) {
            return "at step " + std::to_string(k + 1) + " one arm does " + nodeText(a) +
                   " where the other does " + nodeText(b);
        }
        if (a.kind == NodeKind::Call && a.model != b.model) {
            return "at step " + std::to_string(k + 1) + " the arms call different endpoints: " +
                   a.model + " and " + b.model;
        }
        if (a.kind == NodeKind::Call) {
            return "at step " + std::to_string(k + 1) +
                   " the arms send different request text to the same endpoint, and a provider's "
                   "response length depends on what a request says, not only on its size";
        }
        return "at step " + std::to_string(k + 1) + " the arms differ: " + nodeText(a) + " vs " +
               nodeText(b);
    }
    if (left.size() != right.size()) {
        return "one arm makes " + std::to_string(left.size()) + " top-level request(s), the other " +
               std::to_string(right.size());
    }
    return "the arms differ only in how their requests may be reordered for this observer";
}

// ----------------------------------------------------------- predicates ----

std::string predicateKey(const GuardFact& guard, const Condition& condition) {
    std::ostringstream out;
    out << guard.secretRootId << (condition.kind == ConditionKind::Flag ? "F" : "T");
    if (condition.kind == ConditionKind::TokenBound) {
        out << static_cast<int>(condition.op) << ':' << condition.limit;
    }
    return out.str();
}

bool compare(std::size_t value, ComparisonOp op, std::size_t limit) {
    switch (op) {
        case ComparisonOp::Less: return value < limit;
        case ComparisonOp::LessEqual: return value <= limit;
        case ComparisonOp::Greater: return value > limit;
        case ComparisonOp::GreaterEqual: return value >= limit;
        case ComparisonOp::Equal: return value == limit;
        case ComparisonOp::NotEqual: return value != limit;
    }
    return false;
}

struct Predicate {
    std::string key;
    int root{0};
    ConditionKind kind{ConditionKind::Flag};
    ComparisonOp op{ComparisonOp::LessEqual};
    std::size_t limit{0};
    bool boundKnown{false};
    std::size_t bound{0};
    std::string display;
};

// ------------------------------------------------------------- builder ----

using Outcomes = std::map<std::string, bool>;

class Builder {
public:
    // Resolve: every secret guard takes the outcome given.  Local: a nested
    // secret guard is accepted only if its own arms agree.
    Builder(const SemanticResult& semantic, const Outcomes* outcomes, Observer observer)
        : semantic_(semantic), outcomes_(outcomes), observer_(observer) {}

    Sig build(const Block& block) {
        Sig out;
        into(block, out, "");
        return out;
    }

    bool defined() const { return defined_; }
    const std::string& reason() const { return reason_; }

private:
    void undefine(const std::string& why) {
        if (defined_) {
            defined_ = false;
            reason_ = why;
        }
    }

    // A public variable standing for itself.
    static Piece variable(int binding, const std::string& name) {
        Piece piece;
        piece.kind = Piece::Kind::Var;
        piece.binding = binding;
        piece.display = name;
        return piece;
    }

    // What a binding denotes inside the region being compared.
    //
    // A copy (endorse or declassify) of a value with public content denotes
    // the same text as its source, so it is followed back to it.  A declassified
    // copy of a *secret* is not: it stands for itself, as a public value.  That
    // is what declassification means -- the guarantee is stated for secrets
    // that agree on every declassified value -- and it is trusted, not checked.
    Piece pieceFor(int binding, const std::string& name) {
        for (auto scope = scopes_.rbegin(); scope != scopes_.rend(); ++scope) {
            const auto found = scope->find(binding);
            if (found != scope->end()) {
                return found->second;
            }
        }
        const auto fact = semantic_.bindings.find(binding);
        if (fact == semantic_.bindings.end()) {
            return variable(binding, name);
        }
        if (fact->second.dataLabel.isSecret()) {
            undefine("'" + name + "' carries secret content into a request");
            return variable(binding, name);
        }
        if (fact->second.aliasOf != 0) {
            const auto source = semantic_.bindings.find(fact->second.aliasOf);
            if (source != semantic_.bindings.end() && !source->second.dataLabel.isSecret()) {
                return pieceFor(fact->second.aliasOf, source->second.name);
            }
        }
        return variable(binding, name);
    }

    void into(const Block& block, Sig& out, const std::string& prefix) {
        scopes_.emplace_back();
        for (const auto& statement : block) {
            if (statement) {
                statementInto(*statement, out, prefix);
            }
        }
        scopes_.pop_back();
    }

    void statementInto(const Stmt& statement, Sig& out, const std::string& prefix) {
        switch (statement.kind()) {
            case StmtKind::Let: {
                const auto& let = static_cast<const LetStmt&>(statement);
                if (!let.call) {
                    return;
                }
                const auto site = semantic_.callSites.find(let.call.get());
                if (site == semantic_.callSites.end()) {
                    undefine("a call site was not analysed");
                    return;
                }
                Node node;
                node.kind = NodeKind::Call;
                node.path = prefix + std::to_string(out.size());
                node.model = site->second.modelIdentity;
                node.modelString = site->second.modelString;
                node.provider = site->second.modelProvider;
                node.location = statement.location;
                for (const TemplatePiece& part : site->second.pieces) {
                    Piece piece;
                    if (!part.isArgument) {
                        piece.text = part.text;
                    } else if (part.argument < site->second.arguments.size()) {
                        const ArgumentFact& argument = site->second.arguments[part.argument];
                        if (argument.isSecret) {
                            undefine("'" + argument.name + "' carries secret content into a request");
                        }
                        if (argument.isLiteral) {
                            piece.text = argument.literalText;
                        } else {
                            piece = pieceFor(argument.bindingId, argument.name);
                        }
                    }
                    // Adjacent text is one run of characters to the provider.
                    if (piece.kind == Piece::Kind::Text && !node.pieces.empty() &&
                        node.pieces.back().kind == Piece::Kind::Text) {
                        node.pieces.back().text += piece.text;
                    } else if (piece.kind != Piece::Kind::Text || !piece.text.empty()) {
                        node.pieces.push_back(piece);
                    }
                }
                const auto introduced = semantic_.introduced.find(&statement);
                if (introduced != semantic_.introduced.end()) {
                    Piece result;
                    result.kind = Piece::Kind::Result;
                    result.path = node.path;
                    result.display = let.name;
                    scopes_.back()[introduced->second] = result;
                }
                out.push_back(std::move(node));
                return;
            }
            case StmtKind::Retry: {
                const auto& retry = static_cast<const RetryStmt&>(statement);
                Node node;
                node.kind = NodeKind::Retry;
                node.path = prefix + std::to_string(out.size());
                node.bound = retry.bound;
                node.location = statement.location;
                Sig body;
                into(retry.body, body, node.path + ".0.");
                node.children.push_back(std::move(body));
                out.push_back(std::move(node));
                return;
            }
            case StmtKind::If: {
                const auto& branch = static_cast<const IfStmt&>(statement);
                const auto guard = semantic_.guards.find(&branch);
                if (guard == semantic_.guards.end()) {
                    undefine("a guard was not analysed");
                    return;
                }
                if (guard->second.secretData) {
                    secretBranchInto(branch, guard->second, out, prefix);
                    return;
                }
                // Both executions evaluate this guard on the same text, so they
                // take the same arm; the arms need not agree.
                Node node;
                node.kind = NodeKind::Branch;
                node.path = prefix + std::to_string(out.size());
                node.location = statement.location;
                node.guard.subject = pieceFor(guard->second.subjectId, branch.condition.subjectName);
                node.guard.kind = branch.condition.kind;
                node.guard.op = branch.condition.op;
                node.guard.limit = branch.condition.limit;
                Sig thenSig;
                Sig elseSig;
                into(branch.thenBranch, thenSig, node.path + ".0.");
                into(branch.elseBranch, elseSig, node.path + ".1.");
                node.children.push_back(std::move(thenSig));
                node.children.push_back(std::move(elseSig));
                out.push_back(std::move(node));
                return;
            }
            case StmtKind::Reclassify: {
                const auto introduced = semantic_.introduced.find(&statement);
                if (introduced == semantic_.introduced.end()) {
                    return;
                }
                const auto fact = semantic_.bindings.find(introduced->second);
                if (fact == semantic_.bindings.end() || fact->second.aliasOf == 0) {
                    return;
                }
                const auto& reclassify = static_cast<const ReclassifyStmt&>(statement);
                const auto source = semantic_.bindings.find(fact->second.aliasOf);
                if (source != semantic_.bindings.end() && source->second.dataLabel.isSecret()) {
                    // Declassified here: a public value standing for itself.
                    scopes_.back()[introduced->second] = variable(introduced->second, reclassify.name);
                } else {
                    scopes_.back()[introduced->second] =
                        pieceFor(fact->second.aliasOf, reclassify.sourceName);
                }
                return;
            }
            case StmtKind::Input:
            case StmtKind::Secret:
            case StmtKind::Model:
            case StmtKind::Prompt:
            case StmtKind::Tool:
            case StmtKind::Require:
            case StmtKind::Emit:
            case StmtKind::Output:
                // None of these sends anything to a model.
                return;
        }
    }

    void secretBranchInto(const IfStmt& branch, const GuardFact& guard, Sig& out,
                          const std::string& prefix) {
        if (outcomes_) {
            const auto outcome = outcomes_->find(predicateKey(guard, branch.condition));
            const bool taken = outcome != outcomes_->end() && outcome->second;
            into(taken ? branch.thenBranch : branch.elseBranch, out, prefix);
            return;
        }
        // Local mode: the nested branch contributes its common signature, if it
        // has one.
        Sig thenOut = out;
        Sig elseOut = out;
        into(branch.thenBranch, thenOut, prefix);
        into(branch.elseBranch, elseOut, prefix);
        Remap left;
        Remap right;
        if (normalizedKey(thenOut, observer_, left) != normalizedKey(elseOut, observer_, right)) {
            undefine("a nested secret-guarded branch at line " +
                     std::to_string(branch.location.line) + " has arms that send different requests");
        }
        out = std::move(thenOut);
    }

    const SemanticResult& semantic_;
    const Outcomes* outcomes_;
    Observer observer_;
    std::vector<std::map<int, Piece>> scopes_;
    bool defined_{true};
    std::string reason_;
};

// --------------------------------------------------------------- walker ----

void collectSecretBranches(const Block& block, const SemanticResult& semantic,
                           std::vector<const IfStmt*>& branches) {
    for (const auto& statement : block) {
        if (!statement) {
            continue;
        }
        if (statement->kind() == StmtKind::Retry) {
            collectSecretBranches(static_cast<const RetryStmt&>(*statement).body, semantic, branches);
        } else if (statement->kind() == StmtKind::If) {
            const auto& branch = static_cast<const IfStmt&>(*statement);
            const auto guard = semantic.guards.find(&branch);
            if (guard != semantic.guards.end() && guard->second.secretData) {
                branches.push_back(&branch);
            }
            collectSecretBranches(branch.thenBranch, semantic, branches);
            collectSecretBranches(branch.elseBranch, semantic, branches);
        }
    }
}

// The combinations of outcomes the secrets allow for these predicates.  Each
// secret is independent of the others; for one secret, the reachable outcome
// vectors are found by evaluating its predicates at every value that could
// change one of them.
std::vector<Outcomes> feasibleOutcomes(const std::vector<Predicate>& predicates,
                                       std::size_t limit, std::size_t& total, bool& enumerated) {
    std::map<int, std::vector<const Predicate*>> bySecret;
    for (const Predicate& predicate : predicates) {
        bySecret[predicate.root].push_back(&predicate);
    }
    std::vector<std::vector<Outcomes>> perSecret;
    for (const auto& entry : bySecret) {
        bool hasFlag = false;
        bool boundKnown = false;
        std::size_t bound = 0;
        std::set<std::size_t> lengths{0};
        for (const Predicate* predicate : entry.second) {
            if (predicate->kind == ConditionKind::Flag) {
                hasFlag = true;
            } else {
                lengths.insert(predicate->limit);
                lengths.insert(predicate->limit + 1);
                if (predicate->limit > 0) {
                    lengths.insert(predicate->limit - 1);
                }
            }
            if (predicate->boundKnown) {
                boundKnown = true;
                bound = predicate->bound;
            }
        }
        if (boundKnown) {
            lengths.insert(bound);
        }
        std::set<std::vector<bool>> seen;
        std::vector<Outcomes> vectors;
        for (const bool flag : hasFlag ? std::vector<bool>{false, true} : std::vector<bool>{false}) {
            for (const std::size_t length : lengths) {
                if (boundKnown && length > bound) {
                    continue;
                }
                std::vector<bool> signature;
                Outcomes outcomes;
                for (const Predicate* predicate : entry.second) {
                    const bool value = predicate->kind == ConditionKind::Flag
                                           ? flag
                                           : compare(length, predicate->op, predicate->limit);
                    signature.push_back(value);
                    outcomes[predicate->key] = value;
                }
                if (seen.insert(signature).second) {
                    vectors.push_back(outcomes);
                }
            }
        }
        perSecret.push_back(std::move(vectors));
    }

    // The secrets are independent inputs, so every combination of per-secret
    // vectors is reachable and the total is their product.
    total = 1;
    bool overflow = false;
    for (const auto& vectors : perSecret) {
        const std::size_t count = std::max<std::size_t>(1, vectors.size());
        if (total > static_cast<std::size_t>(-1) / count) {
            total = static_cast<std::size_t>(-1);
            overflow = true;
        } else {
            total *= count;
        }
    }
    enumerated = !overflow && total <= limit;
    if (!enumerated) {
        return {};
    }
    std::vector<Outcomes> combined{Outcomes{}};
    for (const auto& vectors : perSecret) {
        std::vector<Outcomes> next;
        for (const Outcomes& prefix : combined) {
            for (const Outcomes& part : vectors) {
                Outcomes merged = prefix;
                merged.insert(part.begin(), part.end());
                next.push_back(std::move(merged));
            }
        }
        combined = std::move(next);
    }
    return combined;
}

std::string predicateText(const IfStmt& branch, const SemanticResult& semantic) {
    const auto guard = semantic.guards.find(&branch);
    std::string text = conditionToString(branch.condition);
    if (guard != semantic.guards.end()) {
        const auto root = semantic.bindings.find(guard->second.secretRootId);
        if (root != semantic.bindings.end() && root->second.name != branch.condition.subjectName) {
            text += " (a copy of secret '" + root->second.name + "')";
        }
    }
    return text;
}

void analyzeWorkflow(const WorkflowDecl& workflow, const SemanticResult& semantic,
                     const RelationalOptions& options, RelationalResult& result) {
    const Observer observer = workflow.observer;

    // Per-branch obligations, for the certificate and for pointing at the cause.
    std::vector<const IfStmt*> branches;
    collectSecretBranches(workflow.statements, semantic, branches);
    std::vector<std::size_t> failing;
    for (const IfStmt* branch : branches) {
        Builder thenBuilder(semantic, nullptr, observer);
        Builder elseBuilder(semantic, nullptr, observer);
        const Sig thenSig = thenBuilder.build(branch->thenBranch);
        const Sig elseSig = elseBuilder.build(branch->elseBranch);
        Remap left;
        Remap right;
        RelationalObligation obligation;
        obligation.workflow = workflow.name;
        obligation.guard = predicateText(*branch, semantic);
        obligation.location = branch->location;
        obligation.thenSignature = sigText(thenSig);
        obligation.elseSignature = sigText(elseSig);
        if (!thenBuilder.defined() || !elseBuilder.defined()) {
            obligation.discharged = false;
            obligation.detail = "signature undefined: " +
                                (thenBuilder.defined() ? elseBuilder.reason() : thenBuilder.reason());
        } else if (normalizedKey(thenSig, observer, left) != normalizedKey(elseSig, observer, right)) {
            obligation.discharged = false;
            obligation.detail = firstDifference(thenSig, elseSig);
        } else {
            obligation.discharged = true;
            obligation.detail = "both arms send " + obligation.thenSignature;
        }
        if (!obligation.discharged) {
            failing.push_back(result.obligations.size());
        }
        result.obligations.push_back(std::move(obligation));
    }

    // The global count of distinguishable behaviours.
    std::vector<Predicate> predicates;
    std::set<std::string> seenPredicates;
    for (const IfStmt* branch : branches) {
        const GuardFact& guard = semantic.guards.at(branch);
        Predicate predicate;
        predicate.key = predicateKey(guard, branch->condition);
        if (!seenPredicates.insert(predicate.key).second) {
            continue;
        }
        predicate.root = guard.secretRootId;
        predicate.kind = branch->condition.kind;
        predicate.op = branch->condition.op;
        predicate.limit = branch->condition.limit;
        predicate.boundKnown = guard.secretBoundKnown;
        predicate.bound = guard.secretBound;
        predicate.display = predicateText(*branch, semantic);
        predicates.push_back(predicate);
    }

    LeakageReport report;
    report.workflow = workflow.name;
    report.observer = observerName(observer);
    report.rule = relationalRuleName(RelationalRule::Content);
    report.budgetBits = workflow.leakBudgetBits;
    for (const Predicate& predicate : predicates) {
        report.predicates.push_back(predicate.display);
    }

    std::size_t total = 1;
    bool enumerated = true;
    const std::vector<Outcomes> vectors =
        feasibleOutcomes(predicates, options.maxOutcomeVectors, total, enumerated);
    report.outcomeVectors = total;
    report.enumerated = enumerated;
    bool undefinedAnywhere = false;
    std::string undefinedReason;
    if (enumerated) {
        std::map<std::string, std::string> classes;
        for (const Outcomes& outcomes : vectors) {
            Builder builder(semantic, &outcomes, observer);
            const Sig resolved = builder.build(workflow.statements);
            if (!builder.defined()) {
                undefinedAnywhere = true;
                undefinedReason = builder.reason();
            }
            Remap remap;
            const std::string key = normalizedKey(resolved, observer, remap);
            if (classes.find(key) == classes.end()) {
                classes[key] = sigText(resolved);
            }
        }
        report.classes = classes.size();
        for (const auto& entry : classes) {
            report.classSignatures.push_back(entry.second);
        }
    } else {
        // Every combination might be distinguishable.
        report.classes = total;
    }
    report.bits = report.classes <= 1 ? 0.0 : std::log2(static_cast<double>(report.classes));
    const double allowed = std::floor(std::pow(2.0, workflow.leakBudgetBits) + 1e-9);
    report.withinBudget = !undefinedAnywhere && static_cast<double>(report.classes) <= allowed;

    if (undefinedAnywhere) {
        result.diagnostics.error("E236", workflow.location,
                                 "the requests this workflow sends cannot be shown independent of "
                                 "its secrets: " + undefinedReason);
    } else if (!report.withinBudget) {
        std::ostringstream bound;
        bound.precision(3);
        bound << report.bits;
        std::ostringstream budget;
        budget.precision(3);
        budget << workflow.leakBudgetBits;
        const std::string budgetText = workflow.hasLeakBudget
                                           ? "its declared budget is " + budget.str() + " bits"
                                           : "it declares no leakage budget, so none is allowed";
        for (const std::size_t index : failing) {
            const RelationalObligation& obligation = result.obligations[index];
            result.diagnostics.error(
                "E236", obligation.location,
                "the guard '" + obligation.guard + "' depends on a secret and the two arms send " +
                    "different requests, so the " + observerName(observer) +
                    " observer can tell which arm ran; " + obligation.detail + ". then-arm sends [" +
                    obligation.thenSignature + "] and else-arm sends [" + obligation.elseSignature +
                    "]");
        }
        result.diagnostics.error("E236", workflow.location,
                                 "workflow '" + workflow.name + "' has " +
                                     std::to_string(report.classes) +
                                     " distinguishable behaviours depending on its secrets, so it "
                                     "may reveal up to " + bound.str() + " bits; " + budgetText);
    } else if (report.classes > 1) {
        std::ostringstream bound;
        bound.precision(3);
        bound << report.bits;
        result.diagnostics.warning("W238", workflow.location,
                                   "workflow '" + workflow.name + "' may reveal up to " + bound.str() +
                                       " bits about its secrets to the " + observerName(observer) +
                                       " (" + std::to_string(report.classes) +
                                       " distinguishable behaviours), within its declared budget");
    }
    result.leakage.push_back(std::move(report));
}

}  // namespace

RelationalResult RelationalAnalyzer::analyze(const Program& program,
                                             const SemanticResult& semantic) const {
    if (options_.rule == RelationalRule::Sizes) {
        return analyzeWithSizeRule(program, semantic);
    }
    if (options_.rule == RelationalRule::Bounds) {
        return analyzeWithBoundsRule(program, semantic);
    }
    RelationalResult result;
    for (const auto& workflowPointer : program.workflows) {
        if (workflowPointer) {
            analyzeWorkflow(*workflowPointer, semantic, options_, result);
        }
    }
    return result;
}

}  // namespace orchlang
