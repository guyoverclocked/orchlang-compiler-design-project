#include "relational.hpp"

#include <algorithm>
#include <sstream>

namespace orchlang {

std::string SizeTerm::text() const {
    std::ostringstream out;
    out << constant;
    for (const std::string& name : outer) {
        out << " + |" << name << '|';
    }
    for (const std::size_t index : priorResults) {
        out << " + |call#" << index << '|';
    }
    return out.str();
}

bool SignatureNode::operator==(const SignatureNode& other) const {
    if (kind != other.kind) {
        return false;
    }
    if (children.size() != other.children.size()) {
        return false;
    }
    for (std::size_t index = 0; index < children.size(); ++index) {
        if (!signaturesEqual(children[index], other.children[index])) {
            return false;
        }
    }
    switch (kind) {
        case SignatureNodeKind::Call:
            return model == other.model && inputSize == other.inputSize;
        case SignatureNodeKind::Retry:
            return repeatBound == other.repeatBound;
        case SignatureNodeKind::Branch:
            return guard == other.guard;
    }
    return false;
}

bool signaturesEqual(const Signature& left, const Signature& right) {
    if (left.size() != right.size()) {
        return false;
    }
    for (std::size_t index = 0; index < left.size(); ++index) {
        if (left[index] != right[index]) {
            return false;
        }
    }
    return true;
}

namespace {

void renderSignature(std::ostringstream& out, const Signature& signature, int depth);

void renderNode(std::ostringstream& out, const SignatureNode& node, int depth) {
    const std::string pad(static_cast<std::size_t>(depth) * 2, ' ');
    switch (node.kind) {
        case SignatureNodeKind::Call:
            out << pad << "bill(" << node.model << ", in=" << node.inputSize.text() << ")\n";
            break;
        case SignatureNodeKind::Retry:
            out << pad << "retry " << node.repeatBound << " {\n";
            if (!node.children.empty()) {
                renderSignature(out, node.children[0], depth + 1);
            }
            out << pad << "}\n";
            break;
        case SignatureNodeKind::Branch:
            out << pad << "branch " << node.guard << " {\n";
            if (node.children.size() > 0) {
                renderSignature(out, node.children[0], depth + 1);
            }
            out << pad << "} else {\n";
            if (node.children.size() > 1) {
                renderSignature(out, node.children[1], depth + 1);
            }
            out << pad << "}\n";
            break;
    }
}

void renderSignature(std::ostringstream& out, const Signature& signature, int depth) {
    if (signature.empty()) {
        out << std::string(static_cast<std::size_t>(depth) * 2, ' ') << "<no billing>\n";
        return;
    }
    for (const SignatureNode& node : signature) {
        renderNode(out, node, depth);
    }
}

// Builds the billing signature of a block.
//
// `localCalls` maps names bound by calls *inside* the region being abstracted to
// their position in the signature.  A name not in that map was bound outside the
// region, so both compared executions hold the same value for it.
class SignatureBuilder {
public:
    SignatureBuilder(const SemanticResult& semantic, SignatureResult& result)
        : semantic_(semantic), result_(result) {}

    Signature build(const Block& block);

private:
    void undefine(const std::string& reason, const SourceLocation& location) {
        if (result_.defined) {
            result_.defined = false;
            result_.reason = reason;
            result_.location = location;
        }
    }

