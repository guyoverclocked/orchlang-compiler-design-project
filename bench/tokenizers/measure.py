#!/usr/bin/env python3
"""Measure the tokenizer facts that a sound token bound depends on.

OrchLang's cost bound turns text lengths into token counts, and the relational
analysis once compared token counts across the two arms of a secret branch.
Both steps rest on facts about real tokenizers that are easy to assume and
rarely checked.  This script checks them, on real tokenizers pinned to exact
revisions and on real text pinned to exact hashes, and writes what it finds to
bench/results/tokenizers.json and bench/results/tokenizers.txt.

Nothing here is estimated or invented.  Each number is either an exhaustive
computation (every Unicode scalar value, every vocabulary entry) or a maximum
over an explicit, reproducible sample, and the report says which.

Questions answered, per tokenizer:

  Q1  Does tokens(s) <= bytes(s) + sigma hold?  Checked on every Unicode scalar
      value as a one-character string, then on adversarial and corpus strings.
      This is the contract a *guaranteed* input bound needs.
  Q2  How many bytes can one token stand for?  (max over the vocabulary.)  This
      is the only sound way to turn a response's token cap into a byte bound.
  Q3  Can a response re-encode to MORE tokens than the model generated, under
      the same tokenizer?  (max over the vocabulary of |encode(decode(t))|.)
      The compiler used to assume not.
  Q4  Is tokenization subadditive under concatenation?  A bound of the form
      tokens(template) + sum tokens(argument) assumes it is.
  Q5  How often does the default four-characters-per-token estimate fail on
      real multilingual text, code, and JSON?
  Q6  How far can a string's token count grow when it moves from tokenizer A
      to tokenizer B?  (max over A's vocabulary, and typical on corpora.)
  Q7  Are two strings of equal character length billed equally?  (The
      assumption behind comparing literal and template sizes.)

Requirements: pip install -r bench/requirements.txt  (tiktoken, tokenizers,
huggingface_hub).  Network access is needed the first time, to download the
pinned tokenizers and corpora; everything is cached under bench/.cache/.

Usage:  python bench/tokenizers/measure.py [--quick]
"""

import argparse
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
ROOT = os.path.dirname(BENCH)
CACHE = os.path.join(BENCH, '.cache')
RESULTS = os.path.join(BENCH, 'results')

# --------------------------------------------------------------- pinning ----

# Hugging Face tokenizers, pinned to the commit that was measured.  tiktoken
# encodings are pinned by tiktoken itself, which verifies a SHA-256 of each
# downloaded vocabulary file.
HF_TOKENIZERS = {
    'llama3': ('unsloth/Llama-3.2-1B', '9535bd9b1d1dea6acafbdc4813b728796aeb28da'),
    'llama2': ('NousResearch/Llama-2-7b-hf', '8efe6c9b93655b934e27bd9981e3ec13e55aee9d'),
    'mistral': ('mistralai/Mistral-7B-v0.1', '27d67f1b5f57dc0953326b2601d68371d40ea8da'),
    'qwen25': ('Qwen/Qwen2.5-0.5B', '060db6499f32faf8b98477b0a26969ef7d8b9987'),
    'gemma2': ('unsloth/gemma-2-2b', '25319945f7fd83b8b903e12081777b7eef2ba993'),
    'phi3': ('microsoft/Phi-3-mini-4k-instruct', 'f39ac1d28e925b323eae81227eaba4464caced4e'),
    'deepseekv3': ('deepseek-ai/DeepSeek-V3', 'e815299b0bcbac849fa540c768ef21845365c9eb'),
    'olmo2': ('allenai/OLMo-2-1124-7B', '7df9a82518afdecae4e8c026b27adccc8c1f0032'),
    'gpt2': ('openai-community/gpt2', '607a30d783dfa663caf39e06633721c8d4cfcd7e'),
    't5': ('google-t5/t5-small', 'df1b051c49625cf57a3d0d8d3863ed4d13564fe4'),
    'xlmr': ('FacebookAI/xlm-roberta-base', 'e73636d4f797dec63c3081bb6ed5c7b0bb3f2089'),
}
TIKTOKEN = ['cl100k_base', 'o200k_base', 'r50k_base']
ORDER = TIKTOKEN + ['llama3', 'qwen25', 'deepseekv3', 'olmo2', 'gpt2',
                    'llama2', 'mistral', 'phi3', 'gemma2', 't5', 'xlmr']
