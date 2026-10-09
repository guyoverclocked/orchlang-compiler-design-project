#!/usr/bin/env python3
"""Generate explicitly reduced, source-derived workflow patterns.

These are authored bounded abstractions of pinned examples, not faithful ports
of the upstream applications. We do not copy upstream prompts or execute tools.
The secret-routing variants are our policy experiments, not upstream flaws.
See sourced/manifest.json for retained features and individual exclusions.
"""

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / 'sourced'
UPSTREAM = {
    'PDL': ('IBM/prompt-declaration-language', '44a1383f2869afdf69a5bc96954af39490399a3f', 'Apache-2.0'),
    'APPL': ('APPL-Team/APPL', 'e39c7401e5023d1b8d4c851e3a6f1048a462f03d', 'MIT'),
    'LMQL': ('eth-sri/lmql', 'fc8edd4457dc5a5e4e595302166bec797582bf53', 'Apache-2.0'),
}

PATTERNS = [
    ('pdl_chaining', 'PDL', 'examples/demo/2-model-chaining.pdl',
     'Two model requests with the first response in the second request context.',
     ['PDL context accumulation, provider stop strings and original prompts'],
     '  let first: text = call step(query) using m;\n'
     '  let second: text = call follow(first, query) using m;\n'),
    ('pdl_function', 'PDL', 'examples/demo/4-function.pdl',
     'Two explicit invocations of one translation function, inlined as requests.',
     ['First-class functions and original sentences; language strings are authored replacements'],
     '  let first: text = call translate(query, "language-A") using m;\n'
     '  let second: text = call translate(query, "language-B") using m;\n'),
    ('pdl_chat_turn', 'PDL', 'examples/demo/7-chatbot-roles.pdl',
     'One model request using supplied bounded conversation history and a query.',
     ['Unbounded interactive read/until loop, dynamic history growth and role semantics'],
     '  let reply: text = call follow(history, query) using m;\n'),
    ('pdl_tool_proposal', 'PDL', 'examples/demo/8-tools.pdl',
     'One model request that proposes a tool action as data.',
     ['JSON schema enforcement, generated Python expression, dynamic tool selection and execution'],
     '  let proposal: text = call plan(query) using m;\n'),
    ('pdl_react_cycle', 'PDL', 'examples/demo/9-react.pdl',
     'Two dependent requests (thought then action) in a bounded repeated cycle.',
     ['Until-finish loop is restricted to three attempts; tool dispatch/search/calculation, '
      'accumulating context and result semantics are excluded'],
     '  retry 3 {\n'
     '    let thought: text = call step(query) using m;\n'
     '    let action: text = call follow(thought, observation) using m;\n'
     '  }\n'),
    ('pdl_fixed_map', 'PDL', 'examples/map-reduce/context_fork.pdl',
     'A source list of three elements produces three separate model requests.',
     ['Map/array join and PDL context fork; original names replaced by authored constants'],
     '  let first: text = call translate(query, "item-one") using m;\n'
     '  let second: text = call translate(query, "item-two") using m;\n'
     '  let third: text = call translate(query, "item-three") using m;\n'),
    ('pdl_independent', 'PDL', 'examples/independent/independent.pdl',
     'Two requests with independent contexts followed by one outer-context request.',
     ['PDL context independence is reduced to explicit bounded arguments; original prompts'],
     '  let first: text = call translate(query, "context-one") using m;\n'
     '  let second: text = call translate(query, "context-two") using m;\n'
     '  let third: text = call step(query) using m;\n'),
    ('pdl_rag_pair', 'PDL', 'examples/rag/pdf_query.pdl',
     'Two fixed questions each cause an answer request with retrieved passages.',
     ['Embedding model, vector database, library include, retrieval and array rendering; '
      'retrieved passages supplied as bounded untrusted inputs'],
     '  let first: text = call answer(page, query) using m;\n'
     '  let second: text = call answer(page2, query2) using m;\n'),
    ('appl_self_consistency', 'APPL', 'examples/basic/cot_sc.py',
     'Five same-question requests, corresponding to the source sequential five-trial case.',
     ['Parallel implementation, answer parsing and mode aggregation; no answer-quality claim'],
     ''.join('  let trial%d: text = call step(query) using m;\n' % i for i in range(5))),
    ('appl_tool_branch', 'APPL', 'examples/basic/tool_call.py',
     'A proposal request followed conditionally by a response request with tool information.',
     ['Generated tool-call predicate is represented by a public input flag; Python/SymPy '
      'tool execution and tool-message protocol are excluded'],
     '  let proposal: text = call plan(query) using m;\n'
     '  if use_tool {\n'
     '    let answer2: text = call follow(proposal, observation) using m;\n'
     '  }\n'),
    ('appl_valid_retry', 'APPL', 'examples/advanced/repeat_until_valid.py',
     'At most five generation attempts, matching the source num_attempts default.',
     ['Content validator and deterministic source mock responses; copied context and '
      'its growth replaced by a bounded fixed context; offline success oracle used'],
     '  retry 5 {\n'
     '    let attempt: text = call follow(history, query) using m;\n'
     '  }\n'),
    ('appl_two_actor_chat', 'APPL', 'examples/advanced/multi_agent_chat/option1_resume.py',
     'Two rounds of alternating actors, four requests, each with output cap 50.',
     ['Resumable conversation state and heterogeneous source models/tokenizers; '
      'the two actor aliases share one explicit mock model, so no cross-tokenizer '
      'conversion is assumed'],
     '  let a1: text = call step(query) using actor_a;\n'
     '  let b1: text = call step(a1) using actor_b;\n'
     '  let a2: text = call step(b1) using actor_a;\n'
     '  let b2: text = call step(a2) using actor_b;\n'),
    ('lmql_joke_segments', 'LMQL', 'docs/features/examples/2-constraining.md',
     'Two dependent generated segments: a question followed by its punchline.',
     ['LMQL constrained decoding, stop rules and character constraint; generation '
      'segments are represented as separate requests with authored output caps'],
     '  let joke: text = call step(query) using m;\n'
     '  let punchline: text = call follow(joke, query) using m;\n'),
    ('lmql_reason_then_choice', 'LMQL', 'docs/features/examples/3-multi-part.md',
     'A reasoning segment feeds a final answer segment.',
     ['Finite-choice decoding, actual LMQL request batching and original question; '
      'two segment-level requests are an abstraction'],
     '  let reasoning: text = call step(query) using m;\n'
     '  let choice: text = call follow(reasoning, query) using m;\n'),
    ('lmql_retrieval', 'LMQL', 'docs/features/examples/5-wikipedia.md',
     'A generated search term precedes an answer using supplied retrieved text.',
     ['Asynchronous Wikipedia invocation, tool semantics and actual segment batching; '
      'retrieval is a bounded untrusted input'],
     '  let term: text = call step(query) using m;\n'
     '  let answer2: text = call retrieved(term, page, query) using m;\n'),
]

