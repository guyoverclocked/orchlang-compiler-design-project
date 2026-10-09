#include "certificate.hpp"

#include <iomanip>
#include <cmath>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <cstdint>
#include <array>
#include <vector>

namespace orchlang {

namespace {

std::string escape(const std::string& text) {
    std::ostringstream out;
    const char hex[] = "0123456789abcdef";
    for (const unsigned char character : text) {
        switch (character) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (character < 0x20) {
                    out << "\\u00" << hex[(character >> 4) & 0xf] << hex[character & 0xf];
                } else {
                    out << static_cast<char>(character);
                }
                break;
        }
    }
    return out.str();
}

std::string quoted(const std::string& text) { return "\"" + escape(text) + "\""; }

const char* exprKindName(ExprKind kind) {
    switch (kind) {
        case ExprKind::Identifier: return "identifier";
        case ExprKind::StringLiteral: return "text";
        case ExprKind::IntegerLiteral: return "integer";
        case ExprKind::DecimalLiteral: return "decimal";
        case ExprKind::BooleanLiteral: return "boolean";
        case ExprKind::Call: return "call";
    }
    return "unknown";
}

std::string money(double value) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(6) << value;
    return out.str();
}

std::string preciseNumber(double value) {
    if (!std::isfinite(value)) {
        return "null";
    }
    std::ostringstream out;
    out << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return out.str();
}

std::string sha256(const std::string& bytes) {
    static constexpr std::array<std::uint32_t, 64> constants = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
        0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
        0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
        0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
        0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
        0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    std::array<std::uint32_t, 8> state = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                          0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    std::vector<std::uint8_t> message(bytes.begin(), bytes.end());
    const std::uint64_t bitLength = static_cast<std::uint64_t>(message.size()) * 8;
    message.push_back(0x80);
    while (message.size() % 64 != 56) {
        message.push_back(0);
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
        message.push_back(static_cast<std::uint8_t>((bitLength >> shift) & 0xff));
    }

    const auto rotateRight = [](std::uint32_t value, unsigned count) {
        return (value >> count) | (value << (32 - count));
    };
    for (std::size_t offset = 0; offset < message.size(); offset += 64) {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16; ++index) {
            const std::size_t base = offset + index * 4;
            words[index] = (static_cast<std::uint32_t>(message[base]) << 24) |
                           (static_cast<std::uint32_t>(message[base + 1]) << 16) |
                           (static_cast<std::uint32_t>(message[base + 2]) << 8) |
                           static_cast<std::uint32_t>(message[base + 3]);
        }
        for (std::size_t index = 16; index < words.size(); ++index) {
            const std::uint32_t s0 = rotateRight(words[index - 15], 7) ^
                                     rotateRight(words[index - 15], 18) ^
                                     (words[index - 15] >> 3);
            const std::uint32_t s1 = rotateRight(words[index - 2], 17) ^
                                     rotateRight(words[index - 2], 19) ^
                                     (words[index - 2] >> 10);
            words[index] = words[index - 16] + s0 + words[index - 7] + s1;
        }

        std::uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
        std::uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
        for (std::size_t index = 0; index < words.size(); ++index) {
            const std::uint32_t sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
            const std::uint32_t choice = (e & f) ^ (~e & g);
            const std::uint32_t temp1 = h + sum1 + choice + constants[index] + words[index];
            const std::uint32_t sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
            const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = sum0 + majority;
            h = g; g = f; f = e; e = d + temp1;
            d = c; c = b; b = a; a = temp1 + temp2;
        }
        state[0] += a; state[1] += b; state[2] += c; state[3] += d;
        state[4] += e; state[5] += f; state[6] += g; state[7] += h;
    }

    std::ostringstream result;
    result << std::hex << std::setfill('0');
    for (const std::uint32_t word : state) {
        result << std::setw(8) << word;
    }
    return result.str();
}

std::string confidentialityName(const Label& label) { return label.isSecret() ? "secret" : "public"; }
std::string integrityName(const Label& label) { return label.isUntrusted() ? "untrusted" : "trusted"; }

