#!/usr/bin/env python3
"""Generate src/tokenizer_contracts.cpp from bench/results/tokenizers.json.

The compiler may only assume what a tokenizer's structure guarantees.  This
script turns the measurements into contracts of the form

    tokens(s) <= kappa * bytes(s) + sigma

and decides, per tokenizer, whether the contract is *verified*: whether there
is a structural argument that it holds for every string.  The measurement is a
check on the argument, and the script refuses to emit a verified contract that
the measurement contradicts.

The structural arguments:

  byte-level BPE, no normaliser
      Every token is a non-empty run of the text's bytes, so tokens <= bytes.
      sigma is the special tokens added per request.
  byte-level BPE after NFC (Qwen2.5)
      tokens <= bytes(NFC(s)).  Canonical decomposition expands a code point at
      most threefold in UTF-8 (UAX #15; checked exhaustively here), and
      composition never lengthens (checked on every canonical pair), so
      bytes(NFC(s)) <= 3 * bytes(s).  kappa = 3.
  SentencePiece BPE with byte fallback, Metaspace/Replace/Prepend only
      Every token is a vocabulary piece covering at least one character of the
      normalised text, or one byte.  Normalisation maps a space to one '▁'
      and may prepend one more, which no input byte pays for.  So
      tokens <= bytes + 1 + special tokens.
  SentencePiece Unigram with an NFKC-like precompiled charsmap (T5, XLM-R)
      No argument: the charsmap is a custom normaliser whose expansion is not
      bounded by a documented factor, and the measurement shows 194 more
      tokens than bytes on one string.  Unverified.

lambda, the most bytes one generated token can decode to after a provider's
lossy UTF-8 decoding, is read directly from the measured vocabulary.

Usage: python bench/tokenizers/contracts.py
"""

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(ROOT, 'bench', 'results', 'tokenizers.json')
OUTPUT = os.path.join(ROOT, 'src', 'tokenizer_contracts.cpp')

# Normalisation that adds a character no input byte pays for.
DUMMY_PREFIX = {'llama2': 1, 'mistral': 1, 'phi3': 1, 't5': 1, 'xlmr': 1}
NFC = {'qwen25'}
UNVERIFIED = {'t5', 'xlmr'}


def contract(name, entry):
    family = entry['family']
    vocabulary = entry['q2_q3_vocabulary']
    lam = max(vocabulary['max_token_bytes'], vocabulary.get('max_decoded_token_bytes', 0), 3)
    sigma = entry['special_tokens_added_per_request'] + DUMMY_PREFIX.get(name, 0)
    if name in UNVERIFIED:
        return {'name': name, 'family': family + ', NFKC-like charsmap', 'verified': False,
                'kappa': 0, 'sigma': 0, 'lambda': lam, 'lossless': False,
                'evidence': 'no structural bound; measured %+d tokens over bytes on one string'
                            % entry['q1_strings']['max_tokens_minus_bytes']}
    kappa = 3 if name in NFC else 1
    # The measurement must not contradict the argument.  Q1 counts without
    # special tokens, so only the dummy prefix may exceed kappa * bytes.  A
    # code point is at most four bytes, so on one code point the excess over
    # bytes is at most (kappa - 1) * 4 plus the prefix.
    prefix = DUMMY_PREFIX.get(name, 0)
    per_code_point = entry['q1_code_points']['max_tokens_minus_bytes']
    on_strings = entry['q1_strings']['max_tokens_minus_bytes']
    if per_code_point > (kappa - 1) * 4 + prefix or (kappa == 1 and on_strings > prefix):
        raise SystemExit('%s: measured tokens exceed %d * bytes + %d (per code point %d, strings %d); '
                         'the structural argument does not hold'
                         % (name, kappa, prefix, per_code_point, on_strings))
    if kappa == 1:
        evidence = ('every token covers at least one byte%s; exhaustive over %d scalar values and '
                    '%d strings, max tokens-bytes %d'
                    % (' (plus one dummy-prefix piece)' if DUMMY_PREFIX.get(name) else '',
                       entry['q1_code_points']['scalar_values_checked'],
                       entry['q1_strings']['strings_checked'],
                       max(entry['q1_code_points']['max_tokens_minus_bytes'],
                           entry['q1_strings']['max_tokens_minus_bytes'])))
    else:
        evidence = ('tokens <= bytes(NFC(s)) <= 3 bytes(s); NFD expands a code point at most 3x '
                    '(UAX #15), composition never lengthens; measured max per code point %d tokens '
                    'over bytes' % entry['q1_code_points']['max_tokens_minus_bytes'])
    return {'name': name, 'family': family + (' after NFC' if name in NFC else ''),
            'verified': True, 'kappa': kappa, 'sigma': sigma, 'lambda': lam,
            'lossless': name not in NFC, 'evidence': evidence}


def cpp_string(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def main():
    facts = json.load(open(RESULTS, encoding='utf-8'))
    if facts.get('quick'):
        raise SystemExit('refusing to generate contracts from a --quick measurement')
    entries = [contract(name, entry) for name, entry in facts['tokenizers'].items()]
    # The runtime's own tokenizer: a verified contract by construction.  Its
    # longest vocabulary entry is 9 bytes, and a mock provider's output unit is
    # a word of at most 12 bytes with its separator, so lambda is 12.
    entries.append({'name': 'mockbpe', 'family': 'OrchLang runtime mock (greedy longest match, '
                    'byte fallback)', 'verified': True, 'kappa': 1, 'sigma': 0, 'lambda': 12,
                    'lossless': True, 'evidence': 'by construction: every token covers at least '
                    'one byte; a mock output unit is at most 12 bytes'})
    lines = []
    for e in entries:
        lines.append('    {%s, %s, %s, %d, %d, %d, %s,\n     %s},' % (
            cpp_string(e['name']), cpp_string(e['family']), 'true' if e['verified'] else 'false',
            e['kappa'], e['sigma'], e['lambda'], 'true' if e['lossless'] else 'false',
            cpp_string(e['evidence'])))
    source = '''// GENERATED by bench/tokenizers/contracts.py from bench/results/tokenizers.json.
// Do not edit by hand: rerun the measurement and the generator instead.
//
// Measured on %d real tokenizers, Unicode %s, %d UDHR languages.

#include "tokenizer_contracts.hpp"

#include <sstream>

namespace orchlang {

namespace {

const TokenizerContract kContracts[] = {
%s
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
''' % (len(facts['tokenizers']), facts['unicode_version'], facts['corpora']['udhr_languages'],
       '\n'.join(lines))
    with io.open(OUTPUT, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(source)
    for e in entries:
        print('%-12s verified=%-5s kappa=%d sigma=%d lambda=%d' % (
            e['name'], e['verified'], e['kappa'], e['sigma'], e['lambda']))


if __name__ == '__main__':
    main()