# A representative subset for the quadratic cross-tokenizer measurement.
CROSS = ['cl100k_base', 'o200k_base', 'llama3', 'qwen25', 'mistral', 'gemma2', 't5']

# Real text, pinned by URL and SHA-256.
UDHR = ('https://raw.githubusercontent.com/nltk/nltk_data/'
        '550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/corpora/udhr2.zip',
        '0796c314b09a930c989c6f9d93d226af9af13feccd88496e196c743dd266c7f3')
CPYTHON = 'https://raw.githubusercontent.com/python/cpython/v3.12.7/'
CODE_FILES = ['Lib/json/decoder.py', 'Lib/functools.py', 'Lib/textwrap.py', 'Lib/heapq.py',
              'Lib/bisect.py', 'Lib/fractions.py', 'Lib/string.py', 'Lib/csv.py',
              'Objects/listobject.c', 'Objects/boolobject.c', 'Modules/_bisectmodule.c',
              'Include/object.h']
CLDR = 'https://raw.githubusercontent.com/unicode-org/cldr-json/46.0.0/cldr-json/'
JSON_FILES = ['cldr-localenames-full/main/ja/languages.json',
              'cldr-localenames-full/main/ar/territories.json',
              'cldr-localenames-full/main/hi/scripts.json',
              'cldr-localenames-full/main/ru/languages.json',
              'cldr-localenames-full/main/zh/territories.json',
              'cldr-localenames-full/main/en/languages.json',
              'cldr-numbers-full/main/th/numbers.json',
              'cldr-dates-full/main/ko/ca-gregorian.json']


def fetch(url, sha256=None):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if not os.path.exists(path):
        data = urllib.request.urlopen(url, timeout=120).read()
        with open(path, 'wb') as handle:
            handle.write(data)
    data = open(path, 'rb').read()
    digest = hashlib.sha256(data).hexdigest()
    if sha256 is not None and digest != sha256:
        raise SystemExit('hash mismatch for %s: %s' % (url, digest))
    return data, digest


# ------------------------------------------------------------ tokenizers ----

class Tok:
    """A uniform view of one tokenizer: counts without special tokens, the raw
    bytes of each vocabulary entry, and a lossy decode like a provider's."""

    def __init__(self, name):
        self.name = name
        if name in TIKTOKEN:
            import tiktoken
            self.kind = 'tiktoken'
            self.enc = tiktoken.get_encoding(name)
            self.family = 'byte-level BPE'
            self.normalizer = None
            self.revision = 'tiktoken ' + tiktoken.__version__
            special = set(self.enc._special_tokens.values())
            self.ids = [i for i in range(self.enc.n_vocab) if i not in special and self._tt_valid(i)]
        else:
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
            repo, revision = HF_TOKENIZERS[name]
            path = hf_hub_download(repo, 'tokenizer.json', revision=revision,
                                   cache_dir=os.path.join(CACHE, 'hf'))
            self.kind = 'hf'
            self.revision = '%s@%s' % (repo, revision)
            self.tok = Tokenizer.from_file(path)
            config = json.loads(self.tok.to_str())
            model = config['model']
            decoder = json.dumps(config.get('decoder'))
            self.normalizer = config.get('normalizer')
            self.byte_level = 'ByteLevel' in decoder
            if self.byte_level:
                self.family = 'byte-level BPE'
            elif model['type'] == 'BPE' and model.get('byte_fallback'):
                self.family = 'SentencePiece BPE, byte fallback'
            else:
                self.family = 'SentencePiece %s, no byte fallback' % model['type']
            special = {t.content for t in self.tok.get_added_tokens_decoder().values()}
            vocab = self.tok.get_vocab()
            self.pieces = {i: p for p, i in vocab.items() if p not in special}
            self.ids = sorted(self.pieces)
            if self.byte_level:
                self.unbyte = {c: b for b, c in bytes_to_unicode().items()}

    def _tt_valid(self, i):
        try:
            self.enc.decode_single_token_bytes(i)
            return True
        except KeyError:
            return False

    def count(self, text):
        if self.kind == 'tiktoken':
            return len(self.enc.encode(text, disallowed_special=()))
        return len(self.tok.encode(text, add_special_tokens=False).ids)

    def counts(self, texts):
        if not texts:
            return []
        if self.kind == 'tiktoken':
            return [len(x) for x in self.enc.encode_batch(texts, disallowed_special=(), num_threads=4)]
        return [len(e.ids) for e in self.tok.encode_batch(texts, add_special_tokens=False)]

    def request_overhead(self):
        """Tokens added when special tokens are enabled (BOS/EOS markers)."""
        if self.kind == 'tiktoken':
            return 0
        return (len(self.tok.encode('hello world', add_special_tokens=True).ids)
                - len(self.tok.encode('hello world', add_special_tokens=False).ids))

    def token_bytes(self, i):
        if self.kind == 'tiktoken':
            return self.enc.decode_single_token_bytes(i)
        piece = self.pieces[i]
        if self.byte_level:
            return bytes(self.unbyte[c] for c in piece)
        match = re.fullmatch(r'<0x([0-9A-Fa-f]{2})>', piece)
        if match:
            return bytes([int(match.group(1), 16)])
        return piece.replace('▁', ' ').encode('utf-8')

    def decode(self, ids):
        """What a provider returns: the UTF-8 decoding of the generated bytes,
        with ill-formed sequences replaced."""
        return b''.join(self.token_bytes(i) for i in ids).decode('utf-8', errors='replace')