    const SemanticResult& semantic_;
    SignatureResult& result_;
    std::vector<std::pair<std::string, std::size_t>> localCalls_;
    std::size_t callIndex_{0};
};

Signature SignatureBuilder::build(const Block& block) {
    Signature signature;
    for (const auto& statement : block) {
        if (!statement) {
            continue;
        }
        switch (statement->kind()) {
            case StmtKind::Let: {
                const auto& let = static_cast<const LetStmt&>(*statement);
                if (!let.call) {
                    break;
                }
                const auto found = semantic_.callSites.find(let.call.get());
                if (found == semantic_.callSites.end()) {
                    undefine("call site was not analysed", statement->location);
                    break;
                }
                const CallSiteFacts& site = found->second;

                SignatureNode node;
                node.kind = SignatureNodeKind::Call;
                node.model = site.modelName;
                node.location = statement->location;
                node.inputSize.constant = site.promptTemplateTokens;

                for (const ArgumentFact& argument : site.arguments) {
                    if (argument.isSecret) {
                        undefine("an argument depends on a secret, so its size is not "
                                 "guaranteed to agree across executions",
                                 statement->location);
                        continue;
                    }
                    if (argument.isLiteral) {
                        node.inputSize.constant += argument.literalTokens;
                        continue;
                    }
                    // A result produced earlier inside this region is fixed by
                    // the oracle coupling and referred to by position; anything
                    // else was bound outside and is fixed by hypothesis.
                    bool local = false;
                    for (const auto& entry : localCalls_) {
                        if (entry.first == argument.name) {
                            node.inputSize.priorResults.push_back(entry.second);
                            local = true;
                            break;
                        }
                    }
                    if (!local) {
                        node.inputSize.outer.push_back(argument.name);
                    }
                }
                std::sort(node.inputSize.outer.begin(), node.inputSize.outer.end());
                std::sort(node.inputSize.priorResults.begin(), node.inputSize.priorResults.end());

                localCalls_.push_back({let.name, callIndex_});
                ++callIndex_;
                signature.push_back(std::move(node));
                break;
            }
            case StmtKind::Retry: {
                const auto& retry = static_cast<const RetryStmt&>(*statement);
                SignatureNode node;
                node.kind = SignatureNodeKind::Retry;
                node.repeatBound = retry.bound;
                node.location = statement->location;
                node.children.push_back(build(retry.body));
                signature.push_back(std::move(node));
                break;
            }
            case StmtKind::If: {
                const auto& branch = static_cast<const IfStmt&>(*statement);
                const auto guard = semantic_.guardOwnLabels.find(&branch);
                const bool secretGuard = guard != semantic_.guardOwnLabels.end() &&
                                         guard->second.isSecret();

                Signature thenSignature = build(branch.thenBranch);
                Signature elseSignature =
                    branch.hasElse ? build(branch.elseBranch) : Signature{};

                if (secretGuard) {
                    // A nested secret branch must already have been discharged
                    // on its own; if its arms agree, either one stands for both,
                    // which is what makes the analysis compositional.
                    if (!signaturesEqual(thenSignature, elseSignature)) {
                        undefine("a nested secret-guarded branch has arms that bill differently",
                                 statement->location);
                    }
                    for (SignatureNode& node : thenSignature) {
                        signature.push_back(std::move(node));
                    }
                    break;
                }

                // A public guard sees the same public data in both executions,
                // so both take the same arm; the arms need not agree.
                SignatureNode node;
                node.kind = SignatureNodeKind::Branch;
                node.guard = conditionToString(branch.condition);
                node.location = statement->location;
                node.children.push_back(std::move(thenSignature));
                node.children.push_back(std::move(elseSignature));
                signature.push_back(std::move(node));
                break;
            }
            case StmtKind::Reclassify: {
                // Relabelling copies a value, so the new name denotes the same
                // quantity.  Inherit the source's position if it had one.
                const auto& reclassify = static_cast<const ReclassifyStmt&>(*statement);
                for (const auto& entry : localCalls_) {
                    if (entry.first == reclassify.sourceName) {
                        localCalls_.push_back({reclassify.name, entry.second});
                        break;
                    }
                }
                break;
            }
            case StmtKind::Input:
            case StmtKind::Secret:
            case StmtKind::Model:
            case StmtKind::Prompt:
            case StmtKind::Tool:
            case StmtKind::Require:
            case StmtKind::Emit:
            case StmtKind::Output:
                // None of these reaches a model, so none of them bills.
                break;
        }
    }
    return signature;
}

SignatureResult signatureOf(const Block& block, const SemanticResult& semantic) {
    SignatureResult result;
    SignatureBuilder builder(semantic, result);
    result.signature = builder.build(block);
    return result;
}

// Walks a workflow discharging the relational obligation at every
// secret-guarded branch.
class Checker {
public:
    Checker(const SemanticResult& semantic, RelationalResult& result, std::string workflow)
        : semantic_(semantic), result_(result), workflow_(std::move(workflow)) {}