PREAMBLE = '''  input query: text max_tokens 160;
  input query2: text max_tokens 160;
  input history: text max_tokens 600;
  input page: text untrusted max_tokens 300;
  input page2: text untrusted max_tokens 300;
  input observation: text untrusted max_tokens 120;
  input use_tool: boolean;
  secret route: boolean;
  model m = mock("common-metric-worker") max_tokens 96;
  model actor_a = mock("common-metric-actor") max_tokens 50;
  model actor_b = mock("common-metric-actor") max_tokens 50;
  prompt step(x: text) -> text = "Process {x}";
  prompt follow(x: text, q: text) -> text = "Use {x} to answer {q}";
  prompt translate(x: text, target: text) -> text = "Translate {x} for {target}";
  prompt plan(x: text) -> text = "Propose an action for {x}";
  prompt answer(p: text, q: text) -> text = "Answer {q} from {p}";
  prompt retrieved(t: text, p: text, q: text) -> text = "For {q}, use {p} and term {t}";
'''


def generate(source_metadata=None):
    metadata_path = OUT / 'upstream_files.json'
    metadata = source_metadata or json.loads(metadata_path.read_text())
    rows = []
    for name, framework, path, retained, excluded, body in PATTERNS:
        repository, revision, license_name = UPSTREAM[framework]
        upstream = metadata[framework + ':' + path]
        urls = 'https://github.com/%s/blob/%s/%s' % (repository, revision, path)
        files = {}
        for variant in ('base', 'balanced', 'unbalanced'):
            if variant == 'base':
                content = body
            else:
                indent = lambda text: ''.join('  ' + line + '\n' for line in text.splitlines())
                other = body
                if variant == 'unbalanced':
                    other += '  let extra_request: text = call step(query) using m;\n'
                content = '  if route {\n' + indent(body) + '  } else {\n' + indent(other) + '  }\n'
            workflow_name = ''.join(x.title() for x in name.split('_')) + variant.title()
            text = '// Authored bounded projection; provenance: sourced/manifest.json\n'
            text += 'workflow %s budget 100000 {\n' % workflow_name
            text += PREAMBLE + content + '  output query;\n}\n'
            destination = OUT / variant / (name + '.orch')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text)
            files[variant] = {'path': str(destination.relative_to(HERE.parent)),
                              'sha256': hashlib.sha256(text.encode()).hexdigest(),
                              'expected': 'reject:E236' if variant == 'unbalanced' else 'accept'}
        rows.append({'id': name, 'framework': framework, 'source_url': urls,
                     'revision': revision, 'source_path': path,
                     'source_sha256': upstream['sha256'], 'source_lines': upstream['lines'],
                     'upstream_license': license_name, 'retained': retained,
                     'excluded_or_replaced': excluded,
                     'added_contracts': ['bounded common abstract input-token metric',
                         'provider caps (96; actors 50)', 'input/history/passage bounds',
                         'public/untrusted labels are author assignments',
                         'secret route and unequal-arm mutation are author experiments'],
                     'projection_status': 'partial abstraction; upstream behavior not executed',
                     'variants': files})
    manifest = {'format': 'orchlang-sourced-patterns', 'version': 1,
                'scope': '15 pinned source examples, 45 authored bounded variants; '
                         'not 15 full ports or 45 independent real applications',
                'execution': 'offline mock only; common abstract token metric',
                'selection': 'purposive examples from three DSL frameworks, selected after '
                             'compiler design; no independent annotator or held-out claim',
                'patterns': rows,
                'excluded_candidates': [
                    {'source': 'PDL examples/map-reduce/reduce.pdl',
                     'reason': 'pure numeric reduction contains no model requests'},
                    {'source': 'APPL examples/advanced/tree_of_thoughts/tot.py',
                     'reason': 'dynamic search frontier and Python state not represented'},
                    {'source': 'LangGraph dynamic agent and STORM examples',
                     'reason': 'graph routing, tools and state cannot be faithfully translated '
                               'to the current finite DSL'}]}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Generated %d source-derived patterns (%d files).' % (len(rows), 3 * len(rows)))


if __name__ == '__main__':
    generate()