// The bindings of one workflow, in declaration order, with the label and bound
// the type system settled on.  Scopes are matched by name prefix so branch and
// retry bodies are reported alongside the workflow they belong to.
struct BindingView {
    std::string scope;
    std::string name;
    std::string kind;
    std::string type;
    Label label;
    bool boundKnown{false};
    std::size_t bound{0};
};

std::vector<BindingView> bindingsOf(const SemanticResult& semantic, const std::string& workflow) {
    const std::string prefix = "workflow:" + workflow;
    std::vector<BindingView> bindings;
    for (const Scope& scope : semantic.symbols.scopes()) {
        if (scope.name.compare(0, prefix.size(), prefix) != 0) {
            continue;
        }
        if (scope.name.size() > prefix.size() && scope.name[prefix.size()] != ':') {
            continue;
        }
        for (const auto& entry : scope.symbols) {
            const Symbol& symbol = entry.second;
            bindings.push_back({scope.name, symbol.name, symbolKindName(symbol.kind),
                                typeName(symbol.type), symbol.label, symbol.tokenBoundKnown,
                                symbol.tokenBound});
        }
    }
    return bindings;
}

void collectCallFacts(const Block& block, const SemanticResult& semantic,
                      std::vector<const CallSiteFacts*>& calls) {
    for (const auto& statement : block) {
        if (!statement) {
            continue;
        }
        if (statement->kind() == StmtKind::Let) {
            const auto& let = static_cast<const LetStmt&>(*statement);
            if (let.call) {
                const auto found = semantic.callSites.find(let.call.get());
                if (found != semantic.callSites.end()) {
                    calls.push_back(&found->second);
                }
            }
        } else if (statement->kind() == StmtKind::If) {
            const auto& branch = static_cast<const IfStmt&>(*statement);
            collectCallFacts(branch.thenBranch, semantic, calls);
            collectCallFacts(branch.elseBranch, semantic, calls);
        } else if (statement->kind() == StmtKind::Retry) {
            collectCallFacts(static_cast<const RetryStmt&>(*statement).body, semantic, calls);
        }
    }
}

std::string contentLabelName(const Label& label) {
    return std::string(confidentialityName(label)) + "," + integrityName(label);
}

const WorkflowCost* costOf(const CostResult& cost, const std::string& workflow) {
    for (const WorkflowCost& candidate : cost.workflows) {
        if (candidate.name == workflow) {
            return &candidate;
        }
    }
    return nullptr;
}

}  // namespace

