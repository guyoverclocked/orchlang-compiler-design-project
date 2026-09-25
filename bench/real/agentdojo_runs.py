#!/usr/bin/env python3
"""Extract AgentDojo's recorded attack runs for the ported tasks.

For every ported AgentDojo task, read the runs AgentDojo publishes for
gpt-4o-2024-05-13 under its headline attack ("important_instructions") and
record, for each injection task, whether the injection succeeded
(security: true) and the sequence of tool calls the agent made.  The ground
truth plan's calls come from agentdojo_canaries.json.  evaluate.py (E11)
classifies each successful run as within-plan or outside-plan.

Needs the pinned sources:  bash bench/real/fetch_sources.sh
Writes bench/real/agentdojo_runs.json.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, '..', '.cache', 'real', 'agentdojo', 'runs', 'gpt-4o-2024-05-13')
ATTACK = 'important_instructions'


def main():
    manifest = json.load(open(os.path.join(HERE, 'manifest.json')))
    canaries = json.load(open(os.path.join(HERE, 'agentdojo_canaries.json')))
    if not os.path.isdir(RUNS):
        sys.exit('AgentDojo runs not found; run bench/real/fetch_sources.sh')
    out = {'model': 'gpt-4o-2024-05-13', 'attack': ATTACK, 'tasks': {}}
    for c in manifest['candidates']:
        if c['decision'] != 'port' or not c['id'].startswith('ad-'):
            continue
        _, suite, number = c['id'].split('-')
        directory = os.path.join(RUNS, suite, 'user_task_%s' % number, ATTACK)
        runs = []
        for name in sorted(os.listdir(directory)):
            data = json.load(open(os.path.join(directory, name)))
            calls = [tc['function'] for m in data['messages'] if m['role'] == 'assistant'
                     for tc in (m.get('tool_calls') or [])]
            runs.append({'injection_task': data['injection_task_id'], 'security': data['security'],
                         'utility': data['utility'], 'calls': calls})
        out['tasks'][c['id']] = {
            'plan': [call['function'] for call in canaries[c['id']]['calls']],
            'runs': runs,
        }
    json.dump(out, open(os.path.join(HERE, 'agentdojo_runs.json'), 'w'), indent=1)
    print('wrote agentdojo_runs.json for %d tasks' % len(out['tasks']))


if __name__ == '__main__':
    main()