def bytes_to_unicode():
    """GPT-2's reversible byte-to-character map used by byte-level BPE."""
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(ord('\xa1'), ord('\xac') + 1)) + \
        list(range(ord('\xae'), ord('\xff') + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


# --------------------------------------------------------------- corpora ----

def corpora(quick):
    data, digest = fetch(*UDHR)
    udhr = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith('.txt'):
                continue
            raw = archive.read(name)
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                continue
            udhr.append((name.split('/')[-1][:-4], text))
    code = []
    for path in CODE_FILES:
        blob, _ = fetch(CPYTHON + path)
        code.append((path, blob.decode('utf-8')))
    js = []
    for path in JSON_FILES:
        blob, _ = fetch(CLDR + path)
        js.append((path, blob.decode('utf-8')))
    if quick:
        udhr = udhr[::8]
    return {'multilingual': udhr, 'code': code, 'json': js}, digest


def windows(text, width, step):
    return [text[i:i + width] for i in range(0, max(1, len(text) - width + 1), step)]


def adversarial_strings():
    """Strings built to stress normalisers and byte fallback."""
    expanders = [c for c in map(chr, range(0x80, 0x30000))
                 if not 0xD800 <= ord(c) <= 0xDFFF
                 and len(unicodedata.normalize('NFKC', c).encode()) > 2 * len(c.encode())]
    rng = random.Random(7)
    out = []
    out.append(''.join(expanders[:200]))
    out.append('ﷺ' * 64)
    out.append('\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466' * 20)
    out.append('e' + '́' * 200)
    out.append(' ' * 300)
    out.append('​' * 300)
    out.append('9' * 300)
    for _ in range(40):
        out.append(''.join(rng.choice(expanders) for _ in range(rng.randint(1, 80))))
    for _ in range(40):
        out.append(''.join(chr(rng.randint(0x20, 0x2FFFF)) for _ in range(rng.randint(1, 80)))
                   .encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))
    return [s for s in out if s]


# ---------------------------------------------------------- measurements ----

def all_scalar_values():
    return [chr(c) for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF]


def q1_codepoints(tok, chars, byte_lengths):
    counts = tok.counts(chars)
    worst_excess, worst_ratio, over = -10 ** 9, 0.0, 0
    examples = []
    for ch, n, b in zip(chars, counts, byte_lengths):
        excess = n - b
        if excess > 0:
            over += 1
        if excess > worst_excess:
            worst_excess = excess
        if n / b > worst_ratio:
            worst_ratio = n / b
        if excess > 0 and len(examples) < 400:
            examples.append((excess, 'U+%04X' % ord(ch), n, b))
    examples.sort(reverse=True)
    return {'scalar_values_checked': len(chars),
            'max_tokens_minus_bytes': worst_excess,
            'max_tokens_per_byte': round(worst_ratio, 3),
            'scalar_values_with_tokens_gt_bytes': over,
            'worst_examples': [{'code_point': c, 'tokens': n, 'bytes': b}
                               for _, c, n, b in examples[:5]]}


def q1_strings(tok, strings):
    counts = tok.counts(strings)
    excess = [n - len(s.encode()) for s, n in zip(strings, counts)]
    worst = max(range(len(strings)), key=lambda i: excess[i])
    return {'strings_checked': len(strings), 'max_tokens_minus_bytes': excess[worst],
            'max_tokens_per_byte': round(max(n / max(1, len(s.encode()))
                                             for s, n in zip(strings, counts)), 3)}


def q2_q3_vocab(tok):
    raw = [tok.token_bytes(i) for i in tok.ids]
    longest = max(range(len(raw)), key=lambda k: len(raw[k]))
    decoded = [r.decode('utf-8', errors='replace') for r in raw]
    counts = tok.counts(decoded)
    worst = max(range(len(counts)), key=lambda k: counts[k])
    expanding = sum(1 for n in counts if n > 1)
    # A provider returns text, not bytes: ill-formed UTF-8 is replaced by
    # U+FFFD, three bytes, so a partial-character token can grow on decoding.
    lossy = [len(d.encode('utf-8')) for d in decoded]
    return {
        'vocabulary_entries': len(raw),
        'max_token_bytes': len(raw[longest]),
        'max_decoded_token_bytes': max(lossy),
        'longest_token': raw[longest].decode('utf-8', errors='replace')[:40],
        'mean_token_bytes': round(sum(map(len, raw)) / len(raw), 2),
        'reencode_max_tokens_for_one_token': counts[worst],
        'reencode_worst_token': decoded[worst][:40],
        'tokens_that_reencode_to_more_than_one': expanding,
    }, decoded, counts


CONTEXT_PREFIX = 'Input: '


def in_context(tok, texts):
    """Tokens a string costs when spliced after a fixed prompt prefix, which is
    how a response is reused.  Removes the SentencePiece dummy-prefix artefact
    that inflates counts of strings encoded in isolation."""
    base = tok.count(CONTEXT_PREFIX)
    return [n - base for n in tok.counts([CONTEXT_PREFIX + t for t in texts])]


def q3_in_context(tok, decoded):
    counts = in_context(tok, decoded)
    worst = max(range(len(counts)), key=lambda k: counts[k])
    return {'reencode_max_tokens_for_one_token': counts[worst],
            'reencode_worst_token': decoded[worst][:40],
            'tokens_that_reencode_to_more_than_one': sum(1 for n in counts if n > 1)}


def q3_sequences(tok, decoded, counts, rng, trials, length):
    """Random and worst-case generated sequences, decoded then re-encoded in
    context.  A model samples from its whole vocabulary, so any sequence of
    vocabulary entries is a possible response."""
    ids = list(range(len(decoded)))
    texts, labels = [], []
    for trial in range(trials):
        texts.append(''.join(decoded[rng.choice(ids)] for _ in range(length)))
        labels.append('random #%d' % trial)
    # The entries that re-encode worst, alone and repeated: does repetition
    # re-merge, or compound?
    top = sorted(ids, key=lambda k: -counts[k])[:50]
    for k in top:
        texts.append(decoded[k] * length)
        labels.append('repeat %r' % decoded[k][:20])
    reencoded = in_context(tok, texts)
    worst = max(range(len(texts)), key=lambda k: reencoded[k])
    return {'sequences': len(texts), 'sequence_length': length,
            'max_reencoded_tokens_per_generated_token': round(reencoded[worst] / length, 3),
            'worst_sequence': labels[worst]}


def q4_concatenation(tok, decoded, docs, rng, pairs):
    """tokens(u + v) - tokens(u) - tokens(v), over vocabulary pairs and over
    real texts cut at random points (a template followed by an argument)."""
    us, vs = [], []
    for _ in range(pairs):
        us.append(decoded[rng.randrange(len(decoded))])
        vs.append(decoded[rng.randrange(len(decoded))])
    for _ in range(pairs):
        doc = docs[rng.randrange(len(docs))]
        if len(doc) < 4:
            continue
        a = rng.randrange(0, len(doc) - 2)
        b = rng.randrange(a + 1, min(len(doc), a + 400))
        c = rng.randrange(b + 1, min(len(doc), b + 400) + 1)
        us.append(doc[a:b])
        vs.append(doc[b:c])
    nu, nv, nuv = tok.counts(us), tok.counts(vs), tok.counts([u + v for u, v in zip(us, vs)])
    deltas = [w - x - y for x, y, w in zip(nu, nv, nuv)]
    worst = max(range(len(deltas)), key=lambda k: deltas[k])
    return {'pairs': len(deltas), 'max_defect': deltas[worst],
            'pairs_with_positive_defect': sum(1 for d in deltas if d > 0),
            'worst_pair': [us[worst][:30], vs[worst][:30]]}


def q5_estimate(tok, category_docs, width):
    """How often the four-per-token estimate is exceeded on fixed-width windows.

    Two versions: ceil(chars / 4), which is what the documentation says, and
    ceil(bytes / 4), which is what the compiler computed (std::string::size()
    counts bytes).  They agree on ASCII and nowhere else.
    """
    out = {}
    for category, docs in category_docs.items():
        texts = []
        for doc in docs:
            texts.extend(windows(doc, width, width))
        counts = tok.counts(texts)
        chars = sum(len(t) for t in texts)
        byts = sum(len(t.encode()) for t in texts)
        tokens = sum(counts)
        by_chars = [-(-len(t) // 4) for t in texts]
        by_bytes = [-(-len(t.encode()) // 4) for t in texts]
        fail_c = sum(1 for n, e in zip(counts, by_chars) if n > e)
        fail_b = sum(1 for n, e in zip(counts, by_bytes) if n > e)
        out[category] = {'windows': len(texts), 'chars_per_token': round(chars / tokens, 2),
                         'bytes_per_token': round(byts / tokens, 2),
                         'estimate_exceeded': fail_c,
                         'estimate_exceeded_pct': round(100.0 * fail_c / len(texts), 1),
                         'byte_estimate_exceeded_pct': round(100.0 * fail_b / len(texts), 1),
                         'max_tokens_over_estimate': round(max(n / max(1, e)
                                                               for n, e in zip(counts, by_chars)), 2),
                         'max_tokens_over_byte_estimate': round(max(n / max(1, e)
                                                                    for n, e in zip(counts, by_bytes)), 2)}
    return out


def q7_equal_length(tok, docs, rng, samples):
    """Two strings of equal character length: how often do their counts differ?"""
    left, right = [], []
    for _ in range(samples):
        width = rng.randint(4, 40)
        d1, d2 = docs[rng.randrange(len(docs))], docs[rng.randrange(len(docs))]
        if len(d1) <= width or len(d2) <= width:
            continue
        a, b = rng.randrange(len(d1) - width), rng.randrange(len(d2) - width)
        left.append(d1[a:a + width])
        right.append(d2[b:b + width])
    n1, n2 = tok.counts(left), tok.counts(right)
    differ = sum(1 for x, y in zip(n1, n2) if x != y)
    return {'pairs': len(left), 'counts_differ': differ,
            'counts_differ_pct': round(100.0 * differ / max(1, len(left)), 1),
            'max_difference': max(abs(x - y) for x, y in zip(n1, n2))}


def q6_cross(toks, decoded_by_name, docs):
    out = {}
    for a in CROSS:
        for b in CROSS:
            if a == b:
                continue
            source = decoded_by_name[a]
            counts = toks[b].counts(source)
            worst = max(range(len(counts)), key=lambda k: counts[k])
            ta, tb = toks[a].counts(docs), toks[b].counts(docs)
            ratios = sorted(y / x for x, y in zip(ta, tb) if x > 0)
            out['%s->%s' % (a, b)] = {
                'max_tokens_for_one_source_token': counts[worst],
                'worst_source_token': source[worst][:40],
                'corpus_median_ratio': round(ratios[len(ratios) // 2], 3),
                'corpus_max_ratio': round(ratios[-1], 3),
            }
    return out


def normalization_expansion():
    """Per-code-point UTF-8 expansion of NFC, NFD and NFKC (Python's Unicode
    tables).  Canonical decomposition is per-character, so the NFD figure bounds
    whole strings; NFKC also composes across characters and is reported only
    per code point."""
    out = {'unicode_version': unicodedata.unidata_version}
    for form in ('NFC', 'NFD', 'NFKC'):
        worst, where = 0.0, None
        for c in all_scalar_values():
            b = len(c.encode('utf-8', errors='surrogatepass'))
            n = len(unicodedata.normalize(form, c).encode('utf-8', errors='surrogatepass'))
            if n / b > worst:
                worst, where = n / b, 'U+%04X' % ord(c)
        out[form] = {'max_bytes_ratio': round(worst, 3), 'at': where}
    return out


# ----------------------------------------------------------------- driver ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true',
                        help='smaller samples; for development, not for reported numbers')
    args = parser.parse_args()
    rng = random.Random(20260925)
    start = time.time()

    texts, udhr_digest = corpora(args.quick)
    docs = [t for _, t in texts['multilingual']] + [t for _, t in texts['code']] + \
        [t for _, t in texts['json']]
    category_docs = {k: [t for _, t in v] for k, v in texts.items()}
    category_docs['adversarial'] = adversarial_strings()
    chars = all_scalar_values()
    if args.quick:
        chars = chars[::17]
    byte_lengths = [len(c.encode('utf-8')) for c in chars]

    results = {'generated_by': 'bench/tokenizers/measure.py', 'quick': args.quick,
               'python': sys.version.split()[0], 'unicode_version': unicodedata.unidata_version,
               'corpora': {'udhr2_sha256': udhr_digest, 'udhr_languages': len(texts['multilingual']),
                           'code_files': CODE_FILES, 'json_files': JSON_FILES},
               'normalization': normalization_expansion() if not args.quick else None,
               'tokenizers': {}}
    toks, decoded_by_name = {}, {}
    for name in ORDER:
        t0 = time.time()
        tok = Tok(name)
        toks[name] = tok
        entry = {'revision': tok.revision, 'family': tok.family,
                 'normalizer': (tok.normalizer or {}).get('type') if tok.kind == 'hf' else None,
                 'special_tokens_added_per_request': tok.request_overhead()}
        entry['q1_code_points'] = q1_codepoints(tok, chars, byte_lengths)
        entry['q1_strings'] = q1_strings(tok, category_docs['adversarial'] + docs)
        vocab, decoded, counts = q2_q3_vocab(tok)
        decoded_by_name[name] = decoded
        entry['q2_q3_vocabulary'] = vocab
        entry['q3_in_context'] = q3_in_context(tok, decoded)
        entry['q3_sequences'] = q3_sequences(tok, decoded, counts, rng,
                                             100 if args.quick else 2000, 64)
        entry['q4_concatenation'] = q4_concatenation(tok, decoded, docs, rng,
                                                     5000 if args.quick else 200000)
        entry['q5_estimate'] = q5_estimate(tok, category_docs, 256)
        entry['q7_equal_length'] = q7_equal_length(tok, docs, rng, 2000 if args.quick else 50000)
        entry['seconds'] = round(time.time() - t0, 1)
        results['tokenizers'][name] = entry
        print('%-12s %5.1fs  L=%-4d rho=%-3d q1=%+d defect=%+d' % (
            name, entry['seconds'], vocab['max_token_bytes'],
            entry['q3_in_context']['reencode_max_tokens_for_one_token'],
            entry['q1_code_points']['max_tokens_minus_bytes'],
            entry['q4_concatenation']['max_defect']), flush=True)

    sample_docs = [d[:2000] for d in docs]
    results['q6_cross'] = q6_cross(toks, decoded_by_name, sample_docs)
    results['seconds'] = round(time.time() - start, 1)

    os.makedirs(RESULTS, exist_ok=True)
    suffix = '.quick' if args.quick else ''
    with io.open(os.path.join(RESULTS, 'tokenizers%s.json' % suffix), 'w', encoding='utf-8',
                 newline='\n') as handle:
        handle.write(json.dumps(results, indent=1, ensure_ascii=False) + '\n')
    with io.open(os.path.join(RESULTS, 'tokenizers%s.txt' % suffix), 'w', encoding='utf-8',
                 newline='\n') as handle:
        handle.write(report(results))
    print(report(results))


def report(r):
    out = io.StringIO()
    out.write('Tokenizer facts behind a token bound\n====================================\n\n')
    out.write('%d UDHR languages, %d code files, %d JSON files; Unicode %s%s\n\n' % (
        r['corpora']['udhr_languages'], len(r['corpora']['code_files']),
        len(r['corpora']['json_files']), r['unicode_version'],
        '  [QUICK: reduced samples, not for reporting]' if r['quick'] else ''))
    head = ('tokenizer', 'family', 'L', 'Q1 max(t-b)', 'Q1 strings', 'Q3 rho1', 'Q3 seq', 'Q4 defect',
            'Q5 chars/4 fails ml/code/json', 'Q5 bytes/4 fails', 'Q7 differ')
    rows = []
    for name, e in r['tokenizers'].items():
        q5 = e['q5_estimate']
        rows.append((name, e['family'][:30], e['q2_q3_vocabulary']['max_token_bytes'],
                     e['q1_code_points']['max_tokens_minus_bytes'],
                     e['q1_strings']['max_tokens_minus_bytes'],
                     e['q3_in_context']['reencode_max_tokens_for_one_token'],
                     e['q3_sequences']['max_reencoded_tokens_per_generated_token'],
                     e['q4_concatenation']['max_defect'],
                     '%s/%s/%s%%' % (q5['multilingual']['estimate_exceeded_pct'],
                                    q5['code']['estimate_exceeded_pct'],
                                    q5['json']['estimate_exceeded_pct']),
                     '%s/%s/%s%%' % (q5['multilingual']['byte_estimate_exceeded_pct'],
                                    q5['code']['byte_estimate_exceeded_pct'],
                                    q5['json']['byte_estimate_exceeded_pct']),
                     '%s%%' % e['q7_equal_length']['counts_differ_pct']))
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    out.write('  '.join(str(h).ljust(w) for h, w in zip(head, widths)) + '\n')
    out.write('  '.join('-' * w for w in widths) + '\n')
    for row in rows:
        out.write('  '.join(str(x).ljust(w) for x, w in zip(row, widths)) + '\n')
    out.write('\nL = most bytes one token stands for; Q1 = max of tokens(s) - bytes(s) over every\n'
              'scalar value (then over adversarial and corpus strings); Q3 rho1 = most tokens one\n'
              'vocabulary entry re-encodes to, spliced after "%s"; Q3 seq = most re-encoded\n'
              'tokens per generated token over random and repeated sequences, in the same\n'
              'context; Q4 = max tokens(u+v) - tokens(u) - tokens(v); Q5 = share of\n'
              '256-character windows where tokens > ceil(chars/4), and > ceil(bytes/4); Q7 =\n'
              'share of equal-character-length pairs with different token counts.\n\n'
              % CONTEXT_PREFIX)
    if r.get('normalization'):
        out.write('Unicode normalisation, worst UTF-8 expansion of one code point:\n')
        for form in ('NFC', 'NFD', 'NFKC'):
            n = r['normalization'][form]
            out.write('  %-5s x%s at %s\n' % (form, n['max_bytes_ratio'], n['at']))
        out.write('\n')
    out.write('Cross-tokenizer expansion (Q6): worst single source token, and corpus ratios\n')
    for pair, e in sorted(r['q6_cross'].items()):
        out.write('  %-26s one token -> %3d   corpus median x%-6s max x%s\n' % (
            pair, e['max_tokens_for_one_source_token'], e['corpus_median_ratio'],
            e['corpus_max_ratio']))
    return out.getvalue()


if __name__ == '__main__':
    main()