std::string printCertificate(const Program& program, const SemanticResult& semantic,
                             const CostResult& cost, const ProgramIR& ir,
                             const RelationalResult& relational,
                             const std::string& sourceBytes) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"format\": \"orchlang-safety-certificate\",\n";
    out << "  \"version\": 3,\n";
    out << "  \"source_sha256\": "
        << (sourceBytes.empty() ? "null" : quoted(sha256(sourceBytes))) << ",\n";
    out << "  \"assumptions\": {\n";
    out << "    \"chars_per_token\": " << semantic.options.charsPerToken << ",\n";
    out << "    \"input_accounting\": \"Each call adds ceil(UTF-8 template bytes / chars_per_token) "
           "to the separately declared argument bounds.\",\n";
    out << "    \"output_assumption\": \"The oracle emits no more than the resolved model contract's "
           "declared max_tokens cap.\",\n";
    out << "    \"input_assumption\": \"For every complete request, target-model input usage is at most "
           "the sum of the template estimate and declared argument bounds. chars_per_token is a "
           "UTF-8 byte divisor; provider tokenizers, request envelopes, and tokenization boundary "
           "effects are not modeled.\",\n";
    out << "    \"note\": \"These are explicit abstract accounting assumptions, not a guarantee about "
           "real provider billing.\"\n";
    out << "  },\n";
    out << "  \"workflows\": [\n";

    for (std::size_t index = 0; index < program.workflows.size(); ++index) {
        const WorkflowDecl* workflow = program.workflows[index].get();
        if (!workflow) {
            continue;
        }
        const WorkflowCost* workflowCost = costOf(cost, workflow->name);
        bool declassificationPresent = false;
        for (const ReclassificationSite& site : semantic.reclassifications) {
            if (site.workflow == workflow->name && !site.endorsement) {
                declassificationPresent = true;
                break;
            }
        }
        bool workflowObligationsDischarged = true;
        for (const RelationalObligation& obligation : relational.obligations) {
            if (obligation.workflow == workflow->name && !obligation.discharged) {
                workflowObligationsDischarged = false;
                break;
            }
        }
        const bool billingNoninterferenceClaimed = !declassificationPresent &&
                                                    relational.success() &&
                                                    workflowObligationsDischarged;
        out << "    {\n";
        out << "      \"name\": " << quoted(workflow->name) << ",\n";
        out << "      \"budget_tokens\": " << workflow->budget << ",\n";
        out << "      \"security_contract\": {\n";
        out << "        \"declassification_present\": "
            << (declassificationPresent ? "true" : "false") << ",\n";
        out << "        \"billing_noninterference_claimed\": "
            << (billingNoninterferenceClaimed ? "true" : "false") << ",\n";
        out << "        \"guarantee_scope\": {\n";
        out << "          \"property\": \"paired billing-trace equality under the stated abstract model\",\n";
        out << "          \"oracle_coupling\": \"Paired executions share abstract responses under "
               "Ω(M,k,Q) when resolved contract M, per-contract ordinal k, retry outcomes, and the "
               "complete modeled request Q match. The default ordinal mock ignores Q in its output "
               "projection; --request-sensitive-oracle adds decoded template bytes, ordered literal "
               "bytes, and identifier Value(tokens,flag) fields to Q. This models no real provider "
               "request text.\",\n";
        out << "          \"token_usage\": \"Input use follows the summed UTF-8 template and declared "
               "argument bounds; output use respects the resolved contract's max_tokens cap.\",\n";
        out << "          \"relational_obligations\": \"A discharged entry records a local structural "
               "request-trace comparison. It is not by itself a universal whole-workflow claim.\",\n";
        out << "          \"declassification\": "
            << quoted(declassificationPresent
                          ? "This workflow contains declassification, so this certificate makes no "
                            "unconditional billing noninterference claim. A release-aware argument "
                            "would require paired executions to agree on all released values."
                          : "This workflow contains no declassification; the claim is still conditional "
                            "on the stated shared-oracle and abstract token-accounting assumptions.")
            << "\n";
        out << "        }\n";
        out << "      },\n";

        out << "      \"bound\": {";
        if (workflowCost) {
            out << "\"guaranteed_tokens\": " << workflowCost->bound.guaranteed
                << ", \"estimated_tokens\": " << workflowCost->bound.estimated
                << ", \"total_tokens\": " << workflowCost->bound.total()
                << ", \"component_sum_tokens\": " << workflowCost->bound.componentSum()
                << ", \"within_budget\": " << (workflowCost->withinBudget() ? "true" : "false")
                << ", \"defined\": " << (workflowCost->bound.defined ? "true" : "false")
                << ", \"cost\": " << preciseNumber(workflowCost->bound.money)
                << ", \"cost_complete\": " << (workflowCost->bound.moneyComplete ? "true" : "false");
        }
        out << "},\n";

        out << "      \"derivation\": [\n";
        if (workflowCost) {
            for (std::size_t step = 0; step < workflowCost->derivation.size(); ++step) {
                const DerivationStep& entry = workflowCost->derivation[step];
                out << "        {\"depth\": " << entry.depth << ", \"rule\": " << quoted(entry.rule)
                    << ", \"detail\": " << quoted(entry.detail)
                    << ", \"guaranteed_tokens\": " << entry.bound.guaranteed
                    << ", \"estimated_tokens\": " << entry.bound.estimated
                    << ", \"total_tokens\": " << entry.bound.total()
                    << ", \"line\": " << entry.location.line << "}"
                    << (step + 1 == workflowCost->derivation.size() ? "" : ",") << '\n';
            }
        }
        out << "      ],\n";

        std::vector<const CallSiteFacts*> calls;
        collectCallFacts(workflow->statements, semantic, calls);
        out << "      \"call_facts\": [\n";
        for (std::size_t callIndex = 0; callIndex < calls.size(); ++callIndex) {
            const CallSiteFacts& call = *calls[callIndex];
            out << "        {\"id\": " << call.id
                << ", \"location\": {\"file\": " << quoted(call.location.file)
                << ", \"line\": " << call.location.line
                << ", \"column\": " << call.location.column << "}"
                << ", \"result\": " << quoted(call.resultName)
                << ", \"result_value_id\": " << call.resultValueIdentity
                << ", \"prompt\": " << quoted(call.promptName)
                << ", \"model_alias\": " << quoted(call.modelAlias)
                << ", \"model_contract\": ";
            if (call.resolvedModel) {
                const ModelContract& model = *call.resolvedModel;
                out << "{\"provider\": " << quoted(model.provider)
                    << ", \"model\": " << quoted(model.modelName)
                    << ", \"max_tokens\": " << model.maxTokens
                    << ", \"has_unit_price\": " << (model.hasUnitPrice ? "true" : "false")
                    << ", \"unit_price\": " << preciseNumber(model.unitPrice)
                    << ", \"stable_key\": " << quoted(model.stableKey())
                    << ", \"tokenizer_identity\": " << quoted(model.tokenizerIdentity()) << "}";
            } else {
                out << "null";
            }
            out << ", \"template_text\": " << quoted(call.promptTemplateText)
                << ", \"template_tokens\": " << call.promptTemplateTokens
                << ", \"arguments\": [";
            for (std::size_t argumentIndex = 0; argumentIndex < call.arguments.size();
                 ++argumentIndex) {
                const ArgumentFact& argument = call.arguments[argumentIndex];
                if (argumentIndex != 0) {
                    out << ", ";
                }
                out << "{\"position\": " << argumentIndex
                    << ", \"kind\": " << quoted(argument.isLiteral ? "literal" : "value")
                    << ", \"literal_expr_kind\": ";
                if (argument.isLiteral) {
                    out << quoted(exprKindName(argument.literalKind));
                } else {
                    out << "null";
                }
                out << ", \"name\": " << quoted(argument.name)
                    << ", \"literal_text\": ";
                if (argument.isLiteral) {
                    out << quoted(argument.literalText);
                } else {
                    out << "null";
                }
                out << ", \"binding_id\": " << argument.bindingIdentity
                    << ", \"value_id\": " << argument.valueIdentity
                    << ", \"content_label\": " << quoted(contentLabelName(argument.contentLabel))
                    << ", \"token_bound\": ";
                if (argument.tokenBoundKnown) {
                    out << argument.tokenBound;
                } else {
                    out << "null";
                }
                out << ", \"token_bound_tokenizer\": ";
                if (argument.tokenBoundTokenizer.empty()) {
                    out << "null";
                } else {
                    out << quoted(argument.tokenBoundTokenizer);
                }
                out << "}";
            }
            out << "]}" << (callIndex + 1 == calls.size() ? "" : ",") << '\n';
        }
        out << "      ],\n";

        const std::vector<BindingView> bindings = bindingsOf(semantic, workflow->name);
        out << "      \"bindings\": [\n";
        for (std::size_t binding = 0; binding < bindings.size(); ++binding) {
            const BindingView& view = bindings[binding];
            out << "        {\"scope\": " << quoted(view.scope) << ", \"name\": " << quoted(view.name)
                << ", \"kind\": " << quoted(view.kind) << ", \"type\": " << quoted(view.type)
                << ", \"confidentiality\": " << quoted(confidentialityName(view.label))
                << ", \"integrity\": " << quoted(integrityName(view.label))
                << ", \"token_bound\": ";
            if (view.boundKnown) {
                out << view.bound;
            } else {
                out << "null";
            }
            out << "}" << (binding + 1 == bindings.size() ? "" : ",") << '\n';
        }
        out << "      ],\n";

        out << "      \"reclassifications\": [\n";
        std::vector<const ReclassificationSite*> sites;
        for (const ReclassificationSite& site : semantic.reclassifications) {
            if (site.workflow == workflow->name) {
                sites.push_back(&site);
            }
        }
        for (std::size_t site = 0; site < sites.size(); ++site) {
            const ReclassificationSite& entry = *sites[site];
            out << "        {\"operation\": " << quoted(entry.endorsement ? "endorse" : "declassify")
                << ", \"source\": " << quoted(entry.sourceName)
                << ", \"result\": " << quoted(entry.resultName)
                << ", \"from\": " << quoted(labelName(entry.from))
                << ", \"to\": " << quoted(labelName(entry.to))
                << ", \"justification\": " << quoted(entry.reason)
                << ", \"line\": " << entry.location.line << "}"
                << (site + 1 == sites.size() ? "" : ",") << '\n';
        }
        out << "      ],\n";

        out << "      \"relational_obligations\": [\n";
        std::vector<const RelationalObligation*> obligations;
        for (const RelationalObligation& obligation : relational.obligations) {
            if (obligation.workflow == workflow->name) {
                obligations.push_back(&obligation);
            }
        }
        for (std::size_t index2 = 0; index2 < obligations.size(); ++index2) {
            const RelationalObligation& entry = *obligations[index2];
            out << "        {\"guard\": " << quoted(entry.guard)
                << ", \"discharged\": " << (entry.discharged ? "true" : "false")
                << ", \"detail\": " << quoted(entry.detail)
                << ", \"line\": " << entry.location.line << "}"
                << (index2 + 1 == obligations.size() ? "" : ",") << '\n';
        }
        out << "      ],\n";

        out << "      \"sinks\": [\n";
        std::vector<const IRNode*> sinks;
        for (const WorkflowIR& lowered : ir.workflows) {
            if (lowered.workflowName != workflow->name) {
                continue;
            }
            for (const IRNode& node : lowered.nodes) {
                if (node.kind == IRNodeKind::Emit) {
                    sinks.push_back(&node);
                }
            }
        }
        for (std::size_t sink = 0; sink < sinks.size(); ++sink) {
            out << "        {\"tool\": " << quoted(sinks[sink]->name)
                << ", \"region\": " << quoted(sinks[sink]->region)
                << ", \"line\": " << sinks[sink]->location.line << "}"
                << (sink + 1 == sinks.size() ? "" : ",") << '\n';
        }
        out << "      ]\n";
        out << "    }" << (index + 1 == program.workflows.size() ? "" : ",") << '\n';
    }

    out << "  ]\n}\n";
    return out.str();
}