    void block(const Block& statements);

private:
    const SemanticResult& semantic_;
    RelationalResult& result_;
    std::string workflow_;
};

void Checker::block(const Block& statements) {
    for (const auto& statement : statements) {
        if (!statement) {
            continue;
        }
        if (statement->kind() == StmtKind::Retry) {
            block(static_cast<const RetryStmt&>(*statement).body);
            continue;
        }
        if (statement->kind() != StmtKind::If) {
            continue;
        }
        const auto& branch = static_cast<const IfStmt&>(*statement);

        // Check the arms first, so a nested obligation is reported at its own
        // location rather than being folded into the enclosing one.
        block(branch.thenBranch);
        block(branch.elseBranch);

        const auto guard = semantic_.guardOwnLabels.find(&branch);
        if (guard == semantic_.guardOwnLabels.end() || !guard->second.isSecret()) {
            continue;
        }

        const std::string guardText = conditionToString(branch.condition);
        const SignatureResult thenSide = signatureOf(branch.thenBranch, semantic_);
        const SignatureResult elseSide =
            branch.hasElse ? signatureOf(branch.elseBranch, semantic_) : SignatureResult{};

        RelationalObligation obligation;
        obligation.workflow = workflow_;
        obligation.guard = guardText;
        obligation.location = statement->location;

        if (!thenSide.defined || !elseSide.defined) {
            const std::string why = thenSide.defined ? elseSide.reason : thenSide.reason;
            obligation.discharged = false;
            obligation.detail = "signature undefined: " + why;
            result_.diagnostics.error(
                "E236", statement->location,
                "this branch is guarded by a secret and its billing cannot be shown independent "
                "of that secret (" + why + ")");
        } else if (!signaturesEqual(thenSide.signature, elseSide.signature)) {
            obligation.discharged = false;
            std::ostringstream detail;
            detail << "signatures differ\n  then:\n" << signatureText(thenSide.signature)
                   << "  else:\n" << signatureText(elseSide.signature);
            obligation.detail = detail.str();

            std::ostringstream message;
            message << "this branch is guarded by a secret and its two arms bill differently, so "
                       "the bill reveals the secret; then-arm bills ["
                    << signatureText(thenSide.signature) << "] and else-arm bills ["
                    << signatureText(elseSide.signature) << "]";
            std::string text = message.str();
            for (char& character : text) {
                if (character == '\n') {
                    character = ' ';
                }
            }
            result_.diagnostics.error("E236", statement->location, text);
        } else {
            obligation.discharged = true;
            obligation.detail = "both arms bill " + signatureText(thenSide.signature);
        }
        result_.obligations.push_back(std::move(obligation));
    }
}

}  // namespace

std::string signatureText(const Signature& signature) {
    std::ostringstream out;
    if (signature.empty()) {
        return "nothing";
    }
    bool first = true;
    for (const SignatureNode& node : signature) {
        if (!first) {
            out << "; ";
        }
        first = false;
        switch (node.kind) {
            case SignatureNodeKind::Call:
                out << node.model << "(in=" << node.inputSize.text() << ")";
                break;
            case SignatureNodeKind::Retry:
                out << "retry " << node.repeatBound << "{"
                    << (node.children.empty() ? std::string("nothing")
                                              : signatureText(node.children[0]))
                    << "}";
                break;
            case SignatureNodeKind::Branch:
                out << "if " << node.guard << "{"
                    << (node.children.size() > 0 ? signatureText(node.children[0])
                                                 : std::string("nothing"))
                    << "}else{"
                    << (node.children.size() > 1 ? signatureText(node.children[1])
                                                 : std::string("nothing"))
                    << "}";
                break;
        }
    }
    return out.str();
}

RelationalResult RelationalAnalyzer::analyze(const Program& program,
                                             const SemanticResult& semantic) const {
    RelationalResult result;
    for (const auto& workflowPointer : program.workflows) {
        if (!workflowPointer) {
            continue;
        }
        Checker checker(semantic, result, workflowPointer->name);
        checker.block(workflowPointer->statements);
    }
    return result;
}

}  // namespace orchlang
