#include "relational.hpp"

#include <algorithm>
#include <iomanip>
#include <map>
#include <sstream>
#include <utility>

namespace orchlang {

namespace {

const char* literalKindName(ExprKind kind) {
    switch (kind) {
        case ExprKind::StringLiteral: return "text";
        case ExprKind::IntegerLiteral: return "integer";
        case ExprKind::DecimalLiteral: return "decimal";
        case ExprKind::BooleanLiteral: return "boolean";
        case ExprKind::Identifier: return "identifier";
        case ExprKind::Call: return "call";
    }
    return "unknown";
}

}  // namespace

std::string RequestAtom::text() const {
    std::ostringstream out;
    switch (kind) {
        case RequestAtomKind::Literal:
            out << "literal(" << literalKindName(literalKind) << ','
                << std::quoted(literal) << ')';
            break;
        case RequestAtomKind::OuterValue:
            out << "outer(" << (literal.empty() ? std::string("value") : literal)
                << "#" << identity << ')';
            break;
        case RequestAtomKind::PriorResult:
            out << "result(" << identity << ')';
            break;
    }
    return out.str();
}

bool SignatureNode::operator==(const SignatureNode& other) const {
    if (kind != other.kind || children.size() != other.children.size()) {
        return false;
    }
    for (std::size_t index = 0; index < children.size(); ++index) {
        if (!signaturesEqual(children[index], other.children[index])) {
            return false;
        }
    }
    switch (kind) {
        case SignatureNodeKind::Call:
            return modelContract == other.modelContract &&
                   promptTemplateText == other.promptTemplateText && arguments == other.arguments;
        case SignatureNodeKind::Retry:
            return repeatBound == other.repeatBound;
        case SignatureNodeKind::Branch:
            return guardTerm == other.guardTerm;
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
            out << pad << "bill(";
            if (node.modelContract) {
                out << node.modelContract->displayName();
            } else {
                out << "<unresolved-model:" << node.modelAlias << '>';
            }
            out << ", template=" << std::quoted(node.promptTemplateText) << ", args=[";
            for (std::size_t index = 0; index < node.arguments.size(); ++index) {
                if (index != 0) {
                    out << ", ";
                }
                out << node.arguments[index].text();
            }
            out << "])\n";
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

// Builds a signature of exact request content. The environment is copied when
// entering a branch/retry body, so child-scope bindings never leak into sibling
// arms or later statements. The monotonically assigned call positions are
// local to this signature and align corresponding results across secret arms.
class SignatureBuilder {
public:
    explicit SignatureBuilder(const SemanticResult& semantic, SignatureResult& result)
        : semantic_(semantic), result_(result) {}

    Signature build(const Block& block) {
        std::map<std::size_t, std::size_t> priorResults;
        std::size_t nextPosition = 0;
        return build(block, priorResults, nextPosition);
    }

private:
    using ResultEnvironment = std::map<std::size_t, std::size_t>;

    void undefine(const std::string& reason, const SourceLocation& location) {
        if (result_.defined) {
            result_.defined = false;
            result_.reason = reason;
            result_.location = location;
        }
    }

    RequestAtom atomForValue(std::size_t valueIdentity, const std::string& name,
                             const ResultEnvironment& environment) const {
        const auto prior = environment.find(valueIdentity);
        if (prior != environment.end()) {
            return {RequestAtomKind::PriorResult, name, prior->second};
        }
        return {RequestAtomKind::OuterValue, name, valueIdentity};
    }

    static std::size_t saturatingAdd(std::size_t left, std::size_t right) {
        const std::size_t maximum = static_cast<std::size_t>(-1);
        return right > maximum - left ? maximum : left + right;
    }

    static std::size_t saturatingMultiply(std::size_t value, std::size_t factor) {
        const std::size_t maximum = static_cast<std::size_t>(-1);
        return value != 0 && factor > maximum / value ? maximum : value * factor;
    }

    GuardTerm guardFor(const IfStmt& branch, const ResultEnvironment& environment) {
        GuardTerm term;
        term.kind = branch.condition.kind;
        term.op = branch.condition.op;
        term.limit = branch.condition.limit;
        const auto facts = semantic_.branchGuards.find(&branch);
        if (facts == semantic_.branchGuards.end() || !facts->second.resolved) {
            undefine("the branch guard binding was not resolved", branch.location);
            return term;
        }
        term.subject = atomForValue(facts->second.valueIdentity,
                                    branch.condition.subjectName, environment);
        return term;
    }

    Signature build(const Block& block, ResultEnvironment environment,
                    std::size_t& nextPosition) {
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
                    node.modelContract = site.resolvedModel;
                    node.modelAlias = site.modelAlias;
                    node.promptTemplateText = site.promptTemplateText;
                    node.location = statement->location;
                    if (!site.resolvedModel) {
                        undefine("the call has no resolved model contract", statement->location);
                    }
                    for (const ArgumentFact& argument : site.arguments) {
                        if (argument.isSecret) {
                            undefine("an argument contains secret data, so its request may differ "
                                     "across executions",
                                     statement->location);
                            continue;
                        }
                        if (argument.isLiteral) {
                            node.arguments.push_back(
                                {RequestAtomKind::Literal, argument.literalText, 0,
                                 argument.literalKind});
                        } else {
                            node.arguments.push_back(atomForValue(
                                argument.valueIdentity, argument.name, environment));
                        }
                    }
                    signature.push_back(std::move(node));

                    const auto resultIdentity =
                        semantic_.letResultValueIdentities.find(&let);
                    if (resultIdentity == semantic_.letResultValueIdentities.end()) {
                        undefine("the call result binding was not resolved", statement->location);
                    } else {
                        environment[resultIdentity->second] = nextPosition;
                    }
                    ++nextPosition;
                    break;
                }
                case StmtKind::Retry: {
                    const auto& retry = static_cast<const RetryStmt&>(*statement);
                    SignatureNode node;
                    node.kind = SignatureNodeKind::Retry;
                    node.repeatBound = retry.bound;
                    node.location = statement->location;
                    const std::size_t firstPosition = nextPosition;
                    std::size_t afterOneAttempt = firstPosition;
                    node.children.push_back(build(retry.body, environment, afterOneAttempt));
                    const std::size_t positionsPerAttempt = afterOneAttempt - firstPosition;
                    nextPosition = saturatingAdd(
                        firstPosition, saturatingMultiply(positionsPerAttempt, retry.bound));
                    signature.push_back(std::move(node));
                    break;
                }
                case StmtKind::If: {
                    const auto& branch = static_cast<const IfStmt&>(*statement);
                    const auto guard = semantic_.branchGuards.find(&branch);
                    if (guard == semantic_.branchGuards.end() || !guard->second.resolved) {
                        undefine("the branch guard binding was not resolved", statement->location);
                        break;
                    }

                    // Alternatives start at the same abstract call position.
                    // The enclosing sequence advances by the larger arm, so a
                    // corresponding post-branch call has one identity on both
                    // paths and declarations still remain arm-local.
                    const std::size_t branchStart = nextPosition;
                    std::size_t afterThen = branchStart;
                    Signature thenSignature = build(branch.thenBranch, environment, afterThen);
                    std::size_t afterElse = branchStart;
                    Signature elseSignature = branch.hasElse
                        ? build(branch.elseBranch, environment, afterElse)
                        : Signature{};
                    nextPosition = std::max(afterThen, afterElse);

                    if (guard->second.contentLabel.isSecret()) {
                        // A secret predicate is allowed only when its own arms
                        // have the same billing structure. This keeps the
                        // check compositional inside a larger secret arm.
                        if (!signaturesEqual(thenSignature, elseSignature)) {
                            undefine("a nested secret-guarded branch has arms that bill differently",
                                     statement->location);
                        }
                        for (SignatureNode& node : thenSignature) {
                            signature.push_back(std::move(node));
                        }
                        break;
                    }

                    // Public data and corresponding model results are equal in
                    // the paired executions. Preserve the branch predicate by
                    // lexical value identity, not its source spelling.
                    SignatureNode node;
                    node.kind = SignatureNodeKind::Branch;
                    node.guard = conditionToString(branch.condition);
                    node.guardTerm = guardFor(branch, environment);
                    node.location = statement->location;
                    node.children.push_back(std::move(thenSignature));
                    node.children.push_back(std::move(elseSignature));
                    signature.push_back(std::move(node));
                    break;
                }
                case StmtKind::Reclassify:
                case StmtKind::Input:
                case StmtKind::Secret:
                case StmtKind::Model:
                case StmtKind::Prompt:
                case StmtKind::Tool:
                case StmtKind::Require:
                case StmtKind::Emit:
                case StmtKind::Output:
                    // None of these introduces a billable model request.
                    break;
            }
        }
        return signature;
    }