std::string printCertificateSummary(const CostResult& cost, const SemanticResult& semantic) {
    std::ostringstream out;
    for (const WorkflowCost& workflow : cost.workflows) {
        out << workflow.name << ":\n";
        out << "  token bound   " << workflow.bound.total() << " / budget " << workflow.budget
            << "\n";
        out << "  components    output <= " << workflow.bound.guaranteed << ", input <= "
            << workflow.bound.estimated << " @ " << semantic.options.charsPerToken
            << " chars/token";
        if (workflow.bound.componentSum() != workflow.bound.total()) {
            out << "  (sum " << workflow.bound.componentSum()
                << " exceeds the total bound; the two maxima fall on different branches)";
        }
        out << '\n';
        if (workflow.bound.money > 0.0) {
            out << "  cost bound    " << money(workflow.bound.money)
                << (workflow.bound.moneyComplete ? "" : "  (partial: some models declare no price)")
                << '\n';
        }

        std::size_t secrets = 0;
        std::size_t untrusted = 0;
        for (const BindingView& binding : bindingsOf(semantic, workflow.name)) {
            if (binding.label.isSecret()) {
                ++secrets;
            }
            if (binding.label.isUntrusted()) {
                ++untrusted;
            }
        }
        out << "  labels        " << secrets << " secret, " << untrusted << " untrusted\n";

        std::size_t declassifications = 0;
        std::size_t endorsements = 0;
        for (const ReclassificationSite& site : semantic.reclassifications) {
            if (site.workflow != workflow.name) {
                continue;
            }
            if (site.endorsement) {
                ++endorsements;
            } else {
                ++declassifications;
            }
        }
        if (declassifications != 0 || endorsements != 0) {
            out << "  escape hatches " << declassifications << " declassify, " << endorsements
                << " endorse (each justified in the certificate)\n";
        }
    }
    return out.str();
}

}  // namespace orchlang
