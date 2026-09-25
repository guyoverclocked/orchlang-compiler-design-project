// PROVISIONAL: replaced by bench/tokenizers/contracts.py output.
#include "tokenizer_contracts.hpp"

#include <sstream>

namespace orchlang {

namespace {

const TokenizerContract kContracts[] = {
    {"cl100k_base", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"o200k_base", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"r50k_base", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"gpt2", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"llama3", "byte-level BPE", true, 1, 1, 128, true, "provisional"},
    {"olmo2", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"deepseekv3", "byte-level BPE", true, 1, 0, 128, true, "provisional"},
    {"qwen25", "byte-level BPE after NFC", true, 3, 0, 128, false, "provisional"},
    {"llama2", "SentencePiece BPE, byte fallback", true, 1, 2, 27, true, "provisional"},
    {"mistral", "SentencePiece BPE, byte fallback", true, 1, 2, 25, true, "provisional"},
    {"phi3", "SentencePiece BPE, byte fallback", true, 1, 1, 27, true, "provisional"},
    {"gemma2", "SentencePiece BPE, byte fallback", true, 1, 1, 48, true, "provisional"},
    {"t5", "SentencePiece Unigram, NFKC-like charsmap", false, 0, 0, 18, false, "provisional"},
    {"xlmr", "SentencePiece Unigram, NFKC-like charsmap", false, 0, 0, 48, false, "provisional"},
    {"mockbpe", "OrchLang runtime mock (greedy longest match, byte fallback)", true, 1, 0, 12, true, "by construction: every token covers at least one byte"},
};

}  // namespace

const TokenizerContract* findTokenizerContract(const std::string& name) {
    for (const TokenizerContract& contract : kContracts) {
        if (name == contract.name) {
            return &contract;
        }
    }
    return nullptr;
}

std::string knownTokenizerNames() {
    std::ostringstream out;
    bool first = true;
    for (const TokenizerContract& contract : kContracts) {
        out << (first ? "" : ", ") << contract.name;
        first = false;
    }
    return out.str();
}

}  // namespace orchlang