    const SemanticResult& semantic_;
    SignatureResult& result_;
};

SignatureResult signatureOf(const Block& block, const SemanticResult& semantic) {
    SignatureResult result;
    SignatureBuilder builder(semantic, result);
    result.signature = builder.build(block);
    return result;
}

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
        block(branch.thenBranch);
        block(branch.elseBranch);

        const auto guard = semantic_.branchGuards.find(&branch);
        if (guard == semantic_.branchGuards.end() || !guard->second.resolved ||
            !guard->second.contentLabel.isSecret()) {
            continue;
        }

        const std::string guardText = conditionToString(branch.condition);
        const SignatureResult thenSide = signatureOf(branch.thenBranch, semantic_);
        const SignatureResult elseSide = branch.hasElse
            ? signatureOf(branch.elseBranch, semantic_)
            : SignatureResult{};

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
                "this branch is guarded by secret data and its billing cannot be shown independent "
                "of that data (" + why + ")");
        } else if (!signaturesEqual(thenSide.signature, elseSide.signature)) {
            obligation.discharged = false;
            std::ostringstream detail;
            detail << "signatures differ\n  then:\n" << signatureText(thenSide.signature)
                   << "  else:\n" << signatureText(elseSide.signature);
            obligation.detail = detail.str();

            std::ostringstream message;
            message << "this branch is guarded by secret data and its two arms have different "
                       "billing contracts or request content; then-arm ["
                    << signatureText(thenSide.signature) << "] and else-arm ["
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
            obligation.detail = "both arms have identical request and billing contracts: " +
                               signatureText(thenSide.signature);
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
                if (node.modelContract) {
                    out << node.modelContract->displayName();
                } else {
                    out << "<unresolved-model:" << node.modelAlias << '>';
                }
                out << " request(template=" << std::quoted(node.promptTemplateText) << ", args=[";
                for (std::size_t index = 0; index < node.arguments.size(); ++index) {
                    if (index != 0) {
                        out << ", ";
                    }
                    out << node.arguments[index].text();
                }
                out << "])";
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
