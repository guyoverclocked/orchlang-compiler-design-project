#!/usr/bin/env python3
"""Does a real model's output length depend on what a request says?

The withdrawn size rule assumed, without saying so, that two requests of equal
size to the same model are answered with equal output lengths under shared
randomness.  This script tests that assumption on a real, small, openly
licensed instruction-tuned model run locally on the CPU, with no API key.

Every pair of chat requests is padded to exactly the same number of tokens
under the model's own tokenizer and chat template -- the strongest form of
"equal size" any rule could compare -- and differs only in content: either the
instruction ("reply briefly" / "reply in detail") or only the argument (two
different tickets under the same instruction).  Each request is answered once
greedily and once per sampling seed, with the seed shared between the two
requests of a pair; that shared seed is the coupling the relational analysis
reasons under.  The script also checks the coupling's premise: the same
request with the same seed gives the same answer.

Requirements: pip install -r bench/requirements.txt  (torch, transformers)
Usage:        python bench/provider/measure.py [--seeds N] [--max-new-tokens N]
Output:       bench/results/provider.json
"""

import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
RESULTS = os.path.join(BENCH, 'results')
CACHE = os.path.join(BENCH, '.cache', 'hf')

MODEL = 'HuggingFaceTB/SmolLM2-135M-Instruct'
REVISION = '12fd25f77366fa6b3b4b768ec3050bf629380bac'

TICKETS = [
    'My printer shows error 0x3F and will not print anything since this morning.',
    'I was charged twice for the March invoice and need one charge refunded.',
    'The mobile app logs me out every time I switch to another application.',
    'Our team cannot see the shared dashboard after the latest update.',
    'Please change the delivery address on order 5521 to our new office.',
    'The export to CSV drops every row that contains a comma in the name field.',
]

INSTRUCTIONS = [
    ('Acknowledge this support ticket in one short sentence.',
     'Escalate this support ticket with a detailed step-by-step analysis.'),
    ('Classify this ticket as billing, technical or other. Answer with one word.',
     'Explain every possible cause of this ticket and how an engineer should check each.'),
    ('Reply with a one-line summary of the ticket.',
     'Write a complete, friendly reply to the customer with all next steps.'),
]


def chat_ids(tokenizer, text):
    return tokenizer.apply_chat_template([{'role': 'user', 'content': text}],
                                         add_generation_prompt=True)


def equalise(tokenizer, left, right, filler=' Thanks.'):
    """Pad the shorter request with filler until both have the same token count
    under the chat template, or give up."""
    for _ in range(40):
        a, b = len(chat_ids(tokenizer, left)), len(chat_ids(tokenizer, right))
        if a == b:
            return left, right, a
        if a < b:
            left += filler
        else:
            right += filler
    return None


def build_pairs(tokenizer):
    pairs = []
    for brief, detailed in INSTRUCTIONS:
        for ticket in TICKETS[:3]:
            made = equalise(tokenizer, '%s\n\nTicket: %s' % (brief, ticket),
                            '%s\n\nTicket: %s' % (detailed, ticket))
            if made:
                pairs.append({'kind': 'instruction', 'a': made[0], 'b': made[1], 'tokens': made[2]})
    for brief, _ in INSTRUCTIONS:
        for first, second in ((TICKETS[0], TICKETS[3]), (TICKETS[1], TICKETS[4]),
                              (TICKETS[2], TICKETS[5])):
            made = equalise(tokenizer, '%s\n\nTicket: %s' % (brief, first),
                            '%s\n\nTicket: %s' % (brief, second))
            if made:
                pairs.append({'kind': 'argument', 'a': made[0], 'b': made[1], 'tokens': made[2]})
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=4)
    parser.add_argument('--max-new-tokens', type=int, default=96)
    args = parser.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, cache_dir=CACHE)
    model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION, cache_dir=CACHE,
                                                 torch_dtype=torch.float32)
    model.eval()

    def generate(text, seed):
        ids = torch.tensor([chat_ids(tokenizer, text)])
        kwargs = {'max_new_tokens': args.max_new_tokens, 'pad_token_id': tokenizer.eos_token_id,
                  'attention_mask': torch.ones_like(ids)}
        if seed is None:
            kwargs['do_sample'] = False
        else:
            torch.manual_seed(seed)
            kwargs.update(do_sample=True, temperature=0.8, top_p=0.95)
        with torch.no_grad():
            out = model.generate(ids, **kwargs)
        generated = out[0, ids.shape[1]:].tolist()
        return generated

    start = time.time()
    pairs = build_pairs(tokenizer)
    for index, pair in enumerate(pairs):
        pair['greedy'] = [len(generate(pair['a'], None)), len(generate(pair['b'], None))]
        pair['sampled'] = []
        for seed in range(1, args.seeds + 1):
            pair['sampled'].append([seed, len(generate(pair['a'], seed)),
                                    len(generate(pair['b'], seed))])
        print('pair %2d %-11s tokens=%d greedy=%s sampled=%s' % (
            index, pair['kind'], pair['tokens'], pair['greedy'],
            [s[1:] for s in pair['sampled']]), flush=True)

    determinism = []
    for pair in pairs[:6]:
        first = generate(pair['b'], 7)
        second = generate(pair['b'], 7)
        determinism.append(first == second)

    differing = sum(1 for p in pairs if p['greedy'][0] != p['greedy'][1] or
                    any(s[1] != s[2] for s in p['sampled']))
    comparisons = [(s[1], s[2]) for p in pairs for s in p['sampled']] + \
        [tuple(p['greedy']) for p in pairs]
    summary = {
        'pairs': len(pairs),
        'seeds': args.seeds,
        'max_new_tokens': args.max_new_tokens,
        'pairs_differing': differing,
        'comparisons': len(comparisons),
        'comparisons_differing': sum(1 for a, b in comparisons if a != b),
        'mean_abs_difference': round(sum(abs(a - b) for a, b in comparisons) / len(comparisons), 2),
        'instruction_pairs': sum(1 for p in pairs if p['kind'] == 'instruction'),
        'argument_pairs': sum(1 for p in pairs if p['kind'] == 'argument'),
        'argument_pairs_differing': sum(1 for p in pairs if p['kind'] == 'argument' and (
            p['greedy'][0] != p['greedy'][1] or any(s[1] != s[2] for s in p['sampled']))),
        'determinism_trials': len(determinism),
        'determinism_identical': sum(1 for d in determinism if d),
        'seconds': round(time.time() - start, 1),
    }
    result = {'generated_by': 'bench/provider/measure.py', 'model': MODEL, 'revision': REVISION,
              'torch': torch.__version__, 'transformers': transformers.__version__,
              'python': sys.version.split()[0], 'decoding': 'greedy, and sampling at temperature '
              '0.8, top_p 0.95 with the seed shared within a pair', 'summary': summary,
              'pairs': pairs}
    os.makedirs(RESULTS, exist_ok=True)
    with io.open(os.path.join(RESULTS, 'provider.json'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(result, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
