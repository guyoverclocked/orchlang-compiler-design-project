#include "certificate.hpp"

#include <iomanip>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace orchlang {

namespace {

std::string escape(const std::string& text) {
    std::ostringstream out;
    for (const char character : text) {
        switch (character) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << character; break;
        }
    }
    return out.str();
}

std::string quoted(const std::string& text) { return "\"" + escape(text) + "\""; }

std::string money(double value) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(6) << value;
    return out.str();
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
                             const CostResult& cost, const ProgramIR& ir) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"format\": \"orchlang-safety-certificate\",\n";
    out << "  \"version\": 1,\n";
    out << "  \"assumptions\": {\n";
    out << "    \"chars_per_token\": " << semantic.options.charsPerToken << ",\n";
    out << "    \"note\": \"The guaranteed component needs no tokenization assumption; the "
           "estimated component is sound only if the deployed tokenizer emits at most one token "
           "per chars_per_token characters.\"\n";
    out << "  },\n";
    out << "  \"workflows\": [\n";

    for (std::size_t index = 0; index < program.workflows.size(); ++index) {
        const WorkflowDecl* workflow = program.workflows[index].get();
        if (!workflow) {
            continue;
        }
        const WorkflowCost* workflowCost = costOf(cost, workflow->name);
        out << "    {\n";
        out << "      \"name\": " << quoted(workflow->name) << ",\n";
        out << "      \"budget_tokens\": " << workflow->budget << ",\n";

        out << "      \"bound\": {";
        if (workflowCost) {
            out << "\"guaranteed_tokens\": " << workflowCost->bound.guaranteed
                << ", \"estimated_tokens\": " << workflowCost->bound.estimated
                << ", \"total_tokens\": " << workflowCost->bound.total()
                << ", \"within_budget\": " << (workflowCost->withinBudget() ? "true" : "false")
                << ", \"defined\": " << (workflowCost->bound.defined ? "true" : "false")
                << ", \"cost\": " << money(workflowCost->bound.money)
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
                    << ", \"line\": " << entry.location.line << "}"
                    << (step + 1 == workflowCost->derivation.size() ? "" : ",") << '\n';
            }
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
            << "  (guaranteed " << workflow.bound.guaranteed << " + estimated "
            << workflow.bound.estimated << " @ " << semantic.options.charsPerToken
            << " chars/token)\n";
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
